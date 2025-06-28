# fix_stock_ledger_custom_fields.py
# Utility script to fix existing Stock Ledger Entries with missing custom fields
# Run this script after implementing the new custom fields functionality

import frappe
from frappe import _
import json
from datetime import datetime, timedelta

def execute():
    """
    Main execution function to fix missing custom fields in Stock Ledger Entries
    """
    frappe.init()
    
    print("=" * 60)
    print("Stock Ledger Custom Fields Fix Utility")
    print("=" * 60)
    
    # Get user input for date range
    from_date = input("Enter from date (YYYY-MM-DD) or press Enter for last 30 days: ").strip()
    to_date = input("Enter to date (YYYY-MM-DD) or press Enter for today: ").strip()
    
    if not from_date:
        from_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    if not to_date:
        to_date = datetime.now().strftime('%Y-%m-%d')
    
    print(f"\nProcessing Stock Ledger Entries from {from_date} to {to_date}")
    
    # Import the fix function
    from customize_erpnext.api.stock_ledger.update_stock_ledger_invoice_number_receive_date import fix_missing_custom_fields_in_sle
    
    filters = {
        'from_date': from_date,
        'to_date': to_date
    }
    
    try:
        # Run the fix
        result = fix_missing_custom_fields_in_sle(filters)
        
        print("\n" + "=" * 40)
        print("RESULTS:")
        print("=" * 40)
        print(f"Total vouchers processed: {result['total_vouchers_processed']}")
        print(f"Successfully fixed: {result['successfully_fixed']}")
        
        if result['vouchers_processed']:
            print(f"\nProcessed vouchers:")
            for voucher in result['vouchers_processed'][:10]:  # Show first 10
                print(f"  - {voucher}")
            if len(result['vouchers_processed']) > 10:
                print(f"  ... and {len(result['vouchers_processed']) - 10} more")
        
        print(f"\nFix completed successfully!")
        
    except Exception as e:
        print(f"Error during fix process: {str(e)}")
        frappe.log_error(f"Custom fields fix error: {str(e)}", "Fix Stock Ledger Custom Fields")

def validate_custom_fields_status():
    """
    Function to validate current status of custom fields in Stock Ledger Entries
    """
    print("\n" + "=" * 50)
    print("VALIDATION REPORT")
    print("=" * 50)
    
    # Check if custom fields exist
    custom_fields_query = """
        SELECT 
            dt,
            fieldname,
            label,
            fieldtype
        FROM `tabCustom Field`
        WHERE dt = 'Stock Ledger Entry'
        AND fieldname IN ('custom_invoice_number', 'custom_receive_date')
        ORDER BY dt, fieldname
    """
    
    custom_fields = frappe.db.sql(custom_fields_query, as_dict=1)
    
    print("\n1. Custom Fields Status:")
    if custom_fields:
        for field in custom_fields:
            print(f"   ✓ {field.dt}: {field.fieldname} ({field.fieldtype})")
    else:
        print("   ❌ No custom fields found in Stock Ledger Entry")
        return
    
    # Check data coverage
    coverage_query = """
        SELECT 
            voucher_type,
            COUNT(*) as total_entries,
            COUNT(custom_invoice_number) as has_invoice,
            COUNT(custom_receive_date) as has_receive_date,
            ROUND(COUNT(custom_invoice_number) * 100.0 / COUNT(*), 2) as invoice_coverage_pct,
            ROUND(COUNT(custom_receive_date) * 100.0 / COUNT(*), 2) as receive_date_coverage_pct
        FROM `tabStock Ledger Entry`
        WHERE voucher_type IN ('Stock Entry', 'Stock Reconciliation')
        AND is_cancelled = 0
        AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAYS)
        GROUP BY voucher_type
        ORDER BY voucher_type
    """
    
    coverage_data = frappe.db.sql(coverage_query, as_dict=1)
    
    print("\n2. Data Coverage (Last 90 days):")
    if coverage_data:
        for data in coverage_data:
            print(f"   {data.voucher_type}:")
            print(f"     Total entries: {data.total_entries}")
            print(f"     Invoice coverage: {data.has_invoice}/{data.total_entries} ({data.invoice_coverage_pct}%)")
            print(f"     Receive date coverage: {data.has_receive_date}/{data.total_entries} ({data.receive_date_coverage_pct}%)")
    else:
        print("   No data found for analysis")
    
    # Check for inconsistencies
    from customize_erpnext.api.stock_ledger.update_stock_ledger_invoice_number_receive_date import validate_custom_fields_consistency
    
    print("\n3. Data Consistency Check:")
    inconsistencies = validate_custom_fields_consistency()
    
    if inconsistencies['stock_entry_issues']:
        print(f"   ❌ Found {len(inconsistencies['stock_entry_issues'])} Stock Entry inconsistencies")
    else:
        print("   ✓ Stock Entry data is consistent")
    
    if inconsistencies['stock_reconciliation_issues']:
        print(f"   ❌ Found {len(inconsistencies['stock_reconciliation_issues'])} Stock Reconciliation inconsistencies")
    else:
        print("   ✓ Stock Reconciliation data is consistent")

def interactive_menu():
    """
    Interactive menu for different operations
    """
    while True:
        print("\n" + "=" * 50)
        print("Stock Ledger Custom Fields Utility")
        print("=" * 50)
        print("1. Fix missing custom fields")
        print("2. Validate custom fields status")
        print("3. Show sample data")
        print("4. Exit")
        
        choice = input("\nSelect option (1-4): ").strip()
        
        if choice == '1':
            execute()
        elif choice == '2':
            validate_custom_fields_status()
        elif choice == '3':
            show_sample_data()
        elif choice == '4':
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please select 1-4.")

def show_sample_data():
    """
    Show sample data to verify custom fields
    """
    print("\n" + "=" * 40)
    print("SAMPLE DATA")
    print("=" * 40)
    
    sample_query = """
        SELECT 
            sle.voucher_type,
            sle.voucher_no,
            sle.item_code,
            sle.warehouse,
            sle.actual_qty,
            sle.custom_invoice_number,
            sle.custom_receive_date,
            sle.posting_date
        FROM `tabStock Ledger Entry` sle
        WHERE sle.voucher_type IN ('Stock Entry', 'Stock Reconciliation')
        AND sle.is_cancelled = 0
        AND (sle.custom_invoice_number IS NOT NULL OR sle.custom_receive_date IS NOT NULL)
        ORDER BY sle.posting_date DESC
        LIMIT 10
    """
    
    sample_data = frappe.db.sql(sample_query, as_dict=1)
    
    if sample_data:
        print(f"\nShowing {len(sample_data)} recent entries with custom fields:")
        print("-" * 120)
        print(f"{'Type':<15} {'Voucher':<15} {'Item':<15} {'Warehouse':<12} {'Qty':<8} {'Invoice':<12} {'Date':<12} {'Posted'}")
        print("-" * 120)
        
        for row in sample_data:
            print(f"{row.voucher_type:<15} {row.voucher_no:<15} {row.item_code:<15} {row.warehouse:<12} {row.actual_qty:<8} {(row.custom_invoice_number or ''):<12} {(str(row.custom_receive_date) if row.custom_receive_date else ''):<12} {row.posting_date}")
    else:
        print("No Stock Ledger Entries found with custom fields data")

if __name__ == "__main__":
    interactive_menu()