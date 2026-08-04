# -*- coding: utf-8 -*-
"""Setup for the Labor Contract feature (contract-renewal tracking).

Idempotent — safe to re-run on any environment:
  1. Ensure custom fields custom_period / custom_warning_before / custom_description
     exist on Employment Type.
  2. Ensure the 5 fixed-sequence Employment Type records exist with the correct
     period/warning values (creates missing ones, corrects existing ones).

Deliberately does NOT create any email Notification. Contract-renewal alerts are
still being specified; who receives them is the Admin's decision, made by hand in
the UI. An earlier version of this patch shipped an enabled Notification with
receiver_by_role "HR Manager" — that role expanded to 11 real accounts and a bulk
backfill of 14 contracts fired 154 real emails. Never arm an alert from code.
"""
import frappe


EMPLOYMENT_TYPES = [
    # name, custom_period (days), custom_warning_before (days)
    ("30 Days Probationary Contract", 30, 7),
    ("60 Days Probationary Contract", 60, 14),
    ("1 Year Employment Contract", 365, 30),
    ("3 Year Employment Contract", 1095, 30),
    ("Indefinite-term Employment Contract", 0, 0),
]


def execute():
    _ensure_custom_fields()
    _ensure_employment_types()
    frappe.db.commit()


def _ensure_custom_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields(
        {
            "Employment Type": [
                {
                    "fieldname": "custom_description",
                    "label": "Description",
                    "fieldtype": "Data",
                    "insert_after": "employee_type_name",
                },
                {
                    "fieldname": "custom_column_break_szkj9",
                    "fieldtype": "Column Break",
                    "insert_after": "custom_description",
                },
                {
                    "fieldname": "custom_period",
                    "label": "Period",
                    "fieldtype": "Int",
                    "insert_after": "custom_column_break_szkj9",
                    "description": "Contract validity in days. Leave 0/blank for Indefinite-term.",
                },
                {
                    "fieldname": "custom_warning_before",
                    "label": "Warning Before",
                    "fieldtype": "Int",
                    "insert_after": "custom_period",
                    "description": "Days before End Date the next contract stage is created. Leave 0/blank for Indefinite-term.",
                },
            ]
        },
        ignore_validate=True,
    )


def _ensure_employment_types():
    for name, period, warning_before in EMPLOYMENT_TYPES:
        if not frappe.db.exists("Employment Type", name):
            frappe.get_doc({
                "doctype": "Employment Type",
                "employee_type_name": name,
                "custom_period": period,
                "custom_warning_before": warning_before,
            }).insert(ignore_permissions=True)
        else:
            frappe.db.set_value(
                "Employment Type", name,
                {"custom_period": period, "custom_warning_before": warning_before},
                update_modified=False,
            )
