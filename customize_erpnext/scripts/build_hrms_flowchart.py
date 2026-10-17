#!/usr/bin/env python3
"""Sinh docs/flowchart/hrms.drawio — sơ đồ hoạt động của HRMS v16 (nhân sự).

Chạy:  python3 scripts/build_hrms_flowchart.py
Đối chiếu source mà không ghi đè file:  ... --check

Nhân sự đã tách khỏi ERPNext từ v14 nên nó là sơ đồ riêng, không nhét chung vào
erpnext.drawio. Chỗ hai bên gặp nhau là khung Accounting: phiếu lương, tạm ứng
và hoàn ứng đều đẩy sang Journal Entry / Payment Entry của ERPNext.

Các mũi tên KHÔNG viết theo trí nhớ: mỗi cái kèm một chỗ trong source HRMS đang
cài (bảng EVIDENCE), `--check` sẽ grep lại toàn bộ.

Sơ đồ này vẽ HRMS gốc, KHÔNG vẽ phần custom của TIQN (chấm công tối ưu, đăng ký
tăng ca, đồng phục...). Phần đó nằm ở docs/mindmap/hr_mindmap.md.

Phần bố cục / sinh XML / ghi tài liệu nằm ở flowchart_common.py.
"""

from flowchart_common import COL, GROUP_W, H_GAP, Flowchart, main

VERSION = "v16"
SRC = "/home/frappe/frappe-bench/apps/hrms/hrms"

# ── khung module: (id, tên, màu, cột, hàng, [(id ô, nhãn), ...]) ──────────
MODULES = [
    ("g_rec", "Recruitment", "crm", 0, 0, [
        ("jr", "Job Requisition"), ("jo", "Job Opening"), ("ja", "Job Applicant"),
        ("iv", "Interview"), ("off", "Job Offer")]),
    ("g_emp", "Employee Lifecycle", "selling", 1, 0, [
        ("onb", "Employee Onboarding"), ("emp", "Employee"),
        ("prom", "Employee Promotion"), ("tr", "Employee Transfer"),
        ("sep", "Employee Separation")]),
    ("g_att", "Shift &amp; Attendance", "stock", 2, 0, [
        ("st", "Shift Type"), ("sa", "Shift Assignment"), ("chk", "Employee Checkin"),
        ("ar", "Attendance Request"), ("att", "Attendance")]),
    ("g_leave", "Leave", "project", 3, 0, [
        ("lpa", "Leave Policy Assignment"), ("la", "Leave Allocation"),
        ("lapp", "Leave Application"), ("lle", "Leave Ledger Entry"),
        ("clr", "Compensatory Leave Request"), ("enc", "Leave Encashment")]),
    ("g_pay", "Payroll", "buying", 4, 0, [
        ("ss", "Salary Structure"), ("ssa", "Salary Structure Assignment"),
        ("pe", "Payroll Entry"), ("slip", "Salary Slip"),
        ("adds", "Additional Salary")]),
    ("g_claim", "Claims", "sub", 5, 0, [
        ("adv", "Employee Advance"), ("exp", "Expense Claim"), ("grat", "Gratuity")]),
    ("g_perf", "Performance", "mfg", 0, 1, [
        ("ac", "Appraisal Cycle"), ("appr", "Appraisal")]),
    ("g_train", "Training", "quality", 1, 1, [
        ("tp", "Training Program"), ("te", "Training Event"), ("tres", "Training Result")]),
    ("g_exit", "Exit", "support", 2, 1, [
        ("exi", "Exit Interview"), ("fnf", "Full and Final Statement")]),
    ("g_acc", "Accounting (ERPNext)", "accounts", 5, 1, [
        ("je", "Journal Entry"), ("pay", "Payment Entry"), ("gl", "General Ledger")]),
]

# ── mũi tên ───────────────────────────────────────────────────────────────
#   doc  = tạo chứng từ tiếp theo
#   data = chỉ lấy dữ liệu, không sinh chứng từ
#   gl   = ghi vào sổ cái
EDGES = [
    # tuyển dụng
    ("jr", "jo", "", "doc"), ("jo", "ja", "apply", "data"),
    ("ja", "iv", "schedule", "doc"), ("ja", "off", "", "doc"),
    ("off", "emp", "hire", "doc"), ("off", "onb", "", "data"),
    # vòng đời nhân viên
    ("onb", "emp", "", "doc"),
    ("emp", "prom", "", "doc"), ("emp", "tr", "", "doc"), ("emp", "sep", "", "doc"),
    ("emp", "exi", "", "doc"), ("emp", "fnf", "final pay", "doc"),
    # ca làm việc và chấm công
    ("st", "sa", "", "doc"), ("sa", "chk", "", "data"),
    ("chk", "att", "auto", "doc"), ("ar", "att", "", "doc"),
    ("lapp", "att", "on leave", "doc"), ("att", "slip", "payment days", "data"),
    # nghỉ phép
    ("lpa", "la", "", "doc"), ("la", "lle", "", "doc"), ("lapp", "lle", "", "doc"),
    ("clr", "la", "", "doc"), ("enc", "lle", "", "doc"), ("enc", "adds", "encashed", "doc"),
    # lương
    ("ss", "ssa", "", "doc"), ("ssa", "slip", "", "data"),
    ("pe", "slip", "run payroll", "doc"), ("adds", "slip", "", "data"),
    ("grat", "adds", "", "doc"), ("pe", "je", "salary accrual", "doc"),
    # tạm ứng, hoàn ứng
    ("adv", "exp", "adjusted", "data"), ("adv", "je", "advance paid", "doc"),
    ("exp", "pay", "reimburse", "doc"),
    # đánh giá, đào tạo
    ("ac", "appr", "", "doc"), ("tp", "te", "", "doc"), ("te", "tres", "", "doc"),
    # sổ cái
    ("exp", "gl", "", "gl"), ("je", "gl", "", "gl"), ("pay", "gl", "", "gl"),
]

# Mũi tên phải băng qua vài khung: cho chạy vòng lên dải trống trên cùng.
OVERHEAD = {
    ("att", "slip"): ("R", COL[2] + GROUP_W + H_GAP // 2, "L", COL[4] - H_GAP // 2),
}

# ── bằng chứng: mỗi mũi tên chỉ tới đúng chỗ trong source HRMS v16 ────────
# (nguồn, đích) -> (file trong apps/hrms/hrms, mẫu regex phải grep ra, nghĩa)
EVIDENCE = {
    ("jr", "jo"): ("hr/doctype/job_requisition/job_requisition.py", r"def make_job_opening",
                   "Job Requisition > Create > Job Opening"),
    ("jo", "ja"): ("hr/doctype/job_applicant/job_applicant.json", r'"options": "Job Opening"',
                   "Job Applicant trỏ về Job Opening đang tuyển"),
    ("ja", "iv"): ("hr/doctype/job_applicant/job_applicant.py", r"def create_interview",
                   "Job Applicant > Schedule Interview"),
    ("ja", "off"): ("hr/doctype/job_applicant/job_applicant.js", r'Create Job Offer',
                    "Job Applicant > Create Job Offer"),
    ("off", "emp"): ("hr/doctype/job_offer/job_offer.py", r"def make_employee",
                     "Job Offer > Create Employee"),
    ("off", "onb"): ("hr/doctype/employee_onboarding/employee_onboarding.json",
                     r'"options": "Job Offer"', "Employee Onboarding trỏ về Job Offer"),
    ("onb", "emp"): ("hr/doctype/employee_onboarding/employee_onboarding.py",
                     r"def make_employee", "Employee Onboarding > Create Employee"),
    ("emp", "prom"): ("hr/doctype/employee_promotion/employee_promotion.py",
                      r'frappe\.get_doc\("Employee"', "Promotion submit thì cập nhật Employee"),
    ("emp", "tr"): ("hr/doctype/employee_transfer/employee_transfer.py",
                    r'frappe\.get_doc\("Employee"', "Transfer submit thì cập nhật Employee"),
    ("emp", "sep"): ("hr/doctype/employee_separation/employee_separation.json",
                     r'"options": "Employee"', "Employee Separation mở theo một nhân viên"),
    ("emp", "exi"): ("hr/doctype/exit_interview/exit_interview.py", r'"employee": self\.employee',
                     "Mỗi nhân viên nghỉ việc chỉ một Exit Interview"),
    ("emp", "fnf"): ("hr/doctype/full_and_final_statement/full_and_final_statement.json",
                     r'"options": "Employee"',
                     "Full and Final Statement chốt các khoản phải trả / phải thu khi nghỉ"),
    ("st", "sa"): ("hr/doctype/shift_assignment/shift_assignment.json", r'"options": "Shift Type"',
                   "Shift Assignment gán một Shift Type cho nhân viên"),
    ("sa", "chk"): ("hr/doctype/employee_checkin/employee_checkin.py",
                    r"get_actual_start_end_datetime_of_shift",
                    "Máy chấm công vào giờ nào thì tra ca đang gán để biết thuộc ca nào"),
    ("chk", "att"): ("hr/doctype/shift_type/shift_type.py", r"mark_attendance_and_link_log",
                     "Chạy auto attendance: dữ liệu quẹt thẻ sinh bản ghi Attendance"),
    ("ar", "att"): ("hr/doctype/attendance_request/attendance_request.py",
                    r"def create_attendance_records", "Attendance Request submit thì tạo Attendance"),
    ("lapp", "att"): ("hr/doctype/leave_application/leave_application.py", r"def update_attendance",
                      "Đơn nghỉ duyệt xong đánh dấu Attendance là On Leave"),
    ("att", "slip"): ("payroll/doctype/salary_slip/salary_slip.py",
                      r'payroll_based_on == "Attendance"',
                      "Phiếu lương đếm ngày công từ Attendance (nếu cấu hình theo chấm công)"),
    ("lpa", "la"): ("hr/doctype/leave_policy_assignment/leave_policy_assignment.py",
                    r"def create_leave_allocation", "Gán chính sách nghỉ thì cấp phép cho cả kỳ"),
    ("la", "lle"): ("hr/doctype/leave_allocation/leave_allocation.py",
                    r"def create_leave_ledger_entry", "Mỗi lần cấp phép ghi một dòng sổ phép"),
    ("lapp", "lle"): ("hr/doctype/leave_application/leave_application.py",
                      r"create_leave_ledger_entry", "Đơn nghỉ trừ phép qua sổ phép"),
    ("clr", "la"): ("hr/doctype/compensatory_leave_request/compensatory_leave_request.py",
                    r"self\.create_leave_allocation", "Làm ngày nghỉ thì được cấp bù phép"),
    ("enc", "lle"): ("hr/doctype/leave_encashment/leave_encashment.py",
                     r"create_leave_ledger_entry", "Bán phép thì trừ số ngày trong sổ phép"),
    ("enc", "adds"): ("hr/doctype/leave_encashment/leave_encashment.py",
                      r'frappe\.new_doc\("Additional Salary"\)',
                      "Tiền bán phép đi vào lương qua Additional Salary"),
    ("ss", "ssa"): ("payroll/doctype/salary_structure/salary_structure.py",
                    r'frappe\.new_doc\("Salary Structure Assignment"\)',
                    "Gán thang lương cho từng nhân viên"),
    ("ssa", "slip"): ("payroll/doctype/salary_slip/salary_slip.py",
                      r"def set_salary_structure_assignment",
                      "Phiếu lương lấy thang lương đang hiệu lực của nhân viên"),
    ("pe", "slip"): ("payroll/doctype/payroll_entry/payroll_entry.py", r"def create_salary_slips",
                     "Payroll Entry tạo phiếu lương hàng loạt"),
    ("adds", "slip"): ("payroll/doctype/salary_slip/salary_slip.py", r'"Additional Salary"',
                       "Khoản cộng/trừ phát sinh được nhặt vào phiếu lương"),
    ("grat", "adds"): ("payroll/doctype/gratuity/gratuity.py",
                       r'frappe\.new_doc\("Additional Salary"\)',
                       "Trợ cấp thôi việc trả qua Additional Salary"),
    ("pe", "je"): ("payroll/doctype/payroll_entry/payroll_entry.py", r"def make_accrual_jv_entry",
                   "Payroll Entry hạch toán chi phí lương bằng Journal Entry"),
    ("adv", "exp"): ("hr/doctype/expense_claim/expense_claim.py", r"def get_advances",
                     "Hoàn ứng trừ vào khoản đã tạm ứng"),
    ("adv", "je"): ("hr/doctype/employee_advance/employee_advance.py",
                    r'frappe\.new_doc\("Journal Entry"\)', "Chi tạm ứng ghi bằng Journal Entry"),
    ("exp", "pay"): ("hr/doctype/expense_claim/expense_claim.js", r"make_payment_entry",
                     "Expense Claim > Payment: trả tiền bằng Payment Entry"),
    ("ac", "appr"): ("hr/doctype/appraisal_cycle/appraisal_cycle.py", r"def create_appraisals",
                     "Mở đợt đánh giá thì sinh phiếu đánh giá cho từng người"),
    ("tp", "te"): ("hr/doctype/training_event/training_event.json", r'"options": "Training Program"',
                   "Buổi đào tạo thuộc một chương trình"),
    ("te", "tres"): ("hr/doctype/training_event/training_event.js", r"Training Result",
                     "Training Event > Training Result: chấm kết quả sau buổi học"),
    ("exp", "gl"): ("hr/doctype/expense_claim/expense_claim.py", r"self\.make_gl_entries",
                    "Expense Claim submit thì ghi sổ cái"),
    ("je", "gl"): ("../../erpnext/erpnext/accounts/doctype/journal_entry/journal_entry.py",
                   r"make_gl_entries", "Journal Entry submit thì ghi sổ cái"),
    ("pay", "gl"): ("../../erpnext/erpnext/accounts/doctype/payment_entry/payment_entry.py",
                    r"make_gl_entries", "Payment Entry submit thì ghi sổ cái"),
}

# Có trong source v16 nhưng CỐ Ý không vẽ, để sơ đồ đủ đơn giản cho người quản lý:
OMITTED = [
    ("Staffing Plan giới hạn số lượng tuyển của Job Opening",
     "hr/doctype/job_opening/job_opening.py::validate_current_vacancies"),
    ("Appointment Letter in từ Job Applicant", "hr/doctype/appointment_letter"),
    ("Employee Referral → Job Applicant", "hr/doctype/employee_referral"),
    ("Shift Request → Shift Assignment, Shift Schedule Assignment",
     "hr/doctype/shift_request/shift_request.py"),
    ("Leave Control Panel cấp phép hàng loạt, Leave Adjustment, Leave Block List",
     "hr/doctype/leave_control_panel"),
    ("Employee Benefit Application / Claim, Employee Tax Exemption Declaration → Proof Submission",
     "payroll/doctype/employee_tax_exemption_declaration"),
    ("Payroll Entry → Payment Entry (chi lương), Salary Withholding, Payroll Correction",
     "payroll/doctype/payroll_entry/payroll_entry.py::make_payment_entry"),
    ("Employee Grievance, Daily Work Summary, Vehicle Log, Travel Request", "hr/doctype"),
    ("Toàn bộ phần custom của TIQN (chấm công tối ưu, đăng ký tăng ca, đồng phục, khám sức khoẻ)",
     "apps/customize_erpnext — xem docs/mindmap/hr_mindmap.md"),
]


CHART = Flowchart(
    key="hrms",
    app="HRMS",
    version=VERSION,
    src=SRC,
    title="HRMS %s — how the HR system works" % VERSION,
    subtitle="Employee is the master record every HR document points to; "
             "money ends up in the ERPNext General Ledger.",
    modules=MODULES,
    edges=EDGES,
    overhead=OVERHEAD,
    evidence=EVIDENCE,
    omitted=OMITTED,
    quirks=[
        "**Journal Entry / Payment Entry / General Ledger** là của ERPNext, không phải HRMS. "
        "Vẽ vào đây để thấy tiền lương và tạm ứng đi đâu.",
        "**Employee** là DocType của ERPNext (module Setup), không phải của HRMS — "
        "HRMS chỉ thêm field vào. Vẫn vẽ như trung tâm vì mọi chứng từ nhân sự trỏ về nó.",
        "**Gratuity** thuộc module Payroll, nhưng xếp chung khung Claims vì nó cũng là "
        "một khoản trả cho nhân viên.",
    ],
    legend_col=3,
    legend_w=COL[4] + GROUP_W - COL[3],
)


if __name__ == "__main__":
    raise SystemExit(main(CHART))
