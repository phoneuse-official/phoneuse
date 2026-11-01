import base64
import threading

from backend import streaming
from backend.usb import DeviceError


def test_mjpeg_failure_falls_back_to_usb_webdriver_screenshot(monkeypatch):
    frame = b'\xff\xd8test-jpeg\xff\xd9'
    published = threading.Event()
    monkeypatch.setattr(streaming, 'list_usb', lambda: [{'SerialNumber': 'device', 'DeviceID': 1}])
    monkeypatch.setattr(streaming, 'binding_for', lambda device: None)
    monkeypatch.setattr(streaming, 'connect', lambda *args: (_ for _ in ()).throw(DeviceError('no MJPEG')))
    monkeypatch.setattr(streaming.controller, '_perform', lambda *args: base64.b64encode(frame).decode())

    original_publish = streaming.FrameSource.publish

    def publish(source, data):
        original_publish(source, data)
        published.set()
        source.stopped.set()

    monkeypatch.setattr(streaming.FrameSource, 'publish', publish)
    source = streaming.FrameSource('device')
    assert published.wait(2)
    source.thread.join(timeout=2)

    assert not source.thread.is_alive()
    assert source.transport == 'wda-screenshot'
    assert source.frame == frame
    assert source.error is None


def test_screenshot_stop_while_waiting_for_lock_skips_capture(monkeypatch):
    source = streaming.FrameSource.__new__(streaming.FrameSource)
    source.device = 'device'
    source.stopped = threading.Event()
    acquired = threading.Event()
    released = threading.Event()
    calls = []

    class StopDuringAcquire:
        def acquire(self, timeout):
            source.stopped.set()
            acquired.set()
            return True

        def release(self):
            released.set()

    monkeypatch.setattr(streaming.controller, 'lock', lambda device: StopDuringAcquire())
    monkeypatch.setattr(streaming.controller, '_perform', lambda *args: calls.append(args))

    source._run_screenshots()

    assert acquired.is_set()
    assert released.is_set()
    assert calls == []
