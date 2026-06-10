"""Public (guest) API to expose Stock Balance Customize for Excel / Power Query.

Endpoint (GET, no authentication):
    /api/method/customize_erpnext.api.stock.stock_balance_api.get_stock_balance

Returns the same rows as the "Stock Balance Customize" report, as a JSON array of
records keyed by the report's column labels (Power-Query friendly).

SECURITY: allow_guest=True exposes stock data without login. Restrict access at the
network/proxy level (VPN, firewall, IP allow-list) if the data is sensitive.
"""

import frappe
from frappe.utils import getdate, today

from customize_erpnext.customize_erpnext.report.stock_balance_customize.stock_balance_customize import (
    execute as run_stock_balance,
)


def _as_bool(value, default):
    if value is None or value == "":
        return 1 if default else 0
    if isinstance(value, bool):
        return 1 if value else 0
    return 1 if str(value).strip().lower() in ("1", "true", "yes", "y", "on") else 0


def _default_from_date():
    """Fiscal year start (01-04): current year if month in [4..12], else previous year."""
    d = getdate(today())
    year = d.year if d.month >= 4 else d.year - 1
    return f"{year}-04-01"


def _default_company():
    return (
        frappe.db.get_single_value("Global Defaults", "default_company")
        or frappe.defaults.get_global_default("company")
    )


def _to_records(columns, data):
    """Flatten report rows into records keyed by column label (ordered)."""
    cols = [(c.get("fieldname"), c.get("label")) for c in columns if c.get("fieldname")]
    records = []
    for row in data:
        records.append({label: row.get(fieldname) for fieldname, label in cols})
    return records


@frappe.whitelist(allow_guest=True)
def get_stock_balance(
    from_date=None,
    to_date=None,
    warehouse=None,
    item_group=None,
    show_variant_attributes=None,
    summary_qty_by_invoice_number=None,
    group_by_batch=None,
    show_stock_ageing_data=None,
    include_zero_stock_items=None,
    company=None,
):
    """Run Stock Balance Customize and return Power-Query friendly records.

    Defaults: from_date = fiscal-year start (01/04), to_date = today, warehouse/item_group = all,
    show_variant_attributes = True, group by invoice = True, group by batch = True,
    show_stock_ageing_data = False, include_zero_stock_items = True.
    """
    filters = {
        "company": company or _default_company(),
        "from_date": from_date or _default_from_date(),
        "to_date": to_date or today(),
        "show_variant_attributes": _as_bool(show_variant_attributes, True),
        "summary_qty_by_invoice_number": _as_bool(summary_qty_by_invoice_number, True),
        "group_by_batch": _as_bool(group_by_batch, True),
        "show_stock_ageing_data": _as_bool(show_stock_ageing_data, False),
        "include_zero_stock_items": _as_bool(include_zero_stock_items, True),
    }
    if warehouse:
        filters["warehouse"] = warehouse
    if item_group:
        filters["item_group"] = item_group

    columns, data = run_stock_balance(filters)
    return _to_records(columns, data)
