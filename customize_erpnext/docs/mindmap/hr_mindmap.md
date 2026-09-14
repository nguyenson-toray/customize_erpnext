<!-- HR Mindmap - Quản lý Nhân sự — Sơ đồ chức năng phần Nhân sự, dùng để giới thiệu và hướng dẫn người dùng -->
<!-- Tạo bằng build_mindmap.py. Nội dung và phân loại sửa trong script rồi chạy lại. -->
<!-- Nhãn tiến độ SỬA TRỰC TIẾP trong file này được, build lại vẫn giữ nguyên: [Done] | [In process 60%] | [Pending: lý do chưa làm] -->
<!-- Xem sơ đồ trên hệ thống: /mindmap?file=hr_mindmap.md -->
<!-- Hoặc dán toàn bộ file vào https://markmap.js.org/repl -->

# HR - Human Resources / Quản lý Nhân sự

> Hồ sơ nhân viên, chấm công, tăng ca, nghỉ phép và tiền lương [Guide](/lms/courses/module-hrms)

- **01. Employee Records / Hồ sơ nhân viên** `[Done]` — Dữ liệu gốc về con người: cơ cấu tổ chức, hồ sơ và giấy tờ của từng nhân viên, cùng các mốc vòng đời từ tiếp nhận, điều chuyển đến nghỉ việc
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
    - **01. [Employee Transfer / Điều chuyển](/desk/employee-transfer)** `[Override]` `[Done]`
    - **02. [Employee Promotion / Thăng chức](/desk/employee-promotion)** `[Override]` `[Done]`
    - **03. [Employee Transfer & Promotion Report / Báo cáo điều chuyển & thăng chức](/desk/query-report/Employee%20Transfer%20and%20Promotion)** `[Custom]` `[Done]`
  - **11. [Resignation Application / Đơn nghỉ việc](/desk/resignation-application)** `[Custom]` `[Done]` — Ngày nộp đơn, ngày nghỉ chính thức, số ngày báo trước, lý do nghỉ và danh sách bàn giao: thẻ, đồng phục, kệ giày, vân tay, công cụ, công việc
  - **12. [Employee reports / Báo cáo nhân sự](/desk/dashboard-view/HR%20Overview)** `[Override]` `[Done]` — Headount, hiện diện, vắng, tăng ca, tuyển mới, nghỉ việc, cơ cấu theo độ tuổi, giới tính, cấp bậc
- **02. Time & Attendance / Chấm công** `[Done]` — Từ khai ca và máy chấm công tới dữ liệu quét vào ra, tính công tự động hằng ngày, điều chỉnh khi sai sót và báo cáo đối chiếu
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
 
- **03. [Overtime / Tăng ca](/desk/overtime-registration)** `[Custom]` `[Done]` — Đăng ký giờ tăng ca theo ngày và theo nhân viên, phê duyệt, tổng hợp báo cáo và kiểm tra giới hạn giờ theo quy định của luật
 <!--
  - **01. [Overtime levels / Bậc tăng ca](/desk/overtime-level)** `[Custom]` `[Done]` — Hệ số tăng ca cho ngày thường, chủ nhật và ngày lễ
  -->
  - **01. [Register overtime / Đăng ký tăng ca](/desk/overtime-registration)** `[Custom]` `[Done]` — Chọn ngày, chọn nhân viên, khai giờ bắt đầu và giờ kết thúc tăng ca; nút Get Employees lọc theo bộ phận và nhóm, thấy ngay tổng giờ công khi chọn thêm người
  - **02. [Request & approval / Yêu cầu & phê duyệt](/desk/overtime-request)** `[Custom]` `[Done]` — Bộ phận đề xuất, cấp trên phê duyệt trước khi tính công - Chưa áp dụng
  - **03. Overtime reports / Báo cáo tăng ca** `[Done]`
    - **01. [By registration / Theo phiếu đăng ký](/desk/query-report/Overtime%20Registration)** `[Custom]` `[Done]` — Danh sách phiếu tăng ca và số giờ theo từng phiếu
    - **02. [By time slot / Theo khung giờ](/desk/query-report/Overtime%20Registration%20by%20Time%20Slot)** `[Custom]` `[Done]` — Số người và số giờ tăng ca theo từng khung giờ trong ngày
    - **03. [By quantity / Theo số lượng](/desk/query-report/Overtime%20Registration%20Quantity)** `[Custom]` `[Done]` — Tổng hợp số giờ tăng ca theo bộ phận và theo kỳ
    - **04. [Compliance check / Kiểm tra tuân thủ](/desk/query-report/OT%20Compliance)** `[Custom]` `[Done]` — Cảnh báo khi vượt giới hạn giờ tăng ca theo quy định của luật
- **04. Leave / Nghỉ phép** `[Done]` — Khai loại phép và lịch nghỉ lễ, phân bổ số dư phép, nhân viên nộp đơn và quản lý duyệt, kết quả cập nhật thẳng vào bảng công
  - **01. [Leave types / Loại phép](/desk/leave-type)** `[Standard]` `[Done]` — Phép năm, nghỉ không lương, nghỉ ốm, thai sản, nghỉ bù
  - **02. [Holiday list / Lịch nghỉ lễ](/desk/holiday-list)** `[Standard]` `[Done]` — Danh sách ngày lễ và ngày nghỉ bù áp dụng cho từng năm
  - **03. [Leave balance / Số dư phép](/desk/leave-allocation)** `[Override]` `[Done]` — Phân bổ phép đầu kỳ và phép tích lũy theo từng tháng làm việc
  - **04. [Leave application / Đơn xin nghỉ phép](/desk/leave-application)** `[Override]` `[Done]` — Nhân viên tạo đơn, người quản lý phê duyệt, công được cập nhật theo đơn
  - **05. [Half day leave / Nghỉ nửa ngày](/desk/leave-application)** `[Override]` `[Done]` — Nghỉ nửa ngày phép vẫn được tính đủ công cho ngày đó
  - **06. [Compensatory & encashment / Nghỉ bù & thanh toán phép](/desk/compensatory-leave-request)** `[Standard]` `[Pending]` — Nghỉ bù cho ngày làm thêm và thanh toán phép chưa dùng
  - **07. [Leave reports / Báo cáo phép](/desk/query-report/Employee%20Leave%20Balance)** `[Standard]` `[Done]` — Số dư phép từng nhân viên và lịch sử nghỉ theo kỳ
- **05. Payroll / Tiền lương** `[In process 50%]` — Cấu hình tỷ lệ bảo hiểm và thuế, gán cơ cấu lương cho nhân viên, chạy bảng lương theo kỳ rồi phát phiếu lương và báo cáo chi trả
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
- **06. Recruitment / Tuyển dụng** `[Pending]` — Quy trình xuyên suốt: hoạch định nhu cầu, đăng tin, tiếp nhận và phỏng vấn ứng viên, đến khi ứng viên trở thành nhân viên chính thức
  - **01. [Staffing Plan / Kế hoạch nhân sự](/desk/staffing-plan)** `[Standard]` `[Pending]` — Hoạch định số lượng và ngân sách tuyển dụng cho một khoảng thời gian; số tin tuyển của mỗi chức danh bị giới hạn bởi số vị trí trống trong kế hoạch. Bước tùy chọn
    - **01. [Check Vacancies On Job Offer Creation / Ràng buộc chỉ tiêu](/desk/hr-settings)** `[Standard]` `[Pending]` — Phải tích mục này trong HR Settings thì việc kiểm soát chỉ tiêu mới có hiệu lực
  - **02. [Job Requisition / Yêu cầu tuyển dụng](/desk/job-requisition)** `[Standard]` `[Pending]` — Đề xuất tuyển nhân sự trong nội bộ, có thể kèm phê duyệt; hệ thống tự tính Time to Fill từ lúc yêu cầu tới khi tuyển xong. Bước tùy chọn
  - **03. [Job Opening / Vị trí tuyển dụng](/desk/job-opening)** `[Standard]` `[Pending]` — Vị trí còn trống, bắt buộc phải có thì mới tạo được hồ sơ ứng viên; đóng vị trí là chặn nộp thêm, và yêu cầu tuyển dụng liên quan tự chuyển sang Filled
  - **04. [Job Portal / Cổng tuyển dụng](/jobs)** `[Custom]` `[Pending]` — Trang /jobs để ứng viên tự tìm và nộp đơn, nộp xong hệ thống tự tạo hồ sơ ứng viên; phải tích Publish on website ở vị trí tuyển dụng thì tin mới hiện ra
  - **05. [Job Applicant / Hồ sơ ứng viên](/desk/job-applicant)** `[Standard]` `[Pending]` — Tài liệu trung tâm của tuyển dụng: hồ sơ, nguồn ứng viên, lịch sử phỏng vấn và đánh giá; tạo tay, từ cổng tuyển dụng, từ giới thiệu nội bộ hoặc tạo nhanh từ vị trí tuyển dụng
    - **01. [Employee Referral / Giới thiệu nội bộ](/desk/employee-referral)** `[Standard]` `[Pending]` — Nhân viên giới thiệu ứng viên; khi ứng viên được nhận hoặc bị loại thì trạng thái bản ghi giới thiệu tự cập nhật theo
    - **02. Applicant status / Trạng thái ứng viên** `[Standard]` `[Pending]` — Open, Replied, Rejected, Hold, Accepted; phỏng vấn đạt KHÔNG tự đổi trạng thái ứng viên, HR phải xem tổng hợp rồi cập nhật tay
  - **06. [Interview / Phỏng vấn](/desk/interview)** `[Standard]` `[Pending]` — Lên lịch phỏng vấn theo từng vòng và ghi nhận đánh giá của người phỏng vấn
    - **01. [Interview Round / Vòng phỏng vấn](/desk/interview-round)** `[Standard]` `[Pending]` — Khai các vòng và người phỏng vấn của từng vòng; bắt buộc có trước khi lên lịch được
    - **02. [Interview Type / Hình thức phỏng vấn](/desk/interview-type)** `[Standard]` `[Pending]` — Phân loại hình thức: hội đồng, trực tiếp… Tùy chọn
    - **03. [Interview Feedback / Đánh giá phỏng vấn](/desk/interview-feedback)** `[Standard]` `[Pending]` — Chỉ người được gắn vào vòng phỏng vấn mới gửi được đánh giá; hệ thống tổng hợp điểm kỹ năng và nhận xét theo từng ứng viên
    - **04. Calendar & reminder / Lịch & nhắc lịch** `[Standard]` `[Pending]` — Xem các buổi phỏng vấn dạng lịch và tự gửi email nhắc lịch cho người phỏng vấn
  - **07. [Job Offer / Thư mời nhận việc](/desk/job-offer)** `[Standard]` `[Pending]` — Thư mời chính thức, bắt buộc tạo từ một hồ sơ ứng viên: mô tả công việc, thời gian báo trước khi nghỉ, thưởng, số ngày phép năm
  - **08. [Appointment Letter / Thư bổ nhiệm](/desk/appointment-letter)** `[Standard]` `[Pending]` — Văn bản chính thức mời ứng viên gia nhập công ty; soạn theo mẫu có sẵn rồi in PDF gửi ứng viên
  - **09. [Employee Onboarding / Tiếp nhận nhân viên mới](/desk/employee-onboarding)** `[Standard]` `[Pending]` — Bước cuối của tuyển dụng: kế thừa dữ liệu ứng viên để tạo hồ sơ nhân viên chính thức, chi tiết xem nhánh Hồ sơ nhân viên

- **07. Other HR functions / Chức năng HR khác** `[Pending]` — Phần lớn đang dùng theo bản chuẩn, chưa điều chỉnh riêng cho công ty
  - **01. [Performance appraisal / Đánh giá hiệu suất](/desk/appraisal)** `[Standard]` `[Pending]` — Kỳ đánh giá, mục tiêu, tiêu chí đánh giá và phản hồi
  - **02. [Training / Đào tạo](/desk/training-program)** `[Standard]` `[Pending]` — Chương trình đào tạo, buổi đào tạo, kết quả và phản hồi của người học
  - **03. [Expense claim & travel / Hoàn ứng & công tác](/desk/expense-claim)** `[Standard]` `[Pending]` — Đề nghị thanh toán chi phí, tạm ứng và yêu cầu đi công tác
