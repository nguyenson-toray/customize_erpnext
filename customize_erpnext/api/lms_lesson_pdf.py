"""Export one LMS lesson to PDF (button added by www/_lms.html).

Access follows the LMS itself: `get_lesson` decides who may read the lesson, and private
images go through the same checks as `serve_resource`. A file the reader may not open
becomes a note in the PDF instead of failing the export.
"""

import base64
import json
import mimetypes
import re
from urllib.parse import unquote, urlsplit

import frappe
from bs4 import BeautifulSoup
from frappe import _
from frappe.utils import cint, escape_html, get_url, md_to_html, sanitize_html, strip_html
from frappe.utils.pdf import get_pdf
from lms.lms.doctype.course_lesson.course_lesson import (
	_references_vouched_by_owner,
	_resolve_lesson_references,
)
from lms.lms.permissions import can_access_lesson
from lms.lms.utils import get_lesson, get_lms_path

# SVG is left out: File.get_content returns it as text and it can carry its own links.
_EMBEDDABLE_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"}
_LOCAL_FILE_PREFIXES = ("/files/", "/private/files/")

# The server has no emoji font, so wkhtmltopdf would print an empty box for these.
_KEYCAP_EMOJI = re.compile("(\\d)\ufe0f?\u20e3")
_MARKS_WITH_PLAIN_FORM = str.maketrans({"\u2705": "\u2714", "\u274c": "\u2718"})
_EMOJI = re.compile("[\U0001f000-\U0001faff\u2b50\ufe0f\u200d] ?")

_PDF_CSS = """
	body { font-family: "DejaVu Sans", sans-serif; font-size: 11pt; line-height: 1.5; color: #1f2933; }
	h1 { font-size: 20pt; margin: 0 0 4pt; line-height: 1.25; }
	h2 { font-size: 15pt; margin: 16pt 0 6pt; }
	h3 { font-size: 13pt; margin: 14pt 0 4pt; }
	h4, h5, h6 { font-size: 11pt; margin: 12pt 0 4pt; }
	h1, h2, h3, h4, h5, h6 { page-break-after: avoid; }
	p { margin: 0 0 8pt; }
	ul, ol { margin: 0 0 8pt; padding-left: 18pt; }
	li { margin-bottom: 3pt; }
	a { color: #1d5fa8; }
	img { display: block; max-width: 100%; margin: 6pt 0 10pt; page-break-inside: avoid; }
	table { width: 100%; border-collapse: collapse; margin: 0 0 10pt; }
	tr { page-break-inside: avoid; }
	th, td { border: 1px solid #c5ccd3; padding: 4pt 6pt; text-align: left; vertical-align: top; }
	th { background: #eef1f4; }
	pre { background: #f4f5f7; padding: 8pt; white-space: pre-wrap; word-wrap: break-word; font-size: 9pt; }
	.lesson-source { color: #5f6c7b; font-size: 9pt; margin: 0 0 14pt; padding-bottom: 8pt; border-bottom: 1px solid #c5ccd3; }
	.caption { color: #5f6c7b; font-size: 9pt; margin-top: -6pt; }
	.note { color: #5f6c7b; font-style: italic; }
	ul.checklist { list-style: none; padding-left: 0; }
"""


@frappe.whitelist(methods=["GET"])
def download_lesson_pdf(course: str, chapter: int, lesson: int):
	chapter, lesson = cint(chapter), cint(lesson)
	details = _get_readable_lesson(course, chapter, lesson)
	lesson_url = get_url(f"/{get_lms_path()}/courses/{course}/learn/{chapter}-{lesson}")

	frappe.local.response.update(
		{
			"type": "download",
			"content_type": "application/pdf",
			# as_raw corrupts non-ASCII names, so the browser builds the readable one.
			"filename": f"{frappe.scrub(course)}-{chapter}-{lesson}.pdf",
			"filecontent": get_pdf(
				_lesson_html(details, lesson_url),
				{
					"margin-top": "15mm",
					"margin-bottom": "15mm",
					"footer-right": "[page]/[topage]",
					"footer-font-size": "8",
				},
				smart_shrinking=True,
			),
		}
	)


def _get_readable_lesson(course, chapter, lesson):
	"""Return the lesson with its stored content, or refuse.

	`get_lesson` answers without a `name` when the lesson is locked, hidden, missing or SCORM.
	"""
	details = get_lesson(course, chapter, lesson)
	if not details or not details.get("name"):
		frappe.throw(_("You cannot export this lesson to PDF."), frappe.PermissionError)

	# get_lesson rewrites private URLs for the browser; the PDF reads the files directly.
	details.content, details.body = frappe.db.get_value(
		"Course Lesson", details.name, ["content", "body"]
	)
	return details


def _lesson_html(details, lesson_url):
	body = _blocks_html(details.content, lesson_url, details.title) or _clean(md_to_html(details.body or ""))
	if details.youtube:
		body += _note(_("Video: {0}").format(_link(details.youtube)))

	return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>{_PDF_CSS}</style></head>
<body>
	<h1>{_drawable_text(escape_html(details.title))}</h1>
	<p class="lesson-source">
		{escape_html(details.course_title)} / {escape_html(details.chapter_title)}<br>
		Xem chi tiết nội dung gốc tại: {_link(lesson_url)}
	</p>
	{_embed_images(_drawable_text(body))}
</body>
</html>"""


def _drawable_text(html):
	html = _KEYCAP_EMOJI.sub(r"\1. ", html)
	return _EMOJI.sub("", html.translate(_MARKS_WITH_PLAIN_FORM))


def _blocks_html(content, lesson_url, title=None):
	try:
		blocks = json.loads(content or "{}").get("blocks") or []
	except ValueError:
		return ""
	if blocks and _repeats_title(blocks[0], title):
		blocks = blocks[1:]
	return "".join(_block_html(block, lesson_url) for block in blocks)


def _repeats_title(block, title):
	"""Lessons often open with their own title as a heading; the PDF already prints it."""
	if not title or block.get("type") != "header":
		return False
	return strip_html((block.get("data") or {}).get("text") or "").strip() == title.strip()


def _block_html(block, lesson_url):
	kind, data = block.get("type"), block.get("data") or {}

	if kind == "header":
		level = min(max(cint(data.get("level")) or 2, 2), 6)
		return f"<h{level}>{_clean(data.get('text'))}</h{level}>"
	if kind in ("paragraph", "markdown"):
		text = _clean(data.get("text"))
		return f"<p>{text}</p>" if text else ""
	if kind == "list":
		return _list_html(data.get("items") or [], data.get("style"))
	if kind == "table":
		return _table_html(data)
	if kind == "codeBox":
		return f"<pre><code>{escape_html(data.get('code') or '')}</code></pre>"
	if kind == "image":
		caption = _clean(data.get("caption"))
		caption_html = f'<p class="caption">{caption}</p>' if caption else ""
		return f'<img src="{escape_html(data.get("url") or "")}">{caption_html}'
	if kind == "upload":
		return _upload_html(data, lesson_url)
	# Quiz, assignment, program, embed: they only work inside the LMS.
	return _note(_("Interactive content: {0}").format(_link(lesson_url, _("open the online lesson"))))


def _upload_html(data, lesson_url):
	file_url = data.get("file_url") or ""
	mime_type = mimetypes.guess_type(urlsplit(file_url).path)[0]
	if mime_type in _EMBEDDABLE_IMAGE_TYPES:
		return f'<img src="{escape_html(file_url)}">'

	file_name = escape_html(unquote(file_url.rsplit("/", 1)[-1]))
	return _note(
		_("File not shown in the PDF: {0}. {1}").format(
			file_name, _link(lesson_url, _("Open the online lesson"))
		)
	)


def _list_html(items, style):
	tag = "ol" if style == "ordered" else "ul"
	css = ' class="checklist"' if style == "checklist" else ""
	rows = []
	for item in items:
		if isinstance(item, str):
			item = {"content": item}
		mark = ""
		if style == "checklist":
			mark = "☑ " if (item.get("meta") or {}).get("checked") else "☐ "
		nested = _list_html(item["items"], style) if item.get("items") else ""
		rows.append(f"<li>{mark}{_clean(item.get('content'))}{nested}</li>")
	return f"<{tag}{css}>{''.join(rows)}</{tag}>"


def _table_html(data):
	rows = []
	for index, row in enumerate(data.get("content") or []):
		cell = "th" if index == 0 and data.get("withHeadings") else "td"
		rows.append("<tr>" + "".join(f"<{cell}>{_clean(value)}</{cell}>" for value in row) + "</tr>")
	return f"<table>{''.join(rows)}</table>"


def _embed_images(html):
	"""Put image data in the HTML; wkhtmltopdf only fetches what it can reach without a session.

	Private files would be refused to students, and an outside address should not be fetched
	from the server, so anything that cannot be embedded becomes a note.
	"""
	soup = BeautifulSoup(html, "html.parser")
	for img in soup.find_all("img"):
		src = img.get("src") or ""
		data_uri = src if src.startswith("data:image/") else _local_image_data_uri(src)
		if data_uri:
			img["src"] = data_uri
			continue

		is_external = urlsplit(src).scheme in ("http", "https")
		message = _("Image: {0}").format(_link(src)) if is_external else _("Image not available.")
		img.replace_with(BeautifulSoup(_note(message), "html.parser"))
	return str(soup)


def _local_image_data_uri(src):
	file_url = unquote(urlsplit(src).path)
	mime_type = mimetypes.guess_type(file_url)[0]
	if not file_url.startswith(_LOCAL_FILE_PREFIXES) or ".." in file_url:
		return None
	if mime_type not in _EMBEDDABLE_IMAGE_TYPES:
		return None

	is_private = file_url.startswith("/private/")
	if is_private and not _can_read_private_lesson_file(file_url):
		return None

	file_name = frappe.db.get_value("File", {"file_url": file_url, "is_private": cint(is_private)})
	if not file_name:
		return None

	try:
		content = frappe.get_doc("File", file_name).get_content()
	except OSError:
		frappe.log_error(title="LMS lesson PDF: cannot read image", message=file_url)
		return None
	return f"data:{mime_type};base64,{base64.b64encode(content).decode()}"


def _can_read_private_lesson_file(file_url):
	"""Same rule as lms `serve_resource`, so naming a file in a lesson does not unlock it."""
	references = _references_vouched_by_owner(_resolve_lesson_references(file_url))
	return any(can_access_lesson(lesson, instructor_only=only) for lesson, only in references)


def _clean(html):
	if not html:
		return ""
	return sanitize_html(html, always_sanitize=True, disallowed_tags={"html", "head", "meta", "link", "body"})


def _link(url, label=None):
	safe_url = escape_html(url)
	return f'<a href="{safe_url}">{escape_html(label) if label else safe_url}</a>'


def _note(html):
	return f'<p class="note">{html}</p>'
