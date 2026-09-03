# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Đơn nghỉ việc — thay cho việc HR sửa tay trực tiếp trên Employee.

## Vòng đời

    Draft      HR đang nhập
    Submitted  đã duyệt  -> ghi relieving_date + lý do sang Employee
    Cancelled  đã RÚT ĐƠN -> hoàn nguyên Employee

## 🔴 Ngày nghỉ còn ở TƯƠNG LAI thì duyệt đơn KHÔNG đổi `Employee.status`

`Employee.status = 'Left'` là công tắc mà cả hệ thống đang đọc — `shift_type_optimized.py` ngừng
sinh chấm công, `api/biometric_sync.py` xếp người đó vào diện xoá vân tay khỏi máy, headcount trừ
ngay. Duyệt đơn ngày 01/09 cho ngày nghỉ 30/09 mà đổi status luôn thì 29 ngày còn lại **mất công,
mất lương, mất vân tay** — trong khi người ta vẫn đang đi làm.

Nên khi ngày nghỉ còn ở tương lai, duyệt đơn chỉ ghi `relieving_date` + lý do; `status` để job
00:00 đặt đúng vào ngày nghỉ (`overrides/employee/employee.py::auto_mark_employees_as_left`).

`relieving_date` thì ghi ngay là ĐÚNG: engine chấm công đọc nó để biết mốc dừng, phép năm
prorate theo nó, và một ngày ở tương lai thì chưa chặn gì cả.

⚠ **`relieving_date` là ngày BẮT ĐẦU nghỉ việc** — ngày đầu tiên không còn đi làm, không phải
ngày làm việc cuối cùng. Toàn bộ code trong app đã hiểu như vậy: `should_mark_attendance()` trả
False khi `relieving_date <= ngày đang xét`, và bước dọn cuối của engine xoá chấm công **từ**
`relieving_date` trở đi. Hiểu lệch một ngày ở đây là lệch một công.

**Ngoại lệ — ngày nghỉ đã qua hoặc là hôm nay:** chuyển `Left` NGAY lúc submit, không đợi nửa
đêm. Lý do phải đợi ở trên không còn đúng nữa (không còn ngày công nào để mất), và bắt HR nhập
đơn lùi ngày rồi chờ tới hôm sau mới thấy đúng trạng thái là vô nghĩa.

Cả hai đường đều gọi **cùng một hàm** `employee.mark_employee_left()` để không bao giờ lệch nhau.

## Đồng bộ MỘT CHIỀU: đơn là nguồn, Employee là bản sao

Ngày nghỉ **sửa được cả sau khi duyệt** (`allow_on_submit`) vì hai bên vẫn có thể thoả thuận lại,
và mỗi lần sửa là đẩy thẳng sang Employee.

Không có chiều ngược lại. HR sửa tay `Employee.relieving_date` thì **đơn không đổi theo** — muốn
đổi ngày nghỉ thì sửa trên đơn. Có đơn trước rồi mới có ngày nghỉ trên hồ sơ.

⚠ Hệ quả phải biết: sửa tay trên Employee sẽ khiến hai bên lệch nhau **im lặng**, và lần sửa đơn
kế tiếp sẽ ghi đè lại. Hiện **chưa chặn** thao tác sửa tay đó.

## Vì sao không override `Employee Separation` của HRMS

`EmployeeBoardingController.on_submit` tạo một **Project** rồi một **Task cho mỗi activity**,
assign user/role và gửi mail; child table `Employee Boarding Activity` mang `task_weight`,
`begin_on`, `duration`. Nó cũng không đụng `relieving_date`, không đổi `status`, và **không có
khái niệm rút đơn**. Site đang có 0 record Employee Separation / 0 Template nên cũng chẳng có gì
để giữ. Override sẽ phải vô hiệu hoá gần hết hành vi của nó.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, get_link_to_form, getdate

from customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract import business_today
from customize_erpnext.overrides.employee.employee import (
	mark_employee_left,
	restore_employee_active,
)

# Field trên Employee mà đơn này ghi vào. Thứ tự không quan trọng; điều quan trọng là
# `on_cancel` chỉ xoá field nào CÒN đúng giá trị đơn này đã ghi.
HANDOVER_FIELDS = (
	"handover_id_card",
	"handover_uniform",
	"handover_shoe_rack",
	"handover_fingerprint",
	"handover_tools",
	"handover_work",
)

# 🚧 TẠM TẮT — chờ module Labor Contract hoàn thiện.
#
# BLLĐ 2019 Điều 35 đặt hai ngưỡng khác nhau: **30 ngày** với HĐ xác định thời hạn, **45 ngày**
# với HĐ không xác định thời hạn. Biết áp ngưỡng nào thì phải đọc được loại hợp đồng đang hiệu
# lực của nhân viên — đó là việc của `Labor Contract`, hiện chưa xong (hook tạo hợp đồng đầu tiên
# còn đang tắt trong `hooks.py`).
#
# Cảnh báo bằng một ngưỡng cứng 30 ngày sẽ **báo sai cho toàn bộ người ký HĐ không xác định thời
# hạn** — dạy HR bỏ qua cảnh báo, tức tệ hơn là không cảnh báo. Nên tắt hẳn cho tới khi tra được
# đúng loại hợp đồng.
#
# `notice_days` VẪN được tính và lưu (chỉ `hidden` trên form), để lúc bật lại không có khoảng
# trống dữ liệu trên các đơn nhập trong thời gian này.
NOTICE_CHECK_ENABLED = False
MIN_NOTICE_DAYS = 30

# 🚧 TẠM TẮT — đang import dữ liệu nghỉ việc cũ (21/08/2026).
#
# Site có 1.389 nhân viên đã ở trạng thái `Left`, hồ sơ giấy của họ giờ mới được nhập thành đơn.
# Chặn "đã Left rồi thì không tạo đơn nữa" là đúng cho nghiệp vụ hằng ngày nhưng chặn đúng việc
# nhập bù đó.
#
# ⚠ Bật lại sau khi import xong. Khi bật, guard vẫn **tự bỏ qua trong Data Import**
# (`frappe.flags.in_import`, đặt ở `frappe/core/doctype/data_import/importer.py:74`) — nhập bù
# lần sau không phải sửa code nữa. Nhập tay trên form thì vẫn bị chặn như thiết kế.
#
# Cái KHÔNG tắt: `validate_no_other_application` vẫn chạy, nên import hai lần cùng một người vẫn
# bị chặn. Đó mới là thứ giữ cho lô import không sinh trùng.
BLOCK_ALREADY_LEFT = False

# Đơn lập SAU ngày nghỉ bao nhiêu ngày thì vẫn chấp nhận (chỉ cảnh báo).
#
# Vì sao không chặn: nghỉ ngang là chuyện thường ở xưởng — người ta thôi đến làm, HR chờ một hai
# hôm rồi mới ra quyết định. Ngày nghỉ có trước, giấy tờ có sau. Đo trên file import thật của HR:
# **125/1.387 dòng** rơi vào diện này, trong đó 68 dòng trễ đúng 1 ngày và 101 dòng trễ ≤ 2 ngày;
# xa nhất 14 ngày. Nhóm này lệch hẳn về lý do — dẫn đầu là "Không phù hợp với môi trường làm
# việc" (31%), có cả "Tự ý bỏ việc" và "Nghỉ quá 5 ngày không phép".
#
# Bản đầu `throw` thẳng, chặn đúng 125 dòng đó và chặn luôn ca hai bên thoả thuận lùi ngày nghỉ
# về trước hôm nhận đơn.
#
# Vì sao vẫn giữ một mốc chặn: bỏ hẳn là mất khả năng bắt gõ nhầm năm (nhận đơn 2026, nghỉ 2025).
# 30 ngày phủ trọn dữ liệu thật mà vẫn bắt được loại sai đó.
MAX_LATE_LETTER_DAYS = 30


class ResignationApplication(Document):
	# ------------------------------------------------------------------ naming
	# def autoname(self):
	# 	"""`RA-YYYY-MM-#####`, YYYY-MM lấy từ `resignation_letter_date`.

	# 	Không dùng naming series `.YYYY.`/`.MM.`: chúng lấy theo **ngày chạy**, nên đơn nhận
	# 	tháng 3 mà nhập vào tháng 8 sẽ mang số tháng 8 — sai với cách HR tra cứu.

	# 	⚠ Số phát ra ngay khi lưu lần đầu. Sửa `resignation_letter_date` sau đó KHÔNG đổi tên bản ghi
	# 	(Frappe không đổi tên khi save lại) — đó là lý do field có description nhắc sửa trước
	# 	khi lưu.

	# 	🔴 Bộ đếm nằm ở `tabSeries` với tiền tố `RA-YYYY-MM-`. Mất dòng đó là phát lại từ 00001
	# 	và đụng tên đã tồn tại (`DuplicateEntryError`) — cùng cái bẫy đã xảy ra với Leave
	# 	Application, xem `scripts/repair_leave_application_series.sql`.
	# 	"""
	# 	from frappe.model.naming import make_autoname

	# 	d = getdate(self.resignation_letter_date or business_today())
	# 	self.name = make_autoname(f"RA-{d.year:04d}-{d.month:02d}-.#####")

	# ---------------------------------------------------------------- validate
	def validate(self):
		self.set_notice_days()
		self.set_handover_progress()
		self.validate_dates()
		self.validate_reason()
		self.validate_employee_state()
		self.validate_no_other_application()
		if NOTICE_CHECK_ENABLED:
			self.warn_short_notice()

	def set_notice_days(self):
		if self.resignation_letter_date and self.relieving_date:
			self.notice_days = date_diff(self.relieving_date, self.resignation_letter_date)
		else:
			self.notice_days = 0

	def set_handover_progress(self):
		done = sum(1 for f in HANDOVER_FIELDS if self.get(f))
		self.handover_progress = f"{done}/{len(HANDOVER_FIELDS)}"

	def validate_dates(self):
		# `<` chứ không `<=`: **nghỉ đúng ngày vào làm là có thật** — người vào làm rồi bỏ ngay
		# hôm đó. Đo trên file import của HR: 3 hồ sơ như vậy (TIQN-1502, TIQN-1531, TIQN-1997).
		# Cũng khớp với core: `Employee.validate_date` dùng `validate_from_to_dates` vốn cho phép
		# hai ngày bằng nhau.
		if self.date_of_joining and getdate(self.relieving_date) < getdate(self.date_of_joining):
			frappe.throw(
				_("Relieving Date cannot be before Date of Joining ({0}).").format(
					frappe.format(self.date_of_joining, {"fieldtype": "Date"})
				),
				title=_("Invalid Relieving Date"),
			)

		late = date_diff(self.resignation_letter_date, self.relieving_date)
		if late > MAX_LATE_LETTER_DAYS:
			frappe.throw(
				_("Resignation Letter Date is {0} days after the Relieving Date. More than {1} days apart is almost always a typo — check the year.").format(
					late, MAX_LATE_LETTER_DAYS
				),
				title=_("Invalid Dates"),
			)
		elif late > 0:
			# Nghỉ ngang: ngày nghỉ có trước, quyết định có sau. Hợp lệ, chỉ nhắc để HR nhìn lại.
			frappe.msgprint(
				_("Resignation Letter Date is {0} day(s) after the Relieving Date.").format(late),
				title=_("Letter Dated After Leaving"),
				indicator="orange",
			)

	def validate_reason(self):
		"""Chốt chặn server-side. JS chỉ *lọc hiển thị*, không phải bảo đảm.

		Đổi `reason_for_leaving_group` sau khi đã chọn `reason_for_leaving_group_2` là ra cặp lệch nhau — JS có xoá ô con nhưng
		Data Import và API thì không đi qua JS.
		"""
		group = frappe.db.get_value(
			"Resignation Reason Group 2", self.reason_for_leaving_group_2, "reason_for_leaving_group"
		)
		if group and group != self.reason_for_leaving_group:
			frappe.throw(
				_("Reason {0} belongs to group {1}, not {2}.").format(
					frappe.bold(self.reason_for_leaving_group_2), frappe.bold(group), frappe.bold(self.reason_for_leaving_group)
				),
				title=_("Reason Does Not Match Group"),
			)

	def validate_employee_state(self):
		"""Không cho tạo đơn cho người đã `Left`. Xem `BLOCK_ALREADY_LEFT` — đang TẮT."""
		if not BLOCK_ALREADY_LEFT or frappe.flags.in_import:
			return

		status = frappe.db.get_value("Employee", self.employee, "status")
		if status == "Left":
			frappe.throw(
				_("Employee {0} is already marked as Left.").format(frappe.bold(self.employee)),
				title=_("Employee Already Left"),
			)

	def validate_no_other_application(self):
		other = frappe.db.get_value(
			"Resignation Application",
			{"employee": self.employee, "docstatus": 1, "name": ("!=", self.name)},
			"name",
		)
		if other:
			frappe.throw(
				_("Employee {0} already has a submitted resignation: {1}. Withdraw it first.").format(
					frappe.bold(self.employee), get_link_to_form("Resignation Application", other)
				),
				title=_("Duplicate Resignation"),
			)

	def warn_short_notice(self):
		"""🚧 Chưa được gọi — xem `NOTICE_CHECK_ENABLED`.

		Khi bật lại: thay `MIN_NOTICE_DAYS` cứng bằng ngưỡng tra từ loại hợp đồng đang hiệu lực
		(`Labor Contract.contract_type`), 30 hay 45 ngày tuỳ HĐ có xác định thời hạn hay không.
		"""
		if self.notice_days is not None and 0 <= self.notice_days < MIN_NOTICE_DAYS:
			frappe.msgprint(
				_("Notice period is {0} day(s), less than the {1} days required by Labour Code 2019 Article 35.").format(
					self.notice_days, MIN_NOTICE_DAYS
				),
				title=_("Short Notice"),
				indicator="orange",
			)

	# ------------------------------------------------------------------ submit
	def on_submit(self):
		sync_to_employee(self)

	# ------------------------------------------------- sửa sau khi đã duyệt
	def before_update_after_submit(self):
		"""Ngày nghỉ đổi sau khi duyệt -> validate lại + tính lại field dẫn xuất.

		⚠ Frappe **không** chạy `validate()` trên đường update-after-submit, chỉ chạy
		`before_update_after_submit` / `on_update_after_submit`. Không lặp lại phần kiểm ở đây thì
		sửa ngày sau khi duyệt sẽ đi thẳng vào DB mà không qua một kiểm tra nào.
		"""
		self.set_notice_days()
		self.set_handover_progress()
		self.validate_dates()

	def on_update_after_submit(self):
		sync_to_employee(self)

	def on_cancel(self):
		"""Cancel = **rút đơn**."""
		if not self.withdrawal_date:
			self.withdrawal_date = business_today()
			self.db_set("withdrawal_date", self.withdrawal_date, update_modified=False)
		revert_employee(self)


# =============================================================================
# Đồng bộ sang Employee
#
# Dùng `frappe.db.set_value`, KHÔNG `doc.save()`: save Employee xoá cache toàn site và chạy
# `update_user_status` (disable User). Cả hai đều không thuộc về việc duyệt một lá đơn cho ngày
# nghỉ còn ở tương lai. Việc disable User để job 00:00 làm, đúng lúc người ta thật sự nghỉ.
#
# Mẫu lấy từ `employee_maternity/employee_status_sync.py`.
# =============================================================================

def _employee_values(doc) -> dict:
	"""Field trên Employee mà đơn này làm chủ.

	`resignation_letter_date` là field CÓ SẴN của core Employee, ý nghĩa trùng khít với
	`resignation_letter_date` của đơn (ngày nhận đơn xin nghỉ) — nên map thẳng vào đó thay vì khai thêm một
	custom field nữa. HRMS `Employee Separation` cũng dùng đúng tên này.

	⚠ Danh sách này được `revert_employee()` dùng lại để hoàn nguyên khi rút đơn, và nó chỉ xoá
	field nào CÒN đúng giá trị đơn đã ghi. Thêm field vào đây là tự động có cả hai chiều.
	"""
	return {
		"resignation_letter_date": doc.resignation_letter_date,
		"relieving_date": doc.relieving_date,
		"custom_reason_for_leaving_group": doc.reason_for_leaving_group,
		"custom_reason_for_leaving_group_2": doc.reason_for_leaving_group_2,
		"reason_for_leaving": doc.reason_detail or doc.reason_for_leaving_group_2,
	}


def sync_to_employee(doc):
	values = _employee_values(doc)
	frappe.db.set_value("Employee", doc.employee, values)

	note = _("Resignation {0} submitted — leaving from {1}").format(
		doc.name, frappe.format(doc.relieving_date, {"fieldtype": "Date"})
	)

	extra = _reconcile_status(doc)
	if extra:
		note += " — " + extra

	_breadcrumb(doc.employee, note)


def _reconcile_status(doc) -> str:
	"""Giữ bất biến: **`status = Left` ⟺ ngày nghỉ đã tới**.

	Đối chiếu theo CẢ HAI hướng, vì ngày nghỉ sửa được sau khi duyệt:

	  · ngày đã tới mà còn `Active` -> chuyển `Left` ngay, không đợi job 00:00
	  · ngày lùi ra tương lai mà đang `Left` -> **mở lại `Active`**

	Hướng thứ hai là lý do phải có hàm này. Người đã bị đánh `Left` hôm 20/08, rồi hai bên thoả
	thuận lại lùi sang 05/09 — không mở lại thì 16 ngày còn đi làm đó **không sinh chấm công**
	(`shift_type_optimized` bỏ qua NV `Left`) và họ nằm trong diện xoá vân tay khỏi máy.

	`<=` chứ không `<`: `relieving_date` là ngày ĐẦU TIÊN không còn đi làm, nên đúng hôm đó người
	ta đã nghỉ rồi.
	"""
	if getdate(doc.relieving_date) <= getdate(business_today()):
		result = mark_employee_left(doc.employee)
		if result["ok"]:
			return _("marked as Left")

		# Còn cấp dưới Active: việc HR phải xử lý, không phải lỗi kỹ thuật. Đơn vẫn lưu được
		# (relieving_date + lý do đã ghi); job 00:00 sẽ thử lại mỗi đêm.
		frappe.msgprint(
			_("Employee not marked as Left yet: {0} employee(s) still report to them ({1}). Reassign them, then the nightly job will finish this.").format(
				len(result["reports_to_self"]), ", ".join(result["reports_to_self"][:5])
			),
			title=_("Still Has Subordinates"),
			indicator="orange",
		)
		return _("still has subordinates, status unchanged")

	if frappe.db.get_value("Employee", doc.employee, "status") == "Left":
		restore_employee_active(doc.employee)
		return _("leaving date moved to the future, reopened as Active")

	return ""


def revert_employee(doc):
	"""Hoàn nguyên Employee khi rút đơn.

	⚠ Chỉ xoá field nào **còn đúng giá trị đơn này đã ghi**. Nếu HR đã sửa tay hoặc một đơn mới
	hơn đã ghi đè, xoá mù sẽ thổi bay dữ liệu của người khác.
	"""
	written = _employee_values(doc)
	current = frappe.db.get_value("Employee", doc.employee, list(written) + ["status"], as_dict=True)
	if not current:
		return  # nhân viên đã bị xoá

	to_clear = {k: None for k, v in written.items() if _same(current.get(k), v)}

	reverted = sorted(to_clear)

	if to_clear:
		frappe.db.set_value("Employee", doc.employee, to_clear)

	# Đã bị đánh Left (bởi job 00:00 hoặc bởi chính lúc submit đơn lùi ngày) -> mở lại.
	# `restore_employee_active` mở khoá luôn tài khoản User, nếu không thì người ta đi làm lại
	# mà không đăng nhập được và chẳng có gì báo vì sao.
	if current.status == "Left":
		restore_employee_active(doc.employee)
		reverted.append("status")

	if not reverted:
		return

	_breadcrumb(
		doc.employee,
		_("Resignation {0} withdrawn on {1} — reverted {2}").format(
			doc.name,
			frappe.format(doc.withdrawal_date, {"fieldtype": "Date"}),
			", ".join(reverted),
		),
	)


def _same(a, b) -> bool:
	"""So khớp giá trị Employee với giá trị đơn đã ghi, bỏ qua khác biệt date/str."""
	if a is None or b is None:
		return a == b
	if isinstance(a, str) and isinstance(b, str):
		return a.strip() == b.strip()
	try:
		return getdate(a) == getdate(b)
	except Exception:
		return str(a) == str(b)


def _breadcrumb(employee: str, content: str):
	"""Ghi Comment lên Employee.

	Field lifecycle đổi mà không có nguyên nhân nhìn thấy được thì sau này không ai truy ra —
	cùng lý do với `employee_status_sync._set_employee_status`.
	"""
	try:
		frappe.get_doc({
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": "Employee",
			"reference_name": employee,
			"content": content,
		}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Resignation Application: comment failed")


# =============================================================================
# Nút Withdraw
# =============================================================================

@frappe.whitelist()
def withdraw(name: str, withdrawal_date: str, withdrawal_reason: str | None = None):
	"""Ghi ngày/lý do rút rồi cancel đơn.

	Phải là một hàm server: hộp thoại Cancel mặc định của Frappe không hỏi được hai field này,
	và ghi bằng `set_value` từ client rồi cancel sau là hai request tách rời — nửa chừng lỗi thì
	đơn mang ngày rút mà vẫn đang submitted.
	"""
	doc = frappe.get_doc("Resignation Application", name)
	doc.check_permission("cancel")

	if doc.docstatus != 1:
		frappe.throw(_("Only a submitted application can be withdrawn."))

	doc.db_set("withdrawal_date", getdate(withdrawal_date), update_modified=False)
	doc.db_set("withdrawal_reason", withdrawal_reason, update_modified=False)
	doc.reload()
	doc.cancel()
	return doc.name
