"""Prepare a trusted iPhone and keep its installed WDA running over iOS 17+ USB."""
import argparse
import fcntl
import signal
import subprocess
import threading
import time
import asyncio
import os
import plistlib
import sys
from pathlib import Path

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.installation_proxy import InstallationProxyService
from pymobiledevice3.services.mobile_image_mounter import PersonalizedImageMounter
from backend.usb import wda_request, DeviceError

parser = argparse.ArgumentParser()
parser.add_argument('udid')
parser.add_argument('--bundle-id', default=os.environ.get('PHONEUSE_WDA_BUNDLE_ID','com.facebook.WebDriverAgentRunner.xctrunner'))
parser.add_argument('--prepare-only', action='store_true')
parser.add_argument('--parent-pid', type=int)
args = parser.parse_args()
# The descriptor survives exec into the xcuitest launcher.
from backend.service import STATE
locks=STATE/'wda-locks';locks.mkdir(mode=0o700,exist_ok=True)
if not args.udid or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-' for c in args.udid):
    parser.error('设备标识无效')
lock_file=(locks/(args.udid+'.lock')).open('a')
try:
    fcntl.flock(lock_file,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:
    print('这个设备已有代理启动进程，请等待它完成或退出。',file=sys.stderr)
    raise SystemExit(75)
os.set_inheritable(lock_file.fileno(),True)
if args.parent_pid:
    if os.getpgrp()!=os.getpid():
        parser.error('受管模式需要独立进程组')
    def watch_parent():
        while True:
            if os.getppid()!=args.parent_pid:
                os.killpg(os.getpgrp(),signal.SIGTERM)
                return
            time.sleep(2)
    threading.Thread(target=watch_parent,daemon=True).start()


async def prepare():
    async with asyncio.timeout(90):
        async with await create_using_usbmux(serial=args.udid, autopair=False) as device:
            if not device.paired:
                raise RuntimeError('请先在手机上信任这台 Mac')
            if not await device.get_developer_mode_status():
                raise RuntimeError('请先开启开发者模式并完成重启确认')
            if args.bundle_id not in await InstallationProxyService(device).get_apps():
                raise RuntimeError('未安装指定的 WDA 代理应用')
            mounter = PersonalizedImageMounter(device)
            if not await mounter.is_image_mounted('Personalized'):
                root = Path('/Library/Developer/DeveloperDiskImages/iOS_DDI/Restore')
                manifest_path = root / 'BuildManifest.plist'
                if not manifest_path.exists():
                    raise RuntimeError('缺少本地开发者镜像，请安装对应 Apple 开发者支持组件')
                manifest = plistlib.loads(manifest_path.read_bytes())
                hardware = (await device.get_value(key='HardwareModel')).lower()
                identity = next((b for b in manifest['BuildIdentities'] if b['Info']['DeviceClass'].lower() == hardware), None)
                if not identity:
                    raise RuntimeError('本地开发者镜像不包含这个手机型号')
                entries = identity['Manifest']
                image = root / entries['PersonalizedDMG']['Info']['Path']
                trust = root / entries['LoadableTrustCache']['Info']['Path']
                await mounter.mount(image, manifest_path, trust)
            print('手机配对、开发者模式、代理应用和开发者镜像已就绪。', flush=True)


try:
    try:
        status = wda_request(args.udid, 'GET', '/status')
    except DeviceError:
        status = {}
    if status.get('value', {}).get('ready'):
        print('WDA 已在运行，无需重复启动。')
        raise SystemExit(0)
    asyncio.run(prepare())
    if not args.prepare_only:
        command=[sys.executable, '-m', 'pymobiledevice3', 'developer', 'dvt', 'xcuitest',
                 args.bundle_id, '--udid', args.udid, '--userspace']
        if args.parent_pid:
            child=subprocess.Popen(command,pass_fds=(lock_file.fileno(),))
            raise SystemExit(child.wait())
        os.execv(sys.executable,command)
except (RuntimeError, TimeoutError) as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(1)
