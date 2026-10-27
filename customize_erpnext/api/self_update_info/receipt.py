"""Phiếu PDF / PNG: phiếu NV tải ở trang www và phiếu phía HR (Generate PDF / PDF Split).

Tách nguyên văn từ self_update_info_api.py (27/10/2026) — mặt tiền đó re-export mọi tên."""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from .rules import (
	DOCUMENTS_KEY,
	REMARKS_KEY,
	_SIGNATURE_PREFIX,
)
from .config import (
	_commitment_html,
	_is_table,
	_setting_documents,
)
from .values import (
	_SIGN_GROUPS,
	_clean_documents,
	_fill_from_employee,
	_fmt_date_vn,
	_sign_join,
	_sign_value_vi,
	_status_text_vi,
	_table_list,
)


# Phiếu PDF phía HR LUÔN 1 trang (user 27/10/2026): tràn → thu nhỏ cả trang (wkhtmltopdf --zoom) từng bước
# 0,05 tới khi vừa. Đo 27/10: phiếu đủ mục + câu hỏi phí + bảng hồ sơ cần 0,95; mỗi lần dựng ~0,37 giây.
# Tới mức nhỏ nhất vẫn tràn → trả bản nhỏ nhất (nhiều trang) chứ không cắt nội dung.
HR_RECEIPT_ZOOM_STEPS = (1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7)


def _hr_receipt_pdf(doc, sign_config):
	"""PDF phiếu HR (_hr_receipt_html) thu nhỏ vừa đúng 1 trang A4 — Generate PDF + PDF Split."""
	import io

	from frappe.utils.pdf import get_pdf
	from pypdf import PdfReader

	html = _hr_receipt_html(doc, sign_config)
	pdf = None
	for zoom in HR_RECEIPT_ZOOM_STEPS:
		pdf = get_pdf(html, {"zoom": str(zoom)})
		if len(PdfReader(io.BytesIO(pdf)).pages) <= 1:
			break
	return pdf


# Đầu phiếu HR (compact): dòng 1 = Mã NV · Họ tên · các field dòng đầu; mỗi dòng sau 1 tuple.
# Field có trong Setting thì lên đầu phiếu và bỏ khỏi bảng (user 16/10/2026: bỏ hẳn "Thông tin chung").
_HR_HEADER_LINES = (("gender",), ("date_of_birth", "cell_number"))


# % độ rộng 6 cột đầu phiếu: nhãn | giá trị × 3 (cột 3 đủ "Số điện thoại:", cột 4 họ tên dài, cột 5 "Ngày nhận việc:").
_HR_HEADER_COL_WIDTHS = (13, 16, 13, 26, 15, 17)


# Lề PDF phía HR (user 16/10/2026: trái/phải rộng bảng hồ sơ thêm chút, trên/dưới bớt 1 xíu); phiếu www giữ 15mm.
HR_RECEIPT_SIDE_MARGIN = "10mm"


HR_RECEIPT_TB_MARGIN = "10mm"


def _hr_receipt_html(doc, sign_config):
	"""Phiếu PDF phía HR (Generate PDF + PDF Split): đúng mẫu phiếu tải ở trang www, khác 2 điểm:
	- chỉ field tick "Info for Sign" (`sign_config` = _info_for_sign_config(_build_config()));
	- phiếu chưa ký trên www vẫn in cam kết + ô trống để NV ký tay (sign_on_paper);
	- bảng "Hồ sơ / Tình trạng" (_document_checklist_html: hồ sơ NV đã tick + ô HR đánh tay) ngay trên chữ ký;
	- gom dòng cho gọn trang (compact): địa chỉ, CCCD + ngày cấp, liên hệ khẩn cấp.
	Field "Auto Fill Data" phiếu chưa có giá trị → lấy từ Employee (_fill_from_employee), như phiếu www."""
	saved = _fill_from_employee(sign_config, json.loads(doc.data_json or "{}"), doc.employee)
	# Phiếu có bản chụp hồ sơ → in đúng bản đó; phiếu cũ (trước 27/10/2026) → danh sách Setting, chưa tick.
	documents = _clean_documents(saved.get(DOCUMENTS_KEY)) if DOCUMENTS_KEY in saved else _setting_documents()
	checklist = _document_checklist_html(documents)
	return _build_submission_html(
		doc, saved, sign_config, sign_on_paper=True, checklist_html=checklist, compact=True,
		side_margin=HR_RECEIPT_SIDE_MARGIN, tb_margin=HR_RECEIPT_TB_MARGIN,
	)


def _document_checklist_html(items):
	"""Bảng hồ sơ cuối phiếu HR: `items` = [{document, required, checked}] (bản chụp trong phiếu; phiếu cũ chưa
	có → danh sách Setting, chưa tick). Trống → "".
	4 cột Hồ sơ | Tình trạng | Hồ sơ | Tình trạng: nửa đầu ở cặp cột trái, nửa sau ở cặp cột phải;
	số hồ sơ lẻ → hồ sơ cuối 1 hàng trải ngang. Ô ☐ trước tên hồ sơ = NV đã tick nộp (☑);
	Đạt / Không đạt / Quá hạn / Khác để HR đánh tay. Cuối bảng: "Tình trạng hồ sơ" (chỉ khi phiếu có bản chụp)
	+ "Thông tin khác về hồ sơ" + dòng chấm viết tay.
	Ô ☐ / ☑ vẽ bằng CSS (span.cb / span.cb.on) — không phụ thuộc font của wkhtmltopdf."""
	items = [d for d in items or [] if str(d.get("document") or "").strip()]
	if not items:
		return ""
	esc = frappe.utils.escape_html
	cb = "<span class='cb'></span>"
	marks = f"Đạt {cb}&nbsp; Không đạt {cb}&nbsp; Quá hạn {cb}"

	def doc_cell(no, colspan=""):
		d = items[no - 1]
		box = "<span class='cb on'></span>" if d.get("checked") else cb
		req = " *" if d.get("required") else ""
		return f"<td class='cdoc'{colspan}>{no} {box} {esc(d['document'])}{req}</td>"

	half = len(items) // 2
	rows = [
		"<tr><th class='hdoc'>Hồ sơ</th><th class='hst'>Tình trạng</th><th class='hdoc'>Hồ sơ</th><th class='hst'>Tình trạng</th></tr>"
	]
	status = f"<td class='cst'>{marks}<br>Khác: <span class='fill'></span></td>"
	for i in range(1, half + 1):
		rows.append(f"<tr>{doc_cell(i)}{status}{doc_cell(half + i)}{status}</tr>")
	if len(items) % 2:
		span = " colspan='2'"
		rows.append(
			f"<tr>{doc_cell(len(items), span)}"
			f"<td class='cst' colspan='2'>{marks}&nbsp; Khác: <span class='fill w'></span></td></tr>"
		)
	if any("checked" in d for d in items):
		rows.append(
			"<tr><td colspan='4' class='cnote'><b>Tình trạng hồ sơ (NV tự khai, * = bắt buộc):</b> "
			f"{esc(_status_text_vi(items))}</td></tr>"
		)
	rows.append(
		"<tr><td colspan='4' class='cnote'>Thông tin khác về hồ sơ (nếu có):"
		"<div class='dots'></div><div class='dots'></div></td></tr>"
	)
	return f"<div class='checklist'><table class='chk'>{''.join(rows)}</table></div>"


def _receipt_base(doc):
	"""Tên file phiếu: "<mã NV> <họ tên> <yyyyMMdd_HHmm>"."""
	stamp = frappe.utils.format_datetime(now_datetime(), "yyyyMMdd_HHmm")
	return f"{doc.employee} {(doc.employee_name or '').strip()} {stamp}".strip()


def _html_to_png(html):
	"""Render HTML to a PNG (bytes) via wkhtmltoimage (stdin → stdout)."""
	import subprocess

	cmd = [
		"wkhtmltoimage",
		"--format", "png",
		"--encoding", "utf-8",
		"--quality", "94",
		"--width", "820",
		"--enable-local-file-access",
		"--quiet",
		"-", "-",
	]
	try:
		proc = subprocess.run(
			cmd, input=html.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE
		)
	except FileNotFoundError:
		frappe.throw(_("wkhtmltoimage is not installed on the server."))
	if not proc.stdout:
		frappe.log_error(proc.stderr.decode("utf-8", "ignore"), "wkhtmltoimage failed")
		frappe.throw(_("Could not render the image."))

	# wkhtmltoimage emits a large RGBA PNG. Flatten onto white + optimize to
	# keep the file small enough to save comfortably on a phone.
	try:
		import io

		from PIL import Image

		img = Image.open(io.BytesIO(proc.stdout))
		if img.mode in ("RGBA", "LA", "P"):
			bg = Image.new("RGB", img.size, "#FFFFFF")
			img = img.convert("RGBA")
			bg.paste(img, mask=img.split()[-1])
			img = bg
		else:
			img = img.convert("RGB")
		out = io.BytesIO()
		img.save(out, format="PNG", optimize=True)
		return out.getvalue()
	except Exception:
		return proc.stdout


def _logo_data_uri():
	"""Return the company logo as a base64 data URI (for the PDF), or ''."""
	import base64
	import os

	path = frappe.get_app_path("customize_erpnext", "public", "images", "logo_500.jpg")
	if not os.path.exists(path):
		return ""
	with open(path, "rb") as fh:
		b64 = base64.b64encode(fh.read()).decode()
	return f"data:image/jpeg;base64,{b64}"


def _strip_section_no(label):
	"""Drop a leading ordinal prefix from a section name for the receipt.

	e.g. "1. Thông tin chung" / "2) Trình độ" / "3 - CCCD" -> "Thông tin chung"…
	so the PDF/PNG shows the plain Section name without the numbering HR typed.
	"""
	import re

	cleaned = re.sub(r"^\s*\d+\s*[.)\-–—]\s*", "", label or "").strip()
	return cleaned or (label or "")


def _table_html(f, rows):
	"""Bảng con trên phiếu PDF/PNG: bảng nhỏ có tiêu đề cột; không có dòng → ""."""
	rows = _table_list(rows)
	if not rows:
		return ""
	esc = frappe.utils.escape_html
	head = "".join(f"<th>{esc(c['label'])}</th>" for c in f["columns"])
	body = "".join(
		"<tr>" + "".join(f"<td>{esc(_sign_value_vi(c, r.get(c['fieldname'])))}</td>" for c in f["columns"]) + "</tr>"
		for r in rows
	)
	return f"<table class='sub'><tr>{head}</tr>{body}</table>"


def _build_submission_html(
	doc, saved, config, sign_on_paper=False, checklist_html="", compact=False, side_margin="15mm", tb_margin="15mm"
):
	"""Phiếu HTML (PDF/PNG). `sign_on_paper=True` (phiếu phía HR, _hr_receipt_html): phiếu chưa ký trên
	trang www vẫn in câu cam kết + ô trống để NV ký tay; phiếu đã ký in chữ ký như thường.
	`checklist_html` (chỉ phiếu HR, _document_checklist_html) in sau Ghi chú, trước chữ ký — chữ ký luôn cuối phiếu.
	`compact=True` (chỉ phiếu HR) gom dòng cho gọn trang, ghép như Info for Sign (_sign_join):
	- mỗi Section địa chỉ (có ô Address Province) → 1 dòng "thôn, xã, tỉnh"; các Section địa chỉ liền nhau
	  chung 1 tiêu đề "Địa chỉ";
	- nhóm _SIGN_GROUPS (Số CCCD + ngày cấp; người liên hệ + quan hệ + SĐT khẩn cấp) → 1 dòng, đặt ở chỗ
	  field đầu tiên của nhóm. Nhóm chỉ còn 1 field trong config thì in như thường.
	`side_margin` / `tb_margin` = lề trái-phải / trên-dưới trang PDF (phiếu HR 10mm; phiếu www giữ 15mm).
	compact còn đưa Giới tính lên đầu phiếu, cùng dòng Mã NV + Họ tên."""
	company = (
		frappe.defaults.get_global_default("company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or ""
	)
	logo = _logo_data_uri()
	submitted = frappe.utils.format_datetime(doc.submitted_on, "dd/MM/yyyy HH:mm") if doc.submitted_on else ""

	# The employee code is already shown in the header — skip any field that just
	# repeats it (e.g. a field mapped to `employee` / `name`).
	skip_fields = {"employee", "name"}
	# compact (phiếu HR): các field ở _HR_HEADER_LINES lên đầu phiếu (cạnh Mã NV / Họ tên) → bỏ khỏi bảng;
	# Section chỉ còn các field này (vd "Thông tin chung") tự mất vì rỗng.
	by_fn = {f["fieldname"]: f for s in config["sections"] for f in s["fields"]}
	header_lines = [[by_fn[fn] for fn in line if fn in by_fn] for line in _HR_HEADER_LINES] if compact else []
	skip_fields |= {f["fieldname"] for line in header_lines for f in line}
	rows = []
	addr_run = []  # dòng địa chỉ đã gom (compact), chờ in dưới 1 tiêu đề "Địa chỉ"
	esc = frappe.utils.escape_html

	def fmt(f):
		"""Giá trị 1 field (không phải bảng con) như in trên phiếu."""
		val = saved.get(f["fieldname"])
		val = "" if val is None else str(val)
		if f.get("fieldtype") == "Date" and val:
			return _fmt_date_vn(val)  # ngày trên phiếu: dd/mm/yyyy
		if f.get("fieldtype") == "Select" and val:
			return _sign_value_vi(f, val)  # Married → "Đã kết hôn"; size dép in gọn "6-7" (không dùng Option Labels)
		return val

	def row_html(label, val_html):
		return f"<tr><td class='lbl'>{esc(label)}</td><td class='val'>{val_html or '&mdash;'}</td></tr>"

	# compact: field → nhóm gộp 1 dòng (chỉ nhóm có ≥ 2 field trong config)
	group_of, members = {}, {}
	if compact:
		for kind, (fns, _label) in _SIGN_GROUPS.items():
			ms = [f for s in config["sections"] for f in s["fields"] if f["fieldname"] in fns and not _is_table(f)]
			if len(ms) > 1:
				members[kind] = ms
				group_of.update({f["fieldname"]: kind for f in ms})

	def flush_addr():
		if addr_run:
			rows.append('<tr><td colspan="2" class="sec">Địa chỉ</td></tr>')
			rows.extend(addr_run)
			addr_run.clear()

	for sec in config["sections"]:
		if compact and any(f.get("widget") == "Address Province" for f in sec["fields"]):
			fs = [f for f in sec["fields"] if f["fieldname"] not in skip_fields]
			if fs:
				val = _sign_join("address", [(f, str(saved.get(f["fieldname"]) or "").strip()) for f in fs])
				addr_run.append(
					"<tr><td class='lbl'>{0}</td><td class='val'>{1}</td></tr>".format(
						frappe.utils.escape_html(_strip_section_no(sec["label"])),
						frappe.utils.escape_html(val) or "&mdash;",
					)
				)
			continue
		flush_addr()
		sec_rows = []
		for f in sec["fields"]:
			if f["fieldname"] in skip_fields:
				continue
			if _is_table(f):
				sec_rows.append(row_html(f["label"], _table_html(f, saved.get(f["fieldname"]))))
				continue
			kind = group_of.get(f["fieldname"])
			if kind:
				if f is members[kind][0]:
					val = _sign_join(kind, [(m, fmt(m).strip()) for m in members[kind]])
					sec_rows.append(row_html(_SIGN_GROUPS[kind][1], esc(val)))
				continue
			sec_rows.append(row_html(f["label"], esc(fmt(f))))
		if not sec_rows:
			continue  # drop a section that became empty
		rows.append(
			f'<tr><td colspan="2" class="sec">{frappe.utils.escape_html(_strip_section_no(sec["label"]))}</td></tr>'
		)
		rows.extend(sec_rows)
	flush_addr()
	# Phiếu NV tải (trang www): hồ sơ đã tick + tình trạng, 2 dòng. Phiếu HR (compact) in bảng hồ sơ riêng.
	documents = _clean_documents(saved.get(DOCUMENTS_KEY)) if not compact else []
	if documents:
		done = [d["document"] for d in documents if d["checked"]]
		rows.append('<tr><td colspan="2" class="sec">Hồ sơ nộp kèm</td></tr>')
		rows.append(row_html("Đã có", esc("; ".join(done))))
		rows.append(row_html("Tình trạng hồ sơ", esc(_status_text_vi(documents))))

	remarks = saved.get(REMARKS_KEY) or ""
	remarks_block = ""
	if remarks:
		remarks_block = (
			"<div class='remarks'><div class='rlabel'>Ghi chú thêm</div>"
			f"<div class='rtext'>{frappe.utils.escape_html(remarks)}</div></div>"
		)

	logo_img = f"<img src='{logo}' class='logo'/>" if logo else ""
	emp_code, emp_name = esc(doc.employee), esc(doc.employee_name or "")
	# compact (phiếu HR): ô bảng đệm 2px thay 3px (cùng cỡ chữ) → thêm chỗ cho bảng hồ sơ + chữ ký trên trang 1.
	# Đặt CUỐI <style> để thắng rule td mặc định.
	# Cột nhãn của bảng hẹp lại (40% → 30%) để cột giá trị rộng hơn (bảng con Học vấn / Kinh nghiệm…).
	compact_css = (
		"table.data td{padding:2px 7px} table.data td.lbl{width:30%} table.data td.val{width:70%}" if compact else ""
	)
	if compact:
		# Đầu phiếu dạng bảng không viền, cột thẳng hàng: dòng 1 Mã NV · Họ tên · (Giới tính);
		# các dòng sau theo _HR_HEADER_LINES (Ngày sinh · Số điện thoại).
		lines = [[("Mã nhân viên", emp_code), ("Họ và tên", emp_name)]
			+ [(f["label"], esc(fmt(f)) or "&mdash;") for f in header_lines[0]]] if header_lines else [
			[("Mã nhân viên", emp_code), ("Họ và tên", emp_name)]]
		lines += [[(f["label"], esc(fmt(f)) or "&mdash;") for f in line] for line in header_lines[1:] if line]
		# Ngày nhận việc (field của phiếu, fetch từ Employee — không phụ thuộc Setting): cuối dòng 2.
		doj = doc.get("date_of_joining")
		doj_item = ("Ngày nhận việc", esc(_fmt_date_vn(doj)) if doj else "&mdash;")
		if len(lines) > 1 and len(lines[1]) < 3:
			lines[1].append(doj_item)
		else:
			lines.append([doj_item])
		# 6 cột cố định (nhãn | giá trị × 3) → 2 dòng thẳng cột, trải đều chiều ngang.
		id_lines = "<table class='meta-t'><colgroup>" + "".join(
			f"<col style='width:{w}%'>" for w in _HR_HEADER_COL_WIDTHS) + "</colgroup>" + "".join(
			"<tr>" + "".join(f"<td class='mk'>{esc(lbl)}:</td><td class='mv'>{v}</td>" for lbl, v in line)
			+ "<td></td><td></td>" * (3 - len(line)) + "</tr>"
			for line in lines
		) + "</table>"
	else:
		id_lines = f"<div><b>Mã nhân viên:</b> {emp_code}</div><div><b>Họ và tên:</b> {emp_name}</div>"
	# Đã ký → "Ký lúc" ở khung chữ ký là mốc thời gian; chỉ phiếu cũ chưa ký mới hiện giờ gửi.
	submitted_line = "" if doc.get("signed_on") else f"<div><b>Thời điểm gửi:</b> {submitted}</div>"

	# Cam kết + chữ ký (vẽ trên trang www). Chỉ nhận đúng data URL PNG đã kiểm ở save_form_data.
	sign_block = ""
	commitment = _commitment_html()
	sig = doc.get("signature") or ""
	if doc.get("commitment_confirmed") or sig:
		signed = frappe.utils.format_datetime(doc.signed_on, "dd/MM/yyyy HH:mm") if doc.get("signed_on") else ""
		sig_img = f"<img src='{sig}' class='sig'/>" if sig.startswith(_SIGNATURE_PREFIX) else ""
		sign_block = (
			"<div class='commit'>"
			+ ("" if doc.get("commitment_confirmed") else "")
			+ commitment
			+ "</div><div class='signbox'><div class='slabel'>Người khai ký tên</div>"
			+ sig_img
			+ f"<div class='sname'>{frappe.utils.escape_html(doc.employee_name or '')}</div>"
			+ (f"<div class='sdate'>Ký lúc: {signed}</div>" if signed else "")
			+ "</div>"
		)
	elif sign_on_paper:
		sign_block = (
			"<div class='commit'>"
			+ commitment
			+ "</div><div class='signbox'><div class='slabel'>Người khai ký tên</div>"
			+ "<div class='sigspace'></div>"
			+ f"<div class='sname'>{frappe.utils.escape_html(doc.employee_name or '')}</div>"
			+ "</div>"
		)

	return f"""
<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  /* Lề trang PDF: get_pdf đọc từ rule .print-format (khai ở options của get_pdf sẽ bị ghi đè).
     Lề 15mm cả 4 phía (user chọn 15/10/2026); phần còn lại thu gọn để phiếu + chữ ký vừa 1 trang A4. */
  .print-format{{margin-top:{tb_margin};margin-bottom:{tb_margin};margin-left:{side_margin};margin-right:{side_margin}}}
  body{{font-family:'Helvetica Neue',Arial,sans-serif;color:#1f2733;font-size:11px;line-height:1.3;margin:0}}
  .head{{text-align:left;border-bottom:2px solid #1e3a8a;padding-bottom:6px;margin-bottom:8px;overflow:hidden}}
  .logo{{height:30px;float:left;margin:1px 10px 0 0}}
  .company{{font-size:11px;font-weight:bold;color:#1e3a8a;text-transform:uppercase}}
  .title{{font-size:17px;font-weight:bold;color:#1e3a8a;margin-top:1px}}
  .meta{{margin:6px 0;font-size:11px}}
  .meta b{{display:inline-block;min-width:110px}}
  table{{width:100%;border-collapse:collapse;margin-top:4px}}
  tr{{page-break-inside:avoid}}
  td{{border:1px solid #d5dbe3;padding:3px 7px;vertical-align:top}}
  td.sec{{background:#eef2ff;font-weight:bold;color:#1e3a8a;padding:3px 7px}}
  td.lbl{{width:40%;color:#475569}}  /* chỉ dòng tiêu đề Section (td.sec) có nền */
  td.val{{width:60%}}
  .remarks{{margin-top:8px;border:1px solid #d5dbe3;border-radius:5px;padding:6px 8px}}
  .rlabel{{font-weight:bold;color:#1e3a8a;margin-bottom:2px}}
  .signoff{{page-break-inside:avoid}}
  .commit{{margin-top:8px;font-style:italic}}
  .signbox{{margin:4px 0 0 auto;width:240px;text-align:center}}
  .slabel{{font-weight:bold}}
  .sig{{max-width:220px;max-height:60px;margin:3px 0}}
  .sigspace{{height:60px;margin:3px 0}}  /* ô trống để ký tay (sign_on_paper) */
  table.sub{{margin:0}}  /* bảng con (Học vấn, Quá trình làm việc) trong ô giá trị */
  table.sub th,table.sub td{{border:1px solid #e3e8ef;padding:1px 4px;font-size:10px;font-weight:normal;text-align:left}}
  table.sub th{{color:#475569}}
  .sname{{font-weight:bold}}
  .sdate{{font-size:10px;color:#64748b}}
  /* Bảng hồ sơ HR kiểm tra (_document_checklist_html) — không cắt đôi giữa 2 trang.
     Cùng font / viền / tiêu đề với bảng nội dung phía trên (td, td.sec). */
  .checklist{{margin-top:6px;page-break-inside:avoid}}
  .tail{{page-break-inside:avoid}}  /* bảng hồ sơ + chữ ký luôn cùng trang — chữ ký không đứng riêng trang sau */
  table.chk{{table-layout:fixed}}  /* cột theo đúng % ở th — tên hồ sơ không bị ép hẹp */
  table.chk td{{padding:2px 7px;line-height:1.25}}
  table.chk th{{border:1px solid #d5dbe3;padding:2px 7px;background:#eef2ff;font-weight:bold;color:#1e3a8a;text-align:left}}
  table.chk th.hdoc{{width:23%}}
  table.chk th.hst{{width:27%}}
  table.chk td.cst{{white-space:nowrap}}
  .cb{{display:inline-block;width:9px;height:9px;border:1px solid #475569;vertical-align:-1px;margin:0 1px}}
  /* ☑ hồ sơ NV đã tick: dấu ✓ vẽ bằng viền xoay (không phụ thuộc font) */
  .cb.on{{position:relative}}
  .cb.on:after{{content:"";position:absolute;left:2px;top:-1px;width:3px;height:7px;border:solid #1e3a8a;
    border-width:0 2px 2px 0;-webkit-transform:rotate(45deg);transform:rotate(45deg)}}
  .fill{{display:inline-block;width:65%;border-bottom:1px dotted #475569;height:10px}}
  /* đầu phiếu HR (compact): bảng không viền */
  table.meta-t{{width:100%;table-layout:fixed;margin:0;border-collapse:collapse;font-size:12.5px}}
  table.meta-t td{{border:none;padding:1px 6px 1px 0;white-space:nowrap;overflow:hidden}}
  table.meta-t td.mk{{font-weight:bold}}
  {compact_css}
  .fill.w{{width:120px}}  /* hàng trải ngang: "Khác" nằm cùng dòng với Đạt / Không đạt / Quá hạn */
  .dots{{border-bottom:1px dotted #475569;height:12px}}
</style></head><body>
  <div class="head">
    {logo_img}
    <div class="company">{frappe.utils.escape_html(company)}</div>
    <div class="title">PHIẾU CẬP NHẬT THÔNG TIN NHÂN VIÊN</div>
  </div>
  <div class="meta">
    {id_lines}
    {submitted_line}
  </div>
  <table class="data">{''.join(rows)}</table>
  {remarks_block}
  <div class="tail">{checklist_html}<div class="signoff">{sign_block}</div></div>
</body></html>
"""
