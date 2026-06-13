"""Phase B — Action APIs & Phase C — Dashboard APIs for Uniform Control."""
import frappe
from frappe import _
from frappe.utils import flt, cint, today

from customize_erpnext.uniform_control.utils import (
    get_eligible_employees_for_allocation,
    get_uniform_warehouse,
    get_item_available_qty,
    get_policy_for_template,
)


def _check_permission(doctype="Uniform Allocation", ptype="read"):
    if not frappe.has_permission(doctype, ptype):
        frappe.throw(_("Not permitted"), frappe.PermissionError)


# ─────────────────────────────── Phase B ───────────────────────────────────

@frappe.whitelist()
def get_eligible_employees(
    allocation_type, uniform_type=None, department=None,
    joining_date_from=None, joining_date_to=None,
    group=None, gender=None,
):
    """
    Return employees eligible for the given allocation_type.
    Includes suggested item_code, qty, available_qty per row.
    """
    _check_permission()
    return get_eligible_employees_for_allocation(
        allocation_type, uniform_type, department,
        joining_date_from, joining_date_to, group, gender,
    )


@frappe.whitelist(methods=["POST"])
def create_allocation(header, items):
    """
    Create a Draft Uniform Allocation from payload.
    header: dict with posting_date, allocation_type, company, set_warehouse, etc.
    items: list of dicts (employee, item_code, qty, issue_reason, ...)
    """
    _check_permission(ptype="create")

    if isinstance(header, str):
        header = frappe.parse_json(header)
    if isinstance(items, str):
        items = frappe.parse_json(items)

    alloc = frappe.new_doc("Uniform Allocation")
    alloc.update(header)
    for item in items:
        alloc.append("items", item)

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
    """Employees with uniform items Due Soon / Overdue (Active employees only).
    Includes the profile size/color for the template (per policy variant_source)."""
    _check_permission(doctype="Employee Uniform Profile")

    from customize_erpnext.uniform_control.utils import get_employee_id_prefix

    prefix = get_employee_id_prefix()
    prefix_cond = "AND p.employee LIKE %(prefix)s" if prefix else ""

    rows = frappe.db.sql(
        f"""
        SELECT
            p.employee, p.employee_name, p.department,
            eui.item_template, eui.last_issue_date, eui.next_due_date, eui.status,
            p.shirt_size, p.hat_color, p.shoe_size,
            e.designation, e.gender, e.custom_group
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

    setting = frappe.get_single("Uniform Setting")
    source_field = {"Shirt Size": "shirt_size", "Cap Color": "hat_color", "Shoe Size": "shoe_size"}
    for r in rows:
        emp_data = {
            "department": r.department,
            "designation": r.designation,
            "gender": r.gender,
            "custom_group": r.custom_group,
        }
        policy = get_policy_for_template(r.item_template, setting, emp_data)
        field = source_field.get(policy.get("variant_source")) if policy else None
        r["size"] = r.get(field) or "" if field else ""
        for k in ("shirt_size", "hat_color", "shoe_size", "designation", "gender"):
            r.pop(k, None)

    return rows


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
        "Employee", "Employee Name", "Department", "Group", "Uniform Type",
        "Size", "Last Issue Date", "Next Due Date", "Status",
    ])
    for r in get_due_items(limit=100000):
        ws_due.append([
            r.get("employee"), r.get("employee_name"), r.get("department"),
            r.get("custom_group"), r.get("item_template"), r.get("size"),
            str(r.get("last_issue_date") or ""), str(r.get("next_due_date") or ""),
            r.get("status"),
        ])

    ws_stock = wb.create_sheet("Uniform Stock")
    ws_stock.append([
        "Item Code", "Item Name", "Template", "Actual Qty", "Reserved Qty",
        "Reorder Level", "Reorder Qty", "Valuation Rate", "Stock Value",
        "Low Stock", "Warehouse",
    ])
    for r in get_uniform_stock_excel():
        ws_stock.append([
            r.get("item_code"), r.get("item_name"), r.get("template"),
            r.get("actual_qty"), r.get("reserved_qty"), r.get("reorder_level"),
            r.get("reorder_qty"), r.get("valuation_rate"), r.get("stock_value"),
            r.get("low_stock"), r.get("warehouse"),
        ])

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
