# Archived Files - API Directory

This directory contains archived code files that are no longer actively used in the system.

## 📋 Archived Files

### `_archived_sync_att_user_fingerprint.py`

**Date Archived:** 2025-10-10
**Original Name:** `sync_att_user_fingerprint.py`
**Reason for Archiving:** Not integrated with ERPNext API, not called from UI

#### Why This File Was Archived:

1. **❌ No ERPNext API Integration**
   - Missing `@frappe.whitelist()` decorators
   - Cannot be called from JavaScript/Frontend
   - Uses standalone class-based architecture

2. **❌ No Active References**
   - No JavaScript files reference this module
   - No Python files import this module
   - Not used anywhere in the codebase

3. **❌ Missing Dependencies**
   ```python
   from config import ATTENDANCE_DEVICES, FINGERPRINT_CONFIG  # ❌ config.py doesn't exist
   from core.erpnext_api import ERPNextAPI                    # ❌ Module doesn't exist
   ```

4. **❌ Superseded by Better Implementation**
   - Replaced by: `/customize_erpnext/api/utilities.py`
   - utilities.py has:
     -  `@frappe.whitelist()` decorators
     -  Called from `shared_fingerprint_sync.js`
     -  Parallel processing with ThreadPoolExecutor
     -  Connection caching (30s)
     -  Fast connection checks (2s timeout)
     -  Better error handling
     -  Bandwidth optimization (only sends actual fingerprint data)
     -  Detailed logging

#### What This File Does (For Reference):

Class-based standalone module for syncing fingerprints to ZKTeco attendance devices:

**Main Features:**
- `AttendanceDeviceSync` class with connection management
- Detailed logging with emoji indicators
- Only sends fingerprints with actual data (bandwidth optimized)
- Vietnamese name handling with unidecode
- Sync history tracking (if ERPNextAPI existed)

**Key Methods:**
- `connect_device()` - Connect to attendance machine
- `sync_employee_to_device()` - Sync one employee to device
- `sync_to_device()` - Sync multiple employees to one device
- `sync_all_to_device()` - Sync to all devices
- `get_device_users()` - Get users from device
- `clear_device_data()` - Clear all device data

#### Current Active Implementation:

**File:** `/customize_erpnext/api/utilities.py`

**Key Functions:**
```python
@frappe.whitelist()
def sync_employee_to_single_machine(employee_id, machine_name):
    """Sync one employee to one specific machine (for parallel processing)"""
    # Called from: shared_fingerprint_sync.js (line 478)
    ...

@frappe.whitelist()
def get_enabled_attendance_machines():
    """Get list of enabled attendance machines with parallel connection checks"""
    # Called from: shared_fingerprint_sync.js (line 239)
    ...
```

**Frontend Integration:**
- `/public/js/shared_fingerprint_sync.js` - Main sync UI
- `/public/js/custom_scripts/employee_list.js` - List view sync
- `/public/js/custom_scripts/employee.js` - Form view sync

#### Should This File Be Restored?

**NO** - Unless you need:
1. Standalone command-line sync tool (not integrated with ERPNext UI)
2. Class-based architecture for sync operations
3. More detailed device info logging (serial, firmware, etc.)

**If you need these features**, consider:
- Extracting useful parts to integrate into `utilities.py`
- Creating a separate CLI tool using this code
- Adding missing features to `utilities.py` instead

#### Comparison Table:

| Feature | _archived_sync_att_user_fingerprint.py | utilities.py (current) |
|---------|---------------------------------------|----------------------|
| **ERPNext API Integration** | ❌ NO |  YES |
| **Called from UI** | ❌ NO |  YES (shared_fingerprint_sync.js) |
| **Architecture** | Class-based (standalone) | Function-based (API endpoints) |
| **Parallel Processing** | ❌ Sequential |  Parallel (ThreadPoolExecutor) |
| **Connection Caching** | ❌ NO |  YES (30s cache) |
| **Fast Connection Check** | ❌ 10s timeout |  2s timeout |
| **Bandwidth Optimization** |  Only sends actual data |  Only sends actual data |
| **Logging** |  Detailed with emoji |  Detailed with emoji |
| **Device Info** |  Serial, firmware, platform | ❌ NO |
| **Sync History** |  YES (if ERPNextAPI exists) | ❌ NO |
| **Dependencies** | ❌ Missing (config.py, core.erpnext_api) |  All available |

#### How to Restore (If Needed):

```bash
cd /home/frappe/frappe-bench/apps/customize_erpnext/customize_erpnext/api
mv _archived_sync_att_user_fingerprint.py sync_att_user_fingerprint.py
```

Then you would need to:
1. Create missing `config.py` file with `ATTENDANCE_DEVICES` config
2. Create missing `core/erpnext_api.py` module
3. Add `@frappe.whitelist()` decorators if you want UI integration
4. Update imports in other files

#### Recommended Action:

**Keep archived** - utilities.py provides all necessary functionality for production use.

---

**Last Updated:** 2025-10-10
**Archived By:** System maintenance - code cleanup
**Related Files:**
- Active: `/customize_erpnext/api/utilities.py`
- Frontend: `/customize_erpnext/public/js/shared_fingerprint_sync.js`
- Documentation: `/IMPROVEMENTS_FINGERPRINT_SYNC.md`
