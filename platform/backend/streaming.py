"""One MJPEG reader per phone; subscribers always receive the newest frame."""
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
            raise DeviceError('视频流已断开')
        total += len(line)
        if total > 8192:
            raise DeviceError('视频帧头过大')
        line = line.strip()
        if not line:
            if length is not None:
                break
            continue
        if line.lower().startswith(b'content-length:'):
            try:
                length = int(line.split(b':', 1)[1].strip())
            except ValueError:
                raise DeviceError('视频帧长度无效')
            if not 4 <= length <= MAX_FRAME:
                raise DeviceError('视频帧长度超过限制')
    data = stream.read(length)
    if len(data) != length or not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
        raise DeviceError('视频帧损坏或截断')
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
                raise DeviceError('视频流已关闭')
            if self.seq == last_seq:
                return None
            return self.seq, self.frame, self.received_at

    def _run(self):
        response = None
        try:
            device = next((d for d in list_usb() if d['SerialNumber'] == self.device), None)
            if not device:
                raise DeviceError('手机已离线')
            if self.native_target:
                try:
                    for frame in native_frames(self.device,self.native_target,self.stopped):
                        self.publish(frame)
                    return
                except (DeviceError,OSError):
                    if self.stopped.is_set():return
                    if self.seq:raise
                    # Startup failure keeps an already usable WDA path available.
                    self.transport='wda-mjpeg'

            sock = connect(device['DeviceID'], 9100)
            self.socket = sock
            if self.stopped.is_set():
                return
            sock.settimeout(6)
            sock.sendall(b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
            response = http.client.HTTPResponse(sock)
            response.begin()
            if response.status != 200 or 'multipart/' not in response.getheader('Content-Type', ''):
                raise DeviceError('手机没有提供 MJPEG 视频流')
            threading.Thread(target=self._configure,daemon=True).start()
            while not self.stopped.is_set():
                self.publish(read_frame(response))
        except Exception as exc:
            with self.condition:
                self.error = str(exc) if isinstance(exc, DeviceError) else '视频连接中断，请重连'
                self.condition.notify_all()
        finally:
            if response is not None:
                response.close()
            if self.socket:
                self.socket.close()

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
            if entry[1]>=MAX_SUBSCRIBERS:raise DeviceError(f'同一手机最多允许{MAX_SUBSCRIBERS}个视频连接，请关闭不使用的观看页面')
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
