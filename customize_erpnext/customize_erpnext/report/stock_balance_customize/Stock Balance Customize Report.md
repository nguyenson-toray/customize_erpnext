# Stock Balance Customize Report

## Tổng quan

**Stock Balance Customize** là một báo cáo tồn kho tùy chỉnh trong ERPNext hiển thị số dư kho hàng tại một thời điểm với các tính năng mở rộng, bao gồm variant attributes và stock aging data.

## Chức năng chính

### 📊 Stock Balance Summary
- Hiển thị tồn kho tổng hợp (không phải từng transaction)
- Opening Qty, In Qty, Out Qty, Balance Qty
- Tính toán valuation và balance value
- Group theo Item + Warehouse + Invoice Number

### 🎯 Filters nâng cao
- **Thời gian**: From Date, To Date
- **Đối tượng**: Company, Warehouse, Item, Item Group, Brand
- **Warehouse Type**: Lọc theo loại kho
- **Invoice Number**: Filter theo số hóa đơn cụ thể
- **UOM**: Include UOM cho conversion
- **Stock Aging**: Hiển thị thông tin tuổi kho

### 🏷️ Variant Attributes
- Hiển thị các thuộc tính variant của items
- Thứ tự cố định: **Color, Size, Brand, Season, Info**
- Tự động filter các giá trị null, empty, "nan"

### 📅 Stock Aging Integration
- **Average Age**: Tuổi trung bình của stock
- **Earliest Age**: Tuổi cũ nhất
- **Latest Age**: Tuổi mới nhất
- FIFO queue tracking

### 🧾 Invoice & Receive Date
- Invoice Number từ Stock Entry hoặc Stock Reconciliation
- Receive Date tracking
- Group riêng biệt theo invoice number

## Logic xử lý

### 1. Class-based Architecture
```python
class StockBalanceCustomizeReport:
    def __init__(self, filters=None)
    def run()  # Main execution flow
    def prepare_opening_data_from_closing_balance()
    def prepare_stock_ledger_entries()
    def prepare_new_data()
```

### 2. Data Grouping Logic
```python
def get_group_by_key(self, row):
    # Group by: company + item_code + warehouse + invoice_number
    # Đảm bảo mỗi invoice có row riêng biệt
    group_by_key = [row.company, row.item_code, row.warehouse]
    if invoice_number:
        group_by_key.append(invoice_number)
```

### 3. Stock Aging (FIFO)
```python
if self.filters.get("show_stock_ageing_data"):
    # Sử dụng FIFOSlots để tính stock aging
    item_wise_fifo_queue = FIFOSlots(self.filters, self.sle_entries).generate()
    # Tính average_age, earliest_age, latest_age
```

### 4. Closing Balance Integration
```python
def prepare_opening_data_from_closing_balance(self):
    # Lấy data từ Closing Stock Balance nếu có
    # Tránh tính toán lại từ đầu nếu có closing balance
```

### 5. Item Warehouse Map
```python
def get_item_warehouse_map(self):
    # Tạo map: group_key -> balance_data
    # Xử lý opening/in/out quantities
    # Update balance values theo timeline
```

## Cấu trúc Columns

### Core Columns
| Field | Type | Description |
|-------|------|-------------|
| item_code | Link | Item code |
| item_name | Data | Item name |
| item_group | Link | Item group |
| warehouse | Link | Warehouse |
| custom_invoice_number | Data | Invoice number |
| custom_receive_date | Date | Receive date |
| voucher_type | Data | Last voucher type |
| voucher_no | Dynamic Link | Last voucher number |
| stock_uom | Link | Stock UOM |
| bal_qty | Float | **Balance Quantity** |
| opening_qty | Float | Opening quantity |
| in_qty | Float | Inward quantity |
| out_qty | Float | Outward quantity |

### Stock Aging Columns (Optional)
| Field | Type | Description |
|-------|------|-------------|
| average_age | Float | Tuổi trung bình (ngày) |
| earliest_age | Float | Tuổi cũ nhất (ngày) |
| latest_age | Float | Tuổi mới nhất (ngày) |

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
    // Red color cho out_qty > 0
    // Green color cho in_qty > 0  
    // Bold cho custom_invoice_number
}
```

### 📊 Zero Stock Items
```python
if not self.filters.get("include_zero_stock_items"):
    # Loại bỏ items có bal_qty = 0 và bal_val = 0
```

### 🏭 Inventory Dimensions Support
- Tự động detect và thêm inventory dimension columns
- Filter theo dimensions
- Show dimension wise stock option

### 📈 Closing Balance Optimization
```python
def get_closing_balance(self):
    # Tìm Closing Stock Balance gần nhất
    # Sử dụng làm opening data để tối ưu performance
    # Ignore closing balance option
```

### 🔄 Opening Vouchers Handling
```python
def get_opening_vouchers(self):
    # Xác định Stock Entry và Stock Reconciliation là opening
    # Tách biệt opening transactions khỏi period transactions
```

## So sánh với Stock Ledger Customize

| Feature | Stock Ledger | Stock Balance |
|---------|-------------|---------------|
| **Data Type** | Transaction details | Summary balances |
| **Rows** | Mỗi transaction = 1 row | Mỗi item/warehouse/invoice = 1 row |
| **Main Focus** | Audit trail, movements | Current stock levels |
| **Stock Aging** | ❌ | ✅ |
| **Closing Balance** | ❌ | ✅ |
| **Valuation** | Per transaction | Summary values |
| **Performance** | Faster for small data | Optimized for large datasets |

## Workflow Logic

### 1. Initialization
```python
def run(self):
    self.prepare_opening_data_from_closing_balance()  # 1
    self.prepare_stock_ledger_entries()               # 2  
    self.prepare_new_data()                           # 3
    self.get_columns()                                # 4
    self.add_additional_uom_columns()                 # 5
```

### 2. Data Processing Flow
```
Closing Balance → Opening Data
Stock Ledger Entries → Raw Transactions  
Group by Key → Item/Warehouse/Invoice
Calculate → Opening + In - Out = Balance
Variant Attributes → Merge with balance data
Stock Aging → Calculate FIFO ages
Final Data → Ready for display
```

### 3. Query Optimization
```python
# Unbuffered cursor cho large datasets
with frappe.db.unbuffered_cursor():
    if not self.filters.get("show_stock_ageing_data"):
        self.sle_entries = self.sle_query.run(as_dict=True, as_iterator=True)
```

## Files cấu trúc

### 📁 stock_balance_customize.json
- Report metadata với timeout: 300 seconds
- Roles permissions (Stock User, Accounts Manager)
- Module: "Customize Erpnext"

### 📁 stock_balance_customize.js
- Advanced filters với warehouse type
- Invoice number filter
- Show aging data checkbox
- Include zero stock items option

### 📁 stock_balance_customize.py
- Class-based architecture
- Complex grouping logic
- Stock aging integration
- Closing balance optimization

## Use Cases

### 📦 Inventory Management
- Kiểm tra tồn kho hiện tại theo warehouse
- Phân tích by item group hoặc brand
- Track inventory theo invoice number

### 📊 Stock Aging Analysis  
- Identify slow-moving inventory
- FIFO analysis cho expired goods
- Optimize inventory turnover

### 💰 Valuation Reporting
- Current stock valuation
- Opening vs closing comparison
- Variance analysis

### 🏷️ Variant Stock Management
- Stock levels theo color/size combinations
- Planning cho seasonal products
- Brand-wise inventory analysis

### 🚀 Performance for Large Data
- Optimized cho datasets lớn
- Closing balance integration
- Unbuffered cursor support

## Advanced Features

### 🔧 Custom Grouping
- Group theo invoice để track từng lô hàng
- Maintain separate records per invoice
- Support multiple invoices cho same item/warehouse

### 📈 Stock Aging Algorithm
```python
# FIFO queue tracking
fifo_queue = sorted(filter(_func, opening_fifo_queue), key=_func)
stock_ageing_data["average_age"] = get_average_age(fifo_queue, to_date)
stock_ageing_data["earliest_age"] = date_diff(to_date, fifo_queue[0][1])
stock_ageing_data["latest_age"] = date_diff(to_date, fifo_queue[-1][1])
```

### 🎯 Precision Control
```python
self.float_precision = cint(frappe.db.get_default("float_precision")) or 3
# Consistent rounding cho all calculations
```