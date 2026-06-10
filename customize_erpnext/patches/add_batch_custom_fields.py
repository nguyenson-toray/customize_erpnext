import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields(
        {
            "Batch": [
                {
                    "fieldname": "custom_lot_number",
                    "label": "Lot Number",
                    "fieldtype": "Data",
                    "insert_after": "item",
                    "in_list_view": 1,
                },
                {
                    "fieldname": "custom_roll_number",
                    "label": "Roll Number",
                    "fieldtype": "Data",
                    "insert_after": "custom_lot_number",
                    "in_list_view": 1,
                },
            ]
        },
        update=True,
    )
    frappe.db.commit()
