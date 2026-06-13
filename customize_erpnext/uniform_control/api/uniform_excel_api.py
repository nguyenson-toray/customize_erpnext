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
    Return current stock of all uniform variants at the Uniform warehouse,
    with reorder levels and low-stock flag.
    """
    _check_permission()

    warehouse = frappe.db.get_single_value("Uniform Setting", "uniform_warehouse")
    if not warehouse:
        return []

    filters = {"warehouse": warehouse}
    if item_template:
        # Get all variants of this template
        variants = frappe.get_all(
            "Item", filters={"variant_of": item_template, "disabled": 0}, pluck="name"
        )
        filters["item_code"] = ["in", variants] if variants else ["in", [item_template]]

    bins = frappe.get_all(
        "Bin",
        filters=filters,
        fields=["item_code", "actual_qty", "reserved_qty", "ordered_qty"],
        order_by="item_code asc",
    )

    results = []
    for b in bins:
        item = frappe.db.get_value(
            "Item", b.item_code,
            ["item_name", "variant_of", "valuation_rate"],
            as_dict=True,
        ) or {}

        # Get reorder level
        reorder = frappe.db.get_value(
            "Item Reorder",
            {"parent": b.item_code, "warehouse": warehouse},
            ["warehouse_reorder_level", "warehouse_reorder_qty"],
            as_dict=True,
        ) or {}

        reorder_level = flt(reorder.get("warehouse_reorder_level"))
        low_stock = 1 if b.actual_qty <= reorder_level and reorder_level > 0 else 0

        results.append({
            "item_code": b.item_code,
            "item_name": item.get("item_name"),
            "template": item.get("variant_of") or b.item_code,
            "actual_qty": flt(b.actual_qty),
            "reserved_qty": flt(b.reserved_qty),
            "reorder_level": reorder_level,
            "reorder_qty": flt(reorder.get("warehouse_reorder_qty")),
            "valuation_rate": flt(item.get("valuation_rate")),
            "stock_value": flt(b.actual_qty) * flt(item.get("valuation_rate")),
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

    else:  # period (month)
        summary = {}
        for r in rows:
            k = str(r.posting_date)[:7]  # YYYY-MM
            if k not in summary:
                summary[k] = {"period": k, "total_cost": 0, "total_qty": 0}
            summary[k]["total_cost"] += flt(r.cost)
            summary[k]["total_qty"] += flt(r.qty)
        return list(summary.values())
