# Tạo file mới: customize_erpnext/customize_erpnext/override_methods/stock_entry.py

import frappe

@frappe.whitelist()
def check_existing_stock_entry(work_order, current_stock_entry=None):
    """
    Kiểm tra xem đã có Stock Entry nào cho Work Order này chưa
    
    Args:
        work_order: Work Order cần kiểm tra
        current_stock_entry: Stock Entry hiện tại (để loại trừ khỏi kết quả kiểm tra)
    
    Returns:
        dict: {'exists': True/False, 'stock_entry': 'SEXXXX'} 
    """
    if not work_order:
        return {'exists': False}
    
    # Lọc điều kiện
    filters = {
        "work_order": work_order,
        "docstatus": 0,  # Draft
        "stock_entry_type": "Material Transfer for Manufacture"
    }
    
    # Loại trừ Stock Entry hiện tại nếu có
    if current_stock_entry:
        filters["name"] = ["!=", current_stock_entry]
    
    # Tìm kiếm Stock Entry
    existing_entries = frappe.get_all(
        "Stock Entry",
        filters=filters,
        fields=["name"],
        limit=1
    )
    
    if existing_entries:
        return {
            'exists': True,
            'stock_entry': existing_entries[0].name
        }
    else:
        return {'exists': False}