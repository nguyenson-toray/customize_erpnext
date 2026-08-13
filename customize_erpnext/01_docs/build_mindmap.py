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

OUT = os.path.dirname(os.path.abspath(__file__))
LANG_CSV = os.path.realpath(os.path.join(OUT, "..", "www", "mindmap", "vi.csv"))

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

    g("Employee Records", "Hồ sơ nhân viên", None, [
        n("Employee profile", "Thông tin nhân viên",
          ("Personal details, department, designation, joining date and employment status",
           "Thông tin cá nhân, phòng ban, chức danh, ngày vào làm, trạng thái làm việc"),
          tag="Override"),
        n("Organization structure", "Cơ cấu tổ chức",
          ("Company, department, designation and employee grade",
           "Công ty, phòng ban, chức danh, bậc lương"), tag="Standard", children=[
            n("Section & Group", "Bộ phận & Nhóm",
              ("Splits a department into sections and groups for finer attendance and reporting",
               "Chia nhỏ phòng ban thành bộ phận và nhóm để chấm công, báo cáo chi tiết hơn"),
              tag="Custom"),
        ]),
        n("Employee photo", "Ảnh nhân viên",
          ("Upload photos, remove the background, crop to ID-photo ratio,"
           " process many photos at once",
           "Tải ảnh, xóa nền, cắt ảnh thẻ đúng tỷ lệ, xử lý nhiều ảnh một lượt"),
          tag="Custom"),
        n("Self-service update", "Nhân viên tự cập nhật thông tin",
          ("Employees submit their own details on a dedicated page, HR reviews then applies them",
           "Nhân viên tự khai thông tin qua trang riêng, HR kiểm tra rồi cập nhật vào hồ sơ"),
          tag="Custom"),
        n("Dependents", "Người phụ thuộc",
          ("Declare dependents used for personal income tax relief",
           "Khai người phụ thuộc để tính giảm trừ thuế thu nhập cá nhân"), tag="Custom"),
        n("Labor contract", "Hợp đồng lao động",
          ("Contract type, duration and tracking of contracts due for renewal",
           "Loại hợp đồng, thời hạn, theo dõi hợp đồng sắp hết hạn cần tái ký"), tag="Custom"),
        n("Employment Type", "Loại hình lao động",
          ("Employment types such as permanent, seasonal and probation,"
           " with tracking of probation end dates",
           "Loại hình lao động: chính thức, thời vụ, thử việc;"
           " theo dõi ngày kết thúc thử việc"), tag="Custom"),
        n("External personnel", "Nhân sự ngoài công ty",
          ("Visitors and contractors who are off payroll but still need to be managed",
           "Khách, nhà thầu, người ngoài bảng lương nhưng vẫn cần quản lý"), tag="Custom"),
        n("Maternity records", "Thai sản",
          ("Tracks the maternity milestones of each employee, used for attendance,"
           " leave and benefit calculation",
           "Theo dõi các mốc thời gian liên quan thai sản của nhân viên,"
           " dùng để tính toán công phép, chế độ"), tag="Custom"),
        n("Joining & leaving", "Tiếp nhận & nghỉ việc",
          ("Onboarding, transfers, promotions and the resignation process",
           "Tiếp nhận nhân viên mới, chuyển bộ phận, thăng chức, thủ tục thôi việc"),
          tag="Standard"),
        n("Employee reports", "Báo cáo nhân sự",
          ("Headcount lists, age structure, years of service and workforce movement",
           "Danh sách nhân sự, cơ cấu theo độ tuổi, thâm niên, biến động nhân sự"),
          tag="Override"),
    ]),

    g("Time & Attendance", "Chấm công", None, [
        n("Fingerprint machines", "Máy chấm công vân tay", None, tag="Custom", children=[
            n("Connect machines", "Kết nối máy",
              ("Register each device and pull scan data into the system automatically",
               "Khai báo máy chấm công, lấy dữ liệu quét về hệ thống tự động"), tag="Custom"),
            n("Register fingerprints", "Đăng ký vân tay",
              ("Enroll fingerprints and check whether the sample quality is acceptable",
               "Đăng ký vân tay cho nhân viên, xem chất lượng mẫu vân tay đạt hay chưa"),
              tag="Custom"),
            n("Push employees to machines", "Đưa nhân viên xuống máy",
              ("Sync the employee list and fingerprints down to each device",
               "Đồng bộ danh sách nhân viên và vân tay xuống từng máy"), tag="Custom"),
            n("Sync machine clock", "Đồng bộ giờ máy",
              ("A device with the wrong clock corrupts every in and out time, so check it regularly",
               "Máy sai giờ sẽ làm sai toàn bộ giờ vào ra, cần kiểm tra định kỳ"), tag="Custom"),
            n("Check scan data", "Kiểm tra dữ liệu quét",
              ("Review scan logs and pull data again when something is missing",
               "Xem log quét, lấy lại dữ liệu khi phát hiện thiếu"), tag="Custom"),
        ]),
        n("Check-in records", "Dữ liệu quét vào - ra",
          ("Every scan is one record and is the basis for calculating attendance",
           "Mỗi lần nhân viên quét là một dòng dữ liệu, là cơ sở để tính công"), tag="Override"),
        g("Shift setup", "Thiết lập ca làm việc", None, [
            n("Shift definition", "Khai báo ca",
              ("Start time, end time, lunch break and the allowed late / early margin",
               "Giờ vào, giờ ra, giờ nghỉ trưa, mức dung sai trễ - về sớm"), tag="Override"),
            n("Assign shift", "Phân ca",
              ("Assign a shift to an employee for a date range",
               "Phân ca cho nhân viên theo khoảng thời gian"), tag="Standard"),
            n("Bulk shift assignment", "Phân ca hàng loạt",
              ("Pick many employees and assign the shift in one go instead of one by one",
               "Chọn nhiều nhân viên và phân ca cùng lúc thay vì làm từng người"), tag="Custom"),
            n("Shift priority", "Thứ tự xác định ca",
              ("Specific assignment first, then the employee default shift, then the shift of the day",
               "Ưu tiên phân ca riêng, sau đó ca mặc định của nhân viên, cuối cùng ca theo ngày"),
              tag="Override"),
        ]),
        n("Attendance calculation", "Tính công tự động", None, tag="Override", children=[
            n("Automatic daily run", "Chạy tự động hằng ngày",
              ("The system turns raw scans into attendance days with no manual work",
               "Hệ thống ghép các lần quét thành ngày công, không cần làm tay"), tag="Override"),
            n("Attendance status", "Trạng thái ngày công",
              ("Present, absent, half day, day off and public holiday",
               "Có mặt, vắng, nửa ngày, ngày nghỉ, ngày lễ"), tag="Standard"),
            n("Late & early leave", "Trễ giờ & về sớm",
              ("Records minutes late or minutes left early against the shift margin",
               "Ghi nhận số phút trễ hoặc về sớm theo dung sai của ca"), tag="Standard"),
            n("Leave-linked days", "Ngày công theo đơn phép",
              ("Days with an approved leave or a holiday are matched automatically, never marked absent",
               "Ngày đã có đơn phép hoặc ngày lễ được khớp tự động, không tính vắng"),
              tag="Override"),
            n("Paid holidays", "Ngày lễ vẫn tính công",
              ("Public holidays are paid leave, so they still count as working days",
               "Ngày lễ nhà nước là nghỉ có lương nên vẫn được tính vào ngày công"),
              tag="Override"),
            n("Anomaly note", "Ghi chú bất thường",
              ("Missing or odd scans are flagged with a note for HR to check and fix by hand",
               "Quét thiếu hoặc quét lẻ được ghi chú lại để HR kiểm tra và xử lý tay"),
              tag="Custom"),
        ]),
        n("Corrections", "Điều chỉnh công",
          ("Fix a single day or update many records at once after reconciliation",
           "Sửa công từng ngày hoặc cập nhật hàng loạt sau khi đối chiếu"), tag="Override"),
        g("Attendance reports", "Báo cáo chấm công", None, [
            n("Monthly attendance sheet", "Bảng công tháng",
              ("Detailed attendance by shift, used for reconciliation and payroll",
               "Bảng công chi tiết theo ca, dùng để đối chiếu và tính lương"), tag="Custom"),
            n("Daily email report", "Báo cáo gửi email hằng ngày",
              ("The system emails yesterday's attendance report to the people in charge",
               "Hệ thống tự gửi báo cáo công của ngày hôm trước cho người phụ trách"),
              tag="Custom"),
            n("Excel export", "Xuất Excel",
              ("A multi-sheet Excel file for checking against data kept outside the system",
               "Bản Excel nhiều sheet để đối chiếu với dữ liệu ngoài hệ thống"), tag="Custom"),
            n("HR overview dashboard", "Bảng điều khiển tổng quan HR",
              ("Headcount and attendance figures summarised on a single page",
               "Số liệu nhân sự và chấm công tổng hợp trên một trang"), tag="Custom"),
        ]),
    ]),

    n("Overtime", "Tăng ca", None, tag="Custom", children=[
        n("Register overtime", "Đăng ký tăng ca",
          ("Pick the date, pick employees, enter overtime start and end time",
           "Chọn ngày, chọn nhân viên, khai giờ bắt đầu và giờ kết thúc tăng ca"), tag="Custom"),
        n("Employee picker", "Chọn nhân viên",
          ("Filter by department and group, and see total man-hours update as you add people",
           "Lọc theo bộ phận và nhóm, thấy ngay tổng giờ công khi chọn thêm người"),
          tag="Custom"),
        n("Overtime levels", "Bậc tăng ca",
          ("Overtime rates for normal days, Sundays and public holidays",
           "Hệ số tăng ca cho ngày thường, chủ nhật và ngày lễ"), tag="Custom"),
        n("Request & approval", "Yêu cầu & phê duyệt",
          ("The department requests, the manager approves before it counts",
           "Bộ phận đề xuất, cấp trên phê duyệt trước khi tính công"), tag="Custom"),
        g("Overtime reports", "Báo cáo tăng ca", None, [
            n("By registration", "Theo phiếu đăng ký",
              ("Overtime slips and the hours booked on each of them",
               "Danh sách phiếu tăng ca và số giờ theo từng phiếu"), tag="Custom"),
            n("By time slot", "Theo khung giờ",
              ("Headcount and hours of overtime per time slot of the day",
               "Số người và số giờ tăng ca theo từng khung giờ trong ngày"), tag="Custom"),
            n("By quantity", "Theo số lượng",
              ("Total overtime hours by department and by period",
               "Tổng hợp số giờ tăng ca theo bộ phận và theo kỳ"), tag="Custom"),
            n("Compliance check", "Kiểm tra tuân thủ",
              ("Warns when overtime exceeds the statutory hour limits",
               "Cảnh báo khi vượt giới hạn giờ tăng ca theo quy định"), tag="Custom"),
        ]),
    ]),

    g("Leave", "Nghỉ phép", None, [
        n("Leave types", "Loại phép",
          ("Annual leave, unpaid leave, sick leave, maternity leave and compensatory leave",
           "Phép năm, nghỉ không lương, nghỉ ốm, thai sản, nghỉ bù"), tag="Standard"),
        n("Leave balance", "Số dư phép",
          ("Opening allocation plus leave earned month by month",
           "Phân bổ phép đầu kỳ và phép tích lũy theo từng tháng làm việc"), tag="Override"),
        n("Leave application", "Đơn xin nghỉ phép",
          ("The employee applies, the manager approves, attendance follows the application",
           "Nhân viên tạo đơn, người quản lý phê duyệt, công được cập nhật theo đơn"),
          tag="Override"),
        n("Half day leave", "Nghỉ nửa ngày",
          ("Half a day of annual leave still counts as a full working day",
           "Nghỉ nửa ngày phép vẫn được tính đủ công cho ngày đó"), tag="Override"),
        n("Import leave from Excel", "Nhập phép từ Excel",
          ("Import leave already taken from a file, used when migrating from the old system",
           "Nhập dữ liệu phép đã sử dụng từ file, dùng khi chuyển từ hệ thống cũ"),
          tag="Custom"),
        n("Holiday list", "Lịch nghỉ lễ",
          ("Public holidays and days off in lieu for each year",
           "Danh sách ngày lễ và ngày nghỉ bù áp dụng cho từng năm"), tag="Standard"),
        n("Compensatory & encashment", "Nghỉ bù & thanh toán phép",
          ("Time off in lieu for extra days worked, and payment for unused leave",
           "Nghỉ bù cho ngày làm thêm và thanh toán phép chưa dùng"), tag="Standard"),
        n("Leave reports", "Báo cáo phép",
          ("Leave balance per employee and leave history by period",
           "Số dư phép từng nhân viên và lịch sử nghỉ theo kỳ"), tag="Standard"),
    ]),

    g("Payroll", "Tiền lương", None, [
        n("Salary structure", "Cơ cấu lương",
          ("Basic salary, allowances and deductions",
           "Lương cơ bản, các khoản phụ cấp và các khoản trừ"), tag="Standard"),
        n("Salary assignment", "Gán lương cho nhân viên",
          ("Assign a salary from an effective date, with bulk import from Excel",
           "Gán mức lương theo ngày hiệu lực, có thể nhập hàng loạt từ Excel"), tag="Override"),
        n("Payroll run", "Chạy bảng lương",
          ("Run payroll for a period and generate payslips for all employees",
           "Chạy theo kỳ lương, sinh phiếu lương cho toàn bộ nhân viên"), tag="Standard"),
        n("Standard working days", "Ngày công chuẩn",
          ("Days in the period minus Sundays; public holidays still count as paid days",
           "Số ngày trong kỳ trừ các ngày chủ nhật, ngày lễ vẫn được tính công"),
          tag="Override"),
        n("Vietnam statutory deductions", "Khấu trừ theo luật Việt Nam", None,
          tag="Override", children=[
            n("Insurance", "Bảo hiểm",
              ("Social insurance, health insurance and unemployment insurance",
               "Bảo hiểm xã hội, bảo hiểm y tế và bảo hiểm thất nghiệp"), tag="Override"),
            n("Union fee", "Đoàn phí",
              ("Trade union fee deducted at the prescribed rate",
               "Trừ đoàn phí công đoàn theo tỷ lệ quy định"), tag="Override"),
            n("Personal income tax", "Thuế thu nhập cá nhân",
              ("Calculated by tax bracket with personal and dependent relief",
               "Tính theo bậc thuế, có giảm trừ bản thân và người phụ thuộc"), tag="Override"),
        ]),
        n("Payroll settings", "Cấu hình lương",
          ("Insurance rates, tax brackets and relief amounts, updated when the law changes",
           "Tỷ lệ bảo hiểm, bậc thuế, mức giảm trừ, cập nhật khi quy định thay đổi"),
          tag="Custom"),
        n("Payslip", "Phiếu lương",
          ("View and print payslips, with the amount spelled out in Vietnamese words",
           "Xem và in phiếu lương, số tiền được ghi bằng chữ tiếng Việt"), tag="Override"),
        n("Payroll reports", "Báo cáo lương",
          ("Salary register, bank payment list and tax summaries",
           "Bảng lương tổng hợp, danh sách chi trả qua ngân hàng, tổng hợp thuế"),
          tag="Standard"),
        n("Loans & advances", "Khoản vay & tạm ứng",
          ("Track loans and advances and deduct them from salary over time",
           "Theo dõi khoản vay và tạm ứng, trừ dần vào lương hằng kỳ"), tag="Standard"),
    ]),

    g("Other HR functions", "Chức năng HR khác",
      ("Mostly used as delivered, not yet tailored to the company",
       "Phần lớn đang dùng theo bản chuẩn, chưa điều chỉnh riêng cho công ty"), [
        n("Recruitment", "Tuyển dụng",
          ("Hiring needs, job openings, applicants, interviews and offer letters",
           "Nhu cầu tuyển, tin tuyển dụng, ứng viên, phỏng vấn, thư mời nhận việc"),
          tag="Standard"),
        n("Online job application", "Ứng tuyển trực tuyến",
          ("A web application form candidates fill in and submit themselves",
           "Mẫu ứng tuyển trên web, ứng viên tự điền và gửi hồ sơ"), tag="Custom"),
        n("Performance appraisal", "Đánh giá hiệu suất",
          ("Appraisal cycles, goals, appraisal criteria and feedback",
           "Kỳ đánh giá, mục tiêu, tiêu chí đánh giá và phản hồi"), tag="Standard"),
        n("Training", "Đào tạo",
          ("Training programs, sessions, results and learner feedback",
           "Chương trình đào tạo, buổi đào tạo, kết quả và phản hồi của người học"),
          tag="Standard"),
        n("Expense claim & travel", "Hoàn ứng & công tác",
          ("Expense claims, employee advances and travel requests",
           "Đề nghị thanh toán chi phí, tạm ứng và yêu cầu đi công tác"), tag="Standard"),
    ]),

    g("System & Access", "Hệ thống & phân quyền", None, [
        n("Roles & permissions", "Vai trò & phân quyền",
          ("Role-based access so each person only sees data within their scope",
           "Phân quyền theo vai trò để mỗi người chỉ thấy dữ liệu thuộc phạm vi của mình"),
          tag="Standard"),
        n("Email alerts", "Cảnh báo qua email",
          ("Alerts are OFF by default; the administrator must choose recipients before enabling",
           "Cảnh báo mặc định để TẮT, người quản trị phải chọn người nhận trước khi bật"),
          tag="Override"),
        n("Vietnamese interface", "Giao diện tiếng Việt",
          ("Each user picks their own display language",
           "Mỗi người dùng chọn ngôn ngữ hiển thị riêng"), tag="Custom"),
        n("Excel & CSV export", "Xuất Excel & CSV",
          ("Download data to a file that opens with Vietnamese characters intact",
           "Tải dữ liệu ra file, mở lên hiển thị đúng dấu tiếng Việt"), tag="Override"),
        n("Menu & shortcuts", "Menu & lối tắt",
          ("Functions grouped into workspaces, with shortcuts on the home page",
           "Nhóm chức năng theo khu vực làm việc và tạo lối tắt trên trang chủ"), tag="Custom"),
    ]),
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
        n("Excel export", "Xuất Excel",
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
    # ── HR: hồ sơ nhân viên
    "Employee profile": "/desk/employee",
    "Organization structure": "/desk/department",
    "Section & Group": "/desk/section",
    "Employee photo": "/employee-photos",
    "Self-service update": "/employee-self-update-info",
    "Dependents": "/desk/employee-dependent",
    "Labor contract": "/desk/query-report/Labor%20Contract%20Report",
    "Employment Type": "/desk/employment-type",
    "External personnel": "/desk/external-personnel",
    "Maternity records": "/desk/query-report/Employee%20Maternity%20Report",
    "Joining & leaving": "/desk/employee-onboarding",
    "Employee reports": "/desk/employee/view/report",

    # ── HR: chấm công
    "Fingerprint machines": "/desk/attendance-machine-setting",
    "Connect machines": "/desk/attendance-machine-setting",
    "Register fingerprints": "/desk/fingerprint-data",
    "Push employees to machines": "/biometric_sync",
    "Sync machine clock": "/desk/attendance-machine-setting",
    "Check scan data": "/desk/employee-checkin/view/report",
    "Check-in records": "/desk/employee-checkin",
    "Shift definition": "/desk/shift-type",
    "Assign shift": "/desk/shift-assignment",
    "Bulk shift assignment": "/desk/shift-assignment",
    "Shift priority": "/desk/shift-type",
    "Attendance calculation": "/desk/attendance",
    "Automatic daily run": "/desk/shift-type",
    "Attendance status": "/desk/attendance/view/report",
    "Late & early leave": "/desk/attendance/view/report",
    "Leave-linked days": "/desk/attendance",
    "Paid holidays": "/desk/holiday-list",
    "Anomaly note": "/desk/attendance/view/report",
    "Corrections": "/desk/attendance",
    "Monthly attendance sheet": "/desk/query-report/Shift%20Attendance%20Customize",
    "Daily email report": "/desk/query-report/Shift%20Attendance%20Customize",
    "Excel export": "/desk/query-report/Shift%20Attendance%20Customize",
    "HR overview dashboard": "/desk/hr",

    # ── HR: tăng ca
    "Overtime": "/desk/overtime-registration",
    "Register overtime": "/desk/overtime-registration",
    "Employee picker": "/desk/overtime-registration/new",
    "Overtime levels": "/desk/overtime-level",
    "Request & approval": "/desk/overtime-request",
    "By registration": "/desk/query-report/Overtime%20Registration",
    "By time slot": "/desk/query-report/Overtime%20Registration%20by%20Time%20Slot",
    "By quantity": "/desk/query-report/Overtime%20Registration%20Quantity",
    "Compliance check": "/desk/query-report/OT%20Compliance",

    # ── HR: nghỉ phép
    "Leave types": "/desk/leave-type",
    "Leave balance": "/desk/leave-allocation",
    "Leave application": "/desk/leave-application",
    "Half day leave": "/desk/leave-application",
    "Import leave from Excel": "/desk/data-import",
    "Holiday list": "/desk/holiday-list",
    "Compensatory & encashment": "/desk/compensatory-leave-request",
    "Leave reports": "/desk/query-report/Employee%20Leave%20Balance",

    # ── HR: tiền lương
    "Salary structure": "/desk/salary-structure",
    "Salary assignment": "/desk/salary-structure-assignment",
    "Payroll run": "/desk/payroll-entry",
    "Standard working days": "/desk/salary-slip",
    "Vietnam statutory deductions": "/desk/tiqn-payroll-settings",
    "Insurance": "/desk/tiqn-insurance-rate",
    "Union fee": "/desk/tiqn-payroll-settings",
    "Personal income tax": "/desk/tiqn-tax-bracket",
    "Payroll settings": "/desk/tiqn-payroll-settings",
    "Payslip": "/desk/salary-slip",
    "Payroll reports": "/desk/query-report/Salary%20Register",
    "Loans & advances": "/desk/employee-advance",

    # ── HR: chức năng khác
    "Recruitment": "/desk/job-opening",
    "Online job application": "/jobs",
    "Performance appraisal": "/desk/appraisal",
    "Training": "/desk/training-program",
    "Expense claim & travel": "/desk/expense-claim",

    # ── HR: hệ thống
    "Roles & permissions": "/desk/role",
    "Email alerts": "/desk/notification",
    "Vietnamese interface": "/desk/user",
    "Excel & CSV export": "/desk/data-export",
    "Menu & shortcuts": "/desk/workspace",

    # ── GA: đồng phục
    "Uniform Control": "/desk/uniform-dashboard",
    "Uniform warehouse & items": "/desk/uniform-setting",
    "Default items": "/desk/uniform-setting",
    "Alert settings": "/desk/uniform-setting",
    "Attrition assumption": "/desk/uniform-setting",
    "Who gets what": "/desk/uniform-rule",
    "Quantity & cycle": "/desk/uniform-rule",
    "One-time items": "/desk/uniform-rule",
    "Rule priority": "/desk/uniform-rule",
    "Sizes": "/desk/employee-uniform-profile",
    "Shoe rack location": "/desk/employee-uniform-profile",
    "Next due date": "/desk/employee-uniform-profile",
    "Manual override": "/desk/employee-uniform-profile",
    "Issued history": "/desk/query-report/Uniform%20Tracking",
    "Find eligible employees": "/desk/uniform-allocation/new",
    "Create & confirm slip": "/desk/uniform-allocation",
    "Warehouse issue": "/desk/stock-entry",
    "Reuse old items": "/desk/uniform-allocation",
    "Item reissue": "/desk/query-report/Employee%20Item%20Reissue",
    "Due & overdue list": "/desk/query-report/Uniform%20Tracking",
    "Recalculate": "/desk/uniform-dashboard",
    "Forecast by period": "/desk/uniform-demand-forecast",
    "Size ratio": "/desk/uniform-demand-forecast",
    "Leavers estimate": "/desk/uniform-demand-forecast",
    "Shortfall vs stock": "/desk/uniform-demand-forecast",
    "Summary dashboard": "/desk/uniform-dashboard",
    "Stock report": "/desk/uniform-dashboard",
    "Due employees report": "/desk/query-report/Uniform%20Tracking",
    "Allocation history report": "/desk/uniform-allocation/view/report",
    "Cost report": "/desk/uniform-dashboard",
    "Weekly reminder email": "/desk/uniform-setting",
    "Uniform Manager role": "/desk/role/Uniform%20Manager",
    "Links to other functions": "/desk/employee-uniform-profile",

    # ── GA: khám sức khỏe
    "Health Check-Up": "/desk/health-check-up-management",
    "Date & hospital": "/desk/health-check-up",
    "Check-up type": "/desk/health-check-up",
    "Employee list": "/desk/health-check-up/view/report",
    "Planned time slot": "/desk/health-check-up-management",
    "Reschedule": "/desk/health-check-up-management",
    "X-ray": "/desk/health-check-up/view/report",
    "Gynecological exam": "/desk/health-check-up/view/report",
    "Pregnancy exclusion": "/desk/health-check-up/view/report",
    "Not attending": "/desk/health-check-up/view/report",
    "Scan to hand out form": "/desk/health-check-up-management",
    "Scan to collect form": "/desk/health-check-up-management",
    "Employee code lookup": "/desk/health-check-up-management",
    "Works offline": "/desk/health-check-up-management",
    "Status per employee": "/desk/health-check-up/view/report",
    "Recalculate status": "/desk/health-check-up-management",
    "Attach result files": "/desk/health-check-up-management",
    "Result & note": "/desk/health-check-up",
    "Management page": "/desk/health-check-up-management",
    "Access control": "/desk/role",

    # ── GA: kệ giày
    "Shoe Rack Management": "/desk/shoe-rack-dashboard",
    "Rack name & type": "/desk/shoe-rack",
    "Compartments": "/desk/shoe-rack",
    "Rack status": "/desk/shoe-rack/view/report",
    "Assign to employee": "/desk/shoe-rack",
    "Assign to external personnel": "/desk/external-personnel",
    "Unidentified user": "/desk/shoe-rack/view/report",
    "Gender per compartment": "/desk/shoe-rack/view/report",
    "Layout manager": "/desk/layout-manager",
    "Pathways": "/desk/layout-manager",
    "Save layout": "/desk/shoe-rack-layout-settings",
    "Dashboard": "/desk/shoe-rack-dashboard",
    "Search & list": "/desk/shoe-rack",
    "Auto sync to uniform profile": "/desk/employee-uniform-profile",
    "Menu shortcut": "/desk/workspace",
}


def apply_links(node):
    link = LINKS.get(node.get("en"))
    if link:
        node["link"] = link
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
    r"(?:\s*(?:—|–|--)\s*(?P<desc>.*?))?\s*$"
)
TAG_RE = re.compile(r"`\[([^\]]+)\]`")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]*)\)")
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

        m = LINE_RE.match(line)
        if not m:
            continue

        raw_label = m.group("label")
        link_match = MD_LINK_RE.search(raw_label)
        # Tiêu đề có thể được bọc thành link markdown, bỏ phần link để khớp đúng mục
        label = MD_LINK_RE.sub(r"\1", raw_label).strip()
        # Số thứ tự tự đánh không tính vào khoá khớp, nhưng phải giữ lại
        num, label = split_order(label)
        entry = found.setdefault(label, {})
        if num:
            entry["num"] = num
        if link_match:
            entry["link"] = link_match.group(2).strip()
        if m.group("desc"):
            entry["desc"] = m.group("desc").strip()
        for t in TAG_RE.findall(m.group("tags")):
            canon, value = parse_status_tag(t)
            if canon:
                entry["status"] = format_status(canon, value)

    return found, newline


def walk(node, depth, out, fn):
    fn(node, depth, out)
    for c in node.get("children", []):
        walk(c, depth + 1, out, fn)


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
            if entry.get("desc") and node.get("desc") and entry["desc"] != node["desc"]:
                node["desc"] = entry["desc"]
                node.pop("desc_en", None)   # mô tả đã đổi, bản dịch cũ không còn đúng
            if entry.get("link"):
                node["link"] = entry["link"]
    for c in node.get("children", []):
        apply_saved_meta(c, saved, keep_content, missing)


# ============================================================ THỨ TỰ HIỂN THỊ
# Thứ tự theo logic nghiệp vụ: cái gì phải có trước thì đứng trước, rồi tới
# phát sinh hằng ngày, cuối cùng là báo cáo. Khoá là tiêu đề tiếng Anh của mục cha.
# Mục không liệt kê ở đây sẽ xếp sau, giữ nguyên thứ tự trong cây.
# Đổi thứ tự thì sửa ở đây rồi chạy: python3 build_mindmap.py --renumber
LOGICAL_ORDER = {
    "HR - Human Resources": [
        "Employee Records", "Time & Attendance", "Overtime", "Leave", "Payroll",
        "Other HR functions", "System & Access",
    ],
    # Cơ cấu và loại hình lao động phải khai trước khi lập hồ sơ nhân viên
    "Employee Records": [
        "Organization structure", "Employment Type", "Employee profile", "Employee photo",
        "Self-service update", "Dependents", "Labor contract", "External personnel",
        "Maternity records", "Joining & leaving", "Employee reports",
    ],
    # Khai ca trước, rồi thiết bị thu dữ liệu, rồi mới tính công được
    "Time & Attendance": [
        "Shift setup", "Fingerprint machines", "Check-in records",
        "Attendance calculation", "Corrections", "Attendance reports",
    ],
    "Overtime": [
        "Overtime levels", "Register overtime", "Employee picker",
        "Request & approval", "Overtime reports",
    ],
    "Leave": [
        "Leave types", "Holiday list", "Leave balance", "Leave application",
        "Half day leave", "Compensatory & encashment", "Import leave from Excel",
        "Leave reports",
    ],
    # Cấu hình tỷ lệ bảo hiểm và bậc thuế phải có trước khi chạy lương
    "Payroll": [
        "Payroll settings", "Salary structure", "Salary assignment",
        "Standard working days", "Vietnam statutory deductions", "Payroll run",
        "Payslip", "Loans & advances", "Payroll reports",
    ],
    "Other HR functions": [
        "Recruitment", "Online job application", "Performance appraisal",
        "Training", "Expense claim & travel",
    ],
    "System & Access": [
        "Roles & permissions", "Menu & shortcuts", "Vietnamese interface",
        "Excel & CSV export", "Email alerts",
    ],
    "GA - General Affairs": [
        "Uniform Control", "Health Check-Up", "Shoe Rack Management",
    ],
    # Thiết lập và định mức trước, cấp phát sau, cuối cùng là dự báo và báo cáo
    "Uniform Control": [
        "Initial setup", "Uniform Manager role", "Entitlement rules",
        "Employee uniform profile", "Allocation & issue", "Tracking",
        "Weekly reminder email", "Demand forecast", "Dashboard & reports",
        "Links to other functions",
    ],
    "Health Check-Up": [
        "Plan a session", "Exam items", "Management page", "On-site scanning",
        "Status & results", "Excel export", "Access control",
    ],
    # Khai kệ, vẽ sơ đồ mặt bằng, rồi mới gán ô cho từng người
    "Shoe Rack Management": [
        "Rack records", "Floor layout", "Compartment assignment", "Dashboard",
        "Search & list", "Auto sync to uniform profile", "Menu shortcut",
    ],
}


def sort_logically(node, warnings):
    order = LOGICAL_ORDER.get(node.get("en"))
    cs = node.get("children", [])
    if order and cs:
        rank = {name: i for i, name in enumerate(order)}
        names = {c.get("en") for c in cs}
        for name in order:
            if name not in names:
                warnings.append(f"LOGICAL_ORDER['{node['en']}'] có '{name}' nhưng cây không có mục này")
        node["children"] = [
            c for _, c in sorted(enumerate(cs),
                                 key=lambda t: (rank.get(t[1].get("en"), 500 + t[0]), t[0]))
        ]
    for c in node.get("children", []):
        sort_logically(c, warnings)


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
    label = node["label"]
    if node.get("link"):
        label = f"[{label}]({node['link']})"
    if node.get("num"):
        label = f"{node['num']} {label}"
    if depth == 0:
        out.append(f"# {node['label']}")
        if node.get("desc"):
            out.append("")
            out.append(f"> {node['desc']}")
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


def emit(key, tree, want_json, from_script=False, renumber=False):
    title, subtitle = HEADERS[key]
    path = os.path.join(OUT, f"{key}_mindmap.md")

    apply_links(tree)
    saved, newline = read_existing_meta(path)
    missing = []
    apply_saved_meta(tree, saved, not from_script, missing)
    tree = dict(tree)
    tree["children"] = list(tree.get("children", [])) + [legend_branch()]
    order_warnings = []
    sort_logically(tree, order_warnings)
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
    with open(path, "w", encoding="utf-8", newline=newline) as f:
        f.write("\n".join(md) + "\n")

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
    if missing:
        print(f"  ⚠ {len(missing)} mục có trong script nhưng không thấy trong .md"
              " (bị xoá hoặc đang comment lại) — build đã thêm lại:")
        for label in missing[:8]:
            print(f"      · {label}")
        if len(missing) > 8:
            print(f"      · ... và {len(missing) - 8} mục nữa")
    return tree


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="xuất thêm file JSON")
    ap.add_argument("--from-script", action="store_true",
                    help="lấy mô tả và link theo script, bỏ phần đã sửa tay trong .md")
    ap.add_argument("--renumber", action="store_true",
                    help="đánh số thứ tự lại toàn bộ theo thứ tự hiện tại")
    args = ap.parse_args()
    trees = [emit("hr", HR, args.json, args.from_script, args.renumber),
             emit("ga", GA, args.json, args.from_script, args.renumber)]
    count = write_lang_csv(trees)
    print(f"{os.path.relpath(LANG_CSV, OUT)}: {count} cặp mô tả EN/VI")


if __name__ == "__main__":
    main()
