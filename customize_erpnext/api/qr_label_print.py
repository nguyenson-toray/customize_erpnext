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
    from reportlab.lib.pagesizes import A4, A5, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, KeepTogether, PageBreak, Spacer
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
def generate_qr_labels_pdf(filters=None, page_format='a5_landscape'):
    """
    Generate PDF with QR code labels for items
    Supports multiple page formats:
    - a5_landscape: A5 landscape (3x4 layout, 50x25mm labels)
    - a4_tommy: A4 Tommy No.138 (5x20 layout, 40x14mm labels)
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

        # Generate PDF based on page format
        if page_format == 'a5_landscape':
            pdf_buffer = create_qr_labels_pdf_a5_landscape(items)
        else:  # Default to a4_tommy
            pdf_buffer = create_qr_labels_pdf(items)

        # Return PDF as base64 for download
        pdf_base64 = base64.b64encode(pdf_buffer.getvalue()).decode()

        return {
            'pdf_data': pdf_base64,
            'filename': f'qr_labels_{page_format}_{frappe.utils.now()}.pdf',
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

    # Create ReportLab Image with default size if not provided
    if size is None:
        size = (12 * mm, 12 * mm)  # Default to 12mm x 12mm as used in the layout
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


def create_qr_labels_pdf_a5_landscape(items):
    """
    Create PDF with QR labels for A5 landscape format

    Layout specification:
    - Page: A5 landscape (210mm x 148mm)
    - Grid: FIXED 3 columns x 4 rows = 12 labels per page
    - Label size: 50mm (width) x 24mm (height) - reduced to fit perfectly
    - Gap between labels: 5mm (horizontal and vertical)

    Calculations:
    - Total width needed: 3×50mm + 2×5mm = 160mm (fits in 210mm)
    - Total height needed: 4×24mm + 3×5mm = 111mm (fits in 148mm)
    - Horizontal margins: (210-160)/2 = 25mm each side
    - Vertical margins: 148-111 = 37mm total (use minimal 5mm top+bottom, 10mm spacer)

    Card layout (each 50x24mm):
        - Top section (11mm height): custom_name_detail (left-aligned, bold)
        - Bottom section (12mm height):
            - Left (12mm width): QR code (10x10mm, centered)
            - Right (38mm width): Group & Location (2 lines, left-aligned)
    """
    buffer = BytesIO()

    # A5 landscape dimensions
    page_width, page_height = landscape(A5)  # 210mm x 148mm

    # Label dimensions
    label_width = 50 * mm
    label_height = 24 * mm  # Reduced from 25mm to 24mm to account for padding/borders

    # Gap between labels
    gap = 5 * mm

    # FIXED: Always 3 columns x 4 rows per page
    cols = 3
    rows = 4

    # Calculate total dimensions needed
    total_labels_width = cols * label_width + (cols - 1) * gap  # 3×50 + 2×5 = 160mm
    total_labels_height = rows * label_height + (rows - 1) * gap  # 4×24 + 3×5 = 111mm

    # Calculate available space
    available_width = page_width  # 210mm
    available_height = page_height  # 148mm

    # Center horizontally: (210 - 160) / 2 = 25mm on each side
    margin_left = (available_width - total_labels_width) / 2
    margin_right = margin_left

    # Calculate vertical margins - keep it simple and consistent
    # Available vertical space: 148mm - 111mm (table) = 37mm
    # Use 15mm top, 22mm bottom to center nicely
    margin_top = 15 * mm
    margin_bottom = 15 * mm

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A5),
        leftMargin=margin_left,
        rightMargin=margin_right,
        topMargin=margin_top,
        bottomMargin=margin_bottom,
        showBoundary=0  # Don't show debug boundary
    )

    # Create table data
    story = []
    items_per_page = 12  # Fixed: 3x4 grid = 12 items per page

    for page_idx, page_start in enumerate(range(0, len(items), items_per_page)):
        # Add page break before each page except the first
        if page_idx > 0:
            story.append(PageBreak())

        page_items = items[page_start:page_start + items_per_page]
        # Always pass cols=3, rows=4 to ensure 3x4 grid
        table_data = create_table_data_a5_landscape(page_items, cols, rows)

        # Create table with gaps - we need to add gap columns and rows
        # Column widths: [card, gap, card, gap, card]
        col_widths = []
        for i in range(cols):
            col_widths.append(label_width)
            if i < cols - 1:  # Add gap column between cards
                col_widths.append(gap)

        # Row heights: [card, gap, card, gap, card, gap, card]
        row_heights = []
        for i in range(rows):
            row_heights.append(label_height)
            if i < rows - 1:  # Add gap row between cards
                row_heights.append(gap)

        # Create table data with gaps
        table_data_with_gaps = create_table_data_with_gaps(table_data, cols, rows)

        # Verify dimensions
        # Should have 7 rows (4 card rows + 3 gap rows) and 5 cols (3 card cols + 2 gap cols)
        expected_rows = rows * 2 - 1  # 4*2-1 = 7
        expected_cols = cols * 2 - 1  # 3*2-1 = 5

        # Create table - CRITICAL: Use exact dimensions to prevent page breaks
        table = Table(table_data_with_gaps,
                     colWidths=col_widths,
                     rowHeights=row_heights,
                     spaceBefore=0,
                     spaceAfter=0,
                     repeatRows=0)  # Don't repeat rows on next page

        # Apply table style
        style_list = [
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]

        table.setStyle(TableStyle(style_list))

        # Keep table together on one page
        table.hAlign = 'LEFT'

        # CRITICAL: Set split method to prevent row splits
        table._splitRows = 0  # Don't allow splitting rows

        # Wrap table in KeepTogether to prevent splits
        story.append(KeepTogether(table))

    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer


def create_table_data_with_gaps(table_data, cols, rows):
    """
    Insert gap rows and columns between cards
    """
    result = []

    for row_idx, row in enumerate(table_data):
        # Add the card row
        new_row = []
        for col_idx, cell in enumerate(row):
            new_row.append(cell)
            # Add gap column after each card except the last
            if col_idx < len(row) - 1:
                new_row.append('')  # Empty gap cell
        result.append(new_row)

        # Add gap row after each card row except the last
        if row_idx < len(table_data) - 1:
            gap_row = [''] * len(new_row)  # Empty gap row
            result.append(gap_row)

    return result


def create_table_data_a5_landscape(items, cols, rows):
    """
    Create table data for A5 landscape labels
    Card layout:
        - Top: custom_name_detail (height: 12mm)
        - Bottom: Left (QR code 10x10mm) | Right (group & location - 2 lines)
    """
    table_data = []

    # Create styles
    styles = getSampleStyleSheet()

    # Style for item name detail at top (12mm height)
    name_style = ParagraphStyle(
        'NameStyle',
        parent=styles['Normal'],
        fontSize=10,
        leading=12,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold'
    )

    # Style for group and location
    info_style = ParagraphStyle(
        'InfoStyle',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        alignment=TA_LEFT,
        fontName='Helvetica'
    )

    for row in range(rows):
        row_data = []
        for col in range(cols):
            item_index = row * cols + col

            if item_index < len(items):
                item = items[item_index]

                # Generate QR code (10x10mm)
                qr_img = generate_qr_code(item['item_code'], size=(10*mm, 10*mm))

                # Create text content
                item_name_text = Paragraph(item['custom_item_name_detail'] or item['item_name'] or '', name_style)

                # Group text (remove 'All' prefix if present)
                group_text = item['item_group'][2:] if item['item_group'] and len(item['item_group']) > 2 else item['item_group'] or ''
                item_group = Paragraph(f"<b>Group:</b> {group_text}", info_style)

                # Location text (empty for now)
                item_location = Paragraph("<b>Location:</b> ", info_style)

                # Create card layout:
                # Row 1: Item name detail (full width, 12mm height)
                # Row 2: QR code (left) | Group + Location (right)
                card_data = [
                    [item_name_text],  # Top section: full width
                    [
                        qr_img,  # Bottom left: QR code
                        [item_group, item_location]  # Bottom right: info
                    ]
                ]

                card_table = Table(
                    card_data,
                    colWidths=[50*mm],  # First row full width
                    rowHeights=[11*mm, 12*mm]  # Top: 11mm, Bottom: 12mm (23mm total + ~1mm padding = 24mm)
                )

                # Apply second level table style for bottom row
                card_table_style = [
                    # Top row (item name)
                    ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                    ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (0, 0), 3),
                    ('RIGHTPADDING', (0, 0), (0, 0), 2),
                    ('TOPPADDING', (0, 0), (0, 0), 2),
                    ('BOTTOMPADDING', (0, 0), (0, 0), 2),
                    # Add border to entire card
                    ('BOX', (0, 0), (-1, -1), 1, colors.black),
                ]

                # Split bottom row into QR and info sections
                bottom_row_data = card_data[1]
                bottom_table = Table(
                    [bottom_row_data],
                    colWidths=[12*mm, 38*mm],  # QR: 12mm (10mm + 2mm padding), Info: 38mm
                    rowHeights=[12*mm]  # Reduced from 13mm to 12mm
                )

                bottom_table_style = [
                    # QR code cell
                    ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                    ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (0, 0), 1),
                    ('RIGHTPADDING', (0, 0), (0, 0), 1),
                    # Info cell
                    ('ALIGN', (1, 0), (1, 0), 'LEFT'),
                    ('VALIGN', (1, 0), (1, 0), 'TOP'),
                    ('LEFTPADDING', (1, 0), (1, 0), 2),
                    ('RIGHTPADDING', (1, 0), (1, 0), 2),
                    ('TOPPADDING', (1, 0), (1, 0), 1),
                ]

                bottom_table.setStyle(TableStyle(bottom_table_style))

                # Recreate card with bottom table
                card_data_final = [
                    [item_name_text],
                    [bottom_table]
                ]

                card_table_final = Table(
                    card_data_final,
                    colWidths=[50*mm],
                    rowHeights=[11*mm, 12*mm]  # Total: 23mm
                )

                card_table_final.setStyle(TableStyle(card_table_style))

                row_data.append(card_table_final)
            else:
                # Empty cell
                row_data.append('')

        table_data.append(row_data)

    return table_data