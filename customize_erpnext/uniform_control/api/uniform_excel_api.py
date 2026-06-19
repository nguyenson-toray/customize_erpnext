"""Phase A — Read / Excel Power Query APIs for Uniform Control."""
import frappe
from frappe import _
from frappe.utils import flt, getdate, today, date_diff


def _check_permission():
    if not frappe.has_permission("Uniform Allocation", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def get_uniform_stock_excel(company=None, item_template=None):
    """
    Return current stock of ALL stockable uniform variants (item_group =
    Uniform Item Group), including items with qty 0 / no Bin record, with
    reorder levels and low-stock flag.
    """
    _check_permission()

    warehouse = frappe.db.get_single_value("Uniform Setting", "uniform_warehouse")
    item_group = frappe.db.get_single_value("Uniform Setting", "uniform_item_group") or "U-Uniform"
    if not warehouse:
        return []

    item_filters = {
        "item_group": item_group, "is_stock_item": 1,
        "has_variants": 0, "disabled": 0,
    }
    if item_template:
        item_filters["variant_of"] = item_template

    items = frappe.get_all(
        "Item", filters=item_filters,
        fields=["name", "item_name", "variant_of", "valuation_rate"],
        order_by="name asc",
    )
    if not items:
        return []
    names = [i.name for i in items]

    # Left-join Bin (qty 0 when no Bin) + reorder levels — one query each
    bin_map = {
        b.item_code: b
        for b in frappe.get_all(
            "Bin", filters={"warehouse": warehouse, "item_code": ["in", names]},
            fields=["item_code", "actual_qty", "reserved_qty"],
        )
    }
    reorder_map = {
        r.parent: r
        for r in frappe.get_all(
            "Item Reorder", filters={"warehouse": warehouse, "parent": ["in", names]},
            fields=["parent", "warehouse_reorder_level", "warehouse_reorder_qty"],
        )
    }

    results = []
    for it in items:
        b = bin_map.get(it.name)
        actual = flt(b.actual_qty) if b else 0
        reserved = flt(b.reserved_qty) if b else 0
        ro = reorder_map.get(it.name)
        reorder_level = flt(ro.warehouse_reorder_level) if ro else 0
        low_stock = 1 if reorder_level > 0 and actual <= reorder_level else 0

        results.append({
            "item_code": it.name,
            "item_name": it.item_name,
            "template": it.variant_of or it.name,
            "actual_qty": actual,
            "reserved_qty": reserved,
            "reorder_level": reorder_level,
            "reorder_qty": flt(ro.warehouse_reorder_qty) if ro else 0,
            "valuation_rate": flt(it.valuation_rate),
            "stock_value": actual * flt(it.valuation_rate),
            "low_stock": low_stock,
            "warehouse": warehouse,
        })

    return results


@frappe.whitelist()
def get_due_employees_excel(allocation_type=None, department=None, uniform_type=None):
    """
    Return employees due for new issue or supplement, with their profile info.
    """
    _check_permission()
    from customize_erpnext.uniform_control.utils import get_eligible_employees_for_allocation

    alloc_type = allocation_type or "New Issue"
    rows = get_eligible_employees_for_allocation(alloc_type, uniform_type, department)
    return rows


@frappe.whitelist()
def get_allocation_history_excel(from_date=None, to_date=None, employee=None, department=None):
    """Return allocation history with stock entry details."""
    _check_permission()

    alloc_filters = {"docstatus": 1}
    if from_date and to_date:
        alloc_filters["posting_date"] = ["between", [from_date, to_date]]
    elif from_date:
        alloc_filters["posting_date"] = [">=", from_date]
    elif to_date:
        alloc_filters["posting_date"] = ["<=", to_date]

    allocations = frappe.get_all(
        "Uniform Allocation",
        filters=alloc_filters,
        fields=["name", "posting_date", "allocation_type", "company", "stock_entry", "total_qty"],
        order_by="posting_date desc",
    )
    if not allocations:
        return []
    headers = {a.name: a for a in allocations}

    item_filters = {
        "parent": ["in", list(headers.keys())],
        "parenttype": "Uniform Allocation",
    }
    if employee:
        item_filters["employee"] = employee
    if department:
        item_filters["department"] = department

    items = frappe.get_all(
        "Uniform Allocation Item",
        filters=item_filters,
        fields=[
            "parent", "employee", "employee_name", "department",
            "item_code", "item_name", "qty", "issue_reason",
        ],
        order_by="parent desc, idx asc",
    )

    results = []
    for item in items:
        alloc = headers[item.parent]
        results.append({
            "allocation": alloc.name,
            "posting_date": alloc.posting_date,
            "allocation_type": alloc.allocation_type,
            "employee": item.employee,
            "employee_name": item.employee_name,
            "department": item.department,
            "item_code": item.item_code,
            "item_name": item.item_name,
            "qty": item.qty,
            "issue_reason": item.issue_reason,
            "stock_entry": alloc.stock_entry,
        })

    return results


@frappe.whitelist()
def get_uniform_cost_excel(group_by="department", from_date=None, to_date=None):
    """
    Return uniform issuance cost grouped by employee / department / period.
    Cost = qty × valuation_rate at time of Stock Entry.
    """
    _check_permission()

    conditions = ["sed.docstatus = 1", "sed.custom_uniform_allocation IS NOT NULL AND sed.custom_uniform_allocation != ''"]
    params = []

    if from_date:
        conditions.append("se.posting_date >= %s")
        params.append(from_date)
    if to_date:
        conditions.append("se.posting_date <= %s")
        params.append(to_date)

    where = " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT
            sed.custom_uniform_employee AS employee,
            sed.item_code,
            sed.qty,
            sed.valuation_rate,
            sed.qty * sed.valuation_rate AS cost,
            se.posting_date,
            sed.custom_uniform_allocation AS allocation,
            e.department,
            e.custom_group AS custom_group,
            e.employee_name
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        LEFT JOIN `tabEmployee` e ON e.name = sed.custom_uniform_employee
        WHERE {where}
        ORDER BY se.posting_date desc
        """,
        params,
        as_dict=True,
    )

    if group_by == "employee":
        summary = {}
        for r in rows:
            k = r.employee or "Unknown"
            if k not in summary:
                summary[k] = {"employee": k, "employee_name": r.employee_name, "total_cost": 0, "total_qty": 0}
            summary[k]["total_cost"] += flt(r.cost)
            summary[k]["total_qty"] += flt(r.qty)
        return list(summary.values())

    elif group_by == "department":
        summary = {}
        for r in rows:
            k = r.department or "Unknown"
            if k not in summary:
                summary[k] = {"department": k, "total_cost": 0, "total_qty": 0}
            summary[k]["total_cost"] += flt(r.cost)
            summary[k]["total_qty"] += flt(r.qty)
        return list(summary.values())

    elif group_by == "group":
        summary = {}
        for r in rows:
            k = r.custom_group or "Unknown"
            if k not in summary:
                summary[k] = {"custom_group": k, "total_cost": 0, "total_qty": 0}
            summary[k]["total_cost"] += flt(r.cost)
            summary[k]["total_qty"] += flt(r.qty)
        return list(summary.values())

    else:  # period (month)
        summary = {}
        for r in rows:
            k = str(r.posting_date)[:7]  # YYYY-MM
            if k not in summary:
                summary[k] = {"period": k, "total_cost": 0, "total_qty": 0}
            summary[k]["total_cost"] += flt(r.cost)
            summary[k]["total_qty"] += flt(r.qty)
        return list(summary.values())
