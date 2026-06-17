"""Employee onboarding hooks — auto-create Uniform Profile + Draft Allocation."""
import frappe
from frappe.utils import cint, today, date_diff, getdate

from customize_erpnext.uniform_control.utils import (
    build_variant_cache,
    get_variant_for_profile,
    get_rules_by_category,
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


def maybe_create_onboarding_allocation(doc, method=None):
    """
    on_update on Employee — if employee is Active and eligible, create a Draft
    Uniform Allocation (New Issue) if one doesn't exist. Runs on_update (not
    validate) so the uniform profile from after_insert already exists and the
    employee row is in the DB.
    """
    if not cint(
        frappe.db.get_single_value("Uniform Setting", "auto_create_onboarding_allocation")
    ):
        return
    if not is_managed_employee(doc.name):
        return
    if doc.status != "Active" or doc.relieving_date:
        return

    # Check if a New Issue allocation already exists for this employee
    existing = frappe.db.exists(
        "Uniform Allocation Item",
        {
            "employee": doc.name,
            "issue_reason": "New Issue",
            "docstatus": ["<", 2],
        },
    )
    if existing:
        return

    setting = frappe.get_single("Uniform Setting")

    days_working = (
        date_diff(getdate(today()), getdate(doc.date_of_joining))
        if doc.date_of_joining
        else 0
    )

    profile_name = frappe.db.get_value("Employee Uniform Profile", {"employee": doc.name})
    profile = frappe.get_doc("Employee Uniform Profile", profile_name) if profile_name else None
    if not profile:
        return

    emp_data = {
        "department": doc.department,
        "designation": doc.designation,
        "gender": doc.gender,
        "custom_group": doc.get("custom_group"),
        "custom_section": doc.get("custom_section"),
    }

    rules = get_rules_by_category(emp_data, setting)
    if not rules:
        return

    cache_templates = [t for t in [profile.shirt_item] if t]
    for cat, rule in rules.items():
        if cat == "Shoe":
            cache_templates.append(rule.item)
    variant_cache = build_variant_cache(cache_templates)

    alloc_items = []
    for cat, rule in rules.items():
        if days_working < cint(rule.eligible_after_days):
            continue

        if cat == "Shirt":
            template = profile.shirt_item or rule.item
            if not template:
                continue
            item_code, err = get_variant_for_profile(template, profile, variant_cache, "Shirt Size")
        elif cat == "Cap":
            item_code = profile.cap_item or rule.item
            err = None
        elif cat == "Shoe":
            item_code, err = get_variant_for_profile(rule.item, profile, variant_cache, "Shoe Size")
        else:  # Bottle / other single item — rule conditions decide who gets it
            item_code, err = rule.item, None
        if not item_code:
            continue

        alloc_items.append({
            "employee": doc.name,
            "employee_name": doc.employee_name,
            "department": doc.department,
            "item_code": item_code,
            "qty": cint(rule.first_qty) or 1,
            "issue_reason": "New Issue",
        })

    if not alloc_items:
        return

    try:
        alloc = frappe.new_doc("Uniform Allocation")
        alloc.posting_date = today()
        alloc.allocation_type = "New Issue"
        alloc.company = doc.company or frappe.defaults.get_user_default("Company")
        alloc.set_warehouse = setting.uniform_warehouse
        for item in alloc_items:
            alloc.append("items", item)
        alloc.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Create Onboarding Allocation Error")


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
