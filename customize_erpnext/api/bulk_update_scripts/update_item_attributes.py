import frappe
import pandas as pd
import os
import datetime

def update_item_attributes(excel_file_path=None):
    """
    Updates items from an Excel file by adding 'Size' and 'Season' attributes to items 
    that already have the 'Color' attribute.
    
    Args:
        excel_file_path (str, optional): Path to the Excel file. 
                         Defaults to a predefined path if not provided.
    """
    # Initialize logging
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_file_path = os.path.join(script_dir, "update_item_attributes_log.txt")
    log_file = open(log_file_path, "w", encoding="utf-8")
    log_message(f"Started item attribute update process at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", log_file)
    
    # Use default path if none is provided
    if not excel_file_path:
        excel_file_path = "/home/frappe/frappe-bench/sites/erp.tiqn.local/public/files/Item Templates.xlsx"
    
    try:
        log_message(f"Reading Excel file from: {excel_file_path}", log_file)
        df = pd.read_excel(excel_file_path)
        
        # Check if the file was read correctly
        if df.empty:
            log_message("Error: Excel file is empty", log_file)
            return
            
        # Get the column name for item codes
        if "Item Code" not in df.columns:
            log_message("Error: 'Item Code' column not found in Excel file", log_file)
            return
            
        # Count items for stats
        total_items = 0
        successfully_updated = 0
        errors = 0
        skipped = 0
        
        # Log item codes for reporting
        item_codes = df["Item Code"].dropna().unique().tolist()
        log_message(f"Found {len(item_codes)} unique item codes in Excel file", log_file)
        has_info = 0
        # Process each item in the Excel file
        for _, row in df.iterrows():
            item_code = row["Item Code"]
            item_group = row["Item Group"]
            has_info = row["Has Info"] or 0
            total_items += 1
            
            try:
                # Get the item from database
                item = frappe.get_doc("Item", item_code)
                
                # Check if the item exists and has variants
                if not item:
                    log_message(f"Warning: Item {item_code} not found in the system", log_file)
                    errors += 1
                    continue
                    
                if not item.has_variants:
                    log_message(f"Warning: Item {item_code} does not have variants enabled", log_file)
                    errors += 1
                    continue
                
                # Check if item already has 'Color' attribute
                has_color_attribute = False
                for attr in item.attributes:
                    if attr.attribute == "Color":
                        has_color_attribute = True
                        break
                
                if not has_color_attribute:
                    log_message(f"Warning: Item {item_code} does not have 'Color' attribute", log_file)
                    errors += 1
                    continue
                
                # Check if Size attribute already exists
                has_size_attribute = False
                has_brand_attribute = False
                has_season_attribute = False 
                has_info_attribute = False 
                
                for attr in item.attributes:
                    if attr.attribute == "Size":
                        has_size_attribute = True
                    if attr.attribute == "Brand":
                        has_size_attribute = True
                    if attr.attribute == "Season":
                        has_season_attribute = True
                    if attr.attribute == "Info":
                        has_info_attribute = True
                
                if has_size_attribute and has_brand_attribute and has_season_attribute and has_info_attribute:
                    log_message(f"Item {item_code} already has Size, Brand, Season, Info attributes - skipping", log_file)
                    skipped += 1
                    continue
                    
                # Log current attributes
                existing_attributes = [attr.attribute for attr in item.attributes]
                log_message(f"Item {item_code} current attributes: {', '.join(existing_attributes)}", log_file)
                
                # Track which attributes were added
                attributes_added = []
                
                # Add Size attribute if it doesn't exist
                if not has_size_attribute:
                    item.append("attributes", {
                        "attribute": "Size"
                    })
                    attributes_added.append("Size")
                
                 # Add Brand attribute if it doesn't exist
                if not has_size_attribute:
                    item.append("attributes", {
                        "attribute": "Brand"
                    })
                    attributes_added.append("Brand")
                
                # Add Season attribute if it doesn't exist
                if not has_season_attribute:
                    item.append("attributes", {
                        "attribute": "Season"
                    })
                    attributes_added.append("Season")
 
                if has_info==1:
                    if not has_info_attribute and has_info:
                        item.append("attributes", {
                            "attribute": "Info"
                        })
                        attributes_added.append("Season")
                
                # Save the item if changes were made
                if attributes_added:
                    item.save()
                    frappe.db.commit()
                    log_message(f"Updated Item: {item_code} - Added attributes: {', '.join(attributes_added)}", log_file)
                    successfully_updated += 1
            
            except Exception as e:
                log_message(f"Error updating item {item_code}: {str(e)}", log_file)
                errors += 1
        
        # Print summary
        log_message("\n--- Summary ---", log_file)
        log_message(f"Total items processed: {total_items}", log_file)
        log_message(f"Successfully updated: {successfully_updated}", log_file)
        log_message(f"Skipped (already had attributes): {skipped}", log_file)
        log_message(f"Errors: {errors}", log_file)
        log_message(f"Process completed at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", log_file)
        
    except Exception as e:
        log_message(f"Error processing Excel file: {str(e)}", log_file)
    
    finally:
        if log_file:
            log_file.close()
            print(f"Log file saved to: {log_file_path}")

def log_message(message, log_file=None):
    """
    Prints a message to console and optionally writes it to a log file
    
    Args:
        message (str): The message to log
        log_file (file object, optional): File handle for logging. Defaults to None.
    """
    print(message)
    if log_file:
        log_file.write(f"{message}\n")
        log_file.flush()  # Ensure message is written immediately

if __name__ == "__main__":
    # Example usage with explicit file path
    # update_item_attributes("/path/to/your/excel/file.xlsx")
    
    # Example usage with default file path
    update_item_attributes()

'''
Cach 1 : bench --site erp.tiqn.local  console
Using default file path : 
import custom_features.custom_features.bulk_update_scripts.update_item_attributes as update_script
update_script.update_item_attributes()

Cach 2 : bench --site erp.tiqn.local  console
Specifying a custom file path:
import custom_features.custom_features.bulk_update_scripts.update_item_attributes as update_script
update_script.update_item_attributes("/home/frappe/frappe-bench/sites/erp.tiqn.local/public//files/Item template.xlsx")
update_script.update_item_attributes("/home/frappe/frappe-bench/sites/erp.tiqn.local/public//files/Item templates - finished goods.xlsx")

Cach 3 : 
Using bench execute with default path:
bench execute custom_features.custom_features.bulk_update_scripts.update_item_attributes.update_item_attributes
'''