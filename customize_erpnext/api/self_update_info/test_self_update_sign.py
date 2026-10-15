# -*- coding: utf-8 -*-
"""Kiểm tra chữ ký / cam kết / sửa trên Desk / Excel "Info for Sign" — KHÔNG ghi DB.

Chỉ sửa doc trong bộ nhớ, gọi hàm thuần, cuối cùng rollback. Không gọi đường nào có commit
(save_form_data chỉ được gọi ở nhánh throw trước khi lưu).

    bench --site erp.tiqn.local execute \
        customize_erpnext.api.self_update_info.test_self_update_sign.run
"""

import io
import json

import frappe

from customize_erpnext.api.self_update_info import self_update_info_api as api

DT = "Employee Self Update Info"


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
	api._build_config = fake_build
	try:
		check("flag: chưa tick → dialog rỗng", api.get_info_for_sign_fields() == [])
		check("flag: chưa tick → xuất báo lỗi", _expect_throw(lambda: api._download_info_for_sign("[]")))
		flagged["value"] = None
		fl = api.get_info_for_sign_fields()
		check("dialog: liệt kê dòng gộp (địa chỉ/khẩn cấp)", "Liên hệ khẩn cấp" in fl and "Địa chỉ hiện tại" in fl, fl)
	finally:
		api._build_config = real_build

	# ---------- Info for Sign ----------
	recs = frappe.get_all(DT, filters={"status": "Submitted"}, fields=["name", "data_json"], limit=3, order_by="name")
	names = [r.name for r in recs]

	api._build_config = fake_build  # tick tất cả cho các kiểm tra layout bên dưới
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
	api._build_config = real_build

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
		other = [r for sec in view["sections"] for r in sec["rows"] if r not in drows]
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
	check("receipt: có câu cam kết + ảnh chữ ký", api.COMMITMENT_TEXT in html and "class='sig'" in html)
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

	cfg = api.get_field_config()
	check("config: có commitment_text", bool(cfg.get("commitment_text")))
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

	api._info_for_sign_pdf_html = spy_html
	try:
		all_names = sorted(frappe.get_all(DT, pluck="name", order_by="employee asc", limit=24))
		rows_real = len(api._sign_items(real_build(), api._info_for_sign_wanted(real_build())))
		F, P = api.INFO_FOR_SIGN_PDF_FIRST, api.INFO_FOR_SIGN_PDF_PER_PAGE
		results.append(((F, P) == (4, 5), "bố cục mặc định: trang 1 = 4 NV, sau = 5 NV", (F, P)))
		if rows_real:
			for n in (4, 9, 14, 24):
				pdf, texts, codes = export(all_names[:n])
				exp = 1 + math.ceil(max(0, n - F) / P)
				fonts_ok = sorted({f for f, lay in tried if lay[0] == min(F, n)})
				results.append((len(pdf.pages) == exp and codes[0] == min(F, n) and all(c == P for c in codes[1:-1]),
					f"A) thật ({rows_real} dòng/NV) {n} NV → {exp} trang, 4/5 NV mỗi trang", (codes, fonts_ok)))
				results.append((all(f"Trang {i + 1}/{exp}" in t for i, t in enumerate(texts)), f"A) {n} NV: 'Trang x/{exp}'", ""))
				results.append(("DANH SÁCH XÁC NHẬN" in texts[0] and all("Thông tin" in t and "Chữ ký" in t for t in texts),
					f"A) {n} NV: tiêu đề trang 1 + tên cột mọi trang", ""))
				box = pdf.pages[0].mediabox
				results.append((float(box.width) > float(box.height), f"A) {n} NV: A4 ngang", ""))
		else:
			results.append((True, "A) bỏ qua — Setting chưa tick Info for Sign", ""))

		api._build_config = fake_all
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
		api._build_config = real_build
		api._info_for_sign_pdf_html = real_html
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
	PN = {**D, "validation": "Person Name"}
	cases = [
		(D, "  duong   minh thang ", "Duong minh thang", "gộp khoảng trắng + hoa ký tự đầu"),
		(D, "thôn 3, xóm đông", "Thôn 3, xóm đông", "chỉ hoa ký tự đầu của cả ô"),
		(D, "Xóm1,thôn", "Xóm 1,thôn", "chèn dấu cách chữ–số"),
		(D, "B2", "B2", "giữ mã B2"), (D, "TDP1", "TDP1", "giữ viết tắt TDP1"), (D, "ABC123", "ABC123", "giữ mã ABC123"),
		(D, "khu A1", "Khu A1", "giữ A1"),
		(PN, "ĐOÀN THANH PHI", "Đoàn Thanh Phi", "Person Name: viết hoa toàn bộ → Hoa Đầu Mỗi Từ"),
		(PN, " duong  minh thang", "Duong Minh Thang", "Person Name: thường → Hoa Đầu Mỗi Từ"),
		({**D, "validation": "Email"}, " Abc@Gmail.com ", "Abc@Gmail.com", "Email: chỉ bỏ khoảng trắng"),
		({"fieldtype": "Small Text", "widget": "Auto"}, "dòng 1  \n  dòng   2", "Dòng 1\ndòng 2", "Small Text giữ xuống dòng"),
		({"fieldtype": "Select", "widget": "Auto"}, "male", "male", "Select không đụng"),
		({**D, "widget": "Address Province"}, "tỉnh x", "tỉnh x", "widget địa chỉ không đụng"),
		(D, "Hoà", "Hoà", "NFC (dấu tách rời → dựng sẵn)"),
		(D, " abc.def@gmail.com ", "abc.def@gmail.com", "giá trị trông như email (chưa gán Validation) → không viết hoa"),
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
	results.append(("Person Name" in frappe.get_meta("Employee Self Update Info Field").get_field("validation").options,
		"Setting: có lựa chọn Validation 'Person Name'", ""))
	frappe.db.rollback()
	for ok, nm, detail in results:
		print(f"{'PASS' if ok else 'FAIL'}  {nm}  {detail}")
	fail = sum(1 for r in results if not r[0])
	print(f"\n{len(results) - fail}/{len(results)} passed")
	return {"passed": len(results) - fail, "failed": fail}
