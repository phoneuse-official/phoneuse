"""Private, explicitly bound macOS USB screen capture. No network listener."""
import contextlib
import json
import os
import selectors
import struct
import subprocess
import time
from pathlib import Path
from .usb import DeviceError

ROOT=Path(__file__).resolve().parents[1]
MAX_FRAME=8*1024*1024

def binding_for(device):
    state=Path(os.environ.get('QUNKONG_STATE_DIR',ROOT/'.state'))
    try:
        bindings=json.loads((state/'native-capture.json').read_text())
        target=bindings.get(device)
        if not isinstance(target,str) or not target or len(target)>256:return None
        # A screen must never be assigned to two device identities.
        if list(bindings.values()).count(target)!=1:return None
        if not (ROOT/'.state/bin/capture-phone').is_file():return None
        return target
    except (OSError,ValueError,AttributeError):return None

class FrameDecoder:
    def __init__(self):self.pending=bytearray();self.length=None
    def feed(self, data):
        self.pending.extend(data)
        while True:
            if self.length is None:
                if len(self.pending)<4:return
                self.length=struct.unpack('!I',self.pending[:4])[0];del self.pending[:4]
                if not 4<=self.length<=MAX_FRAME:raise DeviceError('原生视频帧长度无效')
            if len(self.pending)<self.length:return
            frame=bytes(self.pending[:self.length]);del self.pending[:self.length];self.length=None
            if not frame.startswith(b'\xff\xd8') or not frame.endswith(b'\xff\xd9'):raise DeviceError('原生视频帧损坏')
            yield frame


def frames(device, target, stopped):
    from .service import controller
    process=None
    try:
        process=subprocess.Popen([str(ROOT/'.state/bin/capture-phone'),'--stream',target,'0'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
        os.set_blocking(process.stdout.fileno(),False);os.set_blocking(process.stdin.fileno(),False)
        decoder=FrameDecoder();last_frame=time.monotonic();profile=None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout,selectors.EVENT_READ)
            while not stopped.is_set():
                requested=controller.stream_profiles.get(device,{'fps':60,'quality':45,'scale':75})
                if requested!=profile:
                    try:
                        os.write(process.stdin.fileno(),(json.dumps(requested)+'\n').encode());profile=dict(requested)
                    except BlockingIOError:pass
                events=selector.select(timeout=.5)
                if not events:
                    if time.monotonic()-last_frame>12:raise DeviceError('原生USB视频等待超时，正在恢复')
                    continue
                try:data=os.read(process.stdout.fileno(),65536)
                except BlockingIOError:continue
                if not data:raise DeviceError('原生USB屏幕采集已退出，正在恢复')
                for frame in decoder.feed(data):
                    last_frame=time.monotonic()
                    yield frame
    finally:
        if process:
            if process.poll() is None:
                with contextlib.suppress(ProcessLookupError):process.terminate()
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    with contextlib.suppress(ProcessLookupError):process.kill()
                    process.wait(timeout=2)
            for pipe in (process.stdin,process.stdout):
                if pipe:pipe.close()
