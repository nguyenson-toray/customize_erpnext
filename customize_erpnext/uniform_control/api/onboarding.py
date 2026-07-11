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
    # Skip incomplete records: no Designation AND no custom_group yet.
    # (HR fills these in later; profile can be backfilled then.)
    if not (doc.get("designation") or doc.get("custom_group")):
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
def backfill_uniform_profiles(include_left=0):
    """
    Create missing Employee Uniform Profiles for all Active employees.
    include_left=1 also covers Left/Inactive employees — profiles then act as
    the issuance-history archive (allocation to non-Active stays blocked).
    Run once after install, or anytime:
    bench --site <site> execute customize_erpnext.uniform_control.api.onboarding.backfill_uniform_profiles
    """
    frappe.only_for(("System Manager", "Uniform Manager"))

    filters = {} if frappe.utils.cint(include_left) else {"status": "Active"}
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


def _plan_seed_rows(skip_existing=True):
    """Compute the Issuance Tracking rows the seeder would add — the single
    source of truth shared by 'Insert to DB' and 'Download Excel for import'.

    skip_existing=True  (Insert to DB): skip a category when a tracking row for
        it already exists — idempotent, never duplicates.
    skip_existing=False (Download Excel): always emit the full planned set for
        every profile (a complete snapshot to review / re-import).

    Returns a list of dicts:
      {profile, employee, table, item_template, last_issue_date,
       last_issue_qty, total_issued_qty}
    where `table` is 'shirt_items' (áo) or 'items' (cap/shoe/bottle).

      - Shirt: profile.shirt_item (assigned template). Quantity = the Shirt
        rule's First Issue Qty (áo sơ mi = 4, áo thun = 2). Last issue date:
          * áo sơ mi  → 2026-01-01 if joined before 2026-01-01, else joining
          * áo thun   → joining date (theo rule)
      - Cap / Shoe / Bottle: quantity = matching rule's First Issue Qty
        (default 1), issued on joining date.
    """
    import hashlib
    from frappe.utils import getdate, cint
    from customize_erpnext.uniform_control.utils import (
        get_variant_for_profile, build_variant_cache, get_rules_by_category,
        SIZE_ATTR_MAP,
    )

    # Item Attribute "Size" value → profile Shirt Size select value (Xl → XL)
    SIZE_PROFILE_MAP = {v: k for k, v in SIZE_ATTR_MAP.items() if k != "XXL"}

    SOMI_CUTOFF = getdate("2026-01-01")
    DEFAULT_CAP = "Mũ Xanh Dương Đậm - May"
    BOTTLE = "Bình nước"
    SHOE_TMPL = "Dép"
    has_bottle = bool(frappe.db.exists("Item", BOTTLE))
    setting = frappe.get_single("Uniform Setting")

    # Shirt rules: template -> First Issue Qty; and the set of áo sơ mi templates
    shirt_qty = {
        r.item: cint(r.first_qty) or 1
        for r in frappe.get_all(
            "Uniform Rule", filters={"category": "Shirt", "is_active": 1},
            fields=["item", "first_qty"],
        )
    }
    somi_templates = {t for t in shirt_qty if "sơ mi" in (t or "").lower()}
    cache = build_variant_cache([SHOE_TMPL] + list(shirt_qty))

    def rule_qty(rules, category):
        rule = rules.get(category)
        return (cint(rule.first_qty) or 1) if rule else 1

    # No per-employee shirt size on file → assign a size deterministically by a
    # fixed ratio (S 20% / M 45% / L 25% / Xl 10%). md5(employee) keeps it stable
    # across runs and identical between 'Insert to DB' and the Excel download.
    _size_cum = []  # (cumulative_threshold, size) over 0..99
    _acc = 0
    for _sz, _w in (("S", 20), ("M", 45), ("L", 25), ("Xl", 10)):
        _acc += _w
        _size_cum.append((_acc, _sz))

    def pick_size(employee):
        bucket = int(hashlib.md5((employee or "").encode()).hexdigest(), 16) % 100
        for thr, sz in _size_cum:
            if bucket < thr:
                return sz
        return _size_cum[-1][1]

    def shirt_variant(template, size):
        """Concrete variant for (template, size); falls back to M then any."""
        entry = cache.get(template)
        if not entry or not entry.get("has_variants") or not entry.get("attributes"):
            return template
        attr = entry["attributes"][0]
        by_size = {vmap.get(attr): vname for vname, vmap in entry["variants"]}
        return by_size.get(size) or by_size.get("M") or next(iter(by_size.values()), template)

    profiles = frappe.get_all(
        "Employee Uniform Profile",
        fields=["name", "employee", "shirt_item", "shirt_size", "cap_item", "shoe_size"],
        order_by="name asc",
    )
    emp_names = [p.employee for p in profiles if p.employee]

    # Batch employee data (joining + rule-matching fields) — avoids per-profile queries
    emp_map = {
        e.name: e
        for e in frappe.get_all(
            "Employee", filters={"name": ["in", emp_names]} if emp_names else {"name": ""},
            fields=["name", "date_of_joining", "designation", "grade", "gender",
                    "custom_group", "custom_section", "department"],
        )
    }

    # Batch existing tracking templates per profile (skip-if-exists). When
    # skip_existing is False the plan is a full snapshot, so this is skipped.
    existing_by_parent = {}
    if skip_existing:
        ex_rows = frappe.db.sql(
            """SELECT parent, item_template FROM `tabEmployee Uniform Item`
               WHERE parenttype = 'Employee Uniform Profile' AND item_template IS NOT NULL""",
            as_dict=True,
        )
        tmpl_of = {}
        distinct_items = {r.item_template for r in ex_rows}
        if distinct_items:
            for name, variant_of in frappe.db.sql(
                "SELECT name, variant_of FROM `tabItem` WHERE name IN %(n)s",
                {"n": tuple(distinct_items)},
            ):
                tmpl_of[name] = variant_of or name
        for r in ex_rows:
            existing_by_parent.setdefault(r.parent, set()).add(
                tmpl_of.get(r.item_template, r.item_template)
            )

    def template_of(item):
        return (frappe.db.get_value("Item", item, "variant_of") or item) if item else item

    plan = []
    for p in profiles:
        emp = emp_map.get(p.employee)
        if not emp or not emp.date_of_joining:
            continue
        joining = getdate(emp.date_of_joining)
        existing = existing_by_parent.get(p.name, set())
        rules = get_rules_by_category(emp, setting)
        cand = []  # (item, qty, last_issue_date, table)

        # Shirt — assigned template; áo sơ mi gets the cutoff date, áo thun runs on joining
        shirt = p.shirt_item
        shirt_tmpl = template_of(shirt)
        shirt_size = None  # profile Shirt Size select value backing the variant
        if shirt and shirt_tmpl not in existing and frappe.db.exists("Item", shirt):
            is_somi = shirt_tmpl in somi_templates
            qty = shirt_qty.get(shirt_tmpl) or rule_qty(rules, "Shirt")
            date = (SOMI_CUTOFF if joining < SOMI_CUTOFF else joining) if is_somi else joining
            # Emit a concrete sized variant. Respect the profile's Shirt Size
            # when set; otherwise assign one by the fixed ratio. If shirt_item
            # is already a specific variant, keep it as-is.
            if shirt == shirt_tmpl:
                size_attr = (SIZE_ATTR_MAP.get(p.shirt_size, p.shirt_size)
                             if p.shirt_size else pick_size(p.employee))
                variant = shirt_variant(shirt_tmpl, size_attr)
                if variant != shirt_tmpl:  # resolved a real variant → record its size
                    shirt_size = SIZE_PROFILE_MAP.get(size_attr, size_attr)
            else:
                variant = shirt
            cand.append((variant, qty, date, "shirt_items"))

        # Bottle
        if has_bottle and BOTTLE not in existing:
            cand.append((BOTTLE, rule_qty(rules, "Bottle"), joining, "items"))

        # Cap
        cap = p.cap_item or DEFAULT_CAP
        if cap and template_of(cap) not in existing and frappe.db.exists("Item", cap):
            cand.append((cap, rule_qty(rules, "Cap"), joining, "items"))

        # Shoe — default to 'Free Size' when the profile has no shoe size
        if SHOE_TMPL not in existing:
            variant, _err = get_variant_for_profile(
                SHOE_TMPL, frappe._dict(shoe_size=p.shoe_size or "Free Size"), cache, "Shoe Size"
            )
            if variant:
                cand.append((variant, rule_qty(rules, "Shoe"), joining, "items"))

        for item, qty, date, table in cand:
            plan.append({
                "profile": p.name, "employee": p.employee, "table": table,
                "item_template": item, "last_issue_date": date,
                "last_issue_qty": qty, "total_issued_qty": qty,
                # profile-level Shirt Size to fill when empty (shirt rows only)
                "shirt_size": shirt_size if table == "shirt_items" else None,
            })
    return plan


@frappe.whitelist(methods=["POST"])
def seed_test_tracking():
    """TEST UTILITY (Administrator only) — insert the planned Issuance Tracking
    rows (see _plan_seed_rows) directly into the profiles. Idempotent."""
    if frappe.session.user != "Administrator":
        frappe.throw("Administrator only")

    plan = _plan_seed_rows()
    by_profile = {}
    for row in plan:
        by_profile.setdefault(row["profile"], []).append(row)

    added = 0
    for i, (name, rows) in enumerate(by_profile.items(), start=1):
        doc = frappe.get_doc("Employee Uniform Profile", name)
        for row in rows:
            doc.append(row["table"], {
                "item_template": row["item_template"],
                "last_issue_date": row["last_issue_date"],
                "last_issue_qty": row["last_issue_qty"],
                "total_issued_qty": row["total_issued_qty"],
            })
            added += 1
            # Backfill the profile's Shirt Size from the seeded variant so the
            # forecast size-mix / current-ratio work with test data.
            if row.get("shirt_size") and not doc.shirt_size:
                doc.shirt_size = row["shirt_size"]
        doc.save(ignore_permissions=True)
        if i % 200 == 0:
            frappe.db.commit()

    frappe.db.commit()
    return {
        "added": added,
        "profiles_updated": len(by_profile),
        "total_profiles": frappe.db.count("Employee Uniform Profile"),
    }


@frappe.whitelist()
def seed_test_tracking_excel():
    """TEST UTILITY (Administrator only) — download the planned Issuance
    Tracking rows as an .xlsx laid out for Frappe Data Import into Employee
    Uniform Profile (Update Existing Records). Same data as 'Insert to DB'."""
    if frappe.session.user != "Administrator":
        frappe.throw("Administrator only")

    import openpyxl
    from io import BytesIO
    from openpyxl.styles import Font
    from frappe.utils import today

    # Full snapshot (not just the missing rows) so the download always has data.
    plan = _plan_seed_rows(skip_existing=False)
    by_profile = {}
    for row in plan:
        by_profile.setdefault(row["profile"], []).append(row)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Import"
    headers = [
        "ID", "Shirt Size",
        "Item (Shirts)", "Last Issue Date (Shirts)", "Last Issue Qty (Shirts)", "Total Issued Qty (Shirts)",
        "Item (Other Items)", "Last Issue Date (Other Items)", "Last Issue Qty (Other Items)", "Total Issued Qty (Other Items)",
    ]
    ws.append(headers)

    def _d(v):
        return str(v) if v else ""

    for name, rows in by_profile.items():
        shirts = [r for r in rows if r["table"] == "shirt_items"]
        others = [r for r in rows if r["table"] == "items"]
        size = next((r["shirt_size"] for r in shirts if r.get("shirt_size")), "")
        for k in range(max(len(shirts), len(others), 1)):
            line = [name if k == 0 else "", size if k == 0 else ""]
            s = shirts[k] if k < len(shirts) else None
            line += ([s["item_template"], _d(s["last_issue_date"]), s["last_issue_qty"], s["total_issued_qty"]]
                     if s else ["", "", "", ""])
            o = others[k] if k < len(others) else None
            line += ([o["item_template"], _d(o["last_issue_date"]), o["last_issue_qty"], o["total_issued_qty"]]
                     if o else ["", "", "", ""])
            ws.append(line)

    for cell in ws[1]:
        cell.font = Font(bold=True)

    buf = BytesIO()
    wb.save(buf)
    frappe.response["filename"] = f"seed-tracking-import-{today()}.xlsx"
    frappe.response["filecontent"] = buf.getvalue()
    frappe.response["type"] = "binary"
