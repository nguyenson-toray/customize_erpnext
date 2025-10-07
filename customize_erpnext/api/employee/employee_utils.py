import frappe
import re
import os
import base64
from frappe import _
from frappe.utils.file_manager import save_file
from frappe.utils.pdf import get_pdf
from frappe.utils import get_site_path
import io
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
def generate_employee_cards_pdf(employee_ids, with_barcode=0, page_size='A4'):
    """
    Generate PDF containing employee cards with layout:
    - A4 portrait: 2 columns, 5 rows (10 cards per page)
    - A5 landscape: 2 columns, 2 rows (4 cards per page)
    - Card size: 86mm x 54mm
    - Left column (30mm): company logo (30mm) + employee photo (30mm x 40mm) + optional barcode
    - Right column: Full name (uppercase, bold, 20pt), employee code (bold, 18pt), custom_section (bold, 18pt)
    """
    import tempfile
    import datetime
    import traceback

    try:
        if isinstance(employee_ids, str):
            import json
            employee_ids = json.loads(employee_ids)

        # Convert with_barcode to boolean
        with_barcode = int(with_barcode) == 1

        # Validate page_size
        if page_size not in ['A4', 'A5']:
            page_size = 'A4'

        frappe.logger().info(f"Generating employee cards for {len(employee_ids)} employees (page_size={page_size})")

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

        # Generate HTML for cards
        frappe.logger().info(f"Generating HTML for employee cards (with_barcode={with_barcode}, page_size={page_size})")
        html = generate_employee_cards_html(employees, with_barcode=with_barcode, page_size=page_size)

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

        # Save PDF to temp file
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        pdf_filename = f'employee_cards_{timestamp}.pdf'

        # Save to public files
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(pdf_data)
            tmp_file_path = tmp_file.name

        frappe.logger().info(f"PDF saved to temp file: {tmp_file_path}")

        # Read and save as File document
        with open(tmp_file_path, 'rb') as f:
            file_doc = frappe.get_doc({
                'doctype': 'File',
                'file_name': pdf_filename,
                'is_private': 0,
                'folder': 'Home',
                'content': f.read()
            })
            file_doc.save(ignore_permissions=True)

        # Clean up temp file
        os.unlink(tmp_file_path)

        frappe.db.commit()

        frappe.logger().info(f"Employee cards PDF created: {file_doc.file_url}")

        return {
            'status': 'success',
            'pdf_url': file_doc.file_url,
            'message': f'Generated {len(employees)} employee cards'
        }

    except Exception as e:
        error_trace = traceback.format_exc()
        frappe.logger().error(f"Error generating employee cards PDF: {str(e)}\n{error_trace}")
        frappe.log_error(f"Error: {str(e)}\n\nTraceback:\n{error_trace}", "Employee Cards PDF Error")
        frappe.throw(_("Failed to generate employee cards PDF: {0}").format(str(e)))


def generate_employee_cards_html(employees, with_barcode=False, page_size='A4'):
    """
    Generate HTML for employee cards with proper layout
    - A4: portrait, 2x5 layout
    - A5: landscape, 2x2 layout
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
            margin-left: 30mm;
            padding-top: 9mm;
            padding-left: 0.5mm;
            padding-right: 0.5mm;
            padding-bottom: 2mm;
            text-align: center;
        }}

        .employee-barcode {{
            width: 28mm;
            height: auto;
            max-height: 5mm;
            margin-top: 0mm;
            display: block;
        }}

        .employee-name {{
            font-size: 20pt !important;
            font-weight: bold;
            text-transform: uppercase;
            margin: 0 0 3mm 0;
            line-height: 1.3;
            word-wrap: break-word;
            color: #000;
            text-align: center;
        }}

        .employee-name.long-name {{
            font-size: 18pt !important;
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
                    card_html = generate_single_card_html(emp, company_logo, with_barcode)
                    html_parts.append(card_html)
                else:
                    # Empty card to maintain layout
                    html_parts.append('<div class="card" style="visibility: hidden;"></div>')

            html_parts.append('<div class="clearfix"></div>')
            html_parts.append('</div>')  # end card-row

        # Page break before back side
        html_parts.append('<div class="page-break"></div>')

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


def generate_single_card_html(employee, company_logo, with_barcode=False):
    """Generate HTML for a single employee card"""

    # Get employee image URL - always returns a valid base64 image or placeholder
    emp_image_url = get_full_image_url(employee.get('image', ''))

    # Escape HTML special characters in text
    employee_name = frappe.utils.escape_html(employee.get('employee_name', ''))
    employee_code = frappe.utils.escape_html(employee.get('name', ''))
    employee_section = frappe.utils.escape_html(employee.get('custom_section', ''))

    # Simple logic for name display
    name_class = 'employee-name'
    name_html = employee_name
    name_length = len(employee_name)

    # Rule 1: Name >= 20 chars -> use font size 18pt
    if name_length >= 20:
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
            import json
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


