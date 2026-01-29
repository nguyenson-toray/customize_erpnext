import frappe
import json
import os
from datetime import datetime

def export_custom_fields_from_site(doctypes=None, output_file=None):
    """
    Export Custom Fields từ site hiện tại
    
    Args:
        doctypes (list, optional): Danh sách các DocType cần export Custom Fields
        output_file (str, optional): Đường dẫn file output. Nếu không chỉ định, sẽ tạo file với timestamp
    
    Returns:
        str: Đường dẫn đến file JSON đã export
    """
    # Tạo tên file mặc định nếu không được chỉ định
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"/tmp/custom_fields_{timestamp}.json"
    
    # Khởi tạo filters
    filters = {}
    if doctypes:
        filters["dt"] = ["in", doctypes]
    
    # Lấy tất cả Custom Fields theo filter
    custom_fields = frappe.get_all(
        "Custom Field",
        filters=filters,
        fields=["*"],
        order_by="dt, idx"
    )
    
    # Ghi dữ liệu vào file JSON
    with open(output_file, "w") as f:
        json.dump(custom_fields, f, indent=4)
    
    print(f"Đã export {len(custom_fields)} Custom Fields vào file {output_file}")
    return output_file

def import_custom_fields_to_site(input_file, update_existing=True):
    """
    Import Custom Fields từ file JSON vào site hiện tại
    
    Args:
        input_file (str): Đường dẫn đến file JSON chứa Custom Fields
        update_existing (bool): Cập nhật Custom Fields đã tồn tại nếu True
    
    Returns:
        tuple: (số lượng đã import, số lượng đã cập nhật, số lượng lỗi)
    """
    # Kiểm tra file tồn tại
    if not os.path.exists(input_file):
        print(f"Lỗi: File {input_file} không tồn tại!")
        return (0, 0, 0)
    
    # Đọc dữ liệu từ file JSON
    with open(input_file, "r") as f:
        custom_fields_data = json.load(f)
    
    imported_count = 0
    updated_count = 0
    error_count = 0
    
    # Import từng Custom Field
    for cf_data in custom_fields_data:
        try:
            # Bỏ qua các trường không cần thiết khi tạo/cập nhật
            if "name" in cf_data:
                cf_name = cf_data.pop("name")
            if "modified" in cf_data:
                cf_data.pop("modified")
            if "creation" in cf_data:
                cf_data.pop("creation")
            if "modified_by" in cf_data:
                cf_data.pop("modified_by")
            if "owner" in cf_data:
                cf_data.pop("owner")
            if "docstatus" in cf_data:
                cf_data.pop("docstatus")
            
            # Kiểm tra xem Custom Field đã tồn tại chưa
            existing = frappe.db.exists("Custom Field", {
                "dt": cf_data.get("dt"),
                "fieldname": cf_data.get("fieldname")
            })
            
            if existing and update_existing:
                # Cập nhật custom field hiện có
                cf = frappe.get_doc("Custom Field", existing)
                cf.update(cf_data)
                cf.save()
                updated_count += 1
                print(f" Đã cập nhật Custom Field: {cf_data.get('dt')}.{cf_data.get('fieldname')}")
            elif not existing:
                # Tạo custom field mới
                cf = frappe.new_doc("Custom Field")
                cf.update(cf_data)
                cf.insert()
                imported_count += 1
                print(f" Đã tạo Custom Field: {cf_data.get('dt')}.{cf_data.get('fieldname')}")
            else:
                print(f" Bỏ qua Custom Field đã tồn tại: {cf_data.get('dt')}.{cf_data.get('fieldname')}")
        
        except Exception as e:
            error_count += 1
            print(f"❌ Lỗi khi import {cf_data.get('dt')}.{cf_data.get('fieldname')}: {str(e)}")
    
    # Commit các thay đổi
    frappe.db.commit()
    
    print(f"\nTổng kết:")
    print(f"- Đã tạo mới: {imported_count} Custom Fields")
    print(f"- Đã cập nhật: {updated_count} Custom Fields")
    print(f"- Lỗi: {error_count} Custom Fields")
    
    return (imported_count, updated_count, error_count)

# Helper function để lấy danh sách DocTypes có Custom Fields
def get_doctypes_with_custom_fields():
    """Lấy danh sách các DocType có Custom Fields"""
    doctypes = frappe.db.sql("""
        SELECT DISTINCT dt FROM `tabCustom Field` ORDER BY dt
    """, as_dict=0)
    return [d[0] for d in doctypes]

def print_doctypes_with_custom_fields():
    """In danh sách các DocType có Custom Fields"""
    doctypes = get_doctypes_with_custom_fields()
    print(f"Có {len(doctypes)} DocTypes có Custom Fields:")
    for i, dt in enumerate(doctypes, 1):
        count = frappe.db.count("Custom Field", filters={"dt": dt})
        print(f"{i}. {dt} ({count} custom fields)")

# Hướng dẫn sử dụng
def print_usage():
    print("""
HƯỚNG DẪN SỬ DỤNG:

1. EXPORT TỪ SITE A:
   - Kết nối vào site A: bench --site site-a console
   - Dán toàn bộ script này vào console
   - Để xem danh sách DocTypes có Custom Fields:
     print_doctypes_with_custom_fields()
   - Export tất cả Custom Fields:
     export_custom_fields_from_site()
   - Export Custom Fields cho các DocTypes cụ thể:
     export_custom_fields_from_site(doctypes=["Sales Invoice", "Customer"])

2. IMPORT VÀO SITE B:
   - Kết nối vào site B: bench --site site-b console
   - Dán toàn bộ script này vào console
   - Import Custom Fields từ file đã export:
     import_custom_fields_to_site("/tmp/custom_fields_20240506_123045.json")
   - Để không cập nhật các Custom Fields hiện có:
     import_custom_fields_to_site("/tmp/custom_fields_20240506_123045.json", update_existing=False)

3. LÀM MỚI CACHE SAU KHI IMPORT:
   - Thoát khỏi console (gõ exit())
   - Chạy lệnh: bench --site site-b clear-cache
""")

# In hướng dẫn sử dụng
print_usage()