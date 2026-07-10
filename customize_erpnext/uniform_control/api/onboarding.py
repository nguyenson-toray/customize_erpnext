"""Employee onboarding hook — auto-create Uniform Profile.

Allocations are NOT auto-created: HR creates Uniform Allocation manually (grouped)
when needed, instead of one fragmented draft per new employee.
"""
import frappe

from customize_erpnext.uniform_control.utils import (
    build_variant_cache,
    get_variant_for_profile,
    get_employee_id_prefix,
    is_managed_employee,
)

# Employee.gender (Gender doctype values, EN or VI) → profile uniform_gender select
GENDER_PROFILE_MAP = {"Male": "Male", "Female": "Female", "Nam": "Male", "Nữ": "Female"}


def create_uniform_profile_on_employee_insert(doc, method=None):
    """
    after_insert on Employee — create Employee Uniform Profile if not exists,
    then link it back via custom_uniform_profile.
    """
    if not is_managed_employee(doc.name):
        return
    if frappe.db.exists("Employee Uniform Profile", {"employee": doc.name}):
        return

    try:
        profile = frappe.new_doc("Employee Uniform Profile")
        profile.employee = doc.name
        profile.employee_name = doc.employee_name
        profile.department = doc.department
        profile.designation = doc.designation
        profile.uniform_gender = GENDER_PROFILE_MAP.get(doc.gender or "", "")
        profile.insert(ignore_permissions=True)

        # Link back on Employee
        frappe.db.set_value("Employee", doc.name, "custom_uniform_profile", profile.name)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Create Uniform Profile Error")


@frappe.whitelist(methods=["POST"])
def backfill_uniform_profiles():
    """
    Create missing Employee Uniform Profiles for all Active employees.
    Run once after install, or anytime:
    bench --site <site> execute customize_erpnext.uniform_control.api.onboarding.backfill_uniform_profiles
    """
    frappe.only_for(("System Manager", "Uniform Manager"))

    filters = {"status": "Active"}
    prefix = get_employee_id_prefix()
    if prefix:
        filters["name"] = ["like", f"{prefix}%"]

    employees = frappe.get_all(
        "Employee",
        filters=filters,
        fields=["name", "employee_name", "department", "designation", "gender"],
        order_by="name asc",
    )
    created = 0
    for emp in employees:
        if frappe.db.exists("Employee Uniform Profile", {"employee": emp.name}):
            continue
        profile = frappe.new_doc("Employee Uniform Profile")
        profile.employee = emp.name
        profile.employee_name = emp.employee_name
        profile.department = emp.department
        profile.designation = emp.designation
        profile.uniform_gender = GENDER_PROFILE_MAP.get(emp.gender or "", "")
        profile.insert(ignore_permissions=True)
        frappe.db.set_value("Employee", emp.name, "custom_uniform_profile", profile.name)
        created += 1

    return {"created": created, "active_employees": len(employees)}


@frappe.whitelist(methods=["POST"])
def seed_test_tracking():
    """TEST UTILITY (Administrator only) — seed Issuance Tracking on every
    profile to generate data for testing:
      - Bottle: issued on joining date, qty 1
      - Cap: profile.cap_item or default 'Mũ Xanh Dương Đậm - May', joining date, qty 1
      - Shoe: Dép variant from profile shoe_size (default 'Free Size' if none), joining date, qty 1
    Skips a category if a tracking row for it already exists.
    """
    if frappe.session.user != "Administrator":
        frappe.throw("Administrator only")

    from customize_erpnext.uniform_control.utils import get_variant_for_profile, build_variant_cache
    from customize_erpnext.uniform_control.doctype.employee_uniform_profile.employee_uniform_profile import _template_of

    DEFAULT_CAP = "Mũ Xanh Dương Đậm - May"
    BOTTLE = "Bình nước"
    SHOE_TMPL = "Dép"
    cache = build_variant_cache([SHOE_TMPL])
    has_bottle = bool(frappe.db.exists("Item", BOTTLE))

    profiles = frappe.get_all(
        "Employee Uniform Profile", fields=["name", "employee", "cap_item", "shoe_size"]
    )
    added = touched = 0
    for i, p in enumerate(profiles, start=1):
        joining = frappe.db.get_value("Employee", p.employee, "date_of_joining")
        if not joining:
            continue
        doc = frappe.get_doc("Employee Uniform Profile", p.name)
        existing = {_template_of(r.item_template) for r in doc.all_tracking_rows()}
        new_items = []

        if has_bottle and BOTTLE not in existing:
            new_items.append(BOTTLE)

        cap = p.cap_item or DEFAULT_CAP
        cap_tmpl = (frappe.db.get_value("Item", cap, "variant_of") or cap) if cap else None
        if cap and frappe.db.exists("Item", cap) and cap_tmpl not in existing:
            new_items.append(cap)

        if SHOE_TMPL not in existing:
            # default to 'Free Size' when the profile has no shoe size
            variant, _err = get_variant_for_profile(
                SHOE_TMPL, frappe._dict(shoe_size=p.shoe_size or "Free Size"), cache, "Shoe Size"
            )
            if variant:
                new_items.append(variant)

        if not new_items:
            continue
        for item in new_items:
            doc.append(doc.tracking_field_for(item), {
                "item_template": item,
                "last_issue_date": joining,
                "last_issue_qty": 1,
                "total_issued_qty": 1,
            })
            added += 1
        doc.save(ignore_permissions=True)
        touched += 1
        if i % 200 == 0:
            frappe.db.commit()

    frappe.db.commit()
    return {"added": added, "profiles_updated": touched, "total_profiles": len(profiles)}
