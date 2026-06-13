"""Keep Employee Uniform Profile.shoe_rack_location in sync with Shoe Rack assignments."""
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


@frappe.whitelist(methods=["POST"])
def backfill_shoe_rack_locations():
    """
    One-shot sync of shoe_rack_location on ALL profiles from Shoe Rack assignments.
    bench --site <site> execute customize_erpnext.uniform_control.api.shoe_rack_sync.backfill_shoe_rack_locations
    """
    frappe.only_for(("System Manager", "Uniform Manager"))

    emp_rack = {}
    for r in frappe.get_all(
        "Shoe Rack",
        fields=["rack_display_name", *COMPARTMENT_FIELDS],
    ):
        for field in COMPARTMENT_FIELDS:
            if r.get(field):
                emp_rack.setdefault(r.get(field), r.rack_display_name)

    profiles = frappe.get_all(
        "Employee Uniform Profile",
        fields=["name", "employee", "shoe_rack_location"],
    )
    updated = 0
    for p in profiles:
        target = emp_rack.get(p.employee)
        if (p.shoe_rack_location or None) != (target or None):
            frappe.db.set_value(
                "Employee Uniform Profile", p.name,
                "shoe_rack_location", target,
                update_modified=False,
            )
            updated += 1

    return {
        "profiles": len(profiles),
        "updated": updated,
        "employees_with_rack": len(emp_rack),
    }
