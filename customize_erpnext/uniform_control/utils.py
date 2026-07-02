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
    """Map a Uniform Rule variant_by to the profile field value,
    converted to the matching Item Attribute value."""
    if variant_source == "Shirt Size":
        v = profile.shirt_size
        return SIZE_ATTR_MAP.get(v, v)
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
    Templates use exactly 1 variant attribute; variant_source (from Uniform Rule)
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
        return None, _("Variant By is not set in Uniform Rule for {0}").format(item_template)

    value = get_profile_value_for_source(profile, variant_source)
    if not value:
        return None, _("Profile missing {0}").format(_(variant_source))

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
                "one_time", "priority"],
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
    the given employee data. `setting` is accepted for call-site compatibility
    but no longer used (rules are their own DocType)."""
    best = {}  # category -> (sortkey, rule)
    for r in load_active_rules():
        if not r.item or not r.category:
            continue
        rank = _rule_match_rank(r, emp_data or {})
        if rank is None:
            continue
        key = (rank, cint(r.priority), r.name)  # name = stable tiebreaker
        if r.category not in best or key > best[r.category][0]:
            best[r.category] = (key, r)
    return {cat: val[1] for cat, val in best.items()}


def get_default_assignments(emp_data, setting=None):
    """{'Shirt': item_template, 'Cap': item_variant} from the matching rules."""
    rules = get_rules_by_category(emp_data, setting)
    out = {}
    if "Shirt" in rules:
        out["Shirt"] = rules["Shirt"].item
    if "Cap" in rules:
        out["Cap"] = rules["Cap"].item
    return out


def _emp_data_for(employee):
    return frappe.db.get_value(
        "Employee", employee,
        ["designation", "grade", "gender", "custom_group", "custom_section", "department"],
        as_dict=True,
    ) or {}


def apply_default_rules(profile, setting=None, force=False):
    """Pre-fill profile.shirt_item / cap_item from rules.
    force=False fills only empty fields; force=True overwrites. Returns changed
    fieldnames; does not save."""
    assigns = get_default_assignments(_emp_data_for(profile.employee), setting)
    changed = []
    for target, fieldname in (("Shirt", "shirt_item"), ("Cap", "cap_item")):
        item = assigns.get(target)
        if not item:
            continue
        if (force or not profile.get(fieldname)) and profile.get(fieldname) != item:
            profile.set(fieldname, item)
            changed.append(fieldname)
    return changed


def get_rule_for_tracking(item_template, employee, setting=None):
    """Return the Uniform Rule whose category resolves to this tracking template
    for the employee, or None."""
    if setting is None:
        setting = frappe.get_single("Uniform Setting")
    profile = frappe.db.get_value(
        "Employee Uniform Profile", {"employee": employee},
        ["shirt_item", "cap_item"], as_dict=True,
    ) or frappe._dict()
    rules = get_rules_by_category(_emp_data_for(employee), setting)

    for cat, rule in rules.items():
        if cat == "Shirt":
            if item_template in (rule.item, profile.shirt_item):
                return rule
        elif cat == "Cap":
            cap_it = profile.cap_item or rule.item
            base = (frappe.db.get_value("Item", cap_it, "variant_of") or cap_it) if cap_it else None
            if base == item_template:
                return rule
        else:  # Shoe / Bottle
            if rule.item == item_template:
                return rule
    return None


def get_reissue_months(item_template, employee, setting=None):
    """Reissue cycle (months) for a tracking row's template. 0 = no reissue."""
    rule = get_rule_for_tracking(item_template, employee, setting)
    if not rule or rule.one_time:
        return 0
    return cint(rule.reissue_months)


def _load_profiles(employee_names):
    """Load profiles + tracking rows for employees in 2 queries."""
    if not employee_names:
        return {}
    profiles = frappe.get_all(
        "Employee Uniform Profile",
        filters={"employee": ["in", employee_names]},
        fields=["name", "employee", "uniform_gender", "shirt_item", "shirt_size",
                "cap_item", "shoe_size", "shoe_rack_location"],
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
            fields=["parent", "item_template", "total_issued_qty", "next_due_date"],
        )
        # item_template now holds the exact variant — resolve its template for grouping
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


def get_eligible_employees_for_allocation(
    allocation_type, uniform_type=None, department=None,
    joining_date_from=None, joining_date_to=None,
    group=None, gender=None, due_date_from=None, due_date_to=None,
    overdue_only=0,
):
    """Employees eligible for the allocation type, with suggested item + qty.
    due_date_from/to and overdue_only (Supplement only) narrow by next reissue date."""
    if allocation_type == "Replacement" and not (uniform_type or department or group or gender):
        frappe.throw(
            _("Replacement allocations are selected manually. "
              "Set a Uniform Type, Department, Group or Gender filter to narrow the employee list.")
        )

    warehouse = get_uniform_warehouse()
    setting = frappe.get_single("Uniform Setting")
    active_rules = load_active_rules()
    if not active_rules:
        return []

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
        "Employee", filters=filters,
        fields=["name", "employee_name", "department", "designation", "grade",
                "gender", "custom_group", "custom_section", "date_of_joining"],
        order_by="name asc",
    )
    if not employees:
        return []

    profiles = _load_profiles([e.name for e in employees])

    # Caches: variant resolution for shirt/shoe templates; variant_of for caps
    cache_templates = set()
    cap_items = set()
    for r in active_rules:
        if not r.item:
            continue
        if r.category in ("Shirt", "Shoe"):
            cache_templates.add(r.item)
        elif r.category == "Cap":
            cap_items.add(r.item)
    for p in profiles.values():
        if p.get("shirt_item"):
            cache_templates.add(p["shirt_item"])
        if p.get("cap_item"):
            cap_items.add(p["cap_item"])
    variant_cache = build_variant_cache(list(cache_templates))
    cap_variant_of = {}
    if cap_items:
        for it in frappe.get_all("Item", filters={"name": ["in", list(cap_items)]},
                                 fields=["name", "variant_of"]):
            cap_variant_of[it.name] = it.variant_of or it.name

    bin_qty = _load_bin_qty(warehouse)
    today_date = getdate(today())
    supplement_cutoff = add_days(today_date, cint(setting.reminder_days_before) or 30)
    results = []

    for emp in employees:
        days_working = (
            date_diff(today_date, getdate(emp.date_of_joining)) if emp.date_of_joining else 0
        )
        profile = profiles.get(emp.name)
        emp_data = {
            "department": emp.department, "designation": emp.designation,
            "grade": emp.grade, "gender": emp.gender,
            "custom_group": emp.custom_group, "custom_section": emp.custom_section,
        }

        for cat, rule in get_rules_by_category(emp_data, setting).items():
            is_exact = cat in ("Cap", "Bottle")
            if cat == "Shirt":
                chosen = (profile.shirt_item if profile else None) or rule.item
                template = chosen
                var_by = "Shirt Size"
            elif cat == "Cap":
                chosen = (profile.cap_item if profile else None) or rule.item
                template = cap_variant_of.get(chosen, chosen)
                var_by = None
            elif cat == "Shoe":
                chosen = rule.item
                template = rule.item
                var_by = "Shoe Size"
            else:  # Bottle
                chosen = rule.item
                template = rule.item
                var_by = None
            if not chosen:
                continue

            if uniform_type and uniform_type not in (template, chosen):
                continue

            # one_time = issue once: never in Supplement (no periodic reissue).
            # Who gets it is decided by the rule's conditions.
            one_time = cint(rule.one_time)
            if one_time and allocation_type == "Supplement":
                continue

            if allocation_type == "New Issue":
                if days_working < cint(rule.eligible_after_days):
                    continue
                if profile and any(
                    r.get("template") == template and cint(r.total_issued_qty) > 0
                    for r in profile["items"]
                ):
                    continue
                qty = cint(rule.first_qty)
            elif allocation_type == "Supplement":
                if one_time or not profile:
                    continue
                item_row = next(
                    (r for r in profile["items"] if r.get("template") == template), None
                )
                if not item_row or not item_row.next_due_date:
                    continue
                nd = getdate(item_row.next_due_date)
                if cint(overdue_only):
                    if nd >= today_date:  # only past-due items
                        continue
                elif due_date_from or due_date_to:
                    # explicit due-date range overrides the default reminder cutoff
                    if due_date_from and nd < getdate(due_date_from):
                        continue
                    if due_date_to and nd > getdate(due_date_to):
                        continue
                elif nd > supplement_cutoff:
                    continue
                qty = cint(rule.reissue_qty)
            else:  # Replacement
                if not profile or not any(
                    r.get("template") == template and cint(r.total_issued_qty) > 0
                    for r in profile["items"]
                ):
                    continue
                qty = 1
            if not qty:
                continue

            if not profile:
                item_code, err = None, "No uniform profile"
            elif is_exact:
                item_code, err = chosen, None
            else:
                item_code, err = get_variant_for_profile(template, profile, variant_cache, var_by)

            results.append({
                "employee": emp.name,
                "employee_name": emp.employee_name,
                "department": emp.department,
                "item_template": template,
                "item_code": item_code,
                "item_error": err,
                "qty": qty,
                "available_qty": flt(bin_qty.get(item_code, 0)) if item_code else 0,
                "shoe_rack_location": (profile.shoe_rack_location if profile else "") if cat == "Shoe" else "",
            })

    return results


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
