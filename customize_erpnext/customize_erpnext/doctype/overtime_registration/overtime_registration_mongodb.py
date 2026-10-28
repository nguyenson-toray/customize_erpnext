"""ERPNext -> MongoDB: push one Overtime Registration into the legacy OtRegister.

Form button "Sync to MongoDB" (System Manager / HR Manager / HR User only).
- One MongoDB document per row, requestNo = the registration name (OTR-...).
- Re-sync replaces: every document with that requestNo is deleted first.
- Registrations that came FROM MongoDB (row reason "Request number: ...") are
  refused, otherwise the legacy system would get the request twice.
- The reverse sync (network/biometric/mongodb_sync.py) skips requestNo "OTR-"
  so a pushed registration is never pulled back as a new one.
"""

from datetime import datetime

import frappe
from frappe import _
from frappe.utils import getdate

from customize_erpnext.network.biometric.mongodb_sync import _get_mongo

SYNC_ROLES = ("System Manager", "HR Manager", "HR User")


def _hhmm(value):
    """Time / timedelta / 'H:MM:SS' -> 'HH:MM' (the legacy format)."""
    if hasattr(value, "total_seconds"):
        minutes = int(value.total_seconds()) // 60
        return f"{minutes // 60:02d}:{minutes % 60:02d}"
    parts = str(value).split(":")
    return f"{int(parts[0]):02d}:{int(parts[1]):02d}"


def _as_mongo_date(value):
    # The legacy MongoDB stores local midnight labeled as UTC (naive datetime)
    d = getdate(value)
    return datetime(d.year, d.month, d.day)


@frappe.whitelist()
def sync_to_mongodb(name):
    frappe.only_for(SYNC_ROLES)
    doc = frappe.get_doc("Overtime Registration", name)
    doc.check_permission("read")

    if doc.docstatus == 2:
        frappe.throw(_("Cancelled registrations cannot be synced to MongoDB."))
    if any("Request number:" in (row.reason or "") for row in doc.ot_employees):
        frappe.throw(_("This registration was imported from MongoDB and cannot be synced back."))

    request_date = _as_mongo_date(doc.request_date or doc.creation)
    records = [
        {
            "requestNo": doc.name,
            "requestDate": request_date,
            "otDate": _as_mongo_date(row.date),
            "otTimeBegin": _hhmm(row.begin_time),
            "otTimeEnd": _hhmm(row.end_time),
            "empId": row.employee,
            "name": row.employee_name or "",
        }
        for row in doc.ot_employees
        if row.employee and row.date and row.begin_time and row.end_time
    ]
    if not records:
        frappe.throw(_("No complete rows (employee, date, begin and end time) to sync."))

    client, db = _get_mongo()
    try:
        collection = db[frappe.conf.get("biometric_mongodb_ot_collection", "OtRegister")]
        deleted = collection.delete_many({"requestNo": doc.name}).deleted_count
        collection.insert_many(records)
    finally:
        client.close()

    doc.add_comment("Info", _("Synced {0} row(s) to MongoDB ({1} old row(s) replaced)").format(
        len(records), deleted))
    return {"inserted": len(records), "deleted": deleted}


def _was_synced(name):
    # Marker = the timeline comment above ("MongoDB" survives translation).
    # Only synced registrations touch MongoDB, so cancel/delete of the others
    # still works while MongoDB is down.
    return frappe.db.exists("Comment", {
        "reference_doctype": "Overtime Registration",
        "reference_name": name,
        "comment_type": "Info",
        "content": ["like", "%MongoDB%"],
    })


def remove_from_mongodb(doc, method=None):
    """doc_events on_cancel / on_trash: drop the rows pushed by sync_to_mongodb.

    Raises when MongoDB is unreachable so the cancel/delete is rolled back
    instead of leaving OT the legacy system would still count.
    """
    if not _was_synced(doc.name):
        return
    try:
        client, db = _get_mongo()
    except Exception as e:
        frappe.throw(_("Cannot reach MongoDB to remove this registration's OT, so it was not cancelled/deleted. Please try again later. ({0})").format(e))
    try:
        collection = db[frappe.conf.get("biometric_mongodb_ot_collection", "OtRegister")]
        deleted = collection.delete_many({"requestNo": doc.name}).deleted_count
    finally:
        client.close()
    if method == "on_cancel":
        doc.add_comment("Info", _("Removed {0} row(s) from MongoDB").format(deleted))
