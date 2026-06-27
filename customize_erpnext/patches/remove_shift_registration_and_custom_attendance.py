"""
Cleanup of deprecated Shift Registration + Custom Attendance subsystems.

- Shift Registration / Shift Registration Detail: doctypes already removed from
  the registry, only empty orphan tables remained. Shift overrides now come from
  the standard Shift Assignment doctype.
- Custom Attendance: unused subsystem (0 rows, scheduler disabled).
- Employee Checkin.custom_attendance_link: hidden/read-only/NULL Link to the now
  deleted Custom Attendance doctype — removed. (Also removed from the LMS app's
  misconfigured custom_field.json fixture so it no longer resurrects on migrate.)

This patch is idempotent — safe to re-run.
"""

import json

import frappe


def execute():
    # 1. Remove the unused custom field Employee Checkin.custom_attendance_link
    if frappe.db.exists("Custom Field", "Employee Checkin-custom_attendance_link"):
        frappe.delete_doc("Custom Field", "Employee Checkin-custom_attendance_link",
                          force=True, ignore_permissions=True)
        print("   ✓ Removed custom field Employee Checkin-custom_attendance_link")

    # 1b. Drop the orphan column if it lingers (delete_doc doesn't always drop it)
    cols = [c["Field"] for c in frappe.db.sql("SHOW COLUMNS FROM `tabEmployee Checkin`", as_dict=True)]
    if "custom_attendance_link" in cols:
        frappe.db.sql_ddl("ALTER TABLE `tabEmployee Checkin` DROP COLUMN `custom_attendance_link`")
        print("   ✓ Dropped orphan column tabEmployee Checkin.custom_attendance_link")

    # 2. Strip the field from any Employee Checkin field_order Property Setter
    for ps in frappe.get_all(
        "Property Setter",
        filters={"doc_type": "Employee Checkin", "property": "field_order"},
        fields=["name", "value"],
    ):
        if ps.value and "custom_attendance_link" in ps.value:
            try:
                order = [f for f in json.loads(ps.value) if f != "custom_attendance_link"]
                frappe.db.set_value("Property Setter", ps.name, "value", json.dumps(order))
                print(f"   ✓ Cleaned field_order Property Setter {ps.name}")
            except Exception as e:
                print(f"   ⚠️  Could not clean {ps.name}: {e}")

    # 3. Delete the Custom Attendance DocType (drops tabCustom Attendance)
    if frappe.db.exists("DocType", "Custom Attendance"):
        frappe.delete_doc("DocType", "Custom Attendance", force=True, ignore_permissions=True)
        print("   ✓ Deleted DocType Custom Attendance")

    # 4. Drop orphan Shift Registration tables (empty). Keep tabShift Name (in use).
    for table in ("tabShift Registration Detail", "tabShift Registration"):
        frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `{table}`")
        print(f"   ✓ Dropped orphan table {table} (if existed)")

    frappe.db.commit()
