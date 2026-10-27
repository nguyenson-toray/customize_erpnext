"""Cấu hình field từ Employee Self Update Info Setting → config cho trang www / Desk / phiếu.

Tách nguyên văn từ self_update_info_api.py (27/10/2026) — mặt tiền đó re-export mọi tên."""

import frappe
from frappe import _

from .rules import (
	COMMITMENT_TEXT,
	SETTING_DT,
	_ALLOWED_FIELDTYPES,
	_ALLOWED_TABLES,
	_FIELD_DEPENDS,
	_LINK_AS_SELECT,
	_TABLE_COLUMN_TYPES,
	_TABLE_MAX_ROWS,
	_TABLE_REQUIRED_IF,
)


def _option_labels(options, overrides=None):
	"""{giá trị: nhãn hiện trên trang www} cho Select — chỉ option có nhãn khác chính nó.
	Giá trị lưu + Sync vẫn là giá trị gốc (vd Married → "Đã kết hôn").
	`overrides` = cột "Option Labels" của dòng Setting, mỗi dòng `giá trị | nhãn` (vd size dép
	`6-7 | Size 6-7 · dép thường 38-39 · chân 24.5-25 cm`) — ưu tiên hơn bản dịch vi; giá trị
	không có trong options bị bỏ qua. Phiếu PDF / Info for Sign KHÔNG dùng nhãn này (in gọn, _sign_value_vi)."""
	opts = [o for o in options or [] if o]
	out = {}
	for o in opts:
		vi = _(o, lang="vi")
		if vi and vi != o:
			out[o] = vi
	for line in (overrides or "").splitlines():
		if "|" not in line:
			continue
		v, label = (x.strip() for x in line.split("|", 1))
		if v in opts and label:
			out[v] = label
	return out


def _get_setting():
	return frappe.get_cached_doc(SETTING_DT)


def _commitment_html(setting=None):
	"""Câu cam kết cho trang www + phiếu PDF/PNG: Setting.commitment_text (trống → câu mặc định),
	đã escape HTML, mỗi lần xuống dòng thành <br> (giữ cả dòng trống ở đầu/cuối HR cố ý gõ)."""
	text = (setting or _get_setting()).get("commitment_text") or ""
	if not text.strip():
		text = COMMITMENT_TEXT
	return "<br>".join(frappe.utils.escape_html(line) for line in text.replace("\r\n", "\n").split("\n"))


def _selected_rows(setting):
	# Only rows explicitly enabled (enable=1) are exposed on the public page.
	# This single chokepoint governs rendering, save validation and export.
	return [r for r in (setting.selected_fields or []) if r.employee_fieldname and r.enable]


def _build_config():
	"""Resolve the configured fields against the live Employee meta."""
	setting = _get_setting()
	rows = _selected_rows(setting)
	meta = frappe.get_meta("Employee")
	df_by_name = {df.fieldname: df for df in meta.fields}

	sections = {}
	order = []
	for row in rows:
		# Skip fields explicitly disabled via the "Enable" toggle.
		if not row.enable:
			continue
		if row.is_custom:
			# Free-form field that does NOT exist on Employee — defined entirely
			# by the row. Stored in the submission only.
			fieldtype = row.custom_fieldtype or "Data"
			if fieldtype not in _ALLOWED_FIELDTYPES:
				continue
			options = None
			if fieldtype == "Select" and row.custom_options:
				options = [o.strip() for o in row.custom_options.split("\n")]
			field = {
				"fieldname": row.employee_fieldname,
				"label": row.label_vi or row.employee_fieldname,
				"employee_label": row.label_vi or row.employee_fieldname,
				"detail": row.detail or "",
				"placeholder": row.placeholder or "",
				"fieldtype": fieldtype,
				"options": options,
				"option_labels": _option_labels(options, row.get("option_labels")),
				"required": bool(row.required),
				"read_only": bool(row.read_only),
				"widget": "Auto",
				"width": _layout_width(row),
				"custom": True,
				"auto_fill": bool(row.auto_fill_data),
				# Tick "Info for Sign" trong Setting → field có trong Excel Info for Sign.
				"info_for_sign": bool(row.get("info_for_sign")),
				**_validation_meta(row),
			}
		elif (df_by_name.get(row.employee_fieldname) or {}).get("fieldtype") == "Table":
			# Bảng con: chỉ allow-list, cột theo "Table Columns" (trống → mặc định của _ALLOWED_TABLES).
			df = df_by_name[row.employee_fieldname]
			if df.fieldname not in _ALLOWED_TABLES:
				continue
			columns = _table_columns(row, df)
			if not columns:
				continue
			field = {
				"fieldname": df.fieldname,
				"label": row.label_vi or df.label or df.fieldname,
				"employee_label": df.label or df.fieldname,
				"detail": row.detail or "",
				"placeholder": row.placeholder or "",
				"fieldtype": "Table",
				"options": df.options,  # child DocType
				"columns": columns,
				"required_if": _table_required_if(df.fieldname, columns),
				"max_rows": frappe.utils.cint(row.get("max_rows")) or _TABLE_MAX_ROWS,
				"required": bool(row.required),
				"read_only": bool(row.read_only),
				"widget": "Auto",
				"width": "Full",  # bảng con luôn cả hàng
				"custom": False,
				"auto_fill": bool(row.auto_fill_data),
				"info_for_sign": bool(row.get("info_for_sign")),
				**_validation_meta(row),
			}
		else:
			df = df_by_name.get(row.employee_fieldname)
			if not df or df.fieldtype not in _ALLOWED_FIELDTYPES:
				# Field removed/renamed on Employee, or type unsupported — skip.
				continue

			options = None
			fieldtype = df.fieldtype
			if df.fieldtype == "Select" and df.options:
				options = [o for o in df.options.split("\n")]
			elif df.fieldtype == "Link" and df.options in _LINK_AS_SELECT:
				# Danh mục nhỏ (Gender) → dropdown; giá trị vẫn là tên bản ghi Link (Male/Female).
				fieldtype = "Select"
				options = [""] + [o for o in _LINK_AS_SELECT[df.options] if frappe.db.exists(df.options, o)]
			elif df.fieldtype == "Link":
				options = df.options  # the linked doctype name

			field = {
				"fieldname": df.fieldname,
				# UI label: prefer the Vietnamese label, fall back to the Employee
				# field's default label.
				"label": row.label_vi or df.label or df.fieldname,
				# Excel/import label: always the Employee field's own label so the
				# exported file can be re-imported into Employee (Data Import).
				"employee_label": df.label or df.fieldname,
				# Optional guidance shown under the label on the page.
				"detail": row.detail or "",
				# Optional hint text inside the empty input.
				"placeholder": row.placeholder or "",
				"fieldtype": fieldtype,
				"options": options,
				"option_labels": _option_labels(options, row.get("option_labels")) if fieldtype == "Select" else {},
				"required": bool(row.required),
				"read_only": bool(row.read_only),
				"widget": row.widget or "Auto",
				"width": _layout_width(row),
				"custom": False,
				"auto_fill": bool(row.auto_fill_data),
				# Tick "Info for Sign" trong Setting → field có trong Excel Info for Sign.
				"info_for_sign": bool(row.get("info_for_sign")),
				**_validation_meta(row),
			}

		sec = row.section_label or "General"
		if sec not in sections:
			sections[sec] = {"label": sec, "fields": []}
			order.append(sec)
		sections[sec]["fields"].append(field)

	present = {f["fieldname"] for s in order for f in sections[s]["fields"]}
	for s in order:
		for f in sections[s]["fields"]:
			dep = _FIELD_DEPENDS.get(f["fieldname"])
			if dep and dep[0] in present:
				f["depends_on"] = {"field": dep[0], "values": list(dep[1])}
	return {"sections": [sections[s] for s in order]}


def _layout_width(row):
	"""Setting → "Width on Form": "Half" = 2 field Half liền nhau cùng 1 hàng trên trang www; còn lại "Full"."""
	return "Half" if (row.get("layout_width") or "") == "Half" else "Full"


def _table_columns(row, df):
	"""Cột của field bảng con: [{fieldname, label, fieldtype, options, required, placeholder}].

	"Table Columns" của dòng Setting: mỗi dòng `fieldname | Nhãn | bắt buộc(0/1)`; trống → mặc định
	_ALLOWED_TABLES. Cột lạ / kiểu không hỗ trợ / trùng bị bỏ qua.
	"""
	spec = []
	for line in (row.get("table_columns") or "").splitlines():
		parts = [p.strip() for p in line.split("|")]
		if parts and parts[0]:
			spec.append((parts[0], parts[1] if len(parts) > 1 else "", frappe.utils.cint(parts[2]) if len(parts) > 2 else 0))
	if not spec:
		spec = _ALLOWED_TABLES.get(df.fieldname, ())
	child = frappe.get_meta(df.options)
	cols = []
	for fn, label, req in spec:
		cdf = child.get_field(fn)
		if not cdf or cdf.fieldtype not in _TABLE_COLUMN_TYPES or any(c["fieldname"] == fn for c in cols):
			continue
		cols.append({
			"fieldname": fn,
			"label": label or _(cdf.label, lang="vi") or fn,
			"fieldtype": cdf.fieldtype,
			"options": (cdf.options or "").split("\n") if cdf.fieldtype == "Select" else None,
			"option_labels": _option_labels((cdf.options or "").split("\n")) if cdf.fieldtype == "Select" else {},
			"required": bool(req),
			"placeholder": cdf.placeholder or "",
		})
	return cols


def _table_required_if(fieldname, columns):
	"""_TABLE_REQUIRED_IF của bảng, chỉ giữ cột có trong cấu hình; thiếu cột điều kiện → None."""
	rule = _TABLE_REQUIRED_IF.get(fieldname)
	have = {c["fieldname"] for c in columns}
	if not rule or rule["column"] not in have:
		return None
	cols = [c for c in rule["columns"] if c in have]
	req = [c for c in rule.get("required", rule["columns"]) if c in cols]
	return {"column": rule["column"], "values": list(rule["values"]), "columns": cols, "required": req} if cols else None


def _is_table(f):
	return f.get("fieldtype") == "Table"


def _employee_scalar_fields(config):
	"""Field thật trên Employee đọc được bằng get_value (bỏ field custom + bảng con)."""
	return [
		f["fieldname"] for sec in config["sections"] for f in sec["fields"]
		if not f.get("custom") and not _is_table(f)
	]


def _validation_meta(row):
	"""Validation attributes copied from a config row into the field dict."""
	return {
		"validation": row.validation or "",
		"min_length": int(row.min_length or 0),
		"max_length": int(row.max_length or 0),
		"regex": row.regex or "",
	}


def _config_fieldnames(config):
	return [f["fieldname"] for sec in config["sections"] for f in sec["fields"]]


def _setting_documents(setting=None):
	"""Setting → Document Checklist: [{document, required}] (dòng trống bỏ qua)."""
	rows = (setting or _get_setting()).get("document_checklist") or []
	return [
		{"document": (r.document or "").strip(), "required": 1 if r.required else 0}
		for r in rows if (r.document or "").strip()
	]


def _info_for_sign_wanted(config):
	"""Fieldname được tick "Info for Sign" trong Setting (selected_fields)."""
	return {f["fieldname"] for sec in config["sections"] for f in sec["fields"] if f.get("info_for_sign")}


def _info_for_sign_config(config):
	"""Config chỉ giữ field tick "Info for Sign" (cả field Employee lẫn field custom); bỏ Section rỗng.

	Báo lỗi như Excel / PDF gộp khi chưa tick field nào.
	"""
	sections = [
		{**sec, "fields": [f for f in sec["fields"] if f.get("info_for_sign")]} for sec in config["sections"]
	]
	sections = [sec for sec in sections if sec["fields"]]
	if not sections:
		frappe.throw(
			_("No field is ticked \"Info for Sign\" in Employee Self Update Info Setting."),
			title=_("Info for Sign"),
		)
	return {**config, "sections": sections}


def _address_pairs(config):
	"""[(province_fieldname, ward_fieldname)] — ghép theo section, giống trang www
	(mỗi section có 1 field widget Address Province dẫn các field Address Ward)."""
	pairs = []
	for sec in config["sections"]:
		prov = None
		for f in sec["fields"]:
			if f.get("widget") == "Address Province":
				prov = f["fieldname"]
			elif f.get("widget") == "Address Ward":
				pairs.append((prov, f["fieldname"]))
	return pairs
