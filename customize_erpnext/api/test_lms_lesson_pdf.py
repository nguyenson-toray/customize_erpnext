"""Tests for lms_lesson_pdf. Read-only: nothing is saved, and the user is restored.

    bench --site erp.tiqn.local execute customize_erpnext.api.test_lms_lesson_pdf.run_all
"""

import json

import frappe

from customize_erpnext.api import lms_lesson_pdf as pdf

LESSON_URL = "https://example.test/lms/courses/c/learn/1-1"


def _blocks(*blocks):
	return json.dumps({"blocks": [{"type": kind, "data": data} for kind, data in blocks]})


def test_blocks_render():
	html = pdf._blocks_html(
		_blocks(
			("header", {"text": "Tiêu đề", "level": 2}),
			("paragraph", {"text": "Bấm <b>Save</b> & xong<script>alert(1)</script>"}),
			(
				"list",
				{
					"style": "ordered",
					"items": [{"content": "Một", "items": [{"content": "Con", "items": []}]}, "Hai"],
				},
			),
			("table", {"withHeadings": True, "content": [["A"], ["<i>1</i>"]]}),
			("codeBox", {"code": "<b>x</b>"}),
			("quiz", {"quiz": "Q"}),
		),
		LESSON_URL,
	)
	assert "<h2>Tiêu đề</h2>" in html
	assert "<b>Save</b>" in html and "&amp; xong" in html
	assert "<script" not in html and "alert" not in html
	assert "<ol><li>Một<ol><li>Con</li></ol></li><li>Hai</li></ol>" in html
	assert "<th>A</th>" in html and "<td><i>1</i></td>" in html
	assert "&lt;b&gt;x&lt;/b&gt;" in html
	assert LESSON_URL in html


def test_title_heading_is_not_repeated():
	content = _blocks(("header", {"text": "Bài 1", "level": 2}), ("header", {"text": "Bài 1", "level": 2}))
	assert pdf._blocks_html(content, LESSON_URL, "Bài 1").count("Bài 1") == 1
	assert pdf._blocks_html(content, LESSON_URL, "Khác").count("Bài 1") == 2


def test_emoji_become_drawable_text():
	assert pdf._drawable_text("1\ufe0f\u20e3Thêm") == "1. Thêm"
	assert pdf._drawable_text("\U0001f449 Chi tiết \u2705") == "Chi tiết \u2714"
	assert pdf._drawable_text("Tiếng Việt → ok") == "Tiếng Việt → ok"


def test_lesson_link_is_at_the_top():
	details = frappe._dict(
		title="Bài 1",
		course_title="Khoá",
		chapter_title="Chương",
		content=_blocks(("paragraph", {"text": "Nội dung"})),
	)
	html = pdf._lesson_html(details, LESSON_URL)
	assert f'Xem chi tiết nội dung gốc tại: <a href="{LESSON_URL}">{LESSON_URL}</a>' in html
	assert html.index(LESSON_URL) < html.index("Nội dung")


def test_bad_content_is_empty():
	assert pdf._blocks_html("not json", LESSON_URL) == ""
	assert pdf._blocks_html(None, LESSON_URL) == ""


def test_video_upload_is_a_note():
	html = pdf._blocks_html(_blocks(("upload", {"file_url": "/private/files/a%20b.mp4"})), LESSON_URL)
	assert "<img" not in html and "a b.mp4" in html and LESSON_URL in html


def test_images_are_never_fetched():
	data_uri = "data:image/png;base64,AAAA"
	html = pdf._embed_images(
		f'<img src="{data_uri}"><img src="https://outside.test/a.png"><img src="/private/files/../x.png">'
	)
	assert data_uri in html
	assert '<img src="https://outside.test' not in html and 'href="https://outside.test/a.png"' in html
	assert "../x.png" not in html
	assert html.count("<img") == 1


def test_private_file_needs_lesson_reference():
	assert not pdf._can_read_private_lesson_file("/private/files/not-used-by-any-lesson.png")
	assert pdf._local_image_data_uri("/private/files/not-used-by-any-lesson.png") is None


def test_guest_cannot_read_hidden_lesson():
	user = frappe.session.user
	lesson = _hidden_lesson_position()
	try:
		frappe.set_user("Guest")
		try:
			pdf._get_readable_lesson(*lesson)
		except frappe.PermissionError:
			frappe.clear_messages()
			return
		raise AssertionError(f"Guest got {lesson}")
	finally:
		frappe.set_user(user)


def test_endpoint_requires_login():
	assert frappe.get_attr("customize_erpnext.api.lms_lesson_pdf.download_lesson_pdf") not in frappe.guest_methods


def test_missing_lesson_is_refused():
	try:
		pdf._get_readable_lesson("no-such-course", 1, 1)
	except frappe.PermissionError:
		frappe.clear_messages()
		return
	raise AssertionError("Missing lesson did not raise")


def _hidden_lesson_position():
	row = frappe.db.sql(
		"""
		select chapter_ref.parent, chapter_ref.idx, lesson_ref.idx
		from `tabChapter Reference` chapter_ref
		join `tabLesson Reference` lesson_ref on lesson_ref.parent = chapter_ref.chapter
		join `tabCourse Lesson` lesson on lesson.name = lesson_ref.lesson
		where lesson.include_in_preview = 0
		limit 1
		"""
	)
	return row[0]


def run_all():
	tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
	failed = 0
	for test in tests:
		try:
			test()
			print(f"ok    {test.__name__}")
		except Exception as error:
			failed += 1
			print(f"FAIL  {test.__name__}: {error!r}")
	frappe.db.rollback()
	print(f"{len(tests) - failed}/{len(tests)} passed")
