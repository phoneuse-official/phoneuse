"""USB application management using the installed pymobiledevice3 API."""
import asyncio
import re
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.installation_proxy import InstallationProxyService
from .usb import DeviceError, OutcomeUnknown
from pymobiledevice3.exceptions import AppInstallError
from .assets import RUNNER


async def _operation(device, operation, value=None, progress=None):
    async with await create_using_usbmux(serial=device, connection_type='USB', pair_timeout=5) as lockdown:
        async with InstallationProxyService(lockdown) as proxy:
            if operation == 'list':
                apps = await proxy.get_apps()
                return sorted([{'bundle_id': bundle, 'name': str(a.get('CFBundleDisplayName', a.get('CFBundleName', bundle))),
                                'version': str(a.get('CFBundleShortVersionString', '')), 'type': a.get('ApplicationType', 'Unknown'),
                                'protected': bundle == RUNNER or a.get('ApplicationType') != 'User'}
                               for bundle, a in apps.items()], key=lambda a: a['name'].lower())
            if operation == 'install':
                await proxy.install_from_local(value, handler=progress)
            elif operation == 'uninstall':
                apps = await proxy.get_apps(bundle_identifiers=[value])
                if value == RUNNER or value not in apps or apps[value].get('ApplicationType') != 'User':
                    raise DeviceError('Only installed user apps can be removed; WebDriverAgent and system apps cannot')
                await proxy.uninstall(value, handler=progress)
            return {'completed': True}


def operate(device, operation, value=None, progress=None):
    async def bounded():
        return await asyncio.wait_for(_operation(device, operation, value, progress), 600 if operation == 'install' else 60)
    try:
        return asyncio.run(bounded())
    except DeviceError:
        raise
    except Exception as exc:
        # Do not include arbitrary app metadata or filesystem paths in audit errors.
        code = str(exc).split(':', 1)[0]
        code = code if re.fullmatch(r'[A-Za-z][A-Za-z0-9]{2,80}', code) else type(exc).__name__
        error = DeviceError if operation == 'list' or isinstance(exc, AppInstallError) else OutcomeUnknown
        raise error(f'The iPhone app service returned {code}. If the operation started, check the phone; do not retry automatically') from exc
