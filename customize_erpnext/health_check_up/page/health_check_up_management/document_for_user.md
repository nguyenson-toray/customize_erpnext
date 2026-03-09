# Hướng Dẫn Sử Dụng Phầm Mềm Quản Lý Khám Sức Khỏe

## 1. Giới thiệu chung
- Phần mềm giúp hỗ trợ công tác phát hành và thu nhận hồ sơ khám sức khỏe một cách nhanh chóng thông qua việc quét mã vạch (Barcode) và theo dõi tiến độ theo thời gian thực ngay trên trình duyệt.
- Truy cập http://erp.tiqn.local/desk ➡️ Health Check-Up
- Nhập thủ công hoặc Import danh sách vào doctype "Health Check-Up"
- Truy cập trang quản lý : Health Check Up Management : http://erp.tiqn.local/desk/health-check-up-management
### ℹ️ Toàn bộ dữ liệu được lưu tập trung tại doctype "Health Check-Up" ###
## 2. Giao diện chính
Màn hình được chia làm 4 tab chính để dể thao tác:
- **📊 Tổng Quan**: Xem biểu đồ và tiến độ tổng thể của toàn bộ nhân viên tương ứng đợt khám sức khỏe.
- **📥 Phát Hồ Sơ**: Chức năng để ghi nhận lúc nhân viên đến lấy hồ sơ (Bắt đầu khám).
- **📤 Thu Hồ Sơ**: Chức năng để thu lại hồ sơ (Khi nhân viên đã khám xong).
- **📋 Danh Sách NV**: Xem chi tiết trạng thái của từng nhân viên, xem ai nộp trễ, xuất file Excel để báo cáo.
- ** Chọn ngày khám & Cấu hình thời gian trễ cho phép **
---

## 3. Hướng dẫn các thao tác cơ bản

### 3.1. Phát Hồ Sơ (Cho nhân viên bắt đầu khám)
1. Bấm vào thẻ **Phát Hồ Sơ** ở menu phía trên.
2. Dùng súng quét mã vạch để quét **Mã Nhân Viên**, hoặc gõ tay bằng bàn phím (Chỉ cần gõ 4 số cuối của mã nhân viên).
3. Hệ thống sẽ tự động tìm kiếm hiển thị Họ tên & Nhóm nhân viên trên nút bấm màu xanh.
4. *(Tùy chọn)* Nhập thêm ghi chú vào ô trống bên cạnh nếu cần thiết.
5. Bấm nút **"Ghi nhận: [Tên nhân viên]"** hoặc nhấn phím `Enter` để lưu lại.
6. Kết quả (Lịch sử quét trạm) sẽ hiện ngay trên khung màn hình bên dưới.

### 3.2. Thu Hồ Sơ (Khi nhân viên đã khám xong)
1. Bấm vào thẻ **Thu Hồ Sơ**.
2. Tiếp tục thao tác quét mã vạch (hoặc gõ tay 4 số).
3. Khi nhân viên nộp lại hồ sơ, nếu trong hồ sơ của họ có mục **X-Quang** hoặc **Phụ Khoa**, hãy dùng chuột đánh dấu tích (✔) vào 2 ô tương ứng phía dưới thanh quét mã. 
   *(💡 Hệ thống tự động nhận diện giới tính và đánh dấu sẵn mục "Khám phụ khoa" đối với nhân viên Nữ).*
4. Bấm nút **Ghi nhận** để hoàn tất quá trình khám.

### 3.3. Theo dõi Dashboard Tổng quan & Cảnh báo Trễ Giờ
1. Bấm vào thẻ **Tổng Quan**.
2. Phía trên cùng có nút **⚙️ Cấu hình**. Bạn có thể Click vào để chỉnh sửa các ngưỡng thời gian cho phép trễ (Mặc định là 10 phút):
   - *Phút khám trễ cho phép*: Quá thời gian này kể từ lúc hẹn lấy hồ sơ mà nhân viên chưa lấy, sẽ bị máy tính báo là **Trễ Giờ Phát HS** (Hiện màu đỏ).
   - *Phút nộp HS trễ cho phép*: Quá thời gian này kể từ lúc hẹn nộp hồ sơ mà chưa nộp, sẽ bị báo là **Trễ Giờ Thu HS** (Hiện màu cam).
3. Bạn có thể Click Đúp (nhấn chuột 2 lần liên tục) vào các ô thống kê màu sắc (Ví dụ: ô Chưa khám, Trễ giờ...) để bật lên cửa sổ Hiển thị danh sách chi tiết những người đang trong diện đó.

### 3.4. Xem Danh Sách và Tải Excel
1. Bấm vào thẻ **Danh Sách NV**.
2. Tại đây bạn có thể dùng khung Tìm kiếm, hoặc các nút Lọc để truy xuất nhanh nhân viên.
3. Cột **Chênh Lệch** trên bảng sẽ hiển thị cảnh báo trạng thái thời gian rõ ràng:
   - `⏳ Đang trễ P [x] phút`: Đang đến trễ giờ Phát sổ.
   - `⏳ Đang trễ T [x] phút`: Đang quá hạn giờ Thu sổ.
   - `Đã trễ P / T [x] phút`: Nhân viên đó đi muộn nhưng hiện tại đã hoàn thành. 
   - `Đúng giờ`: Khám đúng tiến độ.
4. Bấm nút **Tải file Excel** ở góc phải trên cùng màn hình để tải file Excel về máy tính.

