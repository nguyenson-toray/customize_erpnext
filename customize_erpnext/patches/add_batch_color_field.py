import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields(
        {
            "Batch": [
                {
                    "fieldname": "custom_color",
                    "label": "Color",
                    "fieldtype": "Data",
                    "insert_after": "custom_roll_number",
                    "read_only": 1,
                    "in_list_view": 1,
                },
            ]
        },
        update=True,
    )
    frappe.db.commit()
