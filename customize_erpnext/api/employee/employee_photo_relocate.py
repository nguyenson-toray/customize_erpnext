"""Ảnh NV đổi từ form Employee (sidebar / ô Image / Data Import...) → chuyển vào employee_photos.

Ô Attach Image upload file vào /private/files (mặc định của FileUploader) rồi save Employee. Hook
`on_update` này chép NGUYÊN file sang `public/files/employee_photos/{mã} {tên}.{ext}` — cùng chỗ và
cùng cách đặt tên với trang /employee-photos — trỏ File record + Employee.image sang đó, sinh thumb,
rồi SAU KHI COMMIT mới xoá file nguồn và ảnh cũ của chính NV (chỉ khi không còn ai tham chiếu).

Không xoá theo mã NV (glob) — chỉ đúng file cũ của Employee này. Trang /employee-photos lưu bằng
`frappe.db.set_value` (không qua on_update) nên không đi qua đây.
"""
import os
import re
import shutil
from functools import partial

import frappe

EP_PREFIX = "/files/employee_photos/"


def _disk(url):
	if not url:
		return None
	url = url.split("?")[0]
	if url.startswith("/private/files/"):
		return frappe.get_site_path(url.lstrip("/"))
	if url.startswith("/files/"):
		return frappe.get_site_path("public", url.lstrip("/"))
	return None


def _md5(path):
	import hashlib

	with open(path, "rb") as f:
		return hashlib.md5(f.read()).hexdigest()


def _clean_name(name):
	name = re.sub(r'[<>:"/\\|?*]', "", name or "employee")
	return " ".join(name.split())


def target_url(doc, src_url):
	ext = os.path.splitext(src_url.split("?")[0])[1].lower() or ".jpg"
	return f"{EP_PREFIX}{doc.name} {_clean_name(doc.employee_name)}{ext}"


def _referenced(url, ignore_employee=None):
	"""File/URL còn được dùng ở nơi khác: Employee.image, User.user_image, File record."""
	if frappe.db.exists("Employee", {"image": url, "name": ["!=", ignore_employee or ""]}):
		return True
	if frappe.db.exists("User", {"user_image": url}):
		return True
	return bool(frappe.db.exists("File", {"file_url": url}))


def delete_unreferenced_photos(urls, employee):
	from customize_erpnext.api.employee.employee_photo_thumbs import remove_thumb

	for url in urls:
		try:
			if not url or _referenced(url, ignore_employee=employee):
				continue
			path = _disk(url)
			if path and os.path.exists(path):
				os.remove(path)
			if url.startswith(EP_PREFIX):
				remove_thumb(url)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Employee photo cleanup failed: {url}")


def relocate_employee_image(doc, method=None):
	src_url = (doc.image or "").split("?")[0]
	if not src_url or src_url.startswith(EP_PREFIX) or not src_url.startswith(("/files/", "/private/files/")):
		return
	if not doc.has_value_changed("image"):
		return
	src = _disk(src_url)
	if not src or not os.path.exists(src):
		return

	new_url = target_url(doc, src_url)
	dst = _disk(new_url)
	os.makedirs(os.path.dirname(dst), exist_ok=True)
	shutil.copy2(src, dst)

	before = doc.get_doc_before_save()
	old_url = (before.image or "").split("?")[0] if before else ""

	# File record của ô ảnh: trỏ sang ảnh mới; ảnh cũ / record trùng của chính NV thì bỏ
	recs = frappe.get_all(
		"File",
		filters={"attached_to_doctype": "Employee", "attached_to_name": doc.name, "attached_to_field": "image"},
		fields=["name", "file_url"],
		order_by="creation desc",
	)
	keep = next((r.name for r in recs if r.file_url == src_url), None) or next(
		(r.name for r in recs if r.file_url == new_url), None
	)
	if keep:
		frappe.db.set_value(
			"File", keep,
			{"file_url": new_url, "file_name": os.path.basename(new_url), "is_private": 0,
				"file_size": os.path.getsize(dst), "content_hash": _md5(dst)},
			update_modified=False,
		)
	else:
		f = frappe.get_doc({
			"doctype": "File", "file_name": os.path.basename(new_url), "file_url": new_url, "is_private": 0,
			"folder": "Home/Attachments", "attached_to_doctype": "Employee", "attached_to_name": doc.name,
			"attached_to_field": "image", "file_size": os.path.getsize(dst),
		})
		f.flags.copy_from_existing_file = True  # file đã nằm trên đĩa; không để before_insert ghi lại ra /files/
		f.insert(ignore_permissions=True)
		keep = f.name
	stale = [r.name for r in recs if r.name != keep]
	if stale:
		frappe.db.delete("File", {"name": ["in", stale]})

	doc.db_set("image", new_url, update_modified=False)

	from customize_erpnext.api.employee.employee_photo_thumbs import make_thumb

	make_thumb(new_url)

	to_delete = [src_url]
	if old_url and old_url not in (new_url, src_url):
		to_delete.append(old_url)
	frappe.db.after_commit.add(partial(delete_unreferenced_photos, to_delete, doc.name))
