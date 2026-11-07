"""Bounded, metadata-only local task diagnostics. Never accept arbitrary payloads."""
import json
import sqlite3
import threading
import time
from .service import STATE

_PATH = STATE / 'diagnostics.sqlite3'
_LOCK = threading.Lock()
_MAX_EVENTS = 20000
_MAX_AGE = 7 * 86400
_FIELDS = {
    'task_started': {'transport', 'screen_mode'},
    'task_finished': {'status', 'seconds'},
    'connection': {'transport', 'status'},
    'model_turn': {'seconds', 'status'},
    'device_action': {'action', 'status', 'seconds', 'transport'},
    'verification': {'status', 'reason', 'observations', 'screen_changed', 'seconds', 'image_changed', 'image_compared', 'expected_present'},
    'tap_target': {'target_kind', 'target_height', 'status'},
}
_VALUES = {
    'transport': {'mirroring', 'wda_usb'}, 'screen_mode': {'ocr', 'accessibility'},
    'status': {'started', 'ready', 'ok', 'failed', 'uncertain', 'matched', 'not_matched', 'observation_failed', 'cancelled', 'blocked', 'model_reported_result', 'unverified_result', 'step_limit', 'time_limit', 'token_limit', 'model_output_truncated'},
    'reason': {'destination_text_not_found', 'observation_failed'},
    'target_kind': {'ocr_word', 'icon', 'other'},
    'target_height': {'small', 'medium', 'large'},
    'action': {'tap', 'scroll', 'home', 'screenshot', 'frame_observation', 'source_fast', 'window_size', 'orientation', 'find_elements', 'element_state', 'element_input_state', 'active_app', 'active_element', 'element_click', 'element_fill', 'element_submit_search', 'launch_app', 'swipe', 'other'},
}
_dropped = set()

def emit(trace, event, **fields):
    if event not in _FIELDS:
        return
    clean = {}
    for key, value in fields.items():
        if key not in _FIELDS[event]: continue
        if key in _VALUES:
            value = value if value in _VALUES[key] else ('other' if key == 'action' else 'failed')
        elif key in ('seconds', 'observations'):
            if type(value) not in (int, float): continue
            value = max(0, min(value, 1000000))
        elif key in ('screen_changed', 'image_changed', 'image_compared', 'expected_present'):
            if type(value) is not bool: continue
        clean[key] = value
    try:
        with _LOCK, sqlite3.connect(_PATH, timeout=.1) as db:
            db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, trace TEXT NOT NULL, time REAL NOT NULL, event TEXT NOT NULL, data TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS events_trace ON events(trace,id)')
            db.execute('INSERT INTO events(trace,time,event,data) VALUES (?,?,?,?)', (trace,time.time(),event,json.dumps(clean)))
            db.execute('DELETE FROM events WHERE time < ?', (time.time()-_MAX_AGE,))
            db.execute('DELETE FROM events WHERE id <= (SELECT id FROM events ORDER BY id DESC LIMIT 1 OFFSET ?)', (_MAX_EVENTS,))
    except (sqlite3.Error, OSError):
        _dropped.add(trace)

def read(trace):
    try:
        with _LOCK, sqlite3.connect(_PATH, timeout=.1) as db:
            rows=db.execute('SELECT id,time,event,data FROM events WHERE trace=? ORDER BY id', (trace,)).fetchall()
        return {'events': [{'sequence': i, 'time': t, 'event': e, 'details': json.loads(d)} for i,t,e,d in rows], 'incomplete': trace in _dropped}
    except (sqlite3.Error, OSError):
        return {'events': [], 'incomplete': True}

def delete(trace):
    try:
        with _LOCK, sqlite3.connect(_PATH, timeout=.1) as db:
            db.execute('DELETE FROM events WHERE trace=?', (trace,))
        _dropped.discard(trace)
    except (sqlite3.Error, OSError):
        raise RuntimeError('Could not delete diagnostics') from None
