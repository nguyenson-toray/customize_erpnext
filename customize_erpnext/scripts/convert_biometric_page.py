"""Chuyển www/biometric_sync/index.html (đọc, KHÔNG sửa) thành Page desk network/page/biometric_sync/.

⚠ 19/10/2026: trang www nguồn ĐÃ XOÁ — page desk giờ là nguồn chính, script này KHÔNG chạy lại được nữa.
Giữ làm MẪU để chuyển trang www khác (vd. /door_control): scope CSS + reset Bootstrap, namespace JS +
handler inline, alert/confirm → frappe, nhúng HTML trong JS. Xem skill references/www-to-desk-page.md.

Usage (từ thư mục apps/customize_erpnext/customize_erpnext):
    python3 scripts/convert_biometric_page.py "$PWD"
Chạy lại mỗi khi sửa www/biometric_sync/index.html, cho tới khi bỏ hẳn trang www.
Kiểm tra sau khi chạy: node scripts/smoke_biometric_page.js <script page lấy từ desk_page.get> <đường dẫn jsdom>
"""

import json
import os
import re
import sys

APP = sys.argv[1]
SRC = os.path.join(APP, "www", "biometric_sync", "index.html")
OUT = os.path.join(APP, "network", "page", "biometric_sync")
SCOPE = ".bsync"

src = open(SRC).read()
css = re.search(r"<style>(.*?)</style>", src, re.S).group(1)
body = re.search(r"<body[^>]*>(.*?)<script>", src, re.S).group(1)
js = re.search(r"<script>(.*?)</script>", src, re.S).group(1)


# ── CSS: giới hạn mọi selector trong .bsync ─────────────────────────────────
def split_top(s, sep=","):
	out, depth, cur = [], 0, ""
	for ch in s:
		if ch in "([":
			depth += 1
		elif ch in ")]":
			depth -= 1
		if ch == sep and depth == 0:
			out.append(cur)
			cur = ""
		else:
			cur += ch
	out.append(cur)
	return out


def scope_selector(sel):
	sel = sel.strip()
	if not sel:
		return sel
	if sel in (":root", "html", "body"):
		return SCOPE
	if sel == "*":
		return f"{SCOPE}, {SCOPE} *"
	for g in ("html ", "body "):
		if sel.startswith(g):
			return f"{SCOPE} {sel[len(g):]}"
	if sel.startswith("*"):
		return f"{SCOPE} {sel}"
	return f"{SCOPE} {sel}"


def scope_css(text):
	text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
	text = re.sub(r"@import\s+url\([^)]*\)\s*;", "", text)
	out, i = [], 0
	while i < len(text):
		j = text.find("{", i)
		if j < 0:
			out.append(text[i:])
			break
		prelude = text[i:j].strip()
		# tìm khối khớp
		depth, k = 1, j + 1
		while depth and k < len(text):
			if text[k] == "{":
				depth += 1
			elif text[k] == "}":
				depth -= 1
			k += 1
		inner = text[j + 1:k - 1]
		if prelude.startswith("@keyframes") or prelude.startswith("@font-face"):
			out.append(f"{prelude}{{{inner}}}\n")
		elif prelude.startswith("@media") or prelude.startswith("@supports"):
			out.append(f"{prelude}{{\n{scope_css(inner)}}}\n")
		else:
			sels = [scope_selector(s) for s in split_top(prelude)]
			out.append(f"{', '.join(sels)} {{{inner}}}\n")
		i = k
	return "".join(out)


css_out = scope_css(css)
css_out += """
/* ── chỉnh cho bố cục trong desk (có sidebar nên hẹp hơn tab riêng) ── */
.bsync { min-height: auto; }
.bsync .main-wrap { padding: 4px 0 40px; }
.bsync .tab-nav-wrap { flex-wrap: wrap; }

/* ── gỡ Bootstrap của desk khỏi các class trùng tên ──
 * Trang www cũ không nạp Bootstrap; trong desk thì có, và nó định nghĩa .card là flex column
 * (nút con bị kéo giãn hết chiều ngang), .form-row lề âm, .form-group lề dưới, .badge viền đen,
 * .form-control ép chiều cao. :where() giữ độ ưu tiên ngang Bootstrap (thắng vì nạp sau) nhưng
 * thấp hơn quy tắc riêng của trang (.bsync .machine-item .badge…) nên không đè lên chúng. */
:where(.bsync) .card { display: block; min-width: auto; }
:where(.bsync) .form-group { margin-bottom: 0; }
:where(.bsync) .form-row { margin-left: 0; margin-right: 0; }
:where(.bsync) .progress-bar { display: block; }
:where(.bsync) .badge { display: inline; padding: 0; font-size: inherit; line-height: inherit; border: 0; border-radius: 0; }
:where(.bsync) textarea.form-control { display: block; height: auto; line-height: 1.5; background-color: var(--surface); }
"""
css_out = css_out.replace("'DM Sans', ", "").replace("'JetBrains Mono', ", "")

# ── HTML: bỏ Jinja, đánh dấu phần chỉ System Manager ────────────────────────
body = body.replace(
	"{% if is_system_manager %}\n            <button class=\"tab-btn\" data-tab=\"tab-door\"",
	"<button class=\"tab-btn\" data-sm-only=\"1\" data-tab=\"tab-door\"",
)
body = body.replace(
	"{% if is_system_manager %}\n        <!--",
	"<!--",
)
body = body.replace('<div id="tab-door" class="tab-panel">', '<div id="tab-door" class="tab-panel" data-sm-only="1">')
body = re.sub(r"\s*{% endif %}", "", body)
assert "{%" not in body and "{{" not in body, "jinja left in HTML"
# Tab "IT Door Access" bỏ hẳn khỏi page desk (17/10/2026): đã có /door_control. Trang www cũ giữ nguyên.
body, n1 = re.subn(r'\s*<button class="tab-btn" data-sm-only="1" data-tab="tab-door".*?</button>', "", body, flags=re.S)
body, n2 = re.subn(r"\s*<!--[^>]*?TAB 7: IT DOOR ACCESS.*?</div><!-- end tab-door -->", "", body, flags=re.S)
assert n1 == 1 and n2 == 1, f"door tab not removed ({n1}, {n2})"
assert "tab-door" not in body
# thanh tiêu đề riêng (nền tối, sticky) trùng với tiêu đề của desk -> bỏ
body, n = re.subn(r'\s*<!-- Sticky topbar -->\s*<header class="page-header">.*?</header>', "", body, flags=re.S)
assert n == 1, "header not found"

# ── JS ─────────────────────────────────────────────────────────────────────
js = js.replace('window.csrf_token = "{{ csrf_token }}";', "")
js = js.replace("window.is_system_manager = {{ 1 if is_system_manager else 0 }};",
				'window.is_system_manager = frappe.user.has_role("System Manager") ? 1 : 0;')
js = js.replace("fd.append('csrf_token', window.csrf_token);", "fd.append('csrf_token', frappe.csrf_token);")
assert "{{" not in js and "{%" not in js, "jinja left in JS"

# init: DOMContentLoaded -> chạy ở cuối hàm setup (sau khi mọi let/const đã khai báo)
init_re = re.compile(r"window\.addEventListener\('DOMContentLoaded', \(\) => \{\s*(.*?)\s*\}\);", re.S)
m = init_re.search(js)
init_body = m.group(1)
js = js[:m.start()] + js[m.end():]

# JS của tab IT Door Access (các hàm da*) — từ đầu mục TAB 7 tới hết script
door_js = re.search(r"\n\s*// ═+\n\s*// TAB 7: IT DOOR ACCESS\n.*", js, re.S)
assert door_js, "door JS section not found"
js = js[:door_js.start()] + "\n"
js, n = re.subn(r"\n\s*if \(tabId === 'tab-door'\) daInitTab\(\);", "", js)
assert n == 1 and "daInitTab" not in js and "_daRows" not in js

# listener 'change' gắn vào document -> gắn vào khung trang
js = js.replace("document.addEventListener('change', e => {", "root.addEventListener('change', e => {")
# chọn phần tử trong khung trang, không quét cả desk (.tab-btn / .tab-panel / .user-cb là tên chung)
js = js.replace("document.querySelectorAll(", "root.querySelectorAll(").replace("document.querySelector(", "root.querySelector(")

# confirm/alert -> hộp thoại frappe
js = re.sub(r"(?<![\w.$])confirm\(", "await bsyncConfirm(", js)
js = re.sub(r"(?<![\w.$])alert\(", "bsyncAlert(", js)
for fn in ("del43SpecificDelete", "rsRunDeviceResync", "rsRunMongoResync", "rsRunOtSync", "rsRunDeleteOt"):
	js, n = re.subn(rf"(?<!async )function {fn}\(", f"async function {fn}(", js)
	assert n == 1, fn

# kiểm: mọi 'await bsyncConfirm' phải nằm trong hàm async
lines = js.split("\n")
for i, l in enumerate(lines):
	if "await bsyncConfirm(" in l:
		j = i
		while j >= 0 and not re.search(r"^\s{8}(async\s+)?function\s+\w+", lines[j]):
			j -= 1
		assert "async" in lines[j], f"confirm in non-async fn: {lines[j].strip()}"

# hàm top-level -> xuất ra namespace bsync cho handler inline
funcs = sorted(set(re.findall(r"^\s{8}(?:async\s+)?function\s+([A-Za-z_]\w*)\s*\(", js, re.M)))


def rewrite_handlers(text):
	def fix(m):
		val = m.group(3)
		for fn in funcs:
			val = re.sub(rf"(?<![\w.$]){fn}\(", f"bsync.{fn}(", val)
		return f"{m.group(1)}{m.group(2)}{val}{m.group(2)}"
	return re.sub(r"(\son[a-z]+=)([\"'])(.*?)\2", fix, text)


body = rewrite_handlers(body)
js = rewrite_handlers(js)

helpers = """
        // ── Hộp thoại frappe thay alert/confirm gốc của trình duyệt ──────────────────
        function _bsyncHtml(msg) {
            return frappe.utils.escape_html(String(msg)).replace(/\\n/g, '<br>');
        }
        function bsyncAlert(msg) {
            frappe.msgprint({ message: _bsyncHtml(msg), indicator: 'orange' });
        }
        function bsyncConfirm(msg) {
            return new Promise(resolve => {
                // frappe.confirm tự gọi nhánh "không" khi đóng bằng X / Esc
                frappe.confirm(_bsyncHtml(msg), () => resolve(true), () => resolve(false));
            });
        }
"""

html_full = f'<div class="bsync">\n{body}\n</div>'
html_literal = html_full.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
page_js = f"""// Biometric Sync — Page desk (thay cho trang www /biometric_sync, mở trong desk có sidebar)
// Sinh từ www/biometric_sync/index.html bằng script chuyển đổi; xem
// .claude/plans/biometric_sync_desk_page.md. Server/API không đổi.
//
// Toàn bộ code cũ chạy trong bsync.setup(root) (closure, không còn 70 hàm global); handler inline
// gọi qua namespace `bsync.*`. CSS giới hạn trong .bsync (biometric_sync.css).

frappe.provide("bsync");

// HTML nằm ngay trong file JS (template literal): file .html của Page bị frappe nhúng thành chuỗi
// bọc nháy đơn mà KHÔNG escape nháy đơn bên trong -> onclick="bsync.switchTab('x')" làm gãy cả script.
const BSYNC_HTML = `{html_literal}`;

frappe.pages["biometric-sync"].on_page_load = function (wrapper) {{
    const page = frappe.ui.make_app_page({{
        parent: wrapper,
        title: __("Biometric Sync"),
        single_column: true,
    }});
    $(page.body).html(BSYNC_HTML);
    const root = page.body.find(".bsync").get(0);
    if (!frappe.user.has_role("System Manager")) {{
        root.querySelectorAll("[data-sm-only]").forEach(el => el.remove());
    }}
    bsync.setup(root);
}};

bsync.setup = function (root) {{
{helpers}
{js}

        // ── khởi tạo (trước là DOMContentLoaded) ─────────────────────────────────────
        {init_body}

        Object.assign(bsync, {{ {", ".join(funcs)} }});
}};
"""

page_json = {
	"content": None, "creation": "2026-10-17 18:00:00.000000", "docstatus": 0, "doctype": "Page",
	"idx": 0, "modified": "2026-10-17 18:00:00.000000", "modified_by": "Administrator",
	"module": "Network", "name": "biometric-sync", "owner": "Administrator", "page_name": "biometric-sync",
	"roles": [{"role": "System Manager"}, {"role": "HR Manager"}, {"role": "HR User"}],
	"script": None, "standard": "Yes", "style": None, "system_page": 0, "title": "Biometric Sync",
}

os.makedirs(OUT, exist_ok=True)
open(os.path.join(OUT, "__init__.py"), "w").close()
open(os.path.join(OUT, "biometric_sync.json"), "w").write(json.dumps(page_json, indent=1) + "\n")
open(os.path.join(OUT, "biometric_sync.css"), "w").write(
	"/* Biometric Sync — mọi selector giới hạn trong .bsync để không đè giao diện desk.\n"
	" * Sinh từ www/biometric_sync/index.html. */\n" + css_out)
html_path = os.path.join(OUT, "biometric_sync.html")
if os.path.exists(html_path):
	os.remove(html_path)  # frappe nạp MỌI file .html trong thư mục page -> phải xoá
open(os.path.join(OUT, "biometric_sync.js"), "w").write(page_js)
print("functions exported:", len(funcs))
print("handlers rewritten:", len(re.findall(r"bsync\.\w+\(", body)) + len(re.findall(r'on[a-z]+=["\'][^"\']*bsync\.', js)))
print("confirm->", js.count("await bsyncConfirm("), "| alert->", js.count("bsyncAlert(") - 0)
