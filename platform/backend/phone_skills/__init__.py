"""Registered, bounded phone routines. Skills cannot execute model-supplied code."""
from .cookie import dismiss_cookie_prompt

REGISTRY = {'dismiss_cookie_prompt': dismiss_cookie_prompt}
