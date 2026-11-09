"""Uniform Control — allocation, stock receipt and dashboard APIs."""
import frappe
from frappe import _
from frappe.utils import flt, cint, today, add_days

from customize_erpnext.uniform_control import utils
from customize_erpnext.uniform_control.utils import get_uniform_warehouse


def _check_permission(doctype="Uniform Allocation", ptype="read"):
    if not frappe.has_permission(doctype, ptype):
        frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def get_due_rows(uniform_type=None, department=None, group=None, due_before=None,
                 issue_filter=None):
    """Rows for "Get Employees" on a Uniform Allocation: every item that is due,
    each with its Issue Reason (New Issue / Periodic Supplement)."""
    _check_permission(ptype="create")
    return utils.get_due_rows(uniform_type, department, group, due_before, issue_filter)


@frappe.whitelist(methods=["POST"])
def create_missing_profiles():
    """Dashboard banner: create the profiles managed Active employees lack."""
    _check_permission(doctype="Employee Uniform Profile", ptype="create")
    return {"created": utils.ensure_profiles()}


@frappe.whitelist(methods=["POST"])
def receive_stock(items, posting_date=None):
    """Stock receipt for HR (dashboard "Receive Stock"): creates and submits a
    Material Receipt into the Uniform warehouse. HR needs no Stock Entry rights —
    the same way a Uniform Allocation posts its Material Issue.
    items: list of {item_code, qty, rate}."""
    _check_permission(ptype="create")

    if isinstance(items, str):
        items = frappe.parse_json(items)
    items = [i for i in (items or []) if i.get("item_code")]
    if not items:
        frappe.throw(_("Add at least one item."))

    warehouse = get_uniform_warehouse()
    if not warehouse:
        frappe.throw(_("Uniform Warehouse is not configured in Uniform Setting."))
    group = frappe.db.get_single_value("Uniform Setting", "uniform_item_group")

    for i in items:
        info = frappe.db.get_value("Item", i.get("item_code"),
                                   ["item_group", "has_variants", "disabled"], as_dict=True)
        if not info or (group and info.item_group != group) or info.has_variants or info.disabled:
            frappe.throw(_("{0} is not an active uniform item (one size/colour).").format(i.get("item_code")))
        if cint(i.get("qty")) <= 0:
            frappe.throw(_("{0}: quantity must be greater than 0.").format(i.get("item_code")))
        if flt(i.get("rate")) <= 0:
            frappe.throw(_("{0}: enter the unit price (needed for the stock value).").format(i.get("item_code")))

    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Receipt"
    se.posting_date = posting_date or today()
    se.set_posting_time = 1 if posting_date else 0
    se.company = frappe.db.get_value("Warehouse", warehouse, "company")
    se.to_warehouse = warehouse
    for i in items:
        se.append("items", {
            "item_code": i.get("item_code"),
            "qty": cint(i.get("qty")),
            "t_warehouse": warehouse,
            "basic_rate": flt(i.get("rate")),
        })
    se.insert(ignore_permissions=True)
    se.submit()
    return {"name": se.name, "qty": sum(cint(i.get("qty")) for i in items)}


@frappe.whitelist()
def get_dashboard_summary():
    """Dashboard cards (low stock, items due soon / overdue) + data warnings
    (employees without a profile, without a shirt size, without a shoe size)."""
    _check_permission()

    warehouse = get_uniform_warehouse()
    low_stock_count = 0
    if warehouse:
        bins = {
            b.item_code: flt(b.actual_qty)
            for b in frappe.get_all("Bin", filters={"warehouse": warehouse},
                                    fields=["item_code", "actual_qty"])
        }
        for r in frappe.db.sql(
            """SELECT ir.parent, ir.warehouse_reorder_level FROM `tabItem Reorder` ir
            JOIN `tabItem` i ON i.name = ir.parent
            WHERE ir.warehouse = %s AND i.disabled = 0""",
            warehouse, as_dict=True,
        ):
            level = flt(r.warehouse_reorder_level)
            if level > 0 and bins.get(r.parent, 0) <= level:
                low_stock_count += 1

    # Due / overdue — from next_due_date (always fresh), Active managed employees
    reminder = utils.get_reminder_days()
    prefix = utils.get_employee_id_prefix()
    like = f"{prefix}%" if prefix else "%"
    due_soon, overdue = frappe.db.sql(
        """
        SELECT
            SUM(eui.next_due_date >= %(today)s AND eui.next_due_date <= %(cutoff)s),
            SUM(eui.next_due_date < %(today)s)
        FROM `tabEmployee Uniform Item` eui
        INNER JOIN `tabEmployee Uniform Profile` p ON p.name = eui.parent
        INNER JOIN `tabEmployee` e ON e.name = p.employee
        WHERE eui.next_due_date IS NOT NULL
          AND e.status = 'Active' AND p.employee LIKE %(like)s
        """,
        {"today": today(), "cutoff": add_days(today(), reminder), "like": like},
    )[0]

    no_profile, no_shirt, no_shoe = frappe.db.sql(
        """
        SELECT
            SUM(p.name IS NULL),
            SUM(IFNULL(e.custom_shirt_size, '') = ''),
            SUM(IFNULL(e.custom_shoe_size, '') = '')
        FROM `tabEmployee` e
        LEFT JOIN `tabEmployee Uniform Profile` p ON p.employee = e.name
        WHERE e.status = 'Active' AND e.name LIKE %(like)s
        """,
        {"like": like},
    )[0]

    return {
        "low_stock_variants": low_stock_count,
        "employees_due_soon": cint(due_soon),
        "employees_overdue": cint(overdue),
        "warehouse": warehouse,
        "prefix": prefix,
        "missing_profiles": cint(no_profile),
        "missing_shirt_size": cint(no_shirt),
        "missing_shoe_size": cint(no_shoe),
    }


@frappe.whitelist()
def get_due_items(limit=100, due_before=None):
    """Employees with uniform items due for reissue up to `due_before` (Active
    managed employees), counting EVERY reissue cycle in the horizon.

    Default `due_before` = today + 1 year. Each row carries qty_per_cycle,
    cycles and total_qty; `needed` aggregates total_qty (multi-cycle) per variant.
    Returns {"rows": [...], "needed": {variant: total_qty}}."""
    _check_permission(doctype="Employee Uniform Profile")

    from math import ceil
    from frappe.utils import getdate, date_diff
    from customize_erpnext.uniform_control.utils import (
        reissue_demand, leaver_missed_demand,
    )

    setting = frappe.get_single("Uniform Setting")
    to_date = due_before or add_days(today(), 365)

    res = reissue_demand(to_date, setting)

    # "Est. for Leavers" — MEASURED model: missed re-issues of actual leavers
    # in the Attrition Window → monthly average × months of this horizon,
    # rounded UP, clamped to the variant's gross demand.
    enabled = bool(cint(setting.get("consider_attrition")))
    est, attrition = {}, {"enabled": enabled, "months": 0, "persons": 0,
                          "monthly_total": 0, "period_months": 0}
    if enabled:
        miss = leaver_missed_demand(setting.get("attrition_months"))
        # day-based months so a 1-month horizon inside one calendar month ≠ 0
        period = max(0.0, date_diff(getdate(to_date), getdate(today())) / 30.44)
        for v, monthly in miss["monthly"].items():
            e = min(cint(res["needed"].get(v, 0)), ceil(monthly * period))
            if e > 0:
                est[v] = e
        attrition.update({
            "months": miss["months"], "persons": miss["persons"],
            "monthly_total": round(miss["total_qty"] / miss["months"], 1),
            "period_months": round(period, 1), "window": miss["window"],
        })

    rows = res["rows"]
    # `qty` kept as the per-cycle qty for backward-compatible callers
    for r in rows:
        r["qty"] = r["qty_per_cycle"]
    if cint(limit):
        rows = rows[: cint(limit)]
    return {
        "rows": rows,
        "needed": res["needed"],        # full (gross) demand, from tracking
        "est_for_leavers": est,         # measured slice per variant (positive)
        "attrition": attrition,
    }


@frappe.whitelist(methods=["POST"])
def rebuild_tracking(employee):
    """Repair tool (System Manager): rebuild an employee's tracking rows from the
    SUBMITTED Uniform Allocations, on top of the history imported before ERP
    (base_* fields). Rows of item types never allocated are left untouched."""
    frappe.only_for("System Manager")
    from customize_erpnext.uniform_control.doctype.employee_uniform_profile.employee_uniform_profile import (
        _allocation_history, apply_history,
    )

    name = frappe.db.get_value("Employee Uniform Profile", {"employee": employee})
    if not name:
        return {"ok": False}

    templates = {
        r.template for r in frappe.db.sql(
            """
            SELECT DISTINCT COALESCE(NULLIF(i.variant_of, ''), i.name) AS template
            FROM `tabUniform Allocation Item` uai
            JOIN `tabItem` i ON i.name = uai.item_code
            WHERE uai.docstatus = 1 AND uai.employee = %s
            """,
            employee, as_dict=True,
        )
    }
    profile = frappe.get_doc("Employee Uniform Profile", name)
    by_tmpl = {utils.template_of(row.item_template): row for row in profile.all_tracking_rows()}
    for tmpl in templates:
        row = by_tmpl.get(tmpl) or profile.append(profile.tracking_field_for(tmpl), {"item_template": tmpl})
        apply_history(row, _allocation_history(employee, tmpl))
    profile.save(ignore_permissions=True)  # validate refreshes next_due/status
    return {"ok": True, "rebuilt": len(templates)}


@frappe.whitelist()
def export_dashboard_excel(due_before=None):
    """Download dashboard data as .xlsx — matches the on-screen view:
      sheet 1 "Stock Plan": Stock | Reissue Need (gross, from tracking) |
        Est. for Leavers (negative, informational) | Total | Shortfall;
      sheet 2 "Employees Due for Issue": reissue rows with cycles (multi-cycle).
    `due_before` = reissue horizon (default today)."""
    _check_permission()

    import openpyxl
    from io import BytesIO
    from openpyxl.styles import Font

    from customize_erpnext.uniform_control.api.uniform_excel_api import get_uniform_stock_excel

    # Default horizon = today (same as the dashboard's default filter)
    horizon = due_before or today()
    due = get_due_items(limit=100000, due_before=horizon)
    due_rows, gross = due["rows"], due["needed"]
    est_map = due.get("est_for_leavers") or {}
    attr = due.get("attrition") or {}

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    bold = Font(bold=True)

    # Sheet 1 — purchasing plan. Fixed columns, same as on screen:
    # Reissue Need = gross tracking demand; Est. for Leavers = NEGATIVE
    # informational slice; Total = the two combined; Shortfall = Total − Stock.
    ws_plan = wb.create_sheet("Stock Plan")
    ws_plan.append([
        "Uniform Type", "Item", "Stock", "Reissue Need",
        "Est. for Leavers", "Total", "Shortfall", "Warehouse",
    ])
    for r in get_uniform_stock_excel():
        code = r.get("item_code")
        stock = cint(r.get("actual_qty"))
        g = cint(gross.get(code, 0))
        leavers = -cint(est_map.get(code, 0))
        total = g + leavers
        ws_plan.append([
            r.get("template"), r.get("item_name") or code, stock, g, leavers,
            total, max(0, total - stock), r.get("warehouse"),
        ])

    # Sheet 2 — employees due, with reissue cycles in the horizon
    ws_due = wb.create_sheet("Employees Due for Issue")
    ws_due.append([
        "Employee", "Employee Name", "Department", "Section", "Group", "Uniform Type",
        "Size", "Qty/Cycle", "Cycles", "Total Qty", "Last Issue Date", "Next Due Date", "Status",
    ])
    for r in due_rows:
        ws_due.append([
            r.get("employee"), r.get("employee_name"), r.get("department"),
            r.get("custom_section"), r.get("custom_group"), r.get("item_template"),
            r.get("size"), r.get("qty_per_cycle"), r.get("cycles"), r.get("total_qty"),
            str(r.get("last_issue_date") or ""), str(r.get("next_due_date") or ""), r.get("status"),
        ])

    ws_plan.append([])
    if attr.get("enabled"):
        ws_plan.append([
            f"Note: 'Est. for Leavers' (negative) is MEASURED: in the last {attr['months']} "
            f"full months, {attr['persons']} leavers missed re-issues (avg "
            f"{attr['monthly_total']}/month) → × {attr['period_months']} month(s) of this "
            f"horizon, rounded up. Total = Reissue Need + Est.; Shortfall = Total − Stock."
        ])
    else:
        ws_plan.append([
            "Note: Deduct Attrition is OFF in Uniform Setting — Est. for Leavers is 0 "
            "and Total equals Reissue Need."
        ])

    for ws in (ws_plan, ws_due):
        for cell in ws[1]:
            cell.font = bold

    buf = BytesIO()
    wb.save(buf)

    frappe.response["filename"] = f"uniform-dashboard-{today()}.xlsx"
    frappe.response["filecontent"] = buf.getvalue()
    frappe.response["type"] = "binary"
