# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from dateutil.relativedelta import relativedelta
from frappe import _
from frappe.utils import (
	add_days,
	add_months,
	date_diff,
	get_first_day,
	get_first_day_of_week,
	get_last_day,
	get_last_day_of_week,
	getdate,
	nowdate,
)

from customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract import (
	APPENDIX,
	CONTRACT_1_YEAR,
	CONTRACT_3_YEAR,
	CONTRACT_INDEFINITE,
	business_today,
	positions_at,
)

# Who may download personal data (ID card, address, phone) for drafting
# contracts. The report itself is also open to Department/Factory Managers.
EXPORT_ROLES = ("HR Manager", "HR User", "System Manager")

# BLLĐ 2019 Điều 20 khoản 2: a fixed-term contract that expired while the employee keeps
# working must be followed by a new contract within 30 days, otherwise it becomes an
# indefinite-term contract. Unsigned documents past this many days are flagged.
OVERDUE_LEGAL_DAYS = 30

# Stages that follow a fixed-term contract — leaving these unsigned past 30 days is
# exactly the case above (the 1-year after probation is not).
RENEWS_FIXED_TERM = (CONTRACT_3_YEAR, CONTRACT_INDEFINITE)

UNSIGNED = ("Upcoming", "Overdue")
NOT_CREATED = "Not Created"

# Two words, two sides of a renewal (user review 22/10/2026):
#   Expiring / Days Left   — the contract IN FORCE, counted to its End Date (future)
#   Overdue / Days Overdue — the NEW document not signed yet, counted from the day it
#                            should have taken effect (past). Covers both an unsigned
#                            document and an expired contract whose follow-up was never
#                            created — the legal 30 days run either way.


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, None, get_summary(data)


def get_summary(data):
	late = [r for r in data if (r.days_overdue or 0) > OVERDUE_LEGAL_DAYS]
	return [{
		"label": _("Overdue > {0} Days").format(OVERDUE_LEGAL_DAYS),
		"value": len(late),
		"indicator": "Red" if late else "Green",
		"datatype": "Int",
	}, {
		"label": _("Of which renew a fixed-term contract"),
		"value": sum(1 for r in late if r.legal_risk),
		"indicator": "Red" if any(r.legal_risk for r in late) else "Green",
		"datatype": "Int",
	}]


def get_columns():
	return [
		{"fieldname": "name", "label": _("ID"), "fieldtype": "Link",
		 "options": "Labor Contract", "width": 170},
		{"fieldname": "document_type", "label": _("Document Type"), "fieldtype": "Data",
		 "width": 100},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link",
		 "options": "Employee", "width": 110},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data",
		 "width": 190},
		{"fieldname": "designation", "label": _("Designation"), "fieldtype": "Link",
		 "options": "Designation", "width": 150},
		{"fieldname": "custom_section", "label": _("Section"), "fieldtype": "Link",
		 "options": "Section", "width": 120},
		{"fieldname": "custom_group", "label": _("Group"), "fieldtype": "Link",
		 "options": "Group", "width": 120},
		{"fieldname": "contract_type", "label": _("Contract Type"), "fieldtype": "Link",
		 "options": "Employment Type", "width": 220},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "start_date", "label": _("Start Date"), "fieldtype": "Date",
		 "width": 105},
		{"fieldname": "end_date", "label": _("End Date"), "fieldtype": "Date",
		 "width": 105},
		{"fieldname": "days_left", "label": _("Days Left"), "fieldtype": "Int",
		 "width": 90},
		{"fieldname": "days_overdue", "label": _("Days Overdue"), "fieldtype": "Int",
		 "width": 105},
		{"fieldname": "next_contract_type", "label": _("Next Contract Type"),
		 "fieldtype": "Link", "options": "Employment Type", "width": 200},
		{"fieldname": "next_sign_date", "label": _("Next Sign Date"), "fieldtype": "Date",
		 "width": 115},
		{"fieldname": "next_contract_status", "label": _("Next Contract Status"),
		 "fieldtype": "Data", "width": 130},
		{"fieldname": "signed_on", "label": _("Signed On"), "fieldtype": "Date",
		 "width": 105},
		{"fieldname": "parent_contract", "label": _("Parent Contract"), "fieldtype": "Link",
		 "options": "Labor Contract", "width": 150},
		{"fieldname": "relieving_date", "label": _("Relieving Date"), "fieldtype": "Date",
		 "width": 115},
	]


def _expiring_range(filters, today):
	"""(from, to) for the "Expiring" preset, matched against end_date."""
	preset = filters.get("expiring")
	# Calendar weeks; the first day follows System Settings (Monday on this site)
	if preset == "This Week":
		return get_first_day_of_week(today), get_last_day_of_week(today)
	if preset == "Next Week":
		next_week = add_days(today, 7)
		return get_first_day_of_week(next_week), get_last_day_of_week(next_week)
	if preset == "This Month":
		return get_first_day(today), get_last_day(today)
	if preset == "Next Month":
		next_month = add_months(today, 1)
		return get_first_day(next_month), get_last_day(next_month)
	if preset == "Next 30 Days":
		return today, add_days(today, 30)
	if preset == "Next 60 Days":
		return today, add_days(today, 60)
	if preset == "Custom":
		return filters.get("from_date"), filters.get("to_date")
	return None, None


def _build_conditions(filters):
	today = getdate(business_today())
	conditions = []
	values = {"today": today}

	for field in ("employee", "status", "contract_type", "document_type"):
		if filters.get(field):
			conditions.append(f"lc.{field} = %({field})s")
			values[field] = filters[field]

	# The employee's latest contract that has started — one row per employee. That is
	# the contract in force today, or, when it ran out and nothing follows it, the
	# expired one (so a missed renewal still shows up). Someone who already left
	# (relieving_date = first day off) is out. An unchecked Check filter is not sent
	# at all, so test truthiness.
	if filters.get("current_only"):
		conditions.append(
			"lc.document_type = 'Contract' AND lc.start_date <= %(today)s"
			" AND (emp.relieving_date IS NULL OR emp.relieving_date > %(today)s)"
			" AND NOT EXISTS (SELECT 1 FROM `tabLabor Contract` later"
			"  WHERE later.employee = lc.employee AND later.document_type = 'Contract'"
			"  AND later.start_date <= %(today)s"
			"  AND (later.start_date > lc.start_date"
			"   OR (later.start_date = lc.start_date AND later.creation > lc.creation)))"
		)

	from_date, to_date = _expiring_range(filters, today)
	if from_date:
		conditions.append("lc.end_date >= %(expiring_from)s")
		values["expiring_from"] = from_date
	if to_date:
		conditions.append("lc.end_date <= %(expiring_to)s")
		values["expiring_to"] = to_date

	where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
	return where, values


def _with_positions(rows, filters):
	"""Designation / section / group on the document's start date (Internal Work
	History), then the Section / Group filters — they can't be SQL conditions since
	the values aren't stored on the document."""
	for row, position in zip(rows, positions_at([(r.employee, r.start_date) for r in rows])):
		row.update(position)
	for field in ("custom_section", "custom_group"):
		if filters.get(field):
			rows = [r for r in rows if r.get(field) == filters[field]]
	return rows


def get_data(filters):
	where, values = _build_conditions(filters)
	today = values["today"]

	rows = frappe.db.sql(
		f"""
		SELECT
			lc.name, lc.document_type, lc.employee, lc.employee_name, lc.contract_type,
			lc.status, lc.start_date, lc.end_date, lc.signed_on, lc.parent_contract,
			lc.next_contract_type, lc.next_sign_date, emp.relieving_date,
			et.custom_warning_before AS warning_before,
			-- the follow-up contract, if it was created: the first one starting after this
			-- (not an exact next_sign_date match — a hand-corrected date must not make it
			-- look missing); the latest when that stage was re-signed
			IF(lc.document_type = 'Contract',
				(SELECT nx.status FROM `tabLabor Contract` nx
				 WHERE nx.employee = lc.employee AND nx.document_type = 'Contract'
				   AND nx.start_date > lc.start_date
				 ORDER BY nx.start_date, nx.creation DESC LIMIT 1),
				NULL) AS next_status
		FROM `tabLabor Contract` lc
		INNER JOIN `tabEmployee` emp ON emp.name = lc.employee
		LEFT JOIN `tabEmployment Type` et ON et.name = lc.contract_type
		{where}
		ORDER BY lc.end_date IS NULL, lc.end_date, lc.employee, lc.start_date
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		_add_signing_state(row, today)
	if filters.get("overdue_30"):
		rows = [r for r in rows if (r.days_overdue or 0) > OVERDUE_LEGAL_DAYS]
	return _with_positions(rows, filters)


def _add_signing_state(row, today):
	"""days_left / next_contract_status / days_overdue / legal_risk of one row."""
	working = not row.relieving_date or getdate(row.relieving_date) > today
	# relieving_date = first day off: leaving on/before the next sign date means there
	# is no next contract to sign
	row.leaves_before_next = int(bool(
		row.relieving_date and row.next_sign_date
		and getdate(row.relieving_date) <= getdate(row.next_sign_date)
	))
	needs_next = bool(row.next_contract_type) and not row.leaves_before_next

	# "Not Created" only once it is due — inside the warning window or past the end;
	# before that the follow-up simply isn't expected yet (the daily job creates it)
	due = bool(row.end_date) and date_diff(row.end_date, today) <= (row.warning_before or 0)
	row.next_contract_status = (
		row.next_status or (NOT_CREATED if due else None)
	) if needs_next else None

	# Counted to the End Date while the contract runs; after it, only while nothing
	# follows it — otherwise every past stage of the chain shows a large negative number
	row.days_left = None
	if row.end_date and working and (getdate(row.end_date) >= today or not row.next_status):
		row.days_left = date_diff(row.end_date, today)

	row.days_overdue = None
	risk_type = None
	if working and row.status in UNSIGNED and getdate(row.start_date) < today:
		row.days_overdue = date_diff(today, row.start_date)
		risk_type = row.contract_type
	elif working and needs_next and not row.next_status and getdate(row.next_sign_date) < today:
		# expired with no follow-up created: late from the day the next one should start
		row.days_overdue = date_diff(today, row.next_sign_date)
		risk_type = row.next_contract_type

	row.legal_risk = int((row.days_overdue or 0) > OVERDUE_LEGAL_DAYS and risk_type in RENEWS_FIXED_TERM)


# =============================================================================
# "Export Contract Data" button — one row per document (contract or appendix) in
# HR's mail-merge layout (user decision 22/10/2026: HR's tracking workbook is the
# format, minus "Đc cũ"; one sheet for both kinds of document).
# =============================================================================
# Header text is copied character for character from HR's workbook — Word mail-merge
# fields bind to it, so it must not be translated or tidied up (the line breaks in
# the allowance headers are part of the names).

SALARY_HEADERS = [
	"Lương hàng tháng/ Total", "Số tiền bằng số", "Amount",
	"Lương CB\nTV", "Kỹ thuật\nTV", "Chức vụ\nTV", "Nhà ở\nTV", "PC xe\nTV", "Pc điện thoại\nTV",
	"Fire prevention and fighting allowance/Phụ cấp phòng cháy và chữa cháy:\nTV",
	"Safety and hygiene allowance/Phụ cấp an toàn vệ sinh viên:\nTV",
	"Supporting stages allowance/Phụ cấp hỗ trợ công đoạn:\nTV",
	"Chuyên cần\nTV", "Trách nhiệm\nTV", "Hiệu suất", "Tổng cộng",
	"Lương CB", "Kỹ thuật", "Chức vụ", "Nhà ở", "PC xe", "Pc điện thoại",
	"Fire prevention and fighting allowance/Phụ cấp phòng cháy và chữa cháy:",
	"Safety and hygiene allowance/Phụ cấp an toàn vệ sinh viên:",
	"Supporting stages allowance/Phụ cấp hỗ trợ công đoạn:",
	"Chuyên cần", "Trách nhiệm", "Hiệu suất", "Tổng cộng", "Sum", "Lương cũ",
	"So sánh lương CT và TV",
]

EXPORT_HEADERS = [
	"STT", "MSNV", "Loại", "Số PL/HĐ gần nhất", "Số HĐ", "Tên", "Name", "Mã hợp đồng",
	"Thời gian HĐ (tháng)", "Ngày sinh use", "Ngày sinh", "DOB use", "SDT", "F/M", "Ông/bà",
	"Mr/Ms", "Giới tính", "Gender", "Số CM", "Cấp ngày", "Cấp tại", "Cấp ngày use", "ID",
	"Issued", "At", "Address", "Địa chỉ", "HD từ use", "HD đến use", "HD từ", "HD đến",
	"From use", "To use", "Position currently", "Vị trí HT", "New position", "Vị trí mới",
	*SALARY_HEADERS,
	"Ngày hiệu lực", "Ngày hiệu lực V", "Ngày hiệu lực E", "Kỳ lương", "Kỳ lương E",
	"Kỳ lương V", "Thâm niên", "Số thứ tự HĐ tham chiếu", "Số HD tham chiếu",
	"Ngày của Số HD tham chiếu raw", "Ngày của Số HD/PL tham chiếu TV",
	"Ngày của Số HD/PL tham chiếu E", "Thay đổi", "Tình trạng thông tin", "Đợt", "Ngày pv",
	"Còn làm việc không", "Ngày join", "Ngày hết thử việc",
]

# "Số PL/HĐ gần nhất" / "Mã hợp đồng" / "Thời gian HĐ (tháng)" per stage, as HR fills
# them: HD1 → 1 / 1 / 12, HD2 → 2 / 2 / 36, HD3 → 3 / 3 / (none). Probation: blank.
STAGE_NUMBER = {CONTRACT_1_YEAR: 1, CONTRACT_3_YEAR: 2, CONTRACT_INDEFINITE: 3}
STAGE_MONTHS = {CONTRACT_1_YEAR: 12, CONTRACT_3_YEAR: 36}

# "At" = place of issue in English; the two authority names on the ID card form have
# fixed translations (HR's workbook), anything else (a province) stays as typed.
PLACE_OF_ISSUE_EN = {
	"cục cảnh sát quản lý hành chính về trật tự xã hội":
		"Police Department for Administrative Management of Social Order",
	"bộ công an": "Ministry of Public Security",
}

MONTHS_EN = [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
]

# Payroll period runs from the 26th to the 25th and is named after the month it
# ends in: an appendix effective on 26/05 starts with the June period.
PAYROLL_PERIOD_START_DAY = 26


def _dmy(value):
	return getdate(value).strftime("%d/%m/%Y") if value else ""


def _long_en(value):
	"""26 May 2026 — month names spelled out here, strftime("%B") follows the locale."""
	if not value:
		return ""
	value = getdate(value)
	return f"{value.day:02d} {MONTHS_EN[value.month - 1]} {value.year}"


def _real_date(value):
	return getdate(value) if value else ""


def _payroll_period(effective):
	effective = getdate(effective)
	first = get_first_day(effective)
	return add_months(first, 1) if effective.day >= PAYROLL_PERIOD_START_DAY else first


def _yymm_number(value):
	"""Appendix "Số PL/HĐ gần nhất" = YYMM of the effective date as a number (2410)."""
	return int(getdate(value).strftime("%y%m"))


def _seniority(date_of_joining, on_date):
	if not (date_of_joining and on_date):
		return ""
	delta = relativedelta(getdate(on_date), getdate(date_of_joining))
	return f"{delta.years} năm {delta.months} tháng {delta.days} ngày"


def _gender_cells(gender):
	if gender == "Female":
		return ["F", "Bà", "Ms", "Nữ", "Female"]
	if gender == "Male":
		return ["M", "Ông", "Mr", "Nam", "Male"]
	return ["", "", "", "", gender or ""]


def _still_working(row, today):
	return 1 if row.emp_status == "Active" and (
		not row.relieving_date or getdate(row.relieving_date) > today
	) else 0


@frappe.whitelist()
def export_contract_data(filters=None):
	"""Excel of the documents matching the report's current filters, in HR's
	mail-merge layout. Salary columns stay empty until the salary part is built."""
	frappe.only_for(EXPORT_ROLES)
	from frappe.utils.xlsxutils import make_xlsx

	from customize_erpnext.overrides.employee.employee_address import no_diacritics

	filters = frappe._dict(frappe.parse_json(filters) if isinstance(filters, str) else (filters or {}))
	where, values = _build_conditions(filters)
	today = getdate(business_today())

	rows = frappe.db.sql(
		f"""
		SELECT
			lc.name, lc.document_type, lc.employee, lc.contract_type, lc.start_date,
			lc.end_date, lc.change_type, lc.parent_contract,
			pc.contract_type AS parent_contract_type, pc.start_date AS parent_start_date,
			emp.employee_name, emp.date_of_birth, emp.cell_number, emp.gender,
			emp.custom_id_card_no, emp.custom_id_card_date_of_issue,
			emp.custom_id_card_place_of_issue, emp.permanent_address,
			emp.custom_permanent_address_full, emp.status AS emp_status, emp.relieving_date,
			emp.date_of_joining, emp.custom_finish_probation_contract
		FROM `tabLabor Contract` lc
		INNER JOIN `tabEmployee` emp ON emp.name = lc.employee
		LEFT JOIN `tabLabor Contract` pc ON pc.name = lc.parent_contract
		{where}
		ORDER BY lc.start_date, lc.employee, lc.name
		""",
		values,
		as_dict=True,
	)
	rows = _with_positions(rows, filters)

	# Appendix: "Position currently" = the day before it takes effect, "New position" =
	# on the effective date (only when it actually changed).
	before = positions_at([
		(r.employee, add_days(r.start_date, -1)) if r.document_type == APPENDIX else (None, None)
		for r in rows
	])
	designations = {
		d.name: d.custom_designation_vn
		for d in frappe.get_all("Designation", fields=["name", "custom_designation_vn"])
	}

	data = [EXPORT_HEADERS]
	for stt, (row, prior) in enumerate(zip(rows, before), start=1):
		is_appendix = row.document_type == APPENDIX
		stage_type = row.parent_contract_type if is_appendix else row.contract_type

		if is_appendix:
			number = _yymm_number(row.start_date)
			current_position = prior.designation
			new_position = row.designation if row.designation != prior.designation else None
		else:
			number = STAGE_NUMBER.get(row.contract_type, "")
			current_position = row.designation
			new_position = None

		place = row.custom_id_card_place_of_issue or ""
		contract_dates = (not is_appendix) and row.start_date
		effective = row.start_date if is_appendix else None
		period = _payroll_period(effective) if effective else None

		data.append([
			stt,
			row.employee,
			"PL" if is_appendix else "HD",
			number,
			row.name,
			row.employee_name or "",
			no_diacritics(row.employee_name or ""),
			STAGE_NUMBER.get(stage_type, ""),
			STAGE_MONTHS.get(stage_type, ""),
			_dmy(row.date_of_birth),
			_real_date(row.date_of_birth),
			_long_en(row.date_of_birth),
			row.cell_number or "",
			*_gender_cells(row.gender),
			row.custom_id_card_no or "",
			_real_date(row.custom_id_card_date_of_issue),
			place,
			_dmy(row.custom_id_card_date_of_issue),
			row.custom_id_card_no or "",
			_long_en(row.custom_id_card_date_of_issue),
			PLACE_OF_ISSUE_EN.get(place.strip().lower(), place),
			row.permanent_address or "",
			row.custom_permanent_address_full or "",
			_dmy(row.start_date) if contract_dates else "",
			_dmy(row.end_date) if contract_dates else "",
			_real_date(row.start_date) if contract_dates else "",
			_real_date(row.end_date) if contract_dates else "",
			_long_en(row.start_date) if contract_dates else "",
			_long_en(row.end_date) if contract_dates else "",
			current_position or "",
			designations.get(current_position) or "",
			new_position or "",
			designations.get(new_position) or "",
			*([""] * len(SALARY_HEADERS)),
			_real_date(effective),
			_dmy(effective),
			_long_en(effective),
			_real_date(period),
			f"{MONTHS_EN[period.month - 1][:3]} {period.year}" if period else "",
			f"{period.month:02d}/{period.year}" if period else "",
			_seniority(row.date_of_joining, effective) if effective else "",
			STAGE_NUMBER.get(row.parent_contract_type, "") if is_appendix else "",
			row.parent_contract or "",
			_real_date(row.parent_start_date) if is_appendix else "",
			_dmy(row.parent_start_date) if is_appendix else "",
			_long_en(row.parent_start_date) if is_appendix else "",
			row.change_type or "",
			"", "", "",
			_still_working(row, today),
			_real_date(row.date_of_joining),
			_real_date(row.custom_finish_probation_contract),
		])

	xlsx = make_xlsx(data, "Labor Contracts")
	frappe.response["filename"] = f"Labor_Contract_Data_{nowdate()}.xlsx"
	frappe.response["filecontent"] = xlsx.getvalue()
	frappe.response["type"] = "binary"

