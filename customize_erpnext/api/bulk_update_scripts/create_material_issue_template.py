import frappe
import pandas as pd
import os
from datetime import datetime

@frappe.whitelist()
def create_material_issue_template():
    """Tạo file Excel template và trả về URL để download, khớp với file đính kèm với 10 dòng dữ liệu mẫu và thứ tự cột chính xác."""
    try:
        # Sample data for the 'Data' sheet, khớp với file đính kèm
        sample_data = [
            {
                'No': 1,
                'posting_date': '2025-04-09',
                'posting_time': '17:00:00',
                'custom_no': 'PX010884',
                'custom_material_issue_purpose': 'Md',
                'qty': 1,
                'custom_fg_style': 'M007J',
                'custom_fg_size': 'All Size',
                'custom_fg_qty': '',
                'custom_line': 'Md',
                'custom_fg_color': 'All Color',
                'custom_note': '',
                'custom_invoice_number': 'OV-TIQNVN-AIR 3. 20',
                'custom_item_name_detail': 'ST0452HMP-3D North Atlantic Vital 25Ss'
            },
            {
                'No': 2,
                'posting_date': '2025-04-09',
                'posting_time': '17:00:00',
                'custom_no': 'PX010884',
                'custom_material_issue_purpose': 'Md',
                'qty': 1,
                'custom_fg_style': 'M007J',
                'custom_fg_size': 'All Size',
                'custom_fg_qty': '',
                'custom_line': 'Md',
                'custom_fg_color': 'All Color',
                'custom_note': '',
                'custom_invoice_number': 'OV-TIQNVN-SEA 3.10',
                'custom_item_name_detail': 'AT0452HSMP-3D Forged Iron Vital 25Ss'
            },
            {
                'No': 3,
                'posting_date': '2025-04-17',
                'posting_time': '17:00:00',
                'custom_no': 'PX011045',
                'custom_material_issue_purpose': 'Md',
                'qty': 2,
                'custom_fg_style': 'M007J',
                'custom_fg_size': 'S',
                'custom_fg_qty': '',
                'custom_line': 'Md',
                'custom_fg_color': 'All Color',
                'custom_note': '',
                'custom_invoice_number': 'OV-TIQNVN-AIR 3. 20',
                'custom_item_name_detail': 'ST0452HMP-3D North Atlantic Vital 25Ss'
            },
            {
                'No': 4,
                'posting_date': '2025-04-17',
                'posting_time': '17:00:00',
                'custom_no': 'PX011045',
                'custom_material_issue_purpose': 'Md',
                'qty': 2,
                'custom_fg_style': 'M007J',
                'custom_fg_size': 'S',
                'custom_fg_qty': '',
                'custom_line': 'Md',
                'custom_fg_color': 'All Color',
                'custom_note': '',
                'custom_invoice_number': 'OV-TIQNVN-SEA 3.10',
                'custom_item_name_detail': 'AT0452HSMP-3D Iron Gate Vital 25Ss'
            },
            {
                'No': 5,
                'posting_date': '2025-05-19',
                'posting_time': '17:00:00',
                'custom_no': 'PX011291',
                'custom_material_issue_purpose': 'Sample',
                'qty': 1.5,
                'custom_fg_style': 'M007J',
                'custom_fg_size': '',
                'custom_fg_qty': '',
                'custom_line': 'Kttk',
                'custom_fg_color': 'Cherry Mahogany',
                'custom_note': '',
                'custom_invoice_number': 'OV-TIQNVN-AIR 3. 20',
                'custom_item_name_detail': 'ST0452HMP-3D Cherry Mahogany Vital 25Ss'
            },
            {
                'No': 6,
                'posting_date': '2025-05-19',
                'posting_time': '17:00:00',
                'custom_no': 'PX011291',
                'custom_material_issue_purpose': 'Sample',
                'qty': 1.5,
                'custom_fg_style': 'M007J',
                'custom_fg_size': '',
                'custom_fg_qty': '',
                'custom_line': 'Kttk',
                'custom_fg_color': 'Forged Iron',
                'custom_note': '',
                'custom_invoice_number': 'OV-TIQNVN-SEA 3.10',
                'custom_item_name_detail': 'AT0452HSMP-3D Forged Iron Vital 25Ss'
            },
            {
                'No': 7,
                'posting_date': '2025-05-26',
                'posting_time': '17:00:00',
                'custom_no': 'PX011082',
                'custom_material_issue_purpose': 'Pro',
                'qty': 60,
                'custom_fg_style': 'M007J',
                'custom_fg_size': 'All Size',
                'custom_fg_qty': 470,
                'custom_line': 'Sample',
                'custom_fg_color': 'Iron Forged/Cherry Mahogany',
                'custom_note': '',
                'custom_invoice_number': 'STIO,OV-TIVNQN-SEA 2.8',
                'custom_item_name_detail': '6055 5 6Mm Vital 25Ss'
            },
            {
                'No': 8,
                'posting_date': '2025-05-26',
                'posting_time': '17:00:00',
                'custom_no': 'PX011082',
                'custom_material_issue_purpose': 'Pro',
                'qty': 51,
                'custom_fg_style': 'M007J',
                'custom_fg_size': 'All Size',
                'custom_fg_qty': 400,
                'custom_line': 'Sample',
                'custom_fg_color': 'Iron Gate/North Atlantic',
                'custom_note': '',
                'custom_invoice_number': 'STIO,OV-TIVNQN-SEA 2.8',
                'custom_item_name_detail': '6055 5 6Mm Vital 25Ss'
            },
            {
                'No': 9,
                'posting_date': '2025-05-26',
                'posting_time': '17:00:00',
                'custom_no': 'PX011082',
                'custom_material_issue_purpose': 'Pro',
                'qty': 268,
                'custom_fg_style': 'M007J',
                'custom_fg_size': 'All Size',
                'custom_fg_qty': 470,
                'custom_line': 'Sample',
                'custom_fg_color': 'Iron Forged/Cherry Mahogany',
                'custom_note': '',
                'custom_invoice_number': 'IN-25-00233',
                'custom_item_name_detail': 'E79799 Black 20Mm Vital 25Ss'
            },
            {
                'No': 10,
                'posting_date': '2025-05-26',
                'posting_time': '17:00:00',
                'custom_no': 'PX011082',
                'custom_material_issue_purpose': 'Pro',
                'qty': 127.02,
                'custom_fg_style': 'M007J',
                'custom_fg_size': 'All Size',
                'custom_fg_qty': 400,
                'custom_line': 'Sample',
                'custom_fg_color': 'Iron Gate/North Atlantic',
                'custom_note': '',
                'custom_invoice_number': 'IN-25-00233',
                'custom_item_name_detail': 'E79799 Black 20Mm Vital 25Ss'
            }
        ]

        # Define the exact column order as per the attached file
        desired_column_order = [
            'No',
            'posting_date',
            'posting_time',
            'custom_no',
            'custom_material_issue_purpose',
            'qty',
            'custom_fg_style',
            'custom_fg_size',
            'custom_fg_qty',
            'custom_line',
            'custom_fg_color',
            'custom_note',
            'custom_invoice_number',
            'custom_item_name_detail'
        ]

        # Create DataFrame from sample data and ensure column order
        df = pd.DataFrame(sample_data)
        df = df[desired_column_order]  # Reindex DataFrame to enforce column order

        # Instructions data for the 'Instructions' sheet
        instructions_data = [
            ['Instructions'],
            ['INSTRUCTIONS FOR MATERIAL ISSUE IMPORT'],
            [''],
            ['Required Columns:'],
            ['custom_item_name_detail: Item identifier for searching items'],
            ['custom_no: Grouping number for Stock Entry'],
            ['qty: Quantity to issue (must be positive number)'],
            ['custom_invoice_number: Invoice number reference'],
            [''],
            ['Optional Columns:'],
            ['posting_date: Date in YYYY-MM-DD format (default: today)'],
            ['posting_time: Time in HH:MM:SS format (default: 08:00:00)'],
            ['custom_fg_style: Finished goods style'],
            ['custom_line: Production line'],
            ['custom_fg_color: Finished goods color'],
            ['custom_fg_size: Finished goods size'],
            ['custom_fg_qty: Finished goods quantity'],
            ['custom_material_issue_purpose: Purpose of material issue'],
            ['custom_note: Additional notes'],
            [''],
            ['Notes:'],
            ['- Items will be grouped by custom_no'],
            ['- Warehouse will be auto-detected from Item Default settings'],
            ['- Invoice numbers must exist in Stock Ledger Entry'],
            ['- System will validate available quantity before import'],
            ['- No column is auto-generated sequence number']
        ]

        # Create DataFrame for instructions
        instructions_df = pd.DataFrame(instructions_data, columns=['Instructions'])

        # Get the site path and define template directory and file path
        site_path = frappe.get_site_path()
        template_dir = os.path.join(site_path, "public", "files")
        if not os.path.exists(template_dir):
            os.makedirs(template_dir)

        template_filename = "import_material_issue_template.xlsx"
        template_path = os.path.join(template_dir, template_filename)

        # Create Excel file with multiple sheets
        with pd.ExcelWriter(template_path, engine='openpyxl') as writer:
            # Write 'Data' sheet
            df.to_excel(writer, sheet_name='Data', index=False)

            # Write 'Instructions' sheet without header
            instructions_df.to_excel(writer, sheet_name='Instructions', index=False, header=False)

            # Adjust column width for better readability
            workbook = writer.book
            
            # Format Data sheet
            data_worksheet = writer.sheets['Data']
            # Set column widths for Data sheet
            column_widths = {
                'A': 5,   # No
                'B': 12,  # posting_date
                'C': 12,  # posting_time
                'D': 12,  # custom_no
                'E': 25,  # custom_material_issue_purpose
                'F': 8,   # qty
                'G': 15,  # custom_fg_style
                'H': 15,  # custom_fg_size
                'I': 12,  # custom_fg_qty
                'J': 15,  # custom_line
                'K': 25,  # custom_fg_color
                'L': 20,  # custom_note
                'M': 25,  # custom_invoice_number
                'N': 40   # custom_item_name_detail
            }
            
            for col, width in column_widths.items():
                data_worksheet.column_dimensions[col].width = width

            # Format Instructions sheet
            instructions_worksheet = writer.sheets['Instructions']
            instructions_worksheet.column_dimensions['A'].width = 80

        # Return file URL
        file_url = f"/files/{template_filename}"
        return {
            "file_url": file_url,
            "file_path": template_path,
            "message": "Template created successfully with exact structure from attached file"
        }

    except Exception as e:
        frappe.log_error(f"Error creating Excel template: {str(e)}", "Excel Template Creation")
        frappe.throw(f"Error creating template: {str(e)}")