import frappe
from frappe import _
from collections import defaultdict
import json

def update_stock_ledger_invoice_number_receive_date(doc, method):
    """
    Enhanced update function to handle both custom_invoice_number and custom_receive_date
    """
    if doc.doctype == "Stock Entry":
        update_from_stock_entry_enhanced(doc)
    elif doc.doctype == "Stock Reconciliation":
        update_from_stock_reconciliation_enhanced(doc)

def update_from_stock_entry_enhanced(stock_entry):
    """Enhanced Stock Entry processing with sequential mapping for both fields"""
    
    # Get Stock Ledger Entries in creation order
    stock_ledger_entries = frappe.db.sql("""
        SELECT name, item_code, warehouse, posting_date, posting_time, 
               actual_qty, qty_after_transaction, voucher_detail_no
        FROM `tabStock Ledger Entry`
        WHERE voucher_type = 'Stock Entry' 
        AND voucher_no = %s
        ORDER BY posting_date, posting_time, creation
    """, stock_entry.name, as_dict=1)
    
    # Create detailed mapping with quantities and both custom fields
    item_detail_map = defaultdict(list)
    
    for item in stock_entry.items:
        # Prepare data for both fields
        item_data = {
            'invoice_number': getattr(item, 'custom_invoice_number', None),
            'receive_date': getattr(item, 'custom_receive_date', None),
            'qty': abs(item.qty),
            'idx': item.idx,
            'detail_name': item.name
        }
        
        # Create entries for both source and target transactions
        if item.s_warehouse:  # Source warehouse (outgoing)
            item_detail_map[f"{item.item_code}_{item.s_warehouse}_out"].append({
                **item_data,
                'qty': abs(item.qty)  # Outgoing quantity
            })
        
        if item.t_warehouse:  # Target warehouse (incoming)
            item_detail_map[f"{item.item_code}_{item.t_warehouse}_in"].append({
                **item_data,
                'qty': abs(item.qty)  # Incoming quantity
            })
    
    # Process each Stock Ledger Entry
    updates_to_process = []
    
    for sle in stock_ledger_entries:
        invoice_number = None
        receive_date = None
        
        # Determine transaction type based on actual_qty
        transaction_type = "in" if sle.actual_qty > 0 else "out"
        map_key = f"{sle.item_code}_{sle.warehouse}_{transaction_type}"
        
        # Try to match with voucher_detail_no first (most accurate)
        if sle.voucher_detail_no:
            for item in stock_entry.items:
                if item.name == sle.voucher_detail_no:
                    invoice_number = getattr(item, 'custom_invoice_number', None)
                    receive_date = getattr(item, 'custom_receive_date', None)
                    break
        
        # Fallback to sequential mapping if direct match not found
        if not invoice_number and not receive_date and map_key in item_detail_map:
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
                    receive_date = best_match['receive_date']
                    remaining_items.remove(best_match)
        
        # Prepare update data
        update_data = {}
        if invoice_number:
            update_data['custom_invoice_number'] = invoice_number
        if receive_date:
            update_data['custom_receive_date'] = receive_date
        
        # Add custom_is_opening_stock field from Stock Entry
        if hasattr(stock_entry, 'custom_is_opening_stock'):
            update_data['custom_is_opening_stock'] = stock_entry.custom_is_opening_stock
        else:
            update_data['custom_is_opening_stock'] = 0  # Default to 0 if not present
            
        if update_data:
            updates_to_process.append({
                'sle_name': sle.name,
                'update_data': update_data
            })
    
    # Batch update Stock Ledger Entries
    if updates_to_process:
        batch_update_stock_ledger_entries(updates_to_process)

def update_from_stock_reconciliation_enhanced(stock_reconciliation):
    """Enhanced Stock Reconciliation processing for both fields"""
    
    # Get Stock Ledger Entries with voucher_detail_no
    stock_ledger_entries = frappe.db.sql("""
        SELECT name, item_code, warehouse, actual_qty, voucher_detail_no
        FROM `tabStock Ledger Entry`
        WHERE voucher_type = 'Stock Reconciliation' 
        AND voucher_no = %s
        ORDER BY creation
    """, stock_reconciliation.name, as_dict=1)
    
    # Create mapping with detail names and both custom fields
    detail_field_map = {}
    sequential_map = defaultdict(list)
    
    for item in stock_reconciliation.items:
        # Store both fields for each detail
        detail_field_map[item.name] = {
            'invoice_number': getattr(item, 'custom_invoice_number', None),
            'receive_date': getattr(item, 'custom_receive_date', None)
        }
        
        # Also create sequential mapping as backup
        key = f"{item.item_code}_{item.warehouse}"
        sequential_map[key].append({
            'invoice_number': getattr(item, 'custom_invoice_number', None),
            'receive_date': getattr(item, 'custom_receive_date', None),
            'idx': item.idx,
            'detail_name': item.name
        })
    
    # Prepare updates
    updates_to_process = []
    
    # Update Stock Ledger Entries
    for sle in stock_ledger_entries:
        invoice_number = None
        receive_date = None
        
        # Try direct mapping with voucher_detail_no
        if sle.voucher_detail_no and sle.voucher_detail_no in detail_field_map:
            field_data = detail_field_map[sle.voucher_detail_no]
            invoice_number = field_data['invoice_number']
            receive_date = field_data['receive_date']
        
        # Fallback to sequential mapping
        if not invoice_number and not receive_date:
            key = f"{sle.item_code}_{sle.warehouse}"
            if key in sequential_map and sequential_map[key]:
                item_data = sequential_map[key].pop(0)
                invoice_number = item_data['invoice_number']
                receive_date = item_data['receive_date']
        
        # Prepare update data
        update_data = {}
        if invoice_number:
            update_data['custom_invoice_number'] = invoice_number
        if receive_date:
            update_data['custom_receive_date'] = receive_date
        
        # Add custom_is_opening_stock field (always 0 for Stock Reconciliation)
        update_data['custom_is_opening_stock'] = 0
            
        if update_data:
            updates_to_process.append({
                'sle_name': sle.name,
                'update_data': update_data
            })
    
    # Batch update Stock Ledger Entries
    if updates_to_process:
        batch_update_stock_ledger_entries(updates_to_process)

def batch_update_stock_ledger_entries(updates_to_process):
    """
    Batch update Stock Ledger Entries for better performance
    """
    try:
        for update_item in updates_to_process:
            sle_name = update_item['sle_name']
            update_data = update_item['update_data']
            
            # Build SET clause dynamically
            set_clauses = []
            values = []
            
            for field, value in update_data.items():
                if value is not None:
                    set_clauses.append(f"{field} = %s")
                    values.append(value)
                else:
                    set_clauses.append(f"{field} = NULL")
            
            if set_clauses:
                values.append(sle_name)  # Add name for WHERE clause
                
                query = f"""
                    UPDATE `tabStock Ledger Entry`
                    SET {', '.join(set_clauses)}
                    WHERE name = %s
                """
                
                frappe.db.sql(query, values)
        
        # Commit all updates at once
        frappe.db.commit()
        
        frappe.logger().info(f"Successfully updated {len(updates_to_process)} Stock Ledger Entries with custom fields")
        
    except Exception as e:
        frappe.log_error(
            message=f"Error updating Stock Ledger Entries: {str(e)}",
            title="Stock Ledger Custom Fields Update Error"
        )
        frappe.throw(_("Error updating Stock Ledger Entries: {0}").format(str(e)))

# Enhanced query function for Stock Balance report with both custom fields

def get_stock_balance_with_custom_fields(filters):
    """
    Custom function to get accurate stock balance by invoice number and receive date
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
    
    if filters.get('custom_invoice_number'):
        conditions.append("sle.custom_invoice_number = %s")
        values.append(filters['custom_invoice_number'])
    
    if filters.get('custom_receive_date'):
        conditions.append("sle.custom_receive_date = %s")
        values.append(filters['custom_receive_date'])
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    query = f"""
        SELECT 
            sle.item_code,
            sle.warehouse,
            sle.custom_invoice_number,
            sle.custom_receive_date,
            SUM(sle.actual_qty) as balance_qty,
            SUM(CASE WHEN sle.actual_qty > 0 THEN sle.actual_qty ELSE 0 END) as in_qty,
            SUM(CASE WHEN sle.actual_qty < 0 THEN ABS(sle.actual_qty) ELSE 0 END) as out_qty,
            MAX(sle.qty_after_transaction) as qty_after_transaction,
            COUNT(*) as transaction_count,
            MIN(sle.posting_date) as first_transaction_date,
            MAX(sle.posting_date) as last_transaction_date
        FROM `tabStock Ledger Entry` sle
        WHERE {where_clause}
        AND sle.is_cancelled = 0
        GROUP BY sle.item_code, sle.warehouse, sle.custom_invoice_number, sle.custom_receive_date
        HAVING balance_qty != 0
        ORDER BY sle.item_code, sle.warehouse, sle.custom_invoice_number, sle.custom_receive_date
    """
    
    return frappe.db.sql(query, values, as_dict=1)

# Enhanced validation function to check data consistency

def validate_custom_fields_consistency():
    """
    Validation function to check if custom fields are properly mapped
    """
    # Check Stock Entry consistency
    stock_entry_validation = """
        SELECT DISTINCT
            se.name as stock_entry,
            sei.item_code,
            sei.s_warehouse,
            sei.t_warehouse,
            sei.custom_invoice_number as entry_invoice,
            sei.custom_receive_date as entry_receive_date,
            COUNT(DISTINCT sle.custom_invoice_number) as distinct_sle_invoices,
            COUNT(DISTINCT sle.custom_receive_date) as distinct_sle_receive_dates
        FROM `tabStock Entry` se
        INNER JOIN `tabStock Entry Detail` sei ON se.name = sei.parent
        INNER JOIN `tabStock Ledger Entry` sle ON se.name = sle.voucher_no 
            AND sle.voucher_type = 'Stock Entry'
            AND (
                (sei.s_warehouse = sle.warehouse AND sle.actual_qty < 0) OR
                (sei.t_warehouse = sle.warehouse AND sle.actual_qty > 0)
            )
        WHERE se.docstatus = 1
        GROUP BY se.name, sei.item_code, sei.s_warehouse, sei.t_warehouse, sei.custom_invoice_number, sei.custom_receive_date
        HAVING distinct_sle_invoices > 1 OR distinct_sle_receive_dates > 1
    """
    
    # Check Stock Reconciliation consistency
    stock_recon_validation = """
        SELECT DISTINCT
            sr.name as stock_reconciliation,
            sri.item_code,
            sri.warehouse,
            sri.custom_invoice_number as recon_invoice,
            sri.custom_receive_date as recon_receive_date,
            COUNT(DISTINCT sle.custom_invoice_number) as distinct_sle_invoices,
            COUNT(DISTINCT sle.custom_receive_date) as distinct_sle_receive_dates
        FROM `tabStock Reconciliation` sr
        INNER JOIN `tabStock Reconciliation Item` sri ON sr.name = sri.parent
        INNER JOIN `tabStock Ledger Entry` sle ON sr.name = sle.voucher_no 
            AND sle.voucher_type = 'Stock Reconciliation'
            AND sri.item_code = sle.item_code
            AND sri.warehouse = sle.warehouse
        WHERE sr.docstatus = 1
        GROUP BY sr.name, sri.item_code, sri.warehouse, sri.custom_invoice_number, sri.custom_receive_date
        HAVING distinct_sle_invoices > 1 OR distinct_sle_receive_dates > 1
    """
    
    stock_entry_issues = frappe.db.sql(stock_entry_validation, as_dict=1)
    stock_recon_issues = frappe.db.sql(stock_recon_validation, as_dict=1)
    
    inconsistencies = {
        'stock_entry_issues': stock_entry_issues,
        'stock_reconciliation_issues': stock_recon_issues
    }
    
    if stock_entry_issues or stock_recon_issues:
        frappe.log_error(
            message=f"Custom fields mapping inconsistencies found: {json.dumps(inconsistencies, indent=2, default=str)}",
            title="Custom Fields Validation"
        )
    
    return inconsistencies

# Utility function to fix missing custom fields in existing SLEs

def fix_missing_custom_fields_in_sle(filters=None):
    """
    Utility function to retroactively update Stock Ledger Entries with missing custom fields
    """
    if not filters:
        filters = {}
    
    conditions = []
    values = []
    
    if filters.get('from_date'):
        conditions.append("posting_date >= %s")
        values.append(filters['from_date'])
    
    if filters.get('to_date'):
        conditions.append("posting_date <= %s")
        values.append(filters['to_date'])
    
    if filters.get('voucher_type'):
        conditions.append("voucher_type = %s")
        values.append(filters['voucher_type'])
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    # Get SLEs that might be missing custom fields
    sle_query = f"""
        SELECT DISTINCT voucher_no, voucher_type
        FROM `tabStock Ledger Entry`
        WHERE {where_clause}
        AND is_cancelled = 0
        AND voucher_type IN ('Stock Entry', 'Stock Reconciliation')
        AND (custom_invoice_number IS NULL OR custom_receive_date IS NULL)
        ORDER BY voucher_type, voucher_no
    """
    
    vouchers_to_fix = frappe.db.sql(sle_query, values, as_dict=1)
    
    fixed_count = 0
    for voucher in vouchers_to_fix:
        try:
            # Get the original document
            doc = frappe.get_doc(voucher.voucher_type, voucher.voucher_no)
            
            # Reprocess with our enhanced function
            update_stock_ledger_invoice_number_receive_date(doc, 'on_submit')
            fixed_count += 1
            
        except Exception as e:
            frappe.log_error(
                message=f"Error fixing custom fields for {voucher.voucher_type} {voucher.voucher_no}: {str(e)}",
                title="Custom Fields Fix Error"
            )
    
    return {
        'total_vouchers_processed': len(vouchers_to_fix),
        'successfully_fixed': fixed_count,
        'vouchers_processed': [v.voucher_no for v in vouchers_to_fix]
    }