import frappe
from frappe import _
from collections import defaultdict

def update_stock_ledger_invoice_number(doc, method):
    """
    Enhanced update function with better mapping logic
    """
    if doc.doctype == "Stock Entry":
        update_from_stock_entry_enhanced(doc)
    elif doc.doctype == "Stock Reconciliation":
        update_from_stock_reconciliation_enhanced(doc)

def update_from_stock_entry_enhanced(stock_entry):
    """Enhanced Stock Entry processing with sequential mapping"""
    
    # Get Stock Ledger Entries in creation order
    stock_ledger_entries = frappe.db.sql("""
        SELECT name, item_code, warehouse, posting_date, posting_time, 
               actual_qty, qty_after_transaction, voucher_detail_no
        FROM `tabStock Ledger Entry`
        WHERE voucher_type = 'Stock Entry' 
        AND voucher_no = %s
        ORDER BY posting_date, posting_time, creation
    """, stock_entry.name, as_dict=1)
    
    # Create detailed mapping with quantities
    item_detail_map = defaultdict(list)
    
    for item in stock_entry.items:
        # Create entries for both source and target transactions
        if item.s_warehouse:  # Source warehouse (outgoing)
            item_detail_map[f"{item.item_code}_{item.s_warehouse}_out"].append({
                'invoice_number': item.custom_invoice_number,
                'qty': abs(item.qty),  # Outgoing quantity
                'idx': item.idx,
                'detail_name': item.name
            })
        
        if item.t_warehouse:  # Target warehouse (incoming)
            item_detail_map[f"{item.item_code}_{item.t_warehouse}_in"].append({
                'invoice_number': item.custom_invoice_number,
                'qty': abs(item.qty),  # Incoming quantity
                'idx': item.idx,
                'detail_name': item.name
            })
    
    # Process each Stock Ledger Entry
    for sle in stock_ledger_entries:
        invoice_number = None
        
        # Determine transaction type based on actual_qty
        transaction_type = "in" if sle.actual_qty > 0 else "out"
        map_key = f"{sle.item_code}_{sle.warehouse}_{transaction_type}"
        
        # Try to match with voucher_detail_no first (most accurate)
        if sle.voucher_detail_no:
            for item in stock_entry.items:
                if item.name == sle.voucher_detail_no:
                    invoice_number = item.custom_invoice_number
                    break
        
        # Fallback to sequential mapping if direct match not found
        if not invoice_number and map_key in item_detail_map:
            remaining_items = item_detail_map[map_key]
            if remaining_items:
                # Find best matching quantity
                sle_qty = abs(sle.actual_qty)
                best_match = None
                
                for item_data in remaining_items:
                    if abs(item_data['qty'] - sle_qty) < 0.001:  # Exact match
                        best_match = item_data
                        break
                
                if not best_match and remaining_items:
                    best_match = remaining_items[0]  # Take first available
                
                if best_match:
                    invoice_number = best_match['invoice_number']
                    remaining_items.remove(best_match)
        
        # Update Stock Ledger Entry
        if invoice_number:
            frappe.db.set_value(
                "Stock Ledger Entry",
                sle.name,
                "custom_invoice_number",
                invoice_number,
                update_modified=False
            )

def update_from_stock_reconciliation_enhanced(stock_reconciliation):
    """Enhanced Stock Reconciliation processing"""
    
    # Get Stock Ledger Entries with voucher_detail_no
    stock_ledger_entries = frappe.db.sql("""
        SELECT name, item_code, warehouse, actual_qty, voucher_detail_no
        FROM `tabStock Ledger Entry`
        WHERE voucher_type = 'Stock Reconciliation' 
        AND voucher_no = %s
        ORDER BY creation
    """, stock_reconciliation.name, as_dict=1)
    
    # Create mapping with detail names
    detail_invoice_map = {}
    sequential_map = defaultdict(list)
    
    for item in stock_reconciliation.items:
        detail_invoice_map[item.name] = item.custom_invoice_number
        
        # Also create sequential mapping as backup
        key = f"{item.item_code}_{item.warehouse}"
        sequential_map[key].append({
            'invoice_number': item.custom_invoice_number,
            'idx': item.idx,
            'detail_name': item.name
        })
    
    # Update Stock Ledger Entries
    for sle in stock_ledger_entries:
        invoice_number = None
        
        # Try direct mapping with voucher_detail_no
        if sle.voucher_detail_no and sle.voucher_detail_no in detail_invoice_map:
            invoice_number = detail_invoice_map[sle.voucher_detail_no]
        
        # Fallback to sequential mapping
        if not invoice_number:
            key = f"{sle.item_code}_{sle.warehouse}"
            if key in sequential_map and sequential_map[key]:
                item_data = sequential_map[key].pop(0)
                invoice_number = item_data['invoice_number']
        
        # Update if invoice number found
        if invoice_number:
            frappe.db.set_value(
                "Stock Ledger Entry",
                sle.name,
                "custom_invoice_number",
                invoice_number,
                update_modified=False
            )

# Custom query function for Stock Balance report with invoice number support

def get_stock_balance_with_invoice(filters):
    """
    Custom function to get accurate stock balance by invoice number
    """
    conditions = []
    values = []
    
    if filters.get('item_code'):
        conditions.append("sle.item_code = %s")
        values.append(filters['item_code'])
    
    if filters.get('warehouse'):
        conditions.append("sle.warehouse = %s")
        values.append(filters['warehouse'])
    
    if filters.get('from_date'):
        conditions.append("sle.posting_date >= %s")
        values.append(filters['from_date'])
    
    if filters.get('to_date'):
        conditions.append("sle.posting_date <= %s")
        values.append(filters['to_date'])
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    query = f"""
        SELECT 
            sle.item_code,
            sle.warehouse,
            sle.custom_invoice_number,
            SUM(sle.actual_qty) as balance_qty,
            SUM(CASE WHEN sle.actual_qty > 0 THEN sle.actual_qty ELSE 0 END) as in_qty,
            SUM(CASE WHEN sle.actual_qty < 0 THEN ABS(sle.actual_qty) ELSE 0 END) as out_qty,
            MAX(sle.qty_after_transaction) as qty_after_transaction
        FROM `tabStock Ledger Entry` sle
        WHERE {where_clause}
        AND sle.is_cancelled = 0
        GROUP BY sle.item_code, sle.warehouse, sle.custom_invoice_number
        HAVING balance_qty != 0
        ORDER BY sle.item_code, sle.warehouse, sle.custom_invoice_number
    """
    
    return frappe.db.sql(query, values, as_dict=1)

# Validation function to check data consistency

def validate_invoice_balance_consistency():
    """
    Validation function to check if invoice-level balances match item totals
    """
    validation_query = """
        WITH invoice_balances AS (
            SELECT 
                item_code,
                warehouse,
                custom_invoice_number,
                SUM(actual_qty) as invoice_balance
            FROM `tabStock Ledger Entry`
            WHERE is_cancelled = 0
            AND custom_invoice_number IS NOT NULL
            GROUP BY item_code, warehouse, custom_invoice_number
        ),
        item_totals AS (
            SELECT 
                item_code,
                warehouse,
                SUM(actual_qty) as total_balance
            FROM `tabStock Ledger Entry`
            WHERE is_cancelled = 0
            GROUP BY item_code, warehouse
        ),
        invoice_totals AS (
            SELECT 
                item_code,
                warehouse,
                SUM(invoice_balance) as invoice_sum
            FROM invoice_balances
            GROUP BY item_code, warehouse
        )
        SELECT 
            it.item_code,
            it.warehouse,
            it.total_balance,
            COALESCE(int.invoice_sum, 0) as invoice_sum,
            (it.total_balance - COALESCE(int.invoice_sum, 0)) as difference
        FROM item_totals it
        LEFT JOIN invoice_totals int ON it.item_code = int.item_code AND it.warehouse = int.warehouse
        WHERE ABS(it.total_balance - COALESCE(int.invoice_sum, 0)) > 0.001
    """
    
    inconsistencies = frappe.db.sql(validation_query, as_dict=1)
    
    if inconsistencies:
        frappe.log_error(
            f"Invoice balance inconsistencies found: {inconsistencies}",
            "Stock Balance Validation"
        )
    
    return inconsistencies