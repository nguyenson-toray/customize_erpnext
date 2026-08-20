"""Attendance Request — bổ sung giờ check in/out bị thiếu.

Tạo:
  - Attendance Request.custom_supplement_section / custom_checkin_details (child table)
  - Employee Checkin.custom_attendance_request (truy vết + dọn dẹp khi Cancel)
  - Property Setter mở rộng Attendance Request.reason.options thêm 4 lý do lấy từ
    Employee Checkin.custom_reason_for_manual_check_in

Xem overrides/attendance_request/attendance_request.py và
docs/attendance_request_supplement_plan.md.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

# Giữ đồng bộ với SUPPLEMENT_REASONS trong overrides/attendance_request/attendance_request.py
REASON_OPTIONS = "\n".join(
    [
        "Work From Home",
        "On Duty",
        "Forget Check In/Out",
        "Machine Error",
        "First Working Day",
        "Other",
    ]
)

# Hiện section bổ sung chỉ khi reason là một trong 4 lý do bổ sung giờ công
SUPPLEMENT_DEPENDS_ON = (
    "eval:['Forget Check In/Out', 'Machine Error', 'First Working Day', 'Other']"
    ".includes(doc.reason)"
)


def execute():
    create_custom_fields(
        {
            "Attendance Request": [
                {
                    "fieldname": "custom_supplement_section",
                    "label": "Check In / Out Supplement",
                    "fieldtype": "Section Break",
                    # Sau `explanation` = ngay dưới section Reason. Đặt sau `shift`
                    # thì bảng giờ công lại nằm TRÊN ô Reason, trong khi chính
                    # Reason mới là thứ quyết định bảng có hiện hay không.
                    "insert_after": "explanation",
                    "depends_on": SUPPLEMENT_DEPENDS_ON,
                },
                {
                    "fieldname": "custom_checkin_details",
                    "label": "Check In / Out Details",
                    "fieldtype": "Table",
                    "options": "Attendance Request Checkin Detail",
                    "insert_after": "custom_supplement_section",
                    "depends_on": SUPPLEMENT_DEPENDS_ON,
                    "description": (
                        "Một dòng cho mỗi ngày trong khoảng From Date - To Date. "
                        "Chỉ nhập giờ ở ô cần bổ sung, để trống ô còn lại."
                    ),
                },
                {
                    "fieldname": "custom_signed_form",
                    "label": "Signed Form",
                    "fieldtype": "Attach",
                    "insert_after": "custom_checkin_details",
                    "depends_on": SUPPLEMENT_DEPENDS_ON,
                    # allow_on_submit: chữ ký thường thu được SAU khi phiếu đã submit
                    # (in -> ký -> scan), nên phải đính kèm được ở trạng thái submitted.
                    # An toàn: cả HRMS lẫn override đều không định nghĩa
                    # on_update_after_submit nên bật cờ này không kích hoạt hook nào.
                    "allow_on_submit": 1,
                    "no_copy": 1,
                    "description": (
                        "Bản scan giấy yêu cầu xác nhận công đã có đủ chữ ký."
                    ),
                },
            ],
            "Employee Checkin": [
                {
                    "fieldname": "custom_attendance_request",
                    "label": "Attendance Request",
                    "fieldtype": "Link",
                    "options": "Attendance Request",
                    "insert_after": "custom_other_reason_for_manual_check_in",
                    "read_only": 1,
                    "no_copy": 1,
                    "description": "Phiếu Attendance Request đã sinh ra checkin này (nếu có).",
                },
            ],
        },
        update=True,
    )

    make_property_setter(
        "Attendance Request",
        "reason",
        "options",
        REASON_OPTIONS,
        "Text",
        validate_fields_for_doctype=False,
    )

    frappe.clear_cache(doctype="Attendance Request")
    frappe.clear_cache(doctype="Employee Checkin")
