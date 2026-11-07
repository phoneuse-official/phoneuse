import base64
import time
from backend import inventory as inventory_module, recovery
from backend.usb import DeviceError, UI_AUTOMATION_GUIDANCE


def make_inventory():
    inv = inventory_module.Inventory()
    inv.items = {'phone': {'id': 'phone', 'online': True, 'usb_id': 1, 'model': 'test', 'metadata_at': time.time()}}
    return inv


def test_status_ready_does_not_hide_authorization_failure(monkeypatch):
    inv = make_inventory()
    def request(device, method, path, **kwargs):
        if path == '/status': return {'value': {'ready': True}}
        raise DeviceError(UI_AUTOMATION_GUIDANCE, code='ui_automation_unauthorized')
    monkeypatch.setattr(inventory_module, 'wda_request', request)
    inv.probe({'SerialNumber': 'phone'}, 1)
    item = inv.snapshot()[0]
    assert item['wda_reachable'] is True
    assert item['automation'] == 'unauthorized'
    assert item['health_code'] == 'ui_automation_unauthorized'
    assert 'Enable UI Automation' in item['detail']


def test_health_ready_after_valid_capture(monkeypatch):
    inv = make_inventory()
    monkeypatch.setattr(inventory_module, 'wda_request', lambda device, method, path, **kwargs:
        {'value': {'ready': True}} if path == '/status' else {'value': base64.b64encode(b'\xff\xd8image\xff\xd9').decode()})
    inv.probe({'SerialNumber': 'phone'}, 1)
    assert inv.snapshot()[0]['automation'] == 'ready'
    assert inv.snapshot()[0]['screen_capture'] == 'ready'


def test_external_runner_is_not_restarted(monkeypatch):
    supervisor = recovery.Supervisor()
    messages = []
    monkeypatch.setattr(supervisor, 'state', lambda device, phase, detail, **extra: messages.append((phase, detail)))
    monkeypatch.setattr(recovery.inventory, 'snapshot', lambda: [{'id': 'phone', 'checked_at': time.time(), 'automation': 'unauthorized', 'wda_reachable': True, 'detail': UI_AUTOMATION_GUIDANCE}])
    monkeypatch.setattr(supervisor, 'spawn', lambda device: (_ for _ in ()).throw(AssertionError('must not restart external WDA')))
    supervisor.tick_device({'device': 'phone', 'enabled': True, 'updated': 1}, {'phone'})
    assert messages[-1][0] == 'needs_attention'
    assert 'externally managed' in messages[-1][1]
