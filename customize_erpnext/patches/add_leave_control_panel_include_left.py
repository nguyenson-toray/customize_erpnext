"""Checkbox opt-in cho Leave Control Panel — có kéo người đã nghỉ việc vào danh sách hay không.

Mặc định TẮT = hành vi HRMS gốc (chỉ `status = Active`), an toàn cho vận hành hằng ngày.
Chỉ bật khi cần cấp phép hồi tố cho một kỳ đã qua.

Xem `overrides/leave_control_panel/leave_control_panel.md`.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields(
        {
            "Leave Control Panel": [
                {
                    "fieldname": "custom_include_employees_who_left",
                    "label": "Include employees who left during the period",
                    "fieldtype": "Check",
                    # Mục "Allocate Leaves", cột 2, ngay dưới `allocate_based_on_leave_policy`.
                    # KHÔNG đặt trong Quick Filters: 6 field ở đó đều là Link để *thu hẹp* theo
                    # thuộc tính, còn checkbox này *mở rộng* tập nhân viên theo điều kiện hưởng.
                    "insert_after": "allocate_based_on_leave_policy",
                    "default": "0",
                    "description": (
                        "Off: only Active employees (HRMS default). "
                        "On: anyone whose employment overlaps the allocation period, "
                        "including Left / Inactive — they are still entitled to pro-rated "
                        "annual leave for the months worked (Điều 66 NĐ 145/2020)."
                    ),
                },
            ]
        },
        update=True,
    )
    frappe.db.commit()
