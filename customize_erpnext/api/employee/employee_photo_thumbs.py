"""Ảnh thu nhỏ cho lưới trang /employee-photos.

Thumb nằm ở `public/files/employee_photos/_thumbs/<tên ảnh gốc không đuôi>.jpg`.
An toàn mặc định: `fresh_thumb_url()` chỉ trả thumb khi nó MỚI HƠN ảnh gốc — chỗ nào ghi ảnh
mà không sinh lại thumb (Desk, import...) thì lưới tự dùng ảnh gốc, không bao giờ hiện ảnh cũ.
Xem/sửa/tải ZIP/in thẻ luôn dùng ảnh gốc.

Backfill / dọn thumb mồ côi:
    bench --site erp.tiqn.local execute customize_erpnext.api.employee.employee_photo_thumbs.backfill
"""
import os

import frappe

THUMB_DIRNAME = "_thumbs"
# Card L = 260px CSS; 300×400 đủ nét ở card M trên màn 1,5x
THUMB_SIZE = (300, 400)
THUMB_QUALITY = 80


def photo_disk_path(file_url):
	"""Đường dẫn trên đĩa của ảnh public `/files/...`; None với URL khác (private, http, rỗng)."""
	if not file_url or not file_url.startswith("/files/"):
		return None
	return frappe.get_site_path("public", file_url.split("?")[0].lstrip("/"))


def _thumb_location(file_url):
	"""(đường dẫn đĩa, url) của thumb tương ứng, hoặc (None, None)."""
	src = photo_disk_path(file_url)
	if not src:
		return None, None
	folder_url, name = file_url.split("?")[0].rsplit("/", 1)
	stem = os.path.splitext(name)[0]
	thumb_name = f"{stem}.jpg"
	return (
		os.path.join(os.path.dirname(src), THUMB_DIRNAME, thumb_name),
		f"{folder_url}/{THUMB_DIRNAME}/{thumb_name}",
	)


def fresh_thumb_url(file_url, src_mtime):
	"""URL thumb nếu thumb tồn tại và không cũ hơn ảnh gốc; ngược lại ''."""
	path, url = _thumb_location(file_url)
	if not path or not src_mtime:
		return ""
	try:
		return url if os.stat(path).st_mtime >= src_mtime else ""
	except OSError:
		return ""


def make_thumb(file_url):
	"""Sinh (lại) thumb cho ảnh gốc. Lỗi chỉ ghi log — không được làm hỏng việc lưu ảnh."""
	src = photo_disk_path(file_url)
	path, url = _thumb_location(file_url)
	if not src or not path or not os.path.exists(src):
		return None
	try:
		from PIL import Image, ImageOps

		os.makedirs(os.path.dirname(path), exist_ok=True)
		with Image.open(src) as im:
			im = ImageOps.exif_transpose(im)
			if im.mode in ("RGBA", "LA", "P"):
				im = im.convert("RGBA")
				bg = Image.new("RGB", im.size, (255, 255, 255))
				bg.paste(im, mask=im.getchannel("A"))
				im = bg
			else:
				im = im.convert("RGB")
			im.thumbnail(THUMB_SIZE, Image.LANCZOS)
			tmp = path + ".tmp"
			im.save(tmp, "JPEG", quality=THUMB_QUALITY, optimize=True, progressive=True)
		os.replace(tmp, path)
		return url
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Employee photo thumb failed: {file_url}")
		return None


def remove_thumb(file_url):
	path, _url = _thumb_location(file_url)
	if path and os.path.exists(path):
		try:
			os.remove(path)
		except OSError:
			pass


def backfill(force=0):
	"""Sinh thumb cho mọi ảnh NV còn thiếu/cũ + xoá thumb không còn ảnh gốc. Chạy tay, an toàn chạy lại."""
	images = frappe.get_all("Employee", filters={"image": ["like", "/files/%"]}, pluck="image")
	made = skipped = missing = 0
	keep = set()
	for file_url in images:
		src = photo_disk_path(file_url)
		path, _url = _thumb_location(file_url)
		if not src or not os.path.exists(src):
			missing += 1
			continue
		keep.add(os.path.abspath(path))
		if not int(force) and fresh_thumb_url(file_url, os.stat(src).st_mtime):
			skipped += 1
			continue
		if make_thumb(file_url):
			made += 1

	removed = 0
	for folder in {os.path.dirname(p) for p in keep}:
		for name in os.listdir(folder):
			p = os.path.abspath(os.path.join(folder, name))
			if p not in keep and not name.endswith(".tmp"):  # .tmp = đang ghi dở
				os.remove(p)
				removed += 1

	msg = f"thumbs: made {made}, up-to-date {skipped}, source missing {missing}, orphans removed {removed}"
	print(msg)
	return msg
