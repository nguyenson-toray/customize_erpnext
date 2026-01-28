# Overtime Registration - Tài liệu Thuật toán

## Tổng quan
Tài liệu này mô tả các thuật toán xác thực và logic nghiệp vụ cho doctype Overtime Registration.

## Các Hàm Xác thực

### 1. validate_duplicate_employees() - Kiểm tra trùng lặp trong form
**Mục đích**: Ngăn chặn các bản ghi tăng ca trùng lặp hoặc chồng chéo thời gian trong cùng một form.

**Thuật toán**:
1. Thu thập tất cả entries từ bảng con `ot_employees`
2. Xác thực các trường bắt buộc (employee, date, from, to) cho mỗi entry
3. So sánh từng entry với mọi entry khác sử dụng vòng lặp lồng nhau
4. Với các entry có cùng employee và date, kiểm tra chồng chéo thời gian bằng hàm `times_overlap()`
5. Nếu phát hiện chồng chéo, hiển thị thông báo lỗi và ngăn lưu

**Độ phức tạp thời gian**: O(n²) với n là số lượng entries

**Ví dụ**:
- ✅ Hợp lệ: Nhân viên A (16:00-18:00) và Nhân viên A (18:00-20:00) - Thời gian kề nhau
- ❌ Không hợp lệ: Nhân viên A (16:00-18:00) và Nhân viên A (17:00-19:00) - Thời gian chồng chéo

### 2. validate_conflicting_ot_requests() - Kiểm tra xung đột với yêu cầu đã có
**Mục đích**: Ngăn chặn xung đột với các yêu cầu tăng ca đã được submit trước đó.

**Thuật toán**:
1. Do việc truy vấn database từ client-side gặp vấn đề phân quyền
2. Hàm này chuyển việc kiểm tra xung đột cho server-side (Python)
3. JavaScript chỉ xác thực các trường hợp trong form hiện tại
4. Server sẽ kiểm tra và báo lỗi nếu có xung đột với dữ liệu đã có

**Triển khai**:
- Client-side: Chỉ kiểm tra trong form hiện tại
- Server-side: Kiểm tra với database đầy đủ

### 3. calculate_totals_and_apply_reason() - Tính tổng và áp dụng lý do
**Mục đích**: Quản lý trường lý do chung và tính toán các tổng số.

**Thuật toán**:
1. **Tính Tổng số**:
   - Đếm nhân viên riêng biệt sử dụng Set
   - Tính tổng giờ tăng ca bằng cách tính hiệu thời gian
   - Cập nhật trường `total_employees` và `total_hours`

2. **Quản lý Lý do**:
   - Nếu `reason_general` trống:
     - Thu thập các lý do duy nhất, không trống từ các dòng con
     - Sắp xếp và nối chúng bằng dấu phẩy
     - Đặt làm `reason_general`
   - Nếu `reason_general` đã có giá trị:
     - Áp dụng cho tất cả các dòng con có lý do trống

**Ví dụ**:
- Lý do con: ["Đơn hàng gấp", "Yêu cầu khách hàng"] → Chung: "Đơn hàng gấp, Yêu cầu khách hàng"
- Chung: "Deadline sản xuất" → Áp dụng cho tất cả lý do con trống

## Hàm Hỗ trợ

### times_overlap(from1, to1, from2, to2) - Kiểm tra chồng chéo thời gian
**Mục đích**: Xác định hai khoảng thời gian có chồng chéo hay không.

**Thuật toán**:
```javascript
// Chuyển đổi chuỗi thời gian thành Date objects
time1Start = new Date(`2000-01-01T${from1}`)
time1End = new Date(`2000-01-01T${to1}`)
time2Start = new Date(`2000-01-01T${from2}`)
time2End = new Date(`2000-01-01T${to2}`)

// Kiểm tra chồng chéo sử dụng công thức giao của khoảng
return time1Start < time2End && time2Start < time1End
```

**Giải thích Logic**:
- Sử dụng thuật toán phát hiện chồng chéo khoảng tiêu chuẩn
- Các khoảng kề nhau (16:00-18:00 và 18:00-20:00) trả về false (không chồng chéo)
- Các khoảng chồng chéo (16:00-18:00 và 17:00-19:00) trả về true

**Các Trường hợp Kiểm tra**:
| Khoảng 1 | Khoảng 2 | Chồng chéo | Lý do |
|----------|----------|------------|-------|
| 16:00-18:00 | 18:00-20:00 | ❌ | Kề nhau (chạm điểm cuối) |
| 16:00-18:00 | 17:00-19:00 | ✅ | Chồng chéo |
| 16:00-18:00 | 14:00-16:00 | ❌ | Kề nhau (chạm điểm đầu) |
| 16:00-18:00 | 14:00-17:00 | ✅ | Chồng chéo |
| 16:00-18:00 | 17:00-17:30 | ✅ | Khoảng này chứa khoảng kia |
| 16:00-18:00 | 19:00-21:00 | ❌ | Hoàn toàn tách biệt |

## Chi tiết Triển khai

### Xác thực Client-Side (JavaScript)
- Xác thực trùng lặp trong form được triển khai bằng JavaScript
- Thực thi trong sự kiện `validate` của form trước khi submit
- Cung cấp phản hồi ngay lập tức cho người dùng
- Sử dụng `frappe.validated = false` để ngăn submit form

### Xác thực Server-Side (Python)
- Xác thực xung đột với dữ liệu existing được xử lý bằng Python
- Có quyền truy cập đầy đủ database
- Xử lý trong method `validate()` của document
- Hiển thị lỗi với link có thể click đến document xung đột

### Thông báo Lỗi
- Hỗ trợ đa ngôn ngữ sử dụng hàm `__()`
- Bao gồm số dòng để dễ dàng xác định
- Link có thể click đến document xung đột
- Thông tin chi tiết về khoảng thời gian

### Cân nhắc Hiệu suất
- Xác thực trùng lặp: Độ phức tạp O(n²) có thể chấp nhận cho các trường hợp thông thường
- Xác thực xung đột: Sử dụng truy vấn database nhưng giới hạn bởi filters employee/date
- Tất cả xác thực chạy đồng bộ để đảm bảo tính toàn vẹn dữ liệu

## Cấu trúc Database

### Overtime Registration (Parent)
- `reason_general`: Lý do chung áp dụng cho tất cả entries
- `total_employees`: Số lượng nhân viên riêng biệt được tính
- `total_hours`: Tổng số giờ tăng ca được tính

### Overtime Registration Detail (Child)
- `employee`: Link đến Employee master
- `date`: Ngày tăng ca
- `from`: Thời gian bắt đầu
- `to`: Thời gian kết thúc  
- `reason`: Lý do cụ thể (có thể kế thừa từ lý do chung)

## Quy tắc Nghiệp vụ

1. **Trường Bắt buộc**: Employee, Date, From Time, To Time phải được cung cấp
2. **Không Chồng chéo**: Cùng nhân viên không thể có khoảng thời gian chồng chéo trong cùng ngày
3. **Cho phép Kề nhau**: Khoảng thời gian chạm nhau (16:00-18:00, 18:00-20:00) là hợp lệ
4. **Ngăn chặn Xung đột**: Không thể tạo entries chồng chéo với requests đã submit
5. **Kế thừa Lý do**: Lý do chung áp dụng cho entries không có lý do riêng
6. **Tự động Tính tổng**: Số lượng nhân viên và giờ được tính tự động

## Xử lý Lỗi

### Lỗi Xác thực
- Dừng thực thi ngay khi tìm thấy lỗi đầu tiên
- Hiển thị thông báo lỗi rõ ràng với tham chiếu dòng
- Làm nổi bật xung đột cụ thể với dữ liệu existing

### Tính toàn vẹn Dữ liệu
- Tất cả xác thực phải pass trước khi save
- Các thao tác atomic đảm bảo tính nhất quán
- Link đến document xung đột để dễ dàng giải quyết

## Kiến trúc Hybrid

### JavaScript (Client-side)
- **Ưu điểm**: Phản hồi tức thì, trải nghiệm người dùng tốt
- **Hạn chế**: Không thể truy vấn database do vấn đề phân quyền
- **Sử dụng cho**: Xác thực trong form hiện tại

### Python (Server-side)  
- **Ưu điểm**: Quyền truy cập đầy đủ database, bảo mật
- **Hạn chế**: Phản hồi chậm hơn
- **Sử dụng cho**: Xác thực với dữ liệu existing, logic phức tạp

### Tổng kết Approach
1. **JavaScript xử lý**: Trùng lặp trong form, tính toán tổng, áp dụng lý do
2. **Python xử lý**: Xung đột với database, xác thực phức tạp
3. **Kết hợp**: Tối ưu trải nghiệm người dùng và bảo mật dữ liệu