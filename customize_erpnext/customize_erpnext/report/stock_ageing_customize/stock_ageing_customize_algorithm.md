# Stock Ageing Customize - Thuật Toán Tính Tuổi Tồn Kho

## Tổng Quan

Báo cáo **Stock Ageing Customize** là phiên bản tùy chỉnh của báo cáo Stock Ageing trong ERPNext, sử dụng thuật toán **FIFO (First In, First Out)** để theo dõi và tính toán tuổi tồn kho của các mặt hàng với các tính năng mở rộng đặc biệt.

## Các Tính Năng Tùy Chỉnh Chính

### 1. Custom Receive Date cho Opening Stock
**Mục đích**: Thay thế `posting_date` bằng `custom_receive_date` cho các giao dịch Stock Reconciliation Opening Stock

**Logic Implementation**:
```python
if d.voucher_type == "Stock Reconciliation":
    if d.get("custom_receive_date") and "Opening Stock" in str(d.get("voucher_no", "")):
        d.posting_date = d.custom_receive_date
```

**Lợi ích**:
- Theo dõi chính xác ngày nhận hàng thực tế
- Tính tuổi tồn kho đúng với thời gian thực tế
- Phân biệt giữa ngày ghi sổ và ngày nhận hàng

### 2. Theo Dõi Custom Invoice Number
**Mục đích**: Tổng hợp và theo dõi tồn kho theo từng `custom_invoice_number`

**Cấu trúc FIFO Slot mở rộng**:
```python
# Cấu trúc cũ: [quantity, posting_date, stock_value]
# Cấu trúc mới: [quantity, posting_date, stock_value, custom_invoice_number]
```

**Ứng dụng**:
- Theo dõi hàng hóa theo từng lô hàng/hóa đơn
- Quản lý tồn kho chi tiết hơn
- Truy xuất nguồn gốc hàng hóa

### 3. Khoảng Tuổi Tùy Chỉnh
**Thay đổi**: Từ `30, 60, 90` ngày thành `180, 360, 720` ngày

**Lý do**: Phù hợp với chu kỳ quản lý tồn kho dài hạn

### 4. Hiển Thị Tùy Chọn
- **Show Value**: Hiển thị/ẩn các cột giá trị
- **Show Variant Attributes**: Hiển thị thuộc tính variant của item
- **Ẩn cột Brand**: Loại bỏ thông tin không cần thiết

## Thuật Toán FIFO Slots Chi Tiết

### Khái Niệm Cơ Bản

**FIFO Slots** là cấu trúc dữ liệu queue để theo dõi các lô hàng nhập kho theo thứ tự thời gian:

```python
class FIFOSlots:
    def __init__(self):
        self.item_details = {}  # Thông tin chi tiết item
        self.transferred_item_details = {}  # Transfer bucket cho repack
        self.serial_no_batch_purchase_details = {}  # Serial number tracking
        self.invoice_number_details = {}  # Custom invoice tracking
```

### Cấu Trúc Slot Mở Rộng

```python
# Standard Slot Structure:
slot = [
    quantity,           # float: Số lượng
    posting_date,       # date: Ngày giao dịch (có thể là custom_receive_date)
    stock_value,        # float: Giá trị tồn kho
    custom_invoice_number  # string: Số hóa đơn tùy chỉnh
]
```

## Quy Trình Xử Lý Chi Tiết

### 1. Xử Lý Hàng Nhập Kho (Incoming Stock)

```python
def __compute_incoming_stock(self, row, fifo_queue, transfer_key, serial_nos):
    """
    Xử lý hàng nhập kho với custom_invoice_number tracking
    """
    
    # Kiểm tra có transfer data từ repack không
    transfer_data = self.transferred_item_details.get(transfer_key)
    
    if transfer_data:
        # Xử lý repack: thêm lại hàng đã được chuyển đổi
        self.__adjust_incoming_transfer_qty(transfer_data, fifo_queue, row)
    else:
        # Xử lý hàng nhập thông thường
        if not serial_nos and not row.get("has_serial_no"):
            if fifo_queue and flt(fifo_queue[0][0]) <= 0:
                # Cân bằng stock âm
                fifo_queue[0][0] += flt(row.actual_qty)
                fifo_queue[0][1] = row.posting_date
                fifo_queue[0][2] += flt(row.stock_value_difference)
                fifo_queue[0][3] = row.get("custom_invoice_number", "")
            else:
                # Thêm slot mới
                fifo_queue.append([
                    flt(row.actual_qty), 
                    row.posting_date, 
                    flt(row.stock_value_difference),
                    row.get("custom_invoice_number", "")
                ])
```

### 2. Xử Lý Hàng Xuất Kho (Outgoing Stock)

```python
def __compute_outgoing_stock(self, row, fifo_queue, transfer_key, serial_nos):
    """
    Xử lý hàng xuất kho theo nguyên tắc FIFO
    """
    
    qty_to_pop = abs(row.actual_qty)
    stock_value = abs(row.stock_value_difference)

    while qty_to_pop:
        slot = fifo_queue[0] if fifo_queue else [0, None, 0, ""]
        
        if 0 < flt(slot[0]) <= qty_to_pop:
            # Tiêu thụ toàn bộ slot
            qty_to_pop -= flt(slot[0])
            stock_value -= flt(slot[2])
            # Lưu vào transfer bucket với custom_invoice_number
            self.transferred_item_details[transfer_key].append(fifo_queue.pop(0))
            
        elif not fifo_queue:
            # Xử lý stock âm
            fifo_queue.append([
                -(qty_to_pop), 
                row.posting_date, 
                -(stock_value), 
                row.get("custom_invoice_number", "")
            ])
            qty_to_pop = 0
            
        else:
            # Tiêu thụ một phần slot
            slot[0] = flt(slot[0]) - qty_to_pop
            slot[2] = flt(slot[2]) - stock_value
            # Lưu phần tiêu thụ vào transfer bucket
            self.transferred_item_details[transfer_key].append([
                qty_to_pop, 
                slot[1], 
                stock_value, 
                slot[3] if len(slot) > 3 else ""
            ])
            qty_to_pop = 0
```

### 3. Xử Lý Stock Reconciliation Đặc Biệt

```python
if d.voucher_type == "Stock Reconciliation":
    # Tính actual_qty từ sự thay đổi
    prev_balance_qty = self.item_details[key].get("qty_after_transaction", 0)
    d.actual_qty = flt(d.qty_after_transaction) - flt(prev_balance_qty)
    
    # Sử dụng custom_receive_date cho Opening Stock
    if d.get("custom_receive_date") and "Opening Stock" in str(d.get("voucher_no", "")):
        d.posting_date = d.custom_receive_date
```

## Tính Toán Tuổi Tồn Kho

### 1. Tuổi Trung Bình (Average Age)

```python
def get_average_age(fifo_queue, to_date):
    """
    Tính tuổi trung bình có trọng số theo số lượng
    """
    batch_age = age_qty = total_qty = 0.0
    
    for batch in fifo_queue:
        batch_age = date_diff(to_date, batch[1])  # Tính số ngày từ posting_date
        
        if isinstance(batch[0], (int, float)):
            age_qty += batch_age * batch[0]  # Trọng số theo số lượng
            total_qty += batch[0]
        else:
            # Xử lý serial number
            age_qty += batch_age * 1
            total_qty += 1
    
    return flt(age_qty / total_qty, 2) if total_qty else 0.0
```

### 2. Phân Tích Theo Khoảng Tuổi

```python
def get_range_age(filters, fifo_queue, to_date, item_dict):
    """
    Phân loại tồn kho theo các khoảng tuổi: 0-180, 181-360, 361-720, >720
    """
    precision = cint(frappe.db.get_single_value("System Settings", "float_precision"))
    
    # Tạo mảng để lưu kết quả
    if filters.get("show_value"):
        range_values = [0.0] * ((len(filters.ranges) * 2) + 2)  # [qty, value, qty, value, ...]
    else:
        range_values = [0.0] * (len(filters.ranges) + 1)  # Chỉ quantity
    
    for item in fifo_queue:
        age = flt(date_diff(to_date, item[1]))
        qty = flt(item[0]) if not item_dict["has_serial_no"] else 1.0
        stock_value = flt(item[2])
        
        # Phân loại vào khoảng tuổi tương ứng
        for i, age_limit in enumerate(filters.ranges):  # [180, 360, 720]
            if age <= flt(age_limit):
                if filters.get("show_value"):
                    i *= 2
                    range_values[i] = flt(range_values[i] + qty, precision)
                    range_values[i + 1] = flt(range_values[i + 1] + stock_value, precision)
                else:
                    range_values[i] = flt(range_values[i] + qty, precision)
                break
        else:
            # Vượt quá tất cả khoảng tuổi - đưa vào khoảng cuối
            if filters.get("show_value"):
                range_values[-2] = flt(range_values[-2] + qty, precision)
                range_values[-1] = flt(range_values[-1] + stock_value, precision)
            else:
                range_values[-1] = flt(range_values[-1] + qty, precision)
    
    return range_values
```

## Xử Lý Các Trường Hợp Đặc Biệt

### 1. Repack Entries (Manufacturing/Conversion)

**Khái niệm Transfer Bucket**:
- Khi có repack, hàng được tiêu thụ từ FIFO queue
- Hàng sau khi repack được thêm lại với ngày gốc để duy trì tính chính xác
- Transfer bucket theo dõi hàng đã tiêu thụ tạm thời

```python
def __adjust_incoming_transfer_qty(self, transfer_data, fifo_queue, row):
    """
    Thêm lại hàng đã được repack với thông tin ngày gốc
    """
    transfer_qty_to_pop = flt(row.actual_qty)
    stock_value = flt(row.stock_value_difference)

    while transfer_qty_to_pop:
        if transfer_data and 0 < transfer_data[0][0] <= transfer_qty_to_pop:
            # Sử dụng hết bucket
            transfer_qty_to_pop -= transfer_data[0][0]
            stock_value -= transfer_data[0][2]
            add_to_fifo_queue(transfer_data.pop(0))
        elif not transfer_data:
            # Bucket rỗng - hàng thừa từ repack
            add_to_fifo_queue([
                transfer_qty_to_pop, 
                row.posting_date, 
                stock_value, 
                row.get("custom_invoice_number", "")
            ])
            transfer_qty_to_pop = 0
        else:
            # Sử dụng một phần bucket
            transfer_data[0][0] -= transfer_qty_to_pop
            transfer_data[0][2] -= stock_value
            add_to_fifo_queue([
                transfer_qty_to_pop, 
                transfer_data[0][1], 
                stock_value,
                transfer_data[0][3] if len(transfer_data[0]) > 3 else ""
            ])
            transfer_qty_to_pop = 0
```

### 2. Serial Number Items

```python
# Xử lý serial number riêng biệt
for serial_no in serial_nos:
    if self.serial_no_batch_purchase_details.get(serial_no):
        # Sử dụng ngày mua đã lưu
        fifo_queue.append([
            serial_no, 
            self.serial_no_batch_purchase_details.get(serial_no), 
            valuation,
            row.get("custom_invoice_number", "")
        ])
    else:
        # Lưu ngày mua mới
        self.serial_no_batch_purchase_details.setdefault(serial_no, row.posting_date)
        fifo_queue.append([
            serial_no, 
            row.posting_date, 
            valuation,
            row.get("custom_invoice_number", "")
        ])
```

### 3. Negative Stock Handling

```python
# Khi stock âm
if not fifo_queue:
    # Tạo slot âm
    fifo_queue.append([
        -(qty_to_pop), 
        row.posting_date, 
        -(stock_value), 
        row.get("custom_invoice_number", "")
    ])
    
    # Lưu vào transfer bucket
    self.transferred_item_details[transfer_key].append([
        qty_to_pop, 
        row.posting_date, 
        stock_value, 
        row.get("custom_invoice_number", "")
    ])
```

## Tính Năng Hiển Thị Mở Rộng

### 1. Show Value Toggle

```python
# Khi show_value = True: [qty1, val1, qty2, val2, qty3, val3, qty4, val4]
# Khi show_value = False: [qty1, qty2, qty3, qty4]

if filters.get("show_value"):
    row.extend(range_values)  # Toàn bộ
else:
    qty_only_values = [range_values[i] for i in range(0, len(range_values), 2)]
    row.extend(qty_only_values)  # Chỉ quantity
```

### 2. Variant Attributes Display

```python
def get_variant_attributes(item_code):
    """
    Lấy thuộc tính variant của item
    """
    variant_attrs = frappe.db.sql("""
        SELECT attribute, attribute_value 
        FROM `tabItem Variant Attribute`
        WHERE parent = %s
        ORDER BY idx
    """, item_code, as_dict=1)
    
    attr_values = [attr.attribute_value for attr in variant_attrs] if variant_attrs else []
    
    # Đảm bảo có đủ 3 cột attribute
    while len(attr_values) < 3:
        attr_values.append("")
    
    return attr_values[:3]
```

## Ví Dụ Minh Họa

### Ví Dụ 1: Opening Stock với Custom Receive Date

```
Input Data:
-----------
Voucher: "Opening Stock 001"
Posting Date: 2024-01-01
Custom Receive Date: 2023-12-15
Quantity: 100
Custom Invoice Number: "INV001"

Processing:
-----------
# Vì có "Opening Stock" trong voucher_no và có custom_receive_date
posting_date được thay thế = "2023-12-15"

FIFO Queue Result:
------------------
[[100, "2023-12-15", 10000, "INV001"]]

Age Calculation (to_date = 2024-06-01):
---------------------------------------
Age = date_diff("2024-06-01", "2023-12-15") = 169 ngày
Range: 0-180 ngày
```

### Ví Dụ 2: Theo Dõi Theo Custom Invoice Number

```
Input Transactions:
-------------------
1. Date: 2024-01-01, Qty: +50, Invoice: "INV001"
2. Date: 2024-01-15, Qty: +30, Invoice: "INV002"  
3. Date: 2024-02-01, Qty: -20, Invoice: ""

FIFO Processing:
----------------
After Transaction 1: [[50, "2024-01-01", 5000, "INV001"]]
After Transaction 2: [[50, "2024-01-01", 5000, "INV001"], [30, "2024-01-15", 3000, "INV002"]]
After Transaction 3: [[30, "2024-01-01", 3000, "INV001"], [30, "2024-01-15", 3000, "INV002"]]

Transfer Bucket:
----------------
Key: ("SE-003", "Item A", "Warehouse 1")
Value: [[20, "2024-01-01", 2000, "INV001"]]  # 20 units from INV001 consumed

Result Analysis:
----------------
- Remaining Stock: 60 units
- 30 units from INV001 (older batch)
- 30 units from INV002 (newer batch)
- Traceability maintained through custom_invoice_number
```

### Ví Dụ 3: Age Range Analysis

```
FIFO Queue (to_date = 2024-12-01):
-----------------------------------
[[100, "2024-01-01", 10000, "INV001"],    # Age: 335 days
 [50,  "2024-06-01", 5000,  "INV002"],    # Age: 183 days  
 [75,  "2024-10-01", 7500,  "INV003"]]    # Age: 61 days

Age Range Processing (ranges = [180, 360, 720]):
------------------------------------------------
Item 1 (Age: 335): 181-360 range
Item 2 (Age: 183): 181-360 range  
Item 3 (Age: 61):  0-180 range

Result:
-------
Range 0-180:     Qty: 75,  Value: 7500
Range 181-360:   Qty: 150, Value: 15000
Range 361-720:   Qty: 0,   Value: 0
Range >720:      Qty: 0,   Value: 0
```

## Performance Considerations

### 1. Database Optimization
```python
# Sử dụng unbuffered cursor cho dataset lớn
with frappe.db.unbuffered_cursor():
    stock_ledger_entries = self.__get_stock_ledger_entries()
    
# Iterator pattern để tránh memory overflow
return sle_query.run(as_dict=True, as_iterator=True)
```

### 2. Memory Management
```python
# Xóa iterator sau khi sử dụng
del stock_ledger_entries

# Sử dụng generator thay vì list khi có thể
def filter_entries(entries):
    for entry in entries:
        if entry.meets_criteria():
            yield entry
```

### 3. Query Optimization
```python
# Chỉ select các field cần thiết
sle_query = frappe.qb.from_(sle).select(
    item.name, item.item_name, item.item_group,
    sle.actual_qty, sle.posting_date, sle.custom_invoice_number
).where(conditions)

# Sử dụng proper indexing
sle_query = sle_query.orderby(sle.posting_datetime, sle.creation)
```

## Lưu Ý Quan Trọng

### 1. Data Consistency
- Custom fields có thể null - code xử lý gracefully
- Backward compatibility với dữ liệu cũ
- Validation cho custom_receive_date và custom_invoice_number

### 2. Error Handling
```python
# Xử lý missing fields
custom_invoice = row.get("custom_invoice_number", "")
custom_date = row.get("custom_receive_date") 

# Validation
if custom_date and custom_date > today():
    frappe.msgprint("Custom receive date cannot be in future")
```

### 3. Access Control
- Đảm bảo user permissions cho custom fields
- Role-based access cho báo cáo
- Audit trail cho các thay đổi custom fields

## Kết Luận

Thuật toán **Stock Ageing Customize** cung cấp một giải pháp toàn diện và linh hoạt để:

1. **Theo dõi tuổi tồn kho chính xác** với custom receive date
2. **Quản lý truy xuất nguồn gốc** qua custom invoice number  
3. **Phân tích chi tiết** với các khoảng tuổi phù hợp
4. **Hiển thị linh hoạt** theo nhu cầu người dùng
5. **Xử lý robust** các trường hợp phức tạp như repack, serial items, negative stock

Thuật toán này đặc biệt phù hợp cho các doanh nghiệp có nhu cầu quản lý tồn kho chi tiết và truy xuất nguồn gốc hàng hóa chặt chẽ.