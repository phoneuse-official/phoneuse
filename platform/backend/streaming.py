"""One MJPEG reader per phone; subscribers always receive the newest frame."""
import base64
import http.client
import socket
import threading
import time

from .usb import DeviceError, connect, list_usb
from .service import controller
from .native_capture import binding_for, frames as native_frames

MAX_FRAME = 8 * 1024 * 1024
MAX_SUBSCRIBERS = 8  # Shared capture; each viewer receives only the latest frame.


def read_frame(stream):
    """Parse bounded multipart headers. Content-Length delimits binary JPEG data."""
    total, length = 0, None
    while True:
        line = stream.readline(8193)
        if not line:
            raise DeviceError('Video stream disconnected')
        total += len(line)
        if total > 8192:
            raise DeviceError('Video frame header too large')
        line = line.strip()
        if not line:
            if length is not None:
                break
            continue
        if line.lower().startswith(b'content-length:'):
            try:
                length = int(line.split(b':', 1)[1].strip())
            except ValueError:
                raise DeviceError('Invalid video frame length')
            if not 4 <= length <= MAX_FRAME:
                raise DeviceError('Video frame exceeds the size limit')
    data = stream.read(length)
    if len(data) != length or not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
        raise DeviceError('Video frame is corrupt or truncated')
    return data


class FrameSource:
    def __init__(self, device):
        self.device = device
        self.native_target = binding_for(device)
        self.transport = "native-usb" if self.native_target else "wda-mjpeg"
        self.condition = threading.Condition()
        self.stopped = threading.Event()
        self.socket = None
        self.seq = 0
        self.frame = None
        self.received_at = None
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True, name=f'mjpeg-{device[-8:]}')
        self.thread.start()

    def publish(self, frame):
        with self.condition:
            self.seq += 1
            self.frame = frame
            self.received_at = time.monotonic()
            self.condition.notify_all()

    def next(self, last_seq):
        with self.condition:
            self.condition.wait_for(lambda: self.seq != last_seq or self.error or self.stopped.is_set(), timeout=1)
            if self.error:
                raise DeviceError(self.error)
            if self.stopped.is_set():
                raise DeviceError('Video stream closed')
            if self.seq == last_seq:
                return None
            return self.seq, self.frame, self.received_at

    def _run(self):
        response = None
        try:
            device = next((d for d in list_usb() if d['SerialNumber'] == self.device), None)
            if not device:
                raise DeviceError('The phone is offline')
            if self.native_target:
                try:
                    for frame in native_frames(self.device,self.native_target,self.stopped):
                        self.publish(frame)
                    return
                except (DeviceError,OSError):
                    if self.stopped.is_set():return
                    self.transport='wda-mjpeg'

            try:
                sock = connect(device['DeviceID'], 9100)
                self.socket = sock
                if self.stopped.is_set():
                    return
                sock.settimeout(6)
                sock.sendall(b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
                response = http.client.HTTPResponse(sock)
                response.begin()
                if response.status != 200 or 'multipart/' not in response.getheader('Content-Type', ''):
                    raise DeviceError('The phone did not provide an MJPEG video stream')
                threading.Thread(target=self._configure,daemon=True).start()
                while not self.stopped.is_set():
                    self.publish(read_frame(response))
            except (DeviceError,OSError,http.client.HTTPException):
                if self.stopped.is_set():
                    return
                if response is not None:
                    response.close()
                    response=None
                if self.socket:
                    self.socket.close()
                    self.socket=None
                self.transport='wda-screenshot'
                self._run_screenshots()
        except Exception as exc:
            with self.condition:
                self.error = str(exc) if isinstance(exc, DeviceError) else 'Video connection interrupted; reconnect'
                self.condition.notify_all()
        finally:
            if response is not None:
                response.close()
            if self.socket:
                self.socket.close()

    def _run_screenshots(self):
        lock=controller.lock(self.device)
        while not self.stopped.is_set():
            if not lock.acquire(timeout=5):
                continue
            try:
                if self.stopped.is_set():
                    return
                try:
                    value=controller._perform(self.device,'screenshot',{})
                except DeviceError:
                    controller.sessions.pop(self.device,None)
                    raise
            finally:
                lock.release()
            if not isinstance(value,str) or len(value)>((MAX_FRAME+2)//3)*4:
                raise DeviceError('The phone returned an invalid or oversized screenshot')
            try:
                frame=base64.b64decode(value,validate=True)
            except (ValueError,TypeError):
                raise DeviceError('The phone returned an invalid screenshot')
            if not 4<=len(frame)<=MAX_FRAME or not (frame.startswith(b'\xff\xd8') and frame.endswith(b'\xff\xd9') or frame.startswith(b'\x89PNG\r\n\x1a\n')):
                raise DeviceError('The phone returned a screenshot in an invalid format')
            self.publish(frame)
            self.stopped.wait(.5)

    def _configure(self):
        # First frame never waits for a WDA control session or a running command.
        lock=controller.lock(self.device)
        if not lock.acquire(blocking=False):return
        try:
            if self.stopped.is_set():return
            settings=controller.stream_profiles.get(self.device, {'fps':60,'quality':50,'scale':75})
            try:controller._perform(self.device,'stream_settings',settings)
            except DeviceError:
                controller.sessions.pop(self.device,None)
                if not self.stopped.is_set():controller._perform(self.device,'stream_settings',settings)
        except Exception:pass  # Settings failure must not tear down healthy video.
        finally:lock.release()

    def stop(self):
        self.stopped.set()
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.socket.close()
        with self.condition:
            self.condition.notify_all()
        # Finish releasing the native capture before a replacement opens it.
        if self.native_target and threading.current_thread() is not self.thread:
            self.thread.join(timeout=3)


class StreamHub:
    def __init__(self, grace_seconds=10):
        self.lock=threading.RLock();self.sources={};self.timers={};self.grace_seconds=grace_seconds

    def subscribe(self, device):
        with self.lock:
            timer=self.timers.pop(device,None)
            if timer:timer.cancel()
            entry=self.sources.get(device)
            if entry and (entry[0].error or entry[0].stopped.is_set()):
                entry[0].stop();self.sources.pop(device);entry=None
            if entry is None:
                self.sources[device]=entry=[FrameSource(device),0]
            if entry[1]>=MAX_SUBSCRIBERS:raise DeviceError(f'At most {MAX_SUBSCRIBERS} video connections are allowed per phone. Close viewer tabs you are not using')
            entry[1]+=1
            return entry[0]

    def expire(self, device, source):
        with self.lock:
            entry=self.sources.get(device)
            if entry and entry[0] is source and entry[1]==0:
                self.sources.pop(device);self.timers.pop(device,None);source.stop()

    def unsubscribe(self, device, source):
        with self.lock:
            entry=self.sources.get(device)
            if entry and entry[0] is source:
                entry[1]-=1
                if entry[1]==0:
                    if self.grace_seconds<=0 or source.error:self.expire(device,source)
                    else:
                        timer=threading.Timer(self.grace_seconds,self.expire,args=(device,source));timer.daemon=True
                        self.timers[device]=timer;timer.start()

    def close(self):
        with self.lock:
            for timer in self.timers.values():timer.cancel()
            for source,_ in self.sources.values():source.stop()
            self.timers.clear();self.sources.clear()

hub=StreamHub()
