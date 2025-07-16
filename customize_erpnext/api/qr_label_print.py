# Tomy 138	100 tem/tờ A4	40mm x 14mm
import frappe
from io import BytesIO
import base64

try:
    import qrcode
    import qrcode.constants
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.platypus.flowables import Image as ReportLabImage
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


@frappe.whitelist()
def generate_qr_labels_pdf(filters=None):
    """
    Generate PDF with QR code labels for items
    Layout: 100 labels per A4 page (5 columns x 20 rows)
    Each label: 40mm x 14mm with 12x12mm QR code + item info
    """
    # Check dependencies
    if not QRCODE_AVAILABLE:
        frappe.throw("QR code library not available. Please install: pip install qrcode[pil]")
    
    if not REPORTLAB_AVAILABLE:
        frappe.throw("ReportLab library not available. Please install: pip install reportlab")
    
    if not PIL_AVAILABLE:
        frappe.throw("Pillow library not available. Please install: pip install Pillow")
    
    try:
        # Parse filters
        if isinstance(filters, str):
            import json
            filters = json.loads(filters)
        
        if not filters:
            filters = {}
        
        # Get items based on filters
        items = get_filtered_items(filters)
        
        if not items:
            frappe.throw("No items found with the specified filters")
        
        # Generate PDF
        pdf_buffer = create_qr_labels_pdf(items)
        
        # Return PDF as base64 for download
        pdf_base64 = base64.b64encode(pdf_buffer.getvalue()).decode()
        
        return {
            'pdf_data': pdf_base64,
            'filename': f'qr_labels_{frappe.utils.now()}.pdf',
            'items_count': len(items)
        }
        
    except Exception as e:
        frappe.log_error(f"Error generating QR labels PDF: {str(e)}")
        frappe.throw(f"Error generating PDF: {str(e)}")

@frappe.whitelist()
def get_filtered_items(filters):
    """Get items based on filters"""
    # Parse filters if it's a JSON string
    if isinstance(filters, str):
        import json
        try:
            filters = json.loads(filters)
        except (json.JSONDecodeError, TypeError):
            filters = {}
    
    if not filters:
        filters = {}
    
    conditions = []
    values = {}
    
    # Base query
    query = """
        SELECT 
            item_code,
            item_name,
            custom_item_name_detail,
            item_group,
            creation,
            modified
        FROM `tabItem`
        WHERE disabled = 0 AND has_variants = 0
    """
    
    # Add filters
    if filters.get('item_code'):
        conditions.append("item_code LIKE %(item_code)s")
        values['item_code'] = f"%{filters['item_code']}%"
    
    if filters.get('custom_item_name_detail'):
        conditions.append("custom_item_name_detail LIKE %(custom_item_name_detail)s")
        values['custom_item_name_detail'] = f"%{filters['custom_item_name_detail']}%"
    
    if filters.get('item_group'):
        conditions.append("item_group = %(item_group)s")
        values['item_group'] = filters['item_group']
    
    if filters.get('created_after'):
        conditions.append("creation >= %(created_after)s")
        values['created_after'] = filters['created_after']
    
    if filters.get('item_codes'):
        item_codes = filters['item_codes']
        if item_codes:
            placeholders = ', '.join([f'%(item_code_{i})s' for i in range(len(item_codes))])
            conditions.append(f"item_code IN ({placeholders})")
            for i, code in enumerate(item_codes):
                values[f'item_code_{i}'] = code
    
    # Add conditions to query
    if conditions:
        query += " AND " + " AND ".join(conditions)
    
    # Add ordering and limit
    #  Ordering by creation date desc and item group acs
    query +=  " ORDER BY item_group ASC , custom_item_name_detail ASC , creation DESC"
    
    if filters.get('limit'):
        query += f" LIMIT {int(filters['limit'])}"
    
    return frappe.db.sql(query, values, as_dict=True)


def generate_qr_code(data, size=None):
    """Generate QR code image"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_Q,
        box_size=8,
        border=2
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    # Create QR code image
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to bytes
    img_buffer = BytesIO()
    qr_img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    # Create ReportLab Image
    reportlab_img = ReportLabImage(img_buffer, width=size[0], height=size[1])
    return reportlab_img


@frappe.whitelist()
def generate_qr_code_base64(data):
    """Generate QR code image and return as base64 string for web display"""
    try:
        import qrcode
        import qrcode.constants
        from io import BytesIO
        import base64
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_Q,
            box_size=8,
            border=2
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        # Create QR code image
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        img_buffer = BytesIO()
        qr_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        return base64.b64encode(img_buffer.getvalue()).decode()
        
    except Exception as e:
        frappe.log_error(f"Error generating QR code: {str(e)}")
        return ""


def create_qr_labels_pdf(items):
    """Create PDF with QR labels layout"""
    buffer = BytesIO()
    
    # A4 dimensions with margins
    page_width, page_height = A4
    margin_left = margin_right = 2 * mm
    margin_top = margin_bottom = 4 * mm
    
    # Gap between labels
    gap = 1 * mm
    
    # Fixed label dimensions
    label_width = 40 * mm
    label_height = 14 * mm
    
    # Calculate grid dimensions based on available space and gaps
    available_width = page_width - margin_left - margin_right
    available_height = page_height - margin_top - margin_bottom
    
    # Calculate how many labels fit with gaps
    cols = int((available_width + gap) / (label_width + gap))
    rows = int((available_height + gap) / (label_height + gap))
    
    # Ensure minimum of 1 column and row
    cols = max(1, cols)
    rows = max(1, rows)
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=margin_left,
        rightMargin=margin_right,
        topMargin=margin_top,
        bottomMargin=margin_bottom
    )
    
    # Create table data
    story = []
    current_page_items = []
    
    # Fixed: 100 labels per page maximum
    items_per_page = min(100, cols * rows)
    
    for i, item in enumerate(items):
        current_page_items.append(item)
        
        # When we have reached 100 items or it's the last item, create a page
        if len(current_page_items) == items_per_page or i == len(items) - 1:
            table_data = create_table_data(current_page_items, cols, rows)
            
            # Create table with spacing for gaps
            table = Table(table_data, 
                         colWidths=[label_width] * cols, 
                         rowHeights=[label_height] * rows,
                         spaceBefore=gap,
                         spaceAfter=gap)
            
            # Apply table style with gaps (no borders)
            style_list = [
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), gap/2),
                ('RIGHTPADDING', (0, 0), (-1, -1), gap/2),
                ('TOPPADDING', (0, 0), (-1, -1), gap/2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), gap/2),
            ]
            
            table.setStyle(TableStyle(style_list))
            
            story.append(table)
            current_page_items = []
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer


def create_table_data(items, cols, rows):
    """Create table data for labels"""
    table_data = []
    
    # Create styles
    styles = getSampleStyleSheet()
    group_style = ParagraphStyle(
        'CodeStyle',
        parent=styles['Normal'],
        fontSize=8,
        leading=9,
        alignment=TA_LEFT,
        fontName='Helvetica'
    )
    
    name_style = ParagraphStyle(
        'NameStyle',
        parent=styles['Normal'],
        fontSize=8,
        leading=7,
        alignment=TA_LEFT,
        fontName='Helvetica'
    )
    name_style_long = ParagraphStyle(
        'NameStyle',
        parent=styles['Normal'],
        fontSize=6,
        leading=7,
        alignment=TA_LEFT,
        fontName='Helvetica'
    )
    
    for row in range(rows):
        row_data = []
        for col in range(cols):
            item_index = row * cols + col
            
            if item_index < len(items):
                item = items[item_index]
                
                # Generate QR code
                qr_img = generate_qr_code(item['item_code'])
                
                # Create text content
                # item_group removed 'All' prefix : 2 characters
                item_group = Paragraph(item['item_group'][2:] or '', group_style)  
                if len(item['custom_item_name_detail']) > 44:
                    item_name_text = Paragraph(item['custom_item_name_detail'] , name_style_long)
                else:
                    item_name_text = Paragraph(item['custom_item_name_detail'] or item['item_name'] or '', name_style)
                
                # Create nested table for QR + text layout
                cell_data = [
                    [qr_img, [item_group, item_name_text]]
                ]
                
                cell_table = Table(
                    cell_data,
                    colWidths=[12*mm, 26*mm],  # QR: 12mm, Text: 26mm
                    rowHeights=[12*mm]
                )
                
                cell_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (0, 0), 'CENTER'),    # QR center
                    ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),   # QR middle
                    ('ALIGN', (1, 0), (1, 0), 'LEFT'),      # Text left
                    ('VALIGN', (1, 0), (1, 0), 'TOP'),      # Text top
                    ('LEFTPADDING', (1, 0), (1, 0), 2),
                    ('RIGHTPADDING', (1, 0), (1, 0), 1),
                    ('TOPPADDING', (1, 0), (1, 0), 1),
                    ('BOTTOMPADDING', (1, 0), (1, 0), 1),
                ]))
                
                row_data.append(cell_table)
            else:
                # Empty cell
                row_data.append('')
        
        table_data.append(row_data)
    
    return table_data


@frappe.whitelist()
def get_item_groups():
    """Get list of item groups for filter dropdown"""
    return frappe.get_all('Item Group', 
                         filters={'is_group': 0}, 
                         fields=['name'], 
                         order_by='name')


@frappe.whitelist()
def get_recent_items(limit=50):
    """Get recently created items"""
    return frappe.get_all('Item', 
                         fields=['item_code', 'item_name', 'custom_item_name_detail', 'creation'],
                         order_by='creation desc',
                         limit=limit)