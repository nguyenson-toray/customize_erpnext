import frappe


def execute():
    """Index for the automatic log pull: its per-machine cursor is
    MAX(time) WHERE device_id = <machine> on ~1M Employee Checkin rows."""
    frappe.db.add_index("Employee Checkin", ["device_id", "time"], "idx_emp_checkin_device_time")
