"""Environment settings. PHONEUSE_* names win; the older QUNKONG_* names still work."""
import os


def setting(name, default=None):
    for prefix in ('PHONEUSE_', 'QUNKONG_'):
        if prefix + name in os.environ:
            return os.environ[prefix + name] or default
    return default
