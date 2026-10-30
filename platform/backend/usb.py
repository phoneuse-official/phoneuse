"""Read-only USB discovery and HTTP transport to a device's WDA port."""
import http.client
import json
import plistlib
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
            raise DeviceError("USB 连接已断开")
        result.extend(part)
    return bytes(result)


def mux_request(payload):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect('/var/run/usbmuxd')
        body = plistlib.dumps({"ProgName": "qunkong", "ClientVersionString": "1.0", **payload})
        sock.sendall(struct.pack('<IIII', len(body) + 16, 1, 8, 1) + body)
        length, _, _, _ = struct.unpack('<IIII', read_exact(sock, 16))
        if not 16 <= length <= 4 * 1024 * 1024:
            raise DeviceError("USB 返回无效数据")
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
        raise DeviceError("设备端口未开启；请先启动手机自动化服务" if port == 8100 else "设备服务不可用")
    return sock


def device_info(device):
    info = {"id": device['SerialNumber'], "name": "iPhone", "connection": "USB"}
    try:
        with connect(device['DeviceID'], 62078) as sock:
            for key, dest in [('DeviceName', 'name'), ('ProductType', 'model'), ('ProductVersion', 'ios')]:
                body = plistlib.dumps({"Request": "GetValue", "Key": key, "Label": "qunkong"})
                sock.sendall(struct.pack('>I', len(body)) + body)
                length = struct.unpack('>I', read_exact(sock, 4))[0]
                if length > 1024 * 1024:
                    raise DeviceError("设备信息过大")
                data = plistlib.loads(read_exact(sock, length))
                info[dest] = data.get('Value', '未知')
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
        raise DeviceError('手机已离线')
    connection = UsbHTTPConnection(device['DeviceID'])
    connection.timeout = timeout
    try:
        connection.request(method, path, body=body if binary else (json.dumps(body) if body is not None else None),
                           headers={'Content-Type': content_type or 'application/json', 'Connection': 'close'})
        response = connection.getresponse()
        raw = response.read(24 * 1024 * 1024 + 1)
        if len(raw) > 24 * 1024 * 1024:
            raise DeviceError('设备响应超过限制')
        result = json.loads(raw)
        value = result.get('value')
        if response.status >= 400 or isinstance(value, dict) and value.get('error'):
            if binary and isinstance(value, dict) and '授权' in str(value.get('message', '')):
                raise OutcomeUnknown('等待相册授权：请打开 WebDriverAgent 完成授权，并先检查相册。本次请求可能在授权后完成，勿直接重试')
            raise DeviceError(f"WDA: {value.get('error', response.status) if isinstance(value, dict) else response.status}")
        return result
    except (OSError, http.client.HTTPException, ValueError) as exc:
        if binary:
            raise OutcomeUnknown(f'导入响应中断：{type(exc).__name__}，结果未确认，请先检查手机相册，勿直接重试') from exc
        raise DeviceError(f'手机自动化服务不可用：{type(exc).__name__}') from exc
    finally:
        connection.close()
