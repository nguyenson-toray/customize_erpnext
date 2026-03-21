"""
Employee Onboarding API

Public APIs (allow_guest=True) — dùng cho web page self-service:
  get_eligible_employees  → Danh sách nhân viên có thể điền form
  get_onboarding_config   → Feature flags từ Employee Onboarding Settings
  verify_phone            → Xác thực 2 số cuối SĐT / 2 số ngày sinh
  get_onboarding_form     → Lấy dữ liệu form đã điền
  save_onboarding_form    → Tạo mới / cập nhật form
  upload_cccd_photo       → Upload ảnh CCCD lên Frappe files

HR APIs (require login):
  approve_onboarding      → Duyệt 1 form
  bulk_approve_onboarding → Duyệt nhiều / tất cả
  reject_onboarding       → Từ chối (kèm lý do)
  sync_to_employee        → Đồng bộ dữ liệu sang Employee
  download_cccd_photos    → Tải ảnh CCCD về dưới dạng ZIP
  download_onboarding_excel → Xuất Excel thông tin onboarding
"""

import frappe
from frappe import _


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ONBOARDING_FIELDS = [
	"id_card_no", "id_card_date_of_issue", "id_card_place_of_issue",
	"id_card_front_photo", "id_card_back_photo",
	"id_card_cmnd_no", "id_card_cmnd_date_of_issue", "id_card_cmnd_place_of_issue",
	"marital_status",
	"no_bank_account", "bank_name", "bank_ac_no", "bank_branch",
	"education_level", "university", "major",
	"current_address_province", "current_address_commune",
	"current_address_village", "current_address_full",
	"permanent_address_province", "permanent_address_commune",
	"permanent_address_village", "permanent_address_full",
	"place_of_origin_province", "place_of_origin_commune",
	"place_of_origin_village", "place_of_origin_full",
	"personal_email",
	"number_of_childrens",
	"emergency_contact_name", "emergency_phone_number",
	"date_of_birth", "cell_number",
	"tax_code", "shirt_size", "shoe_size",
]

# Mapping from onboarding form field → Employee field
_SYNC_MAP = {
	"id_card_no":                     "custom_id_card_no",
	"id_card_date_of_issue":          "custom_id_card_date_of_issue",
	"id_card_place_of_issue":         "custom_id_card_place_of_issue",
	"id_card_cmnd_no":                "custom_id_card_cmnd_no",
	"id_card_cmnd_date_of_issue":     "custom_id_card_cmnd_date_of_issue",
	"id_card_cmnd_place_of_issue":    "custom_id_card_cmnd_place_of_issue",
	"marital_status":                 "marital_status",
	"bank_name":                      "bank_name",
	"bank_ac_no":                     "bank_ac_no",
	"bank_branch":                    "bank_branch",
	"education_level":                "custom_education_level",
	"university":                     "custom_university",
	"major":                          "custom_major",
	"current_address_province":       "custom_current_address_province",
	"current_address_commune":        "custom_current_address_commune",
	"current_address_village":        "custom_current_address_village",
	"current_address_full":           "custom_current_address_full",
	"permanent_address_province":     "custom_permanent_address_province",
	"permanent_address_commune":      "custom_permanent_address_commune",
	"permanent_address_village":      "custom_permanent_address_village",
	"permanent_address_full":         "custom_permanent_address_full",
	"place_of_origin_province":       "custom_place_of_origin_address_province",
	"place_of_origin_commune":        "custom_place_of_origin_address_commune",
	"place_of_origin_village":        "custom_place_of_origin_address_village",
	"place_of_origin_full":           "custom_place_of_origin_address_full",
	"personal_email":                 "personal_email",
	"emergency_contact_name":         "person_to_be_contacted",
	"emergency_phone_number":         "emergency_phone_number",
	"number_of_childrens":            "custom_number_of_childrens",
	"date_of_birth":                  "date_of_birth",
	"cell_number":                    "cell_number",
	"tax_code":                       "custom_tax_code",
}

# Feature flag keys with their defaults (1 = enabled)
_FEATURE_FLAGS = [
	"upload_cccd", "current_address", "permanent_address",
	"place_of_origin_address", "personal_email",
	"emergency_contact", "number_of_childrens",
	"tax_code", "shirt_size", "shoe_size",
]


def _get_onboarding_settings():
	"""
	Đọc feature flags từ tabSingles (Single DocType — safe cho Guest via raw SQL).
	Trả dict với default=1 (enabled) cho mọi flag chưa được set.
	"""
	rows = frappe.db.sql(
		"SELECT `field`, `value` FROM `tabSingles`"
		" WHERE `doctype`='Employee Onboarding Settings'",
		as_dict=False,
	)
	cfg = {}
	for field, value in rows:
		try:
			cfg[field] = int(value) if value is not None else 1
		except (ValueError, TypeError):
			cfg[field] = 1
	for key in _FEATURE_FLAGS:
		cfg.setdefault(key, 1)
	return cfg


def _get_eligible_employee_ids():
	"""Return list of employee IDs from the (Single) Settings employee list."""
	emp_rows = frappe.db.sql(
		"SELECT `employee` FROM `tabEmployee Onboarding Employee`"
		" WHERE `parent`=%s AND `parenttype`=%s AND `employee` IS NOT NULL",
		("Employee Onboarding Settings", "Employee Onboarding Settings"),
		as_dict=True,
	)
	emp_ids = [r["employee"] for r in emp_rows if r.get("employee")]
	if not emp_ids:
		return []

	employees = frappe.get_all(
		"Employee",
		filters={"name": ["in", emp_ids]},
		fields=["name", "employee_name", "date_of_birth", "cell_number"],
		order_by="employee_name asc",
		ignore_permissions=True,
	)

	return employees


# ---------------------------------------------------------------------------
# Public APIs
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def get_eligible_employees():
	"""
	Return employees eligible for self-service onboarding:
	- Theo cấu hình Settings
	- Chỉ trả những employee CHƯA có form hoặc có form status=Rejected
	- Không trả cell_number (private)
	"""
	employees = _get_eligible_employee_ids()
	if not employees:
		return []

	emp_ids = [e.name for e in employees]

	# Get existing forms for these employees (ignore permissions for Guest)
	existing_forms = {
		row.employee: row.status
		for row in frappe.get_all(
			"Employee Onboarding Form",
			filters={"employee": ["in", emp_ids]},
			fields=["employee", "status"],
			order_by="creation desc",
			ignore_permissions=True,
		)
	}

	result = []
	for emp in employees:
		form_status = existing_forms.get(emp.name)
		# Skip if already Approved or Synced (cannot re-edit)
		if form_status in ("Approved", "Synced"):
			continue
		birth_year = ""
		if emp.date_of_birth:
			try:
				birth_year = str(emp.date_of_birth)[:4]
			except Exception:
				pass
		result.append({
			"employee_id": emp.name,
			"display_name": emp.employee_name,
			"birth_year": birth_year,
			"has_phone": bool(emp.cell_number and str(emp.cell_number).strip()),
		})

	return result


@frappe.whitelist(allow_guest=True)
def get_onboarding_config():
	"""Return feature flags for the onboarding web form (safe for Guest)."""
	return _get_onboarding_settings()


@frappe.whitelist(allow_guest=True)
def verify_phone(employee_id, last2=None, dob_dd=None):
	"""
	Verify employee identity.
	- If employee has cell_number: verify last2 (2 digits)
	- If no cell_number: verify dob_dd (2 digits, DD format — day of birth only)
	Returns {"valid": True/False}
	"""
	if not employee_id:
		return {"valid": False}

	emp = frappe.db.get_value(
		"Employee", employee_id, ["cell_number", "date_of_birth"], as_dict=True
	)
	if not emp:
		return {"valid": False}

	cell = str(emp.cell_number or "").strip().replace(" ", "").replace("-", "")
	has_phone = bool(cell)

	if has_phone:
		if not last2:
			return {"valid": False}
		last2 = str(last2).strip()
		if len(last2) != 2 or not last2.isdigit():
			return {"valid": False}
		return {"valid": len(cell) >= 2 and cell[-2:] == last2}
	else:
		if not dob_dd:
			return {"valid": False}
		dob_dd = str(dob_dd).strip()
		if len(dob_dd) != 2 or not dob_dd.isdigit():
			return {"valid": False}
		if not emp.date_of_birth:
			return {"valid": False}
		try:
			dob_str = str(emp.date_of_birth)  # "YYYY-MM-DD"
			parts = dob_str.split("-")
			expected = parts[2].zfill(2)  # DD only
			return {"valid": dob_dd == expected}
		except Exception:
			return {"valid": False}


@frappe.whitelist(allow_guest=True)
def get_onboarding_form(employee_id):
	"""
	Return existing onboarding form data + employee basic info (dob, cell_number).
	Always returns a dict. has_form=True means an editable form exists.
	"""
	if not employee_id:
		return None

	# Fetch employee basic info (raw SQL for Guest)
	emp_rows = frappe.db.sql(
		"SELECT `cell_number`, `date_of_birth` FROM `tabEmployee` WHERE `name`=%s LIMIT 1",
		employee_id, as_dict=True,
	)
	if not emp_rows:
		frappe.throw(_("Employee not found"))
	emp = emp_rows[0]

	emp_dob = str(emp.date_of_birth) if emp.date_of_birth else ""
	emp_cell = str(emp.cell_number or "").strip()

	rows = frappe.db.sql(
		"SELECT `name`, `status`, " +
		", ".join(f"`{f}`" for f in _ONBOARDING_FIELDS) +
		" FROM `tabEmployee Onboarding Form` WHERE `employee`=%s LIMIT 1",
		employee_id,
		as_dict=True,
	)

	if not rows or rows[0].status not in ("Pending Review", "Rejected"):
		# No editable form — return only employee basic info
		return {
			"has_form": False,
			"date_of_birth": emp_dob,
			"cell_number": emp_cell,
		}

	existing = rows[0]
	existing.pop("name", None)
	existing["has_form"] = True
	# Pre-fill from Employee if not yet in the form
	if not existing.get("date_of_birth"):
		existing["date_of_birth"] = emp_dob
	if not existing.get("cell_number"):
		existing["cell_number"] = emp_cell
	return existing


@frappe.whitelist(allow_guest=True)
def save_onboarding_form(employee_id, **kwargs):
	"""
	Create or update Employee Onboarding Form.
	Sets status = Pending Review.
	"""
	if not employee_id:
		frappe.throw(_("Employee ID is required"))

	# Validate employee exists (raw query to bypass Guest permission)
	emp = frappe.db.sql(
		"SELECT `name`, `employee_name`, `date_of_joining`, `cell_number` FROM `tabEmployee` WHERE `name`=%s LIMIT 1",
		employee_id,
		as_dict=True,
	)
	if not emp:
		frappe.throw(_("Employee not found"))
	emp = emp[0]

	# Check if existing form allows editing (raw SQL to bypass Guest permission)
	existing_row = frappe.db.sql(
		"SELECT `name`, `status` FROM `tabEmployee Onboarding Form` WHERE `employee`=%s LIMIT 1",
		employee_id,
		as_dict=True,
	)
	existing_name = existing_row[0].name if existing_row else None
	existing_status = existing_row[0].status if existing_row else None

	if existing_name and existing_status in ("Approved", "Synced"):
		frappe.throw(_("This form has already been {0} and cannot be edited.").format(_(existing_status)))

	if existing_name:
		doc = frappe.get_doc("Employee Onboarding Form", existing_name)
		doc.flags.ignore_permissions = True
	else:
		doc = frappe.new_doc("Employee Onboarding Form")
		doc.flags.ignore_permissions = True
		doc.employee = employee_id

	# Set standard fields from Employee (cell_number may be overridden below by submitted value)
	doc.employee_name = emp.employee_name
	doc.date_of_joining = emp.date_of_joining

	# Set submitted fields
	for field in _ONBOARDING_FIELDS:
		val = kwargs.get(field)
		if val is not None:
			doc.set(field, val if val != "" else None)

	# Assemble full addresses from parts
	def _join_addr(*fields):
		return ", ".join(str(doc.get(f) or "") for f in fields if doc.get(f))

	doc.current_address_full   = _join_addr("current_address_village",  "current_address_commune",  "current_address_province")
	doc.permanent_address_full = _join_addr("permanent_address_village", "permanent_address_commune", "permanent_address_province")
	doc.place_of_origin_full   = _join_addr("place_of_origin_village",  "place_of_origin_commune",  "place_of_origin_province")

	# Always set to Pending Review when employee saves
	doc.status = "Pending Review"

	doc.flags.ignore_permissions = True
	doc.save()

	# Propagate corrected dob / cell_number back to Employee record
	new_dob = (kwargs.get("date_of_birth") or "").strip()
	new_cell = (kwargs.get("cell_number") or "").strip()
	if new_dob:
		frappe.db.sql("UPDATE `tabEmployee` SET `date_of_birth`=%s WHERE `name`=%s", (new_dob, employee_id))
	if new_cell:
		frappe.db.sql("UPDATE `tabEmployee` SET `cell_number`=%s WHERE `name`=%s", (new_cell, employee_id))

	frappe.db.commit()
	return {"status": "success", "message": _("Thông tin đã được lưu thành công.")}


# ---------------------------------------------------------------------------
# HR-only APIs (require login, check HR role)
# ---------------------------------------------------------------------------

def _require_hr():
	"""Throw if user is not HR Manager or HR User."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required"), frappe.AuthenticationError)
	roles = frappe.get_roles()
	if not any(r in roles for r in ("HR Manager", "HR User", "System Manager")):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def approve_onboarding(name):
	"""Approve a single onboarding form."""
	_require_hr()
	doc = frappe.get_doc("Employee Onboarding Form", name)
	if doc.status != "Pending Review":
		frappe.throw(_("Only Pending Review forms can be approved."))
	doc.status = "Approved"
	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"status": "success"}


@frappe.whitelist()
def bulk_approve_onboarding(names=None, approve_all=False):
	"""
	Approve multiple onboarding forms.
	names: JSON list of form names, e.g. '["HR-EMP-001", "HR-EMP-002"]'
	approve_all: if True, approve ALL Pending Review forms regardless of names
	"""
	import json as _json

	_require_hr()

	if isinstance(approve_all, str):
		approve_all = approve_all.lower() in ("1", "true", "yes")

	if approve_all:
		pending = frappe.get_all(
			"Employee Onboarding Form",
			filters={"status": "Pending Review"},
			pluck="name",
		)
	else:
		if isinstance(names, str):
			try:
				names = _json.loads(names)
			except Exception:
				frappe.throw(_("Invalid names format"))
		pending = names or []

	approved = []
	skipped = []
	for name in pending:
		status = frappe.db.get_value("Employee Onboarding Form", name, "status")
		if status != "Pending Review":
			skipped.append(name)
			continue
		frappe.db.set_value("Employee Onboarding Form", name, "status", "Approved")
		approved.append(name)

	frappe.db.commit()
	return {
		"status": "success",
		"approved_count": len(approved),
		"skipped_count": len(skipped),
		"approved": approved,
	}


@frappe.whitelist()
def reject_onboarding(name, reason=""):
	"""Reject an onboarding form with a reason."""
	_require_hr()
	doc = frappe.get_doc("Employee Onboarding Form", name)
	if doc.status != "Pending Review":
		frappe.throw(_("Only Pending Review forms can be rejected."))
	doc.status = "Rejected"
	doc.reject_reason = reason
	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"status": "success"}


@frappe.whitelist()
def sync_to_employee(name):
	"""
	Sync onboarding form data to the linked Employee document.
	Maps onboarding fields → Employee fields (with custom_ prefix where needed).
	"""
	_require_hr()

	doc = frappe.get_doc("Employee Onboarding Form", name)
	if doc.status != "Approved":
		frappe.throw(_("Only Approved forms can be synced to Employee."))

	emp = frappe.get_doc("Employee", doc.employee)

	# Get valid fields on Employee doctype
	emp_meta = frappe.get_meta("Employee")
	valid_emp_fields = {f.fieldname for f in emp_meta.fields}

	synced_fields = []
	for form_field, emp_field in _SYNC_MAP.items():
		val = doc.get(form_field)
		if emp_field in valid_emp_fields:
			emp.set(emp_field, val)
			synced_fields.append(emp_field)

	emp.flags.ignore_permissions = True
	emp.flags.ignore_mandatory = True
	emp.save()

	doc.status = "Synced"
	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {
		"status": "success",
		"synced_fields": synced_fields,
		"message": _("Data synced to Employee successfully."),
	}


# ---------------------------------------------------------------------------
# Photo upload (allow_guest — used from onboarding web page)
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def upload_cccd_photo(employee_id, side, image_data):
	"""
	Upload CCCD photo (front or back) for an employee's onboarding form.

	employee_id: e.g. "TIQN-1234"
	side: "front" or "back"
	image_data: base64 dataURL (client already cropped & compressed to ≤3 MB JPEG)

	Returns: {"file_url": "/files/<encoded_name>"}
	"""
	import base64
	import os
	import re
	from urllib.parse import quote

	if not employee_id or side not in ("front", "back"):
		frappe.throw(_("Invalid parameters"))

	# Fetch employee name
	emp = frappe.db.sql(
		"SELECT `name`, `employee_name` FROM `tabEmployee` WHERE `name`=%s LIMIT 1",
		employee_id, as_dict=True,
	)
	if not emp:
		frappe.throw(_("Employee not found"))
	employee_name = emp[0].employee_name or employee_id

	# Parse dataURL
	if not image_data or not image_data.startswith("data:"):
		frappe.throw(_("Invalid image data"))
	match = re.match(r"data:image/(\w+);base64,(.+)", image_data)
	if not match:
		frappe.throw(_("Invalid image format"))

	raw = match.group(2)
	try:
		file_bytes = base64.b64decode(raw)
	except Exception:
		frappe.throw(_("Failed to decode image"))

	# 4 MB hard limit (client targets ≤3 MB, buffer for overhead)
	if len(file_bytes) > 4 * 1024 * 1024:
		frappe.throw(_("Image is too large. Maximum size is 4 MB."))

	# Build filename: "TIQN-1234 Nguyen Van A CCCD mặt trước.JPG"
	side_label = "mặt trước" if side == "front" else "mặt sau"
	safe_name = re.sub(r'[\\/:*?"<>|]', "", employee_name).strip()
	file_name = f"{employee_id} {safe_name} CCCD {side_label}.JPG"
	file_url = "/files/" + quote(file_name)

	# Save to Frappe public files (overwrite previous upload for same employee+side)
	site_path = frappe.get_site_path()
	public_files = os.path.join(site_path, "public", "files")
	os.makedirs(public_files, exist_ok=True)
	file_path = os.path.join(public_files, file_name)
	with open(file_path, "wb") as f:
		f.write(file_bytes)

	# Create/update File record
	existing_file = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if existing_file:
		frappe.db.set_value("File", existing_file, "attached_to_doctype", "Employee Onboarding Form")
		frappe.db.set_value("File", existing_file, "attached_to_name", employee_id)
	else:
		file_doc = frappe.get_doc({
			"doctype": "File",
			"file_name": file_name,
			"file_url": file_url,
			"attached_to_doctype": "Employee Onboarding Form",
			"attached_to_name": employee_id,
			"is_private": 0,
		})
		file_doc.flags.ignore_permissions = True
		file_doc.insert()

	frappe.db.commit()

	return {"file_url": file_url}


# ---------------------------------------------------------------------------
# CCCD photo ZIP download (HR only)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def download_cccd_photos(names=None):
	"""
	Return base64-encoded ZIP of CCCD photos for selected (or all) forms.
	Each form contributes up to 2 files: front + back.
	"""
	import base64
	import io
	import json
	import os
	import zipfile
	from urllib.parse import unquote

	_require_hr()

	filters = {}
	if names:
		names_list = json.loads(names) if isinstance(names, str) else names
		if names_list:
			filters["name"] = ["in", names_list]

	records = frappe.get_all(
		"Employee Onboarding Form",
		filters=filters,
		fields=["employee", "employee_name", "id_card_front_photo", "id_card_back_photo"],
		order_by="employee_name asc",
	)

	site_path = frappe.get_site_path()
	buf = io.BytesIO()
	added = 0

	with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
		for r in records:
			for side, url_field in [("front", "id_card_front_photo"), ("back", "id_card_back_photo")]:
				file_url = r.get(url_field)
				if not file_url:
					continue
				# URL-decode first (field may store %20 etc.), then resolve filesystem path
				decoded_url = unquote(file_url)
				# Handle both /files/... (public) and /private/files/... (private)
				if decoded_url.startswith("/private/"):
					rel_path = decoded_url.lstrip("/")  # "private/files/..."
					abs_path = os.path.join(site_path, rel_path)
				else:
					rel_path = decoded_url.lstrip("/")  # "files/..."
					abs_path = os.path.join(site_path, "public", rel_path)
				if not os.path.exists(abs_path):
					continue
				arc_name = os.path.basename(abs_path)
				zf.write(abs_path, arc_name)
				added += 1

	if added == 0:
		frappe.throw(_("Không có ảnh CCCD nào để tải."))

	return {
		"filename": "CCCD_photos.zip",
		"data": base64.b64encode(buf.getvalue()).decode("utf-8"),
	}


# ---------------------------------------------------------------------------
# Excel download (HR only)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def download_onboarding_excel(names=None):
	"""Return base64-encoded XLSX of selected (or all) onboarding forms."""
	import base64
	import io
	import json

	_require_hr()

	filters = {}
	if names:
		names_list = json.loads(names) if isinstance(names, str) else names
		if names_list:
			filters["name"] = ["in", names_list]

	records = frappe.get_all(
		"Employee Onboarding Form",
		filters=filters,
		fields=[
			"employee", "employee_name", "date_of_joining", "cell_number", "status",
			"id_card_no", "id_card_date_of_issue", "id_card_place_of_issue",
			"id_card_cmnd_no", "id_card_cmnd_date_of_issue", "id_card_cmnd_place_of_issue",
			"marital_status", "number_of_childrens",
			"no_bank_account", "bank_name", "bank_ac_no", "bank_branch",
			"education_level", "university", "major",
			"current_address_province", "current_address_commune",
			"current_address_village", "current_address_full",
			"permanent_address_province", "permanent_address_commune",
			"permanent_address_village", "permanent_address_full",
			"place_of_origin_province", "place_of_origin_commune",
			"place_of_origin_village", "place_of_origin_full",
			"personal_email",
			"emergency_contact_name", "emergency_phone_number",
		],
		order_by="employee_name asc",
	)

	columns = [
		"Mã NV", "Họ tên", "Ngày gia nhập", "SĐT", "Trạng thái",
		"Số CCCD", "Ngày cấp CCCD", "Nơi cấp CCCD",
		"Số CMND", "Ngày cấp CMND", "Nơi cấp CMND",
		"Hôn nhân", "Số con",
		"Ngân hàng", "Số TK", "Chi nhánh",
		"Trình độ", "Trường học", "Chuyên ngành",
		# Địa chỉ hiện tại
		"ĐC HT - Tỉnh/TP", "ĐC HT - Xã/Phường", "ĐC HT - Số nhà/Thôn", "ĐC HT - Đầy đủ",
		# Địa chỉ hộ khẩu
		"ĐC HK - Tỉnh/TP", "ĐC HK - Xã/Phường", "ĐC HK - Số nhà/Thôn", "ĐC HK - Đầy đủ",
		# Địa chỉ nguyên quán
		"ĐC NQ - Tỉnh/TP", "ĐC NQ - Xã/Phường", "ĐC NQ - Số nhà/Thôn", "ĐC NQ - Đầy đủ",
		# Liên hệ khác
		"Email cá nhân", "Liên hệ khẩn cấp", "SĐT liên hệ KK",
	]
	field_keys = [
		"employee", "employee_name", "date_of_joining", "cell_number", "status",
		"id_card_no", "id_card_date_of_issue", "id_card_place_of_issue",
		"id_card_cmnd_no", "id_card_cmnd_date_of_issue", "id_card_cmnd_place_of_issue",
		"marital_status", "number_of_childrens",
		"bank_name", "bank_ac_no", "bank_branch",
		"education_level", "university", "major",
		"current_address_province", "current_address_commune",
		"current_address_village", "current_address_full",
		"permanent_address_province", "permanent_address_commune",
		"permanent_address_village", "permanent_address_full",
		"place_of_origin_province", "place_of_origin_commune",
		"place_of_origin_village", "place_of_origin_full",
		"personal_email",
		"emergency_contact_name", "emergency_phone_number",
	]

	data = [columns]
	for r in records:
		no_bank = r.get("no_bank_account")
		row = []
		for f in field_keys:
			v = r.get(f)
			if v is None:
				v = ""
			elif no_bank and f in ("bank_name", "bank_ac_no", "bank_branch"):
				v = ""
			else:
				v = str(v)
			row.append(v)
		data.append(row)

	from frappe.utils.xlsxutils import make_xlsx
	xlsx_file = make_xlsx(data, "Employee Onboarding")
	return {
		"filename": "employee_onboarding.xlsx",
		"data": base64.b64encode(xlsx_file.getvalue()).decode("utf-8"),
	}
