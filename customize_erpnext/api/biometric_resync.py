"""Moved to customize_erpnext.network.biometric.resync + customize_erpnext.network.biometric.mongodb_sync (23/10/2026).

Temporary shim so browsers still holding the old JS (and the retired
biometric-attendance-sync-tool, if started again) keep working — delete after ~1 week.
"""

from customize_erpnext.network.biometric.resync import *  # noqa: F401,F403
from customize_erpnext.network.biometric.mongodb_sync import *  # noqa: F401,F403
