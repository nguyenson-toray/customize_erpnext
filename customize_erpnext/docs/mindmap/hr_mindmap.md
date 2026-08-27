<!-- HR Mindmap - Quản lý Nhân sự — Sơ đồ chức năng phần Nhân sự, dùng để giới thiệu và hướng dẫn người dùng -->
<!-- Tạo bằng build_mindmap.py. Nội dung và phân loại sửa trong script rồi chạy lại. -->
<!-- Nhãn tiến độ SỬA TRỰC TIẾP trong file này được, build lại vẫn giữ nguyên: [Done] | [In process 60%] | [Pending: lý do chưa làm] -->
<!-- Xem sơ đồ trên hệ thống: /mindmap?file=hr_mindmap.md -->
<!-- Hoặc dán toàn bộ file vào https://markmap.js.org/repl -->

# HR - Human Resources / Quản lý Nhân sự

> Hồ sơ nhân viên, chấm công, tăng ca, nghỉ phép và tiền lương

- **01. Employee Records / Hồ sơ nhân viên** `[Done]`
  - **01. [Organization structure / Cơ cấu tổ chức](/desk/department)** `[Standard]` `[Done]` — Công ty, phòng ban, chức danh, cấp bậc
    - **01. [Section & Group / Bộ phận & Nhóm](/desk/section)** `[Custom]` `[Done]` — Chia nhỏ phòng ban thành bộ phận và nhóm để chấm công, báo cáo chi tiết hơn
  - **02. [Employment Type / Loại hình lao động](/desk/employment-type)** `[Standard]` `[Done]` — Loại hình lao động: chính thức, thời vụ, thử việc; theo dõi ngày kết thúc thử việc
  - **03. [Employee profile / Thông tin nhân viên](/desk/employee)** `[Override]` `[Done]` — Thông tin cá nhân, phòng ban, chức danh, ngày vào làm, trạng thái làm việc...
  - **04. [Employee photo / Ảnh nhân viên](/employee-photos)** `[Custom]` `[Done]` — Tải ảnh, xóa nền, cắt ảnh thẻ đúng tỷ lệ, xử lý nhiều ảnh một lượt. File ảnh được sử dụng cho chức năng tạo thẻ Nv
  - **05. [Self-service update / Nhân viên tự cập nhật thông tin](/employee-self-update-info)** `[Custom]` `[Done]` — Nhân viên tự khai thông tin qua trang riêng, HR kiểm tra rồi cập nhật vào hồ sơ
  - **06. [Dependents / Người phụ thuộc](/desk/employee-dependent)** `[Custom]` `[In process 50%]` — Khai người phụ thuộc để tính giảm trừ thuế thu nhập cá nhân
  - **07. [Labor contract / Hợp đồng lao động](/desk/query-report/Labor%20Contract%20Report)** `[Custom]` `[Done]` — Loại hợp đồng, thời hạn, theo dõi hợp đồng sắp hết hạn cần tái ký
 <!--
  - **08. [External personnel / Nhân sự ngoài công ty](/desk/external-personnel)** `[Custom]` `[Done]` — Khách, nhà thầu, người ngoài bảng lương nhưng vẫn cần quản lý
  -->
  - **08. [Maternity records / Thai sản](/desk/query-report/Employee%20Maternity%20Report)** `[Custom]` `[Done]` — Theo dõi các mốc thời gian liên quan thai sản của nhân viên, dùng để tính toán công phép, chế độ
  - **09. [Onboarding / Tiếp nhận](/desk/employee-onboarding)** `[Standard]` `[In process 50%]` — Thủ tục tiếp nhận nhân viên mới: danh sách việc cần làm, bàn giao, hoàn tất hồ sơ
  - **10. [Transfer & promotion / Điều chuyển & thăng chức](/desk/employee-transfer)** `[Standard]` `[Done]` — Chuyển bộ phận, đổi chức danh, thăng chức và lưu lại lịch sử thay đổi
    - **01. [Employee Transfer / Điểu chuyển](/desk/employee-transfer)**  `[Override]` `[Done]`
    - **02. [Employee Promotion / Thăng chức](/desk/employee-promotion)**  `[Override]` `[Done]`
    - **03. [Employee Transfer and Promotion Report/ Báo cáo điều chuyển & thăng chức](/desk/query-report/Employee%20Transfer%20and%20Promotion)**  `[Custom]` `[Done]`
  - **11. [Resignation Application / Đơn nghỉ việc](/desk/resignation-application)** `[Custom]` `[Done]` — Ngày nộp đơn, ngày nghỉ chính thức, số ngày báo trước, lý do nghỉ và danh sách bàn giao: thẻ, đồng phục, kệ giày, vân tay, công cụ, công việc
  - **12. [Employee reports / Báo cáo nhân sự](/desk/dashboard-view/HR%20Overview)** `[Override]` `[Done]` — Headount, hiện diện, vắng, tăng ca, tuyển mới, nghỉ việc, cơ cấu theo độ tuổi, giới tính, cấp bậc
- **02. Time & Attendance / Chấm công** `[Done]`
  - **01. Shift setup / Thiết lập ca làm việc** `[Done]`
    - **01. [Shift type / Khai báo ca](/desk/shift-type)** `[Override]` `[Done]` — Giờ vào, giờ ra, giờ nghỉ trưa, mức dung sai trễ - về sớm
    - **02. [Assign shift / Phân ca](/desk/shift-assignment)** `[Standard]` `[Done]` — Phân ca cho nhân viên theo khoảng thời gian
    - **03. [Bulk shift assignment / Phân ca hàng loạt](/desk/shift-assignment-tool)** `[Custom]` `[Done]` — Chọn nhiều nhân viên và phân ca cùng lúc thay vì làm từng người
    - **04. [Shift priority / Thứ tự xác định ca](/desk/shift-type)** `[Override]` `[Done]` — Ưu tiên phân ca riêng, sau đó ca mặc định của nhân viên, cuối cùng theo ca ngày
  - **02. [Fingerprint machines / Máy chấm công vân tay](/desk/attendance-machine-setting)** `[Custom]` `[Done]`
    - **01. [Connect machines / Kết nối máy](/desk/attendance-machine-setting)** `[Custom]` `[Done]` — IT - Khai báo máy chấm công, lấy dữ liệu quét về hệ thống tự động
    - **02. [Register fingerprints / Đăng ký vân tay](/desk/fingerprint-data)** `[Custom]` `[Done]` — Đăng ký vân tay chấm công cho nhân viên
    - **03. [Push employees to machines / Đưa nhân viên xuống máy](/biometric_sync)** `[Custom]` `[Done]` — Đồng bộ danh sách nhân viên và vân tay xuống từng máy
    - **04. [Sync machine clock / Đồng bộ giờ máy](/biometric_sync)** `[Custom]` `[Done]` — IT
    - **05. [Check scan data / Kiểm tra dữ liệu quét](/biometric_sync)** `[Custom]` `[Done]` — IT- Kiểm tra log, xữ lý khi có lỗi
  - **03. [Check-in records / Dữ liệu quét vào - ra](/desk/employee-checkin)** `[Override]` `[Done]` — Mỗi lần nhân viên quét là một dòng dữ liệu, là cơ sở để tính công
  - **04. [Attendance calculation / Tính công tự động](/desk/attendance)** `[Override]` `[Done]`
    - **01. [Automatic daily run / Chạy tự động hằng ngày]()** `[Override]` `[Done]` — 
    - **02. [Attendance status / Trạng thái ngày công](/desk/attendance/view/list)** `[Standard]` `[Done]` — Có mặt, vắng, nửa ngày, ngày nghỉ, ngày lễ
    - **03. [Late & early leave / Trễ giờ & về sớm](/desk/attendance/view/list)** `[Standard]` `[Done]` — Ghi nhận vào trễ, ra sớm theo cài đặt của ca
    - **04. [Leave-linked days / Ngày công theo đơn phép](/desk/attendance)** `[Override]` `[Done]` — Ngày đã có đơn phép hoặc ngày lễ được khớp tự động, không tính vắng
   
    - **05. [Anomaly note / Ghi chú bất thường]()** `[Custom]` `[Done]` — Quét thiếu, tăng ca nhưng không có đáng ký, thai sản,... được ghi chú lại để HR kiểm tra và xử lý tay
<!-- 
 - **05. [Paid holidays / Ngày lễ vẫn tính công](/desk/holiday-list)** `[Override]` `[Done]` — Ngày lễ nhà nước là nghỉ có lương nên vẫn được tính vào ngày công
-->
  - **05. [Corrections / Điều chỉnh công]()** `[Override]` `[Done]` — Điều chỉnh, bổ sung giờ checkin
    - **01. [Attendance confirmation request / Yêu cầu xác nhận công](/desk/attendance-request)** `[Override]` `[Done]` — Phiếu đề nghị bổ sung công; khi duyệt hệ thống tự tạo giờ chấm công và tính lại ngày công đó
    - **02. [Suggested times / Đề xuất giờ tự động](/desk/attendance-request)** `[Custom]` `[Done]` — Hệ thống đề xuất giờ đầu ca, cuối ca, hoặc giờ kết thúc tăng ca đã đăng ký; HR vẫn sửa tay được từng dòng
    - **03. [Bulk create / Tạo phiếu hàng loạt](/desk/attendance-request/view/list)** `[Custom]` `[Done]` — Quét một khoảng ngày, liệt kê những người quét thiếu, tạo một phiếu nháp cho mỗi nhân viên chỉ trong một bước
    - **04. [Signature form / Giấy xác nhận công để ký](/desk/attendance-request/view/list)** `[Custom]` `[Done]` — In giấy yêu cầu xác nhận công gom theo tổ, mỗi tổ một tờ A4; bản scan đã ký được đính kèm ngược lại vào phiếu
  - **06. Attendance reports / Báo cáo chấm công** `[Done]`
    - **01. [Monthly attendance sheet / Bảng công tháng](/desk/query-report/Shift%20Attendance%20Customize)** `[Custom]` `[Done]` — Bảng công chi tiết theo ca, dùng để đối chiếu và tính lương
    - **02. [Daily email report / Báo cáo gửi email hằng ngày]()** `[Custom]` `[Done]` — Hệ thống tự gửi báo cáo: Headcount/ hiện diện/ vắng/ đăng ký tăng ca của hôm nay, các trường hợp chấm công thiếu của ngày hôm trước
    - **03. [Excel export / Xuất Excel](/desk/query-report/Shift%20Attendance%20Customize)** `[Custom]` `[Done]` — Bản Excel có cấu trúc giống app chấm công hiên tại
 
- **03. [Overtime / Tăng ca](/desk/overtime-registration)** `[Custom]` `[Done]`
 <!--
  - **01. [Overtime levels / Bậc tăng ca](/desk/overtime-level)** `[Custom]` `[Done]` — Hệ số tăng ca cho ngày thường, chủ nhật và ngày lễ
  -->
  - **01. [Register overtime / Đăng ký tăng ca](/desk/overtime-registration)** `[Custom]` `[Done]` — Chọn ngày, chọn nhân viên, khai giờ bắt đầu và giờ kết thúc tăng ca
  - **02. [Employee picker / Chọn nhân viên](/desk/overtime-registration/new)** `[Custom]` `[Done]` — Lọc theo bộ phận và nhóm, thấy ngay tổng giờ công khi chọn thêm người
  - **03. [Request & approval / Yêu cầu & phê duyệt](/desk/overtime-request)** `[Custom]` `[Done]` — Bộ phận đề xuất, cấp trên phê duyệt trước khi tính công - Chưa áp dụng
  - **04. Overtime reports / Báo cáo tăng ca** `[Done]`
    - **01. [By registration / Theo phiếu đăng ký](/desk/query-report/Overtime%20Registration)** `[Custom]` `[Done]` — Danh sách phiếu tăng ca và số giờ theo từng phiếu
    - **02. [By time slot / Theo khung giờ](/desk/query-report/Overtime%20Registration%20by%20Time%20Slot)** `[Custom]` `[Done]` — Số người và số giờ tăng ca theo từng khung giờ trong ngày
    - **03. [By quantity / Theo số lượng](/desk/query-report/Overtime%20Registration%20Quantity)** `[Custom]` `[Done]` — Tổng hợp số giờ tăng ca theo bộ phận và theo kỳ
    - **04. [Compliance check / Kiểm tra tuân thủ](/desk/query-report/OT%20Compliance)** `[Custom]` `[Done]` — Cảnh báo khi vượt giới hạn giờ tăng ca theo quy định của luật
- **04. Leave / Nghỉ phép** `[Done]`
  - **01. [Leave types / Loại phép](/desk/leave-type)** `[Standard]` `[Done]` — Phép năm, nghỉ không lương, nghỉ ốm, thai sản, nghỉ bù
  - **02. [Holiday list / Lịch nghỉ lễ](/desk/holiday-list)** `[Standard]` `[Done]` — Danh sách ngày lễ và ngày nghỉ bù áp dụng cho từng năm
  - **03. [Leave balance / Số dư phép](/desk/leave-allocation)** `[Override]` `[Done]` — Phân bổ phép đầu kỳ và phép tích lũy theo từng tháng làm việc
  - **04. [Leave application / Đơn xin nghỉ phép](/desk/leave-application)** `[Override]` `[Done]` — Nhân viên tạo đơn, người quản lý phê duyệt, công được cập nhật theo đơn
  - **05. [Half day leave / Nghỉ nửa ngày](/desk/leave-application)** `[Override]` `[Done]` — Nghỉ nửa ngày phép vẫn được tính đủ công cho ngày đó
  - **06. [Compensatory & encashment / Nghỉ bù & thanh toán phép](/desk/compensatory-leave-request)** `[Standard]` `[Pending]` — Nghỉ bù cho ngày làm thêm và thanh toán phép chưa dùng
  - **07. [Leave reports / Báo cáo phép](/desk/query-report/Employee%20Leave%20Balance)** `[Standard]` `[Done]` — Số dư phép từng nhân viên và lịch sử nghỉ theo kỳ
- **05. Payroll / Tiền lương** `[Done]`
  - **01. [Payroll settings / Cấu hình lương](/desk/tiqn-payroll-settings)** `[Custom]` `[Pending: 50]` — Tỷ lệ bảo hiểm, bậc thuế, mức giảm trừ, cập nhật khi quy định thay đổi
  - **02. [Salary structure / Cơ cấu lương](/desk/salary-structure)** `[Standard]` `[In process 30%]` — Lương cơ bản, các khoản phụ cấp và các khoản trừ
  - **03. [Salary assignment / Gán lương cho nhân viên](/desk/salary-structure-assignment)** `[Override]` `[In process 30%]` — Gán mức lương theo ngày hiệu lực, có thể nhập hàng loạt từ Excel
  - **04. [Standard working days / Ngày công chuẩn](/desk/salary-slip)** `[Override]` `[In process 30%]` — Số ngày trong kỳ trừ các ngày chủ nhật, ngày lễ vẫn được tính công
  - **05. [Vietnam statutory deductions / Khấu trừ theo luật Việt Nam](/desk/tiqn-payroll-settings)** `[Override]` `[Done]`
    - **01. [Insurance / Bảo hiểm](/desk/tiqn-insurance-rate)** `[Override]` `[In process 30%]` — Bảo hiểm xã hội, bảo hiểm y tế và bảo hiểm thất nghiệp
    - **02. [Union fee / Đoàn phí](/desk/tiqn-payroll-settings)** `[Override]` `[In process 30%]` — Trừ đoàn phí công đoàn theo tỷ lệ quy định
    - **03. [Personal income tax / Thuế thu nhập cá nhân](/desk/tiqn-tax-bracket)** `[Override]` `[In process 30%]` — Tính theo bậc thuế, có giảm trừ bản thân và người phụ thuộc
  - **06. [Payroll run / Chạy bảng lương](/desk/payroll-entry)** `[Standard]` `[In process 30%]` — Chạy theo kỳ lương, sinh phiếu lương cho toàn bộ nhân viên
  - **07. [Payslip / Phiếu lương](/desk/salary-slip)** `[Override]` `[In process 30%]` — Xem và in phiếu lương, số tiền được ghi bằng chữ tiếng Việt
<!--  
- **08. [Loans & advances / Khoản vay & tạm ứng](/desk/employee-advance)** `[Standard]` `[Done]` — Theo dõi khoản vay và tạm ứng, trừ dần vào lương hằng kỳ
-->
  - **08. [Payroll reports / Báo cáo lương](/desk/query-report/Salary%20Register)** `[Standard]` `[Pending]` — Bảng lương tổng hợp, danh sách chi trả qua ngân hàng, tổng hợp thuế
- **06. Other HR functions / Chức năng HR khác** `[Pending]` — Phần lớn đang dùng theo bản chuẩn, chưa điều chỉnh riêng cho công ty
  - **01. [Recruitment / Tuyển dụng](/desk/job-opening)** `[Standard]` `[Pending]` — Nhu cầu tuyển, tin tuyển dụng, ứng viên, phỏng vấn, thư mời nhận việc
  - **02. [Online job application / Ứng tuyển trực tuyến](/jobs)** `[Custom]` `[Pending]` — Mẫu ứng tuyển trên web, ứng viên tự điền và gửi hồ sơ
  - **03. [Performance appraisal / Đánh giá hiệu suất](/desk/appraisal)** `[Standard]` `[Pending]` — Kỳ đánh giá, mục tiêu, tiêu chí đánh giá và phản hồi
  - **04. [Training / Đào tạo](/desk/training-program)** `[Standard]` `[Pending]` — Chương trình đào tạo, buổi đào tạo, kết quả và phản hồi của người học
  - **05. [Expense claim & travel / Hoàn ứng & công tác](/desk/expense-claim)** `[Standard]` `[Pending]` — Đề nghị thanh toán chi phí, tạm ứng và yêu cầu đi công tác
- **07. System & Access / Hệ thống & phân quyền** `[Done]`
  - **01. [Roles & permissions / Vai trò & phân quyền](/desk/role)** `[Standard]` `[In process 50%]` — Phân quyền theo vai trò để mỗi người chỉ thấy dữ liệu thuộc phạm vi của mình
  - **02. [Menu & shortcuts / Menu & lối tắt](/desk/workspace)** `[Custom]` `[Done]` — Nhóm chức năng theo khu vực làm việc và tạo lối tắt trên trang chủ
  - **03. [Vietnamese interface / Giao diện tiếng Việt](/desk/user)** `[Custom]` `[Done]` — Mỗi người dùng chọn ngôn ngữ hiển thị riêng
  - **04. [Excel & CSV export / Xuất Excel & CSV](/desk/data-export)** `[Override]` `[Done]` — Tải dữ liệu ra file, mở lên hiển thị đúng dấu tiếng Việt
 
