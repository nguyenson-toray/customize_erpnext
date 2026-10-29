"""API trang www /employee-self-update-info (guest): config, xác thực, đọc / lưu phiếu, tải phiếu.

Tách nguyên văn từ self_update_info_api.py (27/10/2026) — mặt tiền đó re-export mọi tên."""

import json
import mimetypes
import re

import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.utils.html_utils import sanitize_html

from customize_erpnext.api.employee.cccd_expiry import EXPIRY_FIELD as CCCD_EXPIRY_FIELD

from .rules import (
	DOCUMENTS_KEY,
	INFO_DT,
	REMARKS_KEY,
	SETTING_DT,
	_SIGNATURE_MAX_LEN,
	_SIGNATURE_PREFIX,
)
from .config import (
	_build_config,
	_commitment_html,
	_config_fieldnames,
	_employee_scalar_fields,
	_get_setting,
	_is_table,
	_setting_documents,
)
from .values import (
	_apply_cccd_expiry,
	_apply_depends,
	_clean_documents,
	_clean_table_value,
	_documents_snapshot,
	_employee_tables,
	_fill_from_employee,
	_normalize_text,
	_portal_address_errors,
	_validate_value,
)
from .access import (
	_code_ok,
	_eligible_ids,
	_ensure_eligible,
	_gate_edit,
	_gate_receipt,
	_is_hr,
	_make_download_token,
	_receipt_download_allowed,
	_unlock_ok,
)
from .receipt import (
	_build_submission_html,
	_html_to_png,
	_receipt_base,
)


def _submit_device_info():
	"""Basic device/browser info of the submitting request: IP + User-Agent.

	Read-only audit only; no permission prompt, not synced to Employee.
	Returns '' when there is no HTTP request context (e.g. bench execute).
	"""
	try:
		ip = frappe.local.request_ip or ""
	except Exception:
		ip = ""
	def _h(name):
		try:
			return (frappe.get_request_header(name) or "").strip().strip('"')
		except Exception:
			return ""

	# User-Agent Client Hints (Chromium/Android; empty on Safari/iOS). Requires
	# the Accept-CH opt-in sent by the web page (see www/.../index.py).
	model = _h("Sec-CH-UA-Model")
	platform = " ".join(x for x in (_h("Sec-CH-UA-Platform"), _h("Sec-CH-UA-Platform-Version")) if x)

	parts = []
	if ip:
		parts.append(f"IP: {ip}")
	if model:
		parts.append(f"Model: {model}")
	if platform:
		parts.append(f"Platform: {platform}")
	return "\n".join(parts)


# Ảnh chèn vào Start Screen Notes (Text Editor) là file PRIVATE gắn vào Setting → Guest mở /private/files bị 403
# (ảnh hỏng). Trang nhận URL qua start_note_image thay vì /private/files (user 29/10/2026).
# Editor có khi lưu src TUYỆT ĐỐI (https://erp.tiqn.local:8888/private/files/…) → bỏ qua phần scheme + host.
_NOTE_IMG_SRC = re.compile(
	r'(<img\b[^>]*?\bsrc=")(?:https?://[^/"]+)?(/private/files/[^"?]+)(?:\?([^"]*))?(")', re.I)
# Ảnh dán từ điện thoại / ảnh chụp màn hình thường 1–3 MB, trang chỉ hiện rộng ≤ ~600px → thu về cạnh dài ≤ 1200px
# (nét trên màn hình 2x), JPEG: 2,1 MB → ~190 KB. Cache Redis theo content_hash.
_NOTE_IMG_MAX = 1200
_NOTE_IMG_METHOD = "/api/method/customize_erpnext.api.self_update_info.self_update_info_api.start_note_image"


def _note_image_files():
	"""{file_url: File} — ảnh private gắn vào Setting (ảnh dán vào Text Editor của Setting)."""
	rows = frappe.get_all("File", filters={"attached_to_doctype": SETTING_DT, "is_private": 1},
		fields=["name", "file_url", "content_hash", "modified"], order_by="creation desc")
	out = {}
	for r in rows:
		out.setdefault(r.file_url, r)
	return out


def _guest_note_images(html):
	"""img src=/private/files/… gắn vào Setting → URL start_note_image (kèm v= để trình duyệt cache đúng bản).
	File private không gắn vào Setting → giữ nguyên (không mở đường lộ file khác)."""
	if "/private/files/" not in html:
		return html
	files = _note_image_files()

	def sub(m):
		f = files.get(m.group(2))
		if not f:
			return m.group(0)
		v = (f.content_hash or str(f.modified))[:12]
		return f"{m.group(1)}{_NOTE_IMG_METHOD}?fid={f.name}&amp;v={frappe.utils.escape_html(v)}{m.group(4)}"

	return _NOTE_IMG_SRC.sub(sub, html)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def start_note_image(fid, v=None):
	"""Ảnh của Start Screen Notes cho Guest. Chỉ trả file ảnh gắn vào Setting VÀ đang có trong ghi chú."""
	f = frappe.db.get_value("File", fid, ["name", "file_url", "file_name", "attached_to_doctype"], as_dict=True)
	notes = _get_setting().get("start_notes") or ""
	mime = f and (mimetypes.guess_type(f.file_name or f.file_url)[0] or "")
	if not f or f.attached_to_doctype != SETTING_DT or not f.file_url or f.file_url not in notes \
			or not mime.startswith("image/") or mime == "image/svg+xml":
		raise frappe.DoesNotExistError
	content, mime = _note_image_content(f.name, mime)
	frappe.response.update({
		"type": "download", "filename": f.file_name or "image", "content_type": mime,
		"display_content_as": "inline", "filecontent": content,
	})
	# URL đổi theo v= (content_hash) khi thay ảnh → cache lâu được
	frappe.local.response_headers["Cache-Control"] = "private, max-age=86400"


def _note_image_content(fid, mime):
	"""(bytes, mime) ảnh đã thu nhỏ — ảnh nhỏ sẵn / GIF (có thể động) / lỗi đọc ảnh → trả nguyên file."""
	doc = frappe.get_doc("File", fid)
	key = f"esui_note_img:{doc.content_hash or doc.name}:{_NOTE_IMG_MAX}"
	cached = frappe.cache.get_value(key)
	if cached:
		return cached
	raw = doc.get_content()
	out = (raw, mime)
	if mime != "image/gif":
		try:
			import io

			from PIL import Image, ImageOps

			im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
			if max(im.size) > _NOTE_IMG_MAX:
				im.thumbnail((_NOTE_IMG_MAX, _NOTE_IMG_MAX), Image.LANCZOS)
				if im.mode in ("RGBA", "LA", "P"):
					im = im.convert("RGBA")
					bg = Image.new("RGB", im.size, (255, 255, 255))   # JPEG không có nền trong → nền trắng như khung
					bg.paste(im, mask=im.getchannel("A"))
					im = bg
				buf = io.BytesIO()
				im.convert("RGB").save(buf, "JPEG", quality=85, optimize=True, progressive=True)
				if buf.tell() < len(raw):
					out = (buf.getvalue(), "image/jpeg")
		except Exception:
			pass  # ảnh lạ → trả nguyên file
	frappe.cache.set_value(key, out, expires_in_sec=7 * 86400)
	return out


@frappe.whitelist(allow_guest=True)
def get_field_config():
	"""Return the dynamic field configuration for the web form."""
	setting = _get_setting()
	config = _build_config()
	config["require_dob"] = bool(setting.validate_by_dob)
	# Whether the page may keep a local draft (localStorage).
	config["allow_local_draft"] = bool(setting.allow_browser_local_storage)
	# In Zalo's in-app browser, force the user to open in the device browser
	# (PDF download is blocked inside the Zalo webview).
	config["force_device_browser"] = bool(setting.get("force_open_devices_browser"))
	# Receipt file type offered on the success screen: "PDF" (default) or "PNG".
	# PNG renders inline so it can be long-pressed to save inside the Zalo webview.
	config["save_file_type"] = setting.get("save_file_type") or "PDF"
	# Tắt → màn hình "Đã gửi" không có nút tải phiếu (server cũng chặn ở _gate_receipt).
	config["allow_receipt_download"] = _receipt_download_allowed(setting)
	# Lock the form (and receipts) after the first submission. The secret
	# unlock code (bypass_code_for_unlock) is NEVER sent to the client.
	config["lock_after_submit"] = bool(setting.get("lock_after_submit"))
	config["commitment_html"] = _commitment_html(setting)
	# Ghi chú màn hình đầu (trước khi chọn NV), Text Editor: HTML làm sạch ở đây (sanitize_html bỏ script / on* /
	# javascript:) vì trang chèn thẳng innerHTML. Editor trống (<p><br></p>) → "" để trang ẩn khung.
	notes = setting.get("start_notes") or ""
	config["start_notes_html"] = (
		_guest_note_images(sanitize_html(notes, always_sanitize=True))
		if frappe.utils.strip_html(notes).strip() or "<img" in notes else ""
	)
	# Lần đầu mở trên 1 máy: nút "Bắt đầu" chờ N giây để NV đọc ghi chú (user 28/10/2026). Trống / âm → 0 = không chờ.
	config["start_button_delay"] = max(0, frappe.utils.cint(setting.get("start_button_delay")))
	# Hồ sơ nộp kèm: NV tick hồ sơ đã có (không chặn gửi khi thiếu — HR theo dõi ở Tình trạng hồ sơ).
	config["documents"] = _setting_documents(setting)
	return config


@frappe.whitelist(allow_guest=True)
def verify_employee(employee_id, code):
	"""Verify the DOB digits / bypass code before showing the form.

	Returns {valid: bool}. Always valid when validate_by_dob is off.
	"""
	if not employee_id:
		frappe.throw(_("Missing employee"))
	setting = _get_setting()
	_ensure_eligible(setting, employee_id)
	if not setting.validate_by_dob:
		return {"valid": True}
	return {"valid": _code_ok(setting, employee_id, code)}


@frappe.whitelist(allow_guest=True)
def get_access_info(employee_id):
	"""Report whether this employee's form is locked after a first submission.

	Returns {submitted, submitted_on (display), locked}. The unlock code is
	never exposed. Low sensitivity: same as the `submitted` flag already
	returned by get_eligible_employees.
	"""
	if not employee_id:
		frappe.throw(_("Missing employee"))
	setting = _get_setting()
	_ensure_eligible(setting, employee_id)
	submitted_on = frappe.db.get_value(INFO_DT, employee_id, "submitted_on")
	return {
		"submitted": bool(submitted_on),
		"submitted_on": frappe.utils.format_datetime(submitted_on, "dd/MM/yyyy HH:mm") if submitted_on else "",
		"locked": bool(setting.get("lock_after_submit")) and bool(submitted_on),
	}


@frappe.whitelist(allow_guest=True)
def unlock_access(employee_id, code, unlock_code):
	"""Pre-check the unlock: needs BOTH the DOB digits and the unlock code.

	Returns {valid}. Server-side enforcement still happens in get_form_data /
	save_form_data, so bypassing this cannot unlock the form.
	"""
	if not employee_id:
		frappe.throw(_("Missing employee"))
	setting = _get_setting()
	_ensure_eligible(setting, employee_id)
	valid = _code_ok(setting, employee_id, code) and _unlock_ok(setting, unlock_code)
	return {"valid": valid}


@frappe.whitelist(allow_guest=True)
def get_eligible_employees():
	"""Return employees configured in the setting (optionally filtered by group)."""
	setting = _get_setting()
	ids = _eligible_ids(setting)
	if not ids:
		return []

	rows = frappe.get_all(
		"Employee",
		filters={"name": ["in", ids]},
		fields=["name as employee_id", "employee_name as display_name"],
		order_by="employee_name asc",
	)
	submitted = set(
		frappe.get_all(
			INFO_DT,
			filters={"employee": ["in", ids], "status": "Submitted"},
			pluck="employee",
		)
	)
	for r in rows:
		r["submitted"] = r["employee_id"] in submitted
	return rows


@frappe.whitelist(allow_guest=True)
def get_form_data(employee_id, code=None, unlock_code=None):
	"""Return current Employee values overlaid with any saved draft/submission.

	`code` = DOB digits / bypass code, required only when validate_by_dob is on.
	`unlock_code` = required together with `code` when the form is locked after
	a first submission (lock_after_submit).

	Returns:
	    {
	      original: {fieldname: value},   # live Employee values
	      values:   {fieldname: value},   # what to show (draft overrides original)
	      has_existing: bool,
	      status: "Draft"|"Submitted"|None,
	      employee_name: str,
	    }
	"""
	if not employee_id:
		frappe.throw(_("Missing employee"))

	setting = _get_setting()
	_ensure_eligible(setting, employee_id)
	_gate_edit(setting, employee_id, code, unlock_code)

	config = _build_config()
	fieldnames = _config_fieldnames(config)
	# Only real Employee fields can be read from the Employee record; custom
	# fields have no source value. Bảng con đọc riêng (list dòng, kèm `name`).
	real_fields = _employee_scalar_fields(config)

	emp = frappe.db.get_value(
		"Employee", employee_id, ["employee_name"] + real_fields, as_dict=True
	) or {}
	employee_name = emp.get("employee_name")
	original = {fn: (emp.get(fn) if fn in real_fields else None) for fn in fieldnames}
	original.update(_employee_tables(employee_id, config))

	values = dict(original)
	status = None
	has_existing = False
	remarks = ""
	documents = []  # tên hồ sơ đã tick ở lần gửi trước
	if frappe.db.exists(INFO_DT, employee_id):
		doc = frappe.get_doc(INFO_DT, employee_id)
		status = doc.status
		has_existing = True
		saved = json.loads(doc.data_json or "{}")
		remarks = saved.get(REMARKS_KEY, "")
		documents = [d["document"] for d in _clean_documents(saved.get(DOCUMENTS_KEY)) if d["checked"]]
		tables = {f["fieldname"] for sec in config["sections"] for f in sec["fields"] if _is_table(f)}
		for fn in fieldnames:
			if fn in saved:
				if fn in tables and not isinstance(saved[fn], list):
					continue  # bảng con lưu dạng cũ (chữ, khi còn là field custom) → giữ dòng Employee
				values[fn] = saved[fn]

	# Fields with auto_fill = 0 must be re-entered every visit: never prefill
	# them from Employee or from a previous submission.
	no_fill = {
		f["fieldname"]
		for sec in config["sections"]
		for f in sec["fields"]
		if not f.get("auto_fill")
	}
	for fn in no_fill:
		values[fn] = None

	return {
		"original": original,
		"values": values,
		"has_existing": has_existing,
		"status": status,
		"employee_name": employee_name,
		"remarks": remarks,
		"documents": documents,
		# HR sửa qua ?emp= → trang không bắt buộc cam kết + chữ ký.
		"is_hr": _is_hr(),
	}


@frappe.whitelist(allow_guest=True)
def save_form_data(employee_id, data, code=None, unlock_code=None, commitment=None, signature=None, documents=None):
	"""Store submitted values as JSON. Does NOT write back to Employee.

	`commitment` (1/0) + `signature` (data URL PNG từ ô vẽ chữ ký): bắt buộc với NV;
	HR sửa qua ?emp= thì không bắt buộc — không gửi chữ ký thì giữ chữ ký cũ.
	`documents` = JSON list tên hồ sơ NV tick (Setting → Document Checklist); thiếu hồ sơ bắt buộc vẫn gửi được.
	"""
	if not employee_id:
		frappe.throw(_("Missing employee"))

	is_hr = _is_hr()
	committed = frappe.utils.cint(commitment) == 1
	signature = (signature or "").strip()
	if signature:
		if not signature.startswith(_SIGNATURE_PREFIX) or len(signature) > _SIGNATURE_MAX_LEN:
			frappe.throw(_("Invalid signature image"))
	# Ký thì PHẢI tick cam kết — kể cả HR (chữ ký không kèm cam kết vô nghĩa; bug 28/10/2026: HR test ký được khi
	# chưa tick). HR không ký (sửa hộ qua ?emp=) thì không bắt buộc cả hai — giữ chữ ký cũ của NV.
	if (signature or not is_hr) and not committed:
		frappe.throw("Vui lòng tick ô cam kết thông tin khai đúng sự thật.")
	if not is_hr and not signature:
		frappe.throw("Vui lòng ký tên vào ô chữ ký.")

	setting = _get_setting()
	_ensure_eligible(setting, employee_id)
	_gate_edit(setting, employee_id, code, unlock_code)

	if isinstance(data, str):
		data = json.loads(data or "{}")

	config = _build_config()
	allowed = set(_config_fieldnames(config))

	# Keep only configured, editable fields.
	editable = {
		f["fieldname"]
		for sec in config["sections"]
		for f in sec["fields"]
		if not f["read_only"]
	}
	clean = {k: v for k, v in (data or {}).items() if k in allowed and k in editable}
	# Ô "Ghi chú thêm" gắn cứng (__remarks) đã bỏ 16/10/2026 — cần ghi chú thì thêm custom field trong Setting.

	# Tự chuẩn hoá chữ (NFC, khoảng trắng, chữ–số, viết hoa ký tự đầu / Capitalize Each Word / Sentence Case).
	fields_by_name = {f["fieldname"]: f for sec in config["sections"] for f in sec["fields"]}
	table_errors = []
	for k in list(clean):
		if k in fields_by_name:
			f = fields_by_name[k]
			if _is_table(f):
				# Bảng con: list dòng đã làm sạch (cột, kiểu, max_rows, cột bắt buộc, `name` của chính NV).
				clean[k], errs = _clean_table_value(f, clean[k], employee_id)
				table_errors += errs
			elif f.get("allow_other") and clean[k] not in (f.get("options") or []):
				# "Khác" của widget Select + Other: chữ tự do → chuẩn hoá như field Data
				clean[k] = _normalize_text(dict(f, fieldtype="Data"), clean[k])
			else:
				clean[k] = _normalize_text(f, clean[k])

	# Ngày hết hạn CCCD: không nhận giá trị gửi lên, luôn tự tính.
	_apply_cccd_expiry(config, clean, employee_id)
	# Field "chỉ hiện khi…" (_FIELD_DEPENDS): ẩn → xoá trắng; đang hiện → bắt buộc.
	dep_visible = _apply_depends(config, clean, employee_id)

	# Validate required fields.
	missing = []
	for sec in config["sections"]:
		for f in sec["fields"]:
			required = dep_visible[f["fieldname"]] if f["fieldname"] in dep_visible else f["required"]
			if required and not f["read_only"] and f["fieldname"] != CCCD_EXPIRY_FIELD:
				val = clean.get(f["fieldname"])
				if (not val) if _is_table(f) else (val is None or str(val).strip() == ""):
					missing.append(f["label"])
	if missing:
		frappe.throw(_("Please fill required fields: {0}").format(", ".join(missing)))

	# Format validation (mirrors the client; server is the source of truth).
	errors = list(table_errors)
	for sec in config["sections"]:
		for f in sec["fields"]:
			if f["read_only"] or f["fieldname"] == CCCD_EXPIRY_FIELD or _is_table(f):
				continue  # ngày hết hạn tự tính: thẻ đã quá hạn thì vẫn ghi đúng, không chặn "Future"
			err = _validate_value(f, clean.get(f["fieldname"]))
			if err:
				errors.append(err)
			v = clean.get(f["fieldname"])
			# Select (kể cả Gender hiện dạng dropdown): chỉ nhận giá trị gốc trong options — nhãn tiếng Việt
			# ("Nữ") gửi lên sẽ làm Sync lỗi Link / Select.
			# Select + Other: ngoài danh sách = chữ NV gõ ở "Khác" → hợp lệ (field Employee là Data).
			if (f.get("fieldtype") == "Select" and not f.get("allow_other")
					and v not in (None, "") and v not in (f.get("options") or [])):
				errors.append(_("{0}: {1} is not a valid option").format(f["label"], v))
	errors += _portal_address_errors(config, clean, employee_id)
	if errors:
		frappe.throw("<br>".join(errors))

	snapshot = _documents_snapshot(documents, setting)
	if snapshot:
		clean[DOCUMENTS_KEY] = snapshot

	employee_name = frappe.db.get_value("Employee", employee_id, "employee_name")

	if frappe.db.exists(INFO_DT, employee_id):
		doc = frappe.get_doc(INFO_DT, employee_id)
	else:
		doc = frappe.new_doc(INFO_DT)
		doc.employee = employee_id

	doc.employee_name = employee_name
	doc.data_json = json.dumps(clean, ensure_ascii=False)
	doc.status = "Submitted"
	doc.submitted_on = now_datetime()
	# Append device info each submit (keep history) instead of replacing.
	info = _submit_device_info()
	if info:
		stamp = frappe.utils.format_datetime(now_datetime(), "yyyy-MM-dd HH:mm")
		entry = f"[{stamp}]\n{info}"
		prev = (doc.device_info or "").strip()
		doc.device_info = (prev + "\n\n" + entry) if prev else entry
	if signature:
		doc.signature = signature
		doc.commitment_confirmed = 1 if committed else 0
		doc.signed_on = now_datetime()
	doc.flags.from_portal = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	# Short-lived token so THIS session can download the receipt right away,
	# even though the form is now locked for later (cold) visits.
	return {
		"status": "success",
		"message": _("Your information has been submitted."),
		"download_token": _make_download_token(employee_id) if _receipt_download_allowed(setting) else None,
	}


@frappe.whitelist(allow_guest=True)
def download_submission_pdf(employee_id, code=None, unlock_code=None, token=None):
	"""Return a PDF receipt of the employee's submitted information."""
	html, base = _load_submission_receipt(employee_id, code, unlock_code, token)
	from frappe.utils.pdf import get_pdf

	frappe.response["filename"] = f"{base}.pdf"
	frappe.response["filecontent"] = get_pdf(html)
	frappe.response["type"] = "pdf"


@frappe.whitelist(allow_guest=True)
def download_submission_image(employee_id, code=None, unlock_code=None, token=None):
	"""Return a PNG image of the employee's submitted information as a file download."""
	html, base = _load_submission_receipt(employee_id, code, unlock_code, token)
	frappe.response["filename"] = f"{base}.png"
	frappe.response["filecontent"] = _html_to_png(html)
	frappe.response["type"] = "download"
	frappe.response["content_type"] = "image/png"


def _load_submission_receipt(employee_id, code, unlock_code=None, token=None):
	"""Shared gate + HTML build for the PDF/PNG receipt. Returns (html, base_filename)."""
	if not employee_id:
		frappe.throw(_("Missing employee"))
	setting = _get_setting()
	_ensure_eligible(setting, employee_id)
	_gate_receipt(setting, employee_id, code, unlock_code, token)

	if not frappe.db.exists(INFO_DT, employee_id):
		frappe.throw(_("No submission found for this employee."))

	doc = frappe.get_doc(INFO_DT, employee_id)
	config = _build_config()
	saved = _fill_from_employee(config, json.loads(doc.data_json or "{}"), doc.employee)
	html = _build_submission_html(doc, saved, config)
	return html, _receipt_base(doc)
