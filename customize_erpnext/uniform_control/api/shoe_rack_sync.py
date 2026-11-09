"""Keep Employee Uniform Profile.shoe_rack_location in sync with Shoe Rack assignments.
The nightly utils.sync_profile_copies re-syncs every profile as well."""
import frappe

from customize_erpnext.uniform_control.utils import get_shoe_rack_for_employee

COMPARTMENT_FIELDS = ("compartment_1_employee", "compartment_2_employee")


def sync_profiles_on_rack_update(doc, method=None):
    """on_update on Shoe Rack — refresh shoe_rack_location for every employee
    added to or removed from this rack."""
    try:
        employees = set()
        for field in COMPARTMENT_FIELDS:
            if doc.get(field):
                employees.add(doc.get(field))

        before = doc.get_doc_before_save()
        if before:
            for field in COMPARTMENT_FIELDS:
                if before.get(field):
                    employees.add(before.get(field))

        for emp in employees:
            profile = frappe.db.get_value("Employee Uniform Profile", {"employee": emp})
            if profile:
                frappe.db.set_value(
                    "Employee Uniform Profile",
                    profile,
                    "shoe_rack_location",
                    get_shoe_rack_for_employee(emp),
                )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Shoe Rack Profile Sync Error")
