"""Uniform demand forecast for planned new hires, driven by an HRMS Staffing Plan.

Headcount per designation comes from the Staffing Plan (vacancies / positions).
Staffing Plan has no gender/size, while Uniform Rules + variants do — so gender
split and size mix are inferred from CURRENT employees in the same designation
(fallback: by gender only, then company-wide). Output = demand per item variant
vs current stock. HR can then edit forecast_qty manually."""
import re

import frappe
from frappe import _
from frappe.utils import cint, getdate, today, add_days

from customize_erpnext.uniform_control.utils import (
    get_rules_by_category,
    build_variant_cache,
    get_variant_for_profile,
    get_item_available_qty,
    get_employee_id_prefix,
)

# Uniform Rule category -> (variant_source for get_variant_for_profile, profile size field)
CATEGORY_SIZE = {"Shirt": ("Shirt Size", "shirt_size"), "Shoe": ("Shoe Size", "shoe_size")}


@frappe.whitelist()
def compute(forecast):
    """Fill the forecast's items. Mode decides the source:
      - New Hires: the recruitment plan lines (designation + headcount);
      - Re-issue: upcoming reissue demand up to To Date (multi-cycle);
      - Both: the sum.
    Returns a summary (+ unmapped designations for New Hires)."""
    if not frappe.has_permission("Uniform Demand Forecast", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    doc = frappe.get_doc("Uniform Demand Forecast", forecast)
    setting = frappe.get_single("Uniform Setting")
    warehouse = doc.warehouse or setting.uniform_warehouse
    prefix = get_employee_id_prefix()
    mode = doc.mode or "New Hires"

    demand = {}  # variant -> {"qty":float,"template":..,"size":..,"category":..}
    unmapped = []  # (designation, headcount) with no segment data to infer from

    # ── New-hire demand from the recruitment plan lines ──
    if mode in ("New Hires", "Both"):
        if not doc.lines:
            frappe.throw(_("Add at least one designation in the Recruitment Plan."))
        seg_cache, size_cache = {}, {}
        for d in doc.lines:
            if not d.designation:
                continue
            headcount = cint(d.headcount)
            if headcount <= 0:
                continue
            # Spread headcount across the (grade, gender, group, section) segments
            # of current employees of this designation so grade-based shirt rules
            # and group/section caps resolve correctly.
            segs = _segments(d.designation, prefix, seg_cache)
            if not segs:
                unmapped.append((d.designation, headcount))
                continue
            for seg, frac in segs:
                count = headcount * frac
                if count <= 0:
                    continue
                rules = get_rules_by_category(seg, setting)
                cache = build_variant_cache([r.item for r in rules.values() if r.item])
                for cat, rule in rules.items():
                    cat_qty = count * (cint(rule.first_qty) or 1)
                    _spread(demand, cat, rule, cat_qty, d.designation, seg.get("gender"), prefix, cache, size_cache)

    # ── Re-issue demand up to To Date (multi-cycle) ──
    if mode in ("Re-issue", "Both"):
        from customize_erpnext.uniform_control.utils import reissue_demand
        to_date = doc.to_date or add_days(today(), 365)
        rd = reissue_demand(to_date, setting, prefix)
        for variant, qty in rd["needed"].items():
            if qty <= 0:
                continue
            m = rd["meta"].get(variant, {})
            _add(demand, variant, m.get("template") or variant, m.get("size") or "",
                 m.get("category") or "", qty)

    doc.set("items", [])
    for variant, info in sorted(demand.items()):
        qty = int(round(info["qty"]))
        if qty <= 0:
            continue
        stock = int(get_item_available_qty(variant, warehouse)) if warehouse else 0
        doc.append("items", {
            "item_code": variant,
            "template": info["template"],
            "size": info["size"],
            "category": info["category"],
            "forecast_qty": qty,
            "current_stock": stock,
        })
    doc.save(ignore_permissions=True)  # validate() recomputes totals
    return {
        "items": len(doc.items),
        "total_forecast": doc.total_forecast_qty,
        "total_shortfall": doc.total_shortfall,
        # designations with no current staff to infer from → HR adds manually
        "unmapped": [{"designation": d, "headcount": h} for d, h in unmapped],
    }


@frappe.whitelist()
def current_shirt_ratio(forecast):
    """Current employees' shirt distribution = the reference ratio used to spread
    the forecast. Always covers BOTH shirt types (Áo sơ mi & Áo thun) by scanning
    all managed employees company-wide, as of the forecast's creation date.
    Grouped by shirt template (type + gender) and size.
    Returns {"as_of": date, "rows": [{template, size, qty}]}."""
    doc = frappe.get_doc("Uniform Demand Forecast", forecast)
    setting = frappe.get_single("Uniform Setting")
    prefix = get_employee_id_prefix()
    as_of = getdate(doc.creation) if doc.creation else getdate(today())

    pcond = " AND e.name LIKE %(prefix)s" if prefix else ""
    rows = frappe.db.sql(
        f"""
        SELECT e.grade AS grade, p.uniform_gender AS gender,
               e.custom_group AS custom_group, e.custom_section AS custom_section,
               p.shirt_size AS size, COUNT(*) c
        FROM `tabEmployee` e
        JOIN `tabEmployee Uniform Profile` p ON p.employee = e.name
        WHERE e.date_of_joining <= %(as_of)s
              AND (e.relieving_date IS NULL OR e.relieving_date > %(as_of)s)
              AND p.shirt_size IS NOT NULL AND p.shirt_size != '' {pcond}
        GROUP BY e.grade, p.uniform_gender, e.custom_group, e.custom_section, p.shirt_size
        """,
        {"as_of": as_of, "prefix": f"{prefix}%"}, as_dict=True,
    )

    out, rule_cache = {}, {}
    for r in rows:
        key = (r.grade, r.gender, r.custom_group, r.custom_section)
        if key not in rule_cache:
            seg = {"designation": None, "grade": r.grade, "gender": r.gender,
                   "custom_group": r.custom_group, "custom_section": r.custom_section}
            shirt = get_rules_by_category(seg, setting).get("Shirt")
            rule_cache[key] = shirt.item if shirt else None
        template = rule_cache[key]
        if not template:
            continue
        out[(template, r.size)] = out.get((template, r.size), 0) + r.c

    return {
        "as_of": str(as_of),
        "rows": [{"template": t, "size": s, "qty": q} for (t, s), q in out.items()],
    }


@frappe.whitelist()
def export_forecast_excel(forecast):
    """Download the forecast as .xlsx — sheet 1: Forecast items, sheet 2: the
    current shirt ratio used as the calculation basis."""
    if not frappe.has_permission("Uniform Demand Forecast", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    import openpyxl
    from io import BytesIO
    from openpyxl.styles import Font

    doc = frappe.get_doc("Uniform Demand Forecast", forecast)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    bold = Font(bold=True)

    ws = wb.create_sheet("Forecast")
    ws.append(["Item", "Uniform Type", "Size", "Category", "Forecast Qty", "Current Stock"])
    for r in doc.items:
        ws.append([r.item_code, r.template, r.size, r.category, r.forecast_qty, r.current_stock])

    ws2 = wb.create_sheet("Current Ratio")
    ws2.append(["Type", "Gender", "Size", "Employees"])
    for row in current_shirt_ratio(forecast).get("rows", []):
        t = (row["template"] or "").lower()
        typ = "Áo sơ mi" if "sơ mi" in t else ("Áo thun" if "thun" in t else row["template"])
        gender = "Nữ" if "nữ" in t else ("Nam" if "nam" in t else "")
        ws2.append([typ, gender, row["size"], row["qty"]])

    for w in (ws, ws2):
        for cell in w[1]:
            cell.font = bold

    buf = BytesIO()
    wb.save(buf)
    frappe.response["filename"] = f"{forecast}-{today()}.xlsx"
    frappe.response["filecontent"] = buf.getvalue()
    frappe.response["type"] = "binary"


# ─────────────────────────────── helpers ───────────────────────────────────

def _add(demand, variant, template, size, category, qty):
    e = demand.setdefault(
        variant, {"qty": 0.0, "template": template, "size": size, "category": category}
    )
    e["qty"] += qty


def _spread(demand, cat, rule, cat_qty, designation, gender, prefix, cache, size_cache):
    """Spread a category's quantity across item variants by the size mix."""
    template = rule.item
    entry = cache.get(template) or {}
    sized = CATEGORY_SIZE.get(cat)

    # Non-sized item (a Cap variant / Bottle) or a template without variants → as-is
    if not (sized and entry.get("has_variants")):
        base = frappe.db.get_value("Item", template, "variant_of") or template
        _add(demand, template, base, _suffix(template, base), cat, cat_qty)
        return

    source, field = sized
    mix = _size_mix(designation, gender, field, prefix, size_cache)
    if not mix:
        # No size data → single default variant (e.g. shoes 'Free Size')
        default = "Free Size" if field == "shoe_size" else None
        variant = None
        if default:
            variant, _err = get_variant_for_profile(
                template, frappe._dict({field: default}), cache, source
            )
        if variant:
            _add(demand, variant, template, default, cat, cat_qty)
        else:
            _add(demand, template, template, "", cat, cat_qty)  # template-level fallback
        return

    for sizeval, frac in mix.items():
        variant, _err = get_variant_for_profile(
            template, frappe._dict({field: sizeval}), cache, source
        )
        if variant:
            _add(demand, variant, template, sizeval, cat, cat_qty * frac)


def _suffix(item_code, base):
    """Variant label = item name with the template name stripped off."""
    name = frappe.db.get_value("Item", item_code, "item_name") or item_code
    bname = frappe.db.get_value("Item", base, "item_name") or base
    return name[len(bname):].strip() if name.startswith(bname) else ""


def _ratio_sql(field, where, params):
    rows = frappe.db.sql(
        f"""
        SELECT p.{field} AS k, COUNT(*) c
        FROM `tabEmployee Uniform Profile` p
        JOIN `tabEmployee` e ON e.name = p.employee
        WHERE p.{field} IS NOT NULL AND p.{field} != '' {where}
        GROUP BY p.{field}
        """,
        params, as_dict=True,
    )
    total = sum(r.c for r in rows)
    return {r.k: r.c / total for r in rows} if total else {}


def _segments(designation, prefix, cache):
    """Distribution of (grade, gender, group, section) among current employees of
    this designation → list of (emp_data, fraction). Drives rule matching so a
    planned hire's likely grade/group/section/gender mix is reflected.

    If the designation has no current staff (e.g. a brand-new "... -Trainee"),
    fall back to the base designation before the first dash ("Sewing Worker-
    Trainee" → "Sewing Worker") so trainees inherit that role's uniform."""
    if designation in cache:
        return cache[designation]
    segs = _segments_query(designation, prefix)
    if not segs:
        base = re.split(r"[-–—]", designation, maxsplit=1)[0].strip()
        if base and base != designation:
            segs = _segments_query(base, prefix)  # emp_data carries designation=base
    cache[designation] = segs
    return segs


def _segments_query(designation, prefix):
    pcond = " AND e.name LIKE %(prefix)s" if prefix else ""
    rows = frappe.db.sql(
        f"""
        SELECT e.grade AS grade, p.uniform_gender AS gender,
               e.custom_group AS custom_group, e.custom_section AS custom_section,
               COUNT(*) c
        FROM `tabEmployee` e
        JOIN `tabEmployee Uniform Profile` p ON p.employee = e.name
        WHERE e.status = 'Active' AND e.designation = %(designation)s {pcond}
        GROUP BY e.grade, p.uniform_gender, e.custom_group, e.custom_section
        """,
        {"designation": designation, "prefix": f"{prefix}%"}, as_dict=True,
    )
    total = sum(r.c for r in rows)
    return [
        ({"designation": designation, "grade": r.grade, "gender": r.gender,
          "custom_group": r.custom_group, "custom_section": r.custom_section}, r.c / total)
        for r in rows
    ] if total else []


def _size_mix(designation, gender, field, prefix, cache):
    key = (designation, gender, field)
    if key in cache:
        return cache[key]
    pcond = " AND e.name LIKE %(prefix)s" if prefix else ""
    base = {"prefix": f"{prefix}%"}
    r = _ratio_sql(
        field,
        "AND e.designation = %(designation)s AND p.uniform_gender = %(gender)s" + pcond,
        {**base, "designation": designation, "gender": gender},
    )
    if not r:  # by gender only
        r = _ratio_sql(field, "AND p.uniform_gender = %(gender)s" + pcond, {**base, "gender": gender})
    if not r:  # company-wide
        r = _ratio_sql(field, pcond, base)
    cache[key] = r
    return r
