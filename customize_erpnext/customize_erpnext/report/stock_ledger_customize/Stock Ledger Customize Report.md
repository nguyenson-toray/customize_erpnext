# Stock Ledger Customize Report

## Tổng quan

**Stock Ledger Customize** là một báo cáo tùy chỉnh trong ERPNext hiển thị lịch sử chi tiết của tất cả các giao dịch kho hàng (stock ledger entries) với các tính năng mở rộng.

## Chức năng chính

### 📊 Hiển thị Stock Ledger Entries
- Theo dõi chi tiết từng giao dịch kho (nhập/xuất)
- Hiển thị số lượng trước và sau giao dịch
- Ghi nhận thông tin voucher và voucher type

### 🎯 Filters nâng cao
- **Thời gian**: From Date, To Date
- **Đối tượng**: Company, Warehouse, Item, Item Group
- **Voucher**: Voucher Number
- **Stock Entry Type**: Material Receipt, Material Issue
- **UOM**: Include UOM cho conversion
- **Batch/Serial**: Segregate Serial/Batch Bundle

### 🏷️ Variant Attributes
- Hiển thị các thuộc tính variant của items
- Thứ tự cố định: **Color, Size, Brand, Season, Info**
- Tự động filter các giá trị null, empty, "nan"

### 🧾 Invoice Number Integration
- Hiển thị Invoice Number từ Stock Entry Detail hoặc Stock Reconciliation Item
- Highlight Invoice Number với bold format
- Lọc theo Invoice Number

## Logic xử lý

### 1. Data Retrieval
```python
def get_stock_ledger_entries(filters, items):
    # Query từ Stock Ledger Entry với LEFT JOIN:
    # - Stock Entry (để lấy custom_note)
    # - Stock Entry Detail (để lấy custom_invoice_number)
    # - Stock Reconciliation Item (để lấy custom_invoice_number)
```

### 2. Variant Attributes Processing
```python
def get_variant_values_for(sl_entries):
    # 1. Lấy danh sách unique item codes
    # 2. Query Item Variant Attribute table
    # 3. Filter clean data (loại bỏ null, "nan", empty)
    # 4. Trả về dictionary mapping item_code -> attributes
```

### 3. Column Generation
```python
def get_columns(filters):
    # 1. Base columns (Date, Item, Warehouse, etc.)
    # 2. Inventory dimensions (nếu có)
    # 3. Quantity columns (In Qty, Out Qty, Balance)
    # 4. Variant attributes (theo thứ tự cố định)
```

### 4. Opening Balance
```python
def get_opening_balance(filters, columns, sl_entries):
    # 1. Lấy previous SLE trước from_date
    # 2. Xử lý Stock Entry Type filter nếu có
    # 3. Kiểm tra Opening Stock Reconciliation
    # 4. Trả về opening row
```

## Cấu trúc Columns

### Core Columns
| Field | Type | Description |
|-------|------|-------------|
| date | Datetime | Posting datetime |
| item_code | Link | Item code |
| item_name | Data | Item name |
| stock_uom | Link | Stock UOM |
| in_qty | Float | Quantity in (positive) |
| out_qty | Float | Quantity out (negative) |
| qty_after_transaction | Float | Balance quantity |
| warehouse | Link | Warehouse |
| custom_invoice_number | Data | Invoice number |
| item_group | Link | Item group |
| description | Data | Item description |
| voucher_type | Data | Document type |
| voucher_no | Dynamic Link | Document number |
| note | Text | Custom note |

### Variant Attributes (nếu enabled)
- **Color** - Màu sắc
- **Size** - Kích thước  
- **Brand** - Thương hiệu
- **Season** - Mùa
- **Info** - Thông tin bổ sung
- Các attributes khác (theo alphabet order)

## Tính năng đặc biệt

### 🎨 Formatting
```javascript
formatter: function (value, row, column, data, default_formatter) {
    // Red color cho out_qty âm
    // Green color cho in_qty dương
    // Bold cho custom_invoice_number
}
```

### 🔄 Stock Entry Type Filter
- Lọc theo loại Stock Entry (Material Receipt/Issue)
- Áp dụng cho cả main query và opening balance

### 📦 Inventory Dimensions
- Hỗ trợ inventory dimensions (nếu có trong hệ thống)
- Tự động thêm columns và filters

### 🏭 Error Handling
```python
try:
    from erpnext.stock.doctype.inventory_dimension.inventory_dimension import get_inventory_dimensions
except ImportError:
    def get_inventory_dimensions():
        return []
```

## Files cấu trúc

### 📁 stock_ledger_customize.json
- Report metadata
- Roles permissions (Stock User, Accounts Manager)
- Module: "Customize Erpnext"

### 📁 stock_ledger_customize.js
- Client-side filters definition
- Query filters cho Company, Warehouse, Item
- Formatting rules
- Inventory dimensions integration

### 📁 stock_ledger_customize.py
- Main report logic
- Data processing và query building
- Variant attributes handling
- Opening balance calculation

## Customizations so với Standard

### ✨ Enhancements
1. **Invoice Number display** - Hiển thị số hóa đơn
2. **Variant Attributes** - Thuộc tính biến thể với thứ tự cố định
3. **Stock Entry Type filter** - Lọc theo loại phiếu kho
4. **Enhanced formatting** - Màu sắc và bold text
5. **Better error handling** - Xử lý lỗi inventory dimensions

### 🔧 Technical Improvements
- Clean code structure với proper imports
- Consistent data filtering logic
- Better query optimization với LEFT JOINs
- Proper null/empty value handling

## Use Cases

### 📈 Inventory Management
- Theo dõi lịch sử nhập/xuất kho chi tiết
- Kiểm tra balance qty tại từng thời điểm
- Audit trail cho stock movements

### 🧾 Invoice Tracking
- Liên kết stock movements với invoice numbers
- Theo dõi hàng theo từng đơn hàng cụ thể

### 🏷️ Product Variants
- Quản lý inventory theo attributes (màu, size, etc.)
- Báo cáo chi tiết cho sản phẩm có nhiều biến thể

### 📊 Analysis & Reporting
- Phân tích xu hướng nhập/xuất
- Báo cáo theo warehouse, item group
- Export data cho external analysis