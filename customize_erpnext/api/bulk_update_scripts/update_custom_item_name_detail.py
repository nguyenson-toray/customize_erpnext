import frappe
def update_custom_item_name_detail(old_string=None, new_string=None):
    # Get all records with custom_item_name_detail field
    items = frappe.get_all("Item", filters={}, fields=["name", "custom_item_name_detail"])

    for item in items:
        if item.custom_item_name_detail:
            # Replace specific spaces with regular spaces and strip leading/trailing whitespace
            updated_name = item.custom_item_name_detail.replace(old_string, new_string).strip()            
            # Update only if there was a change
            if updated_name != item.custom_item_name_detail:
                frappe.db.set_value("Item", item.name, "custom_item_name_detail", updated_name)
    # Commit the changes
    frappe.db.commit()

    print("Custom item name details updated successfully")
if __name__ == "__main__": 
    update_custom_item_name_detail()

'''
cd ~/frappe-bench
bench --site erp.tiqn.local  console 
import custom_features.custom_features.bulk_update_scripts.update_custom_item_name_detail as update_script
update_script.update_custom_item_name_detail(" Blank","")
'''