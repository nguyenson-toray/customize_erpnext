import frappe
from frappe import _

# Python code (get_role_profile)
@frappe.whitelist()
def get_role_profile(email=None):
    """
    Lấy role_profile_name và roles của user
    Args:
        email: Email của user. Nếu không có sẽ lấy user hiện tại
        
    Returns:
        dict: Thông tin roles của user
    """
    try:
        if not email:
            email = frappe.session.user
             
        # Lấy role_profile và roles
        user = frappe.get_doc('User', email)
        role_profile = user.role_profile_name
        roles = [role.role for role in user.roles]
        # return role_profile
        return {
            'role_profile': role_profile,
            'roles': roles,
            'has_item_manager_role': 'Item Manager' in roles
        }
        
    except Exception as e:
        frappe.log_error(f"Error in get_role_profile: {str(e)}")
        return None
    
# Get color options for the selected item template 

@frappe.whitelist()
def get_colors_for_template(item_template):
    """Get all colors for an item template"""
    colors = frappe.db.sql("""
        SELECT DISTINCT attribute_value 
        FROM `tabItem Variant Attribute` 
        WHERE attribute = 'Color' 
        AND parent IN (
            SELECT name 
            FROM `tabItem` 
            WHERE variant_of = %s
        )
    """, item_template, as_list=1)
    
    return [color[0] for color in colors] if colors else []

def get_item_default_warehouse(item_code):
    """Get default warehouse for an item"""
    try:
        # Get the first default warehouse from item_defaults
        default_warehouse = frappe.db.sql("""
            SELECT default_warehouse
            FROM `tabItem Default`
            WHERE parent = %s
            AND default_warehouse IS NOT NULL
            ORDER BY idx
            LIMIT 1
        """, item_code, as_dict=True)
        
        return default_warehouse[0].default_warehouse if default_warehouse else None
    except Exception:
        return None

@frappe.whitelist()
def export_master_data_item_attribute():
    """Export master data item attributes to Excel file"""
    import io
    import base64
    from datetime import datetime
    
    try:
        # Import openpyxl
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
            from openpyxl.worksheet.table import Table, TableStyleInfo
        except ImportError:
            frappe.throw(_("openpyxl library is required for Excel export"))
        
        # Create workbook
        wb = Workbook()
        
        # Remove default sheet
        wb.remove(wb.active)
        
        # Create Item sheet
        item_sheet = wb.create_sheet("Item")
        
        # Item sheet headers
        item_headers = [
            'Item Code', 'Item Name', 'Item Name Detail', 'Item Group', 
            'Default Unit of Measure', 'Color', 'Size', 'Brand', 
            'Season', 'Info', 'Default Warehouse', 'Bin Qty', 'Creation'
        ]
        
        # Add headers to Item sheet
        for col, header in enumerate(item_headers, 1):
            cell = item_sheet.cell(row=1, column=col)
            cell.value = header
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center')
        
        # Get all items with their attributes
        items_data = frappe.db.sql("""
            SELECT 
                i.item_code,
                i.item_name,
                i.custom_item_name_detail,
                i.item_group,
                i.stock_uom,
                i.creation
            FROM `tabItem` i
            WHERE i.disabled = 0
            ORDER BY i.item_code ASC
        """, as_dict=True)
        
        # Define attribute order
        attribute_order = ['Color', 'Size', 'Brand', 'Season', 'Info']
        
        # Process each item
        for row_num, item in enumerate(items_data, 2):
            # Get item attributes
            item_attributes = frappe.db.sql("""
                SELECT attribute, attribute_value
                FROM `tabItem Variant Attribute`
                WHERE parent = %s
                ORDER BY idx
            """, item.item_code, as_dict=True)
            
            # Create attribute dictionary
            attr_dict = {}
            for attr in item_attributes:
                attr_dict[attr.attribute] = attr.attribute_value
            
            # Get bin quantity
            bin_qty = frappe.db.sql("""
                SELECT SUM(actual_qty) as total_qty
                FROM `tabBin`
                WHERE item_code = %s
            """, item.item_code, as_dict=True)
            
            total_qty = bin_qty[0].total_qty if bin_qty and bin_qty[0].total_qty else 0
            
            # Get default warehouse for this item
            default_warehouse = get_item_default_warehouse(item.item_code)
            
            # Fill item data
            item_sheet.cell(row=row_num, column=1).value = item.item_code
            item_sheet.cell(row=row_num, column=2).value = item.item_name
            item_sheet.cell(row=row_num, column=3).value = item.custom_item_name_detail
            item_sheet.cell(row=row_num, column=4).value = item.item_group
            item_sheet.cell(row=row_num, column=5).value = item.stock_uom
            
            # Fill attributes in order
            for idx, attr_name in enumerate(attribute_order):
                col = 6 + idx  # Start from column 6 (Color)
                item_sheet.cell(row=row_num, column=col).value = attr_dict.get(attr_name, '')
            
            # Fill warehouse and bin qty
            item_sheet.cell(row=row_num, column=11).value = default_warehouse
            item_sheet.cell(row=row_num, column=12).value = total_qty
            
            # Fill creation time
            item_sheet.cell(row=row_num, column=13).value = item.creation
        
        # Format Item sheet as table
        if len(items_data) > 0:
            item_table = Table(
                displayName="ItemTable",
                ref=f"A1:M{len(items_data) + 1}"
            )
            # Add style
            item_table.tableStyleInfo = TableStyleInfo(
                name="TableStyleMedium9",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=True,
                showColumnStripes=False
            )
            item_sheet.add_table(item_table)
        
        # Create Attribute sheet
        attr_sheet = wb.create_sheet("Attribute")
        
        # Get all attribute values for each attribute type
        col = 1
        for attr_name in attribute_order:
            # Add attribute name header for abbreviation column
            cell = attr_sheet.cell(row=1, column=col)
            cell.value = f"{attr_name} Abbr"
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center')
            
            # Add attribute name header for value column
            cell = attr_sheet.cell(row=1, column=col + 1)
            cell.value = f"{attr_name} Value"
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center')
            
            # Get all values for this attribute with abbreviation from Item Attribute Value
            attr_values = frappe.db.sql("""
                SELECT DISTINCT iav.abbr, iav.attribute_value
                FROM `tabItem Attribute Value` iav
                WHERE iav.parent = %s
                ORDER BY iav.abbr ASC
            """, attr_name, as_dict=True)
            
            # Add abbreviations and values in separate columns
            for row_num, value in enumerate(attr_values, 2):
                if value:
                    # Abbreviation column
                    attr_sheet.cell(row=row_num, column=col).value = value.abbr or ''
                    # Value column
                    attr_sheet.cell(row=row_num, column=col + 1).value = value.attribute_value or ''
            
            # Format each attribute pair as table
            if len(attr_values) > 0:
                # Get column letters
                start_col = chr(64 + col)  # Convert to letter (A, B, C, etc.)
                end_col = chr(64 + col + 1)
                
                attr_table = Table(
                    displayName=f"{attr_name}Table",
                    ref=f"{start_col}1:{end_col}{len(attr_values) + 1}"
                )
                # Add style
                attr_table.tableStyleInfo = TableStyleInfo(
                    name="TableStyleMedium2",
                    showFirstColumn=False,
                    showLastColumn=False,
                    showRowStripes=True,
                    showColumnStripes=False
                )
                attr_sheet.add_table(attr_table)
            
            # Move to next pair of columns (skip one column for spacing)
            col += 3
        
        # Auto-adjust column widths
        for sheet in [item_sheet, attr_sheet]:
            for column in sheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                sheet.column_dimensions[column_letter].width = adjusted_width
        
        # Save to memory
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        # Convert to base64
        xlsx_data = output.getvalue()
        output.close()
        
        # Create filename with current date
        filename = f"Master_Data_Item_Attribute_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        # Return file data
        return {
            'file_data': base64.b64encode(xlsx_data).decode(),
            'filename': filename,
            'items_count': len(items_data)
        }
        
    except Exception as e:
        frappe.log_error(f"Error in export_master_data_item_attribute: {str(e)}")
        frappe.throw(_("Error generating Excel file: {0}").format(str(e)))


