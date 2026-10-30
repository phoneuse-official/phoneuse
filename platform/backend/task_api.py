import asyncio
import json
import time
import uuid
from typing import Literal

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import assets, device_apps, jobs
from .models import Action
from .service import controller, database


class Step(BaseModel):
    model_config = ConfigDict(extra='forbid')
    command: Action
    wait_ms: int = Field(default=0, ge=0, le=60000)

    @model_validator(mode='after')
    def recordable(self):
        if self.command.action in ('screenshot', 'source', 'clipboard_get', 'status', 'window_size', 'active_app', 'battery', 'orientation', 'locked', 'alert_text', 'source_fast', 'find_elements', 'element_state', 'element_click'):
            raise ValueError('工作流不接受读取步骤或临时元素句柄；请使用独立接口')
        return self


class Workflow(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    name: str = Field(min_length=1, max_length=100)
    steps: list[Step] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def name_valid(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError('请输入工作流名称')
        return self


class Task(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    kind: Literal['workflow', 'install', 'uninstall', 'media']
    device_ids: list[str] = Field(min_length=1, max_length=20)
    workflow_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    asset_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    bundle_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{1,249}$')
    confirm_uninstall: bool = False
    run_at: float | None = None
    repeat: int = Field(default=1, ge=1, le=100)
    interval_ms: int = Field(default=0, ge=0, le=60000)
    on_error: Literal['stop', 'continue'] = 'stop'

    @model_validator(mode='after')
    def valid(self):
        required = {'workflow': self.workflow_id, 'install': self.asset_id, 'media': self.asset_id, 'uninstall': self.bundle_id}
        if not required[self.kind]:
            raise ValueError('任务缺少对应工作流、文件或应用')
        if self.kind == 'uninstall' and (not self.confirm_uninstall or self.bundle_id == assets.RUNNER):
            raise ValueError('卸载会删除应用及其数据，需明确 confirm_uninstall；控制代理不可卸载')
        if self.run_at is not None and not time.time() - 5 <= self.run_at <= time.time() + 30 * 86400:
            raise ValueError('定时须在未来30天内')
        return self


def register_routes(app, owner):
    upload_slots = asyncio.Semaphore(2)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': str(exc)}, status_code=400)

    @app.get('/api/devices/{device}/apps')
    def apps(device: str, user=Depends(owner)):
        with controller.lock(device):
            controller.check_lease(user, device)
            return {'apps': device_apps.operate(device, 'list')}

    @app.get('/api/assets')
    def list_assets(user=Depends(owner)):
        with database() as db:
            rows = db.execute('SELECT id FROM assets WHERE owner=? ORDER BY created DESC', (user['hash'],)).fetchall()
        return {'assets': [{k: v for k, v in assets.get_asset(user, r['id']).items() if k != 'owner'} for r in rows]}

    @app.post('/api/assets')
    async def upload(request: Request, filename: str, user=Depends(owner)):
        if not filename or len(filename) > 200 or '/' in filename or '\\' in filename or any(ord(c) < 32 for c in filename):
            raise ValueError('文件名无效')
        asset_id = uuid.uuid4().hex; path = assets.asset_path(asset_id)
        size = 0
        async with upload_slots:
            try:
                async with asyncio.timeout(180):
                    with path.open('xb') as target:
                        path.chmod(0o600)
                        async for chunk in request.stream():
                            size += len(chunk)
                            if size > assets.MAX_UPLOAD:
                                raise HTTPException(413, '单个文件最大128 MB，图片和视频最大50 MB')
                            await asyncio.to_thread(target.write, chunk)
                if not size:
                    raise ValueError('文件为空')
                registration = asyncio.create_task(asyncio.to_thread(assets.register, user, asset_id, filename, size))
                try:
                    result = await asyncio.shield(registration)
                except asyncio.CancelledError:
                    # Finish registration before deciding whether to remove the file.
                    await registration
                    raise
                result.pop('owner', None)
                return result
            except BaseException:
                with database() as db:
                    committed = db.execute('SELECT id FROM assets WHERE id=?', (asset_id,)).fetchone()
                if not committed:
                    path.unlink(missing_ok=True)
                raise

    @app.delete('/api/assets/{asset_id}')
    def delete_asset(asset_id: str, user=Depends(owner)):
        assets.get_asset(user, asset_id)
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            active = db.execute("SELECT payload FROM jobs WHERE status IN ('queued','running','cancelling')").fetchall()
            if any(json.loads(r['payload']).get('asset_id') == asset_id for r in active):
                raise ValueError('文件仍被待执行或运行中任务使用，请先停止任务')
            db.execute('DELETE FROM assets WHERE id=? AND owner=?', (asset_id, user['hash']))
            assets.asset_path(asset_id).unlink(missing_ok=True)
        return {'deleted': True}

    @app.get('/api/workflows')
    def workflows(user=Depends(owner)):
        with database() as db:
            rows = db.execute('SELECT id,name,steps,updated FROM workflows WHERE owner=? ORDER BY updated DESC', (user['hash'],)).fetchall()
        return {'workflows': [dict(r, steps=json.loads(r['steps'])) for r in rows]}

    @app.post('/api/workflows')
    def save_workflow(body: Workflow, user=Depends(owner)):
        workflow_id = body.id or uuid.uuid4().hex
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT owner FROM workflows WHERE id=?', (workflow_id,)).fetchone()
            if existing and existing['owner'] != user['hash']:
                raise PermissionError('无权修改此工作流')
            if not existing and db.execute('SELECT COUNT(*) FROM workflows WHERE owner=?', (user['hash'],)).fetchone()[0] >= 100:
                raise ValueError('工作流数量达到100个上限')
            db.execute('INSERT OR REPLACE INTO workflows VALUES (?,?,?,?,?)', (workflow_id, user['hash'], body.name,
                       json.dumps([s.model_dump(exclude_none=True) for s in body.steps]), time.time()))
        return {'id': workflow_id, 'name': body.name}

    @app.delete('/api/workflows/{workflow_id}')
    def delete_workflow(workflow_id: str, user=Depends(owner)):
        with database() as db:
            db.execute('DELETE FROM workflows WHERE id=? AND owner=?', (workflow_id, user['hash']))
        return {'deleted': True}

    @app.post('/api/jobs')
    def create_job(body: Task, user=Depends(owner)):
        payload = {}
        if body.kind == 'workflow':
            with database() as db:
                workflow = db.execute('SELECT * FROM workflows WHERE id=? AND owner=?', (body.workflow_id, user['hash'])).fetchone()
            if not workflow:
                raise ValueError('工作流不存在或无权访问')
            steps = json.loads(workflow['steps'])
            if len(steps) * body.repeat > 1000 or sum(s['wait_ms'] for s in steps) * body.repeat + body.interval_ms * (body.repeat - 1) > 3500000:
                raise ValueError('单任务最多1000步，等待时长总和不能超过约58分钟')
            payload = {'workflow_id': body.workflow_id, 'name': workflow['name'], 'steps': steps,
                       'repeat': body.repeat, 'interval_ms': body.interval_ms, 'on_error': body.on_error}
        elif body.kind in ('install', 'media'):
            payload = {'asset_id': body.asset_id}
        else:
            payload = {'bundle_id': body.bundle_id}
        return jobs.submit(user, body.kind, body.device_ids, payload, body.run_at)

    @app.get('/api/jobs')
    def list_jobs(user=Depends(owner)):
        with database() as db:
            rows = db.execute('SELECT * FROM jobs WHERE owner=? ORDER BY created DESC LIMIT 100', (user['hash'],)).fetchall()
        return {'jobs': [jobs.public_job(row) for row in rows]}

    @app.get('/api/jobs/{job_id}')
    def read_job(job_id: str, user=Depends(owner)):
        return jobs.get_job(user, job_id)

    @app.post('/api/jobs/{job_id}/cancel')
    def stop_job(job_id: str, user=Depends(owner)):
        return jobs.cancel(user, job_id)
