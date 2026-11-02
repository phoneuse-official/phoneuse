"""Environment settings. PHONEUSE_* names win; the older QUNKONG_* names still work."""
import os


def setting(name, default=None):
    return os.environ.get('PHONEUSE_' + name) or os.environ.get('QUNKONG_' + name) or default
