"""Phase B — Action APIs & Phase C — Dashboard APIs for Uniform Control."""
import frappe
from frappe import _
from frappe.utils import flt, cint, today

from customize_erpnext.uniform_control.utils import (
    get_eligible_employees_for_allocation,
    get_uniform_warehouse,
    get_item_available_qty,
)


def _check_permission(doctype="Uniform Allocation", ptype="read"):
    if not frappe.has_permission(doctype, ptype):
        frappe.throw(_("Not permitted"), frappe.PermissionError)


# ─────────────────────────────── Phase B ───────────────────────────────────

@frappe.whitelist()
def get_eligible_employees(
    allocation_type, uniform_type=None, department=None,
    joining_date_from=None, joining_date_to=None,
    group=None, gender=None, due_date_from=None, due_date_to=None,
    overdue_only=0,
):
    """
    Return employees eligible for the given allocation_type.
    Includes suggested item_code, qty, available_qty per row.
    """
    _check_permission()
    return get_eligible_employees_for_allocation(
        allocation_type, uniform_type, department,
        joining_date_from, joining_date_to, group, gender,
        due_date_from, due_date_to, overdue_only,
    )


ALLOWED_HEADER_FIELDS = {
    "naming_series", "posting_date", "allocation_type", "company", "set_warehouse",
    "uniform_type_filter", "department_filter", "group_filter", "gender_filter",
    "joining_date_from", "joining_date_to",
}
ALLOWED_ITEM_FIELDS = {
    "employee", "item_code", "qty", "issue_reason", "shoe_rack_location", "remark",
}


@frappe.whitelist(methods=["POST"])
def create_allocation(header, items):
    """
    Create a Draft Uniform Allocation from payload (only whitelisted fields).
    header: dict with posting_date, allocation_type, company, set_warehouse, etc.
    items: list of dicts (employee, item_code, qty, issue_reason, ...)
    """
    _check_permission(ptype="create")

    if isinstance(header, str):
        header = frappe.parse_json(header)
    if isinstance(items, str):
        items = frappe.parse_json(items)

    alloc = frappe.new_doc("Uniform Allocation")
    alloc.update({k: v for k, v in (header or {}).items() if k in ALLOWED_HEADER_FIELDS})
    for item in items or []:
        alloc.append("items", {k: v for k, v in item.items() if k in ALLOWED_ITEM_FIELDS})

    alloc.insert(ignore_permissions=True)
    return alloc.name


@frappe.whitelist(methods=["POST"])
def submit_allocation(name):
    """Submit Allocation → creates Material Issue + updates profiles."""
    _check_permission(ptype="submit")

    alloc = frappe.get_doc("Uniform Allocation", name)
    if alloc.docstatus != 0:
        frappe.throw(_("Allocation {0} is not in Draft state.").format(name))
    alloc.submit()
    return {"name": alloc.name, "stock_entry": alloc.stock_entry}


@frappe.whitelist(methods=["POST"])
def receive_stock(items):
    """
    Simplified stock receipt for HR.
    items: list of {item_code, qty, valuation_rate} dicts.
    Creates a Material Receipt Stock Entry into the Uniform warehouse.
    """
    _check_permission(doctype="Stock Entry", ptype="create")

    if isinstance(items, str):
        items = frappe.parse_json(items)

    warehouse = get_uniform_warehouse()
    if not warehouse:
        frappe.throw(_("Uniform Warehouse is not configured in Uniform Setting."))

    # Derive company from the warehouse — user default may belong to another company
    company = (
        frappe.db.get_value("Warehouse", warehouse, "company")
        or frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
    )

    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Receipt"
    se.posting_date = today()
    se.company = company
    se.to_warehouse = warehouse

    for item in items:
        se.append("items", {
            "item_code": item.get("item_code"),
            "qty": cint(item.get("qty")),
            "t_warehouse": warehouse,
            "basic_rate": flt(item.get("valuation_rate", 0)),
        })

    se.insert(ignore_permissions=True)
    se.submit()
    return {"name": se.name, "status": "Submitted"}


# ─────────────────────────────── Phase C ───────────────────────────────────

@frappe.whitelist()
def get_dashboard_summary():
    """
    Return summary data for the Uniform Control Dashboard:
    - total variants in stock
    - low stock count
    - employees due soon / overdue
    - recent allocations count
    """
    _check_permission()

    warehouse = get_uniform_warehouse()

    # Stock summary — without a configured warehouse there is nothing to count
    bins = []
    reorder_levels = {}
    if warehouse:
        bins = frappe.get_all(
            "Bin",
            filters={"warehouse": warehouse},
            fields=["item_code", "actual_qty"],
            order_by="item_code asc",
        )
        reorder_levels = {
            r.parent: flt(r.warehouse_reorder_level)
            for r in frappe.get_all(
                "Item Reorder",
                filters={"warehouse": warehouse},
                fields=["parent", "warehouse_reorder_level"],
            )
        }
    low_stock_count = sum(
        1 for b in bins
        if reorder_levels.get(b.item_code, 0) > 0
        and flt(b.actual_qty) <= reorder_levels[b.item_code]
    )

    # Due / overdue employees
    due_soon = frappe.db.count(
        "Employee Uniform Item", {"status": "Due Soon"}
    )
    overdue = frappe.db.count(
        "Employee Uniform Item", {"status": "Overdue"}
    )

    # Recent allocations (last 30 days)
    recent_allocs = frappe.db.count(
        "Uniform Allocation",
        {"docstatus": 1, "posting_date": [">=", frappe.utils.add_days(today(), -30)]},
    )

    return {
        "total_variants_in_stock": len(bins),
        "low_stock_variants": low_stock_count,
        "employees_due_soon": cint(due_soon),
        "employees_overdue": cint(overdue),
        "allocations_last_30_days": cint(recent_allocs),
        "warehouse": warehouse,
    }


@frappe.whitelist()
def get_due_items(limit=100):
    """Employees with uniform items Due Soon / Overdue (Active managed employees).
    item_template holds the exact variant; `size` is its size/color attribute."""
    _check_permission(doctype="Employee Uniform Profile")

    from customize_erpnext.uniform_control.utils import get_employee_id_prefix

    prefix = get_employee_id_prefix()
    prefix_cond = "AND p.employee LIKE %(prefix)s" if prefix else ""

    rows = frappe.db.sql(
        f"""
        SELECT
            p.employee, p.employee_name, p.department, e.custom_section, e.custom_group,
            eui.item_template, eui.last_issue_date, eui.next_due_date, eui.status
        FROM `tabEmployee Uniform Item` eui
        INNER JOIN `tabEmployee Uniform Profile` p ON p.name = eui.parent
        INNER JOIN `tabEmployee` e ON e.name = p.employee
        WHERE eui.status IN ('Due Soon', 'Overdue')
          AND e.status = 'Active'
          {prefix_cond}
        ORDER BY eui.next_due_date ASC
        LIMIT %(limit)s
        """,
        {"limit": cint(limit) or 100, "prefix": f"{prefix}%"},
        as_dict=True,
    )

    # item_template is the exact variant — show its size/color attribute value
    variants = {r.item_template for r in rows if r.item_template}
    attr_val = {}
    if variants:
        for a in frappe.get_all(
            "Item Variant Attribute",
            filters={"parent": ["in", list(variants)]},
            fields=["parent", "attribute_value"],
        ):
            attr_val.setdefault(a.parent, a.attribute_value)

    for r in rows:
        r["size"] = attr_val.get(r.item_template, "")

    return rows


@frappe.whitelist(methods=["POST"])
def rebuild_tracking(employee):
    """Re-sync an employee's Issuance Tracking from SUBMITTED Uniform Allocations
    (the source of truth). Templates with allocations are recomputed; legacy rows
    with no allocation are left untouched. Then next_due/status are refreshed."""
    _check_permission(doctype="Employee Uniform Profile", ptype="write")
    from customize_erpnext.uniform_control.doctype.employee_uniform_profile.employee_uniform_profile import _template_of

    name = frappe.db.get_value("Employee Uniform Profile", {"employee": employee})
    if not name:
        return {"ok": False}

    rows = frappe.db.sql(
        """
        SELECT uai.item_code, uai.qty, ua.posting_date,
               COALESCE(NULLIF(i.variant_of, ''), i.name) AS template
        FROM `tabUniform Allocation Item` uai
        JOIN `tabUniform Allocation` ua ON ua.name = uai.parent
        JOIN `tabItem` i ON i.name = uai.item_code
        WHERE uai.docstatus = 1 AND uai.employee = %s
        ORDER BY ua.posting_date ASC
        """,
        employee, as_dict=True,
    )
    agg = {}
    for r in rows:
        a = agg.setdefault(r.template, {"total": 0, "last": None, "item": None, "last_qty": 0})
        a["total"] += cint(r.qty)
        d = frappe.utils.getdate(r.posting_date)
        if a["last"] is None or d > a["last"]:
            a["last"], a["item"], a["last_qty"] = d, r.item_code, cint(r.qty)
        elif d == a["last"]:
            a["last_qty"] += cint(r.qty)
            a["item"] = r.item_code

    profile = frappe.get_doc("Employee Uniform Profile", name)
    by_tmpl = {_template_of(row.item_template): row for row in profile.items}
    for tmpl, a in agg.items():
        row = by_tmpl.get(tmpl) or profile.append("items", {})
        row.item_template = a["item"]
        row.last_issue_date = a["last"]
        row.last_issue_qty = a["last_qty"]
        row.total_issued_qty = a["total"]
    profile.save(ignore_permissions=True)  # validate refreshes next_due/status
    return {"ok": True, "rebuilt": len(agg)}


@frappe.whitelist(methods=["POST"])
def apply_default_rules(employee=None):
    """Apply Default Rules to one profile (employee given) or ALL managed
    profiles without Manual Override. Returns count of profiles changed."""
    _check_permission(doctype="Employee Uniform Profile", ptype="write")

    from customize_erpnext.uniform_control import utils

    setting = frappe.get_single("Uniform Setting")
    filters = {}
    if employee:
        filters["employee"] = employee
    else:
        filters["manual_override"] = 0

    # Single employee = explicit intent → overwrite. Bulk = fill empty only,
    # so real per-person assignments (e.g. imported shirts) are preserved.
    force = bool(employee)
    names = frappe.get_all("Employee Uniform Profile", filters=filters, pluck="name")
    changed = 0
    for name in names:
        profile = frappe.get_doc("Employee Uniform Profile", name)
        if not employee and profile.manual_override:
            continue
        fields = utils.apply_default_rules(profile, setting=setting, force=force)
        if fields:
            profile.save(ignore_permissions=True)
            changed += 1

    return {"profiles": len(names), "changed": changed}


@frappe.whitelist()
def export_dashboard_excel():
    """Download dashboard data as .xlsx — sheet 1: Employees Due for Issue,
    sheet 2: Uniform Stock."""
    _check_permission()

    import openpyxl
    from io import BytesIO
    from openpyxl.styles import Font

    from customize_erpnext.uniform_control.api.uniform_excel_api import get_uniform_stock_excel

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    bold = Font(bold=True)

    ws_due = wb.create_sheet("Employees Due for Issue")
    ws_due.append([
        "Employee", "Employee Name", "Department", "Section", "Group", "Uniform Type",
        "Size", "Last Issue Date", "Next Due Date", "Status",
    ])
    for r in get_due_items(limit=100000):
        ws_due.append([
            r.get("employee"), r.get("employee_name"), r.get("department"),
            r.get("custom_section"), r.get("custom_group"), r.get("item_template"),
            r.get("size"), str(r.get("last_issue_date") or ""),
            str(r.get("next_due_date") or ""), r.get("status"),
        ])

    ws_stock = wb.create_sheet("Uniform Stock")
    ws_stock.append(["Item Name", "Template", "Size", "Actual Qty", "Warehouse"])
    for r in get_uniform_stock_excel():
        name = r.get("item_name") or ""
        tmpl = r.get("template") or ""
        # Size = the variant suffix of the item name (template name stripped off)
        size = name[len(tmpl):].strip() if tmpl and name.startswith(tmpl) else ""
        ws_stock.append([name, tmpl, size, r.get("actual_qty"), r.get("warehouse")])

    for ws in (ws_due, ws_stock):
        for cell in ws[1]:
            cell.font = bold

    buf = BytesIO()
    wb.save(buf)

    frappe.response["filename"] = f"uniform-dashboard-{today()}.xlsx"
    frappe.response["filecontent"] = buf.getvalue()
    frappe.response["type"] = "binary"


@frappe.whitelist()
def get_employee_uniform_profile(employee):
    """Return Employee Uniform Profile + issuance history."""
    _check_permission(doctype="Employee Uniform Profile")

    profile_name = frappe.db.get_value(
        "Employee Uniform Profile", {"employee": employee}
    )
    if not profile_name:
        return None

    profile = frappe.get_doc("Employee Uniform Profile", profile_name)

    # Allocation history
    history = frappe.get_all(
        "Uniform Allocation Item",
        filters={"employee": employee, "docstatus": 1},
        fields=["parent", "item_code", "item_name", "qty", "issue_reason"],
        order_by="creation desc",
        limit=50,
    )

    return {
        "profile": profile.as_dict(),
        "history": history,
    }
