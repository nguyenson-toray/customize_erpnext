"""Soát toàn vẹn sau upgrade / dọn dẹp — CHỈ ĐỌC. Bắt các lỗi "gãy im lặng".

Chạy:
    cd ~/frappe-bench/sites && ../env/bin/python -c "
    import frappe; frappe.init(site='erp.tiqn.local'); frappe.connect(); frappe.set_user('Administrator')
    exec(open('../apps/customize_erpnext/customize_erpnext/scripts/check_integrity.py').read())"

Vì sao cần: nhiều lỗi sau upgrade KHÔNG ném lỗi ra ngoài —
- 1 link DocType chết trong Workspace = mất sạch card của workspace đó (`handle_not_exist` nuốt lỗi);
- import lỗi trong overrides/__init__ chỉ ghi Error Log, override không chạy;
- hàm trong hooks không resolve được chỉ lỗi khi tới giờ chạy;
- `get_single_value` field đã bị upstream xoá: frappe v16.50+ NÉM lỗi (trước trả None).
"""

import os

import frappe

issues = []


def issue(kind, msg):
	issues.append((kind, msg))


APP = "customize_erpnext"
modules = frappe.get_all("Module Def", filters={"app_name": APP}, pluck="name")
exists = lambda dt, name: bool(name) and bool(frappe.db.exists(dt, name))

# 1. Controller của mọi DocType trong app
for dt in frappe.get_all("DocType", filters={"module": ["in", modules]}, pluck="name"):
	try:
		frappe.get_meta(dt)
		frappe.get_doc({"doctype": dt})
	except Exception as e:
		issue("doctype", f"{dt}: {type(e).__name__}: {e}")

# 2. Report: module Python import được, ref_doctype còn
for r in frappe.get_all("Report", filters={"module": ["in", modules]}, fields=["name", "report_type", "ref_doctype", "is_standard"]):
	if r.ref_doctype and not exists("DocType", r.ref_doctype):
		issue("report", f"{r.name}: ref_doctype {r.ref_doctype} không còn")
	if r.report_type == "Script Report" and r.is_standard == "Yes":
		try:
			mod = frappe.scrub(frappe.db.get_value("Report", r.name, "module"))
			frappe.get_attr(f"{frappe.local.module_app[mod]}.{mod}.report.{frappe.scrub(r.name)}.{frappe.scrub(r.name)}.execute")
		except Exception as e:
			issue("report", f"{r.name}: {type(e).__name__}: {e}")

# 3. Page nạp được
from frappe.desk.desk_page import get as get_page
for p in frappe.get_all("Page", filters={"module": ["in", modules]}, pluck="name"):
	try:
		get_page(p)
	except Exception as e:
		issue("page", f"{p}: {type(e).__name__}: {e}")

# 4. Link chết trong MỌI Workspace (link DocType chết làm mất sạch card)
for wl in frappe.get_all("Workspace Link", filters={"type": "Link", "parenttype": "Workspace"}, fields=["parent", "link_type", "link_to"]):
	if wl.link_type in ("DocType", "Report", "Page") and wl.link_to and not exists(wl.link_type, wl.link_to):
		issue("workspace", f"{wl.parent}: link {wl.link_type} '{wl.link_to}' không còn")
for ws in frappe.get_all("Workspace Shortcut", filters={"parenttype": "Workspace"}, fields=["parent", "type", "link_to"]):
	if ws.type in ("DocType", "Report", "Page", "Dashboard") and ws.link_to and not exists(ws.type, ws.link_to):
		issue("workspace", f"{ws.parent}: shortcut {ws.type} '{ws.link_to}' không còn")

# 5. Link chết trong Sidebar (app) + Custom Sidebar (lớp site/user)
for parenttype in ("Sidebar", "Custom Sidebar"):
	for it in frappe.get_all("Sidebar Item", filters={"parenttype": parenttype, "type": "Link"},
							 fields=["parent", "label", "link_type", "link_to", "url"]):
		if it.link_type in ("DocType", "Report", "Page", "Workspace", "Dashboard"):
			if not exists(it.link_type, it.link_to):
				issue("sidebar", f"{parenttype} {it.parent}: '{it.label}' → {it.link_type} '{it.link_to}' không còn")
		elif it.link_type == "URL" and not it.url:
			issue("sidebar", f"{parenttype} {it.parent}: '{it.label}' là URL nhưng url rỗng")

# 6. Custom Field / Property Setter trỏ vào DocType hoặc field không còn
for cf in frappe.get_all("Custom Field", fields=["name", "dt", "fieldtype", "options", "insert_after"]):
	if not exists("DocType", cf.dt):
		issue("custom_field", f"{cf.name}: DocType {cf.dt} không còn")
	elif cf.fieldtype in ("Link", "Table", "Table MultiSelect") and cf.options and not exists("DocType", cf.options):
		issue("custom_field", f"{cf.name}: options {cf.options} không còn")
for ps in frappe.get_all("Property Setter", fields=["name", "doc_type", "field_name", "property"]):
	if not exists("DocType", ps.doc_type):
		issue("property_setter", f"{ps.name}: DocType {ps.doc_type} không còn")
	elif ps.field_name and not frappe.get_meta(ps.doc_type).has_field(ps.field_name) and ps.property not in ("in_list_view",):
		issue("property_setter", f"{ps.name}: field {ps.doc_type}.{ps.field_name} không còn")

# 7. hooks: mọi method resolve được, mọi file JS tồn tại
hooks = frappe.get_hooks(app_name=APP)
app_path = frappe.get_app_path(APP)


def check_method(where, path):
	try:
		frappe.get_attr(path)
	except Exception as e:
		issue("hooks", f"{where}: {path} → {type(e).__name__}: {e}")


for doctype, events in (hooks.get("doc_events") or {}).items():
	if doctype != "*" and not exists("DocType", doctype) and not isinstance(doctype, tuple):
		issue("hooks", f"doc_events: DocType {doctype} không còn")
	for ev, methods in events.items():
		for m in (methods if isinstance(methods, list) else [methods]):
			check_method(f"doc_events {doctype}.{ev}", m)
for kind, jobs in (hooks.get("scheduler_events") or {}).items():
	items = jobs.items() if isinstance(jobs, dict) else [(kind, jobs)]
	for key, methods in items:
		for m in methods:
			check_method(f"scheduler {kind} {key}", m)
for k in ("override_whitelisted_methods",):
	for src, dst in (hooks.get(k) or {}).items():
		check_method(k, dst[-1] if isinstance(dst, list) else dst)
for dt, cls in (hooks.get("override_doctype_class") or {}).items():
	check_method(f"override_doctype_class {dt}", cls[-1] if isinstance(cls, list) else cls)
for key in ("doctype_js", "doctype_list_js", "doctype_tree_js"):
	for dt, files in (hooks.get(key) or {}).items():
		if not exists("DocType", dt):
			issue("hooks", f"{key}: DocType {dt} không còn")
		for f in (files if isinstance(files, list) else [files]):
			if not os.path.exists(os.path.join(app_path, f)):
				issue("hooks", f"{key} {dt}: file {f} không có")
for f in hooks.get("app_include_js") or []:
	if f.startswith("/assets/"):
		p = os.path.join(app_path, "public", f.split("/assets/customize_erpnext/", 1)[-1])
		if not os.path.exists(p):
			issue("hooks", f"app_include_js: {f} không có")
	elif not os.path.exists(os.path.join(app_path, "public", "js", f)):
		issue("hooks", f"app_include_js bundle: {f} không có")

# 8. Override nạp đủ
import customize_erpnext.overrides as ov
if ov.failed:
	issue("overrides", f"module override lỗi: {ov.failed}")

# 9. Client/Server Script trong DB trỏ vào DocType không còn
for cs in frappe.get_all("Client Script", filters={"enabled": 1}, fields=["name", "dt"]):
	if not exists("DocType", cs.dt):
		issue("client_script", f"{cs.name}: DocType {cs.dt} không còn")
for ss in frappe.get_all("Server Script", filters={"disabled": 0}, fields=["name", "reference_doctype"]):
	if ss.reference_doctype and not exists("DocType", ss.reference_doctype):
		issue("server_script", f"{ss.name}: DocType {ss.reference_doctype} không còn")

# 10. Print Format / Notification của DocType không còn
for pf in frappe.get_all("Print Format", fields=["name", "doc_type"]):
	if pf.doc_type and not exists("DocType", pf.doc_type):
		issue("print_format", f"{pf.name}: DocType {pf.doc_type} không còn")
for n in frappe.get_all("Notification", fields=["name", "document_type", "enabled"]):
	if n.document_type and not exists("DocType", n.document_type):
		issue("notification", f"{n.name}: DocType {n.document_type} không còn")

frappe.db.rollback()
print(f"\n{'=' * 60}\n{len(issues)} vấn đề")
for kind, msg in sorted(issues):
	print(f"  [{kind}] {msg}")
