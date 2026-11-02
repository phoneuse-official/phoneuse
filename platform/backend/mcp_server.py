"""MCP stdio adapter. Every tool uses the same authenticated API as the UI."""
import os
from pathlib import Path
from urllib.parse import quote

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.utilities.types import Image

from .config import setting

server = MCPServer('phoneuse-local', instructions='List phones and acquire a lease before acting. Coordinates are screen fractions from 0 to 1. Never assume a failed action succeeded.')
BASE = (setting('API_URL') or 'http://127.0.0.1:8765').rstrip('/')


def token():
    value = setting('API_KEY')
    if value:
        return value
    path = setting('TOKEN_FILE')
    if not path:
        raise ValueError('Set PHONEUSE_API_KEY or PHONEUSE_TOKEN_FILE')
    return Path(path).read_text().strip()


def request(method, path, data=None, binary=False):
    response = httpx.request(method, BASE + path, json=data, timeout=60,
                             headers={'Authorization': 'Bearer ' + token()}, trust_env=False)
    if response.is_error:
        raise ValueError(f"API {response.status_code}: {response.json().get('detail', 'request failed')}")
    return response.content if binary else response.json()


@server.tool()
def list_devices() -> dict:
    """List connected iPhones this API key can access, with their automation status."""
    return request('GET', '/api/devices')


@server.tool()
def acquire_device(device_id: str, seconds: int = 300) -> dict:
    """Acquire or renew a phone lease for 30–3600 seconds. Fails if another user holds the phone."""
    return request('POST', f'/api/devices/{quote(device_id, safe="")}/lease', {'seconds': seconds})


@server.tool()
def release_device(device_id: str) -> dict:
    """Release a phone held by this API key."""
    return request('DELETE', f'/api/devices/{quote(device_id, safe="")}/lease')


@server.tool()
def screenshot(device_id: str) -> Image:
    """Take a screenshot of the phone and return the image. Requires an active lease."""
    data = request('GET', f'/api/devices/{quote(device_id, safe="")}/screenshot', binary=True)
    return Image(data=data, format='png' if data.startswith(b'\x89PNG') else 'jpeg')


@server.tool()
def device_action(device_id: str, action: str, parameters: dict | None = None) -> dict:
    """Run one action. Coordinates are screen fractions from 0 to 1.
    tap/long_press/double_tap: x,y. swipe: x,y,x2,y2,duration_ms.
    pinch: x,y (0.2–0.8), scale (0.25–4), duration_ms.
    clipboard_set: text. clipboard_get returns text (iOS may limit this to the foreground app).
    lock/unlock/locked: lock, wake or read lock state; unlock does not bypass the passcode.
    alert_text/accept_alert/dismiss_alert: read, accept or dismiss the current alert. dismiss_keyboard: hide the keyboard.
    text: text. launch_app/terminate_app: bundle_id. open_url: url. button: name (home/volumeup/volumedown).
    No parameters: home, status, source, window_size, active_app, battery, orientation.
    set_orientation: orientation (PORTRAIT/LANDSCAPE). Requires an active lease.
    """
    return request('POST', f'/api/devices/{quote(device_id, safe="")}/actions', {**(parameters or {}), 'action': action})


@server.tool()
def page_source(device_id: str, fast: bool = True) -> dict:
    """Read the UI tree. By default this is compact XML without visible/accessible attributes;
    a node in it is not proof that it can be tapped. fast=false reads the full tree.
    Requires a lease. This is a snapshot, not a live event stream.
    """
    return device_action(device_id, 'source_fast' if fast else 'source')


@server.tool()
def find_elements(device_id: str, query: str) -> dict:
    """Find elements by an accessibility id/name already seen on screen. Returns session-bound handles; there may be none or several.
    Does not tap. With several matches, check the target first; never blindly pick the first. Requires a lease.
    """
    return device_action(device_id, 'find_elements', {'query': query})


@server.tool()
def element_state(device_id: str, session_id: str, element_id: str) -> dict:
    """Read whether a found element is displayed and enabled, and where it is. Find it again if the handle expired; this does not prove nothing covers it."""
    return device_action(device_id, 'element_state', {'session_id': session_id, 'element_id': element_id})


@server.tool()
def click_element(device_id: str, session_id: str, element_id: str) -> dict:
    """Tap an element once after checking it is displayed and enabled. Requires a lease; refused while a job holds the phone. Never replayed on failure.
    Success only means the command finished; read the screen again to confirm the outcome. Handles cannot be saved into workflows.
    """
    return device_action(device_id, 'element_click', {'session_id': session_id, 'element_id': element_id})


@server.tool()
def batch_action(device_ids: list[str], action: str, parameters: dict | None = None) -> dict:
    """Run the same action on up to 20 listed phones you hold leases for. Returns per-phone results; not simultaneous and not rolled back as a whole."""
    return request('POST', '/api/batch', {'device_ids': device_ids, 'command': {**(parameters or {}), 'action': action}})


@server.tool()
def capabilities() -> dict:
    """List the implemented capabilities and the ones not built yet."""
    return request('GET', '/api/capabilities')


@server.tool()
def device_groups() -> dict:
    """List device groups saved for this API key, including offline phones."""
    return request('GET', '/api/groups')


@server.tool()
def save_device_group(name: str, device_ids: list[str]) -> dict:
    """Save or replace a named device group for this API key (up to 20 phones). Does not acquire leases."""
    return request('POST', '/api/groups', {'name': name, 'device_ids': device_ids})


@server.tool()
def delete_device_group(name: str) -> dict:
    """Delete a device group for this API key. Phones and leases are not affected."""
    return request('DELETE', '/api/groups/' + quote(name, safe=''))


@server.tool()
def list_apps(device_id: str) -> dict:
    """List installed apps on a phone with versions and protection status. Requires an active lease."""
    return request('GET', f'/api/devices/{quote(device_id, safe="")}/apps')


@server.tool()
def upload_asset(file_path: str) -> dict:
    """Upload an IPA/PNG/JPEG/MP4/MOV file from the computer running this MCP server. Up to 128 MB; photos and videos up to 50 MB. Upload only: nothing is installed or imported. Returns an asset id."""
    path = Path(file_path).expanduser()
    if not path.is_file() or path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError('File not found or larger than 128 MB')
    with path.open('rb') as content:
        response = httpx.post(BASE + '/api/assets', params={'filename': path.name}, content=content,
            headers={'Authorization': 'Bearer ' + token(), 'Content-Type': 'application/octet-stream'},
            timeout=180, trust_env=False)
    if response.is_error:
        raise ValueError(f"API {response.status_code}: {response.json().get('detail', 'upload failed')}")
    return response.json()


@server.tool()
def list_assets() -> dict:
    """List files uploaded with this API key. File contents are not returned."""
    return request('GET', '/api/assets')


@server.tool()
def delete_asset(asset_id: str) -> dict:
    """Delete an uploaded file stored on this Mac. Apps and photos already on the phone stay. Refused while a pending job uses it."""
    return request('DELETE', '/api/assets/' + quote(asset_id, safe=''))


@server.tool()
def list_workflows() -> dict:
    """List saved workflows and their steps for this API key. Steps may contain typed text."""
    return request('GET', '/api/workflows')


@server.tool()
def save_workflow(name: str, steps: list[dict], workflow_id: str | None = None) -> dict:
    """Save a workflow of up to 100 steps. Each step looks like {command:{action:'tap',x:0.5,y:0.5},wait_ms:500}. wait_ms is the wait before the step, up to 60000. Pass workflow_id to update your own workflow. Does not run it."""
    return request('POST', '/api/workflows', {'name': name, 'steps': steps, **({'id': workflow_id} if workflow_id else {})})


@server.tool()
def delete_workflow(workflow_id: str) -> dict:
    """Delete a workflow template. Jobs already submitted keep their own snapshot and are not cancelled."""
    return request('DELETE', '/api/workflows/' + quote(workflow_id, safe=''))


@server.tool()
def create_job(kind: str, device_ids: list[str], workflow_id: str | None = None,
               asset_id: str | None = None, bundle_id: str | None = None, confirm_uninstall: bool = False,
               run_at: float | None = None, repeat: int = 1, interval_ms: int = 0, on_error: str = 'stop') -> dict:
    """Create a job: kind=workflow/install/media/uninstall with workflow_id/asset_id/bundle_id.
    run_at is a Unix time within the next 30 days; omit it to queue now. Workflows repeat 1–100 times; on_error is stop/continue; failed steps are not retried.
    Uses phones that are free or already held by you; never takes a phone from another user. Uninstall deletes app data and needs confirm_uninstall=true; WebDriverAgent and system apps cannot be uninstalled.
    Returns a job id; read the job result to know whether it succeeded. The Mac service must keep running.
    """
    params = dict(kind=kind, device_ids=device_ids, workflow_id=workflow_id, asset_id=asset_id,
                  bundle_id=bundle_id, confirm_uninstall=confirm_uninstall, run_at=run_at,
                  repeat=repeat, interval_ms=interval_ms, on_error=on_error)
    return request('POST', '/api/jobs', {k: v for k, v in params.items() if v is not None})


@server.tool()
def list_jobs() -> dict:
    """List the latest 100 jobs for this API key with per-phone results. Workflow inputs are not returned."""
    return request('GET', '/api/jobs')


@server.tool()
def get_job(job_id: str) -> dict:
    """Read whether one job finished, failed or was interrupted, with per-phone progress."""
    return request('GET', '/api/jobs/' + quote(job_id, safe=''))


@server.tool()
def cancel_job(job_id: str) -> dict:
    """Cancel a queued job or ask a running job to stop. It stops at the next action boundary and does not undo actions, installs or imports already sent to the phone."""
    return request('POST', '/api/jobs/' + quote(job_id, safe='') + '/cancel')


@server.tool()
def recovery_status() -> dict:
    """Show WDA health, automatic recovery state and recent recovery events for phones you can access."""
    return request('GET', '/api/recovery')


@server.tool()
def configure_recovery(device_id: str, enabled: bool) -> dict:
    """Turn automatic recovery on or off for a phone (local administrator only). When on, a failed WDA is restarted while the phone is idle; tasks are not replayed. Turning it on again after repeated failures resets the retry count. Turning it off does not stop a healthy WDA."""
    return request('POST', '/api/devices/' + quote(device_id, safe='') + '/recovery', {'enabled': enabled})


if __name__ == '__main__':
    server.run()
