# QR Label Print Feature

## Overview
This feature adds QR code label printing functionality to ERPNext Item List. It generates A4 PDF with 100 QR code labels per page (5 columns × 20 rows).

## Label Specifications
- **Label Size**: 40mm × 14mm
- **Layout**: 100 labels per A4 page (5×20 grid)
- **QR Code**: 12mm × 12mm (left side)
- **Text Area**: 26mm × 12mm (right side)
  - Line 1: item_code (bold, 8pt)
  - Line 2: custom_item_name_detail (normal, 6pt)
- **Margins**: 5mm left/right, 8.5mm top/bottom

## Installation

### 1. Install Python Dependencies
```bash
pip install qrcode[pil] reportlab Pillow
```

### 2. Clear Cache and Build
```bash
bench --site your-site-name clear-cache
bench build
bench --site your-site-name migrate
bench restart
```

## Usage

### 1. Access the Feature
1. Go to **Item List** in ERPNext
2. Click **Actions** → **Print QR Labels**

### 2. Filter Options
- **All Items**: Print all active items
- **Selected Items**: Print only selected items from the list
- **Custom Filter**: Use custom criteria:
  - Item Code (contains)
  - Item Name Detail (contains)
  - Item Group
  - Created After (date)
- **Recent Items**: Items created in the last N days

### 3. Preview and Generate
1. Use **Preview Items** to see what will be included
2. Set **Limit** (max 1000 items per batch)
3. Click **Generate PDF** to create and download the PDF

## Features

### Filter Options
- **Filter by Item Code**: Search items containing specific text
- **Filter by Item Name Detail**: Search by custom item name detail
- **Filter by Item Group**: Select specific item group
- **Filter by Creation Date**: Items created after specific date
- **Recent Items**: Items created in last N days
- **Selected Items**: Only selected items from the list view

### PDF Generation
- **A4 Size**: Optimized for standard A4 paper
- **100 Labels per Page**: Efficient use of space
- **QR Code**: Contains item_code for scanning
- **Text Information**: Item code and name detail
- **Professional Layout**: Clean, printable design

### Quality Features
- **High-Quality QR Codes**: Error correction level L
- **Clear Text**: Readable font sizes
- **Proper Margins**: Print-ready margins
- **Batch Processing**: Handle large numbers of items

## Technical Details

### Files Added
1. **Server-side API**: `customize_erpnext/api/qr_label_print.py`
2. **Client-side JS**: `customize_erpnext/public/js/custom_scripts/item_list.js`
3. **Dependencies**: Added to `requirements.txt`

### API Methods
- `generate_qr_labels_pdf()`: Main PDF generation
- `get_filtered_items()`: Item filtering logic
- `get_item_groups()`: Get item groups for dropdown
- `get_recent_items()`: Get recently created items

### Dependencies
- **qrcode[pil]**: QR code generation
- **reportlab**: PDF creation
- **Pillow**: Image processing

## Troubleshooting

### Common Issues

1. **Missing Dependencies Error**
   ```
   Error: QR code library not available
   ```
   **Solution**: Install required packages
   ```bash
   pip install qrcode[pil] reportlab Pillow
   ```

2. **Button Not Visible**
   **Solution**: Clear cache and rebuild
   ```bash
   bench --site your-site-name clear-cache
   bench build
   ```

3. **No Items Found**
   **Solution**: Check filters and ensure items exist with the criteria

4. **PDF Generation Error**
   **Solution**: Check server logs and ensure sufficient memory for large batches

### Performance Tips
- Limit batches to 1000 items for better performance
- Use specific filters to reduce processing time
- For large databases, use date filters to narrow results

## Customization

### Modify Label Layout
Edit `create_table_data()` in `qr_label_print.py`:
- Change font sizes
- Adjust QR code size
- Modify text layout

### Add More Filters
Edit `get_filtered_items()` to add additional filter criteria.

### Change Page Layout
Modify grid dimensions in `create_qr_labels_pdf()`:
- Change `cols` and `rows` variables
- Adjust `label_width` and `label_height`

## Support
For issues or customization requests, contact the IT Team.