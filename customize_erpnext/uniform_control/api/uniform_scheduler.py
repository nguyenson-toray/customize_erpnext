"""Weekly scheduler for Uniform Control — low stock + due employees alerts."""
import frappe
from frappe import _
from frappe.utils import flt, cint, today, getdate, date_diff, add_days


def send_weekly_uniform_alert():
    """
    Runs weekly. Sends one email to alert_recipients with:
    1. Low-stock variants
    2. Employees due for reissue within reminder_days_before
    """
    try:
        setting = frappe.get_single("Uniform Setting")
        if not cint(setting.enable_weekly_alert):
            return

        recipients = [r.strip() for r in (setting.alert_recipients or "").split(",") if r.strip()]
        if not recipients:
            return

        warehouse = setting.uniform_warehouse
        reminder_days = cint(setting.reminder_days_before) or 30
        today_date = getdate(today())
        alert_cutoff = add_days(today_date, reminder_days)

        # ── Low stock section ──
        low_stock_rows = []
        if warehouse:
            bins = frappe.get_all(
                "Bin",
                filters={"warehouse": warehouse},
                fields=["item_code", "actual_qty"],
                order_by="item_code asc",
            )
            reorders = {
                r.parent: r
                for r in frappe.get_all(
                    "Item Reorder",
                    filters={"warehouse": warehouse},
                    fields=["parent", "warehouse_reorder_level", "warehouse_reorder_qty"],
                )
            }
            for b in bins:
                reorder = reorders.get(b.item_code)
                rl = flt(reorder.warehouse_reorder_level) if reorder else 0
                if rl > 0 and flt(b.actual_qty) <= rl:
                    item_name = frappe.db.get_value("Item", b.item_code, "item_name") or b.item_code
                    low_stock_rows.append({
                        "item_code": b.item_code,
                        "item_name": item_name,
                        "actual_qty": flt(b.actual_qty),
                        "reorder_level": rl,
                        "reorder_qty": flt(reorder.warehouse_reorder_qty),
                    })

        # ── Due employees section ──
        due_rows = []
        due_items = frappe.get_all(
            "Employee Uniform Item",
            filters={
                "next_due_date": ["between", [today_date, alert_cutoff]],
                "status": ["in", ["Active", "Due Soon", "Overdue"]],
            },
            fields=["parent", "item_template", "next_due_date", "status"],
            order_by="next_due_date asc",
        )
        from customize_erpnext.uniform_control.utils import is_managed_employee

        for di in due_items:
            profile = frappe.db.get_value(
                "Employee Uniform Profile",
                di.parent,
                ["employee", "employee_name", "department"],
                as_dict=True,
            ) or {}
            if not profile.get("employee"):
                continue
            if not is_managed_employee(profile["employee"]):
                continue
            emp_status = frappe.db.get_value("Employee", profile["employee"], "status")
            if emp_status != "Active":
                continue
            due_rows.append({
                "employee": profile["employee"],
                "employee_name": profile.get("employee_name"),
                "department": profile.get("department"),
                "item_template": di.item_template,
                "next_due_date": str(di.next_due_date),
                "status": di.status,
            })

        if not low_stock_rows and not due_rows:
            return

        # ── Build email ──
        low_table = _build_low_stock_table(low_stock_rows)
        due_table = _build_due_table(due_rows)

        subject = f"[Uniform] Weekly Alert — {today()}"
        message = f"""
        <h3>Uniform Control — Weekly Alert</h3>

        <h4>1. Low Stock Variants ({len(low_stock_rows)} items)</h4>
        {low_table}

        <h4>2. Employees Due for Reissue ({len(due_rows)} rows)</h4>
        {due_table}

        <p><a href="/app/uniform-allocation">Open Uniform Dashboard</a></p>
        """

        frappe.sendmail(
            recipients=recipients,
            subject=subject,
            message=message,
            now=True,
        )
        frappe.db.commit()

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Uniform Weekly Alert Error")


def _build_low_stock_table(rows):
    if not rows:
        return "<p>No low-stock items.</p>"
    html = (
        "<table border='1' cellpadding='4' cellspacing='0'>"
        "<tr><th>Item Code</th><th>Item Name</th><th>Actual Qty</th>"
        "<th>Reorder Level</th><th>Reorder Qty</th></tr>"
    )
    for r in rows:
        html += (
            f"<tr><td>{r['item_code']}</td><td>{r['item_name']}</td>"
            f"<td>{r['actual_qty']}</td><td>{r['reorder_level']}</td>"
            f"<td>{r['reorder_qty']}</td></tr>"
        )
    return html + "</table>"


def _build_due_table(rows):
    if not rows:
        return "<p>No employees due.</p>"
    html = (
        "<table border='1' cellpadding='4' cellspacing='0'>"
        "<tr><th>Employee</th><th>Name</th><th>Department</th>"
        "<th>Uniform Type</th><th>Due Date</th><th>Status</th></tr>"
    )
    for r in rows:
        html += (
            f"<tr><td>{r['employee']}</td><td>{r['employee_name']}</td>"
            f"<td>{r['department']}</td><td>{r['item_template']}</td>"
            f"<td>{r['next_due_date']}</td><td>{r['status']}</td></tr>"
        )
    return html + "</table>"
