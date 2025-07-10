import frappe
from frappe import _
from frappe.utils import flt, getdate

@frappe.whitelist()
def get_stock_by_invoice(item_code, warehouse=None, company=None):
    """Get available stock grouped by invoice number for a specific item"""
    
    if not item_code:
        return []
    
    conditions = ["sle.item_code = %(item_code)s"]
    params = {"item_code": item_code}
    
    if warehouse:
        conditions.append("sle.warehouse = %(warehouse)s")
        params["warehouse"] = warehouse
    
    if company:
        conditions.append("sle.company = %(company)s")
        params["company"] = company
    
    # Query to get stock balance by invoice
    query = """
        SELECT 
            sle.item_code,
            COALESCE(sed.custom_invoice_number, sri.custom_invoice_number) as invoice_number,
            sle.warehouse,
            item.custom_item_name_detail,
            MIN(CASE 
                WHEN sle.voucher_type = 'Stock Reconciliation' THEN sri.custom_receive_date
                WHEN sle.voucher_type = 'Stock Entry' THEN COALESCE(sed.custom_receive_date, se.posting_date)
                ELSE sle.posting_date 
            END) as receive_date,
            SUM(
                CASE
                    WHEN sle.voucher_type = 'Stock Reconciliation' THEN sri.qty -- Use qty from Stock Reconciliation Item
                    ELSE sle.actual_qty
                END
            ) as available_qty,
            item.stock_uom
        FROM `tabStock Ledger Entry` sle
        INNER JOIN `tabItem` item ON sle.item_code = item.name
        LEFT JOIN `tabStock Entry Detail` sed 
            ON sle.voucher_no = sed.parent 
            AND sle.item_code = sed.item_code
            AND sle.voucher_type = 'Stock Entry'
            AND sle.voucher_detail_no = sed.name
        LEFT JOIN `tabStock Entry` se
            ON sle.voucher_no = se.name
            AND sle.voucher_type = 'Stock Entry'
        LEFT JOIN `tabStock Reconciliation Item` sri
            ON sle.voucher_no = sri.parent
            AND sle.item_code = sri.item_code
            AND sle.warehouse = sri.warehouse
            AND sle.voucher_type = 'Stock Reconciliation'
            AND sle.voucher_detail_no = sri.name -- Added to ensure correct join for Stock Reconciliation Item
        WHERE 
            {conditions}
            AND sle.is_cancelled = 0
            AND (sed.custom_invoice_number IS NOT NULL OR sri.custom_invoice_number IS NOT NULL)
        GROUP BY 
            sle.item_code,
            COALESCE(sed.custom_invoice_number, sri.custom_invoice_number),
            sle.warehouse
        HAVING 
            available_qty > 0
        ORDER BY 
            receive_date ASC
    """.format(conditions=" AND ".join(conditions)) 
    result = frappe.db.sql(query, params, as_dict=True) 
    # Format the results
    for row in result:
        row["available_qty"] = flt(row["available_qty"], 3)
        if row["receive_date"]:
            row["receive_date"] = getdate(row["receive_date"])
    
    return result