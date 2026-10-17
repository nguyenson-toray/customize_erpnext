"""Tải hàng loạt ảnh nhân viên thành 1 file ZIP (Employee list → menu "9 Bulk Download Employee Photos").

Luồng: client gọi `preview_employee_photos` (frappe.call) để biết bao nhiêu ảnh tải được
và ai thiếu ảnh, rồi mới `open_url_post` tới `download_employee_photos`. Bước preview là
bắt buộc: open_url_post submit form ngay trên trang hiện tại, nếu server throw thì người
dùng bị đưa sang trang JSON lỗi — nên mọi trường hợp "không có gì để tải" phải chặn ở preview.

Quyền: đọc Employee qua frappe.get_list → áp đủ role + User Permission. Ảnh private
(/private/files/...) cũng trả về nếu người dùng đọc được hồ sơ Employee đó.
"""

import io
import os
import re
import unicodedata
import zipfile
from urllib.parse import unquote

import frappe
from frappe import _
from frappe.utils import now_datetime

MAX_EMPLOYEES = 3000
NAME_FORMATS = ("id_name", "id", "id_name_ascii")


def _parse_ids(employee_ids):
	ids = frappe.parse_json(employee_ids) if isinstance(employee_ids, str) else employee_ids
	if not isinstance(ids, list):
		frappe.throw(_("Invalid employee list"))
	ids = list(dict.fromkeys(str(i).strip() for i in ids if i and str(i).strip()))
	if not ids:
		frappe.throw(_("Please select at least one employee"))
	if len(ids) > MAX_EMPLOYEES:
		frappe.throw(_("You can download at most {0} employees at a time").format(MAX_EMPLOYEES))
	return ids


def _resolve_photo_path(file_url):
	"""Đường dẫn tuyệt đối của ảnh trên đĩa, hoặc None (URL ngoài / data URI / file mất)."""
	if not file_url:
		return None
	url = file_url.split("?", 1)[0]
	if url.startswith("/private/files/"):
		root = frappe.get_site_path("private", "files")
		rel = url[len("/private/files/"):]
	elif url.startswith("/files/"):
		root = frappe.get_site_path("public", "files")
		rel = url[len("/files/"):]
	else:
		return None

	root = os.path.realpath(root)
	# file_url có thể lưu dạng đã percent-encode (%20) hoặc chưa — thử cả hai.
	for candidate in dict.fromkeys((rel, unquote(rel))):
		path = os.path.realpath(os.path.join(root, candidate))
		# Chặn path traversal ("../") ra ngoài thư mục files của site.
		if path.startswith(root + os.sep) and os.path.isfile(path):
			return path
	return None


def _collect(ids):
	"""Trả (entries, missing) theo thứ tự mã NV. Mã không đọc được / không tồn tại → missing."""
	rows = frappe.get_list(
		"Employee",
		filters={"name": ["in", ids]},
		fields=["name", "employee_name", "image"],
		limit_page_length=0,
	)
	by_id = {r.name: r for r in rows}

	entries, missing = [], []
	for emp in sorted(ids):
		row = by_id.get(emp)
		if not row:
			missing.append({"employee": emp, "employee_name": "", "reason": "not_found"})
			continue
		if not row.image:
			missing.append({"employee": emp, "employee_name": row.employee_name, "reason": "no_photo"})
			continue
		path = _resolve_photo_path(row.image)
		if not path:
			missing.append({"employee": emp, "employee_name": row.employee_name, "reason": "file_missing"})
			continue
		entries.append({"employee": emp, "employee_name": row.employee_name or "", "path": path})
	return entries, missing


def _to_ascii(text):
	text = text.replace("đ", "d").replace("Đ", "D")
	return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _archive_name(entry, name_format):
	ext = os.path.splitext(entry["path"])[1].lower() or ".jpg"
	if name_format == "id":
		base = entry["employee"]
	else:
		# Cùng quy ước "{mã} {họ tên}" với file lưu trên server / nút tải ở /employee-photos.
		base = f"{entry['employee']} {entry['employee_name']}".strip()
	if name_format == "id_name_ascii":
		base = _to_ascii(base)
	base = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", base)
	base = re.sub(r"\s+", " ", base).strip(" .") or entry["employee"]
	return base + ext


_REASON_LABELS = {
	"not_found": "Employee not found or no permission",
	"no_photo": "No photo",
	"file_missing": "Photo file not found on server",
}


@frappe.whitelist()
def preview_employee_photos(employee_ids):
	ids = _parse_ids(employee_ids)
	entries, missing = _collect(ids)
	return {
		"requested": len(ids),
		"photo_count": len(entries),
		"total_size": sum(os.path.getsize(e["path"]) for e in entries),
		"missing": missing,
	}


@frappe.whitelist(methods=["POST"])
def download_employee_photos(employee_ids, name_format="id_name"):
	ids = _parse_ids(employee_ids)
	if name_format not in NAME_FORMATS:
		name_format = "id_name"
	entries, missing = _collect(ids)
	if not entries:
		frappe.throw(_("None of the selected employees has a photo"))

	buf = io.BytesIO()
	used = set()
	# ZIP_STORED: JPEG/PNG đã nén sẵn, deflate chỉ tốn CPU mà gần như không nhỏ hơn.
	with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
		for entry in entries:
			arcname = _archive_name(entry, name_format)
			stem, ext = os.path.splitext(arcname)
			n = 2
			while arcname.lower() in used:
				arcname = f"{stem} ({n}){ext}"
				n += 1
			used.add(arcname.lower())
			zf.write(entry["path"], arcname)

		if missing:
			lines = [_("Employees without a downloadable photo") + f" ({len(missing)})", ""]
			lines += [
				"\t".join((m["employee"], m["employee_name"] or "", _(_REASON_LABELS[m["reason"]])))
				for m in missing
			]
			# BOM để Notepad cũ trên Windows hiện đúng tiếng Việt.
			zf.writestr("_missing_photos.txt", "﻿" + "\r\n".join(lines) + "\r\n")

	frappe.response.filename = f"employee_photos_{now_datetime():%Y%m%d_%H%M%S}.zip"
	frappe.response.filecontent = buf.getvalue()
	frappe.response.type = "download"
	frappe.response.content_type = "application/zip"
