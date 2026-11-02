"""Read-only USB discovery and HTTP transport to a device's WDA port."""
import http.client
import json
import plistlib
import re
import socket
import struct


class DeviceError(RuntimeError):
    pass


class OutcomeUnknown(DeviceError):
    pass


def read_exact(sock, count):
    result = bytearray()
    while len(result) < count:
        part = sock.recv(count - len(result))
        if not part:
            raise DeviceError("USB connection closed")
        result.extend(part)
    return bytes(result)


def mux_request(payload):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect('/var/run/usbmuxd')
        body = plistlib.dumps({"ProgName": "phoneuse-local", "ClientVersionString": "1.0", **payload})
        sock.sendall(struct.pack('<IIII', len(body) + 16, 1, 8, 1) + body)
        length, _, _, _ = struct.unpack('<IIII', read_exact(sock, 16))
        if not 16 <= length <= 4 * 1024 * 1024:
            raise DeviceError("USB returned invalid data")
        return sock, plistlib.loads(read_exact(sock, length - 16))
    except Exception:
        sock.close()
        raise


def list_usb():
    sock, result = mux_request({"MessageType": "ListDevices"})
    sock.close()
    return [x['Properties'] for x in result.get('DeviceList', [])
            if x['Properties'].get('ConnectionType') == 'USB']


def connect(device_id, port):
    sock, result = mux_request({"MessageType": "Connect", "DeviceID": device_id,
                                "PortNumber": socket.htons(port)})
    if result.get('Number') != 0:
        sock.close()
        raise DeviceError("Device port not open; start WebDriverAgent on the iPhone first" if port == 8100 else "Device service unavailable")
    return sock


def device_info(device):
    info = {"id": device['SerialNumber'], "name": "iPhone", "connection": "USB"}
    try:
        with connect(device['DeviceID'], 62078) as sock:
            for key, dest in [('DeviceName', 'name'), ('ProductType', 'model'), ('ProductVersion', 'ios')]:
                body = plistlib.dumps({"Request": "GetValue", "Key": key, "Label": "phoneuse-local"})
                sock.sendall(struct.pack('>I', len(body)) + body)
                length = struct.unpack('>I', read_exact(sock, 4))[0]
                if length > 1024 * 1024:
                    raise DeviceError("Device info response too large")
                data = plistlib.loads(read_exact(sock, length))
                info[dest] = data.get('Value', 'Unknown')
    except (OSError, DeviceError) as exc:
        info['error'] = str(exc)
    return info


class UsbHTTPConnection(http.client.HTTPConnection):
    def __init__(self, device_id):
        super().__init__('localhost', 8100, timeout=25)
        self.device_id = device_id

    def connect(self):
        self.sock = connect(self.device_id, 8100)
        self.sock.settimeout(self.timeout)


def wda_request(udid, method, path, body=None, *, binary=False, content_type=None, timeout=25):
    device = next((d for d in list_usb() if d['SerialNumber'] == udid), None)
    if device is None:
        raise DeviceError('The phone is offline')
    connection = UsbHTTPConnection(device['DeviceID'])
    connection.timeout = timeout
    try:
        connection.request(method, path, body=body if binary else (json.dumps(body) if body is not None else None),
                           headers={'Content-Type': content_type or 'application/json', 'Connection': 'close'})
        response = connection.getresponse()
        raw = response.read(24 * 1024 * 1024 + 1)
        if len(raw) > 24 * 1024 * 1024:
            raise DeviceError('Device response exceeded the size limit')
        result = json.loads(raw)
        value = result.get('value')
        if response.status >= 400 or isinstance(value, dict) and value.get('error'):
            if binary and isinstance(value, dict) and re.search(r'authori[sz]|\u6388\u6743', str(value.get('message', '')), re.I):
                raise OutcomeUnknown('Waiting for Photos permission: open WebDriverAgent on the iPhone, allow access, and check the photo library first. This request may still finish after permission is granted, so do not retry it directly')
            raise DeviceError(f"WDA: {value.get('error', response.status) if isinstance(value, dict) else response.status}")
        return result
    except (OSError, http.client.HTTPException, ValueError) as exc:
        if binary:
            raise OutcomeUnknown(f'The import response was interrupted ({type(exc).__name__}); the result is unknown. Check the photo library before retrying') from exc
        raise DeviceError(f'WebDriverAgent is unavailable: {type(exc).__name__}') from exc
    finally:
        connection.close()
