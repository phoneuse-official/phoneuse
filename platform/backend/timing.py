"""Per-task aggregate transport timings; never stores routes, values, or identifiers."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import time

_current=ContextVar('phoneuse_wda_metrics',default=None)

@contextmanager
def collect(metrics):
    token=_current.set(metrics)
    try:yield
    finally:_current.reset(token)


def measured_wda(function):
    @wraps(function)
    def wrapped(device,method,path,*args,**kwargs):
        metrics=_current.get()
        if metrics is None:return function(device,method,path,*args,**kwargs)
        if path.endswith('/elements') or path.endswith('/element'):category='lookup'
        elif '/source' in path:category='observation'
        elif path.endswith('/screenshot'):category='screenshot'
        elif method!='GET':category='mutation'
        else:category='state'
        t=time.monotonic();ok=False
        try:
            value=function(device,method,path,*args,**kwargs);ok=True;return value
        finally:
            bucket=metrics.setdefault(category,{'calls':0,'failed':0,'seconds':0.0})
            bucket['calls']+=1;bucket['failed']+=int(not ok)
            bucket['seconds']=round(bucket['seconds']+time.monotonic()-t,6)
    return wrapped
