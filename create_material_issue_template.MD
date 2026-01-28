# Hướng dẫn sử dụng Import Material Issue Stock Entry

## Tổng quan
Tính năng "Import Material Issue Stock Entry" cho phép bạn tạo nhiều phiếu xuất kho (Stock Entry) cùng lúc từ file Excel.

## Cách sử dụng

### Bước 1: Tải xuống mẫu Excel
1. Truy cập danh sách Stock Entry
2. Nhấp nút "Actions" → "Import Stock Entry - Material Issue"
3. Trong hộp thoại, nhấp nút "Download Template" để tải file mẫu Excel

### Bước 2: Điền dữ liệu vào file Excel
Mở file Excel đã tải và điền thông tin:

**Các cột bắt buộc:**
- **Item Code**: Mã sản phẩm (phải tồn tại trong hệ thống)
- **Custom Item Name Detail**: Tên chi tiết sản phẩm
- **Quantity**: Số lượng xuất kho
- **Source Warehouse**: Kho xuất
- **Posting Date**: Ngày ghi sổ (định dạng: DD/MM/YYYY)
- **Custom No**: Số phiếu tùy chỉnh
- **Custom Invoice Number**: Số hóa đơn tùy chỉnh

**Lưu ý quan trọng:**
- Đảm bảo tất cả Item Code phải tồn tại trong hệ thống
- Kiểm tra kho có đủ số lượng tồn kho
- Ngày ghi sổ phải đúng định dạng
- Không được để trống các trường bắt buộc

### Bước 3: Upload và kiểm tra file
1. Chọn file Excel đã hoàn thành
2. Nhấp "Validate File" để kiểm tra dữ liệu
3. Xem kết quả kiểm tra:
   - ✅ **Thành công**: Hiển thị tổng số dòng hợp lệ
   - ❌ **Lỗi**: Hiển thị danh sách lỗi cần sửa

### Bước 4: Tạo Stock Entry
1. Sau khi validation thành công, nhấp "Import Stock Entries"
2. Hệ thống sẽ tạo các phiếu xuất kho tự động
3. Kiểm tra kết quả và danh sách Stock Entry được tạo

## Các lỗi thường gặp

### 1. Item không tồn tại
**Lỗi**: "Missing Items"
**Nguyên nhân**: Mã sản phẩm không có trong hệ thống
**Cách sửa**: Kiểm tra và sửa lại mã sản phẩm cho đúng

### 2. Kho không tồn tại
**Lỗi**: "Missing Warehouses" 
**Nguyên nhân**: Tên kho không đúng hoặc không tồn tại
**Cách sửa**: Kiểm tra tên kho và sửa lại cho đúng

### 3. Không đủ tồn kho
**Lỗi**: "Stock/Invoice Issues"
**Nguyên nhân**: Số lượng yêu cầu lớn hơn tồn kho hiện có
**Cách sửa**: Giảm số lượng xuất hoặc kiểm tra lại tồn kho

### 4. Lỗi định dạng ngày
**Lỗi**: Invalid date format
**Nguyên nhân**: Ngày không đúng định dạng DD/MM/YYYY
**Cách sửa**: Sửa lại định dạng ngày cho đúng

## Mẹo sử dụng hiệu quả

1. **Kiểm tra dữ liệu trước**: Luôn validate file trước khi import
2. **Sửa từng lỗi**: Đọc kỹ thông báo lỗi và sửa từng mục một
3. **Backup dữ liệu**: Sao lưu dữ liệu trước khi thực hiện import lớn
4. **Test với ít dữ liệu**: Thử với vài dòng trước khi import toàn bộ
5. **Kiểm tra sau import**: Xác nhận các Stock Entry được tạo đúng

## Hỗ trợ
Nếu gặp vấn đề, vui lòng liên hệ bộ phận IT để được hỗ trợ.