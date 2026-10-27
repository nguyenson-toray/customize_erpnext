"""Đọc, chuẩn hoá, kiểm tra và định dạng giá trị đã khai (field thường, bảng con, hồ sơ nộp kèm).

Tách nguyên văn từ self_update_info_api.py (27/10/2026) — mặt tiền đó re-export mọi tên."""

import json
import re

import frappe
from frappe import _

from customize_erpnext.api.employee.cccd_expiry import DOB_FIELD as CCCD_DOB_FIELD
from customize_erpnext.api.employee.cccd_expiry import EXPIRY_FIELD as CCCD_EXPIRY_FIELD
from customize_erpnext.api.employee.cccd_expiry import ISSUE_FIELD as CCCD_ISSUE_FIELD
from customize_erpnext.api.employee.cccd_expiry import cccd_expiry_iso

from .config import (
	_address_pairs,
	_is_table,
	_setting_documents,
)


def _dep_parent_value(f, values, employee):
	"""Giá trị field điều kiện: trong `values` nếu có, không thì lấy trên Employee."""
	parent = f["depends_on"]["field"]
	if parent in values:
		return values.get(parent)
	return frappe.db.get_value("Employee", employee, parent) if employee else None


def _apply_depends(config, values, employee):
	"""Field có depends_on: ẩn → values[fn] = "" (Sync xoá luôn trên Employee). Trả {fieldname: đang hiện}."""
	visible = {}
	for sec in config["sections"]:
		for f in sec["fields"]:
			if not f.get("depends_on") or f.get("read_only"):
				continue
			fn = f["fieldname"]
			visible[fn] = (_dep_parent_value(f, values, employee) or "") in f["depends_on"]["values"]
			if not visible[fn]:
				values[fn] = ""
	return visible


def _column_required(f, c, row):
	"""Cột `c` có bắt buộc ở dòng `row` không: bắt buộc cố định, hoặc theo required_if."""
	if c["required"]:
		return True
	rule = f.get("required_if")
	return bool(rule) and c["fieldname"] in rule["required"] and row.get(rule["column"]) in rule["values"]


def _column_hidden(f, c, row):
	"""Cột `c` bị ẩn ở dòng `row`: thuộc required_if và cột điều kiện ĐÃ chọn giá trị ngoài `values`."""
	rule = f.get("required_if")
	v = row.get(rule["column"]) if rule else None
	return bool(rule) and c["fieldname"] in rule["columns"] and bool(v) and v not in rule["values"]


def _employee_table_rows(employee, f):
	"""Dòng con hiện có trên Employee: [{name, <cột>: chuỗi}] theo idx. Số 0 / None → "".
	Chỉ `max_rows` dòng CUỐI (mới nhất): Employee cũ có thể nhiều dòng hơn Max Rows (Học vấn / Kinh nghiệm
	đặt Max Rows = 1, user 23/10/2026) — trang www điền sẵn đúng dòng đó, Sync xoá phần dư."""
	cols = [c for c in f["columns"]]
	rows = frappe.get_all(
		f["options"],
		filters={"parent": employee, "parenttype": "Employee", "parentfield": f["fieldname"]},
		fields=["name"] + [c["fieldname"] for c in cols],
		order_by="idx asc",
	) if employee else []
	out = []
	for r in rows:
		item = {"name": r.name}
		for c in cols:
			v = r.get(c["fieldname"])
			if c["fieldtype"] in ("Int", "Float") and not v:
				v = ""
			elif c["fieldtype"] == "Date" and v:
				v = str(v)
			elif c["fieldtype"] == "Int":
				v = str(int(v))
			item[c["fieldname"]] = "" if v is None else str(v)
		out.append(item)
	return out[-f["max_rows"]:] if f.get("max_rows") else out


def _employee_tables(employee, config):
	"""{fieldname: dòng con hiện có} cho mọi field bảng con trong config."""
	return {
		f["fieldname"]: _employee_table_rows(employee, f)
		for sec in config["sections"] for f in sec["fields"] if _is_table(f)
	}


def _is_blank(f, value):
	"""Phiếu chưa có giá trị cho field: thiếu khoá / None / chuỗi trắng; bảng con: không có dòng."""
	if _is_table(f):
		return not _table_list(value)
	return value is None or str(value).strip() == ""


def _fill_from_employee(config, saved, employee):
	"""Bản sao `saved` mà field tick "Auto Fill Data" (field Employee thật, không custom) chưa có giá trị
	→ lấy giá trị hiện tại trên Employee. Đúng như trang www điền sẵn khi NV mở form; phủ cả field thêm
	vào Setting SAU khi NV đã gửi phiếu (data_json không có khoá). Dùng cho phiếu PDF/PNG.
	Info for Sign đã có quy tắc tương tự ("mới trống → Employee") trong _info_for_sign_people."""
	missing = [
		f for sec in config["sections"] for f in sec["fields"]
		if f.get("auto_fill") and not f.get("custom") and f["fieldname"] not in ("employee", "name")
		and _is_blank(f, saved.get(f["fieldname"]))
	]
	if not missing or not employee:
		return saved
	scalars = [f["fieldname"] for f in missing if not _is_table(f)]
	emp = (frappe.db.get_value("Employee", employee, scalars, as_dict=True) or {}) if scalars else {}
	out = dict(saved)
	for f in missing:
		fn = f["fieldname"]
		v = _employee_table_rows(employee, f) if _is_table(f) else emp.get(fn)
		if not _is_blank(f, v):
			out[fn] = v if _is_table(f) else str(v)
	return out


def _table_list(value):
	"""Giá trị bảng con trong data_json → list (chuỗi JSON / None / kiểu lạ → [])."""
	if isinstance(value, str):
		try:
			value = json.loads(value or "[]")
		except ValueError:
			return []
	return [r for r in value if isinstance(r, dict)] if isinstance(value, list) else []


def _table_rows_equal(f, a, b):
	"""So sánh 2 danh sách dòng theo các cột cấu hình (bỏ qua `name`)."""
	key = lambda rows: [tuple(str(r.get(c["fieldname"]) or "").strip() for c in f["columns"]) for r in _table_list(rows)]
	return key(a) == key(b)


def _table_text(f, rows, sep="\n"):
	"""Bảng con → chữ: mỗi dòng "Nhãn: giá trị, …" (bỏ ô trống); các dòng nối bằng `sep`."""
	lines = []
	for r in _table_list(rows):
		parts = [
			f"{c['label']}: {_sign_value_vi(c, r.get(c['fieldname']))}"
			for c in f["columns"] if str(r.get(c["fieldname"]) or "").strip()
		]
		if parts:
			lines.append(", ".join(parts))
	return sep.join(lines)


def _value_text(f, value):
	"""Giá trị 1 field dạng chữ (Excel / so sánh): bảng con → _table_text, còn lại như _fmt."""
	return _table_text(f, value) if _is_table(f) else _fmt(value)


def _clean_table_value(f, value, employee):
	"""Làm sạch giá trị bảng con NV / HR gửi lên → (rows, errors). Dùng chung cho trang www + Desk.

	- chỉ giữ cột cấu hình; chuẩn hoá chữ; Int phải là số; Date → ISO; Select ∈ options;
	- bỏ dòng mà mọi ô đều trống; quá `max_rows` → lỗi; cột bắt buộc trống → lỗi;
	- `name` chỉ giữ khi đúng là dòng con của chính NV đó (để Sync sửa đúng dòng), không thì thành dòng mới.
	"""
	errors = []
	if value not in (None, "") and not isinstance(value, (list, str)):
		return [], [_("{0}: invalid data").format(f["label"])]
	own = {r["name"] for r in _employee_table_rows(employee, f)}
	rows, used = [], set()
	for raw in _table_list(value):
		row = {}
		for c in f["columns"]:
			v = raw.get(c["fieldname"])
			row[c["fieldname"]] = _normalize_text(c, "" if v is None else str(v).strip())
		for c in f["columns"]:
			# Cột ẩn (vd THCS/THPT → Trường, Ngành, Năm TN): xoá trắng TRƯỚC khi kiểm, để giá trị còn sót
			# (nhập trước khi đổi trình độ) không gây lỗi cho ô NV không nhìn thấy.
			if _column_hidden(f, c, row):
				row[c["fieldname"]] = ""
				continue
			v = row[c["fieldname"]]
			label = f"{f['label']} – {c['label']}"
			if v and c["fieldtype"] == "Int":
				if not re.fullmatch(r"\d{1,9}", v):
					errors.append(_("{0}: {1} is not a valid number").format(label, v))
			elif v and c["fieldtype"] == "Float":
				try:
					float(v)
				except ValueError:
					errors.append(_("{0}: {1} is not a valid number").format(label, v))
			elif v and c["fieldtype"] == "Date":
				try:
					v = frappe.utils.getdate(v).isoformat()
				except Exception:
					errors.append(_("{0}: {1} is not a valid date").format(label, v))
			elif v and c["fieldtype"] == "Select" and v not in (c.get("options") or []):
				errors.append(_("{0}: {1} is not a valid option").format(label, v))
			row[c["fieldname"]] = v
		if not any(row.values()):
			continue
		for c in f["columns"]:
			if _column_required(f, c, row) and not row[c["fieldname"]]:
				errors.append(_("{0} – row {1}: {2} is required").format(f["label"], len(rows) + 1, c["label"]))
		name = raw.get("name")
		if name in own and name not in used:
			used.add(name)
			row = {"name": name, **row}
		rows.append(row)
	if len(rows) > f["max_rows"]:
		errors.append(_("{0}: at most {1} rows").format(f["label"], f["max_rows"]))
	return rows, errors


# Built-in patterns for the preset validation types.
_VALIDATION_PATTERNS = {
	"Digits": (r"^\d+$", "chỉ gồm chữ số"),
	"Phone": (r"^0\d{9}$", "số điện thoại VN 10 số, bắt đầu bằng 0"),
	"Email": (r"^[^@\s]+@[^@\s]+\.[^@\s]+$", "email hợp lệ"),
	"CCCD": (r"^\d{12}$", "đúng 12 chữ số"),
	"CMND": (r"^\d{9}$", "đúng 9 chữ số"),
}


# Tự chuẩn hoá chữ NV/HR nhập (16/10/2026). Cùng quy tắc với normalizeText() trên trang www — sửa
# một nơi thì sửa cả hai. Chỉ field chữ widget Auto, trừ Email.
_NORMALIZE_TYPES = {"Data", "Small Text", "Text", "Long Text"}


# Chèn dấu cách giữa CHỮ và SỐ khi phần chữ ≥ 2 ký tự và có chữ thường: "Xóm1" → "Xóm 1";
# giữ nguyên mã như "B2", "TDP1", "ABC123".
_WORD_DIGIT = re.compile(r"(?<![^\W\d_])([^\W\d_]{2,})(?=\d)")


_EMAIL_LIKE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# Chữ cái đầu câu: đầu ô / sau . ! ? … + khoảng trắng / đầu dòng; bỏ qua ngoặc, nháy mở trước chữ.
_SENTENCE_START = re.compile(r"(^|[.!?…]\s+|\n)([\"'“‘(\[]*)([^\W\d_])")


def _normalize_text(f, value):
	"""NFC, gộp khoảng trắng, chèn dấu cách chữ–số, viết hoa ký tự đầu của cả ô. Theo Validation:
	- "Capitalize Each Word": hoa ký tự đầu MỖI từ, giữ nguyên phần còn lại ("thôn TDP1" → "Thôn TDP1");
	- "Sentence Case": hoa ký tự đầu MỖI câu (đầu ô, sau . ! ? …, đầu mỗi dòng) — cho ô nhập tự do.
	("Person Name" đã bỏ 16/10/2026 — trùng với Capitalize Each Word.)

	Không đụng: field không phải chữ, widget khác Auto, validation Email.
	"""
	import unicodedata

	if value is None or not isinstance(value, str):
		return value
	if f.get("fieldtype") not in _NORMALIZE_TYPES or (f.get("widget") or "Auto") != "Auto":
		return value
	# Email (theo Validation, hoặc giá trị trông như email dù field chưa gán Validation Email): chỉ bỏ khoảng trắng.
	if (f.get("validation") or "") == "Email" or _EMAIL_LIKE.match(value.strip()):
		return value.strip()
	v = unicodedata.normalize("NFC", value)
	multiline = f.get("fieldtype") != "Data"
	lines = v.split("\n") if multiline else [v]
	lines = [re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in lines]
	v = "\n".join(ln for ln in lines) if multiline else lines[0]
	v = v.strip()
	v = _WORD_DIGIT.sub(lambda m: m.group(1) + " " if any(c.islower() for c in m.group(1)) else m.group(1), v)
	if (f.get("validation") or "") == "Capitalize Each Word":
		return "\n".join(" ".join(w[:1].upper() + w[1:] for w in ln.split(" ")) for ln in v.split("\n"))
	if (f.get("validation") or "") == "Sentence Case":
		return _SENTENCE_START.sub(lambda m: m.group(1) + m.group(2) + m.group(3).upper(), v)
	return v[:1].upper() + v[1:]


def _validate_value(field, value):
	"""Return an error message (str) if `value` fails the field's validation,
	else None. Empty values pass here (handled by the required check)."""
	import re

	val = "" if value is None else str(value).strip()
	if val == "":
		return None

	label = field.get("label") or field.get("fieldname")
	min_len = field.get("min_length") or 0
	max_len = field.get("max_length") or 0
	if min_len and len(val) < min_len:
		return _("{0}: tối thiểu {1} ký tự").format(label, min_len)
	if max_len and len(val) > max_len:
		return _("{0}: tối đa {1} ký tự").format(label, max_len)

	vtype = field.get("validation") or ""
	if not vtype:
		return None

	if vtype in ("Past", "Future"):
		try:
			dv = frappe.utils.getdate(val)
		except Exception:
			return None  # not a parseable date → don't block
		tv = frappe.utils.getdate(frappe.utils.today())
		if vtype == "Past" and dv > tv:
			return _("{0}: không được ở tương lai").format(label)
		if vtype == "Future" and dv < tv:
			return _("{0}: không được ở quá khứ").format(label)
		return None

	if vtype == "Regex":
		pattern = field.get("regex") or ""
		if not pattern:
			return None
		try:
			ok = re.match(pattern, val) is not None
		except re.error:
			return None  # invalid config regex → don't block the employee
		return None if ok else _("{0}: không đúng định dạng").format(label)

	spec = _VALIDATION_PATTERNS.get(vtype)
	if not spec:
		return None
	pattern, desc = spec
	if re.match(pattern, val) is None:
		return _("{0}: phải là {1}").format(label, desc)
	return None


def _apply_cccd_expiry(config, values, employee_id):
	"""Ghi ngày hết hạn CCCD vào `values` (dict data_json) = tính từ ngày sinh + ngày cấp.

	Ngày sinh / ngày cấp lấy trong `values` nếu có (NV vừa khai), không thì lấy Employee.
	Chỉ khi field ngày hết hạn có trên trang và không read_only. Thuật toán: api/employee/cccd_expiry.py.
	"""
	fields = {f["fieldname"]: f for sec in config["sections"] for f in sec["fields"]}
	f = fields.get(CCCD_EXPIRY_FIELD)
	if not f or f.get("read_only") or f.get("custom"):
		return
	emp = frappe.db.get_value("Employee", employee_id, [CCCD_DOB_FIELD, CCCD_ISSUE_FIELD], as_dict=True) or {}
	dob = values[CCCD_DOB_FIELD] if CCCD_DOB_FIELD in values else emp.get(CCCD_DOB_FIELD)
	issue = values[CCCD_ISSUE_FIELD] if CCCD_ISSUE_FIELD in values else emp.get(CCCD_ISSUE_FIELD)
	values[CCCD_EXPIRY_FIELD] = cccd_expiry_iso(dob, issue)


def _portal_address_errors(config, clean, employee_id):
	"""Lỗi cặp Tỉnh/Xã NV gửi từ trang www: tỉnh phải có trong danh mục, xã phải thuộc tỉnh.

	Trang dùng ô gõ-để-tìm (chỉ nhận giá trị trong danh sách) — đây là chốt chặn server cho mọi
	request gửi thẳng. Chỉ kiểm cặp có giá trị KHÁC Employee hiện tại: hồ sơ còn tên trước sáp
	nhập mà NV không đụng tới thì không bị chặn. Field read_only (không có trong `clean`) lấy
	giá trị Employee.
	"""
	pairs = _address_pairs(config)
	if not pairs:
		return []
	fields = {f["fieldname"]: f for sec in config["sections"] for f in sec["fields"]}
	real = [fn for pair in pairs for fn in pair if fn and not fields[fn].get("custom")]
	now = (frappe.db.get_value("Employee", employee_id, real, as_dict=True) or {}) if real else {}

	from customize_erpnext.api.vn_address_search.vn_address_search_api import get_address_error

	errors = []
	for prov, ward in pairs:
		keys = [k for k in (prov, ward) if k]
		value = {k: str(clean.get(k, now.get(k)) or "").strip() for k in keys}
		if not any(value[k] != str(now.get(k) or "").strip() for k in keys):
			continue
		err = get_address_error(value.get(prov, ""), value[ward])
		if err:
			errors.append(f"{fields[ward]['label']}: {err}")
	return errors


def _documents_snapshot(checked, setting=None):
	"""Danh sách Setting + đánh dấu hồ sơ NV tick (`checked` = tên hồ sơ). Setting trống → []."""
	if isinstance(checked, str):
		try:
			checked = json.loads(checked or "[]")
		except ValueError:
			checked = []
	ticked = {str(x).strip() for x in checked or [] if isinstance(x, str)}
	return [{**d, "checked": 1 if d["document"] in ticked else 0} for d in _setting_documents(setting)]


def _clean_documents(value):
	"""Bản chụp hồ sơ HR gửi từ Desk → list sạch [{document, required, checked}] (bỏ dòng không tên)."""
	if isinstance(value, str):
		try:
			value = json.loads(value or "[]")
		except ValueError:
			value = []
	out = []
	for r in value if isinstance(value, list) else []:
		if isinstance(r, dict) and str(r.get("document") or "").strip():
			out.append({
				"document": str(r["document"]).strip(),
				"required": 1 if frappe.utils.cint(r.get("required")) else 0,
				"checked": 1 if frappe.utils.cint(r.get("checked")) else 0,
			})
	return out


def _document_status(items):
	"""(status, [hồ sơ bắt buộc chưa nộp]); chưa có bản chụp → ("", [])."""
	if not items:
		return "", []
	missing = [d["document"] for d in items if d.get("required") and not d.get("checked")]
	return ("Documents Missing" if missing else "Documents Complete"), missing


def _status_text_vi(items):
	"""Dòng tình trạng in trên phiếu: "Đủ" / "Thiếu: A; B"."""
	status, missing = _document_status(items)
	if not status:
		return ""
	return "Thiếu: " + "; ".join(missing) if missing else "Đủ"


def _fmt_date_vn(value):
	"""'2001-07-29' → '29/07/2001'; giá trị không phải ngày → giữ nguyên."""
	try:
		return frappe.utils.getdate(value).strftime("%d/%m/%Y")
	except Exception:
		return str(value)


def _fmt(value):
	if value is None:
		return ""
	return str(value)


# Thông tin liên hệ khẩn cấp (field chuẩn Employee) — Info for Sign ghép thành 1 dòng.
_EMERGENCY_FIELDS = ("person_to_be_contacted", "relation", "emergency_phone_number")


# Số CCCD + ngày cấp → 1 dòng "CCCD": "<số>, cấp ngày dd/mm/yyyy" (ngày hết hạn vẫn dòng riêng).
_CCCD_FIELDS = ("custom_id_card_no", CCCD_ISSUE_FIELD)


# Nhóm field gộp thành 1 dòng: kind → (fieldnames, nhãn dòng). Dòng đặt ở chỗ field đầu tiên của nhóm.
# Giấy phép lái xe + tình trạng (khi "Chưa") → "Chưa (Đang đợi cấp)".
_LICENSE_FIELDS = ("custom_driving_license", "custom_driving_license_status")


# Size áo + size dép → "Áo: M – Dép: 6-7".
_UNIFORM_FIELDS = ("custom_shirt_size", "custom_shoe_size")


_SIGN_GROUPS = {
	"emergency": (_EMERGENCY_FIELDS, "Liên hệ khẩn cấp"),
	"cccd": (_CCCD_FIELDS, "CCCD"),
	"license": (_LICENSE_FIELDS, "Giấy phép lái xe"),
	"uniform": (_UNIFORM_FIELDS, "Size áo / dép"),
}


def _sign_join(kind, parts):
	"""Ghép giá trị của 1 dòng. parts = [(field, giá trị đã định dạng)] theo thứ tự config."""
	if kind == "address":
		# Như custom_*_address_full: chi tiết (thôn/số nhà) → xã → tỉnh.
		rank = {"Address Ward": 1, "Address Province": 2}
		ordered = sorted(parts, key=lambda p: rank.get(p[0].get("widget"), 0))
		return ", ".join(v for _f, v in ordered if v)
	if kind == "emergency":
		by = {f["fieldname"]: v for f, v in parts}
		name, rel, phone = by.get("person_to_be_contacted"), by.get("relation"), by.get("emergency_phone_number")
		head = " ".join(x for x in (name, f"({rel})" if rel else "") if x)
		return " - ".join(x for x in (head, phone) if x)
	if kind == "cccd":
		by = {f["fieldname"]: v for f, v in parts}
		no, issued = by.get("custom_id_card_no"), by.get(CCCD_ISSUE_FIELD)  # ngày đã dd/mm/yyyy (_sign_value_vi)
		return ", ".join(x for x in (no, f"cấp ngày {issued}" if issued else "") if x)
	if kind == "license":
		by = {f["fieldname"]: v for f, v in parts}
		lic, st = by.get(_LICENSE_FIELDS[0]), by.get(_LICENSE_FIELDS[1])
		return f"{lic} ({st})" if lic and st else (lic or st or "")
	if kind == "uniform":
		by = {f["fieldname"]: v for f, v in parts}
		shirt, shoe = by.get(_UNIFORM_FIELDS[0]), by.get(_UNIFORM_FIELDS[1])
		return " – ".join(x for x in (f"Áo: {shirt}" if shirt else "", f"Dép: {shoe}" if shoe else "") if x)
	return parts[0][1] if parts else ""


def _sign_value_vi(f, value):
	"""Giá trị hiển thị tiếng Việt: Select dịch theo bảng vi, Date dd/mm/yyyy, Check Có/Không."""
	if value in (None, ""):
		return ""
	ft = f.get("fieldtype")
	if ft == "Select":
		return _(str(value), lang="vi")
	if ft == "Date":
		try:
			return frappe.utils.getdate(value).strftime("%d/%m/%Y")
		except Exception:
			return str(value)
	if ft == "Check":
		return "Có" if frappe.utils.cint(value) else "Không"
	return str(value).strip()
