#!/usr/bin/env python3
"""Nguồn duy nhất cho 2 sơ đồ tư duy hướng dẫn người dùng.

Emits:
  hr_mindmap.md          - nhánh HR / Nhân sự
  ga_mindmap.md          - nhánh GA / Hành chính tổng hợp
  ../www/mindmap/vi.csv  - bảng dịch phần MÔ TẢ cho trang /mindmap (english,vietnamese)

Chạy với --json để xuất thêm hr_mindmap.json / ga_mindmap.json.

Mô tả song ngữ:
  Tham số desc nhận chuỗi (chỉ tiếng Việt) hoặc tuple ("English", "Tiếng Việt").
  File .md luôn ghi bản tiếng Việt; bản tiếng Anh đi vào vi.csv để trang /mindmap
  đổi qua lại được. Tiêu đề thì đã song ngữ sẵn nên không cần dịch.

Nhãn trên mỗi mục:
  Phân loại  `[Standard]`  chức năng chuẩn của hệ thống, dùng nguyên bản
             `[Override]`  chức năng chuẩn đã được sửa cho phù hợp công ty
             `[Custom]`    chức năng tự phát triển thêm
  Tiến độ    `[Done]` | `[In process 60%]` | `[Pending: lý do chưa làm]`

GIỮ PHẦN SỬA TAY: build lại sẽ đọc file .md cũ và giữ nguyên những gì đã sửa tay
trong đó — nhãn tiến độ (kèm % hoặc lý do), MÔ TẢ, LINK và SỐ THỨ TỰ ở đầu tiêu đề.
Cấu trúc cây và nhãn phân loại thì luôn lấy theo script này. Vì vậy sửa trong .md
hay sửa trên trang /mindmap rồi build lại đều không mất.
  --from-script  bỏ phần sửa tay, lấy lại mô tả và link đúng theo script.
Mục bị xoá hoặc bị comment lại trong .md sẽ được thêm lại và script in cảnh báo;
muốn bỏ hẳn thì xoá trong script này.

SỐ THỨ TỰ: có thể tự đánh số ở đầu tiêu đề trong .md, ví dụ
"01. Employee Records / Hồ sơ nhân viên". Trang /mindmap sắp nhánh theo số đó;
mục không có số thì giữ thứ tự như trong file.

Nguyên tắc nội dung:
  - Tiêu đề song ngữ "English / Tiếng Việt" ở mọi mục.
  - Viết cho NGƯỜI DÙNG: nói chức năng làm được gì, không nói tên file,
    tên DocType kỹ thuật, tên hàm hay đường dẫn code.
  - Mô tả ngắn sau dấu "—", đủ để hiểu ngay, không quá một dòng.
"""

import argparse
import csv
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
# 19/08/2026 dọn 01_docs: file .md sang docs/mindmap (trang /dev-tool đọc ở đó),
# script sinh sang scripts/. Hai đường dẫn dưới đây tính từ scripts/.
OUT = os.path.realpath(os.path.join(HERE, "..", "docs", "mindmap"))
LANG_CSV = os.path.realpath(os.path.join(HERE, "..", "www", "mindmap", "vi.csv"))
# Ghi lại những mục đã từng xuất ra .md, để biết mục nào bị xoá có chủ ý.
# Là file trạng thái của script, giữ cạnh script — docs/mindmap chỉ chứa .md.
STATE_FILE = os.path.join(HERE, "mindmap_state.json")

STATUSES = ("Done", "In process", "Pending")
TYPES = ("Standard", "Override", "Custom")


def n(en, vi, desc=None, children=None, tag=None, status="Done"):
    d = {"en": en, "vi": vi, "label": f"{en} / {vi}"}
    if desc:
        desc_en, desc_vi = (desc, desc) if isinstance(desc, str) else desc
        d["desc"] = desc_vi
        d["desc_en"] = desc_en
    if tag:
        d["type"] = tag
    if status:
        d["status"] = status
    if children:
        d["children"] = children
    return d


def g(en, vi, desc=None, children=None, status="Done"):
    """Mục gom nhóm - gồm nhiều loại khác nhau nên không gắn nhãn phân loại."""
    return n(en, vi, desc, children, tag=None, status=status)


# ============================================================ HR / NHÂN SỰ
HR = n("HR - Human Resources", "Quản lý Nhân sự",
       ("Employee records, attendance, overtime, leave and payroll",
        "Hồ sơ nhân viên, chấm công, tăng ca, nghỉ phép và tiền lương"),
       status=None, children=[
    g("Employee Records", "Hồ sơ nhân viên",
      ("Core people data: organisation structure, each employee's profile and documents, and"
       " the lifecycle milestones from onboarding and transfer to resignation",
       "Dữ liệu gốc về con người: cơ cấu tổ chức, hồ sơ và giấy tờ của từng nhân viên, cùng các"
       " mốc vòng đời từ tiếp nhận, điều chuyển đến nghỉ việc"),
      children=[
        n("Organization structure", "Cơ cấu tổ chức",
          ("Company, department, designation and grade",
           "Công ty, phòng ban, chức danh, cấp bậc"),
          tag="Standard",
          children=[
            n("Section & Group", "Bộ phận & Nhóm",
              ("Splits a department into sections and groups for finer attendance and reporting",
               "Chia nhỏ phòng ban thành bộ phận và nhóm để chấm công, báo cáo chi tiết hơn"),
              tag="Custom",
            ),
          ],
        ),
        n("Employment Type", "Loại hình lao động",
          ("Employment types such as permanent, seasonal and probation, with tracking of"
           " probation end dates",
           "Loại hình lao động: chính thức, thời vụ, thử việc; theo dõi ngày kết thúc thử việc"),
          tag="Standard",
        ),
        n("Employee profile", "Thông tin nhân viên",
          ("Personal details, department, designation, joining date, employment status and so"
           " on",
           "Thông tin cá nhân, phòng ban, chức danh, ngày vào làm, trạng thái làm việc..."),
          tag="Override",
        ),
        n("Employee photo", "Ảnh nhân viên",
          ("Upload photos, remove the background, crop to ID-photo ratio and process many at"
           " once. The image is reused by the employee ID card feature",
           "Tải ảnh, xóa nền, cắt ảnh thẻ đúng tỷ lệ, xử lý nhiều ảnh một lượt. File ảnh được"
           " sử dụng cho chức năng tạo thẻ Nv"),
          tag="Custom",
        ),
        n("Self-service update", "Nhân viên tự cập nhật thông tin",
          ("Employees submit their own details on a dedicated page, HR reviews then applies"
           " them",
           "Nhân viên tự khai thông tin qua trang riêng, HR kiểm tra rồi cập nhật vào hồ sơ"),
          tag="Custom",
        ),
        n("Dependents", "Người phụ thuộc",
          ("Declare dependents used for personal income tax relief",
           "Khai người phụ thuộc để tính giảm trừ thuế thu nhập cá nhân"),
          tag="Custom",
        ),
        n("Labor contract", "Hợp đồng lao động",
          ("Contract type, duration and tracking of contracts due for renewal",
           "Loại hợp đồng, thời hạn, theo dõi hợp đồng sắp hết hạn cần tái ký"),
          tag="Custom",
        ),
        n("Maternity records", "Thai sản",
          ("Tracks the maternity milestones of each employee, used for attendance, leave and"
           " benefit calculation",
           "Theo dõi các mốc thời gian liên quan thai sản của nhân viên, dùng để tính toán công"
           " phép, chế độ"),
          tag="Custom",
        ),
        n("Onboarding", "Tiếp nhận",
          ("Steps for taking on a new employee: checklist, handover and paperwork",
           "Thủ tục tiếp nhận nhân viên mới: danh sách việc cần làm, bàn giao, hoàn tất hồ sơ"),
          tag="Standard",
        ),
        n("Transfer & promotion", "Điều chuyển & thăng chức",
          ("Move between departments, change designation, promote, and keep the history of"
           " changes",
           "Chuyển bộ phận, đổi chức danh, thăng chức và lưu lại lịch sử thay đổi"),
          tag="Standard",
          children=[
            n("Employee Transfer", "Điều chuyển",
              None,
              tag="Override",
            ),
            n("Employee Promotion", "Thăng chức",
              None,
              tag="Override",
            ),
            n("Employee Transfer & Promotion Report", "Báo cáo điều chuyển & thăng chức",
              None,
              tag="Custom",
            ),
          ],
        ),
        n("Resignation Application", "Đơn nghỉ việc",
          ("Resignation letter date, relieving date, notice days, reason for leaving, plus the"
           " handover checklist: ID card, uniform, shoe rack, fingerprint, tools and work",
           "Ngày nộp đơn, ngày nghỉ chính thức, số ngày báo trước, lý do nghỉ và danh sách bàn"
           " giao: thẻ, đồng phục, kệ giày, vân tay, công cụ, công việc"),
          tag="Custom",
        ),
        n("Employee reports", "Báo cáo nhân sự",
          ("Headcount, presence, absence, overtime, new hires, resignations, and structure by"
           " age, gender and grade",
           "Headount, hiện diện, vắng, tăng ca, tuyển mới, nghỉ việc, cơ cấu theo độ tuổi, giới"
           " tính, cấp bậc"),
          tag="Override",
        ),
      ],
    ),
    g("Time & Attendance", "Chấm công",
      ("From shift setup and time clocks through raw scans, automatic daily attendance"
       " calculation, corrections and reconciliation reports",
       "Từ khai ca và máy chấm công tới dữ liệu quét vào ra, tính công tự động hằng ngày, điều"
       " chỉnh khi sai sót và báo cáo đối chiếu"),
      children=[
        g("Shift setup", "Thiết lập ca làm việc",
          None,
          children=[
            n("Shift type", "Khai báo ca",
              ("Start time, end time, lunch break and the allowed late / early margin",
               "Giờ vào, giờ ra, giờ nghỉ trưa, mức dung sai trễ - về sớm"),
              tag="Override",
            ),
            n("Assign shift", "Phân ca",
              ("Assign a shift to an employee for a date range",
               "Phân ca cho nhân viên theo khoảng thời gian"),
              tag="Standard",
            ),
            n("Bulk shift assignment", "Phân ca hàng loạt",
              ("Pick many employees and assign the shift in one go instead of one by one",
               "Chọn nhiều nhân viên và phân ca cùng lúc thay vì làm từng người"),
              tag="Custom",
            ),
            n("Shift priority", "Thứ tự xác định ca",
              ("Specific shift assignment first, then the employee's default shift, and finally"
               " the shift of the day",
               "Ưu tiên phân ca riêng, sau đó ca mặc định của nhân viên, cuối cùng theo ca ngày"),
              tag="Override",
            ),
          ],
        ),
        n("Fingerprint machines", "Máy chấm công vân tay",
          None,
          tag="Custom",
          children=[
            n("Connect machines", "Kết nối máy",
              ("IT - register the time clocks and pull scan data into the system automatically",
               "IT - Khai báo máy chấm công, lấy dữ liệu quét về hệ thống tự động"),
              tag="Custom",
            ),
            n("Register fingerprints", "Đăng ký vân tay",
              ("Enroll attendance fingerprints for employees",
               "Đăng ký vân tay chấm công cho nhân viên"),
              tag="Custom",
            ),
            n("Push employees to machines", "Đưa nhân viên xuống máy",
              ("Sync the employee list and fingerprints down to each device",
               "Đồng bộ danh sách nhân viên và vân tay xuống từng máy"),
              tag="Custom",
            ),
            n("Sync machine clock", "Đồng bộ giờ máy",
              ("IT",
               "IT"),
              tag="Custom",
            ),
            n("Check scan data", "Kiểm tra dữ liệu quét",
              ("IT - review the scan logs and handle errors",
               "IT- Kiểm tra log, xữ lý khi có lỗi"),
              tag="Custom",
            ),
          ],
        ),
        n("Check-in records", "Dữ liệu quét vào - ra",
          ("Every scan is one record and is the basis for calculating attendance",
           "Mỗi lần nhân viên quét là một dòng dữ liệu, là cơ sở để tính công"),
          tag="Override",
        ),
        n("Attendance calculation", "Tính công tự động",
          None,
          tag="Override",
          children=[
            n("Automatic daily run", "Chạy tự động hằng ngày",
              None,
              tag="Override",
            ),
            n("Attendance status", "Trạng thái ngày công",
              ("Present, absent, half day, day off and public holiday",
               "Có mặt, vắng, nửa ngày, ngày nghỉ, ngày lễ"),
              tag="Standard",
            ),
            n("Late & early leave", "Trễ giờ & về sớm",
              ("Records late arrival and early departure against the shift settings",
               "Ghi nhận vào trễ, ra sớm theo cài đặt của ca"),
              tag="Standard",
            ),
            n("Leave-linked days", "Ngày công theo đơn phép",
              ("Days with an approved leave or a holiday are matched automatically, never"
               " marked absent",
               "Ngày đã có đơn phép hoặc ngày lễ được khớp tự động, không tính vắng"),
              tag="Override",
            ),
            n("Anomaly note", "Ghi chú bất thường",
              ("Missing scans, unregistered overtime, maternity cases and the like are noted"
               " for HR to check and fix by hand",
               "Quét thiếu, tăng ca nhưng không có đáng ký, thai sản,... được ghi chú lại để HR"
               " kiểm tra và xử lý tay"),
              tag="Custom",
            ),
          ],
        ),
        n("Corrections", "Điều chỉnh công",
          ("Adjust or add check-in times",
           "Điều chỉnh, bổ sung giờ checkin"),
          tag="Override",
          children=[
            n("Attendance confirmation request", "Yêu cầu xác nhận công",
              ("A request to supplement attendance; on approval the system creates the check-in"
               " times and recalculates that day",
               "Phiếu đề nghị bổ sung công; khi duyệt hệ thống tự tạo giờ chấm công và tính lại"
               " ngày công đó"),
              tag="Override",
            ),
            n("Suggested times", "Đề xuất giờ tự động",
              ("The system suggests the shift start, shift end or the end of registered"
               " overtime; HR can still edit each row by hand",
               "Hệ thống đề xuất giờ đầu ca, cuối ca, hoặc giờ kết thúc tăng ca đã đăng ký; HR"
               " vẫn sửa tay được từng dòng"),
              tag="Custom",
            ),
            n("Bulk create", "Tạo phiếu hàng loạt",
              ("Scan a date range, list everyone with missing scans and create one draft"
               " request per employee in a single step",
               "Quét một khoảng ngày, liệt kê những người quét thiếu, tạo một phiếu nháp cho"
               " mỗi nhân viên chỉ trong một bước"),
              tag="Custom",
            ),
            n("Signature form", "Giấy xác nhận công để ký",
              ("Print the confirmation form grouped by team, one A4 sheet per team; the signed"
               " scan is attached back to the request",
               "In giấy yêu cầu xác nhận công gom theo tổ, mỗi tổ một tờ A4; bản scan đã ký"
               " được đính kèm ngược lại vào phiếu"),
              tag="Custom",
            ),
          ],
        ),
        g("Attendance reports", "Báo cáo chấm công",
          None,
          children=[
            n("Monthly attendance sheet", "Bảng công tháng",
              ("Detailed attendance by shift, used for reconciliation and payroll",
               "Bảng công chi tiết theo ca, dùng để đối chiếu và tính lương"),
              tag="Custom",
            ),
            n("Daily email report", "Báo cáo gửi email hằng ngày",
              ("The system emails today's headcount, presence, absence and registered overtime,"
               " plus yesterday's missing attendance cases",
               "Hệ thống tự gửi báo cáo: Headcount/ hiện diện/ vắng/ đăng ký tăng ca của hôm"
               " nay, các trường hợp chấm công thiếu của ngày hôm trước"),
              tag="Custom",
            ),
            n("Excel export", "Xuất Excel",
              ("An Excel file laid out the same way as the attendance app currently in use",
               "Bản Excel có cấu trúc giống app chấm công hiên tại"),
              tag="Custom",
            ),
          ],
        ),
      ],
    ),
    n("Overtime", "Tăng ca",
      ("Register overtime hours by date and by employee, approve them, then summarise in"
       " reports and check the hour limits set by law",
       "Đăng ký giờ tăng ca theo ngày và theo nhân viên, phê duyệt, tổng hợp báo cáo và kiểm"
       " tra giới hạn giờ theo quy định của luật"),
      tag="Custom",
      children=[
        n("Register overtime", "Đăng ký tăng ca",
          ("Pick the date and the employees, enter overtime start and end time; the Get"
           " Employees button filters by department and group and shows total man-hours as you"
           " add people",
           "Chọn ngày, chọn nhân viên, khai giờ bắt đầu và giờ kết thúc tăng ca; nút Get"
           " Employees lọc theo bộ phận và nhóm, thấy ngay tổng giờ công khi chọn thêm người"),
          tag="Custom",
        ),
        n("Request & approval", "Yêu cầu & phê duyệt",
          ("The department requests and the manager approves before it counts - not in use yet",
           "Bộ phận đề xuất, cấp trên phê duyệt trước khi tính công - Chưa áp dụng"),
          tag="Custom",
        ),
        g("Overtime reports", "Báo cáo tăng ca",
          None,
          children=[
            n("By registration", "Theo phiếu đăng ký",
              ("Overtime slips and the hours booked on each of them",
               "Danh sách phiếu tăng ca và số giờ theo từng phiếu"),
              tag="Custom",
            ),
            n("By time slot", "Theo khung giờ",
              ("Headcount and hours of overtime per time slot of the day",
               "Số người và số giờ tăng ca theo từng khung giờ trong ngày"),
              tag="Custom",
            ),
            n("By quantity", "Theo số lượng",
              ("Total overtime hours by department and by period",
               "Tổng hợp số giờ tăng ca theo bộ phận và theo kỳ"),
              tag="Custom",
            ),
            n("Compliance check", "Kiểm tra tuân thủ",
              ("Warns when overtime exceeds the limits set by law",
               "Cảnh báo khi vượt giới hạn giờ tăng ca theo quy định của luật"),
              tag="Custom",
            ),
          ],
        ),
      ],
    ),
    g("Leave", "Nghỉ phép",
      ("Set up leave types and the holiday list, allocate balances, employees apply and"
       " managers approve, and the result flows straight into the attendance sheet",
       "Khai loại phép và lịch nghỉ lễ, phân bổ số dư phép, nhân viên nộp đơn và quản lý duyệt,"
       " kết quả cập nhật thẳng vào bảng công"),
      children=[
        n("Leave types", "Loại phép",
          ("Annual leave, unpaid leave, sick leave, maternity leave and compensatory leave",
           "Phép năm, nghỉ không lương, nghỉ ốm, thai sản, nghỉ bù"),
          tag="Standard",
        ),
        n("Holiday list", "Lịch nghỉ lễ",
          ("Public holidays and days off in lieu for each year",
           "Danh sách ngày lễ và ngày nghỉ bù áp dụng cho từng năm"),
          tag="Standard",
        ),
        n("Leave balance", "Số dư phép",
          ("Opening allocation plus leave earned month by month",
           "Phân bổ phép đầu kỳ và phép tích lũy theo từng tháng làm việc"),
          tag="Override",
        ),
        n("Leave application", "Đơn xin nghỉ phép",
          ("The employee applies, the manager approves, attendance follows the application",
           "Nhân viên tạo đơn, người quản lý phê duyệt, công được cập nhật theo đơn"),
          tag="Override",
        ),
        n("Half day leave", "Nghỉ nửa ngày",
          ("Half a day of annual leave still counts as a full working day",
           "Nghỉ nửa ngày phép vẫn được tính đủ công cho ngày đó"),
          tag="Override",
        ),
        n("Compensatory & encashment", "Nghỉ bù & thanh toán phép",
          ("Time off in lieu for extra days worked, and payment for unused leave",
           "Nghỉ bù cho ngày làm thêm và thanh toán phép chưa dùng"),
          tag="Standard",
        ),
        n("Leave reports", "Báo cáo phép",
          ("Leave balance per employee and leave history by period",
           "Số dư phép từng nhân viên và lịch sử nghỉ theo kỳ"),
          tag="Standard",
        ),
      ],
    ),
    g("Payroll", "Tiền lương",
      ("Configure insurance and tax rates, assign salary structures to employees, run payroll"
       " for the period, then issue payslips and payment reports",
       "Cấu hình tỷ lệ bảo hiểm và thuế, gán cơ cấu lương cho nhân viên, chạy bảng lương theo"
       " kỳ rồi phát phiếu lương và báo cáo chi trả"),
      children=[
        n("Payroll settings", "Cấu hình lương",
          ("Insurance rates, tax brackets and relief amounts, updated when the law changes",
           "Tỷ lệ bảo hiểm, bậc thuế, mức giảm trừ, cập nhật khi quy định thay đổi"),
          tag="Custom",
        ),
        n("Salary structure", "Cơ cấu lương",
          ("Basic salary, allowances and deductions",
           "Lương cơ bản, các khoản phụ cấp và các khoản trừ"),
          tag="Standard",
        ),
        n("Salary assignment", "Gán lương cho nhân viên",
          ("Assign a salary from an effective date, with bulk import from Excel",
           "Gán mức lương theo ngày hiệu lực, có thể nhập hàng loạt từ Excel"),
          tag="Override",
        ),
        n("Standard working days", "Ngày công chuẩn",
          ("Days in the period minus Sundays; public holidays still count as paid days",
           "Số ngày trong kỳ trừ các ngày chủ nhật, ngày lễ vẫn được tính công"),
          tag="Override",
        ),
        n("Vietnam statutory deductions", "Khấu trừ theo luật Việt Nam",
          None,
          tag="Override",
          children=[
            n("Insurance", "Bảo hiểm",
              ("Social insurance, health insurance and unemployment insurance",
               "Bảo hiểm xã hội, bảo hiểm y tế và bảo hiểm thất nghiệp"),
              tag="Override",
            ),
            n("Union fee", "Đoàn phí",
              ("Trade union fee deducted at the prescribed rate",
               "Trừ đoàn phí công đoàn theo tỷ lệ quy định"),
              tag="Override",
            ),
            n("Personal income tax", "Thuế thu nhập cá nhân",
              ("Calculated by tax bracket with personal and dependent relief",
               "Tính theo bậc thuế, có giảm trừ bản thân và người phụ thuộc"),
              tag="Override",
            ),
          ],
        ),
        n("Payroll run", "Chạy bảng lương",
          ("Run payroll for a period and generate payslips for all employees",
           "Chạy theo kỳ lương, sinh phiếu lương cho toàn bộ nhân viên"),
          tag="Standard",
        ),
        n("Payslip", "Phiếu lương",
          ("View and print payslips, with the amount spelled out in Vietnamese words",
           "Xem và in phiếu lương, số tiền được ghi bằng chữ tiếng Việt"),
          tag="Override",
        ),
        n("Payroll reports", "Báo cáo lương",
          ("Salary register, bank payment list and tax summaries",
           "Bảng lương tổng hợp, danh sách chi trả qua ngân hàng, tổng hợp thuế"),
          tag="Standard",
        ),
      ],
    ),
    g("Recruitment", "Tuyển dụng",
      ("The whole flow: plan the headcount need, post the opening, receive and interview"
       " applicants, up to the point the applicant becomes an employee",
       "Quy trình xuyên suốt: hoạch định nhu cầu, đăng tin, tiếp nhận và phỏng vấn ứng viên,"
       " đến khi ứng viên trở thành nhân viên chính thức"),
      children=[
        n("Staffing Plan", "Kế hoạch nhân sự",
          ("Plan headcount and recruitment budget for a period; the number of openings per"
           " designation is capped by the vacancies in the plan. Optional step",
           "Hoạch định số lượng và ngân sách tuyển dụng cho một khoảng thời gian; số tin tuyển"
           " của mỗi chức danh bị giới hạn bởi số vị trí trống trong kế hoạch. Bước tùy chọn"),
          tag="Standard",
          children=[
            n("Check Vacancies On Job Offer Creation", "Ràng buộc chỉ tiêu",
              ("This box must be ticked in HR Settings for the vacancy control to take effect",
               "Phải tích mục này trong HR Settings thì việc kiểm soát chỉ tiêu mới có hiệu lực"),
              tag="Standard",
            ),
          ],
        ),
        n("Job Requisition", "Yêu cầu tuyển dụng",
          ("Internal request to hire, optionally with an approval step; the system measures"
           " Time to Fill from the request until the position is filled. Optional step",
           "Đề xuất tuyển nhân sự trong nội bộ, có thể kèm phê duyệt; hệ thống tự tính Time to"
           " Fill từ lúc yêu cầu tới khi tuyển xong. Bước tùy chọn"),
          tag="Standard",
        ),
        n("Job Opening", "Vị trí tuyển dụng",
          ("A vacant position; it must exist before any applicant can be linked to it. Closing"
           " it blocks new applicants and flips the related requisition to Filled",
           "Vị trí còn trống, bắt buộc phải có thì mới tạo được hồ sơ ứng viên; đóng vị trí là"
           " chặn nộp thêm, và yêu cầu tuyển dụng liên quan tự chuyển sang Filled"),
          tag="Standard",
        ),
        n("Job Portal", "Cổng tuyển dụng",
          ("The /jobs page where candidates search and apply themselves; submitting creates a"
           " Job Applicant automatically. The opening must have Publish on website ticked to"
           " show up",
           "Trang /jobs để ứng viên tự tìm và nộp đơn, nộp xong hệ thống tự tạo hồ sơ ứng viên;"
           " phải tích Publish on website ở vị trí tuyển dụng thì tin mới hiện ra"),
          tag="Custom",
        ),
        n("Job Applicant", "Hồ sơ ứng viên",
          ("The central record of recruitment: profile, source, interview history and ratings;"
           " created by hand, from the job portal, from a referral or straight from an opening",
           "Tài liệu trung tâm của tuyển dụng: hồ sơ, nguồn ứng viên, lịch sử phỏng vấn và đánh"
           " giá; tạo tay, từ cổng tuyển dụng, từ giới thiệu nội bộ hoặc tạo nhanh từ vị trí"
           " tuyển dụng"),
          tag="Standard",
          children=[
            n("Employee Referral", "Giới thiệu nội bộ",
              ("An employee refers a candidate; when the candidate is accepted or rejected, the"
               " referral record follows automatically",
               "Nhân viên giới thiệu ứng viên; khi ứng viên được nhận hoặc bị loại thì trạng"
               " thái bản ghi giới thiệu tự cập nhật theo"),
              tag="Standard",
            ),
            n("Applicant status", "Trạng thái ứng viên",
              ("Open, Replied, Rejected, Hold, Accepted; clearing an interview does NOT change"
               " the applicant status - HR reviews the summary and updates it by hand",
               "Open, Replied, Rejected, Hold, Accepted; phỏng vấn đạt KHÔNG tự đổi trạng thái"
               " ứng viên, HR phải xem tổng hợp rồi cập nhật tay"),
              tag="Standard",
            ),
          ],
        ),
        n("Interview", "Phỏng vấn",
          ("Schedule interviews round by round and record the interviewers' ratings",
           "Lên lịch phỏng vấn theo từng vòng và ghi nhận đánh giá của người phỏng vấn"),
          tag="Standard",
          children=[
            n("Interview Round", "Vòng phỏng vấn",
              ("Define the rounds and the interviewers of each round; required before any"
               " interview can be scheduled",
               "Khai các vòng và người phỏng vấn của từng vòng; bắt buộc có trước khi lên lịch"
               " được"),
              tag="Standard",
            ),
            n("Interview Type", "Hình thức phỏng vấn",
              ("Classify the format: panel, face to face and so on. Optional",
               "Phân loại hình thức: hội đồng, trực tiếp… Tùy chọn"),
              tag="Standard",
            ),
            n("Interview Feedback", "Đánh giá phỏng vấn",
              ("Only people attached to the round can submit feedback; the system summarises"
               " skill scores and comments per applicant",
               "Chỉ người được gắn vào vòng phỏng vấn mới gửi được đánh giá; hệ thống tổng hợp"
               " điểm kỹ năng và nhận xét theo từng ứng viên"),
              tag="Standard",
            ),
            n("Calendar & reminder", "Lịch & nhắc lịch",
              ("See the interviews in a calendar and let the system email reminders to the"
               " interviewers",
               "Xem các buổi phỏng vấn dạng lịch và tự gửi email nhắc lịch cho người phỏng vấn"),
              tag="Standard",
            ),
          ],
        ),
        n("Job Offer", "Thư mời nhận việc",
          ("The formal offer, always created from an applicant record: job description, notice"
           " period, incentives and annual leave days",
           "Thư mời chính thức, bắt buộc tạo từ một hồ sơ ứng viên: mô tả công việc, thời gian"
           " báo trước khi nghỉ, thưởng, số ngày phép năm"),
          tag="Standard",
        ),
        n("Appointment Letter", "Thư bổ nhiệm",
          ("The formal letter asking the candidate to join; write it from a template and print"
           " a PDF to send",
           "Văn bản chính thức mời ứng viên gia nhập công ty; soạn theo mẫu có sẵn rồi in PDF"
           " gửi ứng viên"),
          tag="Standard",
        ),
        n("Employee Onboarding", "Tiếp nhận nhân viên mới",
          ("Final step of recruitment: carries the applicant data over to create the official"
           " employee record - see the Employee Records branch",
           "Bước cuối của tuyển dụng: kế thừa dữ liệu ứng viên để tạo hồ sơ nhân viên chính"
           " thức, chi tiết xem nhánh Hồ sơ nhân viên"),
          tag="Standard",
        ),
      ],
    ),
    g("Other HR functions", "Chức năng HR khác",
      ("Mostly used as delivered, not yet tailored to the company",
       "Phần lớn đang dùng theo bản chuẩn, chưa điều chỉnh riêng cho công ty"),
      children=[
        n("Performance appraisal", "Đánh giá hiệu suất",
          ("Appraisal cycles, goals, appraisal criteria and feedback",
           "Kỳ đánh giá, mục tiêu, tiêu chí đánh giá và phản hồi"),
          tag="Standard",
        ),
        n("Training", "Đào tạo",
          ("Training programs, sessions, results and learner feedback",
           "Chương trình đào tạo, buổi đào tạo, kết quả và phản hồi của người học"),
          tag="Standard",
        ),
        n("Expense claim & travel", "Hoàn ứng & công tác",
          ("Expense claims, employee advances and travel requests",
           "Đề nghị thanh toán chi phí, tạm ứng và yêu cầu đi công tác"),
          tag="Standard",
        ),
      ],
    ),
])


# ====================================== GA / HÀNH CHÍNH TỔNG HỢP
GA = n("GA - General Affairs", "Hành chính tổng hợp",
       ("Uniforms, health check-ups and shoe racks for the whole factory",
        "Đồng phục, khám sức khỏe và kệ giày cho toàn nhà máy"),
       status=None, children=[

    n("Uniform Control", "Quản lý đồng phục",
      ("Issue uniforms to the right entitlement, on time, with stock under control",
       "Cấp phát đồng phục đúng định mức, đúng hạn và kiểm soát được tồn kho"),
      tag="Custom", children=[
        g("Initial setup", "Thiết lập ban đầu", None, [
            n("Uniform warehouse & items", "Kho & danh mục đồng phục",
              ("Choose the issuing warehouse and the item group used for uniforms",
               "Chọn kho xuất đồng phục và nhóm hàng dùng cho đồng phục"), tag="Custom"),
            n("Default items", "Vật phẩm mặc định",
              ("Items used when no specific entitlement rule applies",
               "Vật phẩm dùng chung khi chưa có quy tắc riêng"), tag="Custom"),
            n("Alert settings", "Cấu hình cảnh báo",
              ("Days of notice before due, email recipients, and the weekly email on / off",
               "Số ngày nhắc trước hạn, người nhận email và bật tắt email hằng tuần"),
              tag="Custom"),
            n("Attrition assumption", "Giả định nghỉ việc",
              ("Allowance for employees who leave mid-period when forecasting demand",
               "Dự phòng cho số nhân viên nghỉ giữa kỳ khi dự báo nhu cầu"), tag="Custom"),
        ]),
        g("Entitlement rules", "Quy tắc định mức", None, [
            n("Who gets what", "Ai được cấp gì",
              ("Entitlement by designation, grade, section, group and gender",
               "Định mức theo chức danh, bậc, bộ phận, nhóm và giới tính"), tag="Custom"),
            n("Quantity & cycle", "Số lượng & chu kỳ",
              ("First issue quantity, days of service to qualify, months before reissue",
               "Số lượng cấp lần đầu, số ngày làm việc để đủ điều kiện, số tháng cấp lại"),
              tag="Custom"),
            n("One-time items", "Vật phẩm cấp một lần",
              ("Items issued only once, never on a recurring cycle",
               "Vật phẩm chỉ cấp một lần, không cấp lại theo chu kỳ"), tag="Custom"),
            n("Rule priority", "Ưu tiên quy tắc",
              ("Decides which rule wins when one person matches several rules",
               "Quyết định quy tắc nào được áp dụng khi một người khớp nhiều quy tắc"),
              tag="Custom"),
        ]),
        g("Employee uniform profile", "Hồ sơ đồng phục nhân viên", None, [
            n("Sizes", "Cỡ áo & cỡ giày",
              ("Store each employee's sizes so the first issue is already correct",
               "Lưu cỡ của từng nhân viên để cấp đúng ngay lần đầu"), tag="Custom"),
            n("Shoe rack location", "Vị trí kệ giày",
              ("The shoe compartment location, filled in automatically from shoe rack management",
               "Vị trí ô để giày, lấy tự động từ phần quản lý kệ giày"), tag="Custom"),
            n("Next due date", "Ngày đến hạn cấp lại",
              ("Calculated from the rule cycle and the most recent issue",
               "Tính theo chu kỳ của quy tắc và lần cấp gần nhất"), tag="Custom"),
            n("Manual override", "Ghi đè thủ công",
              ("Adjust individual cases where the general rule does not fit",
               "Điều chỉnh riêng cho trường hợp ngoại lệ mà quy tắc chung không đúng"),
              tag="Custom"),
            n("Issued history", "Lịch sử đã cấp",
              ("How many times each item was issued and when the last one was",
               "Từng vật phẩm đã cấp bao nhiêu lần, lần cuối là khi nào"), tag="Custom"),
        ]),
        g("Allocation & issue", "Cấp phát", None, [
            n("Find eligible employees", "Tìm nhân viên đủ điều kiện",
              ("Filter by department, group, gender, joining date, or show only overdue people",
               "Lọc theo bộ phận, nhóm, giới tính, ngày vào làm, hoặc chỉ lấy người quá hạn"),
              tag="Custom"),
            n("Create & confirm slip", "Tạo & xác nhận phiếu cấp phát",
              ("Draw up one slip for many people, check it, then confirm",
               "Lập phiếu cấp cho nhiều người, kiểm tra rồi xác nhận"), tag="Custom"),
            n("Warehouse issue", "Xuất kho",
              ("Confirming the slip deducts stock automatically, no double data entry",
               "Xác nhận phiếu là tồn kho được trừ tự động, không nhập liệu hai lần"),
              tag="Custom"),
            n("Reuse old items", "Tái sử dụng đồ cũ",
              ("Record cases where an old item is reused, with the reason for issue",
               "Ghi nhận trường hợp dùng lại đồ cũ kèm lý do cấp"), tag="Custom"),
            n("Item reissue", "Cấp lại vật phẩm",
              ("Handle items lost, damaged or exchanged for another size",
               "Xử lý các trường hợp mất, hỏng hoặc đổi cỡ"), tag="Custom"),
        ]),
        g("Tracking", "Theo dõi", None, [
            n("Due & overdue list", "Danh sách đến hạn & quá hạn",
              ("See immediately who needs to be issued in the coming period",
               "Biết ngay ai cần được cấp trong thời gian tới"), tag="Custom"),
            n("Recalculate", "Tính lại",
              ("Rebuild the whole tracking after changing a rule or fixing old data",
               "Cập nhật lại toàn bộ theo dõi sau khi sửa quy tắc hoặc dữ liệu cũ"),
              tag="Custom"),
        ]),
        g("Demand forecast", "Dự báo nhu cầu", None, [
            n("Forecast by period", "Dự báo theo kỳ",
              ("Quantity to prepare based on entitlement, headcount and the hiring plan",
               "Số lượng cần chuẩn bị dựa trên định mức, số lao động và kế hoạch tuyển mới"),
              tag="Custom"),
            n("Size ratio", "Tỷ lệ cỡ",
              ("Split the quantity across sizes using the ratio actually in use",
               "Phân bổ số lượng theo từng cỡ dựa trên tỷ lệ đang dùng thực tế"), tag="Custom"),
            n("Leavers estimate", "Ước tính nghỉ việc",
              ("Deduct the share for employees expected to leave during the period",
               "Trừ bớt phần cho số lao động dự kiến nghỉ trong kỳ"), tag="Custom"),
            n("Shortfall vs stock", "Thiếu hụt so với tồn kho",
              ("Compare the forecast against stock on hand to know how much to buy",
               "So dự báo với tồn kho hiện có để biết cần đặt mua bao nhiêu"), tag="Custom"),
        ]),
        g("Dashboard & reports", "Bảng điều khiển & báo cáo", None, [
            n("Summary dashboard", "Trang tổng quan",
              ("Issue status, people due and stock on hand on a single page",
               "Tình hình cấp phát, số người đến hạn và tồn kho trên một trang"), tag="Custom"),
            n("Stock report", "Báo cáo tồn kho",
              ("Uniform stock by item and by size",
               "Tồn kho đồng phục theo từng vật phẩm và cỡ"), tag="Custom"),
            n("Due employees report", "Báo cáo nhân viên đến hạn",
              ("The list of people due for issue, exportable to Excel to work from",
               "Danh sách người đến hạn cấp, xuất ra Excel để đi cấp"), tag="Custom"),
            n("Allocation history report", "Báo cáo lịch sử cấp phát",
              ("Look up what was issued, to whom and on which date",
               "Tra lại đã cấp gì, cho ai, ngày nào"), tag="Custom"),
            n("Cost report", "Báo cáo chi phí",
              ("Uniform cost by period and by department",
               "Chi phí đồng phục theo kỳ và theo bộ phận"), tag="Custom"),
        ]),
        n("Weekly reminder email", "Email nhắc hằng tuần",
          ("Automatically emails the people in charge who is due and who is overdue",
           "Tự gửi danh sách người sắp và đã đến hạn cho người phụ trách"), tag="Custom"),
        n("Uniform Manager role", "Vai trò người phụ trách đồng phục",
          ("Only authorised staff can create issue slips and change entitlement rules",
           "Chỉ người được giao quyền mới lập phiếu cấp và sửa quy tắc định mức"),
          tag="Custom"),
        n("Links to other functions", "Liên kết với chức năng khác",
          ("Shares employee data, warehouse stock and shoe rack locations",
           "Dùng chung dữ liệu nhân viên, kho hàng và vị trí kệ giày"), tag="Custom"),
    ]),

    n("Health Check-Up", "Khám sức khỏe",
      ("Run periodic check-ups for the whole factory, track who attended and keep the results",
       "Tổ chức khám định kỳ cho toàn nhà máy, theo dõi ai đã khám và lưu kết quả"),
      tag="Custom", children=[
        g("Plan a session", "Lập kế hoạch đợt khám", None, [
            n("Date & hospital", "Ngày khám & bệnh viện",
              ("Set the date and the medical provider carrying out the check-up",
               "Khai ngày tổ chức và đơn vị y tế thực hiện"), tag="Custom"),
            n("Check-up type", "Loại khám",
              ("Periodic check-up, occupational disease check-up or another type",
               "Khám định kỳ, khám bệnh nghề nghiệp hoặc loại khám khác"), tag="Custom"),
            n("Employee list", "Danh sách nhân viên",
              ("Build the list by department, group and designation",
               "Lập danh sách theo bộ phận, nhóm và chức danh"), tag="Custom"),
            n("Planned time slot", "Khung giờ dự kiến",
              ("Split people across time slots so production is not disrupted",
               "Chia đợt theo giờ để tránh dồn người, không ảnh hưởng sản xuất"), tag="Custom"),
            n("Reschedule", "Dời lịch",
              ("Move the whole session to another date when the hospital changes plan",
               "Đổi ngày khám cho cả đợt khi bệnh viện thay đổi kế hoạch"), tag="Custom"),
        ]),
        g("Exam items", "Nội dung khám", None, [
            n("X-ray", "Chụp X-quang",
              ("Mark which employees have a chest X-ray in this session",
               "Đánh dấu nhân viên có chụp X-quang trong đợt khám"), tag="Custom"),
            n("Gynecological exam", "Khám phụ khoa",
              ("Applies to female workers as required by regulation",
               "Áp dụng cho lao động nữ theo quy định"), tag="Custom"),
            n("Pregnancy exclusion", "Loại trừ khi mang thai",
              ("Pregnant employees skip the X-ray and the gynecological exam",
               "Nhân viên đang mang thai được bỏ chụp X-quang và khám phụ khoa"), tag="Custom"),
            n("Not attending", "Không khám",
              ("Flag people not taking part and record the reason",
               "Đánh dấu và ghi lý do cho người không tham gia đợt khám"), tag="Custom"),
        ]),
        g("On-site scanning", "Quét mã tại chỗ", None, [
            n("Scan to hand out form", "Quét phát phiếu",
              ("Scan the badge when handing out the form; the actual start time is recorded",
               "Quét thẻ nhân viên khi phát phiếu, hệ thống ghi giờ bắt đầu thực tế"),
              tag="Custom"),
            n("Scan to collect form", "Quét thu phiếu",
              ("Scan when collecting the form; the actual finish time is recorded",
               "Quét khi thu phiếu, hệ thống ghi giờ kết thúc thực tế"), tag="Custom"),
            n("Employee code lookup", "Tra mã nhân viên",
              ("Recognises the code even when leading zeros are missing",
               "Nhận diện được cả khi mã quét thiếu số 0 ở đầu"), tag="Custom"),
            n("Works offline", "Hoạt động khi mất mạng",
              ("Scanning keeps working offline and uploads once the network is back",
               "Vẫn quét được khi mất mạng, dữ liệu tự đưa lên khi có mạng lại"), tag="Custom"),
        ]),
        g("Status & results", "Trạng thái & kết quả", None, [
            n("Status per employee", "Trạng thái từng người",
              ("Not yet examined, in progress, examined, not attending",
               "Chưa khám, đang khám, đã khám, không khám"), tag="Custom"),
            n("Recalculate status", "Tính lại trạng thái",
              ("Refresh the status of the whole session after correcting data",
               "Cập nhật lại trạng thái của cả đợt sau khi chỉnh dữ liệu"), tag="Custom"),
            n("Attach result files", "Gắn file kết quả",
              ("Attach the results returned by the hospital to each person's record",
               "Đính kèm kết quả bệnh viện trả về vào hồ sơ từng người"), tag="Custom"),
            n("Result & note", "Kết luận & ghi chú",
              ("Record the health conclusion and anything needing follow-up",
               "Ghi kết luận sức khỏe và các lưu ý cần theo dõi"), tag="Custom"),
        ]),
        n("Management page", "Trang quản lý đợt khám",
          ("Follow session progress in real time: how many done, how many left",
           "Theo dõi tiến độ đợt khám theo thời gian thực: đã khám bao nhiêu, còn lại bao nhiêu"),
          tag="Custom"),
        n("Session Excel export", "Xuất Excel đợt khám",
          ("Export the list and results of each session for records and reporting",
           "Xuất danh sách và kết quả theo từng đợt để lưu hồ sơ và báo cáo"), tag="Custom"),
        n("Access control", "Phân quyền truy cập",
          ("Health data is private, so only the staff in charge can view it",
           "Thông tin sức khỏe là dữ liệu riêng tư, chỉ người phụ trách được xem"),
          tag="Custom"),
    ]),

    n("Shoe Rack Management", "Quản lý kệ giày",
      ("One compartment per person: know whose it is and which ones are free",
       "Mỗi người một ô để giày, biết ô nào của ai và ô nào còn trống"),
      tag="Custom", children=[
        g("Rack records", "Hồ sơ kệ", None, [
            n("Rack name & type", "Tên & loại kệ",
              ("Name racks by area and classify them by type",
               "Đặt tên kệ theo khu vực và phân loại kệ"), tag="Custom"),
            n("Compartments", "Số ô của kệ",
              ("Declare how many shoe compartments each rack has",
               "Khai số ô để giày trên mỗi kệ"), tag="Custom"),
            n("Rack status", "Trạng thái kệ",
              ("In use, free or withdrawn from use",
               "Đang dùng, còn trống hoặc ngưng sử dụng"), tag="Custom"),
        ]),
        g("Compartment assignment", "Gán ô để giày", None, [
            n("Assign to employee", "Gán cho nhân viên",
              ("Assign a compartment to someone on the employee list",
               "Gán ô cho nhân viên trong danh sách nhân sự"), tag="Custom"),
            n("Assign to external personnel", "Gán cho nhân sự ngoài",
              ("Assign a compartment to a visitor or long-term contractor",
               "Gán ô cho khách hoặc nhà thầu làm việc dài ngày"), tag="Custom"),
            n("Unidentified user", "Chưa xác định người dùng",
              ("A compartment holding shoes but with no known owner, needs checking",
               "Ô đang có giày nhưng chưa biết của ai, cần rà soát"), tag="Custom"),
            n("Gender per compartment", "Giới tính theo ô",
              ("Keep male and female areas separate",
               "Bố trí khu nam và khu nữ riêng"), tag="Custom"),
        ]),
        g("Floor layout", "Sơ đồ mặt bằng", None, [
            n("Layout manager", "Trang thiết kế sơ đồ",
              ("Drag and drop racks to match the real factory floor",
               "Kéo thả các kệ đúng theo mặt bằng thật của nhà máy"), tag="Custom"),
            n("Pathways", "Lối đi",
              ("Draw the walkways between rows so the map is easy to read",
               "Vẽ lối đi giữa các dãy kệ để sơ đồ dễ đọc và dễ tìm"), tag="Custom"),
            n("Save layout", "Lưu sơ đồ",
              ("Save the layout so everyone works from the same map",
               "Lưu lại sơ đồ để mọi người cùng xem trên cùng một bản"), tag="Custom"),
        ]),
        n("Dashboard", "Bảng điều khiển",
          ("The whole picture by area: assigned, free, and compartments to check",
           "Nhìn tổng thể theo khu vực: ô đã gán, ô còn trống, ô cần rà soát"), tag="Custom"),
        n("Search & list", "Tìm kiếm & danh sách",
          ("Look up one employee's compartment or browse the full rack list",
           "Tra nhanh vị trí ô của một nhân viên hoặc xem toàn bộ danh sách kệ"), tag="Custom"),
        n("Auto sync to uniform profile", "Tự đồng bộ sang hồ sơ đồng phục",
          ("Changing a compartment updates the uniform profile too, no double editing",
           "Đổi ô để giày thì hồ sơ đồng phục của nhân viên cập nhật theo, không sửa hai nơi"),
          tag="Custom"),
        n("Menu shortcut", "Lối tắt trên menu",
          ("Reach it straight from the home page without hunting through the function list",
           "Truy cập nhanh từ trang chủ mà không cần tìm trong danh sách chức năng"),
          tag="Custom"),
    ]),
])


# ============================================================ LINK TỚI CHỨC NĂNG
# Khoá là tiêu đề tiếng Anh của mục. Link được ghi vào file .md dưới dạng
# markdown [tiêu đề](đường dẫn) nên sửa trực tiếp trong .md cũng được.
# Đường dẫn có dấu cách phải viết %20, nếu không markdown sẽ hiểu sai.
# Dùng đường dẫn tương đối, không ghi tên miền: trang /mindmap có ô chọn host
# nên cùng một file .md mở được ở erp.tiqn.com.vn:8888 hay erp.tiqn.local đều đúng.
# Desk của Frappe v16 nằm ở /desk (đường /app chỉ chuyển hướng sang /desk).
LINKS = {
    # Sinh lại từ docs/mindmap/hr_mindmap.md (nhánh HR) + giữ nguyên phần GA.
    # Link thật nằm trong .md; dict này chỉ là mặc định cho mục mới thêm.
    "Access control": "/desk/role",
    "Alert settings": "/desk/uniform-setting",
    "Allocation history report": "/desk/uniform-allocation/view/report",
    "Anomaly note": "/desk/attendance/view/report",
    "Appointment Letter": "/desk/appointment-letter",
    "Assign shift": "/desk/shift-assignment",
    "Assign to employee": "/desk/shoe-rack",
    "Assign to external personnel": "/desk/external-personnel",
    "Attach result files": "/desk/health-check-up-management",
    "Attendance calculation": "/desk/attendance",
    "Attendance confirmation request": "/desk/attendance-request",
    "Attendance status": "/desk/attendance/view/list",
    "Attrition assumption": "/desk/uniform-setting",
    "Auto sync to uniform profile": "/desk/employee-uniform-profile",
    "Automatic daily run": "/desk/shift-type",
    "Bulk create": "/desk/attendance-request/view/list",
    "Bulk shift assignment": "/desk/shift-assignment-tool",
    "By quantity": "/desk/query-report/Overtime%20Registration%20Quantity",
    "By registration": "/desk/query-report/Overtime%20Registration",
    "By time slot": "/desk/query-report/Overtime%20Registration%20by%20Time%20Slot",
    "Check Vacancies On Job Offer Creation": "/desk/hr-settings",
    "Check scan data": "/biometric_sync",
    "Check-in records": "/desk/employee-checkin",
    "Check-up type": "/desk/health-check-up",
    "Compartments": "/desk/shoe-rack",
    "Compensatory & encashment": "/desk/compensatory-leave-request",
    "Compliance check": "/desk/query-report/OT%20Compliance",
    "Connect machines": "/desk/attendance-machine-setting",
    "Corrections": "/desk/attendance",
    "Cost report": "/desk/uniform-dashboard",
    "Create & confirm slip": "/desk/uniform-allocation",
    "Daily email report": "/desk/query-report/Shift%20Attendance%20Customize",
    "Dashboard": "/desk/shoe-rack-dashboard",
    "Date & hospital": "/desk/health-check-up",
    "Default items": "/desk/uniform-setting",
    "Dependents": "/desk/employee-dependent",
    "Due & overdue list": "/desk/query-report/Uniform%20Tracking",
    "Due employees report": "/desk/query-report/Uniform%20Tracking",
    "Employee Onboarding": "/desk/employee-onboarding",
    "Employee Promotion": "/desk/employee-promotion",
    "Employee Referral": "/desk/employee-referral",
    "Employee Transfer": "/desk/employee-transfer",
    "Employee Transfer & Promotion Report": "/desk/query-report/Employee%20Transfer%20and%20Promotion",
    "Employee code lookup": "/desk/health-check-up-management",
    "Employee list": "/desk/health-check-up/view/report",
    "Employee photo": "/employee-photos",
    "Employee profile": "/desk/employee",
    "Employee reports": "/desk/dashboard-view/HR%20Overview",
    "Employment Type": "/desk/employment-type",
    "Excel export": "/desk/query-report/Shift%20Attendance%20Customize",
    "Expense claim & travel": "/desk/expense-claim",
    "Find eligible employees": "/desk/uniform-allocation/new",
    "Fingerprint machines": "/desk/attendance-machine-setting",
    "Forecast by period": "/desk/uniform-demand-forecast",
    "Gender per compartment": "/desk/shoe-rack/view/report",
    "Gynecological exam": "/desk/health-check-up/view/report",
    "Half day leave": "/desk/leave-application",
    "Health Check-Up": "/desk/health-check-up-management",
    "Holiday list": "/desk/holiday-list",
    "Insurance": "/desk/tiqn-insurance-rate",
    "Interview": "/desk/interview",
    "Interview Feedback": "/desk/interview-feedback",
    "Interview Round": "/desk/interview-round",
    "Interview Type": "/desk/interview-type",
    "Issued history": "/desk/query-report/Uniform%20Tracking",
    "Item reissue": "/desk/query-report/Employee%20Item%20Reissue",
    "Job Applicant": "/desk/job-applicant",
    "Job Offer": "/desk/job-offer",
    "Job Opening": "/desk/job-opening",
    "Job Portal": "/jobs",
    "Job Requisition": "/desk/job-requisition",
    "Labor contract": "/desk/query-report/Labor%20Contract%20Report",
    "Late & early leave": "/desk/attendance/view/list",
    "Layout manager": "/desk/layout-manager",
    "Leave application": "/desk/leave-application",
    "Leave balance": "/desk/leave-allocation",
    "Leave reports": "/desk/query-report/Employee%20Leave%20Balance",
    "Leave types": "/desk/leave-type",
    "Leave-linked days": "/desk/attendance",
    "Leavers estimate": "/desk/uniform-demand-forecast",
    "Links to other functions": "/desk/employee-uniform-profile",
    "Management page": "/desk/health-check-up-management",
    "Manual override": "/desk/employee-uniform-profile",
    "Maternity records": "/desk/query-report/Employee%20Maternity%20Report",
    "Menu shortcut": "/desk/workspace",
    "Monthly attendance sheet": "/desk/query-report/Shift%20Attendance%20Customize",
    "Next due date": "/desk/employee-uniform-profile",
    "Not attending": "/desk/health-check-up/view/report",
    "Onboarding": "/desk/employee-onboarding",
    "One-time items": "/desk/uniform-rule",
    "Organization structure": "/desk/department",
    "Overtime": "/desk/overtime-registration",
    "Pathways": "/desk/layout-manager",
    "Payroll reports": "/desk/query-report/Salary%20Register",
    "Payroll run": "/desk/payroll-entry",
    "Payroll settings": "/desk/tiqn-payroll-settings",
    "Payslip": "/desk/salary-slip",
    "Performance appraisal": "/desk/appraisal",
    "Personal income tax": "/desk/tiqn-tax-bracket",
    "Planned time slot": "/desk/health-check-up-management",
    "Pregnancy exclusion": "/desk/health-check-up/view/report",
    "Push employees to machines": "/biometric_sync",
    "Quantity & cycle": "/desk/uniform-rule",
    "Rack name & type": "/desk/shoe-rack",
    "Rack status": "/desk/shoe-rack/view/report",
    "Recalculate": "/desk/uniform-dashboard",
    "Recalculate status": "/desk/health-check-up-management",
    "Recruitment": "/desk/job-opening",
    "Register fingerprints": "/desk/fingerprint-data",
    "Register overtime": "/desk/overtime-registration",
    "Request & approval": "/desk/overtime-request",
    "Reschedule": "/desk/health-check-up-management",
    "Resignation Application": "/desk/resignation-application",
    "Result & note": "/desk/health-check-up",
    "Reuse old items": "/desk/uniform-allocation",
    "Rule priority": "/desk/uniform-rule",
    "Salary assignment": "/desk/salary-structure-assignment",
    "Salary structure": "/desk/salary-structure",
    "Save layout": "/desk/shoe-rack-layout-settings",
    "Scan to collect form": "/desk/health-check-up-management",
    "Scan to hand out form": "/desk/health-check-up-management",
    "Search & list": "/desk/shoe-rack",
    "Section & Group": "/desk/section",
    "Self-service update": "/employee-self-update-info",
    "Shift priority": "/desk/shift-type",
    "Shift type": "/desk/shift-type",
    "Session Excel export": "/desk/health-check-up-management",
    "Shoe Rack Management": "/desk/shoe-rack-dashboard",
    "Shoe rack location": "/desk/employee-uniform-profile",
    "Shortfall vs stock": "/desk/uniform-demand-forecast",
    "Signature form": "/desk/attendance-request/view/list",
    "Size ratio": "/desk/uniform-demand-forecast",
    "Sizes": "/desk/employee-uniform-profile",
    "Staffing Plan": "/desk/staffing-plan",
    "Standard working days": "/desk/salary-slip",
    "Status per employee": "/desk/health-check-up/view/report",
    "Stock report": "/desk/uniform-dashboard",
    "Suggested times": "/desk/attendance-request",
    "Summary dashboard": "/desk/uniform-dashboard",
    "Sync machine clock": "/biometric_sync",
    "Training": "/desk/training-program",
    "Transfer & promotion": "/desk/employee-transfer",
    "Unidentified user": "/desk/shoe-rack/view/report",
    "Uniform Control": "/desk/uniform-dashboard",
    "Uniform Manager role": "/desk/role/Uniform%20Manager",
    "Uniform warehouse & items": "/desk/uniform-setting",
    "Union fee": "/desk/tiqn-payroll-settings",
    "Vietnam statutory deductions": "/desk/tiqn-payroll-settings",
    "Warehouse issue": "/desk/stock-entry",
    "Weekly reminder email": "/desk/uniform-setting",
    "Who gets what": "/desk/uniform-rule",
    "Works offline": "/desk/health-check-up-management",
    "X-ray": "/desk/health-check-up/view/report",
}


def check_duplicate_names(tree, warnings):
    """Hai mục cùng tiêu đề tiếng Anh sẽ dùng chung một dòng LINKS -> một trong hai
    mục nhận link sai. Đã xảy ra: "Excel export" của Khám sức khỏe từng trỏ sang
    báo cáo chấm công."""
    seen = {}
    for n in all_nodes(tree):
        seen.setdefault(n["en"], []).append(n["label"])
    for en, labels in seen.items():
        if len(labels) > 1:
            warnings.append("trùng tiêu đề tiếng Anh '%s': %s — link sẽ lấy nhầm của nhau"
                            % (en, " | ".join(labels)))


def all_nodes(node):
    yield node
    for c in node.get("children", []):
        yield from all_nodes(c)


def apply_links(node):
    link = LINKS.get(node.get("en"))
    if link:
        node["link"] = link
    guide = GUIDES.get(node.get("en"))
    if guide:
        node["guide"] = guide
    for c in node.get("children", []):
        apply_links(c)


def legend_branch():
    """Nhánh chú thích ký hiệu, đặt cuối mỗi sơ đồ."""
    return g("Legend", "Chú thích ký hiệu", None, [
        g("Classification", "Phân loại chức năng", None, [
            n("Standard", "Chuẩn",
              ("A built-in feature of the system, used as delivered",
               "Chức năng có sẵn của hệ thống, dùng nguyên bản, không sửa gì"), status=None),
            n("Override", "Đã sửa",
              ("A standard feature modified to match company regulations",
               "Chức năng chuẩn nhưng đã được sửa cho phù hợp quy định công ty"), status=None),
            n("Custom", "Phát triển thêm",
              ("Developed in-house; the original system does not have it",
               "Chức năng tự phát triển riêng, hệ thống gốc không có"), status=None),
        ], status=None),
        g("Progress", "Tiến độ", None, [
            n("Done", "Hoàn thành",
              ("Delivered and in use", "Đã triển khai và đang sử dụng"), status=None),
            n("In process", "Đang làm",
              ("Under development or in trial, shown with % complete",
               "Đang phát triển hoặc đang chạy thử, hiện kèm % hoàn thành"), status=None),
            n("Pending", "Chờ làm",
              ("Planned but not started, shown with the reason",
               "Đã lên kế hoạch, chưa bắt đầu, hiện kèm lý do"), status=None),
        ], status=None),
    ], status=None)


HEADERS = {
    "hr": ("HR Mindmap - Quản lý Nhân sự",
           "Sơ đồ chức năng phần Nhân sự, dùng để giới thiệu và hướng dẫn người dùng"),
    "ga": ("GA Mindmap - Hành chính tổng hợp",
           "Sơ đồ chức năng phần Hành chính: đồng phục, khám sức khỏe, kệ giày"),
}

# Nhận cả các cách viết khác nhau khi đọc lại tiến độ sửa tay
STATUS_ALIASES = {
    "done": "Done",
    "in process": "In process",
    "inprocess": "In process",
    "in-process": "In process",
    "in progress": "In process",
    "inprogress": "In process",
    "in-progress": "In process",
    "doing": "In process",
    "wip": "In process",
    "pending": "Pending",
    "todo": "Pending",
    "to do": "Pending",
    "to-do": "Pending",
}

LINE_RE = re.compile(
    r"^\s*- \*\*(?P<label>.+?)\*\*(?P<tags>(?:\s*`\[[^\]]+\]`)*)"
    r"(?:\s*(?:—|–|--)\s*(?P<desc>.*?))?"
    # link bài hướng dẫn có thể đứng cuối dòng ngay cả khi mục không có mô tả
    r"(?:\s*\[[^\]]*\]\(/lms/[^)\s]*\))?\s*$"
)
TAG_RE = re.compile(r"`\[([^\]]+)\]`")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]*)\)")
# Link bài hướng dẫn trong LMS, đặt cuối dòng: [Guide](/lms/courses/module-hrms/learn/4-1)
GUIDE_LINK_RE = re.compile(r"\s*\[([^\]]*)\]\((/lms/[^)\s]*)\)")
# Số thứ tự tự đánh ở đầu tiêu đề: "01. Employee Records / Hồ sơ nhân viên"
ORDER_RE = re.compile(r"^\s*(\d{1,3})\s*[.)\-–]?\s+")


def split_order(label):
    """Tách số thứ tự khỏi tiêu đề: ('01.', 'Employee Records / ...')."""
    m = ORDER_RE.match(label)
    if not m:
        return "", label.strip()
    return label[:m.end()].strip(), label[m.end():].strip()


def parse_status_tag(val):
    """'In process 60%' -> ('In process', '60%');  'Pending: chờ NS' -> ('Pending', 'chờ NS')."""
    raw = val.strip()
    low = raw.lower()
    for k in sorted(STATUS_ALIASES, key=len, reverse=True):
        if low == k:
            return STATUS_ALIASES[k], ""
        if low.startswith(k):
            return STATUS_ALIASES[k], raw[len(k):].lstrip(" :.-–—|").strip()
    return None, None


def format_status(canon, value):
    if not value:
        return canon
    return canon + (": " if canon == "Pending" else " ") + value


def status_base(status):
    """Bỏ phần % hoặc lý do, chỉ lấy Done / In process / Pending để đếm."""
    canon, _ = parse_status_tag(status or "")
    return canon or (status or "")


def read_existing_meta(path):
    """Đọc file .md cũ, lấy lại phần đã sửa tay theo tiêu đề mục.

    Giữ: tiến độ (kèm % hoặc lý do), mô tả và link. Nhờ vậy sửa tay trong .md
    hoặc sửa trên trang /mindmap rồi build lại vẫn không mất.
    """
    if not os.path.exists(path):
        return {}, "\n"

    with open(path, "rb") as f:
        raw = f.read()
    # Editor Windows lưu CRLF; giữ nguyên kiểu xuống dòng để git không diff cả file
    newline = "\r\n" if raw.count(b"\r\n") > raw.count(b"\n") // 2 else "\n"
    text = raw.decode("utf-8")

    found = {}
    in_comment = False
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped.startswith("<!--"):
            if "-->" not in stripped:
                in_comment = True
            continue

        if stripped.startswith("> "):
            g = GUIDE_LINK_RE.search(line)
            if g:
                found.setdefault("__root__", {})["guide"] = g.group(2).strip()
            continue

        m = LINE_RE.match(line)
        if not m:
            continue

        raw_label = m.group("label")
        link_match = MD_LINK_RE.search(raw_label)
        # Link thứ hai trỏ vào /lms/ là bài hướng dẫn, nằm cuối dòng sau phần mô tả
        guide_match = GUIDE_LINK_RE.search(line)
        # Tiêu đề có thể được bọc thành link markdown, bỏ phần link để khớp đúng mục
        label = MD_LINK_RE.sub(r"\1", raw_label).strip()
        # Số thứ tự tự đánh không tính vào khoá khớp, nhưng phải giữ lại
        num, label = split_order(label)
        entry = found.setdefault(label, {})
        if num:
            entry["num"] = num
        # Link hoặc mô tả để rỗng là có chủ ý, phải giữ rỗng chứ không lấy lại từ script
        if link_match:
            entry["link"] = link_match.group(2).strip()
        if guide_match:
            entry["guide"] = guide_match.group(2).strip()
        if m.group("desc") is not None:
            desc = m.group("desc")
            if guide_match:
                desc = desc.replace(guide_match.group(0), "")   # tách link hướng dẫn ra khỏi mô tả
            entry["desc"] = desc.strip()
        for t in TAG_RE.findall(m.group("tags")):
            if t in TYPES:
                entry["type"] = t
                continue
            canon, value = parse_status_tag(t)
            if canon:
                entry["status"] = format_status(canon, value)

    return found, newline


def all_labels(node, out=None):
    if out is None:
        out = []
    out.append(node["label"])
    for c in node.get("children", []):
        all_labels(c, out)
    return out


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)


def prune_removed(node, saved, known, removed):
    """Bỏ khỏi cây những mục đã từng xuất ra .md nhưng nay không còn trong đó.

    Đó là mục bị xoá hoặc comment lại có chủ ý, không dựng lại nữa.
    Mục chưa từng xuất hiện (mới thêm vào script) thì vẫn được thêm.
    """
    keep = []
    for c in node.get("children", []):
        if c["label"] in known and c["label"] not in saved:
            removed.append(c["label"])
            continue
        prune_removed(c, saved, known, removed)
        keep.append(c)
    if node.get("children") is not None:
        node["children"] = keep


def walk(node, depth, out, fn):
    fn(node, depth, out)
    for c in node.get("children", []):
        walk(c, depth + 1, out, fn)


def apply_root_guide(tree, saved):
    entry = saved.get("__root__") or {}
    if entry.get("guide"):
        tree["guide"] = entry["guide"]


def apply_saved_meta(node, saved, keep_content, missing):
    """Áp lại phần đã sửa tay trong .md lên cây lấy từ script.

    keep_content=False (cờ --from-script) thì lấy nội dung theo script, chỉ giữ tiến độ.
    missing: gom các mục có trong script nhưng không thấy trong .md để cảnh báo.
    """
    entry = saved.get(node["label"])
    if entry is None:
        if node.get("status"):        # bỏ qua node gốc và nhánh chú thích
            missing.append(node["label"])
    else:
        if node.get("status") and entry.get("status"):
            node["status"] = entry["status"]
        if entry.get("num"):
            node["num"] = entry["num"]
        if keep_content:
            if "desc" in entry and entry["desc"] != node.get("desc"):
                node.pop("desc_en", None)   # mô tả đã đổi, bản dịch cũ không còn đúng
                if entry["desc"]:
                    node["desc"] = entry["desc"]
                else:
                    node.pop("desc", None)
            if "link" in entry:
                if entry["link"]:
                    node["link"] = entry["link"]
                else:
                    node.pop("link", None)
            if entry.get("guide"):
                node["guide"] = entry["guide"]
            if entry.get("type") and node.get("type"):
                node["type"] = entry["type"]
    for c in node.get("children", []):
        apply_saved_meta(c, saved, keep_content, missing)


# ============================================================ LINK BÀI HƯỚNG DẪN
# Bài học trong LMS ứng với từng mục. Khoá là tiêu đề tiếng Anh, giống LINKS.
# Đường dẫn đọc bài: /lms/courses/<khoá>/learn/<chương>-<bài>
#   module-hrms     1 Employee Photo · 2 Leaves · 3 Shift & Attendance
#                   4 Recruitment · 5 HR Setup
#   uniform-control 1 Vận hành · 2 Thiết lập · 3 Báo cáo · 4 Tổng quan
#   helth-check-up  1 Khám sức khỏe
HRMS = "/lms/courses/module-hrms/learn/"
UNIFORM = "/lms/courses/uniform-control/learn/"
HEALTH = "/lms/courses/helth-check-up/learn/"

GUIDES = {
    # Node gốc của sơ đồ HR trỏ vào trang khoá học, không gắn từng bài cho mục con:
    # bài học hay được sắp lại, gắn lẻ là phải sửa theo liên tục.
    "HR - Human Resources": "/lms/courses/module-hrms",
    # GA gồm ba module thuộc ba khoá khác nhau nên gắn ở từng nhánh
    "Uniform Control": "/lms/courses/uniform-control",
    "Health Check-Up": "/lms/courses/helth-check-up",
    "Shoe Rack Management": "/lms/courses/module-hrms/learn/5-4",
}

# ============================================================ THỨ TỰ HIỂN THỊ
# Thứ tự theo logic nghiệp vụ: cái gì phải có trước thì đứng trước, rồi tới
# phát sinh hằng ngày, cuối cùng là báo cáo. Khoá là tiêu đề tiếng Anh của mục cha.
# Mục không liệt kê ở đây sẽ xếp sau, giữ nguyên thứ tự trong cây.
# Đổi thứ tự thì sửa ở đây rồi chạy: python3 build_mindmap.py --renumber
LOGICAL_ORDER = {
    # Thứ tự hiển thị. Phần HR sinh từ chính hr_mindmap.md nên luôn khớp file.
    "Employee Records": [
        "Organization structure", "Employment Type", "Employee profile", "Employee photo",
        "Self-service update", "Dependents", "Labor contract", "Maternity records",
        "Onboarding", "Transfer & promotion", "Resignation Application", "Employee reports",
    ],
    "Organization structure": [
        "Section & Group",
    ],
    "Transfer & promotion": [
        "Employee Transfer", "Employee Promotion", "Employee Transfer & Promotion Report",
    ],
    "Time & Attendance": [
        "Shift setup", "Fingerprint machines", "Check-in records", "Attendance calculation",
        "Corrections", "Attendance reports",
    ],
    "Shift setup": [
        "Shift type", "Assign shift", "Bulk shift assignment", "Shift priority",
    ],
    "Fingerprint machines": [
        "Connect machines", "Register fingerprints", "Push employees to machines",
        "Sync machine clock", "Check scan data",
    ],
    "Attendance calculation": [
        "Automatic daily run", "Attendance status", "Late & early leave", "Leave-linked days",
        "Anomaly note",
    ],
    "Corrections": [
        "Attendance confirmation request", "Suggested times", "Bulk create", "Signature form",
    ],
    "Attendance reports": [
        "Monthly attendance sheet", "Daily email report", "Excel export",
    ],
    "Overtime": [
        "Register overtime", "Request & approval", "Overtime reports",
    ],
    "Overtime reports": [
        "By registration", "By time slot", "By quantity", "Compliance check",
    ],
    "Leave": [
        "Leave types", "Holiday list", "Leave balance", "Leave application", "Half day leave",
        "Compensatory & encashment", "Leave reports",
    ],
    "Payroll": [
        "Payroll settings", "Salary structure", "Salary assignment", "Standard working days",
        "Vietnam statutory deductions", "Payroll run", "Payslip", "Payroll reports",
    ],
    "Vietnam statutory deductions": [
        "Insurance", "Union fee", "Personal income tax",
    ],
    "Recruitment": [
        "Staffing Plan", "Job Requisition", "Job Opening", "Job Portal", "Job Applicant",
        "Interview", "Job Offer", "Appointment Letter", "Employee Onboarding",
    ],
    "Staffing Plan": [
        "Check Vacancies On Job Offer Creation",
    ],
    "Job Applicant": [
        "Employee Referral", "Applicant status",
    ],
    "Interview": [
        "Interview Round", "Interview Type", "Interview Feedback", "Calendar & reminder",
    ],
    "Other HR functions": [
        "Performance appraisal", "Training", "Expense claim & travel",
    ],
    "HR - Human Resources": [
        "Employee Records", "Time & Attendance", "Overtime", "Leave", "Payroll", "Recruitment",
        "Other HR functions",
    ],
    "GA - General Affairs": [
        "Uniform Control", "Health Check-Up", "Shoe Rack Management",
    ],
    "Uniform Control": [
        "Initial setup", "Uniform Manager role", "Entitlement rules",
        "Employee uniform profile", "Allocation & issue", "Tracking", "Weekly reminder email",
        "Demand forecast", "Dashboard & reports", "Links to other functions",
    ],
    "Health Check-Up": [
        "Plan a session", "Exam items", "Management page", "On-site scanning",
        "Status & results", "Session Excel export", "Access control",
    ],
    "Shoe Rack Management": [
        "Rack records", "Floor layout", "Compartment assignment", "Dashboard", "Search & list",
        "Auto sync to uniform profile", "Menu shortcut",
    ],
}


def sort_logically(node, warnings, skip=()):
    order = LOGICAL_ORDER.get(node.get("en"))
    cs = node.get("children", [])
    if order and cs:
        rank = {name: i for i, name in enumerate(order)}
        names = {c.get("en") for c in cs}
        for name in order:
            if name not in names and name not in skip:
                warnings.append(
                    f"LOGICAL_ORDER['{node['en']}'] có '{name}' nhưng cây không có mục này")
        node["children"] = [
            c for _, c in sorted(enumerate(cs),
                                 key=lambda t: (rank.get(t[1].get("en"), 500 + t[0]), t[0]))
        ]
    for c in node.get("children", []):
        sort_logically(c, warnings, skip)


def assign_numbers(node, force=False):
    """Sắp các mục con theo số thứ tự đã có, rồi đánh số cho mục còn thiếu.

    Số nằm riêng ở khoá "num" nên không ảnh hưởng việc khớp mục khi build lại.
    force=True (cờ --renumber) thì đánh số lại toàn bộ theo thứ tự hiện tại.
    """
    cs = node.get("children", [])
    if not cs:
        return

    if force:
        # Đánh số lại: bỏ số cũ trong .md, lấy đúng thứ tự logic của cây
        ordered = cs
    else:
        def sort_key(item):
            i, c = item
            m = re.match(r"(\d+)", c.get("num") or "")
            return (int(m.group(1)) if m else 1000 + i, i)

        ordered = [c for _, c in sorted(enumerate(cs), key=sort_key)]
    node["children"] = ordered
    for i, c in enumerate(ordered, 1):
        if force or not c.get("num"):
            c["num"] = f"{i:02d}."
    for c in ordered:
        assign_numbers(c, force)


def md_line(node, depth, out):
    tags = ""
    if node.get("type"):
        tags += f" `[{node['type']}]`"
    if node.get("status"):
        tags += f" `[{node['status']}]`"
    desc = f" — {node['desc']}" if node.get("desc") else ""
    if node.get("guide"):
        desc += f" [Guide]({node['guide']})"
    label = node["label"]
    if node.get("link"):
        label = f"[{label}]({node['link']})"
    if node.get("num"):
        label = f"{node['num']} {label}"
    if depth == 0:
        out.append(f"# {node['label']}")
        if node.get("desc"):
            guide = f" [Guide]({node['guide']})" if node.get("guide") else ""
            out.append("")
            out.append(f"> {node['desc']}{guide}")
        out.append("")
        return
    out.append(f"{'  ' * (depth - 1)}- **{label}**{tags}{desc}")


def stats(node, acc=None):
    if acc is None:
        acc = {"total": 0, "type": {}, "status": {}}
    acc["total"] += 1
    if node.get("type"):
        acc["type"][node["type"]] = acc["type"].get(node["type"], 0) + 1
    if node.get("status"):
        base = status_base(node["status"])
        acc["status"][base] = acc["status"].get(base, 0) + 1
    for c in node.get("children", []):
        stats(c, acc)
    return acc


def collect_lang_pairs(node, pairs):
    """Thu cặp (mô tả tiếng Anh, mô tả tiếng Việt) để trang /mindmap đổi ngôn ngữ."""
    en, vi = node.get("desc_en"), node.get("desc")
    if en and vi and en != vi:
        pairs[vi] = en
    for c in node.get("children", []):
        collect_lang_pairs(c, pairs)


def write_lang_csv(trees):
    pairs = {}
    for t in trees:
        collect_lang_pairs(t, pairs)
    collect_lang_pairs(legend_branch(), pairs)

    os.makedirs(os.path.dirname(LANG_CSV), exist_ok=True)
    with open(LANG_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# english", "vietnamese"])
        for vi, en in sorted(pairs.items(), key=lambda kv: kv[1].lower()):
            w.writerow([en, vi])
    return len(pairs)


def emit(key, tree, want_json, from_script=False, renumber=False, dry_run=False,
         state=None):
    title, subtitle = HEADERS[key]
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{key}_mindmap.md")

    apply_links(tree)
    saved, newline = read_existing_meta(path)
    tree = dict(tree)
    tree["children"] = list(tree.get("children", [])) + [legend_branch()]

    # Mục đã từng có trong .md mà nay không còn = bị xoá có chủ ý, không dựng lại
    state = {} if state is None else state
    known = set(state.get(key, []))
    if not known and saved:
        # Chưa có file trạng thái nhưng .md đã tồn tại: coi như mọi mục trong script
        # đã từng xuất ra, để tôn trọng những mục đã bị xoá trong .md
        known = set(all_labels(tree))
    removed = []
    if not from_script:
        prune_removed(tree, saved, known, removed)

    added = []
    apply_saved_meta(tree, saved, not from_script, added)
    if not from_script:
        apply_root_guide(tree, saved)
    order_warnings = []
    check_duplicate_names(tree, order_warnings)
    sort_logically(tree, order_warnings, {lb.split(" / ")[0] for lb in removed})
    assign_numbers(tree, renumber)

    md = [
        f"<!-- {title} — {subtitle} -->",
        "<!-- Tạo bằng build_mindmap.py. Nội dung và phân loại sửa trong script rồi chạy lại. -->",
        "<!-- Nhãn tiến độ SỬA TRỰC TIẾP trong file này được, build lại vẫn giữ nguyên:"
        " [Done] | [In process 60%] | [Pending: lý do chưa làm] -->",
        "<!-- Xem sơ đồ trên hệ thống: /mindmap?file=" + os.path.basename(path) + " -->",
        "<!-- Hoặc dán toàn bộ file vào https://markmap.js.org/repl -->",
        "",
    ]
    walk(tree, 0, md, md_line)
    content = "\n".join(md) + "\n"
    if dry_run:
        old = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        same = old.replace("\r\n", "\n") == content.replace("\r\n", "\n")
        print(f"  [dry-run] {'giống hệt file hiện tại' if same else 'KHÁC file hiện tại'}")
        if not same:
            import difflib
            diff = list(difflib.unified_diff(
                old.replace("\r\n", "\n").split("\n"), content.split("\n"),
                "hiện tại", "sẽ ghi", lineterm="", n=0))
            for line in diff[:14]:
                print("      " + line[:150])
    else:
        with open(path, "w", encoding="utf-8", newline=newline) as f:
            f.write(content)

    if want_json:
        payload = {
            "meta": {"title": title, "subtitle": subtitle,
                     "label_format": "English / Tiếng Việt",
                     "types": list(TYPES), "statuses": list(STATUSES)},
            "root": tree,
        }
        with open(os.path.join(OUT, f"{key}_mindmap.json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    s = stats(tree)
    kept = f", giữ lại {len(saved)} mục đã sửa tay" if saved else ""
    print(f"{key}_mindmap.md: {s['total']} mục | phân loại {s['type']}"
          f" | tiến độ {s['status']}{kept}")
    for w in order_warnings:
        print(f"  ⚠ {w}")
    if removed:
        print(f"  · bỏ qua {len(removed)} mục đã xoá trong .md: "
              + ", ".join(removed[:4]) + (" ..." if len(removed) > 4 else ""))
    if added:
        print(f"  + {len(added)} mục mới từ script: "
              + ", ".join(added[:4]) + (" ..." if len(added) > 4 else ""))
    if not dry_run:
        state[key] = all_labels(tree)
    return tree


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="xuất thêm file JSON")
    ap.add_argument("--from-script", action="store_true",
                    help="lấy mô tả và link theo script, bỏ phần đã sửa tay trong .md")
    ap.add_argument("--renumber", action="store_true",
                    help="đánh số thứ tự lại toàn bộ theo thứ tự hiện tại")
    ap.add_argument("--dry-run", action="store_true",
                    help="chỉ báo cáo, không ghi file nào")
    ap.add_argument("--lang-only", action="store_true",
                    help="chỉ sinh lại bảng dịch vi.csv, không ghi file .md")
    args = ap.parse_args()
    state = load_state()
    # lang-only cũng không ghi .md: giữ nguyên phần comment người dùng tự thêm trong file
    skip_md = args.dry_run or args.lang_only
    trees = [emit("hr", HR, args.json, args.from_script, args.renumber,
                  skip_md, state),
             emit("ga", GA, args.json, args.from_script, args.renumber,
                  skip_md, state)]
    if args.dry_run:
        print("[dry-run] không ghi file nào")
        return
    if not args.lang_only:
        save_state(state)
    count = write_lang_csv(trees)
    print(f"{os.path.relpath(LANG_CSV, OUT)}: {count} cặp mô tả EN/VI")


if __name__ == "__main__":
    main()
