import os
import re
from urllib.parse import urlparse, parse_qs

import frappe
from unidecode import unidecode
from frappe.utils.file_manager import delete_file

LMS_CONTENT_DOCTYPES = {"Course Lesson"}
LMS_FILE_URL_PREFIXES = ("/files/lms_course/", "/private/files/lms_course/")


def _slugify(text):
	"""Vietnamese-safe slug: bỏ dấu, hạ chữ thường, khoảng trắng/ký tự lạ -> '-'."""
	text = unidecode(text or "").lower()
	text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
	return text or "untitled"


def _target_from_lesson(lesson_name):
	lesson = frappe.db.get_value(
		"Course Lesson", lesson_name, ["name", "chapter", "course"], as_dict=True
	)
	if not lesson or not lesson.course:
		return None
	chapter_slug = _slugify(lesson.chapter) if lesson.chapter else "no-chapter"
	lesson_slug = _slugify(lesson.name)
	return lesson.course, chapter_slug, lesson_slug


def _lms_upload_target_from_attach(self):
	"""(course_slug, chapter_slug, lesson_slug) nếu File doc có attached_to_doctype =
	Course Lesson (trường hợp lý tưởng, nhưng thực tế đo được luồng Upload tool trong
	editor KHÔNG gửi field này — xem _lms_upload_target_from_referer bên dưới)."""
	if self.attached_to_doctype not in LMS_CONTENT_DOCTYPES or not self.attached_to_name:
		return None
	return _target_from_lesson(self.attached_to_name)


# .../lms/courses/{course}?editLesson={chapter_idx}-{lesson_idx}  (CourseEditor.vue)
_EDIT_LESSON_RE = re.compile(r"/courses/([^/?#]+)")


def _lms_upload_target_from_referer():
	"""Thực tế đo được: nút Upload trong editor bài học KHÔNG gửi kèm
	doctype/docname cho File (attached_to luôn NULL — có thể do race condition
	phía app lms). Nhận diện qua HTTP Referer thay thế: trang đang mở lúc bấm
	Upload luôn có dạng .../lms/courses/{course}?editLesson={chapter_idx}-{lesson_idx},
	tra ngược Chapter Reference / Lesson Reference theo idx ra đúng tên chapter/lesson.
	"""
	try:
		referer = frappe.get_request_header("Referer") or ""
	except RuntimeError:
		# Không có HTTP request thật (bench execute, background job, scheduler...)
		return None
	if not referer:
		return None

	parsed = urlparse(referer)
	m = _EDIT_LESSON_RE.search(parsed.path)
	if not m:
		return None
	course = m.group(1)

	qs = parse_qs(parsed.query)
	edit_lesson = (qs.get("editLesson") or [None])[0]
	if not edit_lesson or "-" not in edit_lesson:
		return None
	chapter_idx, _, lesson_idx = edit_lesson.partition("-")
	if not (chapter_idx.isdigit() and lesson_idx.isdigit()):
		return None

	chapter = frappe.db.get_value(
		"Chapter Reference", {"parent": course, "idx": chapter_idx}, "chapter"
	)
	if not chapter:
		return None
	lesson = frappe.db.get_value(
		"Lesson Reference", {"parent": chapter, "idx": lesson_idx}, "lesson"
	)
	if not lesson:
		return None
	return _target_from_lesson(lesson)


def _lms_upload_target(self):
	"""(course_slug, chapter_slug, lesson_slug) nếu đây là file upload cho Course
	Lesson; None nếu không -> rơi về hành vi gốc. Thử attached_to trước (rẻ, không
	cần request context), rồi Referer (đường thực tế đang chạy trên production)."""
	return _lms_upload_target_from_attach(self) or _lms_upload_target_from_referer()


def custom_save_file_on_filesystem(self):
	"""Ghi file vào files/lms_course/{course}/{chapter}_{lesson}_{tên gốc} (hoặc
	private/files/... nếu is_private) khi file được upload cho Course Lesson (nút
	Upload trong editor bài học LMS). Mọi upload khác (Employee, Packing List, đính
	kèm document thường...) rơi về hàm gốc File.save_file_on_filesystem, không đổi
	hành vi.
	"""
	target = _lms_upload_target(self)
	if not target:
		return self._original_save_file_on_filesystem()

	course_slug, chapter_slug, lesson_slug = target
	safe_original = re.sub(r"[/\\%?#]", "_", self.file_name)
	new_filename = f"{chapter_slug}_{lesson_slug}_{safe_original}"

	prefix = "/private/files" if self.is_private else "/files"
	self.file_url = f"{prefix}/lms_course/{course_slug}/{new_filename}"

	full_path = self.get_full_path()
	os.makedirs(os.path.dirname(full_path), exist_ok=True)

	# Trùng tên (vd upload lại cùng tên gốc cho cùng lesson) -> thêm hash, không ghi đè âm thầm
	if os.path.exists(full_path):
		name, ext = os.path.splitext(new_filename)
		new_filename = f"{name}_{frappe.generate_hash(length=6)}{ext}"
		self.file_url = f"{prefix}/lms_course/{course_slug}/{new_filename}"

	self.file_name = new_filename
	fpath = self.write_file()

	return {"file_name": os.path.basename(fpath), "file_url": self.file_url}


def custom_delete_file_from_filesystem(self, only_thumbnail=False):
	"""Hàm gốc (frappe.utils.file_manager.delete_file) chỉ hiểu đúng path phẳng
	1 cấp (files/<name> hoặc private/files/<name>): nó tách bằng os.path.split rồi
	so parts[0] == "files" để quyết định public/private. Với path nhiều cấp như
	files/lms_course/{course}/{file}, parts[0] là "files/lms_course/{course}"
	(khác "files") nên nó tưởng đây là private file và ghép sai đường dẫn -> không
	xoá được gì, để lại rác vật lý mỗi khi ảnh LMS bị xoá/thay thế.

	Với file do patch upload này tạo (file_url bắt đầu bằng /files/lms_course/ hoặc
	/private/files/lms_course/), tự resolve full path đúng qua get_full_path() (đã
	hỗ trợ path nhiều cấp) và xoá trực tiếp. Mọi file khác vẫn qua hàm gốc, không
	đổi hành vi.
	"""
	if only_thumbnail:
		return self._original_delete_file_from_filesystem(only_thumbnail=True)

	if self.file_url and self.file_url.startswith(LMS_FILE_URL_PREFIXES):
		full_path = self.get_full_path()
		if os.path.exists(full_path):
			os.remove(full_path)
		if self.thumbnail_url:
			delete_file(self.thumbnail_url)
		return

	return self._original_delete_file_from_filesystem(only_thumbnail=False)
