# Daily Timesheet Report - Báo Cáo Chấm Công Hàng Ngày

## Tổng Quan
Báo cáo Daily Timesheet Report được thiết kế để theo dõi và xuất báo cáo chấm công chi tiết của nhân viên theo từng ngày, phục vụ việc tính toán lương và quản lý nhân sự.

## Đặc Điểm Chính

### 🔍 Hiển Thị Dữ Liệu
- **Luôn hiển thị tất cả nhân viên** đang làm việc trong khoảng thời gian được chọn
- **Nhân viên có dữ liệu chấm công**: Hiển thị đầy đủ thông tin working hours, overtime, check in/out
- **Nhân viên không có dữ liệu chấm công**: Hiển thị thông tin cá nhân, các cột thời gian để trống hoặc = 0

### 📊 Chế Độ Hiển Thị
1. **Detail Mode (Summary = 0)**: Hiển thị từng record hàng ngày của mỗi nhân viên
2. **Summary Mode (Summary = 1)**: Tổng hợp dữ liệu theo nhân viên trong khoảng thời gian

## Bộ Lọc (Filters)

### 📅 Thời Gian
- **Date Type**: Chọn loại khoảng thời gian
  - *Single Date*: Chọn một ngày cụ thể
  - *Date Range*: Chọn khoảng từ ngày - đến ngày  
  - *Monthly*: Chọn tháng và năm (từ ngày 26 tháng trước đến ngày 25 tháng hiện tại)

### 👥 Nhân Viên
- **Department**: Lọc theo phòng ban
- **Section**: Lọc theo bộ phận
- **Group**: Lọc theo nhóm
- **Employee**: Lọc theo nhân viên cụ thể
- **Status**: Lọc theo trạng thái (Present, Absent, Half Day, v.v.)

### ⚙️ Tùy Chọn Hiển Thị
- **Summary**: Tổng hợp dữ liệu theo nhân viên (mặc định: Detail)
- **Detail Columns**: Hiển thị các cột chi tiết bổ sung
- **Chart Type**: Chọn loại biểu đồ (Department Summary, Top 50 Overtime, Top 50 Working Hours)

## Cột Dữ Liệu

### 📋 Thông Tin Cơ Bản
- **Employee**: Mã nhân viên
- **Employee Name**: Tên nhân viên  
- **Group**: Nhóm/Chuyền
- **Attendance Date**: Ngày chấm công (chỉ ở Detail Mode)
- **Shift**: Ca làm việc

### ⏰ Thời Gian Làm Việc
- **Check In/Check Out**: Giờ vào/ra (Detail Mode)
- **Working Hours**: Số giờ làm việc
- **Working Days**: Số ngày công (= Working Hours / 8)

### 🕐 Overtime
- **Actual OT**: Overtime thực tế
- **Registered OT**: Overtime đã đăng ký
- **Final OT**: Overtime cuối cùng được tính
- **Overtime Coefficient**: Hệ số overtime (Detail Columns)
- **Final OT - With Coefficient**: Overtime tính theo hệ số (Detail Columns)

### 📝 Chi Tiết Bổ Sung (Detail Columns = 1)
- **Department**: Phòng ban
- **Section**: Bộ phận
- **Late Entry**: Đi trễ
- **Early Exit**: Về sớm
- **Maternity Benefit**: Thai sản
- **Date of Joining**: Ngày vào làm
- **Relieving Date**: Ngày nghỉ việc
- **Status**: Trạng thái chấm công

## 📈 Biểu Đồ

### 1. Department Summary
- Hiển thị tổng Working Hours và Overtime Hours theo từng phòng ban
- Biểu đồ cột dọc, chiều cao 150px

### 2. Top 50 - Highest Overtime  
- Top 50 nhân viên có Overtime cao nhất
- Biểu đồ cột ngang, chiều cao 150px

### 3. Top 50 - Highest Working Hours
- Top 50 nhân viên có Working Hours cao nhất  
- Biểu đồ cột ngang, chiều cao 150px

## 📤 Export Excel

### ✨ Tính Năng
- **Button**: "Export Excel - HR Template"
- **Luôn xuất dữ liệu chi tiết** (tự động set Summary = 0)
- **Template chuẩn HR** với format bảng chấm công

### 📊 Nội Dung Excel
- **Header**: Tiêu đề song ngữ (Tiếng Anh/Tiếng Việt)
- **Employee Data**: Thông tin nhân viên theo department
- **Daily Data**: Working days cho từng ngày trong period
- **Total Row**: Tổng cộng working days
- **Signatures**: Chữ ký Prepared by, Verified by, Approved by
- **Legend**: Chú thích các ký hiệu chấm công

### 📅 Format Ngày
- **Monthly**: "Jan 2025/ Tháng 01 năm 2025"
- **Date Range**: "01-01-2025 - 31-01-2025"
- **Single Date**: "01-01-2025"

## 🔧 Logic Kỹ Thuật

### 💾 Nguồn Dữ Liệu
- **Chính**: `tabDaily Timesheet` (bảng chấm công chi tiết)
- **Phụ trợ**: `tabEmployee` (thông tin nhân viên)

### 🔄 Xử Lý Dữ Liệu
1. **LEFT JOIN** từ Employee sang Daily Timesheet
2. **Luôn hiển thị tất cả active employees** trong period
3. **Missing data** = 0 hoặc NULL cho các cột thời gian
4. **Decimal rounding** với độ chính xác 2 chữ số thập phân

### 📋 Điều Kiện Lọc
- **Active Period**: `(date_of_joining <= period_end) AND (relieving_date >= period_start)`
- **Exclude Departments**: 'Head of Branch - TIQN', 'Operations Manager - TIQN'
- **Docstatus**: `<= 1` (Draft và Submitted)

## 📝 Lưu Ý Sử Dụng

### ✅ Ưu Điểm
- **Hiển thị đầy đủ**: Không bỏ sót nhân viên nào trong period
- **Linh hoạt**: Nhiều tùy chọn lọc và hiển thị  
- **Export chuẩn**: Template Excel phù hợp với quy trình HR
- **Performance tốt**: Query tối ưu với LEFT JOIN

### ⚠️ Lưu Ý
- **Monthly period**: Từ 26 tháng trước đến 25 tháng hiện tại
- **Working Day**: Tính bằng Working Hours / 8
- **Export luôn Detail**: Không phụ thuộc vào Summary checkbox trên UI
- **Cache**: Cần clear browser cache sau khi update code

## 🔄 Version History
- **v2.0**: Loại bỏ show_zero filter, luôn hiển thị tất cả active employees
- **v1.9**: Force Summary = 0 trong Excel export
- **v1.8**: Giảm chart height từ 300px xuống 150px
- **v1.7**: Tích hợp export Excel với template HR chuẩn