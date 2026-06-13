"""Shared helpers for Uniform Control module."""
import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, today, date_diff, add_days

# Employee.gender values (EN or VI) normalized for policy gender matching
GENDER_ATTR_MAP = {"Male": "Nam", "Female": "Nữ"}

# Profile shirt_size → Item Attribute "Size" values (title-cased in master data)
SIZE_ATTR_MAP = {"XL": "Xl", "2XL": "2Xl", "3XL": "3Xl", "XXL": "2Xl"}


def get_item_available_qty(item_code, warehouse):
    """Return actual_qty from Bin for item at warehouse."""
    qty = frappe.db.get_value(
        "Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"
    )
    return flt(qty)


def get_uniform_warehouse():
    return frappe.db.get_single_value("Uniform Setting", "uniform_warehouse")


def get_employee_id_prefix():
    """Only employees whose ID starts with this prefix are managed (interns etc. ignored)."""
    return (frappe.db.get_single_value("Uniform Setting", "employee_id_prefix") or "").strip()


def is_managed_employee(employee):
    prefix = get_employee_id_prefix()
    return bool(employee) and (not prefix or str(employee).startswith(prefix))


def get_shoe_rack_for_employee(employee):
    """Rack Name from Shoe Rack where the employee occupies a compartment
    (each rack holds 1–2 employees)."""
    if not employee:
        return None
    racks = frappe.get_all(
        "Shoe Rack",
        or_filters={
            "compartment_1_employee": employee,
            "compartment_2_employee": employee,
        },
        pluck="rack_display_name",
        limit=1,
    )
    return racks[0] if racks else None


def get_profile_value_for_source(profile, variant_source):
    """Map a Uniform Policy variant_source to the profile field value,
    converted to the matching Item Attribute value."""
    if variant_source == "Shirt Size":
        v = profile.shirt_size
        return SIZE_ATTR_MAP.get(v, v)
    if variant_source == "Cap Color":
        return profile.hat_color
    if variant_source == "Shoe Size":
        return profile.shoe_size
    return None


def build_variant_cache(templates):
    """
    Preload item + variant attribute data for a list of templates in 3 queries.
    Returns {template: {"has_variants": int, "attributes": [name],
                        "variants": [(variant_name, {attr: value})]}}
    """
    cache = {}
    templates = [t for t in (templates or []) if t]
    if not templates:
        return cache

    items = frappe.get_all(
        "Item",
        filters={"name": ["in", templates]},
        fields=["name", "has_variants"],
    )
    for it in items:
        cache[it.name] = {"has_variants": cint(it.has_variants), "attributes": [], "variants": []}

    if not cache:
        return cache

    template_attrs = frappe.get_all(
        "Item Variant Attribute",
        filters={"parent": ["in", list(cache.keys())]},
        fields=["parent", "attribute"],
        order_by="idx asc",
    )
    for row in template_attrs:
        if row.parent in cache:
            cache[row.parent]["attributes"].append(row.attribute)

    variant_templates = [t for t, v in cache.items() if v["has_variants"]]
    if variant_templates:
        variants = frappe.get_all(
            "Item",
            filters={"variant_of": ["in", variant_templates], "disabled": 0},
            fields=["name", "variant_of"],
            order_by="name asc",
        )
        variant_names = [v.name for v in variants]
        attrs_by_variant = {}
        if variant_names:
            for r in frappe.get_all(
                "Item Variant Attribute",
                filters={"parent": ["in", variant_names]},
                fields=["parent", "attribute", "attribute_value"],
            ):
                attrs_by_variant.setdefault(r.parent, {})[r.attribute] = r.attribute_value
        for v in variants:
            cache[v.variant_of]["variants"].append((v.name, attrs_by_variant.get(v.name, {})))

    return cache


def get_variant_for_profile(item_template, profile, variant_cache=None, variant_source=None):
    """
    Resolve the correct item variant given a template and an Employee Uniform Profile.
    Templates use exactly 1 variant attribute; variant_source (from Uniform Policy)
    says which profile field supplies its value.
    Returns (item_code, error_message).
    """
    if not item_template or not profile:
        return None, "Missing item_template or profile"

    if variant_cache is None or item_template not in variant_cache:
        variant_cache = build_variant_cache([item_template])

    entry = variant_cache.get(item_template)
    if not entry:
        return None, f"Item {item_template} not found"

    # No variants → return as-is (e.g. Water Bottle, Uniform Shirt Female)
    if not entry["has_variants"]:
        return item_template, None

    if not variant_source:
        return None, f"Variant Source is not set in Uniform Policy for {item_template}"

    value = get_profile_value_for_source(profile, variant_source)
    if not value:
        return None, f"Profile missing value for '{variant_source}'"

    attributes = entry["attributes"]
    if len(attributes) != 1:
        return None, (
            f"{item_template} has {len(attributes)} variant attributes — "
            "expected exactly 1"
        )
    attr = attributes[0]

    for variant_name, v_map in entry["variants"]:
        if v_map.get(attr) == value:
            return variant_name, None

    return None, f"No variant found for {item_template} with {attr} = {value}"


def _policy_match_rank(p, emp_data):
    """
    Specificity rank: Department+Group=5 > Department=4 > Designation=3
    > Gender=2 > All=1. 0 = does not match this employee.
    """
    if p.applies_to == "All":
        return 1
    if p.applies_to == "Gender":
        emp_gender = emp_data.get("gender") or ""
        mapped_emp = GENDER_ATTR_MAP.get(emp_gender, emp_gender)
        mapped_policy = GENDER_ATTR_MAP.get(p.gender, p.gender)
        return 2 if mapped_emp and mapped_emp == mapped_policy else 0
    if p.applies_to == "Designation":
        return 3 if p.designation and emp_data.get("designation") == p.designation else 0
    if p.applies_to == "Department":
        if not p.department or emp_data.get("department") != p.department:
            return 0
        if p.group:
            return 5 if emp_data.get("custom_group") == p.group else 0
        return 4
    return 0


def get_policy_for_template(item_template, setting, emp_data):
    """
    Return the most specific active Uniform Policy row for a template + employee data.
    setting: Uniform Setting doc; emp_data: dict with department/designation/gender/custom_group.
    """
    if not setting or not setting.policies:
        return None

    best = None
    best_rank = 0
    for p in setting.policies:
        if not p.is_active or p.item_template != item_template:
            continue
        rank = _policy_match_rank(p, emp_data or {})
        if rank > best_rank:
            best, best_rank = p, rank

    if best:
        return {
            "first_issue_qty": cint(best.first_issue_qty),
            "eligible_after_days": cint(best.eligible_after_days),
            "reissue_cycle_months": cint(best.reissue_cycle_months),
            "reissue_qty": cint(best.reissue_qty),
            "variant_source": best.variant_source,
            "one_time_issue": cint(best.one_time_issue),
            "assign_per_employee": cint(best.assign_per_employee),
        }
    return None


def get_policy_for_item(item_code, employee=None, setting=None, emp_data=None):
    """
    Return the best-matching Uniform Policy row for an item + employee combination.
    Resolves the item's template, then delegates to get_policy_for_template.
    """
    template = frappe.db.get_value("Item", item_code, "variant_of") or item_code

    if setting is None:
        setting = frappe.get_single("Uniform Setting")

    if emp_data is None:
        emp_data = {}
        if employee:
            emp_data = frappe.db.get_value(
                "Employee",
                employee,
                ["department", "designation", "gender", "custom_group"],
                as_dict=True,
            ) or {}

    return get_policy_for_template(template, setting, emp_data)


def _load_profiles(employee_names):
    """Load all Employee Uniform Profiles + items for given employees in 2 queries.
    Returns {employee: profile_dict_with_items}."""
    if not employee_names:
        return {}

    profiles = frappe.get_all(
        "Employee Uniform Profile",
        filters={"employee": ["in", employee_names]},
        fields=[
            "name", "employee", "uniform_gender", "shirt_item", "shirt_size",
            "hat_color", "shoe_size", "shoe_rack_location", "has_water_bottle",
        ],
    )
    by_name = {}
    for p in profiles:
        p["items"] = []
        by_name[p.name] = p

    if by_name:
        rows = frappe.get_all(
            "Employee Uniform Item",
            filters={
                "parent": ["in", list(by_name.keys())],
                "parenttype": "Employee Uniform Profile",
            },
            fields=["parent", "item_template", "total_issued_qty", "next_due_date"],
        )
        for r in rows:
            by_name[r.parent]["items"].append(r)

    return {p.employee: p for p in profiles}


def _load_bin_qty(warehouse):
    if not warehouse:
        return {}
    return {
        b.item_code: flt(b.actual_qty)
        for b in frappe.get_all(
            "Bin", filters={"warehouse": warehouse}, fields=["item_code", "actual_qty"]
        )
    }


def get_eligible_employees_for_allocation(
    allocation_type, uniform_type=None, department=None,
    joining_date_from=None, joining_date_to=None,
    group=None, gender=None,
):
    """
    Return list of employees eligible for given allocation_type.
    Each entry includes suggested item_code, qty, available_qty.
    """
    if allocation_type == "Replacement" and not (uniform_type or department or group or gender):
        frappe.throw(
            _("Replacement allocations are selected manually. "
              "Set a Uniform Type, Department, Group or Gender filter to narrow the employee list.")
        )

    warehouse = get_uniform_warehouse()
    setting = frappe.get_single("Uniform Setting")

    # Base filter: Active employees without relieving_date
    filters = {"status": "Active", "relieving_date": ["is", "not set"]}
    prefix = get_employee_id_prefix()
    if prefix:
        filters["name"] = ["like", f"{prefix}%"]
    if department:
        filters["department"] = department
    if group:
        filters["custom_group"] = group
    if gender:
        filters["gender"] = gender
    if joining_date_from and joining_date_to:
        filters["date_of_joining"] = ["between", [joining_date_from, joining_date_to]]
    elif joining_date_from:
        filters["date_of_joining"] = [">=", joining_date_from]
    elif joining_date_to:
        filters["date_of_joining"] = ["<=", joining_date_to]

    employees = frappe.get_all(
        "Employee",
        filters=filters,
        fields=[
            "name", "employee_name", "department", "designation", "gender",
            "custom_group", "date_of_joining",
        ],
        order_by="name asc",
    )

    # Determine which templates to check
    if uniform_type:
        templates = [uniform_type]
    else:
        templates = []
        seen = set()
        for p in setting.policies or []:
            if p.is_active and p.item_template not in seen:
                templates.append(p.item_template)
                seen.add(p.item_template)

    if not employees or not templates:
        return []

    variant_cache = build_variant_cache(templates)
    profiles = _load_profiles([e.name for e in employees])
    bin_qty = _load_bin_qty(warehouse)

    today_date = getdate(today())
    # Supplement looks ahead: include employees due within the reminder window
    # so HR can prepare before the actual due date
    supplement_cutoff = add_days(today_date, cint(setting.reminder_days_before) or 30)
    results = []

    for emp in employees:
        days_working = (
            date_diff(today_date, getdate(emp.date_of_joining)) if emp.date_of_joining else 0
        )
        profile = profiles.get(emp.name)
        emp_data = {
            "department": emp.department,
            "designation": emp.designation,
            "gender": emp.gender,
            "custom_group": emp.custom_group,
        }

        for template in templates:
            policy = get_policy_for_template(template, setting, emp_data)
            if not policy:
                continue

            # Shirt templates are assigned manually per employee in the profile
            # (any template regardless of gender)
            if policy["assign_per_employee"]:
                if not profile or (profile.shirt_item or "") != template:
                    continue

            # One-time items (water bottle): never in Supplement, and only
            # auto-suggested for employees flagged for it
            if policy["one_time_issue"]:
                if allocation_type == "Supplement":
                    continue
                if not (profile and cint(profile.has_water_bottle)):
                    continue

            # Check eligibility per allocation_type
            if allocation_type == "New Issue":
                if days_working < policy["eligible_after_days"]:
                    continue
                if profile and any(
                    r.item_template == template and cint(r.total_issued_qty) > 0
                    for r in profile["items"]
                ):
                    continue
                qty = policy["first_issue_qty"]

            elif allocation_type == "Supplement":
                if not profile:
                    continue
                item_row = next(
                    (r for r in profile["items"] if r.item_template == template), None
                )
                if not item_row or not item_row.next_due_date:
                    continue
                if getdate(item_row.next_due_date) > supplement_cutoff:
                    continue
                qty = policy["reissue_qty"]

            else:  # Replacement — only employees who already received this item
                if not profile or not any(
                    r.item_template == template and cint(r.total_issued_qty) > 0
                    for r in profile["items"]
                ):
                    continue
                qty = 1

            if not qty:
                continue

            if profile:
                item_code, err = get_variant_for_profile(
                    template, profile, variant_cache, policy["variant_source"]
                )
            else:
                item_code, err = None, "No uniform profile"

            uses_shoe_size = policy["variant_source"] == "Shoe Size"
            shoe_rack = (profile.shoe_rack_location if profile else "") or ""

            results.append({
                "employee": emp.name,
                "employee_name": emp.employee_name,
                "department": emp.department,
                "item_template": template,
                "item_code": item_code,
                "item_error": err,
                "qty": qty,
                "available_qty": flt(bin_qty.get(item_code, 0)) if item_code else 0,
                "shoe_rack_location": shoe_rack if uses_shoe_size else "",
            })

    return results
