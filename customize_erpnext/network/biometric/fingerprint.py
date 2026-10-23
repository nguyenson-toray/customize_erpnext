"""Fingerprint data on Employee + pushing employees to machines.

Moved from api/utilities.py (23/10/2026). Callers: public/js/fingerprint_scanner_dialog.js,
public/js/shared_fingerprint_sync.js (Employee list / form) and the /app/biometric-sync page.
The single-employee push is now a thin wrapper over the batch push (one code path,
zk_device.upsert_users); the old per-employee implementation and the unused
endpoints (get_employee_fingerprint_data, update_fingerprint_names, get_finger_name,
get_employees_for_fingerprint, sync_employee_fingerprint_to_machines) were removed.
"""

import json

import frappe

from customize_erpnext.network.biometric.auth import check_biometric_access
from customize_erpnext.network.biometric.machines import check_door_machine_access, get_machine, get_machines
from customize_erpnext.network.biometric.zk_device import (
    build_zk_cfg,
    check_connection_fast,
    connect_zk,
    finger_name,
    upsert_users,
)


# ---------------------------------------------------------------------------
# Fingerprint data on Employee (scanner dialog)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def save_fingerprint_data(employee_id, finger_index, template_data, quality_score=0):
    """Saves fingerprint template data to the Employee document."""
    check_biometric_access()
    try:
        employee = frappe.get_doc("Employee", employee_id)

        existing_fingerprint = None
        for fp in employee.get("custom_fingerprints"):
            if str(fp.finger_index) == str(finger_index):
                existing_fingerprint = fp
                break

        name = finger_name(finger_index)

        fingerprint_id = None
        if existing_fingerprint:
            existing_fingerprint.template_data = template_data
            existing_fingerprint.finger_name = name
            existing_fingerprint.quality_score = int(quality_score) if quality_score else 0
            fingerprint_id = existing_fingerprint.name
        else:
            new_fingerprint = employee.append("custom_fingerprints", {
                "finger_index": finger_index,
                "finger_name": name,
                "template_data": template_data,
                "quality_score": int(quality_score) if quality_score else 0
            })
            fingerprint_id = new_fingerprint.name

        employee.save(ignore_permissions=True)
        frappe.db.commit()

        return {"success": True, "fingerprint_id": fingerprint_id}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to save fingerprint data")
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def get_employee_fingerprints_status(employee_id):
    """Returns a list of finger_index for which fingerprint data exists for the given employee."""
    check_biometric_access()
    try:
        employee = frappe.get_doc("Employee", employee_id)
        existing_fingers = [fp.finger_index for fp in employee.get("custom_fingerprints") or []]
        return {"success": True, "existing_fingers": existing_fingers}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to get employee fingerprints status")
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def delete_fingerprint_data(employee_id, finger_index):
    """Delete fingerprint template data for a specific finger"""
    check_biometric_access()
    try:
        employee = frappe.get_doc("Employee", employee_id)

        fingerprint_to_remove = None
        for fp in employee.get("custom_fingerprints"):
            if str(fp.finger_index) == str(finger_index):
                fingerprint_to_remove = fp
                break

        if fingerprint_to_remove:
            employee.remove(fingerprint_to_remove)
            employee.save(ignore_permissions=True)
            frappe.db.commit()

            return {
                "success": True,
                "message": f"Deleted fingerprint for finger index {finger_index}"
            }
        else:
            return {
                "success": False,
                "message": f"No fingerprint found for finger index {finger_index}"
            }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to delete fingerprint data")
        return {"success": False, "message": str(e)}


# ---------------------------------------------------------------------------
# Machines list with connection status (sync dialog, biometric-sync Tab 2/3)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_enabled_attendance_machines(include_door=0, include_disabled=0):
    """Enabled machines + a parallel TCP check of each.

    Unlike biometric_sync.get_attendance_machines (scoped list, no probe) this
    one reports online/offline, so the sync dialogs can pre-tick online machines:
    - `include_door=1` adds the door controllers — only for users with the Door
      Control role; everyone else never sees them.
    - `include_disabled=1` adds machines with Enable unticked.
    """
    check_biometric_access()
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        include_door = frappe.utils.cint(include_door) and "Door Control" in frappe.get_roles()
        machines = get_machines(
            enabled_only=not frappe.utils.cint(include_disabled), include_door=include_door
        )

        if not machines:
            return {
                "success": True,
                "machines": [],
                "message": "No enabled attendance machines found"
            }

        def info(machine, status):
            return {
                "name": machine.get("name"),
                "device_name": machine.get("device_name"),
                "ip_address": machine.get("ip_address"),
                "port": machine.get("port") or 4370,
                "location": machine.get("location") or "",
                "is_door_control": machine.get("is_door_control"),
                "enable": machine.get("enable"),
                "connection_status": status["status"],
                "connection_message": status["message"],
                "response_time": status.get("response_time", 0)
            }

        machines_with_status = []
        with ThreadPoolExecutor(max_workers=min(len(machines), 15)) as executor:
            future_to_machine = {
                executor.submit(check_connection_fast, machine): machine
                for machine in machines
            }
            for future in as_completed(future_to_machine, timeout=10):
                machine = future_to_machine[future]
                try:
                    machines_with_status.append(info(machine, future.result()))
                except Exception as e:
                    machines_with_status.append(info(machine, {
                        "status": "error", "message": f"Check timeout: {str(e)}"}))

        return {
            "success": True,
            "machines": machines_with_status,
            "total_machines": len(machines_with_status),
            "online_machines": len([m for m in machines_with_status if m["connection_status"] == "online"]),
            "offline_machines": len([m for m in machines_with_status if m["connection_status"] == "offline"])
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to get enabled attendance machines")
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


# ---------------------------------------------------------------------------
# Push employees (ERPNext -> machine)
# ---------------------------------------------------------------------------

def _prepare_employee_sync_data(employee_id):
    """Employee data for pushing to a machine. Employees without fingerprint
    data are pushed too (user info only)."""
    employee = frappe.get_doc("Employee", employee_id)

    if not employee.attendance_device_id:
        return None, {
            "success": False,
            "message": f"Employee {employee.employee} does not have attendance_device_id"
        }

    fingerprints_data = frappe.db.sql("""
        SELECT finger_index, template_data
        FROM `tabFingerprint Data`
        WHERE parent = %s AND template_data IS NOT NULL AND template_data != ''
        ORDER BY finger_index
    """, employee_id, as_dict=True)
    fingerprints = [{"finger_index": fp.finger_index, "template_data": fp.template_data} for fp in fingerprints_data]

    try:
        from zk import const
        privilege_str = getattr(employee, 'custom_privilege', 'USER_DEFAULT')
        privilege = const.USER_ADMIN if privilege_str == "USER_ADMIN" else const.USER_DEFAULT
    except ImportError:
        privilege = 14 if getattr(employee, 'custom_privilege', 'USER_DEFAULT') == "USER_ADMIN" else 0

    password_int = getattr(employee, 'custom_password', None)
    password = str(password_int) if password_int and password_int != 0 else ""

    employee_data = {
        "employee": employee.employee,
        "employee_name": employee.employee_name,
        "attendance_device_id": employee.attendance_device_id,
        "password": password,
        "privilege": privilege,
        "fingerprints": fingerprints
    }

    return employee_data, None


def _publish_machine_sync_progress(payload):
    """Push per-employee sync progress to the initiating user (socketio)."""
    try:
        frappe.publish_realtime(
            "fingerprint_machine_sync_progress",
            payload,
            user=frappe.session.user,
        )
    except Exception:
        pass  # progress is best-effort; never break the sync for it


def _sync_employees_to_machine(machine_name, employee_ids, publish_progress=True):
    machine = frappe._dict(get_machine(machine_name, allow_door=True))
    # pushing a fingerprint to a door controller = door access: Door Control role only
    check_door_machine_access(machine)
    # A disabled machine is allowed here: the sync dialog lists it unticked and
    # the user ticks it on purpose. `enable` only keeps it out of automatic runs.
    results = []

    def record(emp_id, emp_name, success, fp_count=0, error=None):
        results.append({
            "employee": emp_id,
            "employee_name": emp_name,
            "success": success,
            "fingerprints_synced": fp_count,
            "error": error,
        })
        if publish_progress:
            _publish_machine_sync_progress({
                "machine": machine.device_name,
                "employee": emp_id,
                "employee_name": emp_name,
                "success": success,
                "fingerprints_synced": fp_count,
                "error": error,
                "done": len(results),
                "total": len(employee_ids),
            })

    def summary():
        success_count = sum(1 for r in results if r["success"])
        return {
            "success": success_count > 0,
            "machine": machine.device_name,
            "total": len(employee_ids),
            "success_count": success_count,
            "failed_count": len(results) - success_count,
            "results": results,
        }

    # Prepare all employee data up front (DB reads before touching the device)
    prepared = []
    for emp_id in employee_ids:
        try:
            employee_data, error = _prepare_employee_sync_data(emp_id)
        except Exception as e:
            # e.g. Employee does not exist — must not kill the whole batch
            employee_data, error = None, {"message": str(e)}
        if error:
            record(emp_id, emp_id, False, error=error.get("message"))
        else:
            prepared.append(employee_data)

    if not prepared:
        return summary()

    # Quick network check (once per batch)
    if check_connection_fast(machine, timeout=3)["status"] != "online":
        msg = f"Cannot connect to {machine.ip_address}:{machine.port}"
        for employee_data in prepared:
            record(employee_data["employee"], employee_data["employee_name"], False, error=msg)
        return summary()

    conn = None
    try:
        conn = connect_zk(build_zk_cfg(machine))
        conn.disable_device()
        upsert_users(
            conn,
            [{
                "user_id": e["attendance_device_id"],
                "name": e["employee_name"],
                "privilege": e["privilege"],
                "password": e["password"],
                "fingerprints": e["fingerprints"],
                "employee": e["employee"],
            } for e in prepared],
            lambda user, ok, fp_count, error: record(
                user["employee"], user["name"], ok, fp_count=fp_count, error=error),
        )
        return summary()

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"sync_employees_to_machine: {machine_name}")
        msg = f"Device error: {str(e)}"
        done_ids = {r["employee"] for r in results}
        for employee_data in prepared:
            if employee_data["employee"] not in done_ids:
                record(employee_data["employee"], employee_data["employee_name"], False, error=msg)
        return summary()
    finally:
        if conn:
            try:
                conn.enable_device()
                conn.disconnect()
            except Exception:
                pass


@frappe.whitelist()
def sync_employees_to_machine_batch(machine_name, employee_ids):
    """Sync multiple employees to ONE machine over a SINGLE connection.

    Connect once, disable device once, get_users() once, then upsert each
    employee (delete + set_user + templates). Per-employee progress is published
    via frappe.publish_realtime (event: fingerprint_machine_sync_progress).

    Returns per-employee results:
      {success, machine, total, success_count, failed_count,
       results: [{employee, employee_name, success, fingerprints_synced, error}]}
    """
    check_biometric_access()
    if isinstance(employee_ids, str):
        employee_ids = json.loads(employee_ids)
    return _sync_employees_to_machine(machine_name, employee_ids)


@frappe.whitelist()
def sync_employee_to_single_machine(employee_id, machine_name):
    """Sync one employee to one machine (biometric-sync Tab 2 phase 2 / Tab 3)."""
    check_biometric_access()
    try:
        result = _sync_employees_to_machine(machine_name, [employee_id], publish_progress=False)
        row = result["results"][0] if result["results"] else {}
        if row.get("success"):
            return {
                "success": True,
                "message": f"Synced {row.get('employee_name')} to {result['machine']}"
            }
        return {"success": False, "message": row.get("error") or "Sync failed"}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"sync_employee_to_single_machine: {employee_id} -> {machine_name}")
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }
