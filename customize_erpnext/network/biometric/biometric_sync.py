"""
API endpoints for Sync Fingerprint feature
Reuses ZK logic from biometric-attendance-sync-tool
"""

import frappe
from customize_erpnext.network.biometric.auth import check_biometric_access
import json
import time
import base64
import threading
from concurrent.futures import ThreadPoolExecutor, wait
from struct import pack

from customize_erpnext.network.biometric.zk_device import build_zk_cfg, connect_zk, finger_name
from customize_erpnext.network.biometric.machines import (
    check_door_machine_access, get_machine, get_machines, public_machine,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_machine_doc(machine_name):
    """Return machine config as dict (from Attendance Machine Setting)."""
    return frappe._dict(get_machine(machine_name))


def _is_working(emp, today):
    """Employee still employed on `today`: any status but Left, or Left with a
    relieving_date after today (relieving_date is the FIRST day off, not the last
    day worked)."""
    if emp.get("status") != "Left":
        return True
    rd = emp.get("relieving_date")
    return bool(rd and frappe.utils.getdate(rd) > today)


def _working_device_ids(device_ids):
    """The device_ids among `device_ids` that belong to an employee still working
    today. 🔴 Never deletable from an ATTENDANCE machine (door controllers are the
    exception: their user list is the few people allowed to open the door)."""
    device_ids = [str(d) for d in device_ids or [] if d not in (None, "")]
    if not device_ids:
        return set()
    today = frappe.utils.getdate(frappe.utils.today())
    emps = frappe.get_all(
        "Employee",
        filters={"attendance_device_id": ["in", device_ids]},
        fields=["attendance_device_id", "status", "relieving_date"],
    )
    return {str(e.attendance_device_id) for e in emps if _is_working(e, today)}


def _get_managed_machine_doc(machine_name):
    """Machine config for the Machine Management tab (info, clock, reboot, user list).

    Unlike _get_machine_doc it also resolves door controllers — that tab lists
    them when asked (scope door / all) — but only for the Door Control role,
    the same rule as pushing fingerprints to a door.
    """
    machine = get_machine(machine_name, allow_door=True)
    check_door_machine_access(machine)
    return frappe._dict(machine)


# Machines are independent devices, so per-machine work runs in one thread per
# machine. 🔴 Code running in these threads must NOT call frappe.* that touches
# frappe.local (db, cache, session, log_error…): it is thread-local and unset
# there. Threads only talk to the device; the calling thread does the rest.

def _read_machine_users(machine, with_fingers=False):
    """Connect to one machine (dict from get_machines), read its user list,
    release it. Raises on any failure. Thread-safe (no frappe.local).

    with_fingers: also read every fingerprint template in the same session and
    return (users, {uid: [finger indexes 0..9]}). One bulk get_templates() — measured
    23/10/2026 on Machine 2: 2,196 templates in 3.7 s (+0.8 s for the users), so only
    the Users on Machines view asks for it, not the Tab 4 scans.
    """
    conn = connect_zk(build_zk_cfg(frappe._dict(machine)))
    conn.disable_device()
    try:
        users = conn.get_users()
        if not with_fingers:
            return users
        fingers = {}
        for t in conn.get_templates() or []:
            if getattr(t, "valid", 1):
                fingers.setdefault(t.uid, set()).add(int(t.fid))
        return users, {uid: sorted(fids) for uid, fids in fingers.items()}
    finally:
        conn.enable_device()
        conn.disconnect()


def _read_users_on_machines(machines):
    """Read the user list of every machine in parallel.

    Returns [(machine, users, error)] in the order of `machines`; exactly one
    of users/error is None.
    """
    if not machines:
        return []
    with ThreadPoolExecutor(max_workers=len(machines)) as ex:
        futures = [ex.submit(_read_machine_users, m) for m in machines]
        out = []
        for m, fut in zip(machines, futures):
            try:
                out.append((m, fut.result(), None))
            except Exception as e:
                out.append((m, None, e))
    return out


def _zk_delete_uid(conn, uid, user_id):
    """Delete one user by device uid WITHOUT the refresh_data() that pyzk's
    delete_user() sends after every call — the caller refreshes once per batch.

    Always pass the uid: delete_user(user_id=…) alone makes pyzk download the
    machine's whole user list to look the uid up, on every single call.
    """
    from zk import const
    from zk.exception import ZKErrorResponse

    send = getattr(conn, "_ZK__send_command", None)   # pyzk 0.9 private method
    if send is None:
        # pyzk internals changed — public call (refreshes on its own, still correct)
        conn.delete_user(uid=uid, user_id=user_id)
        return
    resp = send(const.CMD_DELETE_USER, pack("h", uid))
    if not resp.get("status"):
        raise ZKErrorResponse("Can't delete user")


# ---------------------------------------------------------------------------
# 1. get_attendance_machines
# ---------------------------------------------------------------------------

MACHINE_SCOPES = ("attendance", "door", "all")


@frappe.whitelist()
def get_attendance_machines(scope="attendance"):
    """Return enabled machines.

    scope: "attendance" (default — what every other caller gets), "door"
    (door controllers only) or "all". Door controllers need the Door Control
    role; `can_door` tells the page whether to offer those scopes.
    """
    check_biometric_access()
    scope = scope or "attendance"
    if scope not in MACHINE_SCOPES:
        frappe.throw(f"Invalid machine scope: {scope}")
    if scope != "attendance":
        frappe.only_for("Door Control")
    machines = get_machines(
        enabled_only=True, include_door=(scope == "all"), door_only=(scope == "door")
    )
    return {
        "status": "success",
        "machines": [public_machine(m) for m in machines],
        "scope": scope,
        "can_door": "Door Control" in frappe.get_roles(),
    }


# ---------------------------------------------------------------------------
# 2. get_master_device_users
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_master_device_users(machine_name):
    """
    Connect to master machine, get all users, cross-match with ERPNext employees.
    Returns list of users with matched employee info.
    """
    check_biometric_access()
    try:
        doc = _get_machine_doc(machine_name)
        device_cfg = build_zk_cfg(doc)

        conn = connect_zk(device_cfg)
        conn.disable_device()

        try:
            zk_users = conn.get_users()
        finally:
            conn.enable_device()
            conn.disconnect()

        # Build lookup: attendance_device_id → employee
        employees = frappe.get_all(
            "Employee",
            filters={"status": "Active"},
            fields=["name", "employee_name", "attendance_device_id", "date_of_joining", "custom_group"],
        )
        emp_by_device_id = {e["attendance_device_id"]: e for e in employees if e["attendance_device_id"]}

        users_list = []
        for u in zk_users:
            emp = emp_by_device_id.get(str(u.user_id))
            users_list.append({
                "uid": u.uid,
                "user_id": u.user_id,
                "device_name": u.name,
                "matched": bool(emp),
                "employee_id": emp["name"] if emp else None,
                "employee_name": emp["employee_name"] if emp else None,
                "date_of_joining": str(emp["date_of_joining"]) if emp and emp["date_of_joining"] else None,
                "custom_group": emp["custom_group"] if emp else None,
            })

        # Sort: matched first, then by user_id
        users_list.sort(key=lambda x: (0 if x["matched"] else 1, str(x["user_id"])))

        matched_count = sum(1 for u in users_list if u["matched"])
        return {
            "status": "success",
            "machine": machine_name,
            "total_on_device": len(users_list),
            "matched_erpnext": matched_count,
            "users": users_list,
        }

    except Exception as e:
        frappe.log_error(f"get_master_device_users error: {e}")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# 3. get_employees_for_sync
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_employees_for_sync(employee="", employee_name="", attendance_device_id="", date_of_joining=""):
    """Filter active employees for display. Used to pre-filter before loading device users."""
    check_biometric_access()
    try:
        filters = {"status": "Active"}
        if employee:
            filters["name"] = ["like", f"%{employee}%"]
        if employee_name:
            filters["employee_name"] = ["like", f"%{employee_name}%"]
        if attendance_device_id:
            filters["attendance_device_id"] = attendance_device_id
        if date_of_joining:
            filters["date_of_joining"] = [">=", date_of_joining]

        employees = frappe.get_all(
            "Employee",
            filters=filters,
            fields=["name", "employee_name", "attendance_device_id", "date_of_joining", "custom_group"],
            limit=500,
        )
        return {"status": "success", "employees": employees, "count": len(employees)}

    except Exception as e:
        frappe.log_error(f"get_employees_for_sync error: {e}")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# 4. sync_fingerprints  (background job dispatcher)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def sync_fingerprints(master_machine_name, target_machine_names_json, user_ids_json, sync_to_erp=0):
    """
    Enqueue background job to sync fingerprints from master to target machines.
    Returns job_id for polling.
    """
    check_biometric_access()
    try:
        target_machine_names = json.loads(target_machine_names_json)
        user_ids = json.loads(user_ids_json)

        if not user_ids:
            frappe.throw("No users selected")

        # Build a unique job key for this run
        import uuid
        job_id = f"fp_sync_{uuid.uuid4().hex[:12]}"

        # Initialize cache state (frappe.cache().set_value tự json.dumps — truyền dict trực tiếp)
        cache_key = f"biometric_sync:{job_id}"
        frappe.cache().set_value(cache_key, {
            "status": "queued",
            "progress_pct": 0,
            "total_users": len(user_ids),
            "total_machines": len(target_machine_names),
            "done_users": 0,
            "results": [],
            "error": None,
        }, expires_in_sec=3600)

        # Enqueue — KHÔNG truyền job_id= (Frappe dùng làm RQ job identifier, không phải kwarg)
        # queue="default": the single long-queue worker is often occupied for 1h+ by the
        # hourly HRMS process_auto_attendance job — interactive biometric jobs must not
        # wait behind it. Job-level timeout still allows a long run.
        frappe.enqueue(
            "customize_erpnext.network.biometric.biometric_sync._run_sync_job",
            queue="default",
            timeout=3600,
            master_machine_name=master_machine_name,
            target_machine_names=target_machine_names,
            user_ids=user_ids,
            cache_key=cache_key,
            sync_to_erp=bool(int(sync_to_erp)),
        )

        return {"status": "success", "job_id": job_id}

    except Exception as e:
        frappe.log_error(f"sync_fingerprints error: {e}")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Background worker function
# ---------------------------------------------------------------------------

def _run_sync_job(master_machine_name, target_machine_names, user_ids, cache_key, sync_to_erp=False, job_id=None):
    """
    Actual sync logic running in Frappe background worker.
    Reads fingerprints from master, syncs to each target for selected user_ids.
    """
    def _update_cache(patch):
        # frappe.cache().get_value trả về dict trực tiếp (đã json.loads bên trong)
        state = frappe.cache().get_value(cache_key)
        if state:
            state.update(patch)
            frappe.cache().set_value(cache_key, state, expires_in_sec=3600)

    try:
        _update_cache({"status": "running", "phase": "Connecting to master machine..."})

        # --- Connect to master and get fingerprints for selected users ---
        master_doc = _get_machine_doc(master_machine_name)
        master_cfg = build_zk_cfg(master_doc)

        conn = connect_zk(master_cfg)
        conn.disable_device()

        try:
            all_zk_users = conn.get_users()
        except Exception as e:
            conn.enable_device()
            conn.disconnect()
            raise RuntimeError(f"Failed to get user list from master: {e}")

        # Filter only requested user_ids
        user_ids_set = set(str(uid) for uid in user_ids)
        target_users = [u for u in all_zk_users if str(u.user_id) in user_ids_set]

        _update_cache({"phase": f"Reading fingerprints for {len(target_users)} users...", "progress_pct": 5})

        # Read fingerprints per user (same approach as CMD tool 12.sync_from_master_device_to_erpnext.py)
        users_with_fp = []
        n_users = len(target_users)

        for i_u, u in enumerate(target_users):
            pct = 5 + int((i_u + 1) / n_users * 25)   # 5 → 30%
            _update_cache({
                "phase": f"Reading fingerprints: user {i_u + 1}/{n_users} (ID {u.user_id})...",
                "progress_pct": pct,
            })
            fingerprints = []
            for finger_id in range(10):
                try:
                    template = conn.get_user_template(u.uid, finger_id)
                    if (template and hasattr(template, "valid") and
                            template.valid and template.template and len(template.template) > 0):
                        fingerprints.append({
                            "finger_index": finger_id,
                            "template_data": base64.b64encode(template.template).decode("utf-8"),
                        })
                except Exception:
                    pass
            if fingerprints:
                users_with_fp.append({
                    "uid": u.uid,
                    "user_id": u.user_id,
                    "name": u.name,
                    "privilege": u.privilege,
                    "password": u.password,
                    "group_id": u.group_id,
                    "fingerprints": fingerprints,
                })

        conn.enable_device()
        conn.disconnect()

        if not users_with_fp:
            _update_cache({
                "status": "done",
                "progress_pct": 100,
                "phase": "Done — no fingerprint data found on master for selected users",
                "done_users": 0,
            })
            return

        # --- Sync to ERPNext only (machine sync is handled by frontend) ---
        results = []
        total = len(users_with_fp)

        employees = frappe.get_all(
            "Employee",
            filters={"attendance_device_id": ["in", [str(u["user_id"]) for u in users_with_fp]]},
            fields=["name", "attendance_device_id"],
        )
        emp_by_device = {e["attendance_device_id"]: e["name"] for e in employees}

        for idx, u in enumerate(users_with_fp):
            emp_id = emp_by_device.get(str(u["user_id"]))
            if not emp_id:
                results.append({"user_id": u["user_id"], "machine": "ERPNext", "success": False,
                                "message": "Employee not found"})
            else:
                try:
                    # Direct DB operations — bypasses Employee on_save hooks (much faster)
                    frappe.db.delete("Fingerprint Data", {"parent": emp_id, "parenttype": "Employee"})
                    for fp_idx, fp in enumerate(u["fingerprints"]):
                        row = frappe.get_doc({
                            "doctype": "Fingerprint Data",
                            "parent": emp_id,
                            "parenttype": "Employee",
                            "parentfield": "custom_fingerprints",
                            "idx": fp_idx + 1,
                            "finger_index": fp["finger_index"],
                            "finger_name": finger_name(fp["finger_index"]),
                            "template_data": fp["template_data"],
                        })
                        row.db_insert()
                    frappe.db.set_value("Employee", emp_id, "modified",
                                        frappe.utils.now(), update_modified=False)
                    results.append({"user_id": u["user_id"], "machine": "ERPNext", "success": True,
                                    "message": f"OK ({len(u['fingerprints'])} fingerprints)"})
                except Exception as e_erp:
                    results.append({"user_id": u["user_id"], "machine": "ERPNext", "success": False,
                                    "message": str(e_erp)})

            pct = 30 + int((idx + 1) / total * 70)
            _update_cache({
                "progress_pct": pct,
                "done_users": idx + 1,
                "results": results,
                "phase": f"Saved to ERPNext: {idx + 1}/{total} users...",
            })

        frappe.db.commit()
        _update_cache({
            "status": "done",
            "progress_pct": 100,
            "phase": f"ERPNext sync done: {total} users",
            "results": results,
        })

    except Exception as e:
        frappe.log_error(f"_run_sync_job error: {e}")
        _update_cache({"status": "error", "error": str(e), "phase": f"Error: {e}"})


# ---------------------------------------------------------------------------
# 5. get_sync_job_status
# ---------------------------------------------------------------------------


@frappe.whitelist()
def resolve_employee_device_ids(employee_ids_json):
    """Convert ERPNext employee IDs to attendance_device_id (ZK user_id)."""
    check_biometric_access()
    try:
        employee_ids = json.loads(employee_ids_json)
        employees = frappe.get_all(
            "Employee",
            filters={"name": ["in", employee_ids]},
            fields=["name", "employee_name", "attendance_device_id"],
        )
        return {
            "status": "success",
            "employees": [
                {
                    "employee_id": e["name"],
                    "employee_name": e["employee_name"],
                    "attendance_device_id": e["attendance_device_id"],
                }
                for e in employees
            ],
        }
    except Exception as e:
        frappe.log_error(f"resolve_employee_device_ids error: {e}")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def check_employees_fingerprints_in_erp(employee_ids_json):
    """Check which employees already have fingerprints in ERP (custom_fingerprints child table)."""
    check_biometric_access()
    try:
        employee_ids = json.loads(employee_ids_json)
        existing = {}
        for emp_id in employee_ids:
            count = frappe.db.count("Fingerprint Data", {"parent": emp_id})
            if count:
                existing[emp_id] = count
        return {"status": "success", "existing": existing}
    except Exception as e:
        frappe.log_error(f"check_employees_fingerprints_in_erp error: {e}")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_sync_job_status(job_id):
    """Poll sync job status from Redis cache."""
    check_biometric_access()
    try:
        cache_key = f"biometric_sync:{job_id}"
        data = frappe.cache().get_value(cache_key)  # trả về dict trực tiếp
        if not data:
            return {"status": "not_found", "message": "Job not found or expired"}
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# 6. get_left_employees_on_machines  (preview — scan before delete)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_left_employees_on_machines(delay_days=45, include_unmatched=0):
    """
    Scan all enabled machines and classify users into 'to delete' / 'to keep'.
    Rules:
      - NEVER mark working employees for deletion (any status but Left).
      - Left employees: delete if today > relieving_date + delay_days.
      - Unmatched user_ids: delete only if include_unmatched=1.
      - ERPNext fingerprint data is NEVER touched (kept as backup).
    Returns preview data for user confirmation.
    """
    check_biometric_access()
    try:
        delay_days = int(delay_days)
        include_unmatched = int(include_unmatched)
        today_date = frappe.utils.getdate(frappe.utils.today())

        machines = get_machines(enabled_only=True)
        if not machines:
            return {"status": "error", "message": "No enabled attendance machines found"}

        # --- Scan every machine (in parallel) ---
        user_id_to_machines = {}   # str(user_id) -> [machine_name, ...]
        machine_results = []
        for m, zk_users, err in _read_users_on_machines(machines):
            if err is not None:
                machine_results.append({
                    "machine": m["name"], "device_name": m.get("device_name", ""),
                    "ip": m["ip_address"], "total_users": 0, "success": False, "error": str(err),
                })
                continue
            for u in zk_users:
                uid = str(u.user_id)
                user_id_to_machines.setdefault(uid, []).append(m["name"])
            machine_results.append({
                "machine": m["name"], "device_name": m.get("device_name", ""),
                "ip": m["ip_address"], "total_users": len(zk_users), "success": True,
            })

        all_device_ids = list(user_id_to_machines.keys())
        if not all_device_ids:
            return {
                "status": "success",
                "machines_scanned": machine_results,
                "users_to_delete": [],
                "users_to_keep_count": 0,
                "total_unique_user_ids": 0,
                "today": str(today_date),
            }

        # --- Classify user_ids ---
        # every status but Left counts as working — Inactive / Suspended must not
        # fall through to "unmatched" below
        active_emps = frappe.get_all(
            "Employee",
            filters={"status": ["!=", "Left"], "attendance_device_id": ["in", all_device_ids]},
            fields=["name", "employee_name", "attendance_device_id", "custom_group"],
        )
        active_set = {e["attendance_device_id"] for e in active_emps}
        active_by_did = {e["attendance_device_id"]: e for e in active_emps}

        left_emps = frappe.get_all(
            "Employee",
            filters={"status": "Left", "attendance_device_id": ["in", all_device_ids]},
            fields=["name", "employee_name", "attendance_device_id", "relieving_date", "custom_group"],
        )
        left_by_did = {e["attendance_device_id"]: e for e in left_emps}

        users_to_delete = []
        users_to_keep_count = 0

        for uid, mlist in sorted(user_id_to_machines.items(), key=lambda x: x[0]):
            # Rule 1: NEVER delete working employees
            if uid in active_set:
                users_to_keep_count += 1
                continue

            # Rule 2: Left employee
            if uid in left_by_did:
                emp = left_by_did[uid]
                rd = emp.get("relieving_date")
                if rd:
                    days_since = (today_date - frappe.utils.getdate(rd)).days
                    if days_since > delay_days:
                        users_to_delete.append({
                            "user_id": uid,
                            "reason_type": "left_employee",
                            "reason": f"Left {days_since}d ago (threshold: {delay_days}d)",
                            "employee_id": emp["name"],
                            "employee_name": emp["employee_name"],
                            "custom_group": emp.get("custom_group") or "",
                            "relieving_date": str(rd),
                            "days_since_relieving": days_since,
                            "machines": mlist,
                        })
                    else:
                        users_to_keep_count += 1
                else:
                    users_to_keep_count += 1   # No relieving_date — safe to keep
                continue

            # Rule 3: Not matched to any employee
            if include_unmatched:
                users_to_delete.append({
                    "user_id": uid,
                    "reason_type": "unmatched",
                    "reason": "Not in ERPNext",
                    "employee_id": None,
                    "employee_name": None,
                    "custom_group": "",
                    "relieving_date": None,
                    "days_since_relieving": None,
                    "machines": mlist,
                })
            else:
                users_to_keep_count += 1

        # Sort: left employees first (by days desc), then unmatched
        users_to_delete.sort(key=lambda x: (
            0 if x["reason_type"] == "left_employee" else 1,
            -(x.get("days_since_relieving") or 0),
        ))

        return {
            "status": "success",
            "delay_days": delay_days,
            "include_unmatched": bool(include_unmatched),
            "machines_scanned": machine_results,
            "users_to_delete": users_to_delete,
            "users_to_keep_count": users_to_keep_count,
            "total_unique_user_ids": len(all_device_ids),
            "today": str(today_date),
        }

    except Exception as e:
        frappe.log_error(f"get_left_employees_on_machines error: {e}")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# 7. delete_users_from_machines  (background job dispatcher)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def delete_users_from_machines(users_json):
    """
    Enqueue background job to delete specified users from their machines.
    users_json: [{user_id, machines:[...], ...}, ...]
    NEVER touches ERPNext fingerprint data (kept as backup for re-sync).
    """
    check_biometric_access()
    try:
        users = json.loads(users_json)
        if not users:
            frappe.throw("No users selected for deletion")
        _validate_delete_request(users)

        import uuid
        job_id = f"fp_del_{uuid.uuid4().hex[:12]}"
        cache_key = f"biometric_sync:{job_id}"

        total_ops = sum(len(u.get("machines", [])) for u in users)
        frappe.cache().set_value(cache_key, {
            "status": "queued",
            "progress_pct": 0,
            "phase": "Queued...",
            "results": [],
            "done_count": 0,
            "total_count": total_ops,
        }, expires_in_sec=3600)

        # queue="default": see _run_sync_job enqueue — don't wait behind hourly HR jobs
        frappe.enqueue(
            "customize_erpnext.network.biometric.biometric_sync._run_delete_job",
            queue="default",
            timeout=3600,
            users=users,
            cache_key=cache_key,
        )

        return {"status": "success", "job_id": job_id}

    except (frappe.ValidationError, frappe.PermissionError) as e:
        # refused request (working employee, door role, nothing selected) — not a server fault
        return {"status": "error", "message": str(e)}
    except Exception as e:
        frappe.log_error(f"delete_users_from_machines error: {e}")
        return {"status": "error", "message": str(e)}


# Refresh the device index once per this many deletes (and once at the end)
# instead of after every delete as pyzk does — bounds what is left unrefreshed
# if the connection drops mid-batch.
_DELETE_REFRESH_EVERY = 50


def _delete_users_on_machine(cfg, user_ids, report):
    """Thread worker: delete `user_ids` (str) from ONE machine over one connection.

    Calls report(user_id, success, message) exactly once per user_id, in order,
    and report(None, False, message) if the device could not be refreshed or
    re-enabled at the end. No frappe.* in here (see _read_users_on_machines).
    """
    reported = 0
    try:
        conn = connect_zk(cfg)
        unrefreshed = 0
        try:
            conn.disable_device()
            # ONE get_users() per machine; deletes then go by uid (see _zk_delete_uid)
            existing = {str(u.user_id): u for u in conn.get_users()}
            for user_id in user_ids:
                user = existing.get(user_id)
                if user is None:
                    report(user_id, True, "Already absent")
                else:
                    try:
                        _zk_delete_uid(conn, user.uid, user_id)
                        existing.pop(user_id, None)
                        unrefreshed += 1
                        report(user_id, True, "Deleted")
                    except Exception as e_del:
                        report(user_id, False, str(e_del))
                reported += 1
                if unrefreshed >= _DELETE_REFRESH_EVERY:
                    conn.refresh_data()
                    unrefreshed = 0
        finally:
            problems = []
            if unrefreshed:
                try:
                    conn.refresh_data()
                except Exception as e:
                    problems.append(f"refresh failed: {e}")
            try:
                conn.enable_device()
            except Exception as e:
                problems.append(f"re-enable failed: {e}")
            try:
                conn.disconnect()
            except Exception:
                pass
            if problems:
                report(None, False, "Device cleanup — " + "; ".join(problems))

    except Exception as e_conn:
        for user_id in user_ids[reported:]:
            report(user_id, False, f"Connection failed: {e_conn}")


def _validate_delete_request(users):
    """Refuse the whole request when it would delete, from an attendance machine,
    a user_id of an employee still working — or touch a door controller without
    the Door Control role. Machines unknown here are reported per user by the job."""
    attendance_ids = set()
    for name in {m for u in users for m in u.get("machines", [])}:
        try:
            machine = get_machine(name, allow_door=True)
        except frappe.ValidationError:
            continue
        if machine.get("is_door_control"):
            try:
                check_door_machine_access(machine)
            except frappe.PermissionError:
                frappe.throw(f"Deleting users from door controller {name} needs the Door Control role",
                             frappe.PermissionError)
        else:
            attendance_ids.update(str(u["user_id"]) for u in users if name in u.get("machines", []))
    blocked = sorted(_working_device_ids(attendance_ids), key=_user_id_sort_key)
    if blocked:
        frappe.throw(
            f"{len(blocked)} user(s) belong to employees still working and can never be deleted "
            f"from an attendance machine: {', '.join(blocked[:20])}{' …' if len(blocked) > 20 else ''}"
        )


def _run_delete_job(users, cache_key, job_id=None):
    """
    Background worker: delete users from their machines.
    One connection per machine, all machines in parallel (one thread each).
    NEVER deletes ERPNext fingerprint data.
    """
    def _update(patch):
        state = frappe.cache().get_value(cache_key)
        if state:
            state.update(patch)
            frappe.cache().set_value(cache_key, state, expires_in_sec=3600)

    try:
        _update({"status": "running", "phase": "Starting deletion..."})

        # Build machine config lookup from Attendance Machine Setting (door
        # controllers too: delete_users_from_machines checked the Door Control role)
        machines = get_machines(enabled_only=True, include_door=True)
        machine_cfg = {m["name"]: build_zk_cfg(frappe._dict(m)) for m in machines}
        door_machines = {m["name"] for m in machines if m.get("is_door_control")}

        # Group user_ids by machine for batched single-connection deletes
        machine_to_uids = {}   # machine_name -> [str user_id, ...]
        for u in users:
            for mname in u.get("machines", []):
                machine_to_uids.setdefault(mname, []).append(str(u["user_id"]))

        # re-check right before deleting (the request was validated when queued):
        # on attendance machines, user_ids of working employees are never sent
        working = _working_device_ids({uid for uids in machine_to_uids.values() for uid in uids})
        to_send, blocked_ops = {}, {}   # machine -> [user_id]
        for mname, uids in machine_to_uids.items():
            guard = mname not in door_machines
            to_send[mname] = [uid for uid in uids if not (guard and uid in working)]
            blocked_ops[mname] = [uid for uid in uids if guard and uid in working]

        # user lists cached for the xlsx no longer match these machines
        for mname in machine_to_uids:
            frappe.cache().delete_value(_machine_users_cache_key(mname))

        total_ops = sum(len(uids) for uids in machine_to_uids.values())

        # Shared with the machine threads — only touch under `lock`.
        lock = threading.Lock()
        results = []                                   # append-only: the UI renders new lines by index
        progress = {mname: 0 for mname in machine_to_uids}   # machine -> user_ids reported

        def _reporter(mname):
            def report(user_id, success, message):
                with lock:
                    results.append({
                        "user_id": user_id if user_id is not None else "-",
                        "machine": mname, "success": success, "message": message,
                    })
                    if user_id is not None:
                        progress[mname] += 1
            return report

        def _publish():
            # best-effort progress — a Redis hiccup must not abort the deletes
            try:
                with lock:
                    snapshot = list(results)
                    done = sum(progress.values())
                    parts = [f"{m} {progress[m]}/{len(uids)}" for m, uids in machine_to_uids.items()]
                _update({
                    "progress_pct": int(done / total_ops * 100) if total_ops else 0,
                    "phase": f"Deleting {done}/{total_ops} — " + " · ".join(parts),
                    "done_count": done,
                    "results": snapshot,
                })
            except Exception:
                pass

        jobs = []   # (mname, cfg, uids, report)
        for mname, uids in to_send.items():
            report = _reporter(mname)
            for uid in blocked_ops[mname]:
                report(uid, False, "Blocked — employee still working (never deleted from an attendance machine)")
            if not uids:
                continue
            cfg = machine_cfg.get(mname)
            if not cfg:
                for uid in uids:
                    report(uid, False, "Machine not found or disabled")
            else:
                jobs.append((mname, cfg, uids, report))

        if jobs:
            with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
                futures = {
                    ex.submit(_delete_users_on_machine, cfg, uids, report): (mname, uids, report)
                    for mname, cfg, uids, report in jobs
                }
                pending = set(futures)
                while pending:
                    _, pending = wait(pending, timeout=1.0)
                    _publish()

            # The worker reports every user_id itself; this only catches a bug in it
            for fut, (mname, uids, report) in futures.items():
                err = fut.exception()
                if err is not None:
                    with lock:
                        already = progress[mname] - len(blocked_ops[mname])
                    for uid in uids[already:]:
                        report(uid, False, f"Error: {err}")

        ok = sum(1 for r in results if r["success"])
        _update({
            "status": "done",
            "progress_pct": 100,
            "phase": f"Done — {ok}/{len(results)} operations successful",
            "results": results,
            "done_count": sum(progress.values()),
        })

    except Exception as e:
        frappe.log_error(f"_run_delete_job error: {e}")
        _update({"status": "error", "error": str(e), "phase": f"Error: {e}"})


# ---------------------------------------------------------------------------
# 7b. find_employee_on_machines  (locate a specific employee's user_id)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def find_employee_on_machines(query):
    """
    Locate a SINGLE employee's user_id across all enabled attendance machines,
    so it can be removed individually (targeted delete).

    `query` is matched against Employee: exact `name` (Employee ID) or
    `attendance_device_id` first, then a LIKE fallback on `employee_name`/`name`.

    Safety: Active employees are NEVER deletable here (same rule as the bulk
    scan). For Active matches we return status='blocked' without scanning.

    Returns one of:
      {status:'multiple', candidates:[{employee_id, employee_name, status, attendance_device_id}]}
      {status:'blocked',  employee:{...}, message}
      {status:'success',  employee:{...}, found_on:[{machine, device_name, on_device_name}],
                          machines_scanned:[...], today}
      {status:'error',    message}
    """
    check_biometric_access()
    try:
        query = (query or "").strip()
        if not query:
            return {"status": "error", "message": "Please enter an Employee ID, Device ID or name"}

        emp_fields = ["name", "employee_name", "status", "attendance_device_id", "relieving_date"]

        # 1) Exact match on Employee ID or attendance_device_id
        candidates = frappe.get_all(
            "Employee",
            filters={"name": query},
            fields=emp_fields,
        ) or frappe.get_all(
            "Employee",
            filters={"attendance_device_id": query},
            fields=emp_fields,
        )

        # 2) Fallback: LIKE on name / employee_name
        if not candidates:
            candidates = frappe.get_all(
                "Employee",
                filters={"employee_name": ["like", f"%{query}%"]},
                fields=emp_fields,
                limit_page_length=11,
            )
            if not candidates:
                candidates = frappe.get_all(
                    "Employee",
                    filters={"name": ["like", f"%{query}%"]},
                    fields=emp_fields,
                    limit_page_length=11,
                )

        if not candidates:
            return {"status": "error", "message": f"No employee found for '{query}'"}

        if len(candidates) > 1:
            return {
                "status": "multiple",
                "candidates": [{
                    "employee_id": c["name"],
                    "employee_name": c["employee_name"],
                    "status": c["status"],
                    "attendance_device_id": c.get("attendance_device_id") or "",
                } for c in candidates[:10]],
            }

        emp = candidates[0]
        emp_info = {
            "employee_id": emp["name"],
            "employee_name": emp["employee_name"],
            "status": emp["status"],
            "attendance_device_id": emp.get("attendance_device_id") or "",
            "relieving_date": str(emp["relieving_date"]) if emp.get("relieving_date") else None,
        }

        # Safety: never allow deleting an employee who is still working
        if _is_working(emp, frappe.utils.getdate(frappe.utils.today())):
            why = (f"Active" if emp["status"] == "Active"
                   else f"{emp['status']}, relieving date {emp_info['relieving_date'] or '—'}")
            return {
                "status": "blocked",
                "employee": emp_info,
                "message": f"This employee is still working ({why}) — their user_id cannot be deleted from the devices.",
            }

        device_id = emp_info["attendance_device_id"]
        if not device_id:
            return {
                "status": "error",
                "message": f"Employee {emp['name']} has no attendance_device_id set",
            }

        # Scan every enabled machine for this user_id
        machines = get_machines(enabled_only=True)
        if not machines:
            return {"status": "error", "message": "No enabled attendance machines found"}

        found_on = []
        machine_results = []
        target = str(device_id)
        for m, zk_users, err in _read_users_on_machines(machines):
            if err is not None:
                machine_results.append({
                    "machine": m["name"], "device_name": m.get("device_name", ""),
                    "total_users": 0, "success": False, "error": str(err),
                })
                continue
            hit = next((u for u in zk_users if str(u.user_id) == target), None)
            machine_results.append({
                "machine": m["name"], "device_name": m.get("device_name", ""),
                "total_users": len(zk_users), "success": True,
            })
            if hit:
                found_on.append({
                    "machine": m["name"],
                    "device_name": m.get("device_name", ""),
                    "on_device_name": hit.name,
                })

        return {
            "status": "success",
            "employee": emp_info,
            "found_on": found_on,
            "machines_scanned": machine_results,
            "today": str(frappe.utils.getdate(frappe.utils.today())),
        }

    except Exception as e:
        frappe.log_error(f"find_employee_on_machines error: {e}")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# 8. machine_reboot
# ---------------------------------------------------------------------------

@frappe.whitelist()
def machine_reboot(machine_name):
    """Send restart command to a ZK attendance machine."""
    check_biometric_access()
    try:
        doc = _get_managed_machine_doc(machine_name)
        cfg = build_zk_cfg(doc)
        conn = connect_zk(cfg)
        try:
            conn.restart()
        except Exception:
            pass  # restart severs the connection immediately — exception is expected
        finally:
            try:
                conn.disconnect()
            except Exception:
                pass
        return {"status": "success", "machine": machine_name, "message": "Reboot command sent successfully"}
    except Exception as e:
        frappe.log_error(f"machine_reboot error: {e}")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# 9. machine_sync_time
# ---------------------------------------------------------------------------

# ZMM220 firmware (Ver 6.60) ACKs CMD_SET_TIME and then silently drops it. Small
# corrections are dropped nearly always; larger ones usually land but not reliably
# (a measured 20s jump was dropped while a 12s one applied), and a write issued
# immediately after another is dropped almost every time. So: "kick" the clock 15s
# further away from the correct time, pause, write the real time, then verify —
# and repeat until the clock actually moved.
_TIME_KICK_SECONDS = 15
# Pause between consecutive writes; back-to-back writes get dropped.
_TIME_WRITE_PAUSE = 1.0
# Max |device - server| still considered synced, in seconds.
_TIME_SYNC_TOLERANCE = 3
_TIME_SYNC_MAX_ATTEMPTS = 3


def _read_device_drift(cfg):
    """Return (device_time, drift_seconds) on a fresh connection.

    Always use a fresh connection: reading the clock on the same connection that
    just wrote it returns stale values on this firmware.
    """
    from datetime import datetime
    conn = connect_zk(cfg)
    try:
        server_now = datetime.now()
        device_time = conn.get_time()
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass
    if not device_time:
        raise ValueError("Device did not return its clock")
    return device_time, (device_time - server_now).total_seconds()


def _write_device_time(cfg, offset_seconds=0):
    """Set the device clock to server time plus an optional offset."""
    from datetime import datetime, timedelta
    conn = connect_zk(cfg)
    try:
        conn.set_time(datetime.now() + timedelta(seconds=offset_seconds))
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass


@frappe.whitelist()
def machine_sync_time(machine_name):
    """Sync machine clock to current server time.

    Verifies the clock actually moved — the device ACKs writes it ignores, so a
    successful command is not proof of a successful sync.
    """
    check_biometric_access()
    from datetime import datetime
    try:
        doc = _get_managed_machine_doc(machine_name)
        cfg = build_zk_cfg(doc)

        device_time, drift = _read_device_drift(cfg)
        attempts = 0

        while abs(drift) > _TIME_SYNC_TOLERANCE and attempts < _TIME_SYNC_MAX_ATTEMPTS:
            attempts += 1
            # Kick away from the correct time, so the write that follows is a large
            # jump too — the device drops small corrections.
            _write_device_time(cfg, -_TIME_KICK_SECONDS if drift >= 0 else _TIME_KICK_SECONDS)
            time.sleep(_TIME_WRITE_PAUSE)
            _write_device_time(cfg, 0)
            time.sleep(_TIME_WRITE_PAUSE)
            device_time, drift = _read_device_drift(cfg)

        synced = abs(drift) <= _TIME_SYNC_TOLERANCE
        result = {
            "status": "success" if synced else "error",
            "machine": machine_name,
            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "device_time": device_time.strftime("%Y-%m-%d %H:%M:%S"),
            "drift_seconds": round(drift, 1),
            "attempts": attempts,
        }
        if not synced:
            result["message"] = f"Clock still off by {drift:+.1f}s after {attempts} attempts"
        return result
    except Exception as e:
        frappe.log_error(f"machine_sync_time error: {e}")
        return {"status": "error", "message": str(e)}


def sync_all_machine_times_scheduled():
    """Scheduler task: sync the clock on every enabled machine.

    Runs weekly (Monday 05:00) — see scheduler_events in hooks.py. Machines are
    processed one at a time; one unreachable device must not stop the rest.
    """
    results = []
    for machine in get_machines(enabled_only=True):
        name = machine["name"]
        try:
            res = machine_sync_time(name)
        except Exception as e:
            res = {"status": "error", "message": str(e)}
        results.append((name, res))

    failed = [
        f"{name}: {res.get('message') or 'unknown error'}"
        for name, res in results
        if res.get("status") != "success"
    ]
    if failed:
        frappe.log_error(
            title="Weekly machine time sync — failures",
            message="\n".join(failed),
        )
    return {
        "total": len(results),
        "synced": len(results) - len(failed),
        "failed": len(failed),
    }


# ---------------------------------------------------------------------------
# 10. machine_get_info
# ---------------------------------------------------------------------------

@frappe.whitelist()
def machine_get_info(machine_name):
    """
    Read hardware & firmware info from ZK device.
    Uses conn.read_sizes() to get user/finger/record counts + capacity.
    """
    check_biometric_access()
    try:
        doc = _get_managed_machine_doc(machine_name)
        cfg = build_zk_cfg(doc)
        conn = connect_zk(cfg)
        try:
            conn.disable_device()

            # Read memory sizes — populates conn.users, conn.fingers, conn.records, etc.
            try:
                conn.read_sizes()
            except Exception:
                pass

            def _safe(fn):
                try:
                    return fn()
                except Exception:
                    return ""

            firmware_version = _safe(conn.get_firmware_version)
            serial_number    = _safe(conn.get_serialnumber)
            platform         = _safe(conn.get_platform)
            mac_address      = _safe(conn.get_mac)
            device_name_hw   = _safe(conn.get_device_name)
            fp_version       = _safe(conn.get_fp_version)
            device_time_str  = "N/A"
            try:
                dt = conn.get_time()
                if dt:
                    device_time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

            users_count   = getattr(conn, "users", 0) or 0
            users_cap     = getattr(conn, "users_cap", 0) or 0
            fingers_count = getattr(conn, "fingers", 0) or 0
            fingers_cap   = getattr(conn, "fingers_cap", 0) or 0
            records_count = getattr(conn, "records", 0) or 0
            rec_cap       = getattr(conn, "rec_cap", 0) or 0
            faces_count   = getattr(conn, "faces", 0) or 0
            faces_cap     = getattr(conn, "faces_cap", 0) or 0
        finally:
            try:
                conn.enable_device()
            except Exception:
                pass
            conn.disconnect()

        return {
            "status":           "success",
            "machine":          machine_name,
            "ip_address":       doc.ip_address,
            "port":             doc.port,
            "model":            doc.model or "",
            "location":         doc.location or "",
            "device_name":      device_name_hw or doc.device_name or "",
            "firmware_version": str(firmware_version),
            "serial_number":    str(serial_number),
            "platform":         str(platform),
            "mac_address":      str(mac_address),
            "fp_version":       str(fp_version),
            "user_count":       users_count,
            "user_capacity":    users_cap,
            "fp_count":         fingers_count,
            "fp_capacity":      fingers_cap,
            "record_count":     records_count,
            "record_capacity":  rec_cap,
            "face_count":       faces_count,
            "face_capacity":    faces_cap,
            "device_time":      device_time_str,
        }
    except Exception as e:
        frappe.log_error(f"machine_get_info error: {e}")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# 11. machine_get_users / download_machine_users_xlsx
# ---------------------------------------------------------------------------

# The device list read by machine_get_users is kept this long so the xlsx
# download never talks to the device: it goes through open_url_post (a form
# POST), and any server error there replaces the page with a raw JSON error.
_MACHINE_USERS_CACHE_S = 30 * 60

# pyzk zk/const.py USER_DEFAULT / USER_ENROLLER / USER_MANAGER / USER_ADMIN
_PRIVILEGE_LABELS = {0: "User", 2: "Enroller", 6: "Manager", 14: "Admin"}


def _machine_users_cache_key(machine_name):
    return f"biometric_sync:machine_users:{machine_name}"


def _device_user_row(u, fingers=None):
    """One device user as plain data. The PIN itself is never sent, only whether one is set.
    `fingers`: {uid: [finger indexes]} when the templates were read (else the key is absent)."""
    row = {
        "uid": u.uid,
        "user_id": str(u.user_id),
        "name": u.name or "",
        "privilege": _PRIVILEGE_LABELS.get(u.privilege, str(u.privilege)),
        "has_password": bool(u.password),
        "card": str(u.card) if u.card else "",
        "group_id": str(u.group_id or ""),
    }
    if fingers is not None:
        row["fingers"] = fingers.get(u.uid, [])
    return row


def _employees_by_device_id(device_ids):
    """attendance_device_id -> Employee fields; an Active employee wins over others."""
    if not device_ids:
        return {}
    emps = frappe.get_all(
        "Employee",
        filters={"attendance_device_id": ["in", list(device_ids)]},
        fields=["name", "employee_name", "status", "relieving_date", "custom_group",
                "attendance_device_id"],
    )
    out = {}
    for e in emps:
        did = str(e.attendance_device_id)
        if did not in out or (e.status == "Active" and out[did].status != "Active"):
            out[did] = e
    return out


def _with_employees(rows):
    """Copy of device user rows with the matching ERPNext employee added."""
    emp_by_did = _employees_by_device_id({r["user_id"] for r in rows})
    today = frappe.utils.getdate(frappe.utils.today())
    out = []
    for r in rows:
        e = emp_by_did.get(r["user_id"])
        out.append({
            **r,
            "employee": e.name if e else "",
            "employee_name": e.employee_name if e else "",
            "status": e.status if e else "",
            "relieving_date": str(e.relieving_date) if e and e.relieving_date else "",
            "custom_group": (e.custom_group or "") if e else "",
            "is_working": bool(e and _is_working(e, today)),
        })
    return out


@frappe.whitelist()
def machine_get_users(machine_name):
    """Every user stored on one machine, matched to ERPNext employees by
    attendance_device_id. The device list is cached for download_machine_users_xlsx."""
    check_biometric_access()
    try:
        machine = _get_managed_machine_doc(machine_name)
        users, fingers = _read_machine_users(machine, with_fingers=True)
        rows = sorted((_device_user_row(u, fingers) for u in users), key=lambda r: r["uid"])
        read_at = frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S")
        frappe.cache().set_value(
            _machine_users_cache_key(machine_name),
            {"read_at": read_at, "users": rows},
            expires_in_sec=_MACHINE_USERS_CACHE_S,
        )
        return {
            "status": "success",
            "machine": machine_name,
            "is_door_control": bool(machine.is_door_control),
            "read_at": read_at,
            "users": _with_employees(rows),
        }
    except Exception as e:
        frappe.log_error(f"machine_get_users error: {e}")
        return {"status": "error", "message": str(e)}


def _xlsx_sheet_title(name, used):
    """Excel sheet name: max 31 chars, none of []:*?/\\ , unique in the workbook."""
    import re
    base = re.sub(r"[\[\]:*?/\\]", "-", name or "Sheet").strip("'")[:31] or "Sheet"
    title, n = base, 2
    while title.lower() in used:
        suffix = f" ({n})"
        title, n = base[:31 - len(suffix)] + suffix, n + 1
    used.add(title.lower())
    return title


def _user_id_sort_key(user_id):
    """Numeric IDs in numeric order, then the rest alphabetically."""
    return (0, int(user_id), "") if user_id.isdigit() else (1, 0, user_id)


@frappe.whitelist()
def download_machine_users_xlsx(machine_names):
    """xlsx of the user lists last read by machine_get_users (never re-reads a device).

    One sheet per machine; with several machines an "All Machines" sheet comes
    first: one row per user_id with a ✓ column per machine. Employee data is
    looked up fresh. A machine whose list is not in the cache gets a sheet that
    says so instead of an error (see _MACHINE_USERS_CACHE_S).
    """
    check_biometric_access()
    import io
    import re
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    if isinstance(machine_names, str):
        machine_names = json.loads(machine_names)
    machine_names = [m for m in dict.fromkeys(machine_names or []) if m]
    if not machine_names:
        frappe.throw("No machine selected")

    loaded = {}   # machine -> {"machine", "read_at", "users"} (with employees)
    for name in machine_names:
        machine = _get_managed_machine_doc(name)   # same permission rule as reading
        cached = frappe.cache().get_value(_machine_users_cache_key(name))
        loaded[name] = {
            "machine": machine,
            "read_at": cached["read_at"] if cached else None,
            "users": cached["users"] if cached else None,
        }

    # one Employee query for all machines
    all_ids = {r["user_id"] for d in loaded.values() for r in (d["users"] or [])}
    emp_by_did = _employees_by_device_id(all_ids)

    def emp_cols(user_id):
        e = emp_by_did.get(user_id)
        if not e:
            return ["", "", "Not in ERP", None, ""]
        return [e.name, e.employee_name, e.status, e.relieving_date, e.custom_group or ""]

    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="1F4E79")
    caption_font = Font(bold=True, size=12)

    def write_sheet(ws, caption, headers, rows, widths, date_cols=(), text_cols=()):
        ws.cell(row=1, column=1, value=caption).font = caption_font
        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=2, column=c, value=h)
            cell.font, cell.fill = head_font, head_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for r, row in enumerate(rows, 3):
            for c, v in enumerate(row, 1):
                cell = ws.cell(row=r, column=c, value=v)
                if c in date_cols and v:
                    cell.number_format = "DD/MM/YYYY"
                elif c in text_cols:
                    cell.number_format = "@"   # keep leading zeros of IDs
        for c, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(c)].width = w
        ws.freeze_panes = "A3"
        if rows:
            ws.auto_filter.ref = f"A2:{get_column_letter(len(headers))}{len(rows) + 2}"

    wb = Workbook()
    wb.remove(wb.active)
    used_titles = set()
    emp_headers = ["Employee", "ERP Name", "ERP Status", "Relieving Date", "Group"]
    emp_widths = [14, 30, 12, 14, 16]

    if len(machine_names) > 1:
        ok_names = [n for n in machine_names if loaded[n]["users"] is not None]
        by_uid = {}   # user_id -> (first name on device, {machine})
        for n in ok_names:
            for r in loaded[n]["users"]:
                entry = by_uid.setdefault(r["user_id"], [r["name"], set()])
                if not entry[0]:
                    entry[0] = r["name"]
                entry[1].add(n)
        rows = []
        for i, uid in enumerate(sorted(by_uid, key=_user_id_sort_key), 1):
            name_on_device, on = by_uid[uid]
            rows.append([i, uid, name_on_device, *emp_cols(uid), len(on),
                         *["✓" if n in on else "" for n in ok_names]])
        missing = [n for n in machine_names if loaded[n]["users"] is None]
        caption = f"All machines — {len(by_uid)} distinct user IDs on {len(ok_names)} machine(s)"
        if missing:
            caption += f" — NOT LOADED: {', '.join(missing)}"
        write_sheet(
            wb.create_sheet(_xlsx_sheet_title("All Machines", used_titles)), caption,
            ["#", "User ID", "Name on Device", *emp_headers, "On # Machines", *ok_names],
            rows, [6, 12, 26, *emp_widths, 10, *[max(10, len(n) + 2) for n in ok_names]],
            date_cols={7}, text_cols={2},
        )

    for n in machine_names:
        d = loaded[n]
        ws = wb.create_sheet(_xlsx_sheet_title(n, used_titles))
        if d["users"] is None:
            ws.cell(row=1, column=1,
                    value=f"{n}: user list not loaded (or older than "
                          f"{_MACHINE_USERS_CACHE_S // 60} min) — load it on the page, then download again."
                    ).font = caption_font
            continue
        kind = "door controller" if d["machine"].is_door_control else "attendance machine"
        caption = (f"{n} ({kind}, {d['machine'].ip_address}) — {len(d['users'])} users"
                   f" — read from device at {d['read_at']}")
        rows = [
            [i, r["uid"], r["user_id"], r["name"], r["privilege"],
             "Yes" if r["has_password"] else "", r["card"], r["group_id"],
             len(r.get("fingers") or []), ", ".join(str(f) for f in r.get("fingers") or []),
             *emp_cols(r["user_id"])]
            for i, r in enumerate(d["users"], 1)
        ]
        write_sheet(
            ws, caption,
            ["#", "UID", "User ID", "Name on Device", "Privilege", "PIN Set", "Card", "Group ID",
             "Fingers", "Finger IDs (0-9)", *emp_headers],
            rows, [6, 8, 12, 26, 10, 8, 12, 9, 8, 14, *emp_widths],
            date_cols={14}, text_cols={3, 7, 8, 10},
        )

    buf = io.BytesIO()
    wb.save(buf)
    label = machine_names[0] if len(machine_names) == 1 else "All_Machines"
    safe = re.sub(r"[^\w\-]+", "_", label, flags=re.UNICODE).strip("_") or "Machine"
    frappe.response["filename"] = f"Machine_Users_{safe}_{frappe.utils.nowdate()}.xlsx"
    frappe.response["filecontent"] = buf.getvalue()
    frappe.response["type"] = "binary"
