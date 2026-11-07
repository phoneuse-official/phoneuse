import base64
import asyncio
import contextlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .service import LeaseError, authenticate, controller, database, allowed
from .usb import DeviceError
from .streaming import hub
from .models import Action
from . import jobs, task_api, recovery, codex_api, demo
from .inventory import inventory as device_cache

@contextlib.asynccontextmanager
async def lifespan(app):
    device_cache.start()
    jobs.scheduler.start()
    recovery.supervisor.start()
    try:
        yield
    finally:
        demo.manager.stop()
        codex_api.manager.stop()
        jobs.scheduler.stop()
        recovery.supervisor.stop()
        device_cache.stop()
        hub.close()


app = FastAPI(lifespan=lifespan, title='PhoneUse Local API', version='0.1.0', description='Local API for USB-connected iPhones on this Mac. Every device action needs an API key and an active phone lease.')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:3109', 'http://127.0.0.1:3109'],
                   allow_methods=['GET', 'POST', 'DELETE'], allow_headers=['Authorization', 'Content-Type'])


@app.middleware('http')
async def local_security(request: Request, call_next):
    origin = request.headers.get('origin')
    if origin and origin not in ('http://localhost:3109', 'http://127.0.0.1:3109',
                                  'http://localhost:8765', 'http://127.0.0.1:8765'):
        return JSONResponse({'detail': 'Origin not allowed'}, status_code=403)
    try:
        size = int(request.headers.get('content-length', '0'))
    except ValueError:
        return JSONResponse({'detail': 'Invalid Content-Length'}, status_code=400)
    limit = 128 * 1024 * 1024 if request.url.path == '/api/assets' and request.method == 'POST' else 1024 * 1024
    if size < 0 or size > limit:
        return JSONResponse({'detail': 'Request too large'}, status_code=413)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


bearer = HTTPBearer(auto_error=False)


def owner(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    user = authenticate(credentials.credentials if credentials else '')
    if user is None:
        raise HTTPException(401, 'A valid API key is required')
    return user


@app.exception_handler(DeviceError)
async def device_error(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=409 if isinstance(exc, LeaseError) else 503)


@app.exception_handler(PermissionError)
async def permission_error(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=403)


class Lease(BaseModel):
    seconds: int = Field(default=300, ge=30, le=3600)


class StreamSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fps: int = Field(default=30, ge=5, le=60)
    quality: int = Field(default=50, ge=10, le=90)
    scale: int = Field(default=75, ge=25, le=100)




class DeviceGroup(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=60)
    device_ids: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode='after')
    def valid_name(self):
        self.name = self.name.strip()
        if not self.name or self.name in ('.', '..') or any(ord(c) < 32 or c in '/\\' for c in self.name):
            raise ValueError('Group names cannot be empty or contain path separators or control characters')
        return self


@app.get('/api/groups')
def groups(user=Depends(owner)):
    with database() as db:
        rows = db.execute('SELECT name,devices FROM device_groups WHERE owner=? ORDER BY name', (user['hash'],)).fetchall()
    return {'groups': [{'name': r['name'], 'device_ids': [d for d in json.loads(r['devices']) if allowed(user, d)]} for r in rows]}


@app.post('/api/groups')
def save_group(body: DeviceGroup, user=Depends(owner)):
    ids = list(dict.fromkeys(body.device_ids))
    if any(not allowed(user, d) for d in ids):
        raise PermissionError('The group includes a phone this API key cannot access')
    with database() as db:
        db.execute('INSERT OR REPLACE INTO device_groups VALUES (?,?,?)', (user['hash'], body.name, json.dumps(ids)))
    return {'name': body.name, 'device_ids': ids}


@app.delete('/api/groups/{name}')
def delete_group(name: str, user=Depends(owner)):
    with database() as db:
        db.execute('DELETE FROM device_groups WHERE owner=? AND name=?', (user['hash'], name))
    return {'deleted': True}


class Batch(BaseModel):
    device_ids: list[str] = Field(min_length=1, max_length=20)
    command: Action


@app.get('/health')
def health():
    return {'ok': True, 'mode': 'local-device-node', 'version': '0.1.0'}


@app.get('/api/devices')
def devices(user=Depends(owner)):
    items=controller.inventory(user)
    states={r['device']:r for r in recovery.supervisor.snapshot(user)}
    for d in items:d['recovery']=states.get(d['id'])
    return {'devices':items}


@app.post('/api/devices/{device}/lease')
def acquire(device: str, body: Lease, user=Depends(owner)):
    return controller.acquire(user, device, body.seconds)


@app.delete('/api/devices/{device}/lease')
def release(device: str, user=Depends(owner)):
    return controller.release(user, device)


@app.post('/api/devices/{device}/actions')
def action(device: str, body: Action, user=Depends(owner)):
    return {'value': controller.perform(user, device, body.action, body.model_dump(exclude_none=True))}


@app.get('/api/devices/{device}/screenshot')
def screenshot(device: str, user=Depends(owner)):
    value = controller.perform(user, device, 'screenshot', {})
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        raise DeviceError('The phone returned an invalid screenshot')
    content_type = 'image/png' if data.startswith(b'\x89PNG') else 'image/jpeg'
    return Response(data, media_type=content_type)


@app.post('/api/batch')
def batch(body: Batch, user=Depends(owner)):
    device_ids = list(dict.fromkeys(body.device_ids))
    # Preflight authorization; execution is per-device and explicitly non-atomic.
    for device in device_ids:
        controller.check_lease(user, device)
    def perform(device):
        try:
            return {'device': device, 'ok': True, 'value': controller.perform(
                user, device, body.command.action, body.command.model_dump(exclude_none=True))}
        except (DeviceError, PermissionError) as exc:
            return {'device': device, 'ok': False, 'error': str(exc)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        return {'results': list(pool.map(perform, device_ids))}


@app.post('/api/devices/{device}/view')
def open_view(device: str, user=Depends(owner)):
    return controller.view(user,device)


@app.post('/api/devices/{device}/stream-settings')
def stream_settings(device: str, body: StreamSettings, user=Depends(owner)):
    return {'value': controller.perform(user, device, 'stream_settings', body.model_dump())}


@app.websocket('/api/devices/{device}/stream')
async def stream(websocket: WebSocket, device: str):
    origin = websocket.headers.get('origin')
    if origin and origin not in ('http://localhost:3109', 'http://127.0.0.1:3109',
                                  'http://localhost:8765', 'http://127.0.0.1:8765'):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    source = None
    keepalive = False
    receive_task = None
    frame_task = None
    try:
        # Auth is in the first message, never in URLs or access logs.
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=5)
        if len(raw) > 2048:
            raise PermissionError('Authentication message too large')
        auth = json.loads(raw)
        token = auth.get('token') if isinstance(auth, dict) else None
        if not isinstance(token, str):
            raise PermissionError('A valid API key is required')
        user = await asyncio.to_thread(authenticate, token)
        if not user:
            raise PermissionError('A valid API key is required')
        keepalive = auth.get('keepalive') is True
        await asyncio.to_thread(controller.check_lease, user, device)
        source = hub.subscribe(device)
        await websocket.send_json({'type': 'ready', 'format': 'jpeg', 'transport': 'websocket', 'source': source.transport, 'policy': 'latest-frame'})
        receive_task = asyncio.create_task(websocket.receive())
        seq = 0
        last_transport = source.transport
        last_auth = time.monotonic()
        last_renew = time.monotonic()
        while True:
            frame_task = asyncio.create_task(asyncio.to_thread(source.next, seq))
            done, _ = await asyncio.wait({frame_task, receive_task}, return_when=asyncio.FIRST_COMPLETED)
            if receive_task in done:
                break
            frame = frame_task.result()
            if time.monotonic() - last_auth > 1:
                user = await asyncio.to_thread(authenticate, token)
                if not user:
                    raise PermissionError('The API key is no longer valid')
                last_auth = time.monotonic()
            await asyncio.to_thread(controller.check_lease, user, device)
            if keepalive and time.monotonic()-last_renew>=20:
                await asyncio.to_thread(controller.renew_view,user,device)
                last_renew=time.monotonic()
            if frame is None:
                continue
            seq, data, received_at = frame
            # Never hold the command lock while streaming or queue old frames.
            if time.monotonic() - received_at > 1:
                continue
            if source.transport != last_transport:
                last_transport=source.transport
                await websocket.send_json({'type':'source','source':last_transport})
            await asyncio.wait_for(websocket.send_bytes(data), timeout=1)
    except (PermissionError, DeviceError) as exc:
        with contextlib.suppress(Exception):
            await websocket.send_json({'type': 'error', 'message': str(exc), 'retryable': not isinstance(exc,(PermissionError,LeaseError)) and 'iPhone UI automation is not authorized' not in str(exc)})
            await websocket.close(code=1008 if isinstance(exc, (PermissionError, LeaseError)) else 1011)
    except (WebSocketDisconnect, TimeoutError, RuntimeError):
        with contextlib.suppress(Exception):
            await websocket.close(code=1013)
    except ValueError:
        with contextlib.suppress(Exception):
            await websocket.close(code=1008)
    finally:
        if source:
            hub.unsubscribe(device, source)
        for task in (receive_task, frame_task):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        with contextlib.suppress(Exception):
            await websocket.close()


@app.get('/api/audit')
def audit(user=Depends(owner)):
    with database() as db:
        rows = db.execute('SELECT id,time,device,action,success,error FROM audit WHERE owner=? ORDER BY id DESC LIMIT 100',
                          (user['hash'],)).fetchall()
    return {'events': [dict(row) for row in rows]}


@app.get('/api/capabilities')
def capabilities(user=Depends(owner)):
    return {'actions': list(Action.model_fields['action'].annotation.__args__),
            'coordinates': 'normalized_0_to_1', 'screen_transport': 'authenticated_mjpeg_over_websocket',
            'recovery': 'usb_wda_supervision_with_backoff', 'workflows': 'record_edit_repeat_schedule_cancel', 'assets': ['ipa','photo','video'],
            'apps': 'list_install_uninstall', 'groups': 'credential_scoped_persistent', 'max_batch_devices': 20,
            'scope': 'local developer preview',
            'pending': ['WebRTC remote video', 'remote node relay']}


task_api.register_routes(app, owner)
codex_api.register_routes(app, owner)
demo.register_routes(app, owner)


class RecoverySetting(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool


@app.get('/api/recovery')
def recovery_status(user=Depends(owner)):
    states=recovery.supervisor.snapshot(user)
    with database() as db:
        rows=db.execute('SELECT time,device,state,detail FROM recovery_events ORDER BY id DESC LIMIT 100').fetchall()
    return {'devices':states,'can_configure':'*' in user['devices'],
            'events':[dict(r) for r in rows if allowed(user,r['device'])]}


@app.post('/api/devices/{device}/recovery')
def set_recovery(device: str, body: RecoverySetting, user=Depends(owner)):
    return recovery.configure(user,device,body.enabled)
