import frappe
import pandas as pd
import os
import sys
import datetime
from frappe.utils import cstr
import re

@frappe.whitelist()
def create_item_variants_improved(file_path=None, file_url=None):
    """
    Read Excel file and create item variants based on the improved requirements.
    Never re-creates items if they already exist.
    
    Args:
        file_path (str): Path to the Excel file containing item variant data
        file_url (str): URL to the uploaded file (from frontend)
    """
    # Handle file URL from frontend upload
    if file_url and not file_path:
        try:
            # Convert file URL to actual file path
            if file_url.startswith('/files/'):
                # Get the site path and construct full file path
                site_path = frappe.utils.get_site_path()
                # Remove leading slash and construct path
                relative_path = file_url.lstrip('/')
                file_path = os.path.join(site_path, 'public', relative_path)
            else:
                # If it's a full URL, extract the filename and construct path
                filename = file_url.split('/')[-1]
                site_path = frappe.utils.get_site_path()
                file_path = os.path.join(site_path, 'public', 'files', filename)
        except Exception as e:
            print(f"Error constructing file path: {e}")
            # Fallback to manual construction
            current_site = frappe.local.site
            file_path = f"/home/frappe/frappe-bench/sites/{current_site}/public{file_url}"
    
    # Setup logging to files
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_file_path = os.path.join(script_dir, "create_item_variants_improved_validate_data_result.txt")
    error_log_file_path = os.path.join(script_dir, "create_item_variants_improved_result_err.txt")
    
    if not file_path:
        file_path = "/home/frappe/frappe-bench/sites/erp.tiqn.local/public/files/create_item_variants_improved_template.xlsx"
    
    # Ensure we have absolute path
    if not os.path.isabs(file_path):
        file_path = os.path.abspath(file_path)
    
    def check_item_exists(item_code):
        """
        Check if an item exists in the database.
        Uses consistent logic with validation script.
        
        Args:
            item_code (str): Item code to check
            
        Returns:
            bool: True if item exists, False otherwise
        """
        try:
            exists = frappe.db.get_value("Item", item_code, "name")
            return bool(exists)
        except Exception:
            return False
    
    # Create a custom logging function that writes to both console and appropriate log file
    def log_message(message, is_error=False):
        print(message)
        with open(log_file_path, "a", encoding="utf-8") as log_file:
            log_file.write(message + "\n")
        
        # If it's an error, also write to error log file
        if is_error:
            with open(error_log_file_path, "a", encoding="utf-8") as error_log_file:
                error_log_file.write(message + "\n")
    
    def get_attribute_abbreviation(attribute_name, attribute_value):
        """
        Get attribute abbreviation based on attribute value.
        
        Args:
            attribute_name (str): Name of the attribute (Color, Size, Brand, Season, Info)
            attribute_value (str): Value of the attribute
            
        Returns:
            str: Abbreviation for the attribute value, or empty string if not found
        """
        try:
            if not attribute_value:
                return ""
            
            # Query the Item Attribute Value table to find abbreviation
            abbr = frappe.db.get_value(
                "Item Attribute Value",
                {
                    "parent": attribute_name,
                    "attribute_value": attribute_value
                },
                "abbr"
            )
            
            return cstr(abbr) if abbr else ""
            
        except Exception as e:
            log_message(f"Error getting abbreviation for {attribute_name}-{attribute_value}: {str(e)}", is_error=True)
            return ""
    
    def template_has_attribute(template_item_code, attribute_name):
        """
        Check if template item has a specific attribute.
        
        Args:
            template_item_code (str): Template item code
            attribute_name (str): Name of the attribute to check
            
        Returns:
            bool: True if template has the attribute, False otherwise
        """
        try:
            # Check if template has the specified attribute
            has_attr = frappe.db.get_value(
                "Item Variant Attribute",
                {
                    "parent": template_item_code,
                    "attribute": attribute_name
                },
                "name"
            )
            
            return bool(has_attr)
            
        except Exception as e:
            log_message(f"Error checking if template {template_item_code} has attribute {attribute_name}: {str(e)}", is_error=True)
            return False
    
    def find_template_by_item_name(item_name):
        """
        Find template item by item name.
        
        Args:
            item_name (str): Item name to search for
            
        Returns:
            str: Template item code or None if not found
        """
        try:
            # First try exact match
            template = frappe.db.get_value(
                "Item",
                {
                    "item_name": item_name,
                    "has_variants": 1
                },
                "name"
            )
            
            if template:
                return template
            
            # If no exact match, try to find by item_code (in case item_name is actually item_code)
            template = frappe.db.get_value(
                "Item",
                {
                    "name": item_name,
                    "has_variants": 1
                },
                "name"
            )
            
            return template
            
        except Exception as e:
            log_message(f"Error finding template for item name '{item_name}': {str(e)}", is_error=True)
            return None
    
    def clean_and_join_values(values, separator=" "):
        """
        Clean values by removing empty/None values, then join with separator.
        Note: "Blank" is a valid attribute value, so we keep it.
        
        Args:
            values (list): List of values to clean and join
            separator (str): Separator to use for joining
            
        Returns:
            str: Cleaned and joined string
        """
        # Filter out only empty and None values, keep "Blank" as it's a valid attribute value
        clean_values = []
        for value in values:
            if value and cstr(value).strip():
                clean_values.append(cstr(value).strip())
        
        # Join with separator and clean up multiple spaces
        result = separator.join(clean_values)
        # Remove multiple consecutive spaces
        result = re.sub(r'\s+', ' ', result).strip()
        
        return result
    
    def clean_and_join_abbreviations(abbr_list):
        """
        Clean abbreviations by removing empty values, then join with dash.
        
        Args:
            abbr_list (list): List of abbreviations to clean and join
            
        Returns:
            str: Cleaned and joined abbreviations with dash separator
        """
        clean_abbrs = []
        for abbr in abbr_list:
            if abbr and cstr(abbr).strip():
                clean_abbrs.append(cstr(abbr).strip())
        
        return "-".join(clean_abbrs)
    
    # Initialize log files with timestamp
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write(f"Improved Item Variants Creation Log - Started at {timestamp}\n")
        log_file.write("-" * 80 + "\n\n")
    
    with open(error_log_file_path, "w", encoding="utf-8") as error_log_file:
        error_log_file.write(f"Improved Item Variants Creation Error Log - Started at {timestamp}\n")
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
        results = []
        
        # Process each row in the Excel file
        for index, row in df.iterrows():
            try:
                # Extract data from the row
                item_name = cstr(row.get("Item Name", "")).strip()
                color_value = cstr(row.get("Attribute Color - Value", "")).strip()
                size_value = cstr(row.get("Attribute Size - Value", "")).strip()
                brand_value = cstr(row.get("Attribute Brand - Value", "")).strip()
                season_value = cstr(row.get("Attribute Season - Value", "")).strip()
                info_value = cstr(row.get("Attribute Info - Value", "")).strip()
                
                # If no value provided or value is "nan", default to "Blank" for standard attributes
                if not color_value or color_value.lower() == "nan":
                    color_value = "Blank"
                if not size_value or size_value.lower() == "nan":
                    size_value = "Blank"
                if not brand_value or brand_value.lower() == "nan":
                    brand_value = "Blank"
                if not season_value or season_value.lower() == "nan":
                    season_value = "Blank"
                if not info_value or info_value.lower() == "nan":
                    info_value = "Blank"
                
                # Skip if item name is missing
                if not item_name:
                    error_msg = f"Row {index+2}: Item Name is missing"
                    log_message(error_msg, is_error=True)
                    results.append(error_msg)
                    error_count += 1
                    continue
                
                # Find template item
                template_item_code = find_template_by_item_name(item_name)
                if not template_item_code:
                    error_msg = f"Row {index+2}: Template item not found for '{item_name}'"
                    log_message(error_msg, is_error=True)
                    results.append(error_msg)
                    error_count += 1
                    continue
                
                # Get attribute abbreviations
                color_abbr = get_attribute_abbreviation("Color", color_value)
                size_abbr = get_attribute_abbreviation("Size", size_value)
                brand_abbr = get_attribute_abbreviation("Brand", brand_value)
                season_abbr = get_attribute_abbreviation("Season", season_value)
                
                # Build item_code: template_item_code + "-" + join(attribute_abbr with dash)
                abbr_list = [color_abbr, size_abbr, brand_abbr, season_abbr]
                
                # Only include Info abbreviation if template has Info attribute
                if template_has_attribute(template_item_code, "Info"):
                    info_abbr = get_attribute_abbreviation("Info", info_value)
                    abbr_list.append(info_abbr)
                
                item_code_suffix = clean_and_join_abbreviations(abbr_list)
                
                if item_code_suffix:
                    variant_item_code = f"{template_item_code}-{item_code_suffix}"
                else:
                    variant_item_code = template_item_code
                
                # Build custom_item_name_detail: item_name + " " + join(attribute_values)
                value_list = [color_value, size_value, brand_value, season_value]
                
                # Only include Info value if template has Info attribute
                if template_has_attribute(template_item_code, "Info"):
                    value_list.append(info_value)
                
                custom_item_name_detail = f"{item_name} {clean_and_join_values(value_list, ' ')}"
                custom_item_name_detail = custom_item_name_detail.strip()
                
                # Check if variant already exists - NEVER create duplicates
                # Use same logic as validation script for consistency
                if check_item_exists(variant_item_code):
                    error_msg = f"Row {index+2}: Item variant '{variant_item_code}' already exists"
                    log_message(error_msg, is_error=True)
                    results.append(error_msg)
                    error_count += 1
                    continue
                
                log_message(f"Creating variant {variant_item_code} from template {template_item_code}...")
                
                # Get template item
                template_item = frappe.get_doc("Item", template_item_code)
                
                # Create variant
                variant = frappe.new_doc("Item")
                
                # Set variant attributes
                attributes = []
                
                # Always add Color attribute (including "Blank" values)
                attributes.append({
                    "attribute": "Color",
                    "attribute_value": color_value
                })
                
                # Always add Size attribute (including "Blank" values)
                attributes.append({
                    "attribute": "Size",
                    "attribute_value": size_value
                })
                
                # Always add Brand attribute (including "Blank" values)
                attributes.append({
                    "attribute": "Brand",
                    "attribute_value": brand_value
                })
                
                # Always add Season attribute (including "Blank" values)
                attributes.append({
                    "attribute": "Season",
                    "attribute_value": season_value
                })
                
                # Only add Info attribute if template has Info attribute
                if template_has_attribute(template_item_code, "Info"):
                    attributes.append({
                        "attribute": "Info",
                        "attribute_value": info_value
                    })
                    log_message(f"Template has Info attribute, adding Info: {info_value}")
                else:
                    log_message(f"Template does not have Info attribute, skipping Info attribute")
                
                # Create the variant with basic properties
                variant.item_code = variant_item_code
                variant.item_name = item_name  # Use original item_name from Excel
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
                ]
                
                # Copy each property if it exists in the template
                for field in properties_to_copy:
                    try:
                        field_value = getattr(template_item, field, None)
                        if field_value is not None:
                            setattr(variant, field, field_value)
                    except Exception as field_err:
                        log_message(f"Note: Could not copy field '{field}': {str(field_err)}")
                
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
                
                # Copy item_defaults from template
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
                
                except Exception as def_err:
                    log_message(f"Warning: Error copying item defaults: {str(def_err)}", is_error=True)
                
                # Commit the transaction after all operations
                frappe.db.commit()
                
                log_message(f"Row {index+2}: Successfully created item variant '{variant_item_code}' from template '{template_item_code}'.")
                results.append(variant_item_code)  # Store successful item_code
                success_count += 1
                
            except Exception as e:
                error_msg = f"Row {index+2}: Error creating item variant: {str(e)}"
                log_message(error_msg, is_error=True)
                log_message(f"Error details: {frappe.get_traceback()}", is_error=True)
                results.append(error_msg)
                error_count += 1
                # Rollback transaction for this row in case of error
                frappe.db.rollback()
        
        # Update the Results column in the Excel file
        try:
            df['Result'] = results
            # Save updated Excel file
            output_file = file_path.replace('.xlsx', '_with_results.xlsx')
            df.to_excel(output_file, index=False)
            log_message(f"Updated Excel file saved as: {output_file}")
        except Exception as e:
            log_message(f"Warning: Could not update Excel file with results: {str(e)}", is_error=True)
        
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
            "success_count": success_count,
            "error_count": error_count,
            "total_rows": len(df),
            "results": results,
            "log_file": log_file_path
        }
    
    except Exception as e:
        error_message = f"Error in create_item_variants_improved: {str(e)}"
        log_message(error_message, is_error=True)
        log_message(f"Error details: {frappe.get_traceback()}", is_error=True)
        frappe.log_error(error_message, "Improved Item Variant Creation Error")
        frappe.db.rollback()
        
        return {
            "success_count": 0,
            "error_count": 1,
            "total_rows": 0,
            "results": [error_message],
            "log_file": None
        }


if __name__ == "__main__":
    # This is just for local testing
    # In production, this will be called via bench console
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        create_item_variants_improved(file_path)
    else:
        print("Please provide Excel file path as argument")


'''
Usage instructions:
bench --site erp.tiqn.local console
import customize_erpnext.api.bulk_update_scripts.create_item_variants_improved as create_script
create_script.create_item_variants_improved()
or
create_script.create_item_variants_improved("/home/frappe/frappe-bench/sites/erp.tiqn.local/public/files/create_item_variants_improved_template.xlsx")

Key improvements:
1. Find template by Item Name instead of "Variant Of" column
2. Get attribute abbreviations by querying Item Attribute Value table
3. Generate item_code using: template_code + "-" + joined_abbreviations (with dash separator)
4. Generate custom_item_name_detail using: item_name + " " + joined_attribute_values
5. "Blank" is treated as a valid attribute value (not removed)
6. Always create Color, Size, Brand, Season attributes (including "Blank" values)
7. Only create Info attribute if template has Info attribute
8. Save results back to Excel file Result column
9. Better error handling and logging
'''