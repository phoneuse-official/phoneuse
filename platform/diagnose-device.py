"""Bounded diagnostics. Never installs apps or modifies the phone."""
import asyncio
import json
from pathlib import Path

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.installation_proxy import InstallationProxyService
from backend.usb import list_usb, device_info, wda_request, DeviceError


async def diagnose(device):
    result = device_info(device)
    try:
        async with asyncio.timeout(20):
            async with await create_using_usbmux(serial=result['id'], autopair=False) as lockdown:
                result['paired'] = lockdown.paired
                if lockdown.paired:
                    result['developer_mode'] = await lockdown.get_value(
                        domain='com.apple.security.mac.amfi', key='DeveloperModeStatus')
                    apps = await InstallationProxyService(lockdown).get_apps()
                    result['automation_apps'] = [
                        {'id': bid, 'name': app.get('CFBundleDisplayName'), 'version': app.get('CFBundleVersion')}
                        for bid, app in apps.items() if any(word in (bid+' '+str(app.get('CFBundleDisplayName',''))).lower()
                                                           for word in ['panda', 'webdriver', 'xctrunner', 'easyclick'])]
                else:
                    result['next_step'] = '解锁手机并信任此电脑，然后重新诊断。'
    except Exception as exc:
        result['diagnostic_error'] = type(exc).__name__ + ': ' + str(exc)
    try:
        result['wda'] = wda_request(result['id'], 'GET', '/status')
    except DeviceError as exc:
        result['wda_error'] = str(exc)
    return result


async def main():
    results = await asyncio.gather(*(diagnose(d) for d in list_usb()))
    output = json.dumps(results, ensure_ascii=False, indent=2)
    (Path(__file__).resolve().parent / 'device-diagnostic.json').write_text(output)
    print(output)


asyncio.run(main())
