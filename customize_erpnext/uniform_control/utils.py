"""Shared helpers for Uniform Control module.

Who gets what (simplified 09/11/2026):
  - Sizes and gender come from the EMPLOYEE (custom_shirt_size / custom_shoe_size /
    gender — filled through the self-update portal or by HR). The profile only
    mirrors them for display (refreshed nightly by `daily_refresh`).
  - Uniform Rules decide the item per category (Shirt / Cap / Shoe / Bottle).
    Profile.shirt_item / cap_item follow the rules unless Manual Override is
    ticked; then HR's pick wins (a blank field still follows the rule).
  - No shoe size on the Employee → the "Free Size" variant.
"""
import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, today, date_diff, add_days, add_months

# Rule "variant source" → Employee field holding the size
SIZE_FIELDS = {"Shirt Size": "custom_shirt_size", "Shoe Size": "custom_shoe_size"}
# Size variant per category; Cap / Bottle rules point at an exact item
CATEGORY_VARIANT_BY = {"Shirt": "Shirt Size", "Shoe": "Shoe Size"}
# Profile field HR can pin per category (Manual Override)
ASSIGN_FIELDS = {"Shirt": "shirt_item", "Cap": "cap_item"}
# Shoe variant used while the employee has not declared a shoe size
FREE_SIZE = "Free Size"

# Employee shirt size → Item Attribute "Size" values (title-cased in master data)
SIZE_ATTR_MAP = {"XL": "Xl", "2XL": "2Xl", "3XL": "3Xl", "XXL": "2Xl"}

# Employee fields every resolver needs (rule conditions + sizes)
EMPLOYEE_FIELDS = [
    "name", "employee_name", "department", "designation", "grade", "gender",
    "custom_group", "custom_section", "date_of_joining", "status", "relieving_date",
    "custom_shirt_size", "custom_shoe_size",
]


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


def get_reminder_days():
    return cint(frappe.db.get_single_value("Uniform Setting", "reminder_days_before")) or 30


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


def size_value(sizes, variant_source):
    """Size of the employee for a rule's variant source, as an Item Attribute value.
    `sizes` = the Employee row (custom_shirt_size / custom_shoe_size). A missing
    shoe size means the Free Size variant."""
    if variant_source == "Shirt Size":
        v = (sizes or {}).get("custom_shirt_size")
        return SIZE_ATTR_MAP.get(v, v)
    if variant_source == "Shoe Size":
        return (sizes or {}).get("custom_shoe_size") or FREE_SIZE
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


def get_variant_for_sizes(item_template, sizes, variant_cache=None, variant_source=None):
    """
    Resolve the item variant of a template for an employee's sizes.
    Templates use exactly 1 variant attribute; variant_source (Shirt Size /
    Shoe Size) says which Employee size supplies its value.
    Returns (item_code, error_message).
    """
    if not item_template:
        return None, "Missing item template"

    if variant_cache is None or item_template not in variant_cache:
        variant_cache = build_variant_cache([item_template])

    entry = variant_cache.get(item_template)
    if not entry:
        return None, f"Item {item_template} not found"

    # No variants → return as-is (e.g. a plain bottle)
    if not entry["has_variants"]:
        return item_template, None

    if not variant_source:
        return None, _("No size source for {0}").format(item_template)

    value = size_value(sizes, variant_source)
    if not value:
        return None, _("Employee has no {0}").format(_(variant_source))

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

    return None, _("No variant for {0} with size/color {1}").format(item_template, value)


# ───────────────────────────── Unified rule engine ─────────────────────────
# The standalone "Uniform Rule" DocType answers: WHO (Grade/Designation/Group/
# Section/Gender) gets WHICH item, HOW MANY, and the reissue CYCLE. One item per
# Category (Shirt/Cap/Shoe/Bottle) per employee — most specific rule wins.
# Grade & Designation are MULTI-select (a rule may list several).

def load_active_rules():
    """All active Uniform Rule records with their grades/designations resolved
    into sets. Cached per request (frappe.local) so repeated matching is cheap."""
    cached = getattr(frappe.local, "_uniform_rules_cache", None)
    if cached is not None:
        return cached

    rules = frappe.get_all(
        "Uniform Rule", filters={"is_active": 1},
        fields=["name", "category", "item", "group", "section", "gender",
                "first_qty", "eligible_after_days", "reissue_months", "reissue_qty",
                "one_time"],
    )
    gmap, dmap = {}, {}
    for g in frappe.get_all("Uniform Rule Grade", filters={"parenttype": "Uniform Rule"},
                            fields=["parent", "grade"]):
        gmap.setdefault(g.parent, set()).add(g.grade)
    for d in frappe.get_all("Uniform Rule Designation", filters={"parenttype": "Uniform Rule"},
                            fields=["parent", "designation"]):
        dmap.setdefault(d.parent, set()).add(d.designation)
    for r in rules:
        r.grades = gmap.get(r.name, set())
        r.designations = dmap.get(r.name, set())
    frappe.local._uniform_rules_cache = rules
    return rules


def clear_rules_cache():
    frappe.local._uniform_rules_cache = None


def _rule_match_rank(rule, emp_data):
    """Each set condition must match; None = no match. Specificity (most→least):
    Designation(16) > Grade(8) > Group(4) > Section(2) > Gender(1).
    Role level (Grade) outranks team (Group) and department (Section): a Leader
    gets the Leader item regardless of their group/section. Only an exact
    Designation rule overrides the grade. Grade/Designation are multi-select —
    the employee matches if their value is in the rule's list (blank = any)."""
    rank = 0
    if rule.designations:
        if emp_data.get("designation") not in rule.designations:
            return None
        rank += 16
    if rule.grades:
        if emp_data.get("grade") not in rule.grades:
            return None
        rank += 8
    if rule.group:
        if emp_data.get("custom_group") != rule.group:
            return None
        rank += 4
    if rule.section:
        if emp_data.get("custom_section") != rule.section:
            return None
        rank += 2
    if rule.gender:
        if emp_data.get("gender") != rule.gender:
            return None
        rank += 1
    return rank


def get_rules_by_category(emp_data, setting=None):
    """Return {category: rule} — the most specific active rule per category for
    the given employee data. Equal specificity → the rule with the larger name
    (stable). `setting` is accepted for call-site compatibility, unused."""
    best = {}  # category -> (sortkey, rule)
    for r in load_active_rules():
        if not r.item or not r.category:
            continue
        rank = _rule_match_rank(r, emp_data or {})
        if rank is None:
            continue
        key = (rank, r.name)
        if r.category not in best or key > best[r.category][0]:
            best[r.category] = (key, r)
    return {cat: val[1] for cat, val in best.items()}


def get_default_assignments(emp_data, setting=None):
    """{'Shirt': item_template, 'Cap': item_variant} from the matching rules."""
    rules = get_rules_by_category(emp_data, setting)
    return {cat: rules[cat].item for cat in ASSIGN_FIELDS if cat in rules}


def _emp_data_for(employee):
    return frappe.db.get_value(
        "Employee", employee,
        ["designation", "grade", "gender", "custom_group", "custom_section", "department",
         "custom_shirt_size", "custom_shoe_size"],
        as_dict=True,
    ) or {}


def chosen_item(profile, category, rule):
    """Item an employee gets for a category: HR's pick when the profile has
    Manual Override ticked and the field is filled, else the rule's item."""
    field = ASSIGN_FIELDS.get(category)
    if field and profile and cint(profile.get("manual_override")) and profile.get(field):
        return profile.get(field)
    return rule.item


def sync_assignment(profile, emp_data=None):
    """Profile WITHOUT Manual Override: shirt_item / cap_item = the rule result
    (blank when no rule matches). Returns the changed fieldnames; does not save."""
    if cint(profile.get("manual_override")) or not profile.get("employee"):
        return []
    assigns = get_default_assignments(emp_data if emp_data is not None else _emp_data_for(profile.employee))
    changed = []
    for cat, field in ASSIGN_FIELDS.items():
        target = assigns.get(cat)
        if (profile.get(field) or None) != (target or None):
            profile.set(field, target)
            changed.append(field)
    return changed


def template_of(item, cache=None):
    """Template of an item (variant_of), or the item itself."""
    if not item:
        return item
    if cache is not None and item in cache:
        return cache[item]
    t = frappe.db.get_value("Item", item, "variant_of") or item
    if cache is not None:
        cache[item] = t
    return t


def rule_for_template(item_template, rules, profile, tmpl_cache=None):
    """The rule (from `rules` = {category: rule}) whose category resolves to
    this tracking template for the employee, or None."""
    for cat, rule in rules.items():
        chosen = chosen_item(profile, cat, rule)
        if cat == "Shirt":
            if item_template in (rule.item, chosen):
                return rule
        elif cat == "Cap":
            if chosen and template_of(chosen, tmpl_cache) == item_template:
                return rule
        elif rule.item == item_template:  # Shoe / Bottle
            return rule
    return None


def get_rule_for_tracking(item_template, employee, setting=None):
    """Return the Uniform Rule whose category resolves to this tracking template
    for the employee, or None."""
    profile = frappe.db.get_value(
        "Employee Uniform Profile", {"employee": employee},
        ["shirt_item", "cap_item", "manual_override"], as_dict=True,
    ) or frappe._dict()
    rules = get_rules_by_category(_emp_data_for(employee), setting)
    return rule_for_template(item_template, rules, profile)


def get_reissue_months(item_template, employee, setting=None):
    """Reissue cycle (months) for a tracking row's template. 0 = no reissue."""
    rule = get_rule_for_tracking(item_template, employee, setting)
    if not rule or rule.one_time:
        return 0
    return cint(rule.reissue_months)


def compute_item_status(last_issue_date, next_due_date, reminder_days=30, today_date=None):
    """Not Issued / Active / Due Soon / Overdue — from the dates only."""
    if not last_issue_date:
        return "Not Issued"
    if not next_due_date:
        return "Active"
    due = getdate(next_due_date)
    td = getdate(today_date or today())
    if td > due:
        return "Overdue"
    if date_diff(due, td) <= reminder_days:
        return "Due Soon"
    return "Active"


def _load_profiles(employee_names):
    """Load profiles + tracking rows for employees in 2 queries."""
    if not employee_names:
        return {}
    profiles = frappe.get_all(
        "Employee Uniform Profile",
        filters={"employee": ["in", employee_names]},
        fields=["name", "employee", "manual_override", "shirt_item", "cap_item",
                "shoe_rack_location"],
    )
    by_name = {}
    for p in profiles:
        p["items"] = []
        by_name[p.name] = p
    if by_name:
        rows = frappe.get_all(
            "Employee Uniform Item",
            filters={"parent": ["in", list(by_name.keys())],
                     "parenttype": "Employee Uniform Profile"},
            fields=["parent", "item_template", "total_issued_qty", "last_issue_date",
                    "next_due_date"],
        )
        # item_template holds the exact variant — resolve its template for grouping
        items = {r.item_template for r in rows if r.item_template}
        tmpl_of = {}
        if items:
            for it in frappe.get_all("Item", filters={"name": ["in", list(items)]},
                                     fields=["name", "variant_of"]):
                tmpl_of[it.name] = it.variant_of or it.name
        for r in rows:
            r["template"] = tmpl_of.get(r.item_template, r.item_template)
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


def _managed_active_employees(fields=None, **filters):
    flt_ = {"status": "Active", **filters}
    prefix = get_employee_id_prefix()
    if prefix:
        flt_["name"] = ["like", f"{prefix}%"]
    return frappe.get_all("Employee", filters=flt_, fields=fields or ["name"], order_by="name asc")


def ensure_profiles(employees=None):
    """Create the missing Employee Uniform Profiles — for the given employee
    IDs, or every managed Active employee. A profile is created the first time
    it is needed (Get Employees, dashboard, nightly job), so the Employee insert
    hook stays off. Returns the number created."""
    if employees is None:
        employees = [e.name for e in _managed_active_employees()]
    employees = [e for e in (employees or []) if is_managed_employee(e)]
    if not employees:
        return 0
    existing = set(frappe.get_all(
        "Employee Uniform Profile", filters={"employee": ["in", employees]}, pluck="employee"
    ))
    missing = [e for e in employees if e not in existing]
    if not missing:
        return 0
    emp_rows = {
        e.name: e for e in frappe.get_all(
            "Employee", filters={"name": ["in", missing]}, fields=EMPLOYEE_FIELDS
        )
    }
    created, conflicts = 0, []
    for emp in missing:
        e = emp_rows.get(emp)
        if not e:
            continue
        # A profile is named after its employee. An Employee renamed later leaves
        # its profile under the old ID, which may now be another employee's ID.
        owner = frappe.db.get_value("Employee Uniform Profile", emp, "employee")
        if owner and owner != emp:
            conflicts.append(f"{emp} (profile {emp} belongs to {owner})")
            continue
        doc = frappe.get_doc({
            "doctype": "Employee Uniform Profile",
            "employee": emp,
            "employee_name": e.employee_name,
            "department": e.department,
            "designation": e.designation,
            "group": e.custom_group,
            "employment_status": e.status,
            "relieving_date": e.relieving_date,
            "uniform_gender": e.gender,
            "shirt_size": e.custom_shirt_size,
            "shoe_size": e.custom_shoe_size,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.set_value("Employee", emp, "custom_uniform_profile", doc.name, update_modified=False)
        created += 1
    if conflicts:
        frappe.log_error(
            title="Uniform Profile name conflict",
            message="Profile not created — rename the old profile to its employee's ID "
                    "(Employee Uniform Profile ⋯ Rename):\n" + "\n".join(conflicts),
        )
    return created


def resolve_assignment(emp, profile, rules=None, variant_cache=None, tmpl_cache=None):
    """What an employee gets, per category:
      {category: {rule, rule_item, chosen, manual, template, variant, error,
                  first_qty, eligible_after_days, reissue_months, reissue_qty, one_time}}
    `emp` = Employee row (rule conditions + sizes); `profile` = profile row/doc
    (manual_override, shirt_item, cap_item) or None."""
    rules = rules if rules is not None else get_rules_by_category(emp)
    if variant_cache is None:
        variant_cache = build_variant_cache([
            chosen_item(profile, cat, r) for cat, r in rules.items() if cat in CATEGORY_VARIANT_BY
        ])
    out = {}
    for cat, rule in rules.items():
        chosen = chosen_item(profile, cat, rule)
        err = None
        if cat == "Cap":
            template, variant = template_of(chosen, tmpl_cache), chosen
        elif cat in CATEGORY_VARIANT_BY:
            template = chosen
            variant, err = get_variant_for_sizes(template, emp, variant_cache, CATEGORY_VARIANT_BY[cat])
        else:  # Bottle and any other exact item
            template = variant = chosen
        out[cat] = frappe._dict({
            "rule": rule.name, "rule_item": rule.item, "chosen": chosen,
            "manual": chosen != rule.item, "template": template, "variant": variant,
            "error": err, "first_qty": cint(rule.first_qty),
            "eligible_after_days": cint(rule.eligible_after_days),
            "reissue_months": cint(rule.reissue_months), "reissue_qty": cint(rule.reissue_qty),
            "one_time": cint(rule.one_time),
        })
    return out


def get_due_rows(uniform_type=None, department=None, group=None, due_before=None,
                 issue_filter=None):
    """Rows for one Uniform Allocation — every managed Active employee's item
    that is due, each with its reason:
      - "New Issue": never issued this uniform type and past Eligible After (Days);
      - "Periodic Supplement": issued before, not one-time, next due on/before
        `due_before` (default: today + Reminder Days Before).
    issue_filter = "New Issue" / "Periodic Supplement" keeps only that reason.
    Missing profiles are created on the way."""
    if not load_active_rules():
        return []

    filters = {"relieving_date": ["is", "not set"]}
    if department:
        filters["department"] = department
    if group:
        filters["custom_group"] = group
    employees = _managed_active_employees(EMPLOYEE_FIELDS, **filters)
    if not employees:
        return []

    ensure_profiles([e.name for e in employees])
    profiles = _load_profiles([e.name for e in employees])
    warehouse = get_uniform_warehouse()
    bin_qty = _load_bin_qty(warehouse)

    rules_of = {e.name: get_rules_by_category(e) for e in employees}
    templates = set()
    for e in employees:
        for cat, rule in rules_of[e.name].items():
            if cat in CATEGORY_VARIANT_BY:
                templates.add(chosen_item(profiles.get(e.name), cat, rule))
    variant_cache = build_variant_cache(list(templates))
    tmpl_cache = {}

    today_date = getdate(today())
    cutoff = getdate(due_before) if due_before else add_days(today_date, get_reminder_days())
    issue_filter = issue_filter if issue_filter in ("New Issue", "Periodic Supplement") else None
    results = []

    for emp in employees:
        profile = profiles.get(emp.name)
        days_working = date_diff(today_date, getdate(emp.date_of_joining)) if emp.date_of_joining else 0
        assignment = resolve_assignment(emp, profile, rules_of[emp.name], variant_cache, tmpl_cache)
        for cat, a in assignment.items():
            template = a.template
            if not a.chosen or (uniform_type and uniform_type not in (template, a.chosen)):
                continue
            issued = next(
                (r for r in (profile["items"] if profile else [])
                 if r.get("template") == template and cint(r.total_issued_qty) > 0),
                None,
            )
            if not issued:
                if issue_filter == "Periodic Supplement" or days_working < a.eligible_after_days:
                    continue
                reason, qty, next_due = "New Issue", a.first_qty, None
            else:
                if issue_filter == "New Issue" or a.one_time or not issued.next_due_date:
                    continue
                next_due = getdate(issued.next_due_date)
                if next_due > cutoff:
                    continue
                reason, qty = "Periodic Supplement", a.reissue_qty
            if not qty:
                continue

            results.append({
                "employee": emp.name,
                "employee_name": emp.employee_name,
                "department": emp.department,
                "item_template": template,
                "item_code": a.variant,
                "item_error": a.error,
                "qty": qty,
                "issue_reason": reason,
                "next_due_date": str(next_due) if next_due else None,
                "available_qty": flt(bin_qty.get(a.variant, 0)) if a.variant else 0,
                "shoe_rack_location": (profile.shoe_rack_location if profile else "") if cat == "Shoe" else "",
            })

    return results


def refresh_tracking():
    """Bring every managed profile in line with the rules — direct UPDATEs of
    the values that change only (no profile save → no Version per profile):
      1. shirt_item / cap_item of profiles WITHOUT Manual Override = rule result;
      2. next_due_date (cycle of the matching rule) + status of every tracking row.
    Covers left employees too ("Est. for Leavers" reads their next_due_date).
    Runs after a Uniform Rule changes and nightly. Returns counts."""
    clear_rules_cache()
    prefix = get_employee_id_prefix()
    reminder = get_reminder_days()
    today_date = getdate(today())
    like = f"{prefix}%" if prefix else "%"

    profiles = frappe.db.sql(
        """
        SELECT p.name, p.employee, p.manual_override, p.shirt_item, p.cap_item,
               e.designation, e.grade, e.gender, e.custom_group, e.custom_section
        FROM `tabEmployee Uniform Profile` p
        JOIN `tabEmployee` e ON e.name = p.employee
        WHERE p.employee LIKE %(like)s
        """,
        {"like": like}, as_dict=True,
    )
    by_name, rules_of, assigned = {}, {}, 0
    for p in profiles:
        rules = get_rules_by_category(p)
        rules_of[p.name] = rules
        by_name[p.name] = p
        if not cint(p.manual_override):
            new = {"shirt_item": rules["Shirt"].item if "Shirt" in rules else None,
                   "cap_item": rules["Cap"].item if "Cap" in rules else None}
            if any((p.get(f) or None) != (v or None) for f, v in new.items()):
                frappe.db.set_value("Employee Uniform Profile", p.name, new, update_modified=False)
                p.update(new)
                assigned += 1

    rows = frappe.db.sql(
        """
        SELECT eui.name, eui.parent, eui.item_template, eui.last_issue_date,
               eui.next_due_date, eui.status
        FROM `tabEmployee Uniform Item` eui
        JOIN `tabEmployee Uniform Profile` p ON p.name = eui.parent
        WHERE eui.parenttype = 'Employee Uniform Profile' AND p.employee LIKE %(like)s
        """,
        {"like": like}, as_dict=True,
    )
    tmpl_cache = {}
    items = list({r.item_template for r in rows if r.item_template}
                 | {p.cap_item for p in profiles if p.cap_item})
    for i in range(0, len(items), 500):
        for it in frappe.get_all("Item", filters={"name": ["in", items[i:i + 500]]},
                                 fields=["name", "variant_of"]):
            tmpl_cache[it.name] = it.variant_of or it.name

    updated = 0
    for r in rows:
        p = by_name.get(r.parent)
        if not p:
            continue
        rule = rule_for_template(template_of(r.item_template, tmpl_cache), rules_of[r.parent], p, tmpl_cache)
        cycle = 0 if (not rule or cint(rule.one_time)) else cint(rule.reissue_months)
        next_due = add_months(r.last_issue_date, cycle) if (r.last_issue_date and cycle) else None
        status = compute_item_status(r.last_issue_date, next_due, reminder, today_date)
        old_due = getdate(r.next_due_date) if r.next_due_date else None
        new_due = getdate(next_due) if next_due else None
        if old_due != new_due or r.status != status:
            frappe.db.set_value("Employee Uniform Item", r.name,
                                {"next_due_date": new_due, "status": status},
                                update_modified=False)
            updated += 1
    return {"profiles": len(profiles), "assignments_synced": assigned,
            "rows": len(rows), "rows_updated": updated}


def sync_profile_copies():
    """Profile fields copied from the Employee (name, department, designation,
    group, status, relieving date, gender, sizes) + shoe rack location —
    two UPDATEs, only rows that differ."""
    frappe.db.sql(
        """
        UPDATE `tabEmployee Uniform Profile` p
        JOIN `tabEmployee` e ON e.name = p.employee
        SET p.employee_name = e.employee_name, p.department = e.department,
            p.designation = e.designation, p.`group` = e.custom_group,
            p.employment_status = e.status, p.relieving_date = e.relieving_date,
            p.uniform_gender = e.gender, p.shirt_size = e.custom_shirt_size,
            p.shoe_size = e.custom_shoe_size
        WHERE NOT (p.employee_name <=> e.employee_name AND p.department <=> e.department
               AND p.designation <=> e.designation AND p.`group` <=> e.custom_group
               AND p.employment_status <=> e.status AND p.relieving_date <=> e.relieving_date
               AND p.uniform_gender <=> e.gender AND p.shirt_size <=> e.custom_shirt_size
               AND p.shoe_size <=> e.custom_shoe_size)
        """
    )
    frappe.db.sql(
        """
        UPDATE `tabEmployee Uniform Profile` p
        LEFT JOIN (
            SELECT emp, MIN(rack) AS rack FROM (
                SELECT compartment_1_employee AS emp, rack_display_name AS rack
                FROM `tabShoe Rack` WHERE IFNULL(compartment_1_employee, '') != ''
                UNION ALL
                SELECT compartment_2_employee, rack_display_name
                FROM `tabShoe Rack` WHERE IFNULL(compartment_2_employee, '') != ''
            ) x GROUP BY emp
        ) r ON r.emp = p.employee
        SET p.shoe_rack_location = r.rack
        WHERE NOT (p.shoe_rack_location <=> r.rack)
        """
    )
    # Employee → profile link (Employee form, "Uniform" section)
    frappe.db.sql(
        """
        UPDATE `tabEmployee` e
        JOIN `tabEmployee Uniform Profile` p ON p.employee = e.name
        SET e.custom_uniform_profile = p.name
        WHERE NOT (e.custom_uniform_profile <=> p.name)
        """
    )


def daily_refresh():
    """Nightly: create missing profiles, refresh the copied Employee fields,
    then re-sync rule assignments + due dates/status."""
    created = ensure_profiles()
    sync_profile_copies()
    res = refresh_tracking()
    res["profiles_created"] = created
    return res


def get_attrition_rate(months=3):
    """Average monthly attrition of managed employees over the last `months`
    FULL calendar months (the running month is excluded).

    Per month: relieved = employees whose relieving_date falls in the month;
    headcount = employees on payroll at the month's first day (joined before
    it and not yet relieved). Returns
      {"rate": avg_monthly_rate, "months": n,
       "per_month": [{"month": "YYYY-MM", "relieved", "headcount", "rate"}]}.
    """
    from frappe.utils import add_months

    months = max(1, min(cint(months) or 3, 12))
    prefix = get_employee_id_prefix()
    like = f"{prefix}%" if prefix else "%"
    first_of_current = getdate(today()).replace(day=1)

    per_month, rates = [], []
    for i in range(months, 0, -1):
        start = add_months(first_of_current, -i)
        end = add_months(first_of_current, -i + 1)
        relieved = frappe.db.sql(
            """SELECT COUNT(*) FROM `tabEmployee`
               WHERE name LIKE %s AND relieving_date >= %s AND relieving_date < %s""",
            (like, start, end),
        )[0][0]
        headcount = frappe.db.sql(
            """SELECT COUNT(*) FROM `tabEmployee`
               WHERE name LIKE %s AND date_of_joining < %s
                 AND (relieving_date IS NULL OR relieving_date >= %s)""",
            (like, start, start),
        )[0][0]
        rate = (relieved / headcount) if headcount else 0.0
        per_month.append({
            "month": str(start)[:7], "relieved": relieved,
            "headcount": headcount, "rate": rate,
        })
        rates.append(rate)

    return {
        "rate": (sum(rates) / len(rates)) if rates else 0.0,
        "months": months,
        "per_month": per_month,
    }


def _months_until(from_date, to_date):
    """Whole calendar months from from_date to to_date, floored at 0."""
    return max(0, (to_date.year - from_date.year) * 12 + (to_date.month - from_date.month))


def leaver_missed_demand(months=None):
    """MEASURED missed re-issue demand — the basis of "Est. for Leavers".

    Looks at the last N full months (Uniform Setting's Attrition Window when
    `months` is None): tracking rows of RELIEVED employees whose next_due_date
    fell inside that window AFTER they had left — i.e. re-issues that would
    have been handed out had those people not quit. No probability model:
    the people and quantities are real and listable.

    Returns {"months": N, "window": {"from", "to"}, "persons": n,
             "qty": {variant: missed_qty}, "monthly": {variant: qty/N},
             "total_qty": Σ}.
    """
    from frappe.utils import add_months

    if months is None:
        months = frappe.db.get_single_value("Uniform Setting", "attrition_months")
    months = max(1, min(cint(months) or 3, 12))
    prefix = get_employee_id_prefix()
    like = f"{prefix}%" if prefix else "%"
    first_of_current = getdate(today()).replace(day=1)
    window_start = add_months(first_of_current, -months)

    rows = frappe.db.sql(
        """
        SELECT p.employee, e.relieving_date, eui.item_template,
               COALESCE(NULLIF(i.variant_of, ''), i.name) AS tmpl,
               COALESCE(iva.attribute_value, '') AS size
        FROM `tabEmployee Uniform Item` eui
        INNER JOIN `tabEmployee Uniform Profile` p ON p.name = eui.parent
        INNER JOIN `tabEmployee` e ON e.name = p.employee
        INNER JOIN `tabItem` i ON i.name = eui.item_template
        LEFT JOIN `tabItem Variant Attribute` iva
               ON iva.parent = eui.item_template AND iva.attribute = 'Size'
        WHERE e.name LIKE %(like)s AND e.relieving_date IS NOT NULL
          AND eui.next_due_date >= %(ws)s AND eui.next_due_date < %(we)s
          AND e.relieving_date < eui.next_due_date
        """,
        {"like": like, "ws": window_start, "we": first_of_current}, as_dict=True,
    )

    persons, qty, rule_cache = set(), {}, {}
    detail = {}  # (template, size) -> {"persons": set, "qty": n, "variant": name}
    for r in rows:
        key = (r.employee, r.tmpl)
        if key not in rule_cache:
            rule = get_rule_for_tracking(r.tmpl, r.employee)
            rule_cache[key] = cint(rule.reissue_qty) if rule and not rule.one_time else 0
        q = rule_cache[key]
        if q <= 0:
            continue
        persons.add(r.employee)
        qty[r.item_template] = qty.get(r.item_template, 0) + q
        d = detail.setdefault((r.tmpl, r.size), {"persons": set(), "qty": 0})
        d["persons"].add(r.employee)
        d["qty"] += q

    return {
        "months": months,
        "window": {"from": str(window_start), "to": str(add_days(first_of_current, -1))},
        "persons": len(persons),
        "qty": qty,
        "monthly": {v: q / months for v, q in qty.items()},
        "total_qty": sum(qty.values()),
        # per template × size — for the "missed re-issues" analysis table
        "rows": [
            {"template": t, "size": s, "persons": len(d["persons"]), "qty": d["qty"]}
            for (t, s), d in sorted(detail.items())
        ],
    }


def reissue_demand(to_date, setting=None, prefix=None):
    """Reissue demand for current managed Active employees up to `to_date`,
    counting EVERY reissue cycle in [next_due, to_date] (not just the next one).

    Shared by the dashboard (Employees Due / stock "needed") and the Forecast
    re-issue mode. Returns:
      {"rows":   [per employee-item: + size, reissue_months, cycles,
                  qty_per_cycle, total_qty],
       "needed": {variant: Σ total_qty},
       "meta":   {variant: {"template":.., "category":.., "size":..}}}

    """
    from frappe.utils import add_months

    if setting is None:
        setting = frappe.get_single("Uniform Setting")
    if prefix is None:
        prefix = get_employee_id_prefix()
    to_date = getdate(to_date)
    prefix_cond = "AND p.employee LIKE %(prefix)s" if prefix else ""

    rows = frappe.db.sql(
        f"""
        SELECT p.employee, p.employee_name, p.department, e.custom_section, e.custom_group,
               eui.item_template, eui.last_issue_date, eui.next_due_date, eui.status
        FROM `tabEmployee Uniform Item` eui
        INNER JOIN `tabEmployee Uniform Profile` p ON p.name = eui.parent
        INNER JOIN `tabEmployee` e ON e.name = p.employee
        WHERE eui.next_due_date IS NOT NULL AND eui.next_due_date <= %(to_date)s
          AND e.status = 'Active' {prefix_cond}
        ORDER BY eui.next_due_date ASC
        """,
        {"to_date": to_date, "prefix": f"{prefix}%"}, as_dict=True,
    )

    # Variant size/colour attribute for display
    variants = {r.item_template for r in rows if r.item_template}
    attr_val = {}
    if variants:
        for a in frappe.get_all(
            "Item Variant Attribute",
            filters={"parent": ["in", list(variants)]},
            fields=["parent", "attribute_value"],
        ):
            attr_val.setdefault(a.parent, a.attribute_value)

    template_of, rule_cache, needed, meta = {}, {}, {}, {}
    for r in rows:
        variant = r.item_template
        r["size"] = attr_val.get(variant, "")
        if variant not in template_of:
            template_of[variant] = frappe.db.get_value("Item", variant, "variant_of") or variant
        template = template_of[variant]

        key = (r.employee, template)
        if key not in rule_cache:
            rule_cache[key] = get_rule_for_tracking(template, r.employee, setting)
        rule = rule_cache[key]
        qpc = cint(rule.reissue_qty) if rule else 0
        months = 0 if (not rule or rule.one_time) else cint(rule.reissue_months)

        # Count reissue occurrences within [next_due, to_date]
        cycles = 1
        if months > 0:
            nd = getdate(r.next_due_date)
            cycles = 0
            while add_months(nd, cycles * months) <= to_date:
                cycles += 1
        total = cycles * qpc

        r["reissue_months"] = months
        r["qty_per_cycle"] = qpc
        r["cycles"] = cycles
        r["total_qty"] = total
        # Rows with no matching rule / reissue_qty 0 stay visible in the due
        # list (data to review) but must not pollute the stock plan with zeros.
        if total > 0:
            needed[variant] = needed.get(variant, 0) + total
        if variant not in meta:
            meta[variant] = {
                "template": template,
                "category": (rule.category if rule else None),
                "size": r["size"],
            }

    return {"rows": rows, "needed": needed, "meta": meta}
