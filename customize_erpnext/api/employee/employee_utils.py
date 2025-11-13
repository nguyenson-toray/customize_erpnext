import frappe
import re
import os
import base64
import math
import json
from frappe import _
from frappe.utils.file_manager import save_file
from frappe.utils.pdf import get_pdf
from frappe.utils import get_site_path
from frappe.utils import getdate, nowdate, cint, flt, get_files_path, cstr
import io
from datetime import datetime
try:
    from PIL import Image
except:
    Image = None
try:
    import barcode
    from barcode.writer import ImageWriter
except:
    barcode = None

@frappe.whitelist()
def get_next_employee_code():
    """Generate next employee code in TIQN-XXXX format"""
    # Use SQL to get the highest employee number with proper numeric ordering
    result = frappe.db.sql("""
        SELECT employee
        FROM tabEmployee 
        WHERE employee LIKE 'TIQN-%'
        ORDER BY CAST(SUBSTRING(employee, 6) AS UNSIGNED) DESC
        LIMIT 1
    """, as_dict=True)
    
    if not result:
        return "TIQN-0001"
    
    highest_employee = result[0].employee
    
    # Extract number from the highest employee code
    match = re.match(r'TIQN-(\d+)', highest_employee)
    if match:
        current_num = int(match.group(1))
        next_num = current_num + 1
        next_code = f"TIQN-{next_num:04d}"
        return next_code
    
    # Fallback if pattern doesn't match
    return "TIQN-0001"

@frappe.whitelist() 
def get_next_attendance_device_id():
    """Generate next attendance_device_id"""
    # Get maximum attendance_device_id
    result = frappe.db.sql("""
        SELECT MAX(CAST(attendance_device_id AS UNSIGNED)) as max_id 
        FROM tabEmployee 
        WHERE attendance_device_id IS NOT NULL 
        AND attendance_device_id != ''
        AND attendance_device_id REGEXP '^[0-9]+$'
    """, as_dict=True)
    
    max_id = result[0].max_id if result and result[0].max_id else 0
    return str(max_id + 1)

@frappe.whitelist()
def set_series(prefix, current_highest_id):
    """Set naming series to prevent duplicate auto-generated IDs"""
    try:
        # Always update the series value using direct SQL
        frappe.db.sql("""
            UPDATE tabSeries SET current = %s WHERE name = %s
        """, (current_highest_id, prefix))
        frappe.db.commit()
        return {"status": "success", "message": f"Series {prefix} updated to {current_highest_id}"}
        
    except Exception as e:
        frappe.log_error(f"Error updating series {prefix}: {str(e)}")
        return {"status": "error", "message": str(e)}

@frappe.whitelist()
def check_duplicate_employee(employee_code, current_doc_name=None):
    """Check if employee code already exists"""
    filters = {"employee": employee_code}
    if current_doc_name:
        filters["name"] = ["!=", current_doc_name]
    
    existing = frappe.db.exists("Employee", filters)
    return {"exists": bool(existing), "employee_code": employee_code}

@frappe.whitelist()
def check_duplicate_attendance_device_id(attendance_device_id, current_doc_name=None):
    """Check if attendance device ID already exists"""
    if not attendance_device_id:
        return {"exists": False, "attendance_device_id": attendance_device_id}

    filters = {"attendance_device_id": attendance_device_id}
    if current_doc_name:
        filters["name"] = ["!=", current_doc_name]

    existing = frappe.db.exists("Employee", filters)
    return {"exists": bool(existing), "attendance_device_id": attendance_device_id}


@frappe.whitelist()
def upload_employee_image(employee_id, employee_name, file_content, file_name):
    """
    Upload and save employee image to fixed path /private/files/employee_image/{name}_{full_name}.jpg
    Args:
        employee_id: Employee ID (name field)
        employee_name: Employee full name
        file_content: Base64 encoded image data
        file_name: Original file name
    """
    try:
        # Decode base64 image
        if ',' in file_content:
            # Remove data:image/jpeg;base64, prefix if present
            file_content = file_content.split(',')[1]

        file_data = base64.b64decode(file_content)

        # Clean up employee name for file path
        clean_name = employee_name.replace(' ', '_') if employee_name else 'employee'
        clean_name = re.sub(r'[^\w\-_]', '', clean_name)

        # Create fixed file name: {employee_id}_{full_name}.jpg
        final_file_name = f"{employee_id}_{clean_name}.jpg"

        # Create directory path: /private/files/employee_image/
        site_path = frappe.utils.get_site_path()
        employee_image_dir = os.path.join(site_path, 'private', 'files', 'employee_image')

        # Create directory if it doesn't exist
        if not os.path.exists(employee_image_dir):
            os.makedirs(employee_image_dir, exist_ok=True)

        # Full file path
        file_path = os.path.join(employee_image_dir, final_file_name)

        # Save file to disk
        with open(file_path, 'wb') as f:
            f.write(file_data)

        # Create File document in Frappe
        # Use relative path from site directory
        relative_path = f'/private/files/employee_image/{final_file_name}'

        # Check if file record already exists
        existing_file = frappe.db.exists('File', {
            'file_url': relative_path
        })

        if existing_file:
            # Update existing file record
            file_doc = frappe.get_doc('File', existing_file)
            file_doc.file_size = len(file_data)
            file_doc.save(ignore_permissions=True)
        else:
            # Create new file record
            file_doc = frappe.get_doc({
                'doctype': 'File',
                'file_name': final_file_name,
                'file_url': relative_path,
                'is_private': 1,
                'folder': 'Home',  # Use default Home folder
                'attached_to_doctype': 'Employee',
                'attached_to_name': employee_id,
                'attached_to_field': 'image',
                'file_size': len(file_data)
            })
            file_doc.insert(ignore_permissions=True)

        frappe.db.commit()

        return {
            'status': 'success',
            'file_url': relative_path,
            'file_name': final_file_name,
            'message': 'Image uploaded successfully'
        }

    except Exception as e:
        frappe.log_error(f"Error uploading employee image: {str(e)}", "Employee Image Upload Error")
        frappe.throw(_("Failed to upload employee image: {0}").format(str(e)))


@frappe.whitelist()
def generate_employee_cards_pdf(employee_ids, with_barcode=0, page_size='A4', name_font_size=18, max_length_font_20=20):
    """
    Generate PDF containing employee cards with layout:
    - A4 portrait: 2 columns, 5 rows (10 cards per page)
    - A5 landscape: 2 columns, 2 rows (4 cards per page)
    - Card size: 86mm x 54mm
    - Left column (30mm): company logo (30mm) + employee photo (30mm x 40mm) + optional barcode
    - Right column: Full name (uppercase, bold, customizable font size), employee code (bold, 18pt), custom_section (bold, 18pt)

    Args:
        max_length_font_20: Max name length to use 20pt font (default: 20)
        name_font_size: Font size for names >= max_length_font_20 (default: 18)
    """
    import tempfile
    import datetime
    import traceback

    try:
        if isinstance(employee_ids, str):     
            employee_ids = json.loads(employee_ids)

        # Convert with_barcode to boolean
        with_barcode = int(with_barcode) == 1

        # Validate page_size
        if page_size not in ['A4', 'A5']:
            page_size = 'A4'

        # Validate and convert name_font_size to int
        try:
            name_font_size = int(name_font_size) if name_font_size else 18
            # Only allow specific values: 19, 18, 17, 16
            if name_font_size not in [19, 18, 17, 16]:
                name_font_size = 18
        except (ValueError, TypeError):
            name_font_size = 18

        # Validate and convert max_length_font_20 to int
        try:
            max_length_font_20 = int(max_length_font_20) if max_length_font_20 else 20
            # Ensure it's in reasonable range
            if max_length_font_20 < 10 or max_length_font_20 > 50:
                max_length_font_20 = 20
        except (ValueError, TypeError):
            max_length_font_20 = 20

        frappe.logger().info(f"Generating employee cards for {len(employee_ids)} employees (page_size={page_size}, name_font_size={name_font_size}pt, max_length_font_20={max_length_font_20})")

        # Get employee data
        employees = []
        for emp_id in employee_ids:
            try:
                emp = frappe.get_doc('Employee', emp_id)
                employees.append({
                    'name': emp.name,
                    'employee_name': emp.employee_name or '',
                    'custom_section': emp.custom_section or '',
                    'image': emp.image or ''
                })
                frappe.logger().info(f"Added employee {emp_id}, image: {emp.image}")
            except Exception as emp_err:
                frappe.logger().error(f"Error loading employee {emp_id}: {str(emp_err)}")
                continue

        if not employees:
            frappe.throw(_("No valid employees found"))
        if len(employees) %2 != 0:
            # Ensure even number of employees for duplex printing
            employees.append({
                'name': '',
                'employee_name': '',
                'custom_section': '',
                'image': ''
            })
            frappe.logger().info("Added placeholder employee to make even count")
        # Generate HTML for cards
        frappe.logger().info(f"Generating HTML for employee cards (with_barcode={with_barcode}, page_size={page_size}, name_font_size={name_font_size}pt, max_length_font_20={max_length_font_20})")
        html = generate_employee_cards_html(employees, with_barcode=with_barcode, page_size=page_size, name_font_size=name_font_size, max_length_font_20=max_length_font_20)

        # Debug: Save HTML to file for inspection (uncomment if needed)
        # html_path = f'/tmp/employee_cards_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.html'
        # with open(html_path, 'w', encoding='utf-8') as f:
        #     f.write(html)
        # frappe.logger().info(f"HTML saved to {html_path}")

        # Convert HTML to PDF with better error handling
        frappe.logger().info("Converting HTML to PDF")
        try:
            # Set PDF options based on page size
            # CRITICAL: Margins must match CSS @page margins
            pdf_options = {
                'page-size': page_size,
                'orientation': 'Landscape' if page_size == 'A5' else 'Portrait',
                'margin-top': '5mm',
                'margin-bottom': '5mm',
                'margin-left': '5mm',
                'margin-right': '5mm',
                'encoding': 'UTF-8',
                'no-outline': None,
                'enable-local-file-access': None,  # Allow loading local images
                'dpi': 96,  # Standard DPI
                'zoom': 1.0,  # NO SCALING
                'disable-smart-shrinking': None  # Prevent auto-shrinking
            }
            pdf_data = get_pdf(html, pdf_options)
        except Exception as pdf_err:
            error_msg = str(pdf_err)
            frappe.logger().error(f"PDF generation error: {error_msg}")
            frappe.logger().error(traceback.format_exc())
            frappe.throw(_("PDF generation failed: {0}").format(error_msg))

        if not pdf_data:
            frappe.throw(_("PDF generation returned empty data"))

        frappe.logger().info(f"PDF generated successfully, size: {len(pdf_data)} bytes")

        # Generate filename with timestamp
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        pdf_filename = f'employee_cards_{timestamp}.pdf'

        # Convert to base64 for client download
        pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')

        frappe.logger().info(f"Employee cards PDF created: {pdf_filename}")

        return {
            'status': 'success',
            'pdf_data': pdf_base64,
            'pdf_filename': pdf_filename,
            'message': f'Generated {len(employees)} employee cards'
        }

    except Exception as e:
        error_trace = traceback.format_exc()
        frappe.logger().error(f"Error generating employee cards PDF: {str(e)}\n{error_trace}")
        frappe.log_error(f"Error: {str(e)}\n\nTraceback:\n{error_trace}", "Employee Cards PDF Error")
        frappe.throw(_("Failed to generate employee cards PDF: {0}").format(str(e)))

def get_employee_reissue_count(employee_id):
    """Get the reissue count for an employee from Employee Item Reissue doctype"""
    # Default is 1 for first issuance
    reissue_number = 1
    
    # Query the Employee Item Reissue doctype to get the latest reissue count
    reissue_records = frappe.get_all(
        "Employee Item Reissue",
        filters={"employee": employee_id},
        fields=["reissue_count"],
        order_by="reissue_count desc",
        limit=1
    )
    
    # If reissue records exist, add 1 to the highest reissue_count
    if reissue_records and reissue_records[0].get("reissue_count"):
        reissue_number = reissue_records[0].get("reissue_count") + 1
    
    return reissue_number

def generate_employee_cards_html(employees, with_barcode=False, page_size='A4', name_font_size=18, max_length_font_20=20):
    """
    Generate HTML for employee cards with proper layout
    - A4: portrait, 2x5 layout
    - A5: landscape, 2x2 layout
    - name_font_size: font size for long names (default 18pt)
    - max_length_font_20: threshold for switching to smaller font (default 20)
    """
    # Get company logo
    company_logo = get_company_logo()

    # Determine page orientation and size
    page_orientation = 'landscape' if page_size == 'A5' else 'portrait'

    # CSS for card layout
    # Card size: 86mm x 53mm (EXACT - NO SCALING)
    # Page A4: 210mm x 297mm, A5 landscape: 210mm x 148mm
    # With margins 5mm: 210 - 10 = 200mm (usable width)
    # A4: 297 - 10 = 287mm (usable height) - 5 rows with 0.5mm gap
    # A5: 148 - 10 = 138mm (usable height) - 2 rows with 2mm gap

    css = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        @page {{
            size: {page_size} {page_orientation};
            margin: 5mm;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        html, body {{
            font-family: 'Times New Roman', Times, serif;
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
        }}

        .cards-container {{
            width: 173mm;
            margin: 0 auto;
            padding: 0;
        }}

        .card-row {{
            width: 173mm;
            height: 53mm;
            margin: 0;
            clear: both;
            page-break-inside: avoid;
            display: block;
        }}

        .card-row:not(:last-child) {{
            margin-bottom: {'1mm' if page_size == 'A5' else '0.5mm'};
        }}

        .card {{
            width: 86mm;
            height: 53mm;
            border: 1px solid #333;
            padding: 1mm;
            margin: 0 1mm 0 0;
            float: left;
            background: white;
            position: relative;
            overflow: hidden;
            box-sizing: border-box;
            page-break-inside: avoid;
        }}

        .card:nth-child(2n) {{
            margin-right: 0;
        }}

        .card-inner {{
            width: 100%;
            height: 100%;
            position: relative;
        }}

        .card-left {{
            width: 28mm;
            float: left;
            margin-right: 1mm;
        }}

        .company-logo {{
            width: 28mm;
            height: auto;
            margin-top: 1mm;            
            object-fit: contain;
            margin-bottom: 1mm;
            display: block;
        }}
        .employee-photo {{
            width: 28mm;
            height: 37.33mm;
            margin-top: 4mm;
            object-fit: cover;
            border: 1px solid #999;
            display: block;
            background: #f5f5f5;
        }}

        .card-right {{
            margin-left: 5mm;
            padding-top: 9mm;
            padding-left: 0.5mm;
            padding-right: 0.5mm;
            padding-bottom: 2mm;
            text-align: left;
        }}

        .employee-barcode {{
            width: 28mm;
            height: auto;
            max-height: 5mm;
            margin-top: 0mm;
            display: block;
        }}

        .employee-name {{
            text-align: center;
            font-size: 20pt !important;
            font-weight: bold;
            text-transform: uppercase;
            margin: 0 0 3mm 0;
            line-height: 1.3;
            word-wrap: break-word;
            color: #000;
            width: 100%;
        }}

        .employee-name.long-name {{
            font-size: {name_font_size}pt !important;
        }}

        .employee-code {{
            font-size: 18pt !important;
            font-weight: normal;
            margin: 0 0 3mm 0;
            line-height: 1.3;
            color: #000;
            text-align: center;
        }}

        .employee-section {{
            font-size: 18pt !important;
            font-weight: normal;
            margin: 0;
            line-height: 1.3;
            color: #000;
            text-align: center;
        }}

        .employee-section.long-section {{
            font-size: 14pt !important;
        }}

        .page-break {{
            page-break-after: always;
            clear: both;
        }}

        .clearfix {{
            clear: both;
        }}

        /* Back side styles */
        .card-back {{
            width: 86mm;
            height: 53mm;
            border: none;
            padding: 3mm;
            margin: 0 1mm 0 0;
            float: left;
            background: white;
            position: relative;
            overflow: hidden;
            box-sizing: border-box;
            page-break-inside: avoid;
        }}

        .card-back:nth-child(2n) {{
            margin-right: 0;
        }}

        .card-back-title {{
            font-size: 13pt;
            font-weight: bold;
            text-align: center;
            margin-bottom: 2mm;
            color: #000;
        }}

        .card-back-content {{
            font-size: 8.5pt;
            line-height: 1.3;
            text-align: left;
            color: #000;
        }}

        .card-back-content ol {{
            margin: 0;
            padding-left: 5mm;
        }}

        .card-back-content li {{
            margin-bottom: 1mm;
        }}

        .card-back-content ul {{
            margin-top: 0.5mm;
            padding-left: 5mm;
        }}
        #reissue-number{{
            position: absolute;
            bottom: 0;
            right: 1mm;
            font-size: 8px;
        }}
        
    </style>
    </head>
    """

    # Generate HTML for cards
    html_parts = [css, '<body><div class="cards-container">']

    # Determine cards per page based on page size
    # A4: 2 columns x 5 rows = 10 cards
    # A5: 2 columns x 2 rows = 4 cards
    cards_per_page = 4 if page_size == 'A5' else 10
    rows_per_page = 2 if page_size == 'A5' else 5
    total_cards_on_page = cards_per_page  # 2 cards per row

    for page_idx in range(0, len(employees), cards_per_page):
        page_employees = employees[page_idx:page_idx + cards_per_page]

        # FRONT SIDE: Create rows
        for row_idx in range(0, total_cards_on_page, 2):  # 2 cards per row
            html_parts.append('<div class="card-row">')

            # Add 2 cards per row
            for col_idx in range(2):
                emp_idx = row_idx + col_idx
                if emp_idx < len(page_employees):
                    emp = page_employees[emp_idx]
                    card_html = generate_single_card_html(emp, company_logo, with_barcode, max_length_font_20)
                    html_parts.append(card_html)
                else:
                    # Empty card to maintain layout
                    html_parts.append('<div class="card" style="visibility: hidden;"></div>')

            html_parts.append('<div class="clearfix"></div>')
            html_parts.append('</div>')  # end card-row

        # Page break before back side
        # html_parts.append('<div class="page-break"></div>')

        # BACK SIDE: Rules (mirror layout for duplex printing)
        for row_idx in range(0, total_cards_on_page, 2):
            html_parts.append('<div class="card-row">')

            # Add 2 card backs per row - always show barcode on back
            for col_idx in range(2):
                emp_idx = row_idx + col_idx
                if emp_idx < len(page_employees):
                    emp = page_employees[emp_idx]
                    card_back_html = generate_card_back_html(emp)
                    html_parts.append(card_back_html)
                else:
                    # Empty card to maintain layout
                    html_parts.append('<div class="card-back" style="visibility: hidden;"></div>')

            html_parts.append('<div class="clearfix"></div>')
            html_parts.append('</div>')  # end card-row

        # Add page break if not last batch
        if page_idx + cards_per_page < len(employees):
            html_parts.append('<div class="page-break"></div>')

    html_parts.append('</div></body></html>')  # end cards-container, body, html

    return ''.join(html_parts)


def generate_single_card_html(employee, company_logo, with_barcode=False, max_length_font_20=20):
    """Generate HTML for a single employee card with customizable name length threshold"""

    # Get employee image URL - always returns a valid base64 image or placeholder
    emp_image_url = get_full_image_url(employee.get('image', ''))

    # Escape HTML special characters in text
    employee_name = frappe.utils.escape_html(employee.get('employee_name', ''))
    employee_code = frappe.utils.escape_html(employee.get('name', ''))
    employee_section = frappe.utils.escape_html(employee.get('custom_section', ''))

    # Get the reissue number for this employee
    reissue_number = get_employee_reissue_count(employee_code)
    reissue_display = reissue_number if reissue_number > 1 else ''

    # New logic: use max_length_font_20 as threshold
    name_class = 'employee-name'
    name_html = employee_name
    name_length = len(employee_name)

    # Rule 1: Name >= max_length_font_20 -> use smaller font (long-name class)
    if name_length >= max_length_font_20:
        name_class = 'employee-name long-name'

    # Rule 2: Name < 13 chars -> add extra line
    if name_length < 13:
        name_html = f'{employee_name}<br/>&nbsp;'

    # Section logic: >= 19 chars -> use smaller font size
    section_class = 'employee-section'
    section_length = len(employee_section)
    if section_length >= 19:
        section_class = 'employee-section long-section'

    # Generate barcode HTML if requested
    barcode_html = ''
    if with_barcode:
        barcode_data_uri = generate_barcode_code39(employee_code)
        barcode_html = f'<img src="{barcode_data_uri}" class="employee-barcode" alt="Barcode" />'

    card = f'''
    <div class="card">
        <div class="card-inner">
            <div class="card-left">
                <img src="{company_logo}" class="company-logo" alt="Company Logo" />
                <img src="{emp_image_url}" class="employee-photo" alt="Employee Photo" />
                {barcode_html}
            </div>
            <div class="card-right">
                <div class="{name_class}">{name_html}</div>
                <div class="employee-code">{employee_code}</div>
                <div class="{section_class}">{employee_section}</div>
                
            </div>
            <div id="reissue-number"> {reissue_display} </div>
        </div>
    </div>
    '''
    return card


def generate_card_back_html(employee):
    """Generate HTML for card back side with rules"""
    rules_html = '''
    <div class="card-back">
        <div class="card-back-title">QUY ĐỊNH SỬ DỤNG THẺ</div>
        <div class="card-back-content">
            <ol>
                <li>Luôn đeo thẻ khi ra/vào cổng, trong suốt thời gian làm việc và đi công tác</li>
                <li>Không được phép cho người khác mượn thẻ</li>
                <li>Thẻ là tài sản của công ty, do đó:
                    <ul style="margin-top: 1mm; padding-left: 5mm;">
                        <li>Phải được bảo quản cẩn thận</li>
                        <li>Khi thôi việc phải hoàn trả cho công ty</li>
                        <li>Nhặt được xin vui lòng gửi về phòng HCNS</li>
                    </ul>
                </li>
            </ol>
        </div>
    </div>
    '''
    return rules_html


def generate_barcode_code39(code):
    """Generate Code39 barcode as base64 data URI"""
    try:
        if barcode is None:
            frappe.logger().warning("python-barcode library not installed, using placeholder")
            return generate_barcode_placeholder(code)

        # Clean code for Code39 (only uppercase letters, numbers, and some symbols)
        clean_code = str(code).upper()

        # Create Code39 barcode
        from barcode import Code39

        # Generate barcode without text (we'll show it separately)
        barcode_instance = Code39(clean_code, writer=ImageWriter(), add_checksum=False)

        # Save to BytesIO
        buffer = io.BytesIO()
        barcode_instance.write(buffer, {
            'module_width': 0.2,  # Width of narrowest bar
            'module_height': 5.0,  # Height in mm (5mm as required)
            'quiet_zone': 1,      # Minimal quiet zone
            'font_size': 0,       # No text in barcode
            'text_distance': 1,
            'background': 'white',
            'foreground': 'black',
            'write_text': False,  # Don't write text
        })

        # Get image data
        buffer.seek(0)
        img_data = buffer.read()

        # Convert to base64
        base64_data = base64.b64encode(img_data).decode('utf-8')
        return f'data:image/png;base64,{base64_data}'

    except Exception as e:
        frappe.logger().error(f"Error generating barcode: {str(e)}")
        return generate_barcode_placeholder(code)


def generate_barcode_placeholder(code):
    """Generate a simple barcode placeholder SVG"""
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="50" viewBox="0 0 400 50">
        <rect fill="white" width="400" height="50"/>
        <text fill="black" font-size="12" x="200" y="25" text-anchor="middle" dominant-baseline="middle" font-family="monospace">{code}</text>
    </svg>'''

    svg_bytes = svg.encode('utf-8')
    base64_svg = base64.b64encode(svg_bytes).decode('utf-8')
    return f'data:image/svg+xml;base64,{base64_svg}'


def get_company_logo():
    """Get company logo from fixed path /private/files/logo.png"""
    # Always use fixed logo path
    logo_path = '/private/files/logo.png'
    frappe.logger().info(f"Using fixed logo path: {logo_path}")

    try:
        logo_base64 = get_full_image_url(logo_path, is_logo=True)

        # Check if logo was loaded successfully (not a placeholder)
        if logo_base64 and 'LOGO' not in logo_base64:
            frappe.logger().info("Successfully loaded logo from /private/files/logo.png")
            return logo_base64
        else:
            frappe.logger().warning("Logo file not found at /private/files/logo.png, using placeholder")
            return get_placeholder_image('logo')

    except Exception as e:
        import traceback
        frappe.logger().error(f"Error loading logo: {str(e)}\n{traceback.format_exc()}")
        frappe.log_error(f"Error loading logo: {str(e)}\n{traceback.format_exc()}", "Company Logo Error")
        return get_placeholder_image('logo')


def get_full_image_url(file_url, is_logo=False):
    """Convert relative file URL to base64 data URI for PDF embedding"""
    if not file_url:
        return get_placeholder_image('logo' if is_logo else 'no-photo')

    # If already a data URI, return as is
    if file_url.startswith('data:'):
        return file_url

    # Convert file path to base64 for embedding in PDF
    try:
        site_path = get_site_path()
        file_path = None

        # Handle both private and public files
        if file_url.startswith('/private/'):
            file_path = os.path.join(site_path, file_url.lstrip('/'))
        elif file_url.startswith('/files/'):
            file_path = os.path.join(site_path, 'public', file_url.lstrip('/'))
        elif file_url.startswith('http'):
            # Download remote image
            import requests
            response = requests.get(file_url, timeout=5)
            if response.status_code == 200:
                image_data = response.content
                image_type = 'jpeg'
                if 'image/png' in response.headers.get('Content-Type', ''):
                    image_type = 'png'
                base64_data = base64.b64encode(image_data).decode('utf-8')
                return f'data:image/{image_type};base64,{base64_data}'
        else:
            # Try as relative path from site/public
            file_path = os.path.join(site_path, 'public', file_url.lstrip('/'))

        if file_path and os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                image_data = f.read()

                # Determine image type from file extension
                image_type = 'jpeg'
                if file_url.lower().endswith('.png'):
                    image_type = 'png'
                elif file_url.lower().endswith('.gif'):
                    image_type = 'gif'
                elif file_url.lower().endswith('.svg'):
                    image_type = 'svg+xml'

                base64_data = base64.b64encode(image_data).decode('utf-8')
                return f'data:image/{image_type};base64,{base64_data}'
        else:
            frappe.log_error(f"Image file not found: {file_path}", "Image Not Found")
            return get_placeholder_image('logo' if is_logo else 'no-photo')

    except Exception as e:
        frappe.log_error(f"Error converting image to base64: {str(e)}\nFile URL: {file_url}", "Image Conversion Error")
        return get_placeholder_image('logo' if is_logo else 'error')

    # Fallback to placeholder
    return get_placeholder_image('logo' if is_logo else 'no-photo')


def get_placeholder_image(type='no-photo'):
    """Generate placeholder image as base64 data URI"""
    if type == 'no-photo':
        # 3:4 ratio placeholder (300x400)
        svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="300" height="400">
            <rect fill="#e0e0e0" width="300" height="400"/>
            <text fill="#999" font-size="20" x="50%" y="50%" text-anchor="middle" dominant-baseline="middle">No Photo</text>
        </svg>'''
    elif type == 'logo':
        # Logo placeholder
        svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="300" height="100">
            <rect fill="#007bff" width="300" height="100"/>
            <text fill="white" font-size="24" x="50%" y="50%" text-anchor="middle" dominant-baseline="middle">LOGO</text>
        </svg>'''
    else:  # error
        svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="300" height="400">
            <rect fill="#ffebee" width="300" height="400"/>
            <text fill="#c62828" font-size="18" x="50%" y="50%" text-anchor="middle" dominant-baseline="middle">Image Error</text>
        </svg>'''

    # Convert SVG to base64
    svg_bytes = svg.encode('utf-8')
    base64_svg = base64.b64encode(svg_bytes).decode('utf-8')
    return f'data:image/svg+xml;base64,{base64_svg}'


@frappe.whitelist()
def search_employees_by_codes(employee_codes):
    """
    Search employees by employee codes (name field only)
    Args:
        employee_codes: List of employee codes (name field) to search
    Returns:
        List of employee documents (name, employee_name)
    """
    try:
        if isinstance(employee_codes, str):
            employee_codes = json.loads(employee_codes)

        if not employee_codes:
            return []

        frappe.logger().info(f"Searching for employees by codes: {employee_codes}")

        found_employees = []
        not_found = []

        for code in employee_codes:
            code = code.strip()
            if not code:
                continue

            # Search by name field only (exact match)
            employee = frappe.db.get_value('Employee', {'name': code}, ['name', 'employee_name'], as_dict=True)

            if employee:
                found_employees.append({
                    'name': employee.name,
                    'employee_name': employee.employee_name or ''
                })
            else:
                # Not found
                not_found.append(code)

        # Log not found items
        if not_found:
            frappe.logger().warning(f"Employee codes not found: {not_found}")
            # Also inform user about not found codes
            if len(not_found) > 0:
                frappe.msgprint(
                    _("The following employee codes were not found: {0}").format(", ".join(not_found)),
                    title=_("Some Employees Not Found"),
                    indicator="orange"
                )

        frappe.logger().info(f"Found {len(found_employees)} employees out of {len(employee_codes)} codes")

        return found_employees

    except Exception as e:
        import traceback
        frappe.logger().error(f"Error searching employees: {str(e)}\n{traceback.format_exc()}")
        frappe.log_error(f"Error: {str(e)}\n{traceback.format_exc()}", "Employee Search Error")
        return []


@frappe.whitelist()
def get_file_content_base64(file_url):
    """
    Get file content as base64 for cropping
    Args:
        file_url: File URL to read
    Returns:
        Base64 encoded file content
    """
    try:
        site_path = get_site_path()
        file_path = None

        # Handle both private and public files
        if file_url.startswith('/private/'):
            file_path = os.path.join(site_path, file_url.lstrip('/'))
        elif file_url.startswith('/files/'):
            file_path = os.path.join(site_path, 'public', file_url.lstrip('/'))
        else:
            # Try as relative path from site/public
            file_path = os.path.join(site_path, 'public', file_url.lstrip('/'))

        if file_path and os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                file_data = f.read()

                # Determine image type from file extension
                image_type = 'jpeg'
                if file_url.lower().endswith('.png'):
                    image_type = 'png'
                elif file_url.lower().endswith('.gif'):
                    image_type = 'gif'
                elif file_url.lower().endswith('.jpg') or file_url.lower().endswith('.jpeg'):
                    image_type = 'jpeg'

                base64_data = base64.b64encode(file_data).decode('utf-8')
                return f'data:image/{image_type};base64,{base64_data}'
        else:
            frappe.throw(_("File not found: {0}").format(file_url))

    except Exception as e:
        frappe.log_error(f"Error reading file: {str(e)}", "File Read Error")
        frappe.throw(_("Failed to read file: {0}").format(str(e)))


@frappe.whitelist()
def update_employee_photo(employee_id, employee_name, new_file_url, old_file_url=None):
    """
    Update employee photo - rename file to '{name} {full_name}' format and delete old file
    Args:
        employee_id: Employee ID (name field)
        employee_name: Employee full name
        new_file_url: URL of newly uploaded file
        old_file_url: URL of old file to delete (optional)
    Returns:
        Success status and new file name
    """
    try:
        # Log input for debugging
        frappe.logger().info(f"update_employee_photo called: employee_id={employee_id}, new_file_url={new_file_url}, old_file_url={old_file_url}")

        # IMPORTANT: Don't delete old file yet, because new_file_url might reference the same File document
        # if the filename happens to be the same. We'll delete it later after we've renamed the new file.

        # Get site path
        site_path = get_site_path()

        # First, find the uploaded file's actual path from File document
        # The new_file_url might be the file_name returned from upload, not the actual URL
        uploaded_file_doc = None

        # Try to find by file_url first
        uploaded_file_doc = frappe.db.get_value('File', {'file_url': new_file_url}, ['name', 'file_url', 'file_name'], as_dict=True)

        # If not found, try to find by file_name (in case new_file_url is actually the file name)
        if not uploaded_file_doc:
            uploaded_file_doc = frappe.db.get_value('File', {'file_name': new_file_url}, ['name', 'file_url', 'file_name'], as_dict=True)

        # Also try searching for recently created files
        if not uploaded_file_doc:
            # Get most recent file uploaded (within last 5 minutes)
            from frappe.utils import now_datetime, add_to_date
            recent_time = add_to_date(now_datetime(), minutes=-5)
            recent_files = frappe.get_all('File',
                filters={
                    'creation': ['>=', recent_time],
                },
                fields=['name', 'file_url', 'file_name'],
                order_by='creation desc',
                limit=20
            )

            # Try to match by filename
            for f in recent_files:
                if new_file_url in f.get('file_url', '') or new_file_url in f.get('file_name', ''):
                    uploaded_file_doc = f
                    break

        if not uploaded_file_doc:
            frappe.logger().error(f"File document not found for URL/name: {new_file_url}")
            return {
                'success': False,
                'error': f'File document not found in database: {new_file_url}'
            }

        actual_file_url = uploaded_file_doc.get('file_url')

        # Determine uploaded file's physical path
        uploaded_file_path = None
        if actual_file_url.startswith('/private/'):
            uploaded_file_path = os.path.join(site_path, actual_file_url.lstrip('/'))
        elif actual_file_url.startswith('/files/'):
            uploaded_file_path = os.path.join(site_path, 'public', actual_file_url.lstrip('/'))
        else:
            # Handle relative paths
            uploaded_file_path = os.path.join(site_path, 'public', 'files', actual_file_url.lstrip('/'))

        if not uploaded_file_path or not os.path.exists(uploaded_file_path):
            frappe.logger().error(f"Uploaded file not found on disk: {actual_file_url}, tried: {uploaded_file_path}")
            return {
                'success': False,
                'error': f'Uploaded file not found on disk'
            }

        # Get file extension from uploaded file
        file_ext = os.path.splitext(uploaded_file_path)[1] or '.jpg'

        # Create new file name: "{employee_id} {employee_name}.ext"
        new_file_name = f"{employee_id} {employee_name}{file_ext}"

        # Create new file path in employee_photos directory
        # Determine base directory (public or private)
        if '/private/' in uploaded_file_path:
            target_dir = os.path.join(site_path, 'private', 'files', 'employee_photos')
        else:
            target_dir = os.path.join(site_path, 'public', 'files', 'employee_photos')

        # Create directory if it doesn't exist
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        new_file_path = os.path.join(target_dir, new_file_name)

        # Rename file on disk
        if uploaded_file_path != new_file_path:
            # If file with new name exists, delete it first (in case of re-upload)
            if os.path.exists(new_file_path):
                os.remove(new_file_path)
                frappe.logger().info(f"Deleted existing file: {new_file_path}")

            os.rename(uploaded_file_path, new_file_path)
            frappe.logger().info(f"Renamed file from {uploaded_file_path} to {new_file_path}")

        # Determine new file URL based on directory
        if '/private/' in uploaded_file_path:
            new_file_url_updated = f"/private/files/employee_photos/{os.path.basename(new_file_path)}"
        else:
            new_file_url_updated = f"/files/employee_photos/{os.path.basename(new_file_path)}"

        # Update File document
        file_doc = frappe.get_doc('File', uploaded_file_doc['name'])
        file_doc.file_name = new_file_name
        file_doc.file_url = new_file_url_updated
        file_doc.attached_to_doctype = 'Employee'
        file_doc.attached_to_name = employee_id
        file_doc.attached_to_field = 'image'
        file_doc.save(ignore_permissions=True)

        # Update Employee image field
        frappe.db.set_value('Employee', employee_id, 'image', new_file_url_updated)

        # NOW delete old file if exists and it's different from the new one
        if old_file_url and old_file_url != new_file_url_updated:
            try:
                # Delete physical file first
                old_physical_path = None
                if old_file_url.startswith('/private/'):
                    old_physical_path = os.path.join(site_path, old_file_url.lstrip('/'))
                elif old_file_url.startswith('/files/'):
                    old_physical_path = os.path.join(site_path, 'public', old_file_url.lstrip('/'))

                if old_physical_path and os.path.exists(old_physical_path):
                    os.remove(old_physical_path)
                    frappe.logger().info(f"Deleted old physical file: {old_physical_path}")

                # Then delete File document
                old_file_doc = frappe.db.get_value('File', {'file_url': old_file_url}, 'name')
                if old_file_doc and old_file_doc != uploaded_file_doc.get('name'):
                    frappe.delete_doc('File', old_file_doc, ignore_permissions=True, force=True)
                    frappe.logger().info(f"Deleted old file document: {old_file_url}")
            except Exception as e:
                frappe.logger().warning(f"Could not delete old file {old_file_url}: {str(e)}")

        frappe.db.commit()

        return {
            'success': True,
            'new_file_name': new_file_name,
            'new_file_url': new_file_url_updated
        }

    except Exception as e:
        frappe.logger().error(f"Error updating employee photo: {str(e)}")
        frappe.log_error(f"Error: {str(e)}", "Update Employee Photo Error")
        return {
            'success': False,
            'error': str(e)
        }


@frappe.whitelist()
def process_employee_photo(employee_id, employee_name, image_data, remove_bg=0):
    """
    Process employee photo: crop to 3:4 ratio, resize to 450x600px, optionally remove background
    Save to public/files/employee_photos/{employee_id} {employee_name}.jpg

    Args:
        employee_id: Employee ID (name field)
        employee_name: Employee full name
        image_data: Base64 encoded image data (already cropped by frontend)
        remove_bg: Whether to remove background (0 or 1, default: 0)

    Returns:
        Dict with file_url and success status
    """
    try:
        # Validate PIL availability
        if Image is None:
            frappe.throw(_("PIL (Pillow) library is not installed"))

        # Decode base64 image
        if ',' in image_data:
            # Remove data:image/jpeg;base64, prefix if present
            image_data = image_data.split(',')[1]

        file_data = base64.b64decode(image_data)

        # Open image with PIL
        img = Image.open(io.BytesIO(file_data))

        # Convert to RGB if necessary (remove alpha channel)
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Resize to exactly 450x600px (image should already be 3:4 ratio from frontend crop)
        img = img.resize((450, 600), Image.Resampling.LANCZOS)

        # Remove background if requested (convert to int for safety)
        remove_bg = int(remove_bg) if remove_bg else 0
        if remove_bg == 1:
            try:
                from rembg import remove

                # Convert PIL image to bytes
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                img_byte_arr = img_byte_arr.getvalue()

                # Remove background
                output = remove(img_byte_arr)

                # Convert back to PIL Image
                img_no_bg = Image.open(io.BytesIO(output))

                # Create white background
                background = Image.new('RGB', img_no_bg.size, (255, 255, 255))

                # Paste image with removed background onto white background
                if img_no_bg.mode == 'RGBA':
                    background.paste(img_no_bg, mask=img_no_bg.split()[-1])
                else:
                    background.paste(img_no_bg)

                img = background

            except ImportError:
                frappe.msgprint(_("rembg library not installed, skipping background removal"), indicator="orange")
            except Exception as bg_error:
                frappe.log_error(f"Error removing background: {str(bg_error)}", "Background Removal Error")
                frappe.msgprint(_("Failed to remove background, using original image"), indicator="orange")

        # Save to BytesIO with JPEG compression
        output_buffer = io.BytesIO()
        img.save(output_buffer, format='JPEG', quality=85, optimize=True)
        output_data = output_buffer.getvalue()

        # Clean up employee name for file path
        clean_name = employee_name.replace(' ', ' ') if employee_name else 'employee'
        # Remove invalid filename characters but keep Vietnamese characters
        clean_name = re.sub(r'[<>:"/\\|?*]', '', clean_name)

        # Create file name: {employee_id} {employee_name}.jpg
        final_file_name = f"{employee_id} {clean_name}.jpg"

        # Get site path
        site_path = get_site_path()

        # Create directory: public/files/employee_photos/
        employee_photos_dir = os.path.join(site_path, 'public', 'files', 'employee_photos')

        # Create directory if it doesn't exist
        if not os.path.exists(employee_photos_dir):
            os.makedirs(employee_photos_dir, exist_ok=True)

        # Full file path
        file_path = os.path.join(employee_photos_dir, final_file_name)

        # Get old file URL to delete later
        old_file_url = frappe.db.get_value('Employee', employee_id, 'image')

        # Delete ALL old files attached to this employee's image field
        # This includes: old photo + any temporary uploaded files
        try:
            # Get all File documents attached to this employee's image field
            old_files = frappe.get_all('File',
                filters={
                    'attached_to_doctype': 'Employee',
                    'attached_to_name': employee_id,
                    'attached_to_field': 'image'
                },
                fields=['name', 'file_url', 'file_name']
            )

            for old_file in old_files:
                try:
                    # Delete physical file
                    old_physical_path = None
                    if old_file.file_url.startswith('/private/'):
                        old_physical_path = os.path.join(site_path, old_file.file_url.lstrip('/'))
                    elif old_file.file_url.startswith('/files/'):
                        old_physical_path = os.path.join(site_path, 'public', old_file.file_url.lstrip('/'))

                    if old_physical_path and os.path.exists(old_physical_path):
                        os.remove(old_physical_path)
                        frappe.logger().info(f"Deleted old file: {old_physical_path}")

                    # Delete File document
                    frappe.delete_doc('File', old_file.name, ignore_permissions=True, force=True)
                    frappe.logger().info(f"Deleted File document: {old_file.file_name}")

                except Exception as del_err:
                    frappe.logger().warning(f"Could not delete file {old_file.file_name}: {str(del_err)}")

            # Also search and delete any physical files matching this employee in both locations
            # (to clean up orphaned files that may not have File documents)
            try:
                # Search in /files/ directory
                files_dir = os.path.join(site_path, 'public', 'files')
                # Search in /files/employee_photos/ directory
                employee_photos_dir = os.path.join(site_path, 'public', 'files', 'employee_photos')

                for search_dir in [files_dir, employee_photos_dir]:
                    if os.path.exists(search_dir):
                        # Find files matching pattern: {employee_id} *.jpg
                        import glob
                        pattern = os.path.join(search_dir, f"{employee_id} *.jpg")
                        matching_files = glob.glob(pattern)

                        for file_to_delete in matching_files:
                            if os.path.exists(file_to_delete):
                                os.remove(file_to_delete)
                                frappe.logger().info(f"Deleted orphaned file: {file_to_delete}")
            except Exception as cleanup_err:
                frappe.logger().warning(f"Could not cleanup orphaned files: {str(cleanup_err)}")

        except Exception as del_err:
            frappe.logger().warning(f"Could not delete old files: {str(del_err)}")

        # Save file to disk
        with open(file_path, 'wb') as f:
            f.write(output_data)

        # Create file URL
        file_url = f'/files/employee_photos/{final_file_name}'

        # Create or update File document
        existing_file = frappe.db.exists('File', {'file_url': file_url})

        if existing_file:
            # Update existing file record
            file_doc = frappe.get_doc('File', existing_file)
            file_doc.file_size = len(output_data)
            file_doc.save(ignore_permissions=True)
        else:
            # Create new file record
            file_doc = frappe.get_doc({
                'doctype': 'File',
                'file_name': final_file_name,
                'file_url': file_url,
                'is_private': 0,
                'folder': 'Home',
                'attached_to_doctype': 'Employee',
                'attached_to_name': employee_id,
                'attached_to_field': 'image',
                'file_size': len(output_data)
            })
            file_doc.insert(ignore_permissions=True)

        # Update Employee image field
        frappe.db.set_value('Employee', employee_id, 'image', file_url)
        frappe.db.commit()

        return {
            'status': 'success',
            'file_url': file_url,
            'file_name': final_file_name,
            'message': _('Photo processed and saved successfully')
        }

    except Exception as e:
        frappe.logger().error(f"Error processing employee photo: {str(e)}")
        import traceback
        frappe.log_error(f"Error: {str(e)}\n{traceback.format_exc()}", "Employee Photo Processing Error")
        frappe.throw(_("Failed to process employee photo: {0}").format(str(e)))


@frappe.whitelist()
def allow_change_name_attendance_device_id(name):
    """
    Check if employee name and attendance_device_id can be changed
    Returns False if employee has existing checkin records, True otherwise

    Args:
        name: Employee ID (name field)

    Returns:
        bool: True if changes are allowed, False if employee has checkin data
    """
    if not name:
        return True

    # Check if employee has any checkin records
    checkin_exists = frappe.db.exists('Employee Checkin', {'employee': name})

    if checkin_exists:
        return False

    return True


@frappe.whitelist()
def debug_company_logo():
    """Debug method to check company logo"""
    result = []

    try:
        companies = frappe.get_all('Company', fields=['name'], limit=5)
        result.append(f"Found {len(companies)} companies")

        for company_info in companies:
            company_name = company_info['name']
            company_doc = frappe.get_doc('Company', company_name)

            result.append(f"\n=== Company: {company_name} ===")

            # List all fields with 'logo' or 'image' in name
            for field in company_doc.meta.fields:
                if 'logo' in field.fieldname.lower() or 'image' in field.fieldname.lower():
                    value = getattr(company_doc, field.fieldname, None)
                    result.append(f"  {field.fieldname}: {value}")

            # Try common fields
            for field_name in ['company_logo', 'logo', 'image', 'icon']:
                if hasattr(company_doc, field_name):
                    value = getattr(company_doc, field_name, None)
                    result.append(f"  {field_name} (direct): {value}")

        # Check default company
        default_company = frappe.defaults.get_user_default('Company')
        result.append(f"\nDefault company: {default_company}")

    except Exception as e:
        import traceback
        result.append(f"\nError: {str(e)}")
        result.append(traceback.format_exc())

    return "\n".join(result)


@frappe.whitelist()
def bulk_update_employee_holiday_list(employees, holiday_list):
    """
    Bulk update Holiday List cho nhiều Employee
    
    Args:
        employees: List các employee names (JSON string, list, hoặc 'all')
        holiday_list: Tên của Holiday List cần gán
    """
    # Xử lý employees parameter
    if employees == 'all':
        # Lấy tất cả nhân viên Active
        employees = frappe.get_all('Employee', 
            filters={'status': 'Active'},
            pluck='name'
        )
    elif isinstance(employees, str):
        employees = json.loads(employees)
    
    if not employees:
        frappe.throw(_("Vui lòng chọn ít nhất 1 nhân viên"))
    
    if not holiday_list:
        frappe.throw(_("Vui lòng chọn Holiday List"))
    
    # Kiểm tra Holiday List có tồn tại không
    if not frappe.db.exists("Holiday List", holiday_list):
        frappe.throw(_("Holiday List {0} không tồn tại").format(holiday_list))
    
    # Kiểm tra quyền
    if not frappe.has_permission("Employee", "write"):
        frappe.throw(_("Bạn không có quyền cập nhật Employee"))
    
    success_count = 0
    error_list = []
    updated_employees = []
    
    for emp_name in employees:
        try:
            # Kiểm tra employee tồn tại
            if not frappe.db.exists("Employee", emp_name):
                error_list.append(f"{emp_name}: Không tồn tại")
                continue
            
            # Get current holiday list
            current_holiday = frappe.db.get_value("Employee", emp_name, "holiday_list")
            
            # Update
            frappe.db.set_value(
                "Employee", 
                emp_name, 
                "holiday_list", 
                holiday_list,
                update_modified=True
            )
            
            updated_employees.append({
                "name": emp_name,
                "old_holiday": current_holiday,
                "new_holiday": holiday_list
            })
            
            success_count += 1
            
        except Exception as e:
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Lỗi cập nhật Holiday List cho {emp_name}"
            )
            error_list.append(f"{emp_name}: {str(e)}")
    
    frappe.db.commit()
    
    # Tạo message
    message = f" Đã cập nhật Holiday List <strong>{holiday_list}</strong> cho <strong>{success_count}/{len(employees)}</strong> nhân viên"
    
    if error_list:
        message += f"<br><br><b> Lỗi ({len(error_list)}):</b><br>" + "<br>".join(error_list[:10])
        if len(error_list) > 10:
            message += f"<br>... và {len(error_list) - 10} lỗi khác"
    
    return {
        "success": True,
        "message": message,
        "updated_count": success_count,
        "total_count": len(employees),
        "error_count": len(error_list),
        "updated_employees": updated_employees
    }

## Generate Employee List PDF ##

@frappe.whitelist()
def generate_employee_list_pdf(employees=None, company_name=None, include_department=1, 
                              include_section=0, include_notes=1, page_size='A4', 
                              orientation='Portrait'):
    """
    Generate a PDF list of employees with their photos and details
    
    Args:
        employees: List of employee IDs or 'all' for all active employees
        company_name: Title to display on the PDF
        include_department: Whether to include department column (0 or 1)
        include_section: Whether to include section column (0 or 1)
        include_notes: Whether to include notes column (0 or 1)
        page_size: A4 or Letter
        orientation: Portrait or Landscape
    
    Returns:
        dict: {
            'success': True/False,
            'file_url': URL to access the generated PDF,
            'filename': PDF filename
        }
    """
    try:
        # Convert parameters from strings to correct types
        include_department = cint(include_department)
        include_section = cint(include_section)
        include_notes = cint(include_notes)
        
        # Default company name if not provided
        if not company_name:
            company_name = frappe.db.get_single_value("Global Defaults", "default_company") or "Company"
        
        # Get employee data
        employee_data = get_employee_data(employees, include_department, include_section)
        
        # Write debugging info to a file (scope, count, etc.)
        debug_info = {
            "total_employees": len(employee_data),
            "with_images": sum(1 for e in employee_data if e.get('image_data')),
            "scope": "all" if employees == 'all' else (
                     "selected" if isinstance(employees, list) else "range"),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        debug_file_path = os.path.join(frappe.get_site_path(), "public", "files", "pdf_debug_info.json")
        with open(debug_file_path, "w") as f:
            json.dump(debug_info, f)
        
        # Maximum employees per page - 12 is recommended
        employees_per_page = 12
        
        # Calculate number of pages needed
        total_employees = len(employee_data)
        total_pages = math.ceil(total_employees / employees_per_page)
        
        # Generate HTML with proper pagination
        html = generate_employee_list_html(
            employee_data=employee_data,
            company_name=company_name,
            include_department=include_department,
            include_section=include_section,
            include_notes=include_notes,
            orientation=orientation,
            employees_per_page=employees_per_page,
            total_pages=total_pages
        )
        
        # Lưu HTML để xem trước
        debug_html_path = os.path.join(frappe.get_site_path(), "public", "files", "employee_list_debug.html")
        with open(debug_html_path, "w", encoding="utf-8") as f:
            f.write(html)
            
        # URL để xem trước HTML
        html_preview_url = f"/files/employee_list_debug.html"
        
        # Generate PDF
        pdf_options = {
            "page-size": page_size,
            "orientation": orientation.lower(),
            "margin-top": "15mm",
            "margin-bottom": "15mm",
            "margin-left": "10mm",
            "margin-right": "10mm",
            "print-media-type": True,
            "dpi": 300,
            "image-dpi": 300,  # Higher DPI for better image quality
            "enable-local-file-access": True
        }
        
        pdf_data = get_pdf(html, options=pdf_options)
        
        # Create filename based on timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Employee_List_{timestamp}.pdf"
        
        # IMPORTANT: Instead of returning Base64 data directly, save file to server
        # and return a URL for direct download - this prevents Base64 encoding issues
        output_path = os.path.join(frappe.get_site_path(), "public", "files", filename)
        with open(output_path, "wb") as f:
            f.write(pdf_data)
             
        # Generate URL for direct download
        file_url = f"/files/{filename}"
        
        # Return success with file URL instead of Base64 data
        return {
            'success': True,
            'file_url': file_url,
            'filename': filename,
            'preview_url': html_preview_url,
            'employee_count': len(employee_data)
        }
    
    except Exception as e:
        # Write the error to a debug file
        debug_file_path = os.path.join(frappe.get_site_path(), "public", "files", "pdf_error.txt")
        with open(debug_file_path, "w") as f:
            f.write(str(e))
        
        # Truncate error message
        error_msg = str(e)
        if len(error_msg) > 100:
            error_msg = error_msg[:97] + "..."
            
        return {
            'success': False, 
            'error': error_msg,
            'debug_file': debug_file_path
        }


def get_employee_data(employees=None, include_department=1, include_section=0):
    """
    Get employee data for the PDF
    
    Args:
        employees: List of employee IDs or 'all' for all active employees
        include_department: Whether to include department column
        include_section: Whether to include section column
    
    Returns:
        list: List of employee data dictionaries
    """
    fields = ["name", "employee_name", "image", "status"]
    
    if include_department:
        fields.append("department")
    
    # Initialize section_field variable outside the conditional block
    section_field = None
    
    if include_section:
        # Check if section is a standard or custom field
        section_field_options = ["section", "custom_section", "department_section"]
        
        for field in section_field_options:
            if frappe.db.exists("DocField", {"parent": "Employee", "fieldname": field}) or \
               frappe.db.exists("Custom Field", {"dt": "Employee", "fieldname": field}):
                section_field = field
                break
        
        if section_field:
            fields.append(section_field)
    
    # Build filters
    filters = {"status": "Active"}
    
    # Handle different employee selection methods
    if employees == 'all':
        # All active employees - keep the default filter
        pass
    elif isinstance(employees, str) and employees != 'all':
        # Try to parse JSON if it's a string but not 'all'
        try:           
            employees = json.loads(employees)
            filters = {
                "name": ["in", employees],
                "status": "Active"
            }
        except Exception as e:
            # If not JSON, treat as single employee ID
            filters = {
                "name": ["in", [employees]],
                "status": "Active"
            }
            frappe.logger().error(f"Error parsing employees parameter: {str(e)}")
    elif isinstance(employees, list):
        # Specific employees selected or range of IDs
        filters = {
            "name": ["in", employees],
            "status": "Active"  # Still filter for active only
        }
    elif employees:
        # Single employee ID - convert to list
        filters = {
            "name": ["in", [employees]],
            "status": "Active"
        }
    
    # Log the filters for debugging
    debug_file_path = os.path.join(frappe.get_site_path(), "public", "files", "filter_debug.json")
    with open(debug_file_path, "w") as f:
        json.dump({
            "filters": filters,
            "employees_type": str(type(employees)),
            "employees_value": str(employees)[:100] if employees else None
        }, f)
    
    # Fetch employee data
    employee_data = frappe.get_all(
        "Employee",
        fields=fields,
        filters=filters,
        order_by="name"
    )
    
    # Process employee images - with optimizations for size
    for emp in employee_data:
        # Try various methods to get the image
        image_result = process_employee_photo_optimized(emp.get("image"), emp.get("name"))
        
        emp["image_data"] = image_result
        
        # Map section field if found - now section_field is always defined
        if section_field and section_field in emp:
            emp["section"] = emp.get(section_field)
    
    return employee_data


def process_employee_photo_optimized(image_url, employee_id):
    """
    Process employee photo with optimizations for file size
    
    Args:
        image_url: URL of the employee image
        employee_id: Employee ID for direct lookup
        
    Returns:
        str: Base64 encoded image data or empty string
    """
    try:
        # Start with standard path processing
        if image_url:
            # Remove leading slash if present
            if image_url.startswith("/"):
                image_url = image_url[1:]
            
            # Get full path to image
            site_path = frappe.get_site_path()
            img_path = os.path.join(site_path, "public", image_url)
            
            # Check if file exists
            if not os.path.exists(img_path):
                # Try alternative path formats
                alt_paths = [
                    os.path.join(site_path, image_url),
                    os.path.join(get_files_path(), os.path.basename(image_url)),
                    os.path.join(site_path, "public", "files", os.path.basename(image_url)),
                    os.path.join(site_path, "public", "files", "employee_photos", os.path.basename(image_url)),
                    os.path.join(site_path, "private", "files", os.path.basename(image_url))
                ]
                
                for path in alt_paths:
                    if path and os.path.exists(path):
                        img_path = path
                        break
                else:
                    # Try to get from attachments
                    attachments = frappe.get_all(
                        "File",
                        fields=["file_url", "file_name"],
                        filters={
                            "attached_to_doctype": "Employee",
                            "attached_to_name": employee_id,
                            "is_private": 0
                        }
                    )
                    
                    for attachment in attachments:
                        file_url = attachment.get("file_url")
                        if file_url and file_url.lower().endswith(('.jpg', '.jpeg', '.png')):
                            img_path = os.path.join(site_path, "public", file_url.lstrip("/"))
                            if os.path.exists(img_path):
                                break
                    else:
                        # Generate a placeholder with initials
                        return generate_placeholder_image(employee_id)
        else:
            # No image URL, generate placeholder
            return generate_placeholder_image(employee_id)
                
        # Process the image with size optimizations
        try:
            # Open and resize image
            img = Image.open(img_path)
            
            # Calculate desired size - smaller size to reduce PDF file size
            # 1 inch = 2.54 cm
            # 2cm = (2/2.54) inches = (2/2.54)*300 pixels
            # 1.5cm = (1.5/2.54) inches = (1.5/2.54)*300 pixels
            width_px = int((2/2.54) * 300)  # Using 300 DPI instead of 300 for smaller file size
            height_px = int((1.5/2.54) * 300)
            
            # Resize maintaining aspect ratio
            img.thumbnail((width_px, height_px), Image.Resampling.LANCZOS)
            
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Convert to base64 with reduced quality for smaller size
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=60)  # Lower quality (60 instead of 95)
            img_str = base64.b64encode(buffered.getvalue()).decode()
            
            return img_str
        except Exception:
            # If image processing fails, create a placeholder
            return generate_placeholder_image(employee_id)
    except Exception:
        # Silent error handling - return placeholder on any error
        return generate_placeholder_image(employee_id)


def generate_placeholder_image(employee_id):
    """
    Generate a placeholder image for employees without photos
    
    Args:
        employee_id: Employee ID to generate placeholder for
        
    Returns:
        str: Base64 encoded placeholder image
    """
    try:
        # Get employee details for the placeholder
        employee = frappe.get_doc("Employee", employee_id)
        if not employee:
            return ""
            
        # Create a colorful placeholder with initials
        name_parts = employee.employee_name.split()
        initials = ''.join([part[0].upper() for part in name_parts if part])[:2]
        
        # Create colored background based on name hash
        name_hash = sum(ord(c) for c in employee.employee_name)
        colors = [
            (240, 98, 146),  # Pink
            (186, 104, 200),  # Purple
            (79, 195, 247),   # Blue
            (77, 182, 172),   # Teal
            (255, 213, 79),   # Yellow
            (255, 167, 38),   # Orange
            (229, 115, 115),  # Red
            (124, 179, 66)    # Green
        ]
        
        bg_color = colors[name_hash % len(colors)]
        text_color = (255, 255, 255)
        
        # Create the image - smaller size to reduce file size
        img_size = (120, 90)  # Reduced size (150 DPI instead of 300)
        img = Image.new('RGB', img_size, color=bg_color)
        
        # Add text
        try:
            from PIL import ImageDraw, ImageFont
            draw = ImageDraw.Draw(img)
            
            # Try to use a system font, fallback to default
            try:
                font_size = 40  # Smaller font
                # Try to find a suitable font
                font_paths = [
                    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',  # Linux
                    '/usr/share/fonts/TTF/Arial.ttf',  # Some Linux distros
                    '/Library/Fonts/Arial.ttf',  # MacOS
                    'C:\\Windows\\Fonts\\Arial.ttf'  # Windows
                ]
                
                font = None
                for path in font_paths:
                    if os.path.exists(path):
                        font = ImageFont.truetype(path, font_size)
                        break
                        
                if font is None:
                    font = ImageFont.load_default()
            except:
                font = ImageFont.load_default()
                
            # Calculate text position to center it
            text_width, text_height = draw.textsize(initials, font=font) if hasattr(draw, 'textsize') else (font_size, font_size)
            position = ((img_size[0] - text_width) // 2, (img_size[1] - text_height) // 2)
            
            # Draw the text
            draw.text(position, initials, fill=text_color, font=font)
        except:
            # If text drawing fails, just return a blank colored image
            pass
            
        # Convert to base64 with lower quality
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=60)
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return img_str
    except Exception:
        # Silent error handling - return empty string on any error
        return ""


def generate_employee_list_html(employee_data, company_name, include_department=1, 
                               include_section=0, include_notes=1, orientation="Portrait",
                               employees_per_page=12, total_pages=1):
    """
    Generate HTML for the employee list PDF with pagination
    
    Args:
        employee_data: List of employee data dictionaries
        company_name: Company name for the title
        include_department: Whether to include department column
        include_section: Whether to include section column
        include_notes: Whether to include notes column
        orientation: Page orientation
        employees_per_page: Number of employees per page
        total_pages: Total number of pages
    
    Returns:
        str: HTML content for the PDF
    """
    # Start HTML with CSS styling
    html = f"""
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Danh sách Nhân viên</title>
        <style>
            @page {{
                size: {orientation.lower()};
                margin: 15mm 10mm;
            }}
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 0;
                font-size: 10pt;
            }}
        
            .container {{
                width: 100%;
                margin: 0 auto;
            }}
            .header {{
                text-align: center;
                font-size: 14pt;
                font-weight: bold;
                margin-bottom: 20px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                page-break-inside: avoid;
            }}
            thead {{
                display: table-header-group;
            }}
            tr {{
                page-break-inside: avoid;
            }}
            th, td {{
                border: 1px solid #000;
                padding: 4px 6px;
                text-align: center;
                vertical-align: middle;
                font-size: 9pt;
            }}
            th {{
                background-color: #f2f2f2;
                font-weight: bold;
            }}
            .text-left {{
            text-align: left !important;
            }}
            .employee-photo-employee-list {{
                width: 20mm;
                height: 23.33mm !important;
                max-width: 20mm;
                max-height: 23.33mm !important;
                object-fit: contain;
            }}
            .centered {{
                text-align: center;
            }}
            .employee-id {{
                font-weight: bold;
            }}
            .page-number {{
                text-align: right;
                margin-top: 10px;
                font-size: 8pt;
            }}
            .no-results {{
                padding: 30px;
                text-align: center;
                font-size: 14pt;
                color: #888;
            }}
        </style>
    </head>
    <body>
    """
    
    # Handle case where no employees are found
    if len(employee_data) == 0:
        html += f"""
        <div class="container">
            <div class="header">
                DANH SÁCH CÔNG NHÂN VIÊN {company_name}
            </div>
            
            <div class="no-results">
                <p><strong>Không tìm thấy nhân viên nào trong phạm vi đã chọn.</strong></p>
                <p>Vui lòng kiểm tra lại các điều kiện tìm kiếm.</p>
            </div>
        </div>
        """
        html += "</body></html>"
        return html
    
    # Split employees into pages
    pages = []
    for i in range(0, len(employee_data), employees_per_page):
        pages.append(employee_data[i:i+employees_per_page])
    
    # Generate each page
    for page_num, page_employees in enumerate(pages, 1):
        if page_num > 1:
            # Chỉ thêm page-break khi trang có nội dung thực sự
            if len(page_employees) > 0:
                html += '<div class="page-break"></div>\n'
            else:
                continue 
        
        html += f"""
        <div class="container">
            <div class="header">
                DANH SÁCH CÔNG NHÂN VIÊN {company_name}
            </div>
            
            <table>
                <thead>
                    <tr>
                        <th style="width: 5%;">STT</th>
                        <th style="width: 15%;">Mã số nhân viên</th>
                        <th style="width: {25 if include_department else 35}%;">Tên nhân viên</th>
        """
        
        # Add optional column headers
        if include_department:
            html += '<th style="width: 15%;">Bộ phận</th>\n'
        
        if include_section:
            html += '<th style="width: 10%;">Tổ</th>\n'
        
        # Add photo and notes column headers
        html += f"""
                        <th style="width: 10%;">Hình ảnh</th>
        """
        
        if include_notes:
            html += '<th style="width: 15%;">Ghi chú</th>\n'
        
        html += """
                    </tr>
                </thead>
                <tbody>
        """
        
        # Add employee rows
        start_idx = (page_num - 1) * employees_per_page
        for idx, emp in enumerate(page_employees):
            global_idx = start_idx + idx
            html += f"""
                    <tr>
                        <td>{global_idx + 1}</td>
                        <td class="employee-id">{emp.get('name', '')}</td>
                        <td class="text-left">{emp.get('employee_name', '')}</td>
            """
            
            # Add optional department and section columns
            if include_department:
                html += f'<td>{emp.get("department", "")}</td>\n'
            
            if include_section:
                html += f'<td>{emp.get("section", "")}</td>\n'
            
            # Add photo column
            html += f'<td><img src="data:image/jpeg;base64,{emp.get("image_data", "")}" class="employee-photo-employee-list" alt="{emp.get("employee_name", "")}" onerror="this.style.display=\'none\'"></td>\n'
            
            # Add notes column if included
            if include_notes:
                html += '<td></td>\n'
            
            html += """
                    </tr>
            """
        
        # Close table
        html += """
                </tbody>
            </table>
        </div>
        """
    
    # Close HTML
    html += """
    </body>
    </html>
    """
    
    return html
