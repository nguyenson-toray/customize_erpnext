import frappe

SETTING = "Attendance Machine Setting"
DEFAULTS = (("peak_times", "07:30,07:45,17:00,18:00"), ("peak_window_minutes", 15))


def execute():
    """Single already exists, so the new fields' defaults are never written by
    migrate. Set them once; a later cleared Peak Times (= disabled) is kept."""
    for field, value in DEFAULTS:
        if not frappe.db.sql("SELECT 1 FROM `tabSingles` WHERE doctype=%s AND field=%s", (SETTING, field)):
            frappe.db.set_single_value(SETTING, field, value)
