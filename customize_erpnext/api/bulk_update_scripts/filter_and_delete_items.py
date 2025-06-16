# file: custom_features/custom_features/bulk_update_scripts/filter_and_delete_items.py
import frappe

def filter_and_delete_items(filters=None):
    """
    Lọc và xóa các item dựa trên các điều kiện lọc
    
    Params:
        filters (dict): Điều kiện lọc, ví dụ: {"item_group": ["like", "%3.%"]}
    """
    if not filters:
        print("Không có điều kiện lọc được cung cấp")
        return
    
    # Lấy danh sách các item theo điều kiện lọc
    items = frappe.get_all(
        "Item",
        filters=filters,
        fields=["name", "item_name", "item_group"]
    )
    
    if not items:
        print(f"Không tìm thấy item nào thỏa mãn điều kiện: {filters}")
        return
    
    print(f"Tìm thấy {len(items)} item thỏa mãn điều kiện:")
    for i, item in enumerate(items):
        print(f"{i+1}. {item.name} - {item.item_name} ({item.item_group})")
    
    confirmation = input(f"\nBạn có chắc chắn muốn xóa {len(items)} item này? (yes/no): ")
    if confirmation.lower() not in ['yes', 'y']:
        print("Đã hủy thao tác xóa")
        return
    
    # Thực hiện xóa
    count = 0
    for item in items:
        try:
            frappe.delete_doc("Item", item.name, force=1)
            count += 1
            print(f"Đã xóa: {item.name} - {item.item_name}")
        except Exception as e:
            print(f"Lỗi khi xóa {item.name}: {str(e)}")
    
    frappe.db.commit()
    print(f"Đã xóa thành công {count}/{len(items)} item")

def delete_specific_items(item_codes):
    """
    Xóa các item theo mã cụ thể
    
    Params:
        item_codes (list): Danh sách mã item cần xóa
    """
    if not item_codes:
        print("Không có item nào được chỉ định để xóa")
        return
    
    # Kiểm tra xem các item có tồn tại không
    existing_items = []
    for item_code in item_codes:
        if frappe.db.exists("Item", item_code):
            item_name = frappe.db.get_value("Item", item_code, "item_name")
            existing_items.append({"code": item_code, "name": item_name})
        else:
            print(f"Item {item_code} không tồn tại")
    
    if not existing_items:
        print("Không có item nào tồn tại để xóa")
        return
    
    print(f"Chuẩn bị xóa {len(existing_items)} item:")
    for i, item in enumerate(existing_items):
        print(f"{i+1}. {item['code']} - {item['name']}")
    
    confirmation = input(f"\nBạn có chắc chắn muốn xóa {len(existing_items)} item này? (yes/no): ")
    if confirmation.lower() not in ['yes', 'y']:
        print("Đã hủy thao tác xóa")
        return
    
    # Thực hiện xóa
    count = 0
    for item in existing_items:
        try:
            frappe.delete_doc("Item", item['code'], force=1)
            count += 1
            print(f"Đã xóa: {item['code']} - {item['name']}")
        except Exception as e:
            print(f"Lỗi khi xóa {item['code']}: {str(e)}")
    
    frappe.db.commit()
    print(f"Đã xóa thành công {count}/{len(existing_items)} item")


    '''
   bench --site erp-sonnt.tiqn.local console
   import customize_erpnext.api.bulk_update_scripts.filter_and_delete_items as delete_script
delete_script.filter_and_delete_items({"item_group": ["like", "%C%"]})

delete_script.filter_and_delete_items({"item_group": "01 - Finished Goods"})
# Lọc item có item_group chứa "3.%" và không có variants
delete_script.filter_and_delete_items({"item_group": ["like", "%3.%"], "has_variants": 0 })
delete_script.filter_and_delete_items({"item_group": "01 - Finished Goods", "has_variants": 0 })
delete_script.filter_and_delete_items({"item_group": ["like", "%C%"]})
    '''



    