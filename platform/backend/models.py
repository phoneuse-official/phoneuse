from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Action(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    action: Literal['status', 'screenshot', 'source', 'window_size', 'active_app', 'battery',
                    'orientation', 'tap', 'swipe', 'long_press', 'text', 'home', 'button',
                    'launch_app', 'terminate_app', 'open_url', 'set_orientation', 'double_tap', 'pinch',
                    'lock', 'unlock', 'locked', 'alert_text', 'accept_alert', 'dismiss_alert',
                    'clipboard_get', 'clipboard_set', 'dismiss_keyboard',
                    'source_fast', 'find_elements', 'element_state', 'element_click',
                    'element_input_state', 'element_fill', 'element_submit_search']
    query: str | None = Field(default=None, min_length=1, max_length=500)
    element_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_-]+$')
    session_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_-]+$')
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    x2: float | None = Field(default=None, ge=0, le=1)
    y2: float | None = Field(default=None, ge=0, le=1)
    duration_ms: int = Field(default=400, ge=50, le=5000)
    scale: float | None = Field(default=None, ge=0.25, le=4)
    text: str | None = Field(default=None, max_length=4000)
    name: Literal['home', 'volumeup', 'volumedown'] | None = None
    bundle_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{1,249}$')
    url: str | None = Field(default=None, max_length=2000, pattern=r'^https?://[^\s]+$')
    orientation: Literal['PORTRAIT', 'LANDSCAPE', 'UIA_DEVICE_ORIENTATION_LANDSCAPERIGHT'] | None = None

    @model_validator(mode='after')
    def required_params(self):
        fields = {'find_elements': ['query'], 'element_state': ['element_id','session_id'],
                  'element_input_state': ['element_id','session_id'],
                  'element_fill': ['element_id','session_id','text'],
                  'element_submit_search': ['element_id','session_id','text'],
                  'element_click': ['element_id','session_id'], 'pinch': ['x', 'y', 'scale'], 'double_tap': ['x', 'y'], 'clipboard_set': ['text'], 'tap': ['x', 'y'], 'long_press': ['x', 'y'], 'swipe': ['x', 'y', 'x2', 'y2'],
                  'text': ['text'], 'button': ['name'], 'launch_app': ['bundle_id'],
                  'terminate_app': ['bundle_id'], 'open_url': ['url'], 'set_orientation': ['orientation']}
        for field in fields.get(self.action, []):
            if getattr(self, field) is None:
                raise ValueError(f'{self.action} 需要 {field}')
        if self.action in ('element_fill','element_submit_search') and (
            not self.text or len(self.text)>2000 or any(ord(c)<32 or ord(c)==127 for c in self.text)):
            raise ValueError('Targeted input requires nonempty single-line text, up to 2000 characters')
        if self.action == 'pinch' and not (0.2 <= self.x <= 0.8 and 0.2 <= self.y <= 0.8):
            raise ValueError('缩放中心需在屏幕 20%–80% 范围内，为双指手势保留空间')
        return self
