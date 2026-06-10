import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields(
        {
            "Batch": [
                {
                    "fieldname": "custom_initial_quantity",
                    "label": "Initial Quantity",
                    "fieldtype": "Float",
                    "insert_after": "custom_color",
                    "in_list_view": 1,
                    "description": (
                        "Số lượng dự kiến (vd chiều dài cuộn). Dùng để điền sẵn Qty khi bấm "
                        "'Add Multiple Batch' lúc nhập kho. KHÔNG tự tạo tồn kho."
                    ),
                },
            ]
        },
        update=True,
    )
    frappe.db.commit()
