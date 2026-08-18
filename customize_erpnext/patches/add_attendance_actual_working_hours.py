"""`custom_actual_working_hours` — giờ làm thực tế theo check in/out, không bị chặn.

Từ 18/08/2026 `working_hours` là **cơ sở chốt lương** và bị chặn theo đơn nghỉ phép
(xem `overrides/shift_type/leave_hour_cap.py`). Field mới giữ lại con số thật để HR biết ai
"xin nghỉ nhưng vẫn đi làm".

Backfill: trước thay đổi này `working_hours` CHÍNH LÀ giờ thực tế, nên copy sang là đúng.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields(
        {
            "Attendance": [
                {
                    "fieldname": "custom_actual_working_hours",
                    "label": "Actual Working Hours",
                    "fieldtype": "Float",
                    "insert_after": "working_hours",
                    "read_only": 1,
                    "precision": "2",
                    "description": (
                        "Hours actually worked, from check-in/check-out. Never capped. "
                        "Compare with Working Hours: if it is larger, the employee had leave "
                        "but still came to work."
                    ),
                },
            ]
        },
        update=True,
    )

    # Chạy bằng SQL: 170k bản ghi, dùng ORM sẽ mất hàng chục phút và bắn hook vô ích.
    #
    # ⚠ Điều kiện KHÔNG được là `IS NULL`: Frappe tạo cột Float với `DEFAULT 0`, không bao giờ
    # NULL, nên `IS NULL` khớp 0 dòng và patch im lặng không làm gì.
    #
    # `actual = 0 AND working_hours <> 0` vừa đúng nghĩa "chưa backfill", vừa idempotent: sau khi
    # engine áp cap, bản ghi nghỉ trọn ngày có working_hours = 0 và actual > 0 nên không khớp.
    frappe.db.sql("""
        UPDATE `tabAttendance`
        SET custom_actual_working_hours = working_hours
        WHERE ifnull(custom_actual_working_hours, 0) = 0
          AND ifnull(working_hours, 0) <> 0
    """)
    updated = frappe.db.sql("SELECT ROW_COUNT()")[0][0]
    frappe.db.commit()
    print(f"   ✓ backfill custom_actual_working_hours: {updated} dòng")
