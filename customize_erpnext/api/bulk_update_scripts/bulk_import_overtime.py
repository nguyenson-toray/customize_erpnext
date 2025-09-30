# Python Console Script - Bulk Import Overtime Registration từ Excel
# Chạy trong ERPNext Console

import frappe
import pandas as pd
import os
from datetime import datetime
from frappe.utils import getdate
import calendar

def bulk_import_overtime(file_path=None):
    """
    Import hàng loạt Overtime Registration từ file Excel
    Tạo 2 đăng ký mỗi tháng: 1-15 và 16-cuối tháng
    """

    # Tự động tìm file Excel cùng thư mục
    if file_path is None:
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
        except:
            current_dir = frappe.get_site_path()

        file_path = os.path.join(current_dir, 'OT, Shift Registers.xlsx')
        print(f"📂 Tự động tìm file: {file_path}")

    # Kiểm tra file tồn tại
    if not os.path.exists(file_path):
        print(f"❌ File không tồn tại: {file_path}")
        return

    try:
        # Đọc Excel
        print("📖 Đọc file Excel...")
        df = pd.read_excel(file_path, sheet_name='OT Registers - All')
        print(f"✅ Đọc được {len(df)} dòng dữ liệu")

        # Chuyển đổi cột Date sang datetime
        df['Date (OT Employees List)'] = pd.to_datetime(df['Date (OT Employees List)'])

        # Lọc dữ liệu từ tháng 1 đến tháng 9 năm 2025
        df = df[(df['Date (OT Employees List)'].dt.year == 2025) &
                (df['Date (OT Employees List)'].dt.month.between(1, 9))]

        print(f"📊 Lọc dữ liệu từ tháng 1-9/2025: {len(df)} dòng")

        if len(df) == 0:
            print("❌ Không có dữ liệu từ tháng 1-9/2025")
            return

        # Thêm cột phân loại khoảng ngày
        df['period'] = df['Date (OT Employees List)'].apply(lambda x: '1-15' if x.day <= 15 else '16-end')
        df['month'] = df['Date (OT Employees List)'].dt.month
        df['year'] = df['Date (OT Employees List)'].dt.year

        # Nhóm theo năm, tháng và khoảng ngày
        grouped = df.groupby(['year', 'month', 'period'])

        print(f"\n🔢 Tổng số nhóm cần tạo: {len(grouped)}")
        print("=" * 80)

        # Counters
        success_count = 0
        error_count = 0
        errors = []

        # Danh sách tháng
        month_names = {
            1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
            7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
        }

        # Tạo Overtime Registration cho từng nhóm
        for idx, ((year, month, period), group_df) in enumerate(grouped, 1):
            try:
                print(f"\n🔄 [{idx}/{len(grouped)}] Tháng {month}/{year} - Khoảng {period}")

                # Xác định request_date và reason_general
                if period == '1-15':
                    request_date = f"{year}-{month:02d}-01"
                    last_day = 15
                else:
                    request_date = f"{year}-{month:02d}-16"
                    last_day = calendar.monthrange(year, month)[1]

                month_name = month_names.get(month, str(month))
                reason_general = f"{month_name} {period.replace('end', str(last_day))}"

                print(f"  📅 Request Date: {request_date}")
                print(f"  📝 Reason: {reason_general}")
                print(f"  👥 Số dòng nhân viên: {len(group_df)}")

                # Tạo Overtime Registration document
                ot_doc = frappe.new_doc("Overtime Registration")
                ot_doc.request_date = getdate(request_date)
                ot_doc.reason_general = reason_general

                # Thêm chi tiết nhân viên
                for _, row in group_df.iterrows():
                    # Kiểm tra Employee tồn tại
                    employee_id = row['Employee (OT Employees List)']
                    if not frappe.db.exists("Employee", employee_id):
                        print(f"  ⚠️  Employee không tồn tại: {employee_id}")
                        continue

                    ot_doc.append("ot_employees", {
                        "date": getdate(row['Date (OT Employees List)']),
                        "employee": employee_id,
                        "begin_time": row['Begin Time (OT Employees List)'],
                        "end_time": row['End Time (OT Employees List)']
                    })

                if len(ot_doc.ot_employees) == 0:
                    error_msg = f"Tháng {month}/{year} - {period}: Không có nhân viên hợp lệ"
                    print(f"  ❌ {error_msg}")
                    errors.append(error_msg)
                    error_count += 1
                    continue

                # Lưu document
                ot_doc.flags.ignore_permissions = True
                ot_doc.insert()

                # Commit
                frappe.db.commit()

                print(f"  ✅ Tạo thành công: {ot_doc.name} ({len(ot_doc.ot_employees)} employees)")
                success_count += 1

            except Exception as e:
                error_msg = f"Tháng {month}/{year} - {period}: {str(e)}"
                print(f"  ❌ {error_msg}")
                errors.append(error_msg)
                error_count += 1
                frappe.db.rollback()

            # Separator
            if idx < len(grouped):
                print("-" * 60)

        # Báo cáo kết quả
        print("\n" + "=" * 80)
        print("📊 KẾT QUẢ CUỐI CÙNG:")
        print(f"✅ Thành công: {success_count}/{len(grouped)} registrations")
        print(f"❌ Thất bại: {error_count}/{len(grouped)} registrations")

        if errors:
            print(f"\n🚨 CHI TIẾT LỖI:")
            for j, error in enumerate(errors, 1):
                print(f"  {j}. {error}")

        print(f"\n🎉 HOÀN THÀNH!")

    except Exception as e:
        print(f"❌ Lỗi đọc file: {str(e)}")
        import traceback
        traceback.print_exc()

# ==================== CÁCH SỬ DỤNG ====================

def run():
    """Chạy script - tự động đọc file Excel"""
    bulk_import_overtime()

# ==================== HƯỚNG DẪN ====================
print("""
🚀 CÁCH SỬ DỤNG:

1. Đảm bảo file 'OT, Shift Registers.xlsx' có sẵn cùng thư mục script

2. Chạy trong ERPNext Console:
   bench --site erp.tiqn.local console
   import customize_erpnext.api.bulk_update_scripts.bulk_import_overtime as script
   script.run()

3. Script sẽ tự động:
   ✅ Đọc sheet 'OT Registers - All'
   ✅ Lọc dữ liệu tháng 1-9/2025
   ✅ Tạo 2 Overtime Registration mỗi tháng (1-15 và 16-cuối tháng)
   ✅ Điền chi tiết nhân viên vào bảng ot_employees

📝 CẤU TRÚC DỮ LIỆU:
   - Date (OT Employees List) → date
   - Employee (OT Employees List) → employee
   - Begin Time (OT Employees List) → begin_time
   - End Time (OT Employees List) → end_time
""")

# CHẠY SCRIPT:
# run()