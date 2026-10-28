# -*- coding: utf-8 -*-
"""Kiểm tra chữ ký / cam kết / sửa trên Desk / Excel "Info for Sign" — KHÔNG ghi DB.

Chỉ sửa doc trong bộ nhớ, gọi hàm thuần, cuối cùng rollback. Không gọi đường nào có commit
(save_form_data chỉ được gọi ở nhánh throw trước khi lưu).

    bench --site erp.tiqn.local execute \
        customize_erpnext.api.self_update_info.test_self_update_sign.run_all

`run_all` chạy mọi bộ test_* + run và in bảng tổng. Test trang www (jsdom) ở
customize_erpnext/tests_js/self_update_info (`node run.js`).
"""

import io
import json

import frappe
from frappe import _

from customize_erpnext.api.self_update_info import self_update_info_api as api

DT = "Employee Self Update Info"


def _set(name, value):
	"""Thay tạm 1 tên của package self_update_info (vd `_build_config`) ở MỌI module đang giữ nó.

	Code đã tách thành nhiều module (config, values, receipt…); mỗi module import tên về chỗ mình, nên
	gán `api._build_config = fake` chỉ đổi ở mặt tiền — hàm trong module khác vẫn gọi bản thật.
	Gọi lại với giá trị gốc để trả về như cũ."""
	import importlib
	import pkgutil

	import customize_erpnext.api.self_update_info as pkg

	for info in pkgutil.iter_modules(pkg.__path__):
		if info.name.startswith("test_"):
			continue
		mod = importlib.import_module(f"{pkg.__name__}.{info.name}")
		if name in vars(mod):
			setattr(mod, name, value)


def _expect_throw(fn):
	try:
		fn()
	except frappe.ValidationError:
		frappe.clear_messages()
		return True
	return False


def _read_sheet():
	from openpyxl import load_workbook

	wb = load_workbook(io.BytesIO(frappe.response["filecontent"]))
	ws = wb.active
	rows = [[c.value for c in r] for r in ws.iter_rows(min_row=6)]
	return wb, ws, rows


def run():
	results = []

	def check(name, ok, detail=""):
		results.append((bool(ok), name, detail))

	config = api._build_config()
	fields = {f["fieldname"]: f for s in config["sections"] for f in s["fields"]}

	# Cờ "Info for Sign" giả lập TRONG BỘ NHỚ (không ghi Setting): bọc _build_config.
	real_build = api._build_config
	flagged = {"value": None}  # None = tick tất cả; set = chỉ các field này

	def fake_build():
		cfg = real_build()
		for sec in cfg["sections"]:
			for f in sec["fields"]:
				f["info_for_sign"] = flagged["value"] is None or f["fieldname"] in flagged["value"]
		return cfg

	# ---------- chưa tick field nào → báo lỗi, dialog rỗng ----------
	flagged["value"] = set()
	_set("_build_config", fake_build)
	try:
		check("flag: chưa tick → dialog rỗng", api.get_info_for_sign_fields() == [])
		check("flag: chưa tick → xuất báo lỗi", _expect_throw(lambda: api._download_info_for_sign("[]")))
		flagged["value"] = None
		fl = api.get_info_for_sign_fields()
		check("dialog: liệt kê dòng gộp (địa chỉ/khẩn cấp)", "Liên hệ khẩn cấp" in fl and "Địa chỉ hiện tại" in fl, fl)
	finally:
		_set("_build_config", real_build)

	# ---------- Info for Sign ----------
	recs = frappe.get_all(DT, filters={"status": "Submitted"}, fields=["name", "data_json"], limit=3, order_by="name")
	names = [r.name for r in recs]

	_set("_build_config", fake_build)  # tick tất cả cho các kiểm tra layout bên dưới
	api._download_info_for_sign(json.dumps(names))
	wb, ws, rows = _read_sheet()
	check("sign: 1 sheet tên Info for Sign", wb.sheetnames == ["Info for Sign"], wb.sheetnames)
	check(
		"sign: tiêu đề cột tiếng Việt",
		[c.value for c in ws[5]] == ["STT", "Nhân viên", "Thông tin", "Nội dung", "Ghi chú", "Chữ ký"],
	)
	check("sign: cột Ghi chú + Chữ ký luôn trống", all(r[4] in (None, "") and r[5] in (None, "") for r in rows))
	check("sign: A4 ngang", ws.page_setup.orientation == "landscape" and str(ws.page_setup.paperSize) == str(ws.PAPERSIZE_A4), (ws.page_setup.orientation, repr(ws.page_setup.paperSize)))
	first_who = next(r[1] for r in rows if r[1])
	check("sign: ô Nhân viên = Mã NV xuống dòng Họ tên", "\n" in first_who and first_who.split("\n")[0].startswith(("TIQN", "TT")), first_who)
	stts = [r[0] for r in rows if r[0] is not None]
	emps = [r[1] for r in rows if r[1]]
	check("sign: STT theo nhân viên 1..N", stts == list(range(1, len(emps) + 1)), (stts, len(emps)))
	check("sign: STT đứng cùng dòng Mã NV", all((r[0] is None) == (not r[1]) for r in rows))
	check("sign: tên file", frappe.response["filename"] == "employee_info_for_sign.xlsx")
	merged = [str(m) for m in ws.merged_cells.ranges]
	check("sign: có gộp ô Nhân viên", any(m.startswith("B") for m in merged), merged[:5])
	b_ranges = sorted(m.replace("B", "") for m in merged if m.startswith("B"))
	a_ranges = sorted(m.replace("A", "") for m in merged if m.startswith("A") and ":F" not in m)
	f_ranges = sorted(m.replace("F", "") for m in merged if m.startswith("F"))
	check("sign: Chữ ký gộp ô đúng như Nhân viên", f_ranges == sorted(m.replace("B", "") for m in merged if m.startswith("B")))
	e_ranges = sorted(m.replace("E", "") for m in merged if m.startswith("E"))
	check("sign: Ghi chú gộp ô đúng như Nhân viên", e_ranges == f_ranges, e_ranges)
	check("sign: STT gộp ô đúng như Mã NV", a_ranges == b_ranges, (a_ranges, b_ranges))
	sl = api._sign_labels(config)
	check("sign: nhãn không trùng", len(set(sl.values())) == len(sl))
	items = api._sign_items(config, None)
	kinds = [k for _l, _f, k in items]
	check("sign: địa chỉ gộp theo Section", kinds.count("address") == 2, [l for l, _f, k in items if k == "address"])
	check("sign: liên hệ khẩn cấp 1 dòng", kinds.count("emergency") == 1)
	check("sign: số CCCD + ngày cấp 1 dòng 'CCCD'", kinds.count("cccd") == 1 and ("CCCD", "cccd") in [(l, k) for l, _f, k in items])
	cccd_fields = next(fs for l, fs, k in items if k == "cccd")
	check("sign: dòng CCCD gồm đúng số + ngày cấp", [f["fieldname"] for f in cccd_fields] == ["custom_id_card_no", "custom_id_card_date_of_issue"])
	check("sign: ngày hết hạn vẫn dòng riêng", any(k == "field" and fs[0]["fieldname"] == "custom_id_card__date_of_expired" for l, fs, k in items))
	C = lambda fn: {"fieldname": fn, "fieldtype": "Date" if "date" in fn else "Data"}
	j = api._sign_join
	check("sign: CCCD = 'số, cấp ngày dd/mm/yyyy'",
		j("cccd", [(C("custom_id_card_no"), "051234567890"), (C("custom_id_card_date_of_issue"), api._sign_value_vi(C("custom_id_card_date_of_issue"), "2021-03-01"))])
		== "051234567890, cấp ngày 01/03/2021")
	check("sign: CCCD thiếu ngày cấp → chỉ số", j("cccd", [(C("custom_id_card_no"), "051234567890"), (C("custom_id_card_date_of_issue"), "")]) == "051234567890")
	check("sign: CCCD thiếu số → 'cấp ngày …'", j("cccd", [(C("custom_id_card_no"), ""), (C("custom_id_card_date_of_issue"), "01/03/2021")]) == "cấp ngày 01/03/2021")
	check("sign: CCCD trống cả hai → dòng trống", j("cccd", [(C("custom_id_card_no"), ""), (C("custom_id_card_date_of_issue"), "")]) == "")
	labels_all = {r[2] for r in rows}
	check("sign: không còn dòng Tỉnh/Xã lẻ", not any(" - Tỉnh" in l or " - Xã" in l for l in labels_all), labels_all)
	F = lambda fn, w="Auto": {"fieldname": fn, "widget": w}
	check(
		"sign: địa chỉ = thôn, xã, tỉnh",
		api._sign_join("address", [(F("p", "Address Province"), "Tỉnh Quảng Ngãi"), (F("w", "Address Ward"), "Xã Ba Tơ"), (F("v"), "Thôn 3")])
		== "Thôn 3, Xã Ba Tơ, Tỉnh Quảng Ngãi",
	)
	check(
		"sign: khẩn cấp = Tên (Quan hệ) - SĐT",
		api._sign_join("emergency", [(F("person_to_be_contacted"), "Nguyễn A"), (F("relation"), "Mẹ"), (F("emergency_phone_number"), "0905")])
		== "Nguyễn A (Mẹ) - 0905",
	)
	check(
		"sign: khẩn cấp thiếu quan hệ",
		api._sign_join("emergency", [(F("person_to_be_contacted"), "Nguyễn A"), (F("relation"), ""), (F("emergency_phone_number"), "0905")])
		== "Nguyễn A - 0905",
	)

	# Nội dung = mới, mới trống → cũ (tính lại theo từng dòng gộp)
	r0 = frappe.get_doc(DT, names[0])
	saved = json.loads(r0.data_json or "{}")
	expected = {}
	for label, fs, kind in api._sign_items(config, None):
		parts = []
		for f in fs:
			if api._is_table(f):   # bảng con: chữ nhiều dòng, cũ = dòng con trên Employee
				new_s = api._table_text(f, saved.get(f["fieldname"])).strip()
				old_s = api._table_text(f, api._employee_table_rows(r0.employee, f)).strip()
				parts.append((f, api._sign_value_vi(f, new_s or old_s)))
				continue
			new_s = str(saved.get(f["fieldname"]) or "").strip()
			old_s = "" if f.get("custom") else str(frappe.db.get_value("Employee", r0.employee, f["fieldname"]) or "").strip()
			parts.append((f, api._sign_value_vi(f, new_s or old_s)))
		expected[label] = api._sign_join(kind, parts) or None   # trống vẫn có dòng
	got, cur = {}, None
	for r in rows:
		if r[1]:
			cur = r[1].split("\n")[0]
		if cur == r0.employee:
			got[r[2]] = r[3]
	expected.pop("Ghi chú", None); got.pop("Ghi chú", None)
	check("sign: nội dung = mới, trống thì cũ", got == expected, f"{len(got)} dòng của {r0.employee}")
	n_items = len(api._sign_items(config, None))
	per_emp = {}
	cur = None
	for r in rows:
		if r[1]:
			cur = r[1]
		per_emp[cur] = per_emp.get(cur, 0) + 1
	check("sign: mỗi NV đủ dòng của mọi field được tick (kể cả trống)", set(per_emp.values()) == {n_items}, (n_items, per_emp))

	# chỉ các field được tick
	pick = [f for f in fields if f not in ("employee", "name")][:2]
	flagged["value"] = set(pick)
	api._download_info_for_sign(json.dumps(names))
	_, _, rows2 = _read_sheet()
	labels2 = {r[2] for r in rows2}
	allowed = {l for l, _f, _k in api._sign_items(config, set(pick))}
	check("sign: chỉ field được tick", labels2 and labels2 <= allowed, labels2)
	check("sign: không còn dòng Ghi chú", "Ghi chú" not in labels2)

	import inspect
	check("sign: không còn tuỳ chọn chỉ thay đổi", "only_changed" not in inspect.signature(api.download_excel).parameters)
	_set("_build_config", real_build)

	# All Info không đổi
	api.download_excel(json.dumps(names))
	from openpyxl import load_workbook

	wb_all = load_workbook(io.BytesIO(frappe.response["filecontent"]))
	check("All Info: New Data + Old Data", wb_all.sheetnames == ["New Data", "Old Data"], wb_all.sheetnames)

	# Select dịch vi
	sel = next((f for f in fields.values() if f["fieldtype"] == "Select"), None)
	check("Select: hàm dịch chạy", sel is None or api._sign_value_vi(sel, "L") == "L")
	check("Date dd/mm/yyyy", api._sign_value_vi({"fieldtype": "Date"}, "2001-05-14") == "14/05/2001")

	# ---------- bảng Submitted Information: ngày dd/mm/yyyy ----------
	import re as _re2
	rec_d = frappe.db.sql(
		f"SELECT name FROM `{'tab' + DT}` WHERE data_json LIKE '%%\"date_of_birth\": \"____-__-__\"%%' LIMIT 1", pluck=True)
	if rec_d:
		view = api.get_submission_view(rec_d[0])
		drows = [r for sec in view["sections"] for r in sec["rows"] if fields.get(r["fieldname"], {}).get("fieldtype") == "Date"]
		ok = all(
			(not r["value"] or (_re2.match(r"^\d{4}-\d{2}-\d{2}$", r["value"]) and _re2.match(r"^\d{2}/\d{2}/\d{4}$", r["display"])))
			and (not r["old"] or _re2.match(r"^\d{2}/\d{2}/\d{4}$", r["old_display"]))
			for r in drows
		)
		check("view: ngày hiển thị dd/mm/yyyy, value giữ ISO cho ô sửa", ok and drows,
			[(r["fieldname"], r["value"], r["display"], r["old_display"]) for r in drows][:3])
		other = [r for sec in view["sections"] for r in sec["rows"] if r not in drows and not r.get("columns")]  # bảng con: display = chữ, value = list
		check("view: field không phải ngày giữ nguyên", all(r["display"] == r["value"] for r in other))

	# ---------- validate_desk_edit ----------
	def fresh():
		d = frappe.get_doc(DT, names[0])
		d.load_doc_before_save()
		return d, json.loads(d.data_json or "{}")

	text_f = next((f for f in fields.values() if api._hr_editor(f) == "text"), None)
	d, data = fresh()
	if text_f:
		data[text_f["fieldname"]] = "0912345678" if text_f.get("validation") == "Phone" else "Giá trị test"
		d.data_json = json.dumps(data, ensure_ascii=False)
		check("desk: sửa text hợp lệ → qua", not _expect_throw(lambda: api.validate_desk_edit(d)), text_f["fieldname"])

	if sel and api._hr_editor(sel) == "select":
		d, data = fresh()
		data[sel["fieldname"]] = "KHÔNG-CÓ"
		d.data_json = json.dumps(data, ensure_ascii=False)
		check("desk: select sai option → chặn", _expect_throw(lambda: api.validate_desk_edit(d)))

	pairs = api._address_pairs(config)
	if pairs:
		prov, ward = pairs[0]
		d, data = fresh()
		data[prov] = "Thành phố Hà Nội"
		data[ward] = "Xã Ba Tơ"
		d.data_json = json.dumps(data, ensure_ascii=False)
		check("desk: xã không thuộc tỉnh → chặn", _expect_throw(lambda: api.validate_desk_edit(d)))
		d, data = fresh()
		data[prov] = "Tỉnh Quảng Ngãi"
		data[ward] = "Xã Ba Tô"
		d.data_json = json.dumps(data, ensure_ascii=False)
		check("desk: tỉnh/xã hợp lệ → qua", not _expect_throw(lambda: api.validate_desk_edit(d)))

	date_f = next((f for f in fields.values() if api._hr_editor(f) == "date"), None)
	check("desk: field Date có editor date", date_f is not None, date_f and date_f["fieldname"])
	if date_f:
		d, data = fresh()
		data[date_f["fieldname"]] = "2020-01-15" if date_f.get("validation") != "Future" else "2099-01-15"
		d.data_json = json.dumps(data, ensure_ascii=False)
		check("desk: sửa ngày hợp lệ → qua", not _expect_throw(lambda: api.validate_desk_edit(d)))
		d, data = fresh()
		data[date_f["fieldname"]] = "ngày-sai"
		d.data_json = json.dumps(data, ensure_ascii=False)
		check("desk: ngày sai định dạng → chặn", _expect_throw(lambda: api.validate_desk_edit(d)))
		if date_f.get("validation") == "Past":
			d, data = fresh()
			data[date_f["fieldname"]] = "2099-01-01"
			d.data_json = json.dumps(data, ensure_ascii=False)
			check("desk: ngày cấp ở tương lai → chặn", _expect_throw(lambda: api.validate_desk_edit(d)))

	d, data = fresh()
	data["khong_ton_tai"] = "x"
	d.data_json = json.dumps(data)
	check("desk: field lạ → chặn", _expect_throw(lambda: api.validate_desk_edit(d)))

	d, _ = fresh()
	d.signature = api._SIGNATURE_PREFIX + "AAAA"
	check("desk: sửa chữ ký → chặn", _expect_throw(lambda: api.validate_desk_edit(d)))

	d, _ = fresh()
	d.status = "Reviewed"
	check("desk: chỉ đổi status → qua", not _expect_throw(lambda: api.validate_desk_edit(d)))

	synced = frappe.db.get_value(DT, {"status": "Synced"}, "name")
	if synced and text_f:
		d = frappe.get_doc(DT, synced)
		d.load_doc_before_save()
		data = json.loads(d.data_json or "{}")
		data[text_f["fieldname"]] = "x"
		d.data_json = json.dumps(data)
		check("desk: phiếu Synced → chặn", _expect_throw(lambda: api.validate_desk_edit(d)))

	# ---------- save_form_data: cặp tỉnh/xã từ trang www (_portal_address_errors) ----------
	pairs_cfg = api._address_pairs(config)
	check("portal addr: config có cặp tỉnh/xã", bool(pairs_cfg), pairs_cfg)
	if pairs_cfg:
		prov, ward = pairs_cfg[0]
		emp_ok = frappe.db.sql(
			f"""SELECT e.name FROM tabEmployee e JOIN provinces p ON p.full_name = e.`{prov}` COLLATE utf8mb4_bin
			JOIN wards w ON w.province_code = p.code AND w.full_name = e.`{ward}` COLLATE utf8mb4_bin LIMIT 1"""
		)[0][0]
		cur = frappe.db.get_value("Employee", emp_ok, [prov, ward], as_dict=True)
		err = api._portal_address_errors
		check("portal addr: không đổi → qua", err(config, {prov: cur[prov], ward: cur[ward]}, emp_ok) == [], emp_ok)
		check("portal addr: đổi sang cặp đúng → qua", err(config, {prov: "Tỉnh Quảng Ngãi", ward: "Xã Ba Tô"}, emp_ok) == [])
		check("portal addr: xã không thuộc tỉnh → chặn", len(err(config, {prov: "Thành phố Hà Nội", ward: "Xã Ba Tơ"}, emp_ok)) == 1)
		check("portal addr: xã bịa → chặn", len(err(config, {prov: "Tỉnh Quảng Ngãi", ward: "Xã Không Có"}, emp_ok)) == 1)
		check("portal addr: xã không dấu → chặn (không tự đoán)", len(err(config, {prov: "Tỉnh Quảng Ngãi", ward: "Xa Ba To"}, emp_ok)) == 1)
		check("portal addr: đổi tỉnh, giữ xã cũ không thuộc tỉnh mới → chặn",
			len(err(config, {prov: "Thành phố Hà Nội", ward: cur[ward]}, emp_ok)) == 1)
		check("portal addr: chỉ gửi xã (tỉnh read_only) → lấy tỉnh từ Employee",
			err(config, {ward: cur[ward]}, emp_ok) == [] and len(err(config, {ward: "Phường Ba Đình"}, emp_ok)) == 1)
		legacy_checked = False
		for lp, lw in pairs_cfg:
			legacy = frappe.db.get_value("Employee", {lp: "Tỉnh Quảng Nam"}, ["name", lp, lw], as_dict=True)
			if legacy:
				check("portal addr: hồ sơ tên cũ không đổi → qua",
					err(config, {lp: legacy[lp], lw: legacy[lw]}, legacy.name) == [], (legacy.name, legacy[lp]))
				check("portal addr: hồ sơ tên cũ, đổi xã → chặn (tỉnh cũ không còn)",
					len(err(config, {lp: legacy[lp], lw: "Xã Ba Tơ"}, legacy.name)) == 1)
				legacy_checked = True
				break
		check("portal addr: có hồ sơ tên cũ để kiểm", legacy_checked)

	# ---------- save_form_data: chữ ký sai định dạng (throw TRƯỚC khi lưu) ----------
	check(
		"portal: chữ ký sai định dạng → chặn",
		_expect_throw(lambda: api.save_form_data(r0.employee, "{}", signature="data:text/html,<script>")),
	)
	check(
		"portal: chữ ký quá lớn → chặn",
		_expect_throw(lambda: api.save_form_data(r0.employee, "{}", signature=api._SIGNATURE_PREFIX + "A" * 500_000)),
	)

	# ---------- phiếu PDF/PNG ----------
	d = frappe.get_doc(DT, names[0])
	d.signature = api._SIGNATURE_PREFIX + "iVBORw0KGgo="
	d.commitment_confirmed = 1
	d.signed_on = frappe.utils.now_datetime()
	html = api._build_submission_html(d, json.loads(d.data_json or "{}"), config)
	check("receipt: có câu cam kết + ảnh chữ ký", api._commitment_html() in html and "class='sig'" in html)
	import re as _re
	date_fields = [f["fieldname"] for sec in config["sections"] for f in sec["fields"] if f["fieldtype"] == "Date"]
	saved_t = json.loads(d.data_json or "{}")
	for i, fn in enumerate(date_fields):
		saved_t[fn] = f"20{10 + i}-0{1 + i}-2{i}"   # gắn ngày ISO để kiểm định dạng
	html = api._build_submission_html(d, saved_t, config)
	saved_dates = {fn: saved_t.get(fn) for fn in date_fields}
	iso_left = [v for v in saved_dates.values() if v and str(v) in html]
	vn_ok = all(api._fmt_date_vn(v) in html for v in saved_dates.values() if v)
	check("receipt: ngày dd/mm/yyyy, không còn yyyy-mm-dd", vn_ok and not iso_left and not _re.search(r">\d{4}-\d{2}-\d{2}<", html), saved_dates)
	lbl_css = _re.search(r"td\.lbl\{\{?[^}]*\}", html)
	check("receipt: cột nhãn không tô nền, chỉ tiêu đề Section có nền",
		lbl_css and "background" not in lbl_css.group(0) and _re.search(r"td\.sec\{\{?[^}]*background", html), lbl_css and lbl_css.group(0))
	check("receipt: đã ký → không có Thời điểm gửi", "Thời điểm gửi" not in html and "Ký lúc" in html)
	d2 = frappe.get_doc(DT, names[0])
	html2 = api._build_submission_html(d2, json.loads(d2.data_json or "{}"), config)
	check("receipt: chưa ký → giữ Thời điểm gửi", "Thời điểm gửi" in html2 or not d2.submitted_on)
	d.signature = "javascript:alert(1)"
	html = api._build_submission_html(d, json.loads(d.data_json or "{}"), config)
	check("receipt: chữ ký lạ không chèn ảnh", "class='sig'" not in html)

	check("hr pdf: tên file", api._receipt_base(d).startswith(d.employee))
	api.download_pdf_for_hr(names[0])
	check("hr pdf: tải về (attachment)", frappe.response.get("type") == "download", frappe.response.get("type"))
	check("hr pdf: ra file PDF", frappe.response["filecontent"][:4] == b"%PDF" and frappe.response["filename"].endswith(".pdf"),
		(frappe.response["filename"], len(frappe.response["filecontent"])))

	# PDF Split For Each Employee: 1 bản ghi → PDF như Generate PDF; nhiều bản ghi → ZIP mỗi NV 1 PDF.
	import io as _io
	import zipfile as _zip
	api.download_excel(json.dumps(names[:1]), "Info for Sign", "PDF Split")
	check("pdf split: 1 bản ghi → PDF thẳng", frappe.response["filecontent"][:4] == b"%PDF"
		and frappe.response["content_type"] == "application/pdf", frappe.response["filename"])
	api.download_excel(json.dumps(names[:2]), "Info for Sign", "PDF Split")
	zf = _zip.ZipFile(_io.BytesIO(frappe.response["filecontent"]))
	members = zf.namelist()
	check("pdf split: nhiều bản ghi → ZIP mỗi NV 1 PDF",
		frappe.response["content_type"] == "application/zip" and len(members) == 2
		and all(zf.read(m)[:4] == b"%PDF" for m in members), members)
	check("pdf split: giới hạn số bản ghi như PDF gộp",
		_expect_throw(lambda: api._download_info_for_sign_pdf_split(None))
		or frappe.db.count(DT) <= api.INFO_FOR_SIGN_PDF_MAX_RECORDS)

	# PDF Split chỉ in field tick "Info for Sign" — field custom (không có trên Employee) cũng theo cờ.
	cfg_live = real_build()
	all_fields = [f for sec in cfg_live["sections"] for f in sec["fields"]]
	ticked = {f["fieldname"] for f in all_fields if f.get("info_for_sign")}
	if ticked:
		kept = {f["fieldname"] for sec in api._info_for_sign_config(cfg_live)["sections"] for f in sec["fields"]}
		check("pdf split: chỉ giữ field tick Info for Sign (Setting thật)", kept == ticked, sorted(kept ^ ticked))
		unticked_custom = [f["fieldname"] for f in all_fields if f.get("custom") and not f.get("info_for_sign")]
		check("pdf split: field custom không tick bị loại", not (set(unticked_custom) & kept), unticked_custom)
	fake = {"sections": [
		{"label": "A", "fields": [
			{"fieldname": "real_on", "label": "Real On", "custom": False, "info_for_sign": True},
			{"fieldname": "real_off", "label": "Real Off", "custom": False, "info_for_sign": False},
			{"fieldname": "cus_on", "label": "Custom On", "custom": True, "info_for_sign": True},
			{"fieldname": "cus_off", "label": "Custom Off", "custom": True, "info_for_sign": False},
		]},
		{"label": "B", "fields": [{"fieldname": "cus_b", "label": "B Off", "custom": True, "info_for_sign": False}]},
	]}
	got = api._info_for_sign_config(fake)
	check("pdf split: lọc theo cờ, bỏ Section rỗng",
		[(s["label"], [f["fieldname"] for f in s["fields"]]) for s in got["sections"]] == [("A", ["real_on", "cus_on"])],
		got)
	check("pdf split: chưa tick field nào → báo lỗi",
		_expect_throw(lambda: api._info_for_sign_config({"sections": [{"label": "A", "fields": [fake["sections"][0]["fields"][3]]}]})))
	d0 = frappe.get_doc(DT, names[0])
	html0 = api._build_submission_html(d0, json.loads(d0.data_json or "{}"), got)
	# Phiếu chưa ký trên www: PDF Split vẫn in cam kết + ô ký tay; Generate PDF giữ như cũ.
	d_un = frappe.get_doc(DT, names[0])
	d_un.signature, d_un.commitment_confirmed, d_un.signed_on = "", 0, None
	h_paper = api._build_submission_html(d_un, {}, got, sign_on_paper=True)
	h_plain = api._build_submission_html(d_un, {}, got)
	check("pdf split: chưa ký → vẫn có cam kết + ô ký tay",
		api._commitment_html() in h_paper and "Người khai ký tên" in h_paper and "class='sigspace'" in h_paper)
	check("generate pdf: chưa ký → không thêm khung ký", "Người khai ký tên" not in h_plain)
	d_sg = frappe.get_doc(DT, names[0])
	d_sg.signature, d_sg.commitment_confirmed = api._SIGNATURE_PREFIX + "AAAA", 1
	h_sg = api._build_submission_html(d_sg, {}, got, sign_on_paper=True)
	check("pdf split: đã ký → in ảnh chữ ký, không thêm ô trống",
		"class='sig'" in h_sg and "class='sigspace'" not in h_sg)
	# Generate PDF + PDF Split dùng chung _hr_receipt_html = phiếu trang www, chỉ lọc field Info for Sign.
	d_hr = frappe.get_doc(DT, names[0])
	www_html = api._build_submission_html(d_hr, json.loads(d_hr.data_json or "{}"), got)
	hr_html = api._hr_receipt_html(d_hr, got)
	# Phiếu HR có thêm bảng hồ sơ (Setting → Document Checklist) — bỏ ra trước khi so với phiếu www.
	chk = api._document_checklist_html(api._get_setting().get("pdf_document_checklist"))
	hr_cmp = hr_html.replace(chk, "", 1) if chk else hr_html
	# … và địa chỉ gom 1 dòng (compact) → so với phiếu www dựng cùng cờ.
	www_cmp = api._build_submission_html(
		d_hr, api._fill_from_employee(got, json.loads(d_hr.data_json or "{}"), d_hr.employee), got,
		compact=True, side_margin=api.HR_RECEIPT_SIDE_MARGIN, tb_margin=api.HR_RECEIPT_TB_MARGIN,
	)
	check("hr receipt: đúng phiếu trang www (cùng config) khi đã có khung ký",
		hr_cmp == www_cmp or ("class='sigspace'" in hr_cmp and "class='sigspace'" not in www_html))
	check("hr receipt: có cam kết + khung ký", api._commitment_html() in hr_html and "Người khai ký tên" in hr_html)
	if ticked:
		live_sign = api._info_for_sign_config(cfg_live)
		hr_live = api._hr_receipt_html(d_hr, live_sign)
		off_labels = [f["label"] for f in all_fields if not f.get("info_for_sign")
			and f["label"] not in {g["label"] for s2 in live_sign["sections"] for g in s2["fields"]}]
		check("hr receipt: không có nhãn field không tick (Setting thật)",
			not [l for l in off_labels if f">{frappe.utils.escape_html(l)}<" in hr_live], off_labels)
	import inspect

	# Generate PDF + PDF Split cùng 1 đường: _hr_receipt_pdf (thu nhỏ vừa 1 trang) → _hr_receipt_html.
	check("generate pdf + pdf split cùng gọi _hr_receipt_pdf → _hr_receipt_html",
		"_hr_receipt_pdf(doc, " in inspect.getsource(api.download_pdf_for_hr)
		and "_hr_receipt_pdf(doc, " in inspect.getsource(api._download_info_for_sign_pdf_split)
		and "_hr_receipt_html(doc, " in inspect.getsource(api._hr_receipt_pdf))
	check("pdf split: phiếu không có nhãn field không tick",
		"Custom On" in html0 and "Real On" in html0 and "Custom Off" not in html0 and "Real Off" not in html0
		and ">B<" not in html0)

	cfg = api.get_field_config()
	check("config: có commitment_html", bool(cfg.get("commitment_html")))
	check("config: không còn purpose_text (thông báo đầu trang lấy từ index.html)", "purpose_text" not in cfg)
	check("config: field mang cờ info_for_sign", all("info_for_sign" in f for s in cfg["sections"] for f in s["fields"]))

	frappe.db.rollback()
	failed = [r for r in results if not r[0]]
	for ok, name, detail in results:
		print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if detail != '' else ''}")
	print(f"\n{len(results) - len(failed)}/{len(results)} passed")
	return {"passed": len(results) - len(failed), "failed": len(failed)}


def test_join_today():
	"""Nút "Employee Join Today" trên Setting — chạy thật rồi ROLLBACK (không để lại thay đổi).

	bench --site erp.tiqn.local execute \
		customize_erpnext.api.self_update_info.test_self_update_sign.test_join_today
	"""
	import frappe.utils

	results = []
	SETTING = "Employee Self Update Info Setting"
	before = [r.employee for r in frappe.get_doc(SETTING).employees]
	day = frappe.db.sql(
		"SELECT date_of_joining FROM tabEmployee WHERE status='Active' AND date_of_joining IS NOT NULL "
		"GROUP BY date_of_joining HAVING COUNT(*) >= 2 ORDER BY date_of_joining DESC LIMIT 1"
	)[0][0]
	expected = set(frappe.get_all("Employee", {"status": "Active", "date_of_joining": day}, pluck="name"))
	real_today = frappe.utils.today
	try:
		frappe.utils.today = lambda: str(day)
		doc = frappe.get_doc(SETTING)
		doc.btn_join_today()
		got = [r.employee for r in frappe.get_doc(SETTING).employees]
		results.append(("có người vào làm → đúng danh sách", set(got) == expected and len(got) == len(expected), (str(day), len(got))))
		results.append(("danh sách cũ bị xoá hết", not (set(before) - expected) or not set(before) & set(got) - expected, before))
		frappe.utils.today = lambda: "1900-01-01"
		frappe.get_doc(SETTING).btn_join_today()
		results.append(("không ai vào làm → danh sách trống", len(frappe.get_doc(SETTING).employees) == 0))
	finally:
		frappe.utils.today = real_today
		frappe.db.rollback()
		frappe.clear_messages()
	after = [r.employee for r in frappe.get_doc(SETTING).employees]
	results.append(("rollback: Setting giữ nguyên", after == before, after))
	for ok, name, *d in [(r[1], r[0], *r[2:]) for r in results]:
		print(f"{'PASS' if ok else 'FAIL'}  {name}  {d[0] if d else ''}")
	return {"passed": sum(1 for r in results if r[1]), "failed": sum(1 for r in results if not r[1])}


def test_cccd_expiry():
	"""Ngày hết hạn CCCD tự tính — thuật toán + Employee hook + self-update (KHÔNG ghi DB).

	bench --site erp.tiqn.local execute \
		customize_erpnext.api.self_update_info.test_self_update_sign.test_cccd_expiry
	"""
	from customize_erpnext.api.employee import cccd_expiry as cx

	results = []

	def check(name, ok, detail=""):
		results.append((bool(ok), name, detail))

	iso = cx.cccd_expiry_iso
	# thuật toán (đối chiếu kết quả bản JS của trang)
	check("2001-07-29 cấp 2023-08-12 → 2026-07-29 (mốc 25)", iso("2001-07-29", "2023-08-12") == "2026-07-29")
	check("1990-05-10 cấp 2021-03-01 → 2030-05-10 (mốc 40)", iso("1990-05-10", "2021-03-01") == "2030-05-10")
	check("cấp trong 2 năm trước mốc 25 → mốc 40", iso("2000-01-01", "2023-06-01") == "2040-01-01")
	check("cấp từ 58 tuổi → không thời hạn", iso("1965-01-01", "2023-06-01") == "")
	check("cấp sau 60 tuổi → không thời hạn", iso("1950-01-01", "2023-06-01") == "")
	check("sinh 29/02, năm không nhuận → 28/02", iso("2000-02-29", "2021-01-01") == "2025-02-28")
	check("sinh 29/02, năm nhuận → 29/02", iso("2000-02-29", "2035-01-01") == "2040-02-29")
	check("thiếu ngày sinh / ngày cấp → trống", iso(None, "2021-01-01") == "" and iso("2000-01-01", "") == "")

	# Employee hook (trong bộ nhớ)
	emp = frappe.get_doc("Employee", frappe.db.get_value(
		"Employee", {"date_of_birth": ["is", "set"], "custom_id_card_date_of_issue": ["is", "set"]}, "name"))
	emp.custom_id_card__date_of_expired = "2099-01-01"
	cx.set_employee_cccd_expiry(emp)
	check("Employee hook: ghi đè giá trị nhập tay bằng giá trị tính",
		str(emp.custom_id_card__date_of_expired) == iso(emp.date_of_birth, emp.custom_id_card_date_of_issue), emp.name)
	emp.custom_id_card_date_of_issue = None
	cx.set_employee_cccd_expiry(emp)
	check("Employee hook: xoá ngày cấp → xoá ngày hết hạn", emp.custom_id_card__date_of_expired is None)
	meta_ro = frappe.get_meta("Employee").get_field(cx.EXPIRY_FIELD).read_only
	check("Employee: field ngày hết hạn read_only", meta_ro == 1)
	check("Employee hook đã đăng ký", "customize_erpnext.api.employee.cccd_expiry.set_employee_cccd_expiry"
		in frappe.get_hooks("doc_events")["Employee"]["validate"])

	# self-update
	config = api._build_config()
	fields = {f["fieldname"]: f for s in config["sections"] for f in s["fields"]}
	if cx.EXPIRY_FIELD in fields:
		check("bảng HR: ngày hết hạn không có ô sửa", api._hr_editor(fields[cx.EXPIRY_FIELD]) is None)
		vals = {cx.DOB_FIELD: "1990-05-10", cx.ISSUE_FIELD: "2021-03-01", cx.EXPIRY_FIELD: "2099-12-31"}
		api._apply_cccd_expiry(config, vals, emp.name)
		check("portal: bỏ giá trị gửi lên, tính lại", vals[cx.EXPIRY_FIELD] == "2030-05-10", vals)
		vals = {cx.ISSUE_FIELD: "2021-03-01"}
		api._apply_cccd_expiry(config, vals, emp.name)
		check("portal: thiếu ngày sinh trong form → lấy Employee",
			vals[cx.EXPIRY_FIELD] == iso(emp.date_of_birth, "2021-03-01"), vals)
		name = frappe.db.get_value(DT, {"status": ["!=", "Synced"]}, "name")
		if name and cx.ISSUE_FIELD in fields and api._hr_editor(fields[cx.ISSUE_FIELD]):
			d = frappe.get_doc(DT, name)
			d.load_doc_before_save()
			data = json.loads(d.data_json or "{}")
			data[cx.ISSUE_FIELD] = "2021-03-01"
			d.data_json = json.dumps(data, ensure_ascii=False)
			api.validate_desk_edit(d)
			after = json.loads(d.data_json)
			dob = after.get(cx.DOB_FIELD) or frappe.db.get_value("Employee", d.employee, cx.DOB_FIELD)
			check("bảng HR: sửa ngày cấp → ngày hết hạn tính lại", after.get(cx.EXPIRY_FIELD) == iso(dob, "2021-03-01"), name)
	frappe.db.rollback()

	for ok, name, detail in results:
		print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if detail != '' else ''}")
	fail = sum(1 for r in results if not r[0])
	print(f"\n{len(results) - fail}/{len(results)} passed")
	return {"passed": len(results) - fail, "failed": fail}


def test_info_for_sign_pdf():
	"""PDF Info for Sign — không ghi DB.

	A) cấu hình THẬT trong Setting → bố cục 4/5 NV, chữ ≥ 6px, số trang đúng, "Trang x/y".
	B) tick TẤT CẢ field (giả lập trong bộ nhớ) → 4/5 không vừa → tự lùi bố cục, không trang nào tràn.

	bench --site erp.tiqn.local execute \
		customize_erpnext.api.self_update_info.test_self_update_sign.test_info_for_sign_pdf
	"""
	import math
	import re

	from pypdf import PdfReader

	results = []
	real_build = api._build_config
	real_html = api._info_for_sign_pdf_html
	tried = []

	def spy_html(pages, company, font_px):
		tried.append((font_px, [len(p) for p in pages]))
		return real_html(pages, company, font_px)

	def fake_all():
		cfg = real_build()
		for sec in cfg["sections"]:
			for f in sec["fields"]:
				f["info_for_sign"] = True
		return cfg

	def export(names):
		tried.clear()
		api.download_excel(json.dumps(names), "Info for Sign", "PDF")
		pdf = PdfReader(io.BytesIO(frappe.response["filecontent"]))
		texts = [p.extract_text() or "" for p in pdf.pages]
		codes = [len(set(re.findall(r"(?:TIQN|TT|Test)-\d+", t))) for t in texts]
		return pdf, texts, codes

	_set("_info_for_sign_pdf_html", spy_html)
	try:
		all_names = sorted(frappe.get_all(DT, pluck="name", order_by="employee asc", limit=24))
		rows_real = len(api._sign_items(real_build(), api._info_for_sign_wanted(real_build())))
		F, P = api.INFO_FOR_SIGN_PDF_FIRST, api.INFO_FOR_SIGN_PDF_PER_PAGE
		results.append(((F, P) == (4, 5), "bố cục mặc định: trang 1 = 4 NV, sau = 5 NV", (F, P)))
		if rows_real:
			for n in (4, 9, 14, 24):
				pdf, texts, codes = export(all_names[:n])
				# Bố cục thật = 4/5, hoặc lùi theo _SIGN_PDF_FALLBACK khi Setting tick nhiều mục (vd 16 dòng/NV → 3/4).
				# Chỉ 2 trang thì trang 2 không đủ để đọc số NV/trang → lấy theo bố cục có trang 1 = codes[0].
				per_of = dict(((F, P),) + api._SIGN_PDF_FALLBACK)
				f1, p1 = (codes[0], codes[1] if len(codes) > 2 else per_of.get(codes[0], P)) if len(codes) > 1 else (F, P)
				layout_ok = (f1, p1) in ((F, P),) + api._SIGN_PDF_FALLBACK or n <= f1
				exp = 1 + math.ceil(max(0, n - f1) / p1)
				fonts_ok = sorted({f for f, lay in tried if lay[0] == min(f1, n)})
				results.append((layout_ok and len(pdf.pages) == exp and codes[0] == min(f1, n) and all(c == p1 for c in codes[1:-1])
					and sum(codes) == n,
					f"A) thật ({rows_real} dòng/NV) {n} NV → {exp} trang, bố cục {f1}/{p1} NV mỗi trang", (codes, fonts_ok)))
				results.append((all(f"Trang {i + 1}/{exp}" in t for i, t in enumerate(texts)), f"A) {n} NV: 'Trang x/{exp}'", ""))
				results.append(("DANH SÁCH XÁC NHẬN" in texts[0] and all("Thông tin" in t and "Chữ ký" in t for t in texts),
					f"A) {n} NV: tiêu đề trang 1 + tên cột mọi trang", ""))
				box = pdf.pages[0].mediabox
				results.append((float(box.width) > float(box.height), f"A) {n} NV: A4 ngang", ""))
		else:
			results.append((True, "A) bỏ qua — Setting chưa tick Info for Sign", ""))

		_set("_build_config", fake_all)
		pdf, texts, codes = export(all_names[:24])
		layout_used = tried[-1][1][:2] if tried else None
		results.append((0 not in codes and sum(codes) == 24, "B) tick tất cả, 24 NV: không trang nào tràn/trống", (codes, layout_used)))
		results.append((frappe.response["filename"] == f"employee_info_for_sign_{frappe.utils.now_datetime().strftime('%d%m%Y')}.pdf",
			"tên file PDF = employee_info_for_sign_ddmmyyyy.pdf", frappe.response["filename"]))
		results.append((frappe.response.get("type") == "download" and frappe.response.get("content_type") == "application/pdf",
			"PDF Info for Sign tải về (attachment), không mở xem", frappe.response.get("type")))
		over = sorted(frappe.get_all(DT, pluck="name", limit=api.INFO_FOR_SIGN_PDF_MAX_RECORDS + 1))
		blocked = False
		try:
			api.download_excel(json.dumps(over), "Info for Sign", "PDF")
		except frappe.ValidationError:
			blocked = True
			frappe.clear_messages()
		results.append((blocked and len(over) > api.INFO_FOR_SIGN_PDF_MAX_RECORDS, "PDF > 100 phiếu → chặn", len(over)))
		blocked_all = False
		try:
			api.download_excel(None, "Info for Sign", "PDF")   # không chọn dòng nào = tất cả (914)
		except frappe.ValidationError:
			blocked_all = True
			frappe.clear_messages()
		results.append((blocked_all, "PDF không chọn dòng (= tất cả > 100) → chặn", ""))
		api.download_excel(json.dumps(over), "Info for Sign", "Excel")
		results.append((frappe.response.get("filename") == "employee_info_for_sign.xlsx", "Excel > 100 phiếu vẫn xuất", ""))
		results.append((codes[0] < F, "B) tick tất cả: đã lùi bố cục (< 4 NV trang 1)", codes[:3]))
		results.append((all(f"Trang {i + 1}/{len(texts)}" in t for i, t in enumerate(texts)), "B) đánh số trang đúng", len(texts)))
	finally:
		_set("_build_config", real_build)
		_set("_info_for_sign_pdf_html", real_html)
		frappe.db.rollback()
	for ok, name, detail in results:
		print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
	fail = sum(1 for r in results if not r[0])
	print(f"\n{len(results) - fail}/{len(results)} passed")
	return {"passed": len(results) - fail, "failed": fail}


def test_normalize_text():
	"""Tự chuẩn hoá chữ (16/10/2026) — không ghi DB.

	bench --site erp.tiqn.local execute \
		customize_erpnext.api.self_update_info.test_self_update_sign.test_normalize_text
	"""
	results = []
	n = api._normalize_text
	D = {"fieldtype": "Data", "widget": "Auto"}
	CW = {**D, "validation": "Capitalize Each Word"}
	SC = {"fieldtype": "Small Text", "widget": "Auto", "validation": "Sentence Case"}
	cases = [
		(D, "  duong   minh thang ", "Duong minh thang", "gộp khoảng trắng + hoa ký tự đầu"),
		(D, "thôn 3, xóm đông", "Thôn 3, xóm đông", "chỉ hoa ký tự đầu của cả ô"),
		(D, "Xóm1,thôn", "Xóm 1,thôn", "chèn dấu cách chữ–số"),
		(D, "B2", "B2", "giữ mã B2"), (D, "TDP1", "TDP1", "giữ viết tắt TDP1"), (D, "ABC123", "ABC123", "giữ mã ABC123"),
		(D, "khu A1", "Khu A1", "giữ A1"),
		(CW, " duong  minh thang", "Duong Minh Thang", "Capitalize Each Word: tên người → Hoa Đầu Mỗi Từ"),
		(SC, "tôi thích bóng đá. thích cả cầu lông!  còn gì nữa? (hát) và nấu ăn",
			"Tôi thích bóng đá. Thích cả cầu lông! Còn gì nữa? (Hát) và nấu ăn", "Sentence Case: hoa đầu mỗi câu, giữ phần còn lại"),
		(SC, "dòng một\n dòng hai. 3 người", "Dòng một\nDòng hai. 3 người", "Sentence Case: đầu mỗi dòng; câu bắt đầu bằng số giữ nguyên"),
		({**D, "validation": "Sentence Case"}, "xin chào. TP.HCM tốt", "Xin chào. TP.HCM tốt", "Sentence Case: không đụng chữ đã hoa / viết tắt"),
		({**D, "validation": "Email"}, " Abc@Gmail.com ", "Abc@Gmail.com", "Email: chỉ bỏ khoảng trắng"),
		({"fieldtype": "Small Text", "widget": "Auto"}, "dòng 1  \n  dòng   2", "Dòng 1\ndòng 2", "Small Text giữ xuống dòng"),
		({"fieldtype": "Select", "widget": "Auto"}, "male", "male", "Select không đụng"),
		({**D, "widget": "Address Province"}, "tỉnh x", "tỉnh x", "widget địa chỉ không đụng"),
		(D, "Hoà", "Hoà", "NFC (dấu tách rời → dựng sẵn)"),
		(D, " abc.def@gmail.com ", "abc.def@gmail.com", "giá trị trông như email (chưa gán Validation) → không viết hoa"),
		({**D, "validation": "Capitalize Each Word"}, " bóng   đá, cầu lông ", "Bóng Đá, Cầu Lông", "Capitalize Each Word: hoa đầu mỗi từ"),
		({**D, "validation": "Capitalize Each Word"}, "thôn TDP1 xóm1", "Thôn TDP1 Xóm 1", "Capitalize Each Word: giữ phần còn lại (TDP1)"),
		({"fieldtype": "Small Text", "widget": "Auto", "validation": "Capitalize Each Word"}, "hát karaoke\n nấu  ăn",
			"Hát Karaoke\nNấu Ăn", "Capitalize Each Word: mỗi dòng"),
	]
	for f, v, exp, name in cases:
		got = n(f, v)
		results.append((got == exp, name, (v, got)))

	# HR sửa trên Desk cũng được chuẩn hoá
	config = api._build_config()
	text_f = next((f for s in config["sections"] for f in s["fields"]
		if api._hr_editor(f) == "text" and not f.get("validation")), None)
	name = frappe.db.get_value(DT, {"status": ["!=", "Synced"]}, "name")
	if text_f and name:
		d = frappe.get_doc(DT, name)
		d.load_doc_before_save()
		data = json.loads(d.data_json or "{}")
		data[text_f["fieldname"]] = "  xóm1   thôn  tây "
		d.data_json = json.dumps(data, ensure_ascii=False)
		api.validate_desk_edit(d)
		got = json.loads(d.data_json)[text_f["fieldname"]]
		results.append((got == "Xóm 1 thôn tây", "Desk: HR sửa cũng được chuẩn hoá", (text_f["fieldname"], got)))
	import inspect
	results.append(("REMARKS_KEY" not in inspect.getsource(api.save_form_data), "save_form_data không còn lưu __remarks", ""))
	vopts = frappe.get_meta("Employee Self Update Info Field").get_field("validation").options.split("\n")
	results.append(("Person Name" not in vopts and {"Capitalize Each Word", "Sentence Case"} <= set(vopts),
		"Setting: Validation bỏ 'Person Name', có 'Capitalize Each Word' + 'Sentence Case'", vopts))
	results.append((not frappe.db.count("Employee Self Update Info Field", {"validation": "Person Name"}),
		"Setting: không còn dòng nào dùng 'Person Name'", ""))
	frappe.db.rollback()
	for ok, nm, detail in results:
		print(f"{'PASS' if ok else 'FAIL'}  {nm}  {detail}")
	fail = sum(1 for r in results if not r[0])
	print(f"\n{len(results) - fail}/{len(results)} passed")
	return {"passed": len(results) - fail, "failed": fail}


def test_table_fields():
	"""Field bảng con (education, external_work_history) — KHÔNG ghi DB (chỉ đọc + doc trong bộ nhớ, rollback).

	    bench --site erp.tiqn.local execute \\
	        customize_erpnext.api.self_update_info.test_self_update_sign.test_table_fields
	"""
	results = []

	def check(name, ok, detail=""):
		results.append((bool(ok), name, detail))

	frappe.set_user("Administrator")
	# Setting giả lập TRONG BỘ NHỚ: thêm 2 dòng bảng con + 1 dòng internal_work_history (bị chặn).
	real_rows = api._selected_rows

	def fake_rows(setting):
		# Bỏ dòng thật của 2 bảng con (Setting thật có thể đã tick Info for Sign) → chỉ còn dòng giả bên dưới.
		rows = [r for r in real_rows(setting)
			if r.employee_fieldname not in ("education", "external_work_history", "internal_work_history")]
		base = {"enable": 1, "is_custom": 0, "widget": "Auto", "auto_fill_data": 1, "required": 0, "read_only": 0,
			"validation": "", "min_length": 0, "max_length": 0, "regex": "", "detail": "", "placeholder": ""}
		rows.append(frappe._dict(base, employee_fieldname="education", label_vi="Học vấn", section_label="Học vấn",
			info_for_sign=1, max_rows=0, table_columns=""))
		rows.append(frappe._dict(base, employee_fieldname="external_work_history", label_vi="Quá trình làm việc",
			section_label="Quá trình làm việc", info_for_sign=0, max_rows=2,
			table_columns="company_name | Công ty | 1\nsalary | Lương | 0\nkhong_co | X | 0\ntotal_experience"))
		rows.append(frappe._dict(base, employee_fieldname="internal_work_history", label_vi="Nội bộ", section_label="X"))
		return rows

	_set("_selected_rows", fake_rows)
	try:
		cfg = api._build_config()
		fields = {f["fieldname"]: f for s in cfg["sections"] for f in s["fields"]}
		edu, ext = fields.get("education"), fields.get("external_work_history")
		check("config: education có, mặc định 4 cột + 3 dòng",
			edu and [c["fieldname"] for c in edu["columns"]] == ["level", "school_univ", "maj_opt_subj", "year_of_passing"]
			and edu["max_rows"] == 3 and edu["fieldtype"] == "Table", edu and edu["columns"])
		check("config: Level lấy options tiếng Việt (Property Setter)", edu and "Cao đẳng" in edu["columns"][0]["options"])
		check("config: Table Columns tự khai — bỏ cột lạ + cột Currency (lương), nhãn trống lấy theo DocType",
			ext and [c["fieldname"] for c in ext["columns"]] == ["company_name", "total_experience"]
			and ext["columns"][0]["required"] and ext["max_rows"] == 2, ext and ext["columns"])
		check("config: internal_work_history bị chặn", "internal_work_history" not in fields)
		check("scalar fields không gồm bảng con", not {"education", "external_work_history"} & set(api._employee_scalar_fields(cfg)))

		# ---- _clean_table_value ----
		# NV vừa có phiếu vừa có dòng Education (để thử cả view / desk / Info for Sign)
		emp_id = frappe.db.sql(
			"""select i.employee from `tabEmployee Self Update Info` i join `tabEmployee Education` e
			on e.parent = i.employee and e.parenttype = 'Employee' where i.status <> 'Synced' order by i.employee limit 1"""
		)[0][0]
		own = api._employee_table_rows(emp_id, edu)
		check("đọc dòng Employee kèm name", own and own[0].get("name"), own)
		other = frappe.db.get_value("Employee Education", {"parenttype": "Employee", "parent": ["!=", emp_id]}, "name")
		rows, errs = api._clean_table_value(edu, [
			{"name": own[0]["name"], "school_univ": "  cao đẳng  dung quất ", "level": "Cao đẳng", "maj_opt_subj": "May",
				"year_of_passing": "2015", "x": "lạ"},
			{"name": other, "level": "THPT"},
			{"school_univ": "", "level": "", "maj_opt_subj": " "},
		], emp_id)
		check("clean: chuẩn hoá chữ, bỏ cột lạ", rows[0]["school_univ"] == "Cao đẳng dung quất" and "x" not in rows[0], rows)
		check("clean: giữ name dòng của chính NV", rows[0].get("name") == own[0]["name"])
		check("clean: name của NV khác → bỏ (thành dòng mới)", "name" not in rows[1], rows[1])
		check("clean: bỏ dòng trống", len(rows) == 2 and not errs, (rows, errs))
		_r, errs = api._clean_table_value(edu, [{"level": "Cấp 3"}, {"school_univ": "A"}, {"school_univ": "B", "year_of_passing": "năm"}], emp_id)
		check("clean: Select sai, thiếu Trình độ (2 dòng), Int sai → 4 lỗi", len(errs) == 4, errs)
		# Trung cấp trở lên → bắt buộc Trường, Ngành, Năm TN; THCS / THPT thì không (user 16/10/2026)
		check("config: required_if Học vấn", edu.get("required_if") == {"column": "level",
			"values": ["Trung cấp", "Cao đẳng", "Đại học", "Sau đại học"],
			"columns": ["school_univ", "maj_opt_subj", "year_of_passing"],
			"required": ["school_univ", "maj_opt_subj"]}, edu.get("required_if"))
		_r, errs = api._clean_table_value(edu, [{"level": "Cao đẳng"}], emp_id)
		check("required_if: Cao đẳng thiếu Trường/Ngành → 2 lỗi (Năm TN không bắt buộc)", len(errs) == 2
			and not any("Năm tốt nghiệp" in e for e in errs), errs)
		_r, errs = api._clean_table_value(edu, [{"level": "Đại học", "school_univ": "A", "maj_opt_subj": "B", "year_of_passing": "2020"}], emp_id)
		check("required_if: Đại học đủ 3 ô → hợp lệ", not errs, errs)
		_r, errs = api._clean_table_value(edu, [{"level": "THPT"}, {"level": "THCS", "school_univ": "Trường X"}], emp_id)
		check("required_if: THCS / THPT không bắt buộc", not errs, errs)
		check("THCS/THPT: Trường/Ngành/Năm bị xoá trắng (ô ẩn)", _r[1]["school_univ"] == "" and _r[1]["level"] == "THCS", _r)
		_r, errs = api._clean_table_value(edu, [{"level": "THCS", "year_of_passing": "năm"}], emp_id)
		check("ô ẩn sai định dạng không báo lỗi (bị xoá trước khi kiểm)", not errs and _r[0]["year_of_passing"] == "", (_r, errs))
		_r, errs = api._clean_table_value(edu, [{"school_univ": "Trường Y"}], emp_id)
		check("chưa chọn trình độ: giữ Trường, không bắt buộc", _r[0]["school_univ"] == "Trường Y", (_r, errs))
		check("required_if: external không có luật", ext.get("required_if") is None)
		_r, errs = api._clean_table_value(edu, [{"level": "THCS"}] * 4, emp_id)
		check("clean: quá max_rows → lỗi", any("3" in e for e in errs), errs)
		_r, errs = api._clean_table_value(edu, json.dumps([{"level": "THCS"}]), emp_id)
		check("clean: nhận chuỗi JSON", _r == [{"school_univ": "", "level": "THCS", "maj_opt_subj": "", "year_of_passing": ""}] and not errs, _r)
		_r, errs = api._clean_table_value(edu, {"level": "THCS"}, emp_id)
		check("clean: kiểu lạ → lỗi", errs, errs)

		# ---- text / receipt ----
		txt = api._table_text(edu, [{"school_univ": "A", "level": "THCS"}, {"level": "THPT", "year_of_passing": "2010"}])
		check("text: mỗi dòng 1 hàng, bỏ ô trống", txt == "Trình độ: THCS, Trường: A\nTrình độ: THPT, Năm tốt nghiệp: 2010", txt)
		check("so sánh bỏ qua name", api._table_rows_equal(edu, [{"name": "x", "level": "THCS"}], [{"level": "THCS", "school_univ": ""}]))
		doc = frappe.get_doc(DT, frappe.get_all(DT, pluck="name", limit=1)[0])
		html = api._build_submission_html(doc, {"education": [{"school_univ": "Trường <A>", "level": "THCS"}]}, cfg)
		check("phiếu: bảng nhỏ có tiêu đề cột, escape HTML", "class='sub'" in html and "<th>Trường</th>" in html
			and "Trường &lt;A&gt;" in html)
		check("phiếu: bảng con chưa khai → —", "Quá trình làm việc</td><td class='val'>&mdash;" in html)

		# ---- Sync: sửa đúng dòng, thêm dòng mới, KHÔNG xoá dòng ngoài phiếu ----
		emp = frappe.get_doc("Employee", emp_id)
		before = [(r.name, r.school_univ, r.qualification) for r in emp.education]
		first = emp.education[0]
		_, kept, _d = api._sync_table_rows(emp, edu, [{"school_univ": "Mới", "level": "THPT"}])
		check("sync: dòng không name → thêm, dòng cũ giữ nguyên + đếm",
			len(emp.education) == len(before) + 1 and kept == len(before) and emp.education[0].school_univ == before[0][1],
			[(r.name, r.school_univ) for r in emp.education])
		emp = frappe.get_doc("Employee", emp_id)
		first = emp.education[0]
		first.qualification = "Giữ cột không cấu hình"
		_, kept, _d = api._sync_table_rows(emp, edu, [{"name": first.name, "school_univ": "Sửa", "level": "THCS", "year_of_passing": ""}])
		check("sync: name → sửa đúng dòng, giữ cột không cấu hình",
			emp.education[0].school_univ == "Sửa" and emp.education[0].qualification == "Giữ cột không cấu hình"
			and emp.education[0].year_of_passing in (None, 0) and len(emp.education) == len(before) and kept == len(before) - 1,
			[(r.name, r.school_univ, r.year_of_passing) for r in emp.education])
		# ---- Sync lại cùng phiếu (HR đưa về Submitted) KHÔNG nhân bản dòng (TIQN-2547, 22/10/2026) ----
		emp = frappe.get_doc("Employee", emp_id)
		n0 = len(emp.education)
		row0 = {c["fieldname"]: emp.education[0].get(c["fieldname"]) for c in edu["columns"]}
		form = [{k: ("" if v in (None, 0) else str(v)) for k, v in row0.items()}]
		pairs, _k, _d = api._sync_table_rows(emp, edu, form)
		check("sync: dòng không name giống hệt dòng Employee → ghép, không thêm",
			len(emp.education) == n0 and pairs[0][1] is emp.education[0], [(r.name, r.school_univ) for r in emp.education])
		pairs, _k, _d = api._sync_table_rows(emp, edu, [{"school_univ": "Dòng mới test", "level": "THPT"}])
		pairs[0][1].name = "tmp-new-row"  # emp.save() mới đặt name; giả lập
		named = api._rows_with_names(pairs)
		check("sync: ghi name dòng Employee vào phiếu", named == [{"name": "tmp-new-row", "school_univ": "Dòng mới test", "level": "THPT"}], named)
		n1 = len(emp.education)
		pairs, _k, _d = api._sync_table_rows(emp, edu, named)
		check("sync lần 2 với phiếu đã có name → sửa đúng dòng, không thêm", len(emp.education) == n1 and pairs[0][1].name == "tmp-new-row")
		pairs, _k, _d = api._sync_table_rows(emp, edu, [{"school_univ": "Dòng mới test", "level": "THPT"}])
		check("sync lần 2 với phiếu cũ chưa có name → ghép theo nội dung, không thêm", len(emp.education) == n1)
		emp = frappe.get_doc("Employee", emp_id)
		first = emp.education[0]
		pairs, _k, _d = api._sync_table_rows(emp, edu, [dict(form[0]), {"name": first.name, "school_univ": "Đổi", "level": "THPT"}])
		check("sync: dòng có name được ghép trước dòng giống nội dung", pairs[1][1] is first and pairs[0][1] is not first,
			[(r.get("name"), c.name) for r, c in pairs])
		# ---- Max Rows = 1 (Học vấn / Kinh nghiệm, user 23/10/2026): Employee chỉ giữ dòng của lần cập nhật cuối ----
		edu1 = dict(edu, max_rows=1)
		emp = frappe.get_doc("Employee", emp_id)
		emp.append("education", {"level": "THCS", "school_univ": "Cũ 1"})
		emp.append("education", {"level": "THPT", "school_univ": "Cũ 2"})
		for i, ch in enumerate(emp.education):
			ch.name = ch.name or f"tmp-old-{i}"
		n_old = len(emp.education)
		last = emp.education[-1]
		pairs, kept, dropped = api._sync_table_rows(emp, edu1, [{"level": "THPT", "school_univ": "Mới nhất"}])
		check("max 1: phiếu 1 dòng mới → Employee còn đúng dòng đó, xoá hết dòng cũ",
			[r.school_univ for r in emp.education] == ["Mới nhất"] and kept == 0 and dropped == n_old
			and emp.education[0].idx == 1 and pairs[0][1] is emp.education[0],
			[(r.name, r.school_univ, r.idx) for r in emp.education])
		emp = frappe.get_doc("Employee", emp_id)
		emp.append("education", {"level": "THCS", "school_univ": "Cũ 1"})
		emp.append("education", {"level": "THPT", "school_univ": "Cũ 2"})
		for i, ch in enumerate(emp.education):
			ch.name = ch.name or f"tmp-old-{i}"
		last = emp.education[-1]
		pairs, kept, dropped = api._sync_table_rows(emp, edu1, [{"name": last.name, "level": "THPT", "school_univ": "Sửa dòng cuối"}])
		check("max 1: phiếu sửa dòng mới nhất → giữ đúng dòng đó (cùng name), xoá phần còn lại",
			len(emp.education) == 1 and emp.education[0] is last and last.school_univ == "Sửa dòng cuối",
			[(r.name, r.school_univ) for r in emp.education])
		emp = frappe.get_doc("Employee", emp_id)
		pairs, kept, dropped = api._sync_table_rows(emp, edu1, [
			{"level": "THCS", "school_univ": "Dòng 1"}, {"level": "THPT", "school_univ": "Dòng 2"}, {"level": "THPT", "school_univ": "Dòng 3"}])
		check("max 1: phiếu cũ 3 dòng → chỉ lấy dòng cuối", [r.school_univ for r in emp.education] == ["Dòng 3"]
			and len(pairs) == 1, [r.school_univ for r in emp.education])
		emp = frappe.get_doc("Employee", emp_id)
		_, kept, dropped = api._sync_table_rows(emp, edu1, [])
		check("max 1: phiếu không có dòng → giữ 1 dòng mới nhất của Employee",
			len(emp.education) == min(1, len(before)) and (not before or emp.education[0].name == before[-1][0]) and dropped == max(len(before) - 1, 0),
			[(r.name, r.school_univ) for r in emp.education])
		emp = frappe.get_doc("Employee", emp_id)
		emp.append("education", {"level": "THPT", "school_univ": "Mới nhất DB"})
		emp.education[-1].name = "tmp-latest"
		real_get_all = frappe.get_all
		frappe.get_all = lambda *a, **k: [frappe._dict(name=r.name, **{c["fieldname"]: r.get(c["fieldname"]) for c in edu1["columns"]})
			for r in emp.education] if a and a[0] == edu1["options"] else real_get_all(*a, **k)
		try:
			pre = api._employee_table_rows(emp_id, edu1)
			pre3 = api._employee_table_rows(emp_id, edu)
		finally:
			frappe.get_all = real_get_all
		check("max 1: điền sẵn trang www chỉ dòng mới nhất", [r["name"] for r in pre] == ["tmp-latest"], pre)
		check("max 3: điền sẵn tối đa 3 dòng cuối", [r["name"] for r in pre3] == [r.name for r in emp.education][-3:], pre3)

		emp = frappe.get_doc("Employee", emp_id)
		# Chỉ kiểm dòng con (Employee có thể còn relation cũ ngoài danh sách — user tự sửa tay, 16/10/2026).
		for ch in emp.education:
			ch._validate_selects()
		check("sync: dòng con hợp lệ Select", True)

		# ---- validate_desk_edit (HR sửa trên Desk) ----
		rec = frappe.get_all(DT, filters={"employee": emp_id}, pluck="name") or []
		if rec:
			d = frappe.get_doc(DT, rec[0])
			d._doc_before_save = frappe.get_doc(DT, rec[0])
			saved = json.loads(d.data_json or "{}")
			saved["education"] = [{"name": first.name, "school_univ": " sửa trên desk ", "level": "Đại học",
				"maj_opt_subj": "Kế toán", "year_of_passing": "2018"}, {}]
			d.data_json = json.dumps(saved, ensure_ascii=False)
			api.validate_desk_edit(d)
			got = json.loads(d.data_json)["education"]
			check("desk: làm sạch list (chuẩn hoá, bỏ dòng trống, giữ name)",
				got == [{"name": first.name, "school_univ": "Sửa trên desk", "level": "Đại học", "maj_opt_subj": "Kế toán",
					"year_of_passing": "2018"}], got)
			saved["education"] = [{"name": first.name, "school_univ": "A", "level": "Đại học"}]
			d.data_json = json.dumps(saved, ensure_ascii=False)
			check("desk: Đại học thiếu Ngành → chặn", _expect_throw(lambda: api.validate_desk_edit(d)))
			saved["education"] = [{"level": "Lớp 12"}]
			d.data_json = json.dumps(saved, ensure_ascii=False)
			check("desk: Select sai → chặn", _expect_throw(lambda: api.validate_desk_edit(d)))
			view = api.get_submission_view(rec[0])
			vrow = next((r for s in view["sections"] for r in s["rows"] if r["fieldname"] == "education"), None)
			check("view: bảng con có columns + editor table + old_display",
				vrow and vrow["editor"] == "table" and vrow["columns"] and vrow["old_display"] and vrow["required_if"], vrow)

			# ---- Info for Sign: education tick → 1 dòng, chưa khai → lấy Employee ----
			people, _c = api._info_for_sign_people(json.dumps(rec[:1]))
			line = dict(people[0][2]).get("Học vấn")
			check("info for sign: dòng Học vấn lấy từ Employee khi phiếu chưa khai", line and "Trình độ" in line or line, line)
			check("info for sign: bảng con không tick → không có dòng", "Quá trình làm việc" not in dict(people[0][2]))
		else:
			check("có phiếu cho NV có Education", False, emp_id)

		# ---- save_form_data: required bảng con + lỗi gom ----
		f_req = dict(edu, required=True)
		check("required bảng con: list rỗng = thiếu", (not []) and bool([{"level": "THCS"}]))
		check("value_text Excel", api._value_text(edu, [{"level": "THCS"}]) == "Trình độ: THCS" and api._value_text({"fieldtype": "Data"}, 5) == "5")
		_ = f_req
	finally:
		_set("_selected_rows", real_rows)
		frappe.db.rollback()

	fail = 0
	for ok, name, detail in results:
		if not ok:
			fail += 1
		print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if not ok else ''}")
	print(f"\n{len(results) - fail}/{len(results)} passed")
	return {"passed": len(results) - fail, "failed": fail}


def test_document_checklist():
	"""Bảng "Hồ sơ / Tình trạng" cuối phiếu HR (Setting → Document Checklist). Không ghi DB.
	bench --site erp.tiqn.local execute customize_erpnext.api.self_update_info.test_self_update_sign.test_document_checklist"""
	from customize_erpnext.api.self_update_info import self_update_info_api as api

	results = []

	def check(name, ok, detail=""):
		results.append((bool(ok), name, detail))

	H = api._document_checklist_html
	L = lambda names: [{"document": n, "required": 0} for n in names]  # danh sách Setting (phiếu cũ, chưa tick)
	check("trống → không có khối", H([]) == "" and H(None) == "" and H(L(["", "  "])) == "")
	items = [f"Hồ sơ {i}" for i in range(1, 12)]
	h11 = H(L(items[:5] + ["  "] + items[5:]))
	trs = h11.split("<tr>")[1:]
	check("11 mục: tiêu đề + 5 hàng đôi + 1 hàng trải ngang + Thông tin khác", len(trs) == 8, len(trs))
	check("hàng 1: mục 1 bên trái, mục 6 bên phải", "1 <span class='cb'></span> Hồ sơ 1<" in trs[1] and "6 <span class='cb'></span> Hồ sơ 6<" in trs[1], trs[1])
	check("hàng 5: mục 5 + mục 10", "Hồ sơ 5<" in trs[5] and "Hồ sơ 10<" in trs[5], trs[5])
	check("mục 11 trải ngang", "colspan='2'>11 " in trs[6] and "Hồ sơ 11<" in trs[6], trs[6])
	check("dòng trống bị bỏ (không có mục 12)", "12 <span" not in h11)
	check("Thông tin khác về hồ sơ ở cuối", "Thông tin khác về hồ sơ (nếu có):" in trs[7])
	check("ô tình trạng: Đạt / Không đạt / Quá hạn / Khác",
		all(x in trs[1] for x in ("Đạt <span class='cb'>", "Không đạt <span class='cb'>", "Quá hạn <span class='cb'>", "Khác:")))
	h10 = H(L(items[:10]))
	check("10 mục: không có hàng trải ngang", "colspan='2'" not in h10 and len(h10.split("<tr>")[1:]) == 7)
	h1 = H(L(["Chỉ một"]))
	check("1 mục: 1 hàng trải ngang", "colspan='2'>1 " in h1 and len(h1.split("<tr>")[1:]) == 3)
	check("escape HTML tên hồ sơ", "&lt;b&gt;" in H(L(["<b>x</b>"])) and "<b>x" not in H(L(["<b>x</b>"])))
	check("phiếu cũ (chưa tick): không có dòng Tình trạng hồ sơ", "Tình trạng hồ sơ" not in h11)
	snap = [{"document": "A", "required": 1, "checked": 1}, {"document": "B", "required": 1, "checked": 0},
		{"document": "C", "required": 0, "checked": 0}]
	hs = H(snap)
	check("bản chụp: hồ sơ đã tick → ô ☑ (cb on), chưa tick → ô trống",
		"1 <span class='cb on'></span> A *<" in hs and "<span class='cb'></span> B *<" in hs and "C<" in hs and "C *" not in hs, hs)
	check("bản chụp: dòng Tình trạng hồ sơ liệt kê bắt buộc còn thiếu", "Thiếu: B</td>" in hs, hs)
	check("bản chụp: ô Đạt / Không đạt / Quá hạn vẫn để HR đánh tay", "Quá hạn <span class='cb'>" in hs)
	check("bản chụp đủ → Đủ", "Tình trạng hồ sơ (NV tự khai, * = bắt buộc):</b> Đủ<" in H(snap[:1] + snap[2:]))

	names = frappe.get_all(api.INFO_DT, pluck="name", limit=1)
	if names:
		doc = frappe.get_doc(api.INFO_DT, names[0])
		cfg = {"sections": [{"label": "A", "fields": [{"fieldname": "cell_number", "label": "SĐT", "fieldtype": "Data"}]}]}
		h = api._build_submission_html(doc, {}, cfg, sign_on_paper=True, checklist_html=h11)
		check("phiếu HR: bảng hồ sơ nằm TRÊN chữ ký (chữ ký cuối phiếu)",
			h.index("class='checklist'") < h.index("Người khai ký tên") and h.rindex("</table>") < h.index("Người khai ký tên"))
		check("phiếu trang www: không có bảng hồ sơ", "class='checklist'" not in api._build_submission_html(doc, {}, cfg))
		# Địa chỉ gom 1 dòng (chỉ phiếu HR): 2 Section địa chỉ liền nhau → 1 tiêu đề "Địa chỉ" + 2 dòng.
		acfg = {"sections": [
			{"label": "1. CCCD", "fields": [{"fieldname": "custom_id_card_no", "label": "Số CCCD", "fieldtype": "Data"}]},
			{"label": "2. Địa chỉ thường trú", "fields": [
				{"fieldname": "p1", "label": "Tỉnh", "fieldtype": "Data", "widget": "Address Province"},
				{"fieldname": "w1", "label": "Xã", "fieldtype": "Data", "widget": "Address Ward"},
				{"fieldname": "d1", "label": "Thôn", "fieldtype": "Data"}]},
			{"label": "3. Địa chỉ hiện tại", "fields": [
				{"fieldname": "p2", "label": "Tỉnh", "fieldtype": "Data", "widget": "Address Province"},
				{"fieldname": "w2", "label": "Xã", "fieldtype": "Data", "widget": "Address Ward"},
				{"fieldname": "d2", "label": "Thôn", "fieldtype": "Data"}]},
			{"label": "4. Gia đình", "fields": [{"fieldname": "relation", "label": "Mối quan hệ", "fieldtype": "Data"}]},
		]}
		sv = {"p1": "Tỉnh Quảng Ngãi", "w1": "Xã Trường Giang", "d1": "Đông <hoà>", "p2": "Tỉnh Quảng Ngãi"}
		hc = api._build_submission_html(doc, sv, acfg, compact=True)
		hn = api._build_submission_html(doc, sv, acfg)
		check("địa chỉ gom: thôn, xã, tỉnh trên 1 dòng (escape)",
			"<td class='val'>Đông &lt;hoà&gt;, Xã Trường Giang, Tỉnh Quảng Ngãi</td>" in hc, hc[-1500:])
		check("địa chỉ gom: section thiếu xã/thôn vẫn ghép phần có", "<td class='val'>Tỉnh Quảng Ngãi</td>" in hc)
		check("địa chỉ gom: 1 tiêu đề 'Địa chỉ' chung, không còn tiêu đề từng section",
			hc.count('class="sec">Địa chỉ</td>') == 1 and "Địa chỉ thường trú</td><td class='val'>" in hc
			and 'class="sec">Địa chỉ thường trú' not in hc)
		check("địa chỉ gom: thứ tự section giữ nguyên (CCCD → Địa chỉ → Gia đình)",
			hc.index(">CCCD<") < hc.index(">Địa chỉ<") < hc.index(">Gia đình<"))
		check("phiếu trang www: địa chỉ giữ từng dòng", 'class="sec">Địa chỉ thường trú' in hn and ">Thôn<" in hn)
		# CCCD + ngày cấp, liên hệ khẩn cấp → 1 dòng (chỉ phiếu HR / compact)
		gcfg = {"sections": [
			{"label": "1. CCCD", "fields": [
				{"fieldname": "custom_id_card_no", "label": "Số CCCD", "fieldtype": "Data"},
				{"fieldname": api.CCCD_ISSUE_FIELD, "label": "Ngày cấp", "fieldtype": "Date"},
				{"fieldname": "custom_id_card_place_of_issue", "label": "Nơi cấp", "fieldtype": "Data"}]},
			{"label": "2. Gia đình", "fields": [
				{"fieldname": "person_to_be_contacted", "label": "Người liên hệ", "fieldtype": "Data"},
				{"fieldname": "relation", "label": "Mối quan hệ", "fieldtype": "Select", "options": ["", "Mẹ"], "option_labels": {}},
				{"fieldname": "emergency_phone_number", "label": "SĐT khẩn cấp", "fieldtype": "Data"},
				{"fieldname": "marital_status", "label": "TTHN", "fieldtype": "Select", "options": ["", "Married"],
				 "option_labels": {"Married": "Đã kết hôn"}}]},
		]}
		gv = {"custom_id_card_no": "051304006293", api.CCCD_ISSUE_FIELD: "2021-05-09", "custom_id_card_place_of_issue": "Bộ Công an",
			"person_to_be_contacted": "Nguyễn Thị <Nhỏ>", "relation": "Mẹ", "emergency_phone_number": "0382417368",
			"marital_status": "Married"}
		hg = api._build_submission_html(doc, gv, gcfg, compact=True)
		check("gộp: CCCD + ngày cấp 1 dòng",
			"<td class='lbl'>CCCD</td><td class='val'>051304006293, cấp ngày 09/05/2021</td>" in hg, hg[-2500:])
		check("gộp: Nơi cấp vẫn dòng riêng", ">Nơi cấp</td><td class='val'>Bộ Công an<" in hg)
		check("gộp: liên hệ khẩn cấp 1 dòng (escape)",
			"<td class='lbl'>Liên hệ khẩn cấp</td><td class='val'>Nguyễn Thị &lt;Nhỏ&gt; (Mẹ) - 0382417368</td>" in hg)
		check("gộp: không còn dòng lẻ Số CCCD / Ngày cấp / Mối quan hệ / SĐT",
			not any(f">{x}</td>" in hg for x in ("Số CCCD", "Ngày cấp", "Người liên hệ", "Mối quan hệ", "SĐT khẩn cấp")))
		check("gộp: dòng tại vị trí field đầu, field khác trong section giữ thứ tự",
			hg.index(">CCCD</td><td class='val'>") < hg.index(">Nơi cấp<") < hg.index(">Liên hệ khẩn cấp<") < hg.index(">TTHN<"))
		check("gộp: Select khác vẫn in nhãn", "<td class='val'>Đã kết hôn</td>" in hg)
		g1 = {"sections": [{"label": "A", "fields": [gcfg["sections"][0]["fields"][0]]}]}
		check("gộp: nhóm chỉ còn 1 field → in như thường",
			">Số CCCD</td><td class='val'>051304006293<" in api._build_submission_html(doc, gv, g1, compact=True))
		hw = api._build_submission_html(doc, gv, gcfg)
		check("phiếu trang www: không gộp", ">Số CCCD</td>" in hw and ">Mối quan hệ</td>" in hw and ">Liên hệ khẩn cấp<" not in hw)
		# Mã NV + Họ tên cùng 1 dòng; Size áo + Size dép 1 dòng (chỉ phiếu HR)
		check("đầu phiếu HR: Mã NV + Họ tên cùng 1 dòng",
			f"<tr><td class='mk'>Mã nhân viên:</td><td class='mv'>{doc.employee}</td><td class='mk'>Họ và tên:</td>" in hg)
		check("đầu phiếu www: Mã NV, Họ tên 2 dòng", f"<div><b>Mã nhân viên:</b> {doc.employee}</div><div><b>Họ và tên:</b>" in hw)
		ucfg = {"sections": [{"label": "Đồng phục", "fields": [
			{"fieldname": "custom_shirt_size", "label": "Size áo", "fieldtype": "Select", "options": ["", "M"]},
			{"fieldname": "custom_shoe_size", "label": "Size dép", "fieldtype": "Select", "options": ["", "6-7"]}]}]}
		hu = api._build_submission_html(doc, {"custom_shirt_size": "M", "custom_shoe_size": "6-7"}, ucfg, compact=True)
		check("gộp: Size áo / dép 1 dòng", "<td class='lbl'>Size áo / dép</td><td class='val'>Áo: M – Dép: 6-7</td>" in hu, hu[-800:])
		hu2 = api._build_submission_html(doc, {"custom_shirt_size": "M"}, ucfg, compact=True)
		check("gộp: thiếu size dép → chỉ 'Áo: M'", "<td class='val'>Áo: M</td>" in hu2)
		gcf = {"sections": [{"label": "1. Thông tin chung", "fields": [
			{"fieldname": "gender", "label": "Giới tính", "fieldtype": "Select", "options": ["", "Male", "Female"]},
			{"fieldname": "date_of_birth", "label": "Ngày sinh", "fieldtype": "Date"},
			{"fieldname": "cell_number", "label": "Số điện thoại", "fieldtype": "Data"}]},
			{"label": "2. Khác", "fields": [{"fieldname": "custom_x", "label": "X", "fieldtype": "Data"}]}]}
		hgd = api._build_submission_html(doc, {"gender": "Female", "date_of_birth": "1989-07-04", "cell_number": "09"}, gcf, compact=True)
		meta = hgd[hgd.find("class='meta-t'"):hgd.find("</table>", hgd.find("class='meta-t'"))]
		rows_m = meta.split("<tr>")[1:]
		check("đầu phiếu HR dòng 1: Mã NV · Họ tên · Giới tính Nữ",
			len(rows_m) == 2 and "Họ và tên:" in rows_m[0] and "<td class='mk'>Giới tính:</td><td class='mv'>Nữ</td>" in rows_m[0], meta)
		check("đầu phiếu HR dòng 2: Ngày sinh dd/mm/yyyy · Số điện thoại",
			len(rows_m) == 2 and "<td class='mk'>Ngày sinh:</td><td class='mv'>04/07/1989</td><td class='mk'>Số điện thoại:</td><td class='mv'>09</td>" in rows_m[1], meta)
		doj = doc.get("date_of_joining")
		check("đầu phiếu HR dòng 2: Ngày nhận việc (từ phiếu) cuối dòng",
			len(rows_m) == 2 and f"<td class='mk'>Ngày nhận việc:</td><td class='mv'>{api._fmt_date_vn(doj) if doj else '&mdash;'}</td></tr>" in rows_m[1] + "</tr>"
			or (len(rows_m) == 2 and f"Ngày nhận việc:</td><td class='mv'>{api._fmt_date_vn(doj) if doj else '&mdash;'}</td>" in rows_m[1]), meta)
		h1 = api._build_submission_html(doc, {}, {"sections": [{"label": "A", "fields": [{"fieldname": "x", "label": "X", "fieldtype": "Data"}]}]}, compact=True)
		check("đầu phiếu HR: Setting không có Ngày sinh/SĐT → Ngày nhận việc thành dòng riêng",
			"Ngày nhận việc:" in h1 and h1[h1.find("class='meta-t'"):].count("<tr>") >= 2)
		check("bỏ hẳn Section 'Thông tin chung' + 3 dòng khỏi bảng",
			"Thông tin chung" not in hgd and ">Giới tính</td>" not in hgd and ">Ngày sinh</td>" not in hgd and ">Khác<" in hgd)
		hgw = api._build_submission_html(doc, {"gender": "Female"}, gcf)
		check("phiếu www: Giới tính vẫn là dòng trong bảng, không có đầu phiếu dạng bảng",
			">Giới tính</td>" in hgw and "class='meta-t'" not in hgw and ">Thông tin chung<" in hgw)
		hg0 = api._build_submission_html(doc, {}, {"sections": [{"label": "A", "fields": [gcf["sections"][0]["fields"][1]]}]}, compact=True)
		check("đầu phiếu HR: Setting không có Giới tính → không in", "Giới tính" not in hg0)
		check("lề PDF HR 10mm, www 15mm",
			"margin-top:10mm;margin-bottom:10mm;margin-left:10mm" in api._hr_receipt_html(doc, gcf)
			and "margin-top:15mm;margin-bottom:15mm;margin-left:15mm" in hgw)
		setting_docs = api._setting_documents()
		hr = api._hr_receipt_html(doc, cfg)
		saved0 = json.loads(doc.data_json or "{}")
		check("_hr_receipt_html: phiếu cũ → danh sách Setting; có bản chụp → in bản chụp",
			("class='checklist'" in hr) == bool(saved0.get(api.DOCUMENTS_KEY) if api.DOCUMENTS_KEY in saved0 else setting_docs),
			setting_docs)
	else:
		check("có phiếu để thử", False)

	fail = 0
	for ok, name, detail in results:
		if not ok:
			fail += 1
		print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if not ok else ''}")
	print(f"\n{len(results) - fail}/{len(results)} passed")
	return {"passed": len(results) - fail, "failed": fail}



def test_document_status():
	"""Hồ sơ nộp kèm (Setting → Document Checklist, 27/10/2026): bản chụp, Tình trạng hồ sơ, Desk, phiếu.
	Không ghi DB (doc trong bộ nhớ, rollback).
	bench --site erp.tiqn.local execute customize_erpnext.api.self_update_info.test_self_update_sign.test_document_status"""
	from customize_erpnext.api.self_update_info import self_update_info_api as api

	results = []

	def check(name, ok, detail=""):
		results.append((bool(ok), name, detail))

	frappe.set_user("Administrator")
	K = api.DOCUMENTS_KEY
	fake = frappe._dict(document_checklist=[
		frappe._dict(document=" CCCD ", required=1), frappe._dict(document="", required=1),
		frappe._dict(document="GPLX", required=0), frappe._dict(document="Khám SK", required=1)])
	sd = api._setting_documents(fake)
	check("Setting: bỏ dòng trống, strip tên, required 0/1",
		sd == [{"document": "CCCD", "required": 1}, {"document": "GPLX", "required": 0}, {"document": "Khám SK", "required": 1}], sd)
	snap = api._documents_snapshot(json.dumps(["CCCD", "GPLX", "Lạ"]), fake)
	check("bản chụp: tick theo tên, tên lạ bỏ qua",
		[d["checked"] for d in snap] == [1, 1, 0] and len(snap) == 3, snap)
	check("bản chụp: chuỗi JSON hỏng / None → chưa tick", [d["checked"] for d in api._documents_snapshot("x[", fake)] == [0, 0, 0]
		and [d["checked"] for d in api._documents_snapshot(None, fake)] == [0, 0, 0])
	check("Setting trống → bản chụp rỗng", api._documents_snapshot(["CCCD"], frappe._dict(document_checklist=[])) == [])
	check("status: thiếu bắt buộc", api._document_status(snap) == ("Documents Missing", ["Khám SK"]))
	check("status: không bắt buộc chưa tick vẫn Đủ",
		api._document_status(api._documents_snapshot(["CCCD", "Khám SK"], fake)) == ("Documents Complete", []))
	check("status: chưa có bản chụp → trống", api._document_status([]) == ("", []))
	check("clean: bỏ dòng không tên, ép 0/1", api._clean_documents(json.dumps([{"document": " A ", "required": "1", "checked": True},
		{"document": ""}, "x"])) == [{"document": "A", "required": 1, "checked": 1}])
	check("chữ trên phiếu", api._status_text_vi(snap) == "Thiếu: Khám SK"
		and api._status_text_vi(api._documents_snapshot(["CCCD", "Khám SK"], fake)) == "Đủ" and api._status_text_vi([]) == "")

	cfg = api._build_config()
	check("Sync không bao giờ đọc khoá hồ sơ (không phải field cấu hình)", K not in api._config_fieldnames(cfg))
	check("get_field_config có danh sách hồ sơ Setting", api.get_field_config().get("documents") == api._setting_documents())

	names = frappe.get_all(api.INFO_DT, pluck="name", limit=1)
	try:
		if not names:
			check("có phiếu để thử", False)
		else:
			doc = frappe.get_doc(api.INFO_DT, names[0])
			saved = json.loads(doc.data_json or "{}")
			saved[K] = snap
			doc.data_json = json.dumps(saved, ensure_ascii=False)
			api.apply_document_status(doc)
			check("apply: Documents Missing + liệt kê", doc.document_status == "Documents Missing" and doc.missing_documents == "Khám SK",
				(doc.document_status, doc.missing_documents))
			saved.pop(K)
			doc.data_json = json.dumps(saved, ensure_ascii=False)
			api.apply_document_status(doc)
			check("apply: phiếu cũ không có bản chụp → trống", doc.document_status == "" and doc.missing_documents == "")

			# Desk: HR tick hồ sơ — được cả khi Synced; sửa field khác khi Synced vẫn bị chặn.
			def desk(status, new_saved):
				d = frappe.get_doc(api.INFO_DT, names[0])
				before = frappe.get_doc(api.INFO_DT, names[0])
				before.status = status
				before.data_json = json.dumps({**json.loads(before.data_json or "{}"), K: snap}, ensure_ascii=False)
				d._doc_before_save = before
				d.status = status
				d.data_json = json.dumps(new_saved, ensure_ascii=False)
				return d
			base = {**json.loads(frappe.db.get_value(api.INFO_DT, names[0], "data_json") or "{}"), K: snap}
			ticked = [dict(x, checked=1) for x in snap]
			d = desk("Synced", {**base, K: ticked})
			api.validate_desk_edit(d)
			api.apply_document_status(d)
			check("desk: phiếu Synced vẫn tick hồ sơ được → Documents Complete", d.document_status == "Documents Complete"
				and json.loads(d.data_json)[K] == ticked, d.document_status)
			other = next((k for k in base if k not in (K, api.REMARKS_KEY)), None)
			if other:
				d = desk("Synced", {**base, K: ticked, other: "đổi-test"})
				check("desk: phiếu Synced sửa field khác → chặn", _expect_throw(lambda: api.validate_desk_edit(d)))
			d = desk("Submitted", {**base, K: [{"document": "  ", "checked": 1}, dict(snap[0], checked="0")]})
			api.validate_desk_edit(d)
			check("desk: bản chụp được làm sạch", json.loads(d.data_json)[K] == [dict(snap[0], checked=0)], json.loads(d.data_json)[K])

			view = api.get_submission_view(names[0])
			check("view: trả documents + documents_key", view.get("documents_key") == K and isinstance(view.get("documents"), list))

			# Phiếu NV tải: 2 dòng hồ sơ; phiếu HR (compact) không in 2 dòng này (đã có bảng hồ sơ).
			small = {"sections": [{"label": "A", "fields": [{"fieldname": "cell_number", "label": "SĐT", "fieldtype": "Data"}]}]}
			hw = api._build_submission_html(doc, {K: snap}, small)
			check("phiếu www: Hồ sơ nộp kèm + Đã có + Tình trạng",
				'class="sec">Hồ sơ nộp kèm<' in hw and "<td class='val'>CCCD; GPLX</td>" in hw
				and "<td class='lbl'>Tình trạng hồ sơ</td><td class='val'>Thiếu: Khám SK</td>" in hw, hw[-1200:])
			check("phiếu www: chưa có bản chụp → không có khối", "Hồ sơ nộp kèm" not in api._build_submission_html(doc, {}, small))
			check("phiếu HR (compact): không lặp 2 dòng hồ sơ", "Hồ sơ nộp kèm" not in api._build_submission_html(doc, {K: snap}, small, compact=True))
			doc.data_json = json.dumps({K: snap}, ensure_ascii=False)
			hr = api._hr_receipt_html(doc, small)
			check("phiếu HR: in bản chụp của phiếu (☑ + Thiếu)", "<span class='cb on'></span> CCCD *" in hr and "Thiếu: Khám SK" in hr)

			# PDF HR luôn 1 trang (27/10/2026): phiếu đầy đủ thật + bảng hồ sơ + câu hỏi phí → thu nhỏ vừa 1 trang.
			import io

			from pypdf import PdfReader
			full = frappe.get_doc(api.INFO_DT, names[0])
			fs = json.loads(full.data_json or "{}")
			fs[K] = api._documents_snapshot(["CCCD photo công chứng"])
			fs.setdefault("recruitment_fee_paid", "Không")
			full.data_json = json.dumps(fs, ensure_ascii=False)
			sign_cfg = api._info_for_sign_config(cfg)
			pages = len(PdfReader(io.BytesIO(api._hr_receipt_pdf(full, sign_cfg))).pages)
			check("PDF HR: luôn 1 trang", pages == 1, pages)
			tall = dict(sign_cfg, sections=sign_cfg["sections"] + [{"label": f"Thêm {i}", "fields": [
				{"fieldname": f"x{i}", "label": f"X{i}", "fieldtype": "Data"}]} for i in range(25)])
			pages = len(PdfReader(io.BytesIO(api._hr_receipt_pdf(full, tall))).pages)
			check("PDF HR: quá dài so với mức nhỏ nhất → vẫn trả PDF (nhiều trang), không lỗi", pages >= 1, pages)
	finally:
		frappe.db.rollback()

	fail = 0
	for ok, name, detail in results:
		if not ok:
			fail += 1
		print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if not ok else ''}")
	print(f"\n{len(results) - fail}/{len(results)} passed")
	return {"passed": len(results) - fail, "failed": fail}



def test_layout_width():
	"""Setting → Width on Form (27/10/2026): config["width"] = Half / Full; bảng con luôn Full. Không ghi DB.
	bench --site erp.tiqn.local execute customize_erpnext.api.self_update_info.test_self_update_sign.test_layout_width"""
	results = []

	def check(name, ok, detail=""):
		results.append((bool(ok), name, detail))

	check("_layout_width: Half / Full / trống / lạ", [api._layout_width(frappe._dict(layout_width=v)) for v in ("Half", "Full", "", None, "half")]
		== ["Half", "Full", "Full", "Full", "Full"])
	real_rows = api._selected_rows

	def fake_rows(setting):
		base = {"enable": 1, "widget": "Auto", "auto_fill_data": 1, "required": 0, "read_only": 0, "validation": "",
			"min_length": 0, "max_length": 0, "regex": "", "detail": "", "placeholder": "", "info_for_sign": 0}
		return [
			frappe._dict(base, employee_fieldname="gender", label_vi="Giới tính", section_label="A", is_custom=0, layout_width="Half"),
			frappe._dict(base, employee_fieldname="cell_number", label_vi="SĐT", section_label="A", is_custom=0, layout_width=""),
			frappe._dict(base, employee_fieldname="x_custom", label_vi="X", section_label="A", is_custom=1, custom_fieldtype="Data", layout_width="Half"),
			frappe._dict(base, employee_fieldname="education", label_vi="Học vấn", section_label="B", is_custom=0, layout_width="Half",
				max_rows=1, table_columns=""),
		]

	_set("_selected_rows", fake_rows)
	try:
		f = {x["fieldname"]: x for s in api._build_config()["sections"] for x in s["fields"]}
		check("field Employee Half → width Half", f["gender"]["width"] == "Half")
		check("field Employee để trống → Full", f["cell_number"]["width"] == "Full")
		check("field custom Half → Half", f["x_custom"]["width"] == "Half")
		check("bảng con luôn Full (dù Setting chọn Half)", f["education"]["width"] == "Full")
		check("get_field_config gửi width cho trang www",
			all("width" in x for s in api.get_field_config()["sections"] for x in s["fields"]))
	finally:
		_set("_selected_rows", real_rows)

	fail = 0
	for ok, name, detail in results:
		if not ok:
			fail += 1
		print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if not ok else ''}")
	print(f"\n{len(results) - fail}/{len(results)} passed")
	return {"passed": len(results) - fail, "failed": fail}



def test_pdf_pages_merged():
	"""Download File → Info for Sign → "PDF 1 Page Per Employee (1 File)" (27/10/2026): phiếu như PDF Split,
	gộp 1 file, mỗi bản ghi 1 trang theo mã NV. Không ghi DB.
	bench --site erp.tiqn.local execute customize_erpnext.api.self_update_info.test_self_update_sign.test_pdf_pages_merged"""
	from pypdf import PdfReader

	results = []

	def check(name, ok, detail=""):
		results.append((bool(ok), name, detail))

	frappe.set_user("Administrator")
	names = frappe.get_all(DT, pluck="name", order_by="modified desc", limit=3)
	if len(names) < 3:
		check("có ≥ 3 phiếu để thử", False, names)
	else:
		frappe.response.clear()
		api.download_excel(json.dumps(names), "Info for Sign", "PDF Pages")
		r = dict(frappe.response)
		pages = PdfReader(io.BytesIO(r["filecontent"])).pages
		order = sorted(frappe.get_all(DT, filters={"name": ["in", names]}, pluck="employee"))
		texts = [p.extract_text() or "" for p in pages]
		check("1 file PDF (không phải ZIP)", r.get("content_type") == "application/pdf" and r["filename"].endswith(".pdf")
			and r["filecontent"][:4] == b"%PDF", r.get("filename"))
		check("3 bản ghi → 3 trang", len(pages) == 3, len(pages))
		check("mỗi trang đúng 1 NV, theo thứ tự mã NV",
			all(emp in texts[i] and all(o not in texts[i] for o in order if o != emp) for i, emp in enumerate(order)),
			[t[:80] for t in texts])
		frappe.response.clear()
		api.download_excel(json.dumps(names[:1]), "Info for Sign", "PDF Pages")
		check("1 bản ghi → vẫn 1 file PDF 1 trang",
			len(PdfReader(io.BytesIO(frappe.response["filecontent"])).pages) == 1)
		frappe.response.clear()
		api.download_excel(json.dumps(names), "Info for Sign", "PDF Split")
		check("PDF Split giữ nguyên: nhiều bản ghi → ZIP", frappe.response.get("content_type") == "application/zip")
	frappe.response.clear()
	frappe.db.rollback()

	fail = 0
	for ok, name, detail in results:
		if not ok:
			fail += 1
		print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if not ok else ''}")
	print(f"\n{len(results) - fail}/{len(results)} passed")
	return {"passed": len(results) - fail, "failed": fail}



def test_receipt_download_switch():
	"""Setting "Allow Receipt Download" (28/10/2026): tắt → NV không tải được phiếu (kể cả có token); HR vẫn tải.
	Không ghi DB. bench --site erp.tiqn.local execute customize_erpnext.api.self_update_info.test_self_update_sign.test_receipt_download_switch"""
	results = []

	def check(name, ok, detail=""):
		results.append((bool(ok), name, detail))

	def refused(fn):
		try:
			fn()
		except (frappe.PermissionError, frappe.ValidationError):
			frappe.clear_messages()
			return True
		return False

	real_get = api._get_setting
	emp = frappe.get_all(DT, pluck="employee", limit=1)[0]
	try:
		for on in (1, 0):
			fake = frappe.copy_doc(real_get())
			fake.allow_receipt_download = on
			fake.validate_by_dob = 0
			fake.lock_after_submit = 0
			_set("_get_setting", lambda fake=fake: fake)
			check(f"config.allow_receipt_download = {bool(on)}", api.get_field_config()["allow_receipt_download"] is bool(on))
			frappe.set_user("Guest")
			try:
				token = api._make_download_token(emp)
				blocked = refused(lambda: api._gate_receipt(fake, emp, None, None, token))
			finally:
				frappe.set_user("Administrator")
			check("NV (Guest) có token: bật → tải được, tắt → bị chặn" + f" [{bool(on)}]", blocked is (not on), blocked)
			check(f"HR luôn tải được [{bool(on)}]", not refused(lambda: api._gate_receipt(fake, emp, None, None, None)))
		fake.allow_receipt_download = None
		check("ô trống (chưa lưu) = tắt — DB đã đặt sẵn 1 khi thêm field", not api._receipt_download_allowed(fake))
	finally:
		_set("_get_setting", real_get)
		frappe.set_user("Administrator")
		frappe.db.rollback()

	fail = 0
	for ok, name, detail in results:
		if not ok:
			fail += 1
		print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if not ok else ''}")
	print(f"\n{len(results) - fail}/{len(results)} passed")
	return {"passed": len(results) - fail, "failed": fail}



def test_start_notes():
	"""Setting "Start Screen Notes" (Text Editor, 28/10/2026): get_field_config gửi HTML đã làm sạch; editor trống → "".
	Không ghi DB. bench --site erp.tiqn.local execute customize_erpnext.api.self_update_info.test_self_update_sign.test_start_notes"""
	results = []

	def check(name, ok, detail=""):
		results.append((bool(ok), name, detail))

	real_get = api._get_setting
	fake = frappe.copy_doc(real_get())
	_set("_get_setting", lambda: fake)
	try:
		fake.start_notes = ('<div class="ql-editor read-mode"><p>Chuẩn bị <strong>CCCD</strong></p><ul><li>BHXH</li></ul>'
			'<p><a href="https://baohiemxahoi.gov.vn">tra cứu</a></p><script>alert(1)</script>'
			'<img src=x onerror=alert(1)><a href="javascript:alert(1)">j</a></div>')
		h = api.get_field_config()["start_notes_html"]
		check("giữ định dạng: đậm, danh sách, link https", "<strong>CCCD</strong>" in h and "<li>BHXH</li>" in h
			and 'href="https://baohiemxahoi.gov.vn"' in h, h)
		check("bỏ <script>, onerror, javascript:", "<script" not in h and "onerror" not in h and "javascript:" not in h, h)
		for empty in ('<div class="ql-editor read-mode"><p><br></p></div>', "", None, "   "):
			fake.start_notes = empty
			check(f"editor trống {empty!r} → ''", api.get_field_config()["start_notes_html"] == "")
		# Start Button Delay: số giây chờ lần đầu mở; trống / âm → 0
		for v, want in ((20, 20), (None, 0), (-5, 0), ("7", 7)):
			fake.start_button_delay = v
			check(f"start_button_delay {v!r} → {want}", api.get_field_config()["start_button_delay"] == want)
		check("Setting đang đặt 20 giây", real_get().get("start_button_delay") == 20, real_get().get("start_button_delay"))
	finally:
		_set("_get_setting", real_get)

	fail = 0
	for ok, name, detail in results:
		if not ok:
			fail += 1
		print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if not ok else ''}")
	print(f"\n{len(results) - fail}/{len(results)} passed")
	return {"passed": len(results) - fail, "failed": fail}


def test_select_other_and_commit():
	"""28/10/2026: widget "Select + Other" (field Data → dropdown + "Khác" gõ tự do) và bug cam kết: ký thì phải tick,
	kể cả HR. Không ghi DB (save_form_data chỉ gọi ở nhánh throw).
	bench --site erp.tiqn.local execute customize_erpnext.api.self_update_info.test_self_update_sign.test_select_other_and_commit"""
	results = []

	def check(name, ok, detail=""):
		results.append((bool(ok), name, detail))

	def throws(fn, text):
		try:
			fn()
		except frappe.ValidationError as e:
			frappe.clear_messages()
			return text in str(e)
		return False

	real_get, real_cfg = api._get_setting, api._build_config
	emp = frappe.get_all(DT, pluck="employee", limit=1)[0]
	sig = api._SIGNATURE_PREFIX + "AAAA"
	try:
		# ---- cam kết ----
		check("HR ký mà chưa tick → chặn", throws(lambda: api.save_form_data(emp, "{}", commitment=0, signature=sig), "cam kết"))
		frappe.set_user("Guest")
		try:
			check("NV chưa tick → chặn", throws(lambda: api.save_form_data(emp, "{}", commitment=0, signature=sig), "cam kết"))
			check("NV tick mà chưa ký → chặn", throws(lambda: api.save_form_data(emp, "{}", commitment=1, signature=""), "ký tên"))
		finally:
			frappe.set_user("Administrator")

		# ---- config: Select + Other ----
		fake = frappe.copy_doc(real_get())
		_set("_get_setting", lambda: fake)
		rows = {r.employee_fieldname: r for r in fake.selected_fields}
		meta = frappe.get_meta("Employee")
		data_fn = next((fn for fn in ("custom_favorite_sport", "custom_ethnicity") if fn in rows
			and (meta.get_field(fn) or {}).get("fieldtype") == "Data"), None)
		if data_fn:
			rows[data_fn].update({"enable": 1, "widget": api._SELECT_OTHER_WIDGET, "custom_options": "Bóng đá\n\n Cầu lông \n"})
			f = {x["fieldname"]: x for s in api._build_config()["sections"] for x in s["fields"]}[data_fn]
			check("Data + Select + Other → Select, options ['', …] từ Custom Options (bỏ dòng trống, strip)",
				f["fieldtype"] == "Select" and f["options"] == ["", "Bóng đá", "Cầu lông"] and f["allow_other"] is True, f)
			check("widget gửi trang = Auto (chuẩn hoá / Desk editor như field thường)", f["widget"] == "Auto")
			check("Desk editor = text (HR gõ tự do)", api._hr_editor(f) == "text")
		sel_fn = next((fn for fn in rows if fn != "custom_vegetarian"
			and (meta.get_field(fn) or {}).get("fieldtype") == "Select"), None)
		if sel_fn:
			rows[sel_fn].update({"enable": 1, "widget": api._SELECT_OTHER_WIDGET, "custom_options": "X"})
			f = {x["fieldname"]: x for s in api._build_config()["sections"] for x in s["fields"]}[sel_fn]
			check("field Select của Employee + Select + Other → bỏ qua widget (Sync chữ tự do vào Select sẽ lỗi)",
				f["allow_other"] is False and "X" not in f["options"] and f["widget"] == "Auto", f)
		veg = (meta.get_field("custom_vegetarian") or {}).get("fieldtype")
		check("Employee.custom_vegetarian là Data", veg == "Data", veg)
		vrow = rows.get("custom_vegetarian")
		check("Setting: ăn chay dùng Select + Other, có Custom Options",
			vrow and vrow.widget == api._SELECT_OTHER_WIDGET and (vrow.custom_options or "").strip(), vrow and vrow.as_dict())
		_set("_get_setting", real_get)

		# ---- Desk: HR sửa giá trị Khác ----
		names = frappe.get_all(DT, filters={"status": ["!=", "Synced"]}, pluck="name", limit=1)
		if names:
			cfg = real_cfg()
			key = "zz_select_other_test"
			fx = {"fieldname": key, "label": "Ăn chay", "fieldtype": "Select", "widget": "Auto", "allow_other": True,
				"options": ["", "Không"], "option_labels": {}, "required": False, "read_only": False, "validation": "",
				"min_length": 0, "max_length": 0}
			cfg["sections"] = cfg["sections"] + [{"label": "ZZ", "fields": [fx]}]
			_set("_build_config", lambda: cfg)
			d = frappe.get_doc(DT, names[0])
			d.load_doc_before_save()
			data = json.loads(d.data_json or "{}")
			data[key] = "  ăn chay   thứ 6 "
			d.data_json = json.dumps(data, ensure_ascii=False)
			ok = not _expect_throw(lambda: api.validate_desk_edit(d))
			check("Desk: giá trị ngoài danh sách → qua, chuẩn hoá như Data",
				ok and json.loads(d.data_json).get(key) == "Ăn chay thứ 6", json.loads(d.data_json).get(key))
	finally:
		_set("_get_setting", real_get)
		_set("_build_config", real_cfg)
		frappe.set_user("Administrator")
		frappe.db.rollback()

	fail = 0
	for ok, name, detail in results:
		if not ok:
			fail += 1
		print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if not ok else ''}")
	print(f"\n{len(results) - fail}/{len(results)} passed")
	return {"passed": len(results) - fail, "failed": fail}


def test_commitment_text():
	"""Câu cam kết lấy từ Setting.commitment_text (trống → câu mặc định). Không ghi DB.
	bench --site erp.tiqn.local execute customize_erpnext.api.self_update_info.test_self_update_sign.test_commitment_text"""
	results = []

	def check(name, ok, detail=""):
		results.append((bool(ok), name, detail))

	H = lambda v: api._commitment_html(frappe._dict(commitment_text=v))
	check("helper: Setting trống → mặc định", H("  \n") == api.COMMITMENT_TEXT)
	check("helper: giữ xuống dòng ở cuối", H("Tôi xin cam kết.\n\n") == "Tôi xin cam kết.<br><br>", H("Tôi xin cam kết.\n\n"))
	check("helper: xuống dòng → <br>", H("Dòng 1\r\nDòng 2\nDòng 3") == "Dòng 1<br>Dòng 2<br>Dòng 3", H("Dòng 1\r\nDòng 2\nDòng 3"))

	real_get = api._get_setting
	fake = frappe.copy_doc(real_get())
	fake.commitment_text = "Cam kết <b>thử</b> & đúng\nDòng hai"
	_set("_get_setting", lambda: fake)
	try:
		cfg = api.get_field_config()
		want = "Cam kết &lt;b&gt;thử&lt;/b&gt; &amp; đúng<br>Dòng hai"
		check("config: commitment_html lấy từ Setting, đã escape", cfg.get("commitment_html") == want, cfg.get("commitment_html"))
		name = frappe.db.get_value(DT, {"signature": ["like", api._SIGNATURE_PREFIX + "%"]}, "name")
		d = frappe.get_doc(DT, name)
		html = api._build_submission_html(d, json.loads(d.data_json or "{}"), cfg)
		check("phiếu: in câu của Setting, đã escape",
			want in html and api.COMMITMENT_TEXT not in html)
		d.signature, d.commitment_confirmed, d.signed_on = "", 0, None
		paper = api._build_submission_html(d, {}, cfg, sign_on_paper=True)
		check("phiếu ký tay: in câu của Setting", want in paper)
	finally:
		_set("_get_setting", real_get)
		frappe.db.rollback()
	check("trả lại _get_setting thật", api._get_setting is real_get)

	fail = 0
	for ok, name, detail in results:
		if not ok:
			fail += 1
		print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if not ok else ''}")
	print(f"\n{len(results) - fail}/{len(results)} passed")
	return {"passed": len(results) - fail, "failed": fail}


def test_auto_fill_fallback():
	"""Field "Auto Fill Data" phiếu chưa có giá trị (vd thêm vào Setting sau khi NV gửi) → PDF + Desk view
	lấy giá trị Employee. Không ghi DB.
	bench --site erp.tiqn.local execute customize_erpnext.api.self_update_info.test_self_update_sign.test_auto_fill_fallback"""
	from customize_erpnext.api.self_update_info import self_update_info_api as api

	results = []

	def check(name, ok, detail=""):
		results.append((bool(ok), name, detail))

	rec = frappe.db.sql(
		f"""select i.name, i.employee, e.gender, e.cell_number from `tab{api.INFO_DT}` i
		join tabEmployee e on e.name = i.employee
		where ifnull(e.gender, '') != '' and ifnull(e.cell_number, '') != '' limit 1""", as_dict=True)
	if not rec:
		check("có phiếu + Employee có giới tính/SĐT", False)
	else:
		r = rec[0]
		F = lambda fn, **kw: {"fieldname": fn, "label": fn, "fieldtype": "Data", "auto_fill": True, **kw}
		cfg = {"sections": [{"label": "A", "fields": [
			F("gender", fieldtype="Link"), F("cell_number"), F("blood_group", auto_fill=False),
			F("cus_x", custom=True),
		]}]}
		out = api._fill_from_employee(cfg, {"cell_number": "  "}, r.employee)
		check("thiếu khoá → lấy Employee", out.get("gender") == r.gender, out)
		check("chuỗi trắng → lấy Employee", out.get("cell_number") == r.cell_number, out)
		check("auto_fill=0 → không lấy", "blood_group" not in out, out)
		check("field custom → không lấy", "cus_x" not in out, out)
		out2 = api._fill_from_employee(cfg, {"gender": "X", "cell_number": "0900"}, r.employee)
		check("NV đã nhập → giữ giá trị NV", out2["gender"] == "X" and out2["cell_number"] == "0900", out2)
		src = {"a": 1}
		api._fill_from_employee(cfg, src, r.employee)
		check("không sửa dict gốc", src == {"a": 1})

		doc = frappe.get_doc(api.INFO_DT, r.name)
		real_cfg = api._build_config
		real_get = frappe.get_doc
		try:
			_set("_build_config", lambda: cfg)
			saved = json.loads(doc.data_json or "{}")
			doc.data_json = json.dumps({k: v for k, v in saved.items() if k != "gender"})
			frappe.get_doc = lambda dt, name=None, *a, **k: doc if (dt == api.INFO_DT and name == r.name) else real_get(dt, name, *a, **k)
			view = api.get_submission_view(r.name)
			g = next(x for s in view["sections"] for x in s["rows"] if x["fieldname"] == "gender")
			check("Desk view: hiện giới tính từ Employee, không đánh dấu đổi",
				g["display"] == r.gender and g["auto_filled"] and not g["changed"], g)
			html = api._hr_receipt_html(doc, cfg)
			check("PDF HR: có giới tính từ Employee (đầu phiếu)",
				f"<td class='mk'>gender:</td><td class='mv'>{frappe.utils.escape_html(r.gender)}</td>" in html, html[html.find("meta-t"):][:300])
		finally:
			_set("_build_config", real_cfg)
			frappe.get_doc = real_get
			frappe.db.rollback()

	fail = 0
	for ok, name, detail in results:
		if not ok:
			fail += 1
		print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if not ok else ''}")
	print(f"\n{len(results) - fail}/{len(results)} passed")
	return {"passed": len(results) - fail, "failed": fail}


def test_select_vi_labels():
	"""Select hiện tiếng Việt, lưu tiếng Anh (option_labels) + Gender (Link) thành dropdown. Không ghi DB.
	bench --site erp.tiqn.local execute customize_erpnext.api.self_update_info.test_self_update_sign.test_select_vi_labels"""
	from customize_erpnext.api.self_update_info import self_update_info_api as api

	results = []

	def check(name, ok, detail=""):
		results.append((bool(ok), name, detail))

	check("_option_labels: chỉ option có bản dịch khác",
		api._option_labels(["", "Married", "Divorced", "Ăn chay trường"]) == {"Married": "Đã kết hôn", "Divorced": "Đã ly hôn"},
		api._option_labels(["", "Married", "Divorced", "Ăn chay trường"]))
	# So với bản dịch vi hiện hành (không viết cứng chữ dịch — vi.po đổi "Góa" thì test vẫn đúng).
	ms4 = ["Single", "Married", "Divorced", "Widowed"]
	got4 = api._option_labels([""] + ms4)
	check("_option_labels: đủ 4 tình trạng hôn nhân, nhãn = bản dịch vi",
		set(got4) == set(ms4) and all(got4[o] == _(o, lang="vi") for o in ms4), got4)

	cfg = api._build_config()
	fields = {f["fieldname"]: f for s in cfg["sections"] for f in s["fields"]}
	ms = fields.get("marital_status")
	check("config: marital_status có option_labels", ms and ms["option_labels"].get("Married") == "Đã kết hôn", ms)
	g = fields.get("gender")
	check("config: gender (Link) → Select ['', Male, Female] + Nam/Nữ",
		g and g["fieldtype"] == "Select" and g["options"] == ["", "Male", "Female"]
		and g["option_labels"] == {"Male": "Nam", "Female": "Nữ"}, g)
	veg = fields.get("custom_vegetarian")
	check("config: Select vốn tiếng Việt → option_labels rỗng", veg is None or veg["option_labels"] == {}, veg)
	check("config: field không phải Select → option_labels rỗng/không có",
		all(not f.get("option_labels") for f in fields.values() if f["fieldtype"] not in ("Select", "Table")))
	check("_hr_editor: gender sửa được bằng dropdown trên Desk", g and api._hr_editor(g) == "select")
	check("Desk validate: Select chỉ nhận giá trị gốc", g and "Nữ" not in g["options"] and "Female" in g["options"])

	names = frappe.get_all(api.INFO_DT, pluck="name", limit=1)
	if names:
		doc = frappe.get_doc(api.INFO_DT, names[0])
		c2 = {"sections": [{"label": "A", "fields": [
			dict(ms, label="TTHN"), dict(g, label="GT"),
		]}]}
		h = api._build_submission_html(doc, {"marital_status": "Married", "gender": "Female"}, c2)
		check("phiếu PDF: in nhãn tiếng Việt", "<td class='val'>Đã kết hôn</td>" in h and "<td class='val'>Nữ</td>" in h)
		h2 = api._build_submission_html(doc, {"marital_status": "Lạ"}, c2)
		check("phiếu PDF: giá trị ngoài danh sách in nguyên", "<td class='val'>Lạ</td>" in h2)
	check("Info for Sign: gender dịch Nữ", api._sign_value_vi({"fieldtype": "Select"}, "Female") == "Nữ")

	fail = 0
	for ok, name, detail in results:
		if not ok:
			fail += 1
		print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if not ok else ''}")
	print(f"\n{len(results) - fail}/{len(results)} passed")
	return {"passed": len(results) - fail, "failed": fail}


def test_shoe_sport_license():
	"""Size dép (Select + Option Labels), Môn thể thao / Sở trường, GPLX + tình trạng (chỉ hiện khi "Chưa").
	Lưu thử trong transaction rồi rollback — không ghi DB.
	bench --site erp.tiqn.local execute customize_erpnext.api.self_update_info.test_self_update_sign.test_shoe_sport_license"""
	from customize_erpnext.api.self_update_info import self_update_info_api as api

	results = []

	def check(name, ok, detail=""):
		results.append((bool(ok), name, detail))

	meta = frappe.get_meta("Employee")
	check("Employee: custom_shoe_size là Select 2-3…10-11",
		meta.get_field("custom_shoe_size").fieldtype == "Select"
		and meta.get_field("custom_shoe_size").options.split("\n") == ["", "2-3", "4-5", "6-7", "8-9", "10-11"])
	check("Employee: GPLX Có/Chưa/Mất", meta.get_field("custom_driving_license").options.split("\n") == ["", "Có", "Chưa", "Mất"])
	st = meta.get_field("custom_driving_license_status")
	check("Employee: tình trạng GPLX + depends_on Chưa",
		st and st.options.split("\n")[1:] == ["Chưa đăng ký", "Đang đợi ngày thi", "Đang đợi cấp", "Đã thi nhưng chưa đạt"]
		and st.depends_on == "eval:doc.custom_driving_license=='Chưa'")
	check("Employee: Môn thể thao / Sở trường",
		meta.get_field("custom_favorite_sport") and meta.get_field("custom_strengths"))
	check("dữ liệu cũ: không còn GPLX 'Không' / size dép '39'",
		not frappe.db.count("Employee", {"custom_driving_license": "Không"}) and not frappe.db.count("Employee", {"custom_shoe_size": "39"}))

	ol = api._option_labels(["", "6-7", "8-9"], "6-7 | Size 6-7 · dép thường 38-39\n9-9 | lạ\nkhông có gạch\n8-9 |  ")
	check("_option_labels: override theo dòng, bỏ giá trị lạ / nhãn trống", ol == {"6-7": "Size 6-7 · dép thường 38-39"}, ol)
	check("_option_labels: override thắng bản dịch", api._option_labels(["Married"], "Married | Có gia đình") == {"Married": "Có gia đình"})

	cfg = api._build_config()
	F = {f["fieldname"]: f for s in cfg["sections"] for f in s["fields"]}
	shoe = F.get("custom_shoe_size")
	check("config: size dép Select + nhãn 3 thông tin",
		shoe and shoe["fieldtype"] == "Select" and shoe["option_labels"].get("6-7") == "Size 6-7 · dép thường 38-39 · chân 24.5-25 cm", shoe)
	check("config: 'Size dép - Thường mang' đã tắt", "size_shoe_home" not in F)
	check("config: có Môn thể thao / Sở trường, tick Info for Sign",
		all(F.get(x) and F[x]["info_for_sign"] for x in ("custom_favorite_sport", "custom_strengths")))
	stf = F.get("custom_driving_license_status")
	check("config: tình trạng GPLX depends_on GPLX = Chưa",
		stf and stf["depends_on"] == {"field": "custom_driving_license", "values": ["Chưa"]}, stf)
	check("config: field không có trong _FIELD_DEPENDS thì không có depends_on",
		not any(f.get("depends_on") for fn, f in F.items() if fn != "custom_driving_license_status"))

	# _apply_depends
	lic_cfg = {"sections": [{"label": "A", "fields": [
		{"fieldname": "custom_driving_license", "label": "GPLX", "fieldtype": "Select", "options": ["", "Có", "Chưa", "Mất"],
		 "required": False, "read_only": False},
		{"fieldname": "custom_driving_license_status", "label": "Tình trạng GPLX", "fieldtype": "Select",
		 "options": ["", "Đang đợi cấp"], "required": False, "read_only": False,
		 "depends_on": {"field": "custom_driving_license", "values": ["Chưa"]}},
	]}]}
	v = {"custom_driving_license": "Có", "custom_driving_license_status": "Đang đợi cấp"}
	vis = api._apply_depends(lic_cfg, v, None)
	check("depends: GPLX Có → ẩn + xoá tình trạng", vis == {"custom_driving_license_status": False} and v["custom_driving_license_status"] == "")
	v = {"custom_driving_license": "Chưa", "custom_driving_license_status": "Đang đợi cấp"}
	check("depends: GPLX Chưa → hiện, giữ giá trị", api._apply_depends(lic_cfg, v, None) == {"custom_driving_license_status": True}
		and v["custom_driving_license_status"] == "Đang đợi cấp")

	# PDF / Info for Sign: gộp GPLX 1 dòng, size dép in gọn
	names = frappe.get_all(api.INFO_DT, pluck="name", limit=1)
	if names:
		doc = frappe.get_doc(api.INFO_DT, names[0])
		c2 = {"sections": [{"label": "A", "fields": lic_cfg["sections"][0]["fields"] + [dict(shoe, label="Size dép")]}]}
		h = api._build_submission_html(doc, {"custom_driving_license": "Chưa", "custom_driving_license_status": "Đang đợi cấp",
			"custom_shoe_size": "6-7"}, c2, compact=True)
		check("PDF HR: 'Giấy phép lái xe: Chưa (Đang đợi cấp)'",
			"<td class='lbl'>Giấy phép lái xe</td><td class='val'>Chưa (Đang đợi cấp)</td>" in h, h[-1500:])
		check("PDF: size dép in gọn 6-7", "<td class='val'>6-7</td>" in h)
		h2 = api._build_submission_html(doc, {"custom_driving_license": "Có", "custom_driving_license_status": ""}, c2, compact=True)
		check("PDF HR: GPLX Có → không có ngoặc", "<td class='val'>Có</td>" in h2)
	check("Info for Sign: _sign_join license", api._sign_join("license", [({"fieldname": "custom_driving_license"}, "Chưa"),
		({"fieldname": "custom_driving_license_status"}, "Đang đợi ngày thi")]) == "Chưa (Đang đợi ngày thi)")

	# save_form_data thật (HR, cổng kiểm mã tắt). ⚠ save_form_data tự frappe.db.commit() → rollback KHÔNG cứu:
	# chỉ dùng NV CHƯA có phiếu, chặn commit trong lúc test, cuối cùng rollback (sự cố 16/10: ghi đè phiếu TIQN-2548).
	emp = frappe.db.sql(f"""select e.name from tabEmployee e where e.status = 'Active'
		and not exists (select 1 from `tab{api.INFO_DT}` i where i.name = e.name) limit 1""")[0][0]
	real_cfg, real_gate, real_commit = api._build_config, api._gate_edit, frappe.db.commit
	try:
		_set("_build_config", lambda: lic_cfg)
		_set("_gate_edit", lambda *a, **k: None)
		frappe.db.commit = lambda *a, **k: None
		check("save: GPLX Chưa + thiếu tình trạng → chặn",
			_expect_throw(lambda: api.save_form_data(emp, json.dumps({"custom_driving_license": "Chưa"}))))
		api.save_form_data(emp, json.dumps({"custom_driving_license": "Có", "custom_driving_license_status": "Đang đợi cấp"}))
		saved = json.loads(frappe.db.get_value(api.INFO_DT, emp, "data_json"))
		check("save: GPLX Có → tình trạng bị xoá trắng", saved.get("custom_driving_license_status") == "", saved)
		api.save_form_data(emp, json.dumps({"custom_driving_license": "Chưa", "custom_driving_license_status": "Đang đợi cấp"}))
		saved = json.loads(frappe.db.get_value(api.INFO_DT, emp, "data_json"))
		check("save: GPLX Chưa + tình trạng → lưu đủ", saved.get("custom_driving_license_status") == "Đang đợi cấp", saved)
		check("save: tình trạng ngoài danh sách → chặn",
			_expect_throw(lambda: api.save_form_data(emp, json.dumps({"custom_driving_license": "Chưa", "custom_driving_license_status": "Lạ"}))))
	finally:
		_set("_build_config", real_cfg)
		_set("_gate_edit", real_gate)
		frappe.db.commit = real_commit
		frappe.db.rollback()
	check("save: không để lại phiếu sau test", not frappe.db.exists(api.INFO_DT, emp), emp)

	fail = 0
	for ok, name, detail in results:
		if not ok:
			fail += 1
		print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if not ok else ''}")
	print(f"\n{len(results) - fail}/{len(results)} passed")
	return {"passed": len(results) - fail, "failed": fail}


def run_all():
	"""Chạy mọi bộ test của module (Python), in bảng tổng cuối cùng. Trả {suite: (passed, failed)}."""
	suites = [run] + [
		obj for name, obj in sorted(globals().items())
		if name.startswith("test_") and callable(obj)
	]
	summary = {}
	for fn in suites:
		print(f"\n===== {fn.__name__}")
		try:
			r = fn() or {}
			summary[fn.__name__] = (r.get("passed", 0), r.get("failed", 0))
		except Exception as e:
			frappe.db.rollback()
			summary[fn.__name__] = (0, 1)
			print(f"ERROR  {fn.__name__}: {e!r}")
	print("\n===== TỔNG")
	for name, (p, f) in summary.items():
		print(f"{'OK  ' if not f else 'FAIL'}  {name}: {p}/{p + f}")
	total_p = sum(p for p, _f in summary.values())
	total_f = sum(f for _p, f in summary.values())
	print(f"\n{total_p}/{total_p + total_f} passed")
	return {"passed": total_p, "failed": total_f}
