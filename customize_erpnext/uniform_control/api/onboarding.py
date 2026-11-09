"""Employee Uniform Profile creation.

Profiles are created when first needed — Get Employees on a Uniform Allocation,
the dashboard's "Create Profiles" banner, and the nightly job — through
utils.ensure_profiles. The Employee.after_insert hook stays off (disabled
28/07/2026, see hooks.py).
"""
import frappe

from customize_erpnext.uniform_control.utils import ensure_profiles, get_employee_id_prefix


@frappe.whitelist(methods=["POST"])
def backfill_uniform_profiles(include_left=0):
    """Create missing profiles for all managed Active employees; include_left=1
    also covers employees who left (their profile keeps the issuance history).
    bench --site <site> execute customize_erpnext.uniform_control.api.onboarding.backfill_uniform_profiles
    """
    if not frappe.has_permission("Employee Uniform Profile", "create"):
        frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

    employees = None
    if frappe.utils.cint(include_left):
        prefix = get_employee_id_prefix()
        filters = {"name": ["like", f"{prefix}%"]} if prefix else {}
        employees = frappe.get_all("Employee", filters=filters, pluck="name")
    return {"created": ensure_profiles(employees)}
