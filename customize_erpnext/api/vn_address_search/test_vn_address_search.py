# -*- coding: utf-8 -*-
"""Kiểm tra READ-ONLY cho vn_address_search_api — không ghi DB, không save Employee.

    bench --site erp.tiqn.local execute \
        customize_erpnext.api.vn_address_search.test_vn_address_search.run
"""

import frappe

from customize_erpnext.api.vn_address_search import vn_address_search_api as api

QN = "Tỉnh Quảng Ngãi"


def run():
	results = []

	def check(name, ok, detail=""):
		results.append((ok, name, detail))

	provinces = api.get_province_options()
	check("34 tỉnh", len(provinces) == 34, len(provinces))
	check("option có value/label/code", set(provinces[0]) == {"value", "label", "code"}, provinces[0])

	qn_by_name = api.get_ward_options(QN)
	qn_by_code = api.get_ward_options("51")
	check("tra xã theo tên = theo mã", qn_by_name == qn_by_code, len(qn_by_name))
	names = {w["value"] for w in qn_by_name}
	check("Ba Tơ và Ba Tô là 2 xã riêng", {"Xã Ba Tơ", "Xã Ba Tô"} <= names)
	check("Sơn Hà và Sơn Hạ là 2 xã riêng", {"Xã Sơn Hà", "Xã Sơn Hạ"} <= names)

	max_wards = max(len(api.get_ward_options(p["code"])) for p in provinces)
	check("tỉnh nhiều xã nhất ≤ 200 (maxItems JS)", max_wards <= 200, max_wards)
	total = sum(len(api.get_ward_options(p["code"])) for p in provinces)
	check("tổng 3.321 xã", total == 3321, total)

	check("tỉnh không dấu bị từ chối", api._province_code("Tinh Quang Ngai") is None)
	check("tỉnh sai → []", api.get_ward_options("Tỉnh Không Có") == [])

	err = api.get_address_error
	check("hợp lệ", err(QN, "Xã Ba Tơ") is None)
	check("trống cả hai", err("", "") is None)
	check("chỉ có tỉnh", err(QN, "") is None)
	check("xã không tỉnh", err("", "Xã Ba Tơ") is not None)
	check("tỉnh cũ trước sáp nhập", err("Tỉnh Quảng Nam", "") is not None)
	check("xã sai dấu (Ba To)", err(QN, "Xã Ba To") is not None)
	check("xã thuộc tỉnh khác", err("Thành phố Hà Nội", "Xã Ba Tơ") is not None)
	check("check_address API", api.check_address(QN, "Xã Ba Tô")["valid"])

	# Employee: chỉ sửa trong bộ nhớ, KHÔNG save.
	emp_name = frappe.db.get_value(
		"Employee",
		{"custom_current_address_province": QN, "custom_current_address_commune": ["!=", ""]},
		"name",
	)
	doc = frappe.get_doc("Employee", emp_name)
	doc.load_doc_before_save()
	try:
		api.validate_employee_address(doc)
		check("Employee không đổi địa chỉ → qua", True, emp_name)
	except frappe.ValidationError as e:
		check("Employee không đổi địa chỉ → qua", False, str(e))

	doc.custom_current_address_commune = "Xã Không Có"
	try:
		api.validate_employee_address(doc)
		check("Employee đổi sang xã sai → chặn", False)
	except frappe.ValidationError:
		check("Employee đổi sang xã sai → chặn", True)
	frappe.clear_messages()

	old = frappe.db.get_value(
		"Employee", {"custom_current_address_province": "Tỉnh Quảng Nam"}, "name"
	)
	if old:
		doc = frappe.get_doc("Employee", old)
		doc.load_doc_before_save()
		doc.custom_current_address_village = (doc.custom_current_address_village or "") + " "
		try:
			api.validate_employee_address(doc)
			check("hồ sơ tỉnh cũ, sửa field khác → qua", True, old)
		except frappe.ValidationError as e:
			check("hồ sơ tỉnh cũ, sửa field khác → qua", False, str(e))

	frappe.db.rollback()

	failed = [r for r in results if not r[0]]
	for ok, name, detail in results:
		print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if detail != '' else ''}")
	print(f"\n{len(results) - len(failed)}/{len(results)} passed")
	return {"passed": len(results) - len(failed), "failed": len(failed)}


def verify_deploy():
	"""READ-ONLY: hook đã đăng ký, form JS có helper trước employee.js, 4 field là Autocomplete.

	bench --site erp.tiqn.local execute \
		customize_erpnext.api.vn_address_search.test_vn_address_search.verify_deploy
	"""
	from frappe.desk.form.meta import get_meta as get_form_meta

	hook = "customize_erpnext.api.vn_address_search.vn_address_search_api.validate_employee_address"
	js = get_form_meta("Employee").get("__js") or ""
	a = js.find('frappe.provide("customize_erpnext.vn_address")')
	b = js.find("function load_province_options")
	fields = {
		df.fieldname: (df.fieldtype, df.read_only_depends_on or "")
		for df in frappe.get_meta("Employee").fields
		if df.fieldname.endswith(("address_province", "address_commune", "address_village", "to_other_adress"))
	}
	out = {
		"hook_registered": hook in frappe.get_hooks("doc_events")["Employee"]["validate"],
		"helper_in_form_js": a >= 0,
		"helper_before_employee_js": 0 <= a < b,
		"fields": fields,
	}
	print(out)
	return out
