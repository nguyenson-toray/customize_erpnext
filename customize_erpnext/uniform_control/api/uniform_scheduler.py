"""Weekly scheduler for Uniform Control — stock vs upcoming demand + due employees."""
import frappe
from frappe.utils import flt, cint, today, getdate, add_days


def send_weekly_uniform_alert(force=False):
    """
    One email to alert_recipients with:
      1. Uniform stock (ALL U-Uniform variants, incl. 0) vs qty needed for the
         next reissue → flags shortages.
      2. Employees due for reissue (with the qty to issue).
    Weekly via scheduler. force=True (manual button) ignores the enable toggle,
    sends even when nothing is urgent, returns a summary, and re-raises errors.
    """
    try:
        setting = frappe.get_single("Uniform Setting")
        if not force and not cint(setting.enable_weekly_alert):
            return

        recipients = [r.strip() for r in (setting.alert_recipients or "").split(",") if r.strip()]
        if not recipients:
            return {"sent": False, "reason": "no_recipients"} if force else None

        warehouse = setting.uniform_warehouse
        item_group = setting.uniform_item_group or "U-Uniform"
        reminder_days = cint(setting.reminder_days_before) or 30
        today_date = getdate(today())
        alert_cutoff = add_days(today_date, reminder_days)

        from customize_erpnext.uniform_control.utils import (
            get_rule_for_tracking, get_employee_id_prefix,
        )

        # ── Employees due for reissue (+ qty needed per variant) ──
        # Scope by next_due_date ONLY: the stored `status` field is refreshed
        # just on profile save, so it goes stale between saves and would
        # silently drop rows that crossed the Due-Soon boundary since then.
        # The date condition is exactly equivalent to a fresh status check.
        prefix = get_employee_id_prefix()
        prefix_cond = "AND p.employee LIKE %(prefix)s" if prefix else ""
        due_items = frappe.db.sql(
            f"""
            SELECT p.employee, p.employee_name, p.department,
                   eui.item_template, eui.next_due_date
            FROM `tabEmployee Uniform Item` eui
            INNER JOIN `tabEmployee Uniform Profile` p ON p.name = eui.parent
            INNER JOIN `tabEmployee` e ON e.name = p.employee
            WHERE eui.next_due_date IS NOT NULL AND eui.next_due_date <= %(cutoff)s
              AND e.status = 'Active' {prefix_cond}
            ORDER BY eui.next_due_date ASC
            """,
            {"cutoff": alert_cutoff, "prefix": f"{prefix}%"}, as_dict=True,
        )

        # Batch variant→template resolution (avoids one query per row)
        variants = {di.item_template for di in due_items if di.item_template}
        template_of = {}
        if variants:
            for it in frappe.get_all("Item", filters={"name": ["in", list(variants)]},
                                     fields=["name", "variant_of"]):
                template_of[it.name] = it.variant_of or it.name

        due_rows = []
        needed = {}  # variant item_code -> total qty needed next reissue
        rule_cache = {}  # (employee, template) -> rule
        for di in due_items:
            variant = di.item_template
            template = template_of.get(variant, variant)
            key = (di.employee, template)
            if key not in rule_cache:
                rule_cache[key] = get_rule_for_tracking(template, di.employee, setting)
            rule = rule_cache[key]
            qty = cint(rule.reissue_qty) if rule and not rule.one_time else 0
            needed[variant] = needed.get(variant, 0) + qty
            due_rows.append({
                "employee": di.employee,
                "employee_name": di.employee_name,
                "department": di.department,
                "item_template": variant,
                "qty": qty,
                "next_due_date": str(di.next_due_date),
                # status derived from the date — always fresh
                "status": "Overdue" if getdate(di.next_due_date) < today_date else "Due Soon",
            })

        # ── Stock: ALL U-Uniform stockable variants (include 0 qty) ──
        bin_qty, reorder_lvl = {}, {}
        if warehouse:
            bin_qty = {
                b.item_code: flt(b.actual_qty)
                for b in frappe.get_all("Bin", filters={"warehouse": warehouse},
                                        fields=["item_code", "actual_qty"])
            }
            reorder_lvl = {
                r.parent: flt(r.warehouse_reorder_level)
                for r in frappe.get_all("Item Reorder", filters={"warehouse": warehouse},
                                        fields=["parent", "warehouse_reorder_level"])
            }

        stock_rows = []
        short_count = 0
        for it in frappe.get_all(
            "Item",
            filters={"item_group": item_group, "is_stock_item": 1,
                     "has_variants": 0, "disabled": 0},
            fields=["name", "item_name"], order_by="name asc",
        ):
            actual = bin_qty.get(it.name, 0)
            need = needed.get(it.name, 0)
            remaining = actual - need
            rl = reorder_lvl.get(it.name, 0)
            if need > 0 and remaining < 0:
                status = "THIẾU"
                short_count += 1
            elif rl > 0 and actual <= rl:
                status = "Tồn thấp"
            else:
                status = "Đủ"
            stock_rows.append({
                "item_code": it.name, "item_name": it.item_name,
                "actual_qty": actual, "needed": need, "remaining": remaining,
                "reorder_level": rl, "status": status,
            })

        if not stock_rows and not due_rows:
            return {"sent": False, "reason": "nothing_to_alert"} if force else None
        if not force and not due_rows and short_count == 0:
            return  # weekly: nothing urgent (no shortage, no one due)

        # Due table sorted ascending by employee id
        due_rows.sort(key=lambda r: r["employee"])

        # ── Build & send email ──
        subject = f"[Uniform] Cảnh báo tồn kho & đến hạn — {today()}"
        message = f"""
        <h3>Uniform Control — Cảnh báo</h3>
        <h4>1. Tồn kho đồng phục — đủ cho đợt cấp tới? ({short_count} mục THIẾU)</h4>
        {_build_stock_table(stock_rows)}
        <h4>2. Nhân viên đến hạn cấp ({len(due_rows)} dòng)</h4>
        {_build_due_table(due_rows)}
        <p><a href="/app/uniform-dashboard">Mở Uniform Dashboard</a></p>
        """
        frappe.sendmail(recipients=recipients, subject=subject, message=message, now=True)
        frappe.db.commit()

        return {
            "sent": True, "recipients": recipients,
            "short": short_count, "due": len(due_rows),
        } if force else None

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Uniform Weekly Alert Error")
        if force:
            raise


@frappe.whitelist()
def send_uniform_alert_now():
    """Manual trigger for the alert (Uniform Setting button)."""
    frappe.only_for(("System Manager", "Uniform Manager"))
    return send_weekly_uniform_alert(force=True) or {"sent": False, "reason": "disabled"}


def _build_stock_table(rows):
    if not rows:
        return "<p>Chưa có item đồng phục.</p>"
    html = (
        "<table border='1' cellpadding='4' cellspacing='0'>"
        "<tr><th>Item</th><th>Tên</th><th>Tồn</th><th>Cần cấp tới</th>"
        "<th>Sau khi cấp</th><th>Ngưỡng</th><th>Trạng thái</th></tr>"
    )
    for r in rows:
        bg = "#ffd6d6" if r["status"] == "THIẾU" else ("#fff3cd" if r["status"] == "Tồn thấp" else "")
        style = f" style='background:{bg}'" if bg else ""
        html += (
            f"<tr{style}><td>{r['item_code']}</td><td>{r['item_name'] or ''}</td>"
            f"<td align='right'>{r['actual_qty']:g}</td>"
            f"<td align='right'>{r['needed']:g}</td>"
            f"<td align='right'>{r['remaining']:g}</td>"
            f"<td align='right'>{r['reorder_level']:g}</td>"
            f"<td>{r['status']}</td></tr>"
        )
    return html + "</table>"


def _build_due_table(rows):
    if not rows:
        return "<p>Không có nhân viên đến hạn.</p>"
    html = (
        "<table border='1' cellpadding='4' cellspacing='0'>"
        "<tr><th>Mã NV</th><th>Tên</th><th>Phòng ban</th><th>Đồng phục</th>"
        "<th>SL cần cấp</th><th>Hạn</th><th>Trạng thái</th></tr>"
    )
    for r in rows:
        html += (
            f"<tr><td>{r['employee']}</td><td>{r['employee_name'] or ''}</td>"
            f"<td>{r['department'] or ''}</td><td>{r['item_template']}</td>"
            f"<td align='right'>{r['qty']}</td>"
            f"<td>{r['next_due_date']}</td><td>{r['status']}</td></tr>"
        )
    return html + "</table>"
