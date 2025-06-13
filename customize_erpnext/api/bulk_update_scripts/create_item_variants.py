import frappe
import pandas as pd
import os
import sys
import datetime
from frappe.utils import cstr

def create_item_variants(file_path=None):
    """
    Read Excel file and create item variants based on the data.
    
    Args:
        file_path (str): Path to the Excel file containing item variant data
    """
    # Setup logging to files
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_file_path = os.path.join(script_dir, "create_item_variants_log.txt")
    error_log_file_path = os.path.join(script_dir, "create_item_variants_log_err.txt")
    if not file_path:
        file_path = "/home/frappe/frappe-bench/sites/erp.tiqn.local/public/files/Item Variants.xlsx"
    # Create a custom logging function that writes to both console and appropriate log file
    def log_message(message, is_error=False):
        print(message)
        with open(log_file_path, "a", encoding="utf-8") as log_file:
            log_file.write(message + "\n")
        
        # If it's an error, also write to error log file
        if is_error:
            with open(error_log_file_path, "a", encoding="utf-8") as error_log_file:
                error_log_file.write(message + "\n")
    
    # Initialize log files with timestamp
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write(f"Item Variants Creation Log - Started at {timestamp}\n")
        log_file.write("-" * 80 + "\n\n")
    
    with open(error_log_file_path, "w", encoding="utf-8") as error_log_file:
        error_log_file.write(f"Item Variants Creation Error Log - Started at {timestamp}\n")
        error_log_file.write("-" * 80 + "\n\n")
    
    try:
        log_message(f"Reading Excel file: {file_path}")
        
        # Check if file exists
        if not os.path.exists(file_path):
            log_message(f"Error: File not found at {file_path}", is_error=True)
            return
            
        df = pd.read_excel(file_path)
        log_message(f"Successfully read Excel file with {len(df)} rows")
        
        # Initialize counters
        success_count = 0
        error_count = 0
        
        # Process each row in the Excel file
        for index, row in df.iterrows():
            try:
                # Extract data from the row with correct column names
                template_item_code = cstr(row.get("Variant Of"))  # Column name without typo
                if not template_item_code:
                    # Try with the potentially misspelled column name
                    template_item_code = cstr(row.get("Vairiant Of"))
                variant_item_code = cstr(row.get("Item Code"))
                variant_item_name = cstr(row.get("Item Name"))
                custom_item_name_detail = cstr(row.get("Item Name Detail"))  
                # Get attribute values (both abbreviation and full value)
                color_abbr = cstr(row.get("Attribute Color - Abbreviation"))
                color_value = cstr(row.get("Attribute Color - Value"))
                size_abbr = cstr(row.get("Attribute Size - Abbreviation"))
                size_value = cstr(row.get("Attribute Size - Value"))
                brand_abbr = cstr(row.get("Attribute Brand - Abbreviation"))
                brand_value = cstr(row.get("Attribute Brand - Value"))
                season_abbr = cstr(row.get("Attribute Season - Abbreviation"))
                season_value = cstr(row.get("Attribute Season - Value"))
                info_abbr = cstr(row.get("Attribute Info - Abbreviation"))
                info_value = cstr(row.get("Attribute Info - Value")) or ''
                
                # Skip if template item code is missing
                if not template_item_code:
                    log_message(f"Row {index+2}: Template item code is missing. Skipping.", is_error=True)
                    error_count += 1
                    continue
                
                # Skip if variant item code is missing
                if not variant_item_code:
                    log_message(f"Row {index+2}: Variant item code is missing. Skipping.", is_error=True)
                    error_count += 1
                    continue
                
                # Check if template item exists - using direct SQL query
                template_exists = frappe.db.sql("""
                    SELECT name FROM `tabItem` 
                    WHERE name=%s
                """, (template_item_code,))
                
                if not template_exists:
                    log_message(f"Row {index+2}: Template item '{template_item_code}' does not exist. Skipping.", is_error=True)
                    error_count += 1
                    continue
                
                # Check if variant already exists - using direct SQL query
                variant_exists = frappe.db.sql("""
                    SELECT name FROM `tabItem` 
                    WHERE name=%s
                """, (variant_item_code,))
                
                if variant_exists:
                    log_message(f"Row {index+2}: Item variant '{variant_item_code}' already exists in database. Skipping.", is_error=True)
                    error_count += 1
                    continue
                
                log_message(f"Creating variant {variant_item_code} from template {template_item_code}...")
                
                # Get template item
                template_item = frappe.get_doc("Item", template_item_code)
                
                # Create variant
                variant = frappe.new_doc("Item")
                
                # Set variant attributes
                attributes = []
                
                # Add Color attribute
                if color_value:
                    attributes.append({
                        "attribute": "Color",
                        "attribute_value": color_value
                    })
                
                # Add Size attribute
                if size_value:
                    attributes.append({
                        "attribute": "Size",
                        "attribute_value": size_value
                    })
                
                 # Add Brand attribute
                if brand_value:
                    attributes.append({
                        "attribute": "Brand",
                        "attribute_value": brand_value
                    })
                
                # Add Season attribute
                if season_value:
                    attributes.append({
                        "attribute": "Season",  # Using "Season" as per the requirement
                        "attribute_value": season_value
                    })
                
                if info_value !='' and info_value != "Blank":
                    attributes.append({
                        "attribute": "Info",  
                        "attribute_value": info_value
                    })
                
                # Create the variant with basic properties
                variant.item_code = variant_item_code
                variant.item_name = variant_item_name
                variant.variant_of = template_item_code
                variant.item_group = template_item.item_group
                variant.stock_uom = template_item.stock_uom
                variant.brand = template_item.brand
                variant.custom_item_name_detail = custom_item_name_detail
                
                # Safely copy properties that might not exist in all installations
                properties_to_copy = [
                    'is_purchase_item', 
                    'is_customer_provided_item', 
                    'is_sales_item', 
                    'include_item_in_manufacturing',
                    'brand',
                ]
                
                # Copy each property if it exists in the template
                for field in properties_to_copy:
                    try:
                        field_value = getattr(template_item, field, None)
                        if field_value is not None:
                            setattr(variant, field, field_value)
                    except Exception as field_err:
                        log_message(f"Note: Could not copy field '{field}': {str(field_err)}", is_error=True)
                
                # Copy description from template
                if hasattr(template_item, 'description'):
                    variant.description = template_item.description
                
                # Copy custom_description_vietnamese if it exists
                if hasattr(template_item, 'custom_description_vietnamese'):
                    variant.custom_description_vietnamese = template_item.custom_description_vietnamese
                
                # Add attributes
                for attr in attributes:
                    variant.append("attributes", attr)
                
                # Save the variant with ignore_permissions to ensure it works
                variant.flags.ignore_permissions = True
                variant.insert(ignore_permissions=True)
                
                # Now copy the item_defaults (including default_warehouse) after variant is created
                try:
                    # Get item defaults from template
                    template_defaults = frappe.db.sql("""
                        SELECT * FROM `tabItem Default`
                        WHERE parent=%s
                    """, (template_item_code,), as_dict=1)
                    
                    if template_defaults:
                        log_message(f"Found {len(template_defaults)} item defaults to copy from template")
                        
                        # Copy each default row to the variant
                        for default_row in template_defaults:
                            # Create a clean copy of the default row
                            new_default = {}
                            for key, value in default_row.items():
                                if key not in ['name', 'creation', 'modified', 'modified_by', 'owner', 'docstatus', 'idx', 'parent', 'parentfield', 'parenttype']:
                                    new_default[key] = value
                            
                            # Check for existing item default with the same company
                            existing_default = frappe.db.get_value("Item Default", 
                                {"parent": variant_item_code, "company": new_default.get("company")}, 
                                "name")
                            
                            if existing_default:
                                # Update existing default
                                frappe.db.set_value("Item Default", existing_default, new_default)
                                log_message(f"Updated existing item default for company {new_default.get('company')}")
                            else:
                                # Create new item default
                                item_default = frappe.new_doc('Item Default')
                                item_default.parent = variant_item_code
                                item_default.parenttype = 'Item'
                                item_default.parentfield = 'item_defaults'
                                
                                for key, value in new_default.items():
                                    item_default.set(key, value)
                                
                                item_default.insert()
                                log_message(f"Created new item default with warehouse: {new_default.get('default_warehouse', 'Not specified')}")
                    else:
                        # If no defaults found in the template, try to create default based on item_group
                        log_message("No item defaults found in template. Creating defaults based on item group.")
                        group = variant.item_group
                        company = frappe.defaults.get_default('company')
                        
                        if group and company:
                            # Create default warehouses based on item group
                            warehouses_to_create = []
                            
                            # Default cases - add specific warehouses based on your pattern
                            if "Raw Materials" in group:
                                warehouses_to_create.append("03 - Raw Materials - TIQN")
                            if "Fabric" in group or "Material" in group:
                                warehouses_to_create.append("3.1 - Material - Fabric - TIQN")
                            
                            # If no specific mappings, use the general pattern
                            if not warehouses_to_create:
                                warehouses_to_create.append(f"{group} - TIQN")
                            
                            # Create item defaults for each warehouse
                            for warehouse in warehouses_to_create:
                                item_default = frappe.new_doc('Item Default')
                                item_default.parent = variant_item_code
                                item_default.parenttype = 'Item'
                                item_default.parentfield = 'item_defaults'
                                item_default.company = company
                                item_default.default_warehouse = warehouse
                                item_default.insert()
                                
                                log_message(f"Created new item default with warehouse: {warehouse}")
                
                except Exception as def_err:
                    log_message(f"Warning: Error copying item defaults: {str(def_err)}", is_error=True)
                    log_message(f"Error details: {frappe.get_traceback()}", is_error=True)
                
                # Commit the transaction after all operations
                frappe.db.commit()
                
                log_message(f"Row {index+2}: Successfully created item variant '{variant_item_code}' from template '{template_item_code}'.")
                success_count += 1
                
            except Exception as e:
                log_message(f"Row {index+2}: Error creating item variant: {str(e)}", is_error=True)
                log_message(f"Error details: {frappe.get_traceback()}", is_error=True)
                error_count += 1
                # Rollback transaction for this row in case of error
                frappe.db.rollback()
        
        # Print summary
        log_message("\nSummary:")
        log_message(f"Total rows processed: {len(df)}")
        log_message(f"Successfully created: {success_count}")
        log_message(f"Errors: {error_count}")
        
        # Add closing timestamp
        end_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message(f"\nProcess completed at {end_timestamp}")
        
        # Add summary to error log if there were errors
        if error_count > 0:
            with open(error_log_file_path, "a", encoding="utf-8") as error_log_file:
                error_log_file.write("\nSummary:\n")
                error_log_file.write(f"Total rows processed: {len(df)}\n")
                error_log_file.write(f"Successfully created: {success_count}\n")
                error_log_file.write(f"Errors: {error_count}\n")
                error_log_file.write(f"\nProcess completed at {end_timestamp}\n")
        
        return {
            "success": success_count,
            "errors": error_count,
            "total": len(df)
        }
    
    except Exception as e:
        error_message = f"Error in create_item_variants: {str(e)}"
        log_message(error_message, is_error=True)
        log_message(f"Error details: {frappe.get_traceback()}", is_error=True)
        frappe.log_error(error_message, "Item Variant Creation Error")
        frappe.db.rollback()


if __name__ == "__main__":
    # This is just for local testing
    # In production, this will be called via bench console
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        create_item_variants(file_path)
    else:
        print("Please provide Excel file path as argument")


'''
bench --site erp.tiqn.local console
import custom_features.custom_features.bulk_update_scripts.create_item_variants as create_script
create_script.create_item_variants()
or
create_script.create_item_variants("/home/frappe/frappe-bench/sites/erp.tiqn.local/public/files/Item variant.xlsx")
create_script.create_item_variants("/home/frappe/frappe-bench/sites/erp.tiqn.local/public/files/Item variant FS.xlsx")
'''