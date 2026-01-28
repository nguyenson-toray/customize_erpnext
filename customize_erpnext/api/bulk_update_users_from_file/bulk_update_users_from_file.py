# Python Console Script - Bulk User Update từ File
# Chạy trong ERPNext Console

import frappe
import os
from frappe.utils import formatdate

def bulk_update_users_from_file(file_path=None):
    """
    Cập nhật hàng loạt users từ file user_list.txt cùng thư mục
    """
    
    # Tự động tìm file user_list.txt cùng thư mục
    if file_path is None:
        # Lấy thư mục hiện tại
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
        except:
            # Khi chạy trong console, __file__ không tồn tại
            current_dir = frappe.get_site_path()
        
        file_path = os.path.join(current_dir, 'user_list.txt')
        print(f"📂 Tự động tìm file: {file_path}")
    
    # Kiểm tra file tồn tại
    if not os.path.exists(file_path):
        print(f"❌ File không tồn tại: {file_path}")
        print(f"💡 Hãy tạo file user_list.txt trong thư mục: {os.path.dirname(file_path)}")
        return
    
    # Đọc danh sách User ID từ file
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            user_ids = [line.strip() for line in file.readlines() if line.strip()]
    except Exception as e:
        print(f"❌ Lỗi đọc file: {str(e)}")
        return
    
    if not user_ids:
        print(f"❌ File rỗng!")
        return
        
    print(f"📝 Đọc được {len(user_ids)} User ID từ file")
    print("=" * 60)
    
    # Counters
    success_count = 0
    error_count = 0
    errors = []
    
    # Lấy tất cả modules
    try:
        all_modules = frappe.get_all("Module Def", fields=["name"])
        module_names = [m.name for m in all_modules]
        
        print(f"📦 Tìm thấy {len(all_modules)} modules")
        if "TIQN App" in module_names:
            print(f"✅ Module 'TIQN App' có sẵn")
        else:
            print(f"⚠️  Module 'TIQN App' KHÔNG có!")
            
    except Exception as e:
        print(f"❌ Lỗi lấy modules: {str(e)}")
        return
    
    print("=" * 60)
    
    # Xử lý từng User
    for i, user_id in enumerate(user_ids, 1):
        try:
            print(f"\n🔄 [{i}/{len(user_ids)}] User: {user_id}")
            
            # Kiểm tra User tồn tại
            if not frappe.db.exists("User", user_id):
                error_msg = f"User không tồn tại: {user_id}"
                print(f"❌ {error_msg}")
                errors.append(error_msg)
                error_count += 1
                continue
            
            # Lấy User document
            user_doc = frappe.get_doc("User", user_id)
            
            # === 1. TÌM EMPLOYEE VÀ TẠO PASSWORD ===
            employee = None
            if user_doc.email:
                # Tìm Employee theo email
                employees = frappe.get_all("Employee", 
                                         filters={"company_email": user_doc.email}, 
                                         fields=["name", "date_of_birth"])
                if not employees:
                    employees = frappe.get_all("Employee", 
                                             filters={"personal_email": user_doc.email}, 
                                             fields=["name", "date_of_birth"])
                if employees:
                    employee = employees[0]
                    print(f"  👤 Employee: {employee.name}")
                    
            # Tạo password
            if employee and employee.date_of_birth:
                emp_id_proper = employee.name.title()  # PROPER
                dob_formatted = formatdate(employee.date_of_birth, "ddMM")  # ddmm
                new_password = f"{emp_id_proper}{dob_formatted}"
                user_doc.new_password = new_password
                print(f"  🔑 Password: {new_password}")
            else:
                print(f"  ⚠️  Không tạo được password - thiếu Employee/ngày sinh")
            
            # === 2. CLEAR VÀ SET ROLES ===
            user_doc.roles = []  # Xóa tất cả roles
            user_doc.append("roles", {
                "role": "TIQN Registration"
            })
            print(f"  👥 Role: TIQN Registration (đã xóa tất cả roles cũ)")
            
            # === 3. THIẾT LẬP MODULES - QUAN TRỌNG ===
            # Clear tất cả block_modules cũ
            user_doc.block_modules = []
            
            # Logic: Để chỉ allow TIQN App, ta phải:
            # - Không thêm TIQN App vào block_modules (để nó được allow)
            # - Thêm tất cả modules khác với blocked=1
            
            modules_blocked = 0
            for module in all_modules:
                if module.name != "TIQN App":  # Block tất cả trừ TIQN App
                    user_doc.append("block_modules", {
                        "module": module.name,
                        "blocked": 1  # Block
                    })
                    modules_blocked += 1
            
            print(f"  📱 Modules: Blocked {modules_blocked} modules, chỉ allow 'TIQN App'")
            
            # === 4. SET DEFAULT WORKSPACE ===
            user_doc.default_workspace = "Registration"
            print(f"  🏠 Default Workspace: Registration")
            
            # === 5. SET LANGUAGE ===
            user_doc.language = "vi"
            print(f"  🌐 Language: vi")
            
            # === LƯU USER ===
            user_doc.flags.ignore_permissions = True
            user_doc.save()
            
            # Commit sau khi save thành công
            frappe.db.commit()
            
            print(f"✅ Thành công: {user_id}")
            success_count += 1
            
        except Exception as e:
            error_msg = f"Lỗi {user_id}: {str(e)}"
            print(f"❌ {error_msg}")
            errors.append(error_msg)
            error_count += 1
            # Rollback nếu có lỗi
            frappe.db.rollback()
        
        # Separator
        if i < len(user_ids):
            print("-" * 40)
    
    # === BÁO CÁO KẾT QUẢ ===
    print("\n" + "=" * 60)
    print("📊 KẾT QUẢ CUỐI CÙNG:")
    print(f"✅ Thành công: {success_count}/{len(user_ids)} users")
    print(f"❌ Thất bại: {error_count}/{len(user_ids)} users")
    
    if errors:
        print(f"\n🚨 CHI TIẾT LỖI:")
        for j, error in enumerate(errors, 1):
            print(f"  {j}. {error}")
    
    print(f"\n🎯 CÁC THIẾT LẬP ĐÃ ÁP DỤNG:")
    print(f"  👥 Role: TIQN Registration (xóa hết roles cũ)")
    print(f"  📱 Module: Chỉ allow TIQN App (block tất cả khác)")
    print(f"  🏠 Workspace: Registration") 
    print(f"  🌐 Language: vi")
    print(f"  🔑 Password: PROPER(EmployeeID) + ddmm")
    
    print(f"\n🎉 HOÀN THÀNH!")

# ==================== CÁCH SỬ DỤNG ====================

def run():
    """Chạy script - tự động đọc file user_list.txt"""
    bulk_update_users_from_file()

# ==================== HƯỚNG DẪN ====================
print("""
🚀 CÁCH SỬ DỤNG:

1. Tạo file 'user_list.txt' cùng thư mục script:
   user1@tiqn.com.vn
   user2@tiqn.com.vn
   user3@tiqn.com.vn

2. Chạy lệnh:
   run()

3. Script sẽ tự động áp dụng:
   ✅ Role: TIQN Registration
   ✅ Module: Chỉ allow TIQN App  
   ✅ Workspace: Registration
   ✅ Language: vi
   ✅ Password: PROPER(EmployeeID) + ddmm
""")

# CHẠY SCRIPT:
# run()

# UNCOMMENT ĐỂ CHẠY NGAY:
# run()
# bench --site erp.tiqn.local console
# import customize_erpnext.api.bulk_update_users_from_file.bulk_update_users_from_file as script
# script.run() 