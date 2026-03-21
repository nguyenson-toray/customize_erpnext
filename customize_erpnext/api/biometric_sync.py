"""
API endpoints for Sync Fingerprint feature
Reuses ZK logic from biometric-attendance-sync-tool
"""

import frappe
import json
import time
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_machine_doc(machine_name):
    """Return Attendance Machine doc as dict."""
    doc = frappe.get_doc("Attendance Machine", machine_name)
    return doc


def _build_zk_device(doc):
    """Build ZK device config dict from Attendance Machine doc."""
    return {
        "ip": doc.ip_address,
        "port": int(doc.port or 4370),
        "timeout": int(doc.timeout or 10),
        "force_udp": bool(doc.force_udp),
        "ommit_ping": bool(doc.ommit_ping),
    }


def _connect_zk(device_cfg):
    """Connect to ZK device. Returns conn object or raises."""
    from zk import ZK
    zk = ZK(
        device_cfg["ip"],
        port=device_cfg["port"],
        timeout=device_cfg["timeout"],
        force_udp=device_cfg["force_udp"],
        ommit_ping=device_cfg["ommit_ping"],
    )
    conn = zk.connect()
    if not conn:
        raise ConnectionError(f"Cannot connect to {device_cfg['ip']}")
    return conn


def _shorten_name(full_name, max_length=24):
    """Shorten Vietnamese name for device compatibility."""
    try:
        from unidecode import unidecode
        text = unidecode(full_name or "")
    except ImportError:
        text = (full_name or "").encode("ascii", "ignore").decode()
    text = " ".join(text.split()).strip()
    if len(text) > max_length:
        parts = text.split()
        if len(parts) > 1:
            initials = "".join(p[0].upper() for p in parts[:-1])
            return f"{initials} {parts[-1]}"
        return text[:max_length]
    return text


# ---------------------------------------------------------------------------
# 1. get_attendance_machines
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_attendance_machines():
    """Return list of enabled Attendance Machines."""
    machines = frappe.get_all(
        "Attendance Machine",
        filters={"enable": 1},
        fields=["name", "id", "device_name", "ip_address", "port", "model",
                "location", "master_device", "timeout", "force_udp", "ommit_ping"],
        order_by="id asc",
    )
    return {"status": "success", "machines": machines}


# ---------------------------------------------------------------------------
# 2. get_master_device_users
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_master_device_users(machine_name):
    """
    Connect to master machine, get all users, cross-match with ERPNext employees.
    Returns list of users with matched employee info.
    """
    try:
        doc = _get_machine_doc(machine_name)
        device_cfg = _build_zk_device(doc)

        conn = _connect_zk(device_cfg)
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
        frappe.enqueue(
            "customize_erpnext.api.biometric_sync._run_sync_job",
            queue="long",
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
        master_cfg = _build_zk_device(master_doc)

        conn = _connect_zk(master_cfg)
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
                            "finger_name": _get_finger_name(fp["finger_index"]),
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


def _sync_user_to_device(user_data, machine_name, device_cfg):
    """Sync single user fingerprints to one target device."""
    from zk.base import Finger
    user_id = user_data["user_id"]

    try:
        conn = _connect_zk(device_cfg)
        conn.disable_device()

        # Delete existing user
        existing = conn.get_users()
        if any(u.user_id == user_id for u in existing):
            conn.delete_user(user_id=user_id)
            time.sleep(0.1)

        # Create user
        shortened = _shorten_name(user_data["name"], 24)
        if user_data.get("password"):
            conn.set_user(
                name=shortened, privilege=user_data["privilege"],
                password=user_data["password"], group_id=user_data.get("group_id", ""),
                user_id=user_id,
            )
        else:
            conn.set_user(
                name=shortened, privilege=user_data["privilege"],
                group_id=user_data.get("group_id", ""), user_id=user_id,
            )

        # Verify
        users_after = conn.get_users()
        created = next((u for u in users_after if u.user_id == user_id), None)
        if not created:
            conn.enable_device()
            conn.disconnect()
            return {"user_id": user_id, "machine": machine_name, "success": False,
                    "message": "Failed to create user on device"}

        # Send fingerprints — only actual templates (same pattern as utilities.sync_employee_to_single_machine)
        decoded = {}
        for fp in user_data["fingerprints"]:
            try:
                decoded[fp["finger_index"]] = base64.b64decode(fp["template_data"])
            except Exception:
                pass

        templates = []
        for finger_index, template_data in decoded.items():
            templates.append(Finger(uid=created.uid, fid=finger_index, valid=True, template=template_data))
        fp_count = len(templates)

        if templates:
            conn.save_user_template(created, templates)
        conn.enable_device()
        conn.disconnect()

        return {"user_id": user_id, "machine": machine_name, "success": True,
                "message": f"OK ({fp_count} fingerprints)"}

    except Exception as e:
        return {"user_id": user_id, "machine": machine_name, "success": False, "message": str(e)}


# ---------------------------------------------------------------------------
# 5. get_sync_job_status
# ---------------------------------------------------------------------------


def _get_finger_name(finger_index):
    """Map finger index (0-9) to human-readable name."""
    names = {
        0: "Left Little", 1: "Left Ring", 2: "Left Middle", 3: "Left Index", 4: "Left Thumb",
        5: "Right Thumb", 6: "Right Index", 7: "Right Middle", 8: "Right Ring", 9: "Right Little",
    }
    return names.get(int(finger_index), f"Finger {finger_index}")


@frappe.whitelist()
def resolve_employee_device_ids(employee_ids_json):
    """Convert ERPNext employee IDs to attendance_device_id (ZK user_id)."""
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
    try:
        cache_key = f"biometric_sync:{job_id}"
        data = frappe.cache().get_value(cache_key)  # trả về dict trực tiếp
        if not data:
            return {"status": "not_found", "message": "Job không tồn tại hoặc đã hết hạn"}
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
      - NEVER mark Active employees for deletion.
      - Left employees: delete if today > relieving_date + delay_days.
      - Unmatched user_ids: delete only if include_unmatched=1.
      - ERPNext fingerprint data is NEVER touched (kept as backup).
    Returns preview data for user confirmation.
    """
    try:
        delay_days = int(delay_days)
        include_unmatched = int(include_unmatched)
        today_date = frappe.utils.getdate(frappe.utils.today())

        machines = frappe.get_all(
            "Attendance Machine",
            filters={"enable": 1},
            fields=["name", "ip_address", "port", "timeout", "force_udp", "ommit_ping", "device_name"],
            order_by="name asc",
        )
        if not machines:
            return {"status": "error", "message": "No enabled attendance machines found"}

        # --- Scan every machine ---
        user_id_to_machines = {}   # str(user_id) -> [machine_name, ...]
        machine_results = []
        for m in machines:
            dev_cfg = _build_zk_device(frappe._dict(m))
            try:
                conn = _connect_zk(dev_cfg)
                conn.disable_device()
                try:
                    zk_users = conn.get_users()
                finally:
                    conn.enable_device()
                    conn.disconnect()
                for u in zk_users:
                    uid = str(u.user_id)
                    user_id_to_machines.setdefault(uid, []).append(m["name"])
                machine_results.append({
                    "machine": m["name"], "device_name": m.get("device_name", ""),
                    "ip": m["ip_address"], "total_users": len(zk_users), "success": True,
                })
            except Exception as e:
                machine_results.append({
                    "machine": m["name"], "device_name": m.get("device_name", ""),
                    "ip": m["ip_address"], "total_users": 0, "success": False, "error": str(e),
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
        active_emps = frappe.get_all(
            "Employee",
            filters={"status": "Active", "attendance_device_id": ["in", all_device_ids]},
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
            # Rule 1: NEVER delete Active employees
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
    try:
        users = json.loads(users_json)
        if not users:
            frappe.throw("No users selected for deletion")

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

        frappe.enqueue(
            "customize_erpnext.api.biometric_sync._run_delete_job",
            queue="long",
            timeout=3600,
            users=users,
            cache_key=cache_key,
        )

        return {"status": "success", "job_id": job_id}

    except Exception as e:
        frappe.log_error(f"delete_users_from_machines error: {e}")
        return {"status": "error", "message": str(e)}


def _run_delete_job(users, cache_key, job_id=None):
    """
    Background worker: delete users from their machines.
    Groups by machine for efficiency (one connection per machine).
    NEVER deletes ERPNext fingerprint data.
    """
    def _update(patch):
        state = frappe.cache().get_value(cache_key)
        if state:
            state.update(patch)
            frappe.cache().set_value(cache_key, state, expires_in_sec=3600)

    try:
        _update({"status": "running", "phase": "Starting deletion..."})

        # Build machine config lookup from Attendance Machine doctype
        machines = frappe.get_all(
            "Attendance Machine",
            filters={"enable": 1},
            fields=["name", "ip_address", "port", "timeout", "force_udp", "ommit_ping"],
        )
        machine_cfg = {m["name"]: _build_zk_device(frappe._dict(m)) for m in machines}

        # Group user_ids by machine for batched single-connection deletes
        machine_to_users = {}   # machine_name -> [{user_id, employee_name, ...}]
        for u in users:
            for mname in u.get("machines", []):
                machine_to_users.setdefault(mname, []).append(u)

        results = []
        total_ops = sum(len(ulist) for ulist in machine_to_users.values())
        done = 0

        for mname, ulist in machine_to_users.items():
            cfg = machine_cfg.get(mname)
            if not cfg:
                for u in ulist:
                    results.append({
                        "user_id": u["user_id"], "machine": mname,
                        "success": False, "message": "Machine not found or disabled",
                    })
                    done += 1
                continue

            try:
                conn = _connect_zk(cfg)
                conn.disable_device()
                try:
                    existing = conn.get_users()
                    existing_map = {str(u.user_id): u for u in existing}

                    for u in ulist:
                        uid = str(u["user_id"])
                        pct = int(done / total_ops * 100) if total_ops else 0
                        _update({
                            "progress_pct": pct,
                            "phase": f"Deleting {uid} from {mname}...",
                            "done_count": done,
                            "results": results,
                        })

                        if uid in existing_map:
                            try:
                                conn.delete_user(user_id=existing_map[uid].user_id)
                                time.sleep(0.1)
                                results.append({
                                    "user_id": uid, "machine": mname,
                                    "success": True, "message": "Deleted",
                                })
                            except Exception as e_del:
                                results.append({
                                    "user_id": uid, "machine": mname,
                                    "success": False, "message": str(e_del),
                                })
                        else:
                            results.append({
                                "user_id": uid, "machine": mname,
                                "success": True, "message": "Already absent",
                            })
                        done += 1
                finally:
                    conn.enable_device()
                    conn.disconnect()

            except Exception as e_conn:
                for u in ulist:
                    results.append({
                        "user_id": u["user_id"], "machine": mname,
                        "success": False, "message": f"Connection failed: {e_conn}",
                    })
                    done += 1

        ok = sum(1 for r in results if r["success"])
        _update({
            "status": "done",
            "progress_pct": 100,
            "phase": f"Done — {ok}/{len(results)} operations successful",
            "results": results,
            "done_count": done,
        })

    except Exception as e:
        frappe.log_error(f"_run_delete_job error: {e}")
        _update({"status": "error", "error": str(e), "phase": f"Error: {e}"})
