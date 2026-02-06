Hệ thống Quản lý Nghỉ phép (Leave Management) trong Frappe HR là một giải pháp toàn diện cho phép tổ chức cấu hình linh hoạt các loại phép, chính sách và quy trình phê duyệt tự động nhằm tối ưu hóa trải nghiệm của nhân viên và hiệu quả quản trị của HR.
Dưới đây là tổng hợp chi tiết tất cả thông tin và cài đặt dựa trên tài liệu gốc:
1. Leave Type (Loại phép)
Đây là tài liệu cơ bản nhất dùng để định nghĩa các loại hình nghỉ phép (ví dụ: Phép năm, Nghỉ ốm) và các quy tắc đi kèm.
• Các cài đặt chính và ý nghĩa:
    ◦ Maximum Leave Allocation Allowed: Số ngày tối đa được phép phân bổ cho loại phép này trong một giai đoạn.
    ◦ Applicable After (Working Days): Số ngày làm việc tối thiểu kể từ ngày gia nhập để nhân viên bắt đầu được sử dụng loại phép này.
    ◦ Is Carry Forward: Nếu tích chọn, số dư phép chưa dùng sẽ được chuyển sang kỳ phân bổ tiếp theo.
    ◦ Is Leave Without Pay: Đánh dấu là nghỉ không hưởng lương, hệ thống sẽ tự động trừ lương khi tính toán bảng lương.
    ◦ Allow Negative Balance: Cho phép nhân viên xin nghỉ ngay cả khi số dư đã hết.
    ◦ Include holidays within leaves as leaves: Nếu được chọn, các ngày lễ nằm giữa kỳ nghỉ sẽ bị tính là ngày nghỉ.
    ◦ Is Earned Leave: Loại phép tích lũy dần theo thời gian làm việc (ví dụ: mỗi tháng cộng 1 ngày).
    ◦ Allow Encashment: Cho phép quy đổi số dư phép chưa dùng thành tiền vào cuối kỳ.
2. Leave Period (Giai đoạn nghỉ phép)
Là khoảng thời gian (thường theo năm dương lịch hoặc tài chính) mà các ngày phép được phân bổ và có hiệu lực sử dụng.
• Thông tin cài đặt:
    ◦ From Date & To Date: Xác định chu kỳ hiệu lực của phép.
    ◦ Holiday List for Optional Leaves: Danh sách các ngày lễ tùy chọn mà nhân viên có thể chọn nghỉ trong kỳ này.
    ◦ Is Active: Đánh dấu giai đoạn này đang được sử dụng.
3. Leave Policy & Leave Policy Assignment
• Leave Policy (Chính sách phép): Tập hợp danh sách các Leave Type và số ngày nghỉ tương ứng mà một nhóm nhân viên được hưởng trong một năm.
• Leave Policy Assignment (Gán chính sách): Dùng để áp dụng chính sách cho từng nhân viên hoặc hàng loạt nhân viên.
    ◦ Assignment based on: Có thể chọn dựa trên Leave Period (Giai đoạn cố định) hoặc Joining Date (Ngày gia nhập của nhân viên) để xác định mốc thời gian bắt đầu hưởng phép.
    ◦ Khi tài liệu này được gửi (Submit), hệ thống sẽ tự động tạo bản ghi Leave Allocation cho nhân viên.
4. Leave Allocation (Phân bổ phép)
Tài liệu này chính thức cấp số dư phép cho nhân viên để họ có thể nộp đơn xin nghỉ.
• Các phương thức tạo:
    ◦ Tự động qua Leave Policy Assignment.
    ◦ Tạo hàng loạt qua Leave Control Panel.
    ◦ Tự động cộng phép khi duyệt Compensatory Leave Request (Nghỉ bù).
• Leave Adjustment (v16): Cho phép HR tăng hoặc giảm số dư đã phân bổ trực tiếp nếu phát hiện sai sót, hệ thống sẽ tự lưu nhật ký điều chỉnh.
5. Quy trình Đơn xin nghỉ phép (Leave Application)
Đây là tài liệu do nhân viên tạo để đăng ký ngày nghỉ.
• Cài đặt Người phê duyệt (Leave Approver):
    ◦ Cấp Phòng ban (Department): Cài đặt trong hồ sơ phòng ban, người đầu tiên trong danh sách là mặc định.
    ◦ Cấp Nhân viên (Employee): Cài đặt trực tiếp cho từng cá nhân, cấp độ này có ưu tiên cao hơn cấp phòng ban.
• Quy tắc ràng buộc:
    ◦ Không được nghỉ vào ngày nằm trong Leave Block List (trừ người có quyền đặc biệt).
    ◦ Không thể nộp đơn nếu lương của tháng đó đã được xử lý xong.
    ◦ Đơn nghỉ phải nằm trọn trong một giai đoạn phân bổ phép duy nhất.
6. Các tính năng chuyên sâu khác
• Compensatory Leave Request: Đơn xin nghỉ bù khi nhân viên làm việc vào ngày lễ hoặc làm thêm giờ.
• Leave Encashment: Quy đổi phép thành tiền, hệ thống sẽ tự tạo một khoản Additional Salary để cộng vào bảng lương.
• Holiday List Assignment (v16): Cho phép gán nhiều danh sách ngày lễ theo thời gian, giúp lưu vết lịch sử khi nhân viên chuyển chi nhánh/phòng ban.
• Leave Ledger (Sổ cái phép): Một hệ thống sổ cái thống nhất ghi lại mọi giao dịch (cấp phép, nghỉ phép, quy đổi) để đảm bảo tính minh bạch và báo cáo chính xác.