import frappe

def remove_depends_on():
    frappe.get_doc({
        "doctype": "Property Setter",
        "doctype_or_field": "DocField",
        "doc_type": "Your_DocType_Name",  # Thay thế bằng tên DocType của bạn
        "field_name": "working_hours",
        "property": "depends_on",
        "value": "",  # Để trống để bỏ depends_on
        "property_type": "Data"
    }).insert(ignore_permissions=True)