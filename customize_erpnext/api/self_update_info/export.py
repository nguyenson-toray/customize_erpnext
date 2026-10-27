"""Xuất Excel (All Info) + Info for Sign (Excel, PDF gộp, PDF tách từng NV).

Tách nguyên văn từ self_update_info_api.py (27/10/2026) — mặt tiền đó re-export mọi tên."""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from .rules import (
	INFO_DT,
	REMARKS_KEY,
)
from .config import (
	_build_config,
	_employee_scalar_fields,
	_info_for_sign_config,
	_info_for_sign_wanted,
	_is_table,
)
from .values import (
	_SIGN_GROUPS,
	_employee_table_rows,
	_employee_tables,
	_fmt,
	_sign_join,
	_sign_value_vi,
	_value_text,
)
from .access import (
	_require_hr,
)
from .receipt import (
	_hr_receipt_pdf,
	_receipt_base,
	_strip_section_no,
)


@frappe.whitelist()
def download_excel(names=None, export_type="All Info", file_format="Excel"):
	"""Export submissions to xlsx with two sheets — "New Data" (values submitted
	by employees) and "Old Data" (current Employee values).

	The file is designed to be re-imported into Employee via Data Import, so:
	  - the first column is "ID" (= Employee name → maps to the record on update),
	  - field column headers are the Employee field's own label (NOT label_vi),
	  - no Status / Submitted On columns (they would collide with Employee fields).

	"New Data" is the first sheet (the importable one); changed cells are
	highlighted. `names` = JSON list of Employee Self Update Info names, or None
	for all.

	`export_type="Info for Sign"` → file riêng, xem _download_info_for_sign;
	`file_format` (chỉ Info for Sign): "PDF Split" → mỗi bản ghi 1 PDF (_download_info_for_sign_pdf_split),
	"PDF Pages" → cùng các phiếu đó gộp 1 file PDF, mỗi bản ghi 1 trang,
	"PDF" → gộp 1 file danh sách ký (_download_info_for_sign_pdf), còn lại → Excel.
	"""
	_require_hr()
	if export_type == "Info for Sign":
		if file_format == "PDF Split":
			return _download_info_for_sign_pdf_split(names)
		if file_format == "PDF Pages":
			return _download_info_for_sign_pdf_split(names, merge=True)
		if file_format == "PDF":
			return _download_info_for_sign_pdf(names)
		return _download_info_for_sign(names)
	import io

	from openpyxl import Workbook
	from openpyxl.styles import Font, PatternFill

	if isinstance(names, str):
		names = json.loads(names or "null")

	filters = {"name": ["in", names]} if names else {}
	records = frappe.get_all(
		INFO_DT,
		filters=filters,
		fields=["name", "employee", "employee_name", "data_json"],
		order_by="employee asc",
	)

	config = _build_config()
	fields = [f for sec in config["sections"] for f in sec["fields"]]
	# Headers use the Employee field label so the file can be imported back.
	# A trailing "Ghi chú" column holds the employee's free-text remarks.
	header = ["ID", "Employee Name"] + [f["employee_label"] for f in fields] + ["Ghi chú (nhân viên)"]
	real_fieldnames = _employee_scalar_fields(config)

	bold = Font(bold=True)
	changed_fill = PatternFill(start_color="FFF3B0", end_color="FFF3B0", fill_type="solid")

	# Pre-compute old (Employee) and new (submitted) value maps per record.
	rows_data = []
	for rec in records:
		saved = json.loads(rec.get("data_json") or "{}")
		old_vals = frappe.db.get_value(
			"Employee", rec.employee, real_fieldnames, as_dict=True
		) or {} if real_fieldnames else {}
		old_vals = {**old_vals, **_employee_tables(rec.employee, config)}
		rows_data.append({"rec": rec, "saved": saved, "old": old_vals})

	def _write_header(ws):
		ws.append(header)
		for cell in ws[1]:
			cell.font = bold

	wb = Workbook()

	# Sheet 1 — New Data (submitted values; this is the importable sheet).
	ws_new = wb.active
	ws_new.title = "New Data"
	_write_header(ws_new)
	for rd in rows_data:
		rec, saved, old_vals = rd["rec"], rd["saved"], rd["old"]
		row = [rec.employee, rec.employee_name]
		row += [_value_text(f, saved.get(f["fieldname"])) for f in fields]
		row.append(_fmt(saved.get(REMARKS_KEY)))
		ws_new.append(row)
		excel_row = ws_new.max_row
		for idx, f in enumerate(fields):
			fn = f["fieldname"]
			if fn in saved and _value_text(f, saved.get(fn)) != _value_text(f, old_vals.get(fn)):
				ws_new.cell(row=excel_row, column=3 + idx).fill = changed_fill

	# Sheet 2 — Old Data (current values on the Employee record, for reference).
	ws_old = wb.create_sheet("Old Data")
	_write_header(ws_old)
	for rd in rows_data:
		rec = rd["rec"]
		row = [rec.employee, rec.employee_name]
		row += [_value_text(f, rd["old"].get(f["fieldname"])) for f in fields]
		row.append("")  # no "old" remarks
		ws_old.append(row)

	buf = io.BytesIO()
	wb.save(buf)
	frappe.response["filename"] = "employee_self_update_info.xlsx"
	frappe.response["filecontent"] = buf.getvalue()
	frappe.response["type"] = "binary"


@frappe.whitelist()
def get_info_for_sign_fields():
	"""Các dòng sẽ có trong Info for Sign (để dialog Excel hiện cho HR biết): [nhãn].

	Theo cờ "Info for Sign" của từng field trong Setting; địa chỉ / liên hệ khẩn cấp đã gộp.
	"""
	_require_hr()
	config = _build_config()
	wanted = _info_for_sign_wanted(config)
	return [label for label, _fs, _k in _sign_items(config, wanted)] if wanted else []


def _sign_labels(config):
	"""{fieldname: nhãn tiếng Việt} cho Info for Sign.

	Nhãn trùng giữa các Section (Tỉnh / Xã / Chi tiết… của "Địa chỉ thường trú" và
	"Địa chỉ hiện tại") → ghép tên Section: "Địa chỉ thường trú - Tỉnh".
	"""
	from collections import Counter

	items = [
		(sec["label"], f["fieldname"], _(f["label"], lang="vi"))
		for sec in config["sections"]
		for f in sec["fields"]
		if f["fieldname"] not in ("employee", "name")
	]
	dup = Counter(label for _sec, _fn, label in items)
	return {
		fn: (f"{_strip_section_no(sec)} - {label}" if dup[label] > 1 else label)
		for sec, fn, label in items
	}


def _sign_items(config, wanted):
	"""Các dòng của Info for Sign theo thứ tự config: [(nhãn, [field], kiểu)].

	- Section có ô tỉnh (widget Address Province) → 1 dòng "address" mang tên Section,
	  gồm mọi field đã chọn của Section đó;
	- nhóm trong _SIGN_GROUPS (liên hệ khẩn cấp, số CCCD + ngày cấp) → 1 dòng, đặt ở chỗ field đầu tiên;
	- còn lại mỗi field 1 dòng.
	`wanted` = set fieldname được chọn, None = tất cả.
	"""
	labels = _sign_labels(config)
	pick = lambda f: f["fieldname"] not in ("employee", "name") and (wanted is None or f["fieldname"] in wanted)
	group_of = {fn: kind for kind, (fns, _l) in _SIGN_GROUPS.items() for fn in fns}
	members = {
		kind: [f for sec in config["sections"] for f in sec["fields"] if pick(f) and f["fieldname"] in fns]
		for kind, (fns, _l) in _SIGN_GROUPS.items()
	}
	items = []
	for sec in config["sections"]:
		fs = [f for f in sec["fields"] if pick(f)]
		if not fs:
			continue
		if any(f.get("widget") == "Address Province" for f in sec["fields"]):
			items.append((_strip_section_no(sec["label"]), fs, "address"))
			continue
		for f in fs:
			kind = group_of.get(f["fieldname"])
			if kind:
				if f is members[kind][0]:
					items.append((_SIGN_GROUPS[kind][1], members[kind], kind))
				continue
			items.append((labels[f["fieldname"]], [f], "field"))
	return items


INFO_FOR_SIGN_HEADER = ("STT", "Nhân viên", "Thông tin", "Nội dung", "Ghi chú", "Chữ ký")


INFO_FOR_SIGN_TITLE = "DANH SÁCH XÁC NHẬN THÔNG TIN NHÂN VIÊN"


def _info_for_sign_people(names):
	"""Dữ liệu chung cho Info for Sign (Excel + PDF): ([(mã NV, họ tên, [(nhãn, nội dung)])], tên công ty).

	Nội dung = thông tin mới (NV khai), mới trống → Employee; cả hai trống → vẫn có dòng, nội dung "".
	"""
	if isinstance(names, str):
		names = json.loads(names or "null")
	config = _build_config()
	wanted = _info_for_sign_wanted(config)
	if not wanted:
		frappe.throw(
			_("No field is ticked \"Info for Sign\" in Employee Self Update Info Setting."),
			title=_("Info for Sign"),
		)
	items = _sign_items(config, wanted)
	real = [f["fieldname"] for _l, fs, _k in items for f in fs if not f.get("custom") and not _is_table(f)]
	tables = [f for _l, fs, _k in items for f in fs if _is_table(f)]

	filters = {"name": ["in", names]} if names else {}
	records = frappe.get_all(
		INFO_DT, filters=filters, fields=["name", "employee", "employee_name", "data_json"], order_by="employee asc"
	)
	people = []
	for rec in records:
		saved = json.loads(rec.data_json or "{}")
		old = (frappe.db.get_value("Employee", rec.employee, real, as_dict=True) or {}) if real else {}
		old = {**old, **{f["fieldname"]: _employee_table_rows(rec.employee, f) for f in tables}}
		lines = []
		for label, fs, kind in items:
			parts = []
			for f in fs:
				fn = f["fieldname"]
				new_s = _value_text(f, saved.get(fn)).strip()
				old_s = "" if f.get("custom") else _value_text(f, old.get(fn)).strip()
				parts.append((f, _sign_value_vi(f, new_s or old_s)))
			# Chưa có dữ liệu → VẪN in dòng, Nội dung để trống cho NV tự ghi tay bổ sung.
			lines.append((label, _sign_join(kind, parts)))
		people.append((rec.employee, rec.employee_name or "", lines))
	company = (
		frappe.defaults.get_global_default("company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or ""
	)
	return people, company


# PDF Info for Sign: A4 ngang, lề trên/dưới 10mm; trang 1 = tiêu đề + 4 NV, các trang sau 5 NV;
# mỗi trang là 1 bảng riêng → tên cột lặp lại; chân trang "Trang x/y". Cỡ chữ chung = lớn nhất mà
# không trang nào tràn (tìm nhị phân, dựng thử + đếm trang).
INFO_FOR_SIGN_PDF_FIRST = 4


INFO_FOR_SIGN_PDF_PER_PAGE = 5


# Tick quá nhiều mục (vd 17 dòng/NV) thì 4/5 NV không vừa ở cỡ chữ đọc được → lùi bố cục.
_SIGN_PDF_FALLBACK = ((3, 4), (2, 3), (1, 2), (1, 1))


_SIGN_PDF_MIN_FONT = 6.0   # px — dưới mức này coi như không đọc được, lùi bố cục


_SIGN_PDF_MAX_FONT = 16.0  # px — trần cỡ chữ; trang còn trống thì chữ lớn dần tới khi lấp đầy


_SIGN_PDF_COL_WIDTHS = (3.5, 13, 15.5, 38, 15.5, 14.5)   # % — cùng tỉ lệ cột Excel


_SIGN_PDF_SAMPLE_PAGES = 6   # số trang "nặng" nhất (+ trang 1) dùng để dò cỡ chữ


INFO_FOR_SIGN_PDF_MAX_RECORDS = 100   # PDF tối đa 100 phiếu/lần (user 16/10/2026); Excel không giới hạn


def _info_for_sign_pdf_pages(people, first=INFO_FOR_SIGN_PDF_FIRST, per=INFO_FOR_SIGN_PDF_PER_PAGE):
	rest = people[first:]
	return [people[:first]] + [rest[i:i + per] for i in range(0, len(rest), per)]


def _info_for_sign_pdf_html(pages, company, font_px):
	esc = frappe.utils.escape_html
	head = "".join(f"<th style='width:{w}%'>{esc(h)}</th>" for h, w in zip(INFO_FOR_SIGN_HEADER, _SIGN_PDF_COL_WIDTHS))
	today = frappe.utils.now_datetime().strftime("%d/%m/%Y")
	stt = 0
	blocks = []
	for i, page in enumerate(pages):
		body = []
		for emp, emp_name, lines in page:
			stt += 1
			n = len(lines) or 1
			who = esc(emp) + (f"<br>{esc(emp_name)}" if emp_name else "")
			for j, (label, value) in enumerate(lines or [("", "")]):
				cells = ""
				if j == 0:
					cells += f"<td class='c' rowspan='{n}'>{stt}</td><td class='c' rowspan='{n}'>{who}</td>"
				cells += f"<td>{esc(label)}</td><td>{esc(value).replace(chr(10), '<br>')}</td>"
				if j == 0:
					cells += f"<td rowspan='{n}'></td><td rowspan='{n}'></td>"
				body.append(f"<tr class='{'first' if j == 0 else ''}'>{cells}</tr>")
		title = ""
		if i == 0:
			title = (
				f"<div class='co'>{esc(company.upper())}</div><div class='ti'>{esc(INFO_FOR_SIGN_TITLE)}</div>"
				f"<div class='dt'>Ngày: {today}</div>"
			)
		brk = " style='page-break-after:always'" if i < len(pages) - 1 else ""
		blocks.append(f"<div class='pg'{brk}>{title}<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>")
	f = font_px
	return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  .print-format{{margin-top:15mm;margin-bottom:15mm;margin-left:15mm;margin-right:15mm}}
  body{{font-family:Arial,'Helvetica Neue',sans-serif;color:#111;margin:0;font-size:{f}px}}
  .co{{text-align:center;font-weight:bold;font-size:{f + 1}px}}
  .ti{{text-align:center;font-weight:bold;font-size:{f + 5}px;margin:2px 0}}
  .dt{{text-align:center;font-style:italic;font-size:{f}px;margin-bottom:6px}}
  table{{width:100%;border-collapse:collapse;table-layout:fixed}}
  /* line-height 1.1 + đệm 1px: dòng thấp nhất có thể → cùng số dòng/trang nhưng chữ lớn hơn. */
  th,td{{border:1px solid #808080;padding:1px 4px;line-height:1.1;vertical-align:middle;word-wrap:break-word}}
  th{{background:#DCE6F1;font-weight:bold;text-align:center}}
  td.c{{text-align:center}}
  tr.first td{{border-top:1.5px solid #333}}
  tr{{page-break-inside:avoid}}
</style></head><body>{''.join(blocks)}</body></html>"""


def _download_info_for_sign_pdf(names):
	"""PDF Info for Sign (cùng dữ liệu với Excel): A4 ngang, lề trên/dưới 10mm, chân trang "Trang x/y".

	Trang 1: tiêu đề + 4 NV; các trang sau: 5 NV; mỗi trang lặp lại tên cột. Cỡ chữ: tìm nhị phân
	(bước 0,5px, 5–16px) cỡ LỚN NHẤT mà số trang = số trang dự kiến (không trang nào tràn).
	Cỡ tốt nhất < 6px (tick quá nhiều mục) → lùi bố cục 3/4, 2/3, … (_SIGN_PDF_FALLBACK).
	get_pdf tắt JavaScript nên không tự co theo trang được.
	"""
	import io

	from frappe.utils.pdf import get_pdf
	from pypdf import PdfReader

	people, company = _info_for_sign_people(names)
	if not people:
		frappe.throw(_("No record to export."))
	if len(people) > INFO_FOR_SIGN_PDF_MAX_RECORDS:
		frappe.throw(
			_("PDF can export at most {0} records at a time ({1} selected). Select fewer records or use Excel.").format(
				INFO_FOR_SIGN_PDF_MAX_RECORDS, len(people)
			),
			title=_("Info for Sign"),
		)
	options = {
		"orientation": "Landscape",
		"page-size": "A4",
		# Số trang do wkhtmltopdf tự thay [page]/[topage] — không cần JavaScript.
		"footer-center": "Trang [page]/[topage]",
		"footer-font-size": "8",
		"footer-spacing": "2",
	}

	def count(html):
		pdf = get_pdf(html, options=dict(options))
		return pdf, len(PdfReader(io.BytesIO(pdf)).pages)

	def weight(page):
		# Ước lượng độ "nặng": số dòng + dòng xuống hàng của nội dung dài.
		return sum(1 + len(v) // 45 for _e, _n, lines in page for _l, v in lines)

	def best_font(pages):
		"""(cỡ chữ lớn nhất vừa trang theo bước 0,5px trong 5px…_SIGN_PDF_MAX_FONT, pdf) — None nếu 5px vẫn tràn.

		Tìm cỡ chữ trên MẪU nhỏ (trang 1 có tiêu đề + các trang nặng nhất) cho nhanh — dựng cả
		file mỗi lần tốn ~6s/915 phiếu, tìm nhị phân trên cả file sẽ vượt timeout 120s của gunicorn.
		Sau đó dựng cả file 1 lần để kiểm; vẫn tràn thì giảm 0,5px.
		"""
		heavy = sorted(range(1, len(pages)), key=lambda i: weight(pages[i]), reverse=True)[:_SIGN_PDF_SAMPLE_PAGES]
		sample = [pages[0]] + [pages[i] for i in sorted(heavy)]
		cache = {}

		def fits(half):
			if half not in cache:
				cache[half] = count(_info_for_sign_pdf_html(sample, company, half / 2))[1] <= len(sample)
			return cache[half]

		top = int(_SIGN_PDF_MAX_FONT * 2)
		if fits(top):
			lo = top
		elif not fits(10):
			return None
		else:
			lo, hi = 10, top   # fits(lo) đúng, fits(hi) sai
			while hi - lo > 1:
				mid = (lo + hi) // 2
				if fits(mid):
					lo = mid
				else:
					hi = mid
		while True:   # kiểm trên cả file
			pdf, n = count(_info_for_sign_pdf_html(pages, company, lo / 2))
			if n <= len(pages):
				return lo / 2, pdf
			if lo <= 10:
				return None
			lo -= 1

	layouts = ((INFO_FOR_SIGN_PDF_FIRST, INFO_FOR_SIGN_PDF_PER_PAGE),) + _SIGN_PDF_FALLBACK
	pdf = None
	for first, per in layouts:
		got = best_font(_info_for_sign_pdf_pages(people, first, per))
		if got and (got[0] >= _SIGN_PDF_MIN_FONT or (first, per) == layouts[-1]):
			pdf = got[1]
			break
	if pdf is None:   # cả bố cục 1 NV/trang ở 5px vẫn tràn — vẫn xuất (có thể tràn trang)
		pdf = count(_info_for_sign_pdf_html(_info_for_sign_pdf_pages(people, 1, 1), company, 5.0))[0]
	# Tên file theo ngày xuất, không khoảng trắng: employee_info_for_sign_ddmmyyyy.pdf
	frappe.response["filename"] = f"employee_info_for_sign_{frappe.utils.now_datetime().strftime('%d%m%Y')}.pdf"
	frappe.response["filecontent"] = pdf
	# "download" = Content-Disposition: attachment → trình duyệt TẢI VỀ ngay (type "pdf" là inline = mở xem).
	# File chỉ nằm trong bộ nhớ của request, không lưu gì trên server.
	frappe.response["type"] = "download"
	frappe.response["content_type"] = "application/pdf"


def _download_info_for_sign_pdf_split(names, merge=False):
	"""PDF Split For Each Employee: mỗi bản ghi 1 PDF, đúng phiếu của nút "Generate PDF" trên form
	(_hr_receipt_html: mẫu trang www, chỉ field tick "Info for Sign", có cam kết + chữ ký).
	1 bản ghi → tải thẳng PDF; nhiều bản ghi → 1 file ZIP.
	`merge=True` ("PDF Pages", user 27/10/2026): cùng các phiếu đó nối thành 1 file PDF theo mã NV — mỗi bản
	ghi đúng 1 trang (_hr_receipt_pdf thu nhỏ vừa 1 trang), in 1 lần là đủ. Giới hạn
	INFO_FOR_SIGN_PDF_MAX_RECORDS như PDF gộp (~0,35 giây/lần dựng; phiếu tràn trang dựng thêm 1–2 lần để
	thu nhỏ vừa 1 trang, _hr_receipt_pdf → 100 phiếu ≈ 35–75 giây)."""
	import io
	import zipfile

	if isinstance(names, str):
		names = json.loads(names or "null")
	filters = {"name": ["in", names]} if names else {}
	records = frappe.get_all(INFO_DT, filters=filters, pluck="name", order_by="employee asc")
	if not records:
		frappe.throw(_("No record to export."))
	if len(records) > INFO_FOR_SIGN_PDF_MAX_RECORDS:
		frappe.throw(
			_("PDF can export at most {0} records at a time ({1} selected). Select fewer records or use Excel.").format(
				INFO_FOR_SIGN_PDF_MAX_RECORDS, len(records)
			),
			title=_("Info for Sign"),
		)
	config = _info_for_sign_config(_build_config())
	files = []
	for name in records:
		doc = frappe.get_doc(INFO_DT, name)
		doc.check_permission("read")
		files.append((f"{_receipt_base(doc)}.pdf", _hr_receipt_pdf(doc, config)))

	frappe.response["type"] = "download"   # attachment → tải về ngay; không lưu gì trên server
	if merge:
		from pypdf import PdfReader, PdfWriter

		writer = PdfWriter()
		for _filename, pdf in files:
			writer.append(PdfReader(io.BytesIO(pdf)))
		out = io.BytesIO()
		writer.write(out)
		frappe.response["filename"] = f"employee_info_for_sign_{now_datetime().strftime('%d%m%Y')}.pdf"
		frappe.response["filecontent"] = out.getvalue()
		frappe.response["content_type"] = "application/pdf"
		return
	if len(files) == 1:
		frappe.response["filename"], frappe.response["filecontent"] = files[0]
		frappe.response["content_type"] = "application/pdf"
		return
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
		for filename, pdf in files:
			zf.writestr(filename, pdf)
	frappe.response["filename"] = f"employee_info_for_sign_{now_datetime().strftime('%d%m%Y')}.zip"
	frappe.response["filecontent"] = buf.getvalue()
	frappe.response["content_type"] = "application/zip"


def _download_info_for_sign(names):
	"""1 sheet "Info for Sign", A4 ngang: STT | Nhân viên (Mã NV xuống dòng Họ tên) | Thông tin | Nội dung | Ghi chú | Chữ ký.

	- STT đánh theo NHÂN VIÊN; STT / Nhân viên / Chữ ký gộp ô theo nhân viên.
	- Địa chỉ mỗi Section 1 dòng dạng đầy đủ; liên hệ khẩn cấp 1 dòng (xem _sign_items).

	- Nội dung LUÔN là thông tin mới (NV khai); mới trống → lấy giá trị Employee hiện tại;
	  cả hai trống → VẪN in dòng, ô Nội dung trống để NV mới tự ghi tay bổ sung.
	- Chỉ các field được tick "Info for Sign" trong Setting (NV chỉ ký xác nhận một số thông tin),
	  LUÔN đủ các field đó (không lọc "chỉ thay đổi"). Ghi chú NV không xuất.
	- Mã NV / Họ tên / Chữ ký gộp ô theo nhân viên; cột Chữ ký để trống để ký tay khi in.
	"""
	import io

	from openpyxl import Workbook
	from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

	people, company = _info_for_sign_people(names)

	wb = Workbook()
	ws = wb.active
	ws.title = "Info for Sign"

	header = list(INFO_FOR_SIGN_HEADER)
	ncol = len(header)
	thin = Side(style="thin", color="808080")
	border = Border(left=thin, right=thin, top=thin, bottom=thin)
	center = Alignment(horizontal="center", vertical="center", wrap_text=True)
	left = Alignment(horizontal="left", vertical="center", wrap_text=True)

	ws.append([company.upper()])
	ws.append([INFO_FOR_SIGN_TITLE])
	ws.append([f"Ngày: {frappe.utils.now_datetime().strftime('%d/%m/%Y')}"])
	for r in (1, 2, 3):
		ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncol)
		ws.cell(row=r, column=1).alignment = Alignment(horizontal="center")
	ws.cell(row=1, column=1).font = Font(bold=True, size=11)
	ws.cell(row=2, column=1).font = Font(bold=True, size=14)
	ws.cell(row=3, column=1).font = Font(italic=True, size=10)

	head_row = 5
	for c, h in enumerate(header, 1):
		cell = ws.cell(row=head_row, column=c, value=h)
		cell.font = Font(bold=True)
		cell.alignment = center
		cell.border = border
		cell.fill = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")

	row = head_row + 1
	for stt, (emp, emp_name, lines) in enumerate(people, 1):
		first = row
		for label, value in lines:
			head = row == first
			who = f"{emp}\n{emp_name}" if emp_name else emp  # Mã NV xuống dòng Họ tên, chung 1 ô
			# Ghi chú (cột 5) + Chữ ký (cột 6) để trống cho ghi tay / ký tay, gộp theo nhân viên.
			vals = [stt if head else None, who if head else None, label, value, None, None]
			for c, v in enumerate(vals, 1):
				cell = ws.cell(row=row, column=c, value=v)
				cell.border = border
				cell.alignment = left if c in (3, 4, 5) else center
			row += 1
		last = row - 1
		for c in (1, 2, 5, 6):  # STT, Nhân viên, Ghi chú, Chữ ký gộp theo nhân viên
			if last > first:
				ws.merge_cells(start_row=first, start_column=c, end_row=last, end_column=c)
		if last == first:
			ws.row_dimensions[first].height = 42  # đủ chỗ ký + 2 dòng Mã NV/Họ tên khi NV chỉ có 1 dòng

	# A4 ngang: tổng ~140 ký tự để vừa 1 trang khi fitToWidth; cột Nội dung rộng cho địa chỉ đầy đủ.
	for col, width in zip("ABCDEF", (5, 20, 24, 56, 24, 22)):
		ws.column_dimensions[col].width = width
	ws.print_title_rows = f"{head_row}:{head_row}"
	ws.page_setup.orientation = "landscape"
	ws.page_setup.paperSize = ws.PAPERSIZE_A4
	ws.page_setup.fitToWidth = 1
	ws.page_setup.fitToHeight = 0
	ws.sheet_properties.pageSetUpPr.fitToPage = True
	ws.print_options.horizontalCentered = True

	buf = io.BytesIO()
	wb.save(buf)
	frappe.response["filename"] = "employee_info_for_sign.xlsx"
	frappe.response["filecontent"] = buf.getvalue()
	frappe.response["type"] = "binary"
