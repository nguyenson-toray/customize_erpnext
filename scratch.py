import frappe

def execute():
    field = {
        "fieldname": "do_not_auto_suggest",
        "fieldtype": "Check",
        "label": "Do Not Auto Suggest",
        "insert_after": "status",
        "description": "Tick to exclude this rack from being auto-suggested to new employees."
    }
    
    try:
        if frappe.db.exists("Custom Field", {"dt": "Shoe Rack", "fieldname": "do_not_auto_suggest"}):
            print("Field already exists.")
            return

        doc = frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Shoe Rack",
            **field
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        print("Field created successfully.")
    except Exception as e:
        print(f"Error: {e}")
