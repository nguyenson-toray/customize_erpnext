import frappe
import pandas as pd
import os
from frappe.utils import cstr
import re

@frappe.whitelist()
def validate_item_variants_data(file_path=None, file_url=None):
    """
    Validate Excel file data before creating item variants.
    This helps identify potential issues before running the main script.
    
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
    
    if not file_path:
        file_path = "/home/frappe/frappe-bench/sites/erp.tiqn.local/public/files/create_item_variants_improved_template.xlsx"
    
    # Ensure we have absolute path
    if not os.path.isabs(file_path):
        file_path = os.path.abspath(file_path)
    
    def check_item_exists(item_code):
        """
        Check if an item exists in the database.
        Uses the same logic as the creation script to ensure consistency.
        
        Args:
            item_code (str): Item code to check
            
        Returns:
            bool: True if item exists, False otherwise
        """
        try:
            # Try multiple methods to check existence
            exists1 = frappe.db.get_value("Item", item_code, "name")
            exists2 = frappe.db.exists("Item", item_code)
            
            # Test with one specific item for detailed debugging
            if item_code == "C-00V-05X-000-05-0B":
                print(f"DETAILED DEBUG for {item_code}:")
                print(f"  get_value result: {exists1}")
                print(f"  exists result: {exists2}")
                
                # Try to get the actual document
                try:
                    item_doc = frappe.get_doc("Item", item_code)
                    print(f"  get_doc success: {item_doc.name}, disabled: {item_doc.disabled}")
                except Exception as e:
                    print(f"  get_doc failed: {e}")
            
            return bool(exists1)
        except Exception as e:
            if item_code == "C-00V-05X-000-05-0B":
                print(f"DEBUG: Error checking item {item_code}: {e}")
            return False
    
    def get_attribute_abbreviation(attribute_name, attribute_value):
        """Get attribute abbreviation based on attribute value."""
        try:
            if not attribute_value:
                return ""
            
            abbr = frappe.db.get_value(
                "Item Attribute Value",
                {
                    "parent": attribute_name,
                    "attribute_value": attribute_value
                },
                "abbr"
            )
            
            return cstr(abbr) if abbr else ""
            
        except Exception:
            return ""
    
    def template_has_attribute(template_item_code, attribute_name):
        """Check if template item has a specific attribute."""
        try:
            has_attr = frappe.db.get_value(
                "Item Variant Attribute",
                {
                    "parent": template_item_code,
                    "attribute": attribute_name
                },
                "name"
            )
            
            return bool(has_attr)
            
        except Exception:
            return False
    
    def find_template_by_item_name(item_name):
        """Find template item by item name."""
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
            
            # If no exact match, try to find by item_code
            template = frappe.db.get_value(
                "Item",
                {
                    "name": item_name,
                    "has_variants": 1
                },
                "name"
            )
            
            return template
            
        except Exception:
            return None
    
    def clean_and_join_values(values, separator=" "):
        """Clean values by removing empty/None values. Note: "Blank" is a valid value."""
        clean_values = []
        for value in values:
            if value and cstr(value).strip():
                clean_values.append(cstr(value).strip())
        
        result = separator.join(clean_values)
        result = re.sub(r'\s+', ' ', result).strip()
        
        return result
    
    def clean_and_join_abbreviations(abbr_list):
        """Clean abbreviations by removing empty values, then join with dash."""
        clean_abbrs = []
        for abbr in abbr_list:
            if abbr and cstr(abbr).strip():
                clean_abbrs.append(cstr(abbr).strip())
        
        return "-".join(clean_abbrs)
    
    try:
        print(f"Validating Excel file: {file_path}")
        
        # Check if file exists
        if not os.path.exists(file_path):
            print(f"❌ Error: File not found at {file_path}")
            return
            
        df = pd.read_excel(file_path)
        print(f"✅ Successfully read Excel file with {len(df)} rows")
        
        # Validation results
        validation_results = []
        missing_templates = set()
        missing_attributes = {}
        duplicate_variants = set()
        
        print("\n🔍 Validating data...")
        print("-" * 60)
        
        # Process each row for validation
        for index, row in df.iterrows():
            row_num = index + 2  # Excel row number (accounting for header)
            issues = []
            
            # Extract data from the row
            item_name = cstr(row.get("Item Name", "")).strip()
            color_value = cstr(row.get("Attribute Color - Value", "")).strip()
            size_value = cstr(row.get("Attribute Size - Value", "")).strip()
            brand_value = cstr(row.get("Attribute Brand - Value", "")).strip()
            season_value = cstr(row.get("Attribute Season - Value", "")).strip()
            info_value = cstr(row.get("Attribute Info - Value", "")).strip()
            
            # If no value provided or value is "nan", default to "Blank"
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
            
            # Validate item name
            if not item_name:
                issues.append("❌ Item Name is missing")
            else:
                # Check if template exists
                template_item_code = find_template_by_item_name(item_name)
                if not template_item_code:
                    issues.append(f"❌ Template not found for '{item_name}'")
                    missing_templates.add(item_name)
                else:
                    # Validate attribute abbreviations
                    attributes_to_check = [
                        ("Color", color_value),
                        ("Size", size_value), 
                        ("Brand", brand_value),
                        ("Season", season_value)
                    ]
                    
                    # Only check Info if template has Info attribute
                    if template_has_attribute(template_item_code, "Info"):
                        attributes_to_check.append(("Info", info_value))
                    
                    missing_abbr = []
                    for attr_name, attr_value in attributes_to_check:
                        abbr = get_attribute_abbreviation(attr_name, attr_value)
                        if not abbr:
                            missing_abbr.append(f"{attr_name}:{attr_value}")
                            if attr_name not in missing_attributes:
                                missing_attributes[attr_name] = set()
                            missing_attributes[attr_name].add(attr_value)
                    
                    if missing_abbr:
                        issues.append(f"⚠️  Missing abbreviations for: {', '.join(missing_abbr)}")
                    
                    # Generate expected item_code (always include all attributes)
                    color_abbr = get_attribute_abbreviation("Color", color_value)
                    size_abbr = get_attribute_abbreviation("Size", size_value)
                    brand_abbr = get_attribute_abbreviation("Brand", brand_value)
                    season_abbr = get_attribute_abbreviation("Season", season_value)
                    
                    abbr_list = [color_abbr, size_abbr, brand_abbr, season_abbr]
                    
                    # Only include Info if template has Info attribute
                    if template_has_attribute(template_item_code, "Info"):
                        info_abbr = get_attribute_abbreviation("Info", info_value)
                        abbr_list.append(info_abbr)
                    
                    item_code_suffix = clean_and_join_abbreviations(abbr_list)
                    
                    if item_code_suffix:
                        expected_item_code = f"{template_item_code}-{item_code_suffix}"
                    else:
                        expected_item_code = template_item_code
                    
                    # Check if variant already exists - use consistent logic
                    if check_item_exists(expected_item_code):
                        issues.append(f"❌ Variant '{expected_item_code}' already exists")
                        duplicate_variants.add(expected_item_code)
                    
                    # Generate expected custom_item_name_detail
                    value_list = [color_value, size_value, brand_value, season_value]
                    
                    # Only include Info if template has Info attribute
                    if template_has_attribute(template_item_code, "Info"):
                        value_list.append(info_value)
                    
                    expected_detail = f"{item_name} {clean_and_join_values(value_list, ' ')}"
                    expected_detail = expected_detail.strip()
                    
                    if not issues:
                        issues.append(f"✅ Will create: {expected_item_code}")
                        issues.append(f"   Detail: {expected_detail}")
            
            validation_results.append({
                "row": row_num,
                "item_name": item_name,
                "issues": issues
            })
        
        # Print validation summary
        print(f"\n📊 VALIDATION SUMMARY")
        print("=" * 60)
        
        total_rows = len(df)
        valid_rows = sum(1 for result in validation_results if any("✅" in issue for issue in result["issues"]))
        invalid_rows = total_rows - valid_rows
        
        print(f"Total rows: {total_rows}")
        print(f"Valid rows: {valid_rows}")
        print(f"Invalid rows: {invalid_rows}")
        
        # Print issues
        if missing_templates:
            print(f"\n❌ Missing Templates ({len(missing_templates)}):")
            for template in sorted(missing_templates):
                print(f"   - {template}")
        
        if missing_attributes:
            print(f"\n⚠️  Missing Attribute Abbreviations:")
            for attr_name, values in missing_attributes.items():
                print(f"   {attr_name}: {', '.join(sorted(values))}")
        
        if duplicate_variants:
            print(f"\n❌ Duplicate Variants ({len(duplicate_variants)}):")
            for variant in sorted(duplicate_variants):
                print(f"   - {variant}")
        
        # Show detailed results for problem rows
        print(f"\n🔍 DETAILED VALIDATION RESULTS")
        print("=" * 60)
        
        for result in validation_results:
            if any("❌" in issue or "⚠️" in issue for issue in result["issues"]):
                print(f"\nRow {result['row']}: {result['item_name']}")
                for issue in result["issues"]:
                    print(f"   {issue}")
        
        # Show some successful examples
        print(f"\n✅ SUCCESSFUL EXAMPLES (first 5)")
        print("=" * 60)
        success_count = 0
        for result in validation_results:
            if any("✅" in issue for issue in result["issues"]) and success_count < 5:
                print(f"\nRow {result['row']}: {result['item_name']}")
                for issue in result["issues"]:
                    if "✅" in issue or "Detail:" in issue:
                        print(f"   {issue}")
                success_count += 1
        
        # Create validation report file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        report_file = os.path.join(script_dir, "create_item_variants_improved_validate_data_result.txt")
        
        with open(report_file, "w", encoding="utf-8") as f:
            f.write("ITEM VARIANTS VALIDATION REPORT\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"File: {file_path}\n")
            f.write(f"Total rows: {total_rows}\n")
            f.write(f"Valid rows: {valid_rows}\n")
            f.write(f"Invalid rows: {invalid_rows}\n\n")
            
            if missing_templates:
                f.write(f"Missing Templates ({len(missing_templates)}):\n")
                for template in sorted(missing_templates):
                    f.write(f"   - {template}\n")
                f.write("\n")
            
            if missing_attributes:
                f.write("Missing Attribute Abbreviations:\n")
                for attr_name, values in missing_attributes.items():
                    f.write(f"   {attr_name}: {', '.join(sorted(values))}\n")
                f.write("\n")
            
            if duplicate_variants:
                f.write(f"Duplicate Variants ({len(duplicate_variants)}):\n")
                for variant in sorted(duplicate_variants):
                    f.write(f"   - {variant}\n")
                f.write("\n")
            
            f.write("Detailed Results:\n")
            f.write("-" * 30 + "\n")
            for result in validation_results:
                f.write(f"\nRow {result['row']}: {result['item_name']}\n")
                for issue in result["issues"]:
                    f.write(f"   {issue}\n")
        
        print(f"\n📄 Validation report saved to: {report_file}")
        
        if invalid_rows == 0:
            print(f"\n🎉 All data is valid! Ready to create {valid_rows} item variants.")
            print("💡 Expected item code format: TEMPLATE-COLOR-SIZE-BRAND-SEASON-INFO (with dash separators)")
        else:
            print(f"\n⚠️  Found {invalid_rows} rows with issues. Please fix them before running the creation script.")
        
        return {
            "total_rows": total_rows,
            "valid_rows": valid_rows,
            "invalid_rows": invalid_rows,
            "missing_templates": list(missing_templates),
            "missing_attributes": {k: list(v) for k, v in missing_attributes.items()},
            "duplicate_variants": list(duplicate_variants)
        }
    
    except Exception as e:
        print(f"❌ Error during validation: {str(e)}")
        print(f"Error details: {frappe.get_traceback()}")
        return None


@frappe.whitelist()
def download_template():
    """
    Download the Excel template file for creating item variants.
    
    Returns:
        dict: Contains file_data (base64) and filename
    """
    try:
        # Get the template file path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(script_dir, "create_item_variants_improved_template.xlsx")
        
        # Check if file exists
        if not os.path.exists(template_path):
            frappe.throw("Template file not found")
        
        # Read file and encode as base64
        import base64
        with open(template_path, "rb") as f:
            file_data = base64.b64encode(f.read()).decode('utf-8')
        
        return {
            "file_data": file_data,
            "filename": "create_item_variants_template.xlsx"
        }
        
    except Exception as e:
        frappe.throw(f"Error downloading template: {str(e)}")


if __name__ == "__main__":
    # This is just for local testing
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        validate_item_variants_data(file_path)
    else:
        print("Please provide Excel file path as argument")


'''
Usage instructions:
bench --site erp.tiqn.local console
import customize_erpnext.api.bulk_update_scripts.create_item_variants_improved_validate_data as validate_script
validate_script.validate_item_variants_data()
or
validate_script.validate_item_variants_data("/home/frappe/frappe-bench/sites/erp.tiqn.local/public/files/create_item_variants_improved_template.xlsx")

This validation script will:
1. Check if all templates exist
2. Validate attribute abbreviations exist  
3. Check for duplicate variants
4. Generate expected item codes with dash separators (TEMPLATE-COLOR-SIZE-BRAND-SEASON-INFO)
5. Check if templates have Info attribute before validating Info values
6. Create a detailed validation report
7. Show summary of issues and successful examples
8. Note: "Blank" is treated as a valid attribute value

Run this BEFORE running the main creation script to identify and fix issues early.
'''