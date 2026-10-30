"""MCP stdio adapter. Every tool uses the same authenticated API as the UI."""
import os
from pathlib import Path
from urllib.parse import quote

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.utilities.types import Image

server = MCPServer('qunkong-iphone', instructions='先列出手机、获取使用权，再操作。坐标是 0 到 1 的屏幕比例。操作失败不得假定成功。')
BASE = os.environ.get('QUNKONG_API_URL', 'http://127.0.0.1:8765').rstrip('/')


def token():
    value = os.environ.get('QUNKONG_API_KEY')
    if value:
        return value
    path = os.environ.get('QUNKONG_TOKEN_FILE')
    if not path:
        raise ValueError('请设置 QUNKONG_API_KEY 或 QUNKONG_TOKEN_FILE')
    return Path(path).read_text().strip()


def request(method, path, data=None, binary=False):
    response = httpx.request(method, BASE + path, json=data, timeout=60,
                             headers={'Authorization': 'Bearer ' + token()}, trust_env=False)
    if response.is_error:
        raise ValueError(f"API {response.status_code}: {response.json().get('detail', '请求失败')}")
    return response.content if binary else response.json()


@server.tool()
def list_devices() -> dict:
    """列出当前凭证获准访问的已连接 iPhone 和自动化状态。"""
    return request('GET', '/api/devices')


@server.tool()
def acquire_device(device_id: str, seconds: int = 300) -> dict:
    """获取或续期手机使用权，30–3600 秒；占用他人的手机会失败。"""
    return request('POST', f'/api/devices/{quote(device_id, safe="")}/lease', {'seconds': seconds})


@server.tool()
def release_device(device_id: str) -> dict:
    """释放当前凭证占用的手机。"""
    return request('DELETE', f'/api/devices/{quote(device_id, safe="")}/lease')


@server.tool()
def screenshot(device_id: str) -> Image:
    """读取手机截图并返回图像；需要有效使用权。"""
    data = request('GET', f'/api/devices/{quote(device_id, safe="")}/screenshot', binary=True)
    return Image(data=data, format='png' if data.startswith(b'\x89PNG') else 'jpeg')


@server.tool()
def device_action(device_id: str, action: str, parameters: dict | None = None) -> dict:
    """执行动作。tap/long_press: x,y；swipe: x,y,x2,y2,duration_ms；坐标 0–1。
    pinch: x,y(0.2–0.8),scale(0.25–4),duration_ms；double_tap: x,y。
    clipboard_set: text；clipboard_get 返回文字（可能受 iOS 前台限制）。
    lock/unlock/locked: 锁屏/唤醒/状态；unlock 不绕过密码。
    alert_text/accept_alert/dismiss_alert: 读取/确认/取消当前弹窗；dismiss_keyboard: 收起键盘。
    text: text；launch_app/terminate_app: bundle_id；open_url: url；button: name(home/volumeup/volumedown)。
    无参数: home,status,source,window_size,active_app,battery,orientation。
    set_orientation: orientation(PORTRAIT/LANDSCAPE)。需要有效使用权。
    """
    return request('POST', f'/api/devices/{quote(device_id, safe="")}/actions', {**(parameters or {}), 'action': action})


@server.tool()
def page_source(device_id: str, fast: bool = True) -> dict:
    """读取页面树，默认精简XML，省去visible/accessible。不能据此假定节点可点击。
    fast=false读取原有完整树。需要设备使用权；这是当前快照，不是持续事件流。
    """
    return device_action(device_id, 'source_fast' if fast else 'source')


@server.tool()
def find_elements(device_id: str, query: str) -> dict:
    """按页面中已观察到的accessibility id/name查找元素。返回会话绑定句柄，可能零个或多个。
    不会点击；多匹配时先检查目标，不能盲选第一个。需要设备使用权。
    """
    return device_action(device_id, 'find_elements', {'query': query})


@server.tool()
def element_state(device_id: str, session_id: str, element_id: str) -> dict:
    """读取查询返回句柄的显示状态、启用状态和位置。失效时重新定位；状态不保证未被遮挡。"""
    return device_action(device_id, 'element_state', {'session_id': session_id, 'element_id': element_id})


@server.tool()
def click_element(device_id: str, session_id: str, element_id: str) -> dict:
    """检查元素显示且启用后点击一次。需使用权，任务占用时拒绝。失败不重放。
    返回成功只表示命令完成，必须再次读取页面或状态确认任务结果。句柄不能保存到录制工作流。
    """
    return device_action(device_id, 'element_click', {'session_id': session_id, 'element_id': element_id})


@server.tool()
def batch_action(device_ids: list[str], action: str, parameters: dict | None = None) -> dict:
    """对明确指定且已获取使用权的最多20台手机执行同一动作。返回逐台结果，不保证同时完成或整体回滚。"""
    return request('POST', '/api/batch', {'device_ids': device_ids, 'command': {**(parameters or {}), 'action': action}})


@server.tool()
def capabilities() -> dict:
    """获取已实现接口与尚未完成的能力清单。"""
    return request('GET', '/api/capabilities')


@server.tool()
def device_groups() -> dict:
    """列出当前凭证保存的设备分组，包含离线设备。"""
    return request('GET', '/api/groups')


@server.tool()
def save_device_group(name: str, device_ids: list[str]) -> dict:
    """保存或覆盖当前凭证的命名设备组，最多20台；不会自动获取使用权。"""
    return request('POST', '/api/groups', {'name': name, 'device_ids': device_ids})


@server.tool()
def delete_device_group(name: str) -> dict:
    """删除当前凭证的设备分组，不影响设备及使用权。"""
    return request('DELETE', '/api/groups/' + quote(name, safe=''))


@server.tool()
def list_apps(device_id: str) -> dict:
    """读取一台手机的已安装应用、版本和保护状态，需要有效使用权。"""
    return request('GET', f'/api/devices/{quote(device_id, safe="")}/apps')


@server.tool()
def upload_asset(file_path: str) -> dict:
    """上传 MCP 进程所在电脑上的 IPA/PNG/JPEG/MP4/MOV 文件。最大128 MB，媒体最大50 MB。仅上传，不自动安装或导入。返回 asset id。"""
    path = Path(file_path).expanduser()
    if not path.is_file() or path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError('文件不存在或超过128 MB')
    with path.open('rb') as content:
        response = httpx.post(BASE + '/api/assets', params={'filename': path.name}, content=content,
            headers={'Authorization': 'Bearer ' + token(), 'Content-Type': 'application/octet-stream'},
            timeout=180, trust_env=False)
    if response.is_error:
        raise ValueError(f"API {response.status_code}: {response.json().get('detail', '上传失败')}")
    return response.json()


@server.tool()
def list_assets() -> dict:
    """列出当前凭证上传的文件，不返回文件内容。"""
    return request('GET', '/api/assets')


@server.tool()
def delete_asset(asset_id: str) -> dict:
    """删除节点保存的上传文件；不会删除手机中的应用或相册内容。有待执行任务引用时拒绝删除。"""
    return request('DELETE', '/api/assets/' + quote(asset_id, safe=''))


@server.tool()
def list_workflows() -> dict:
    """读取当前凭证保存的工作流及步骤，可能包含输入的文字。"""
    return request('GET', '/api/workflows')


@server.tool()
def save_workflow(name: str, steps: list[dict], workflow_id: str | None = None) -> dict:
    """保存最多100步的工作流。每步形如 {command:{action:'tap',x:0.5,y:0.5},wait_ms:500}。wait_ms为执行前等待，最多60000。传入workflow_id则更新自己的工作流。不会执行。"""
    return request('POST', '/api/workflows', {'name': name, 'steps': steps, **({'id': workflow_id} if workflow_id else {})})


@server.tool()
def delete_workflow(workflow_id: str) -> dict:
    """删除工作流模板。已提交任务使用独立快照，不会随模板删除而取消。"""
    return request('DELETE', '/api/workflows/' + quote(workflow_id, safe=''))


@server.tool()
def create_job(kind: str, device_ids: list[str], workflow_id: str | None = None,
               asset_id: str | None = None, bundle_id: str | None = None, confirm_uninstall: bool = False,
               run_at: float | None = None, repeat: int = 1, interval_ms: int = 0, on_error: str = 'stop') -> dict:
    """创建任务：kind=workflow/install/media/uninstall，对应workflow_id/asset_id/bundle_id。
    run_at为未来30天内的Unix秒，省略则排队执行。workflow可循环1–100次，失败策略stop/continue，不重试失败步骤。
    执行时尝试获取空闲或自己占用的设备，不抢占其他用户。卸载删除应用数据，必须明确confirm_uninstall=true；不可卸载控制代理和系统应用。
    返回任务标识；必须查询任务结果才能判断成功。Mac服务需保持运行。
    """
    params = dict(kind=kind, device_ids=device_ids, workflow_id=workflow_id, asset_id=asset_id,
                  bundle_id=bundle_id, confirm_uninstall=confirm_uninstall, run_at=run_at,
                  repeat=repeat, interval_ms=interval_ms, on_error=on_error)
    return request('POST', '/api/jobs', {k: v for k, v in params.items() if v is not None})


@server.tool()
def list_jobs() -> dict:
    """读取当前凭证最近100个任务的状态及逐台结果，不返回工作流输入内容。"""
    return request('GET', '/api/jobs')


@server.tool()
def get_job(job_id: str) -> dict:
    """查询单个任务是否完成、失败或中断及逐台进度。"""
    return request('GET', '/api/jobs/' + quote(job_id, safe=''))


@server.tool()
def cancel_job(job_id: str) -> dict:
    """取消排队任务或请求停止运行任务。在操作边界停止，不撤销已经发给手机的动作、安装或导入。"""
    return request('POST', '/api/jobs/' + quote(job_id, safe='') + '/cancel')


@server.tool()
def recovery_status() -> dict:
    """查看获准设备的代理健康、自动恢复状态与最近恢复记录。"""
    return request('GET', '/api/recovery')


@server.tool()
def configure_recovery(device_id: str, enabled: bool) -> dict:
    """节点管理员开启或关闭指定设备的自动恢复。开启会在代理故障且设备空闲时尝试启动代理；不重放任务。连续失败后再次开启会重置重试计数。关闭不停止健康代理。"""
    return request('POST', '/api/devices/' + quote(device_id, safe='') + '/recovery', {'enabled': enabled})


if __name__ == '__main__':
    server.run()
