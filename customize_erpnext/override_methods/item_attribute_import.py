# Server-side approach for Item Attribute import handler
# Place this code in a custom app's Python module

import frappe
from frappe import _
import re

def get_next_code(max_code):
    """
    Generate the next code from the current maximum code
    Supports both 2-character and 3-character codes
    
    Args:
        max_code (str): Current maximum code
        
    Returns:
        str: Next code in the sequence
    """
    try:
        # Determine code length
        code_length = len(max_code) if max_code else 3
        
        # If max_code is empty or invalid, return default code
        if not max_code or (code_length != 2 and code_length != 3):
            return '00' if code_length == 2 else '000'
        
        # Define valid characters (0-9 and A-Z)
        valid_chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        
        # Convert current code to list of characters
        code_chars = list(max_code)
        
        # Start from the rightmost character
        position = code_length - 1
        carry = True
        
        # Process each character from right to left
        while position >= 0 and carry:
            # Get current character at this position
            current_char = code_chars[position]
            
            # Find its index in the valid characters
            current_index = valid_chars.find(current_char)
            
            if current_index == len(valid_chars) - 1:
                # If it's the last character (Z), reset to first (0) and carry
                code_chars[position] = '0'
                carry = True
            else:
                # Otherwise, increment to next character and stop carrying
                code_chars[position] = valid_chars[current_index + 1]
                carry = False
            
            # Move to the next position to the left
            position -= 1
        
        # If we still have a carry after processing all positions,
        # we've exceeded the maximum possible code (ZZ or ZZZ)
        if carry:
            frappe.log_error(_('Code sequence overflow, returning to {0}').format('0' * code_length))
            return '0' * code_length
        
        # Join the characters back into a string
        return ''.join(code_chars)
    except Exception as e:
        frappe.log_error(f'Error generating next code: {str(e)}')
        # Fallback is default code in case of error
        return '00' if max_code and len(max_code) == 2 else '000'

@frappe.whitelist()
def get_last_abbreviation(attribute_name):
    """
    Get the last abbreviation used for a specific attribute name
    
    Args:
        attribute_name (str): Name of the attribute (e.g., 'Color')
        
    Returns:
        str: Last abbreviation used or default based on attribute type
    """
    # Find existing attribute with this name
    existing_attr = frappe.get_all(
        'Item Attribute',
        filters={'attribute_name': attribute_name},
        fields=['name']
    )
    
    if existing_attr:
        # Get the attribute values of the existing attribute
        attr_doc = frappe.get_doc('Item Attribute', existing_attr[0].name)
        
        if attr_doc.item_attribute_values and len(attr_doc.item_attribute_values) > 0:
            # Sort by creation or idx to ensure we get the latest
            values = sorted(attr_doc.item_attribute_values, key=lambda x: x.idx)
            if values:
                return values[-1].abbr
    
    # Default abbreviation format based on attribute type
    if attribute_name in ["Color", "Size", "Info"]:
        return "000"  # 3-character code
    elif attribute_name in ["Brand", "Season"]:
        return "00"   # 2-character code
    else:
        return "000"  # Default to 3-character code

def before_import(data_import_doc):
    """Hook that runs before an import starts"""
    if data_import_doc.reference_doctype == "Item Attribute":
        frappe.msgprint(_("Auto-generating abbreviations for Item Attribute values."), alert=True)

def after_import(data_import_doc):
    """Hook that runs after an import completes"""
    if data_import_doc.reference_doctype == "Item Attribute":
        # Check for imported rows without abbreviations
        fix_missing_abbreviations(data_import_doc)

def fix_missing_abbreviations(data_import_doc):
    """
    Fix any imported Item Attribute values that don't have abbreviations
    
    Args:
        data_import_doc: Data Import document
    """
    # Get all imported attribute docs
    imported_rows = frappe.get_all(
        'Data Import Log',
        filters={
            'parent': data_import_doc.name,
            'success': 1,
            'docname': ['!=', '']
        },
        fields=['docname']
    )
    
    # Group by parent document
    attr_names = set()
    for row in imported_rows:
        # Extract the parent document name
        match = re.match(r'^(.+):.+$', row.docname)
        if match:
            attr_names.add(match.group(1))
        else:
            attr_names.add(row.docname)
    
    # Process each attribute
    for attr_name in attr_names:
        try:
            attr_doc = frappe.get_doc('Item Attribute', attr_name)
            
            # Check if any values are missing abbreviations
            values_without_abbr = [v for v in attr_doc.item_attribute_values if not v.abbr]
            
            if values_without_abbr:
                # Find the last used abbreviation
                existing_values = [v for v in attr_doc.item_attribute_values if v.abbr]
                last_abbr = None
                
                if existing_values:
                    # Sort by creation or idx
                    sorted_values = sorted(existing_values, key=lambda x: x.idx)
                    last_abbr = sorted_values[-1].abbr
                else:
                    # Get default based on attribute type
                    last_abbr = get_last_abbreviation(attr_doc.attribute_name)
                
                # Generate and set new abbreviations
                for value in values_without_abbr:
                    last_abbr = get_next_code(last_abbr)
                    value.abbr = last_abbr
                
                # Save the document
                attr_doc.save()
                frappe.db.commit()
                
                frappe.msgprint(_(
                    'Generated {0} abbreviations for attribute "{1}"'
                ).format(len(values_without_abbr), attr_doc.attribute_name))
                
        except Exception as e:
            frappe.log_error(
                f'Error fixing abbreviations for Item Attribute {attr_name}: {str(e)}',
                'Item Attribute Import Fix'
            )

# Hook implementation: Add to your app's hooks.py
"""
# hooks.py example

# Data import hooks
data_import_before_import = [
    "your_app.item_attribute_import.before_import"
]

data_import_after_import = [
    "your_app.item_attribute_import.after_import"
]
"""