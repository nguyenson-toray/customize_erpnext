"""Đo độ tương phản màu chữ / nền theo WCAG AA — CHỈ ĐỌC, không cần frappe.

Chạy (từ ~/frappe-bench):
    S=apps/customize_erpnext/customize_erpnext/scripts/check_contrast.py
    python3 $S pair "#fff" "#00C851"                    # đo 1 cặp chữ / nền
    python3 $S fix "#94a3b8" "#ffffff" "#f1f5f9"       # gợi ý màu cùng tông đạt chuẩn trên MỌI nền đã cho
    python3 $S scan apps/customize_erpnext/customize_erpnext/www/door_control/index.html
    python3 $S scan <file.css|.html|.js> ... [--bg "#ffffff"] [--bg-dark "#151c29"] [--min 4.5] [--all]

Chuẩn: chữ thường ≥ 4.5:1; chữ lớn (≥ 24px, hoặc ≥ 18.66px đậm) ≥ 3:1; viền / icon / thanh
tiến độ chỉ cần 3:1 → giữ được màu tươi, chỉ CHỮ mới phải dùng tông đậm hơn cùng họ màu.

Vì sao có script này (29/10/2026): `npx impeccable detect` quét tĩnh, không ghép được cặp màu
khi màu đi qua biến CSS hoặc HTML do JS dựng — bỏ sót đúng những lỗi nặng nhất (theme sáng
/door_control, chữ phụ /biometric-sync, cả trang /vehicle-dispatch). Script này:
- đọc biến `--x: #hex` theo từng theme (khối có `dark` trong selector / @media = theme tối)
  rồi ghép cặp chữ / nền CÙNG theme;
- `var(--x, #fallback)` không định nghĩa trong file → dùng fallback (biến Frappe như
  `--text-muted` không đo được tĩnh, đã kiểm: theme Frappe đạt chuẩn ở cả 2 theme);
- gradient: lấy điểm màu TỆ nhất; style inline trong HTML / JS (`style="..."`, `style: '...'`);
- bỏ qua `:disabled` / `.disabled` (WCAG miễn), màu có alpha < 1, giá trị `${...}` động;
- khối có `color` mà không có nền → so với `--bg` (mặc định trắng; theme tối: `--bg-dark`, không
  truyền thì bỏ qua), đánh dấu "(nền giả định)" và in TÁCH khỏi nhóm đo chắc chắn.

Giới hạn: không biết khối nào nằm trên nền nào trong DOM thật → kết quả "(nền giả định)" có
thể sai nếu phần tử nằm trên nền tối / nền màu; lúc đó đo lại bằng `pair` với nền thật.
"""

import colorsys
import re
import sys

NAMED = {"white": "#ffffff", "black": "#000000", "#fff": "#ffffff", "#000": "#000000"}


def parse_color(value):
	"""'#abc' / '#aabbcc' / '#aabbccff' / rgb() / rgba(a=1) / white → '#rrggbb'; còn lại None."""
	v = value.strip().lower()
	v = NAMED.get(v, v)
	m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})", v)
	if m:
		h = m.group(1)
		if len(h) == 3:
			h = "".join(c * 2 for c in h)
		if len(h) == 8:
			if h[6:] != "ff":
				return None
			h = h[:6]
		return "#" + h
	m = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)", v)
	if m:
		if m.group(4) is not None and float(m.group(4)) < 1:
			return None
		return "#" + "".join(f"{int(m.group(i)):02x}" for i in (1, 2, 3))
	return None


def luminance(hex_color):
	h = hex_color.lstrip("#")
	c = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
	c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
	return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(fg, bg):
	a, b = sorted([luminance(fg), luminance(bg)], reverse=True)
	return (a + 0.05) / (b + 0.05)


def suggest(fg, bgs, target=4.5):
	"""Giữ hue/saturation của fg, đổi lightness tới khi đạt target trên mọi nền."""
	h = fg.lstrip("#")
	r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
	hue, light, sat = colorsys.rgb_to_hls(r, g, b)
	darken = sum(luminance(x) for x in bgs) / len(bgs) > 0.4
	step = -0.005 if darken else 0.005
	while 0 <= light <= 1:
		cand = "#" + "".join(f"{round(x * 255):02x}" for x in colorsys.hls_to_rgb(hue, light, sat))
		if min(ratio(cand, x) for x in bgs) >= target:
			return cand
		light += step
	return None


# ── scan ─────────────────────────────────────────────────────────────────────


def css_blocks(text, base_offset=0):
	"""Duyệt CSS theo ngoặc, trả (chuỗi selector lồng nhau, thân khai báo, offset)."""
	stack, start, out = [], 0, []
	for i, ch in enumerate(text):
		if ch == "{":
			stack.append((text[start:i].strip().split(";")[-1].strip(), i + 1))
			start = i + 1
		elif ch == "}":
			if stack:
				sel, body_start = stack.pop()
				body = text[body_start:i]
				if "{" not in body:
					out.append(([s for s, _ in stack] + [sel], body, base_offset + body_start))
			start = i + 1
	return out


def decls(body):
	d = {}
	for part in body.split(";"):
		if ":" in part:
			k, v = part.split(":", 1)
			d[k.strip().lower()] = v.strip()
	return d


def theme_of(chain):
	return "dark" if any("dark" in s for s in chain) else "light"


class Scanner:
	def __init__(self, bg_default, bg_dark, min_ratio, show_all):
		self.bg_default, self.bg_dark = bg_default, bg_dark
		self.min, self.show_all = min_ratio, show_all
		self.vars = {}  # name -> {theme: raw value}
		self.findings, self.skipped = [], 0

	def resolve(self, value, theme, depth=0):
		"""→ danh sách hex (gradient có nhiều điểm) hoặc [] nếu không đo được."""
		if depth > 5 or "${" in value or "{{" in value:
			return []
		out = []
		for m in re.finditer(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*(?:\([^()]*\))?[^()]*))?\)", value):
			defs = self.vars.get(m.group(1))
			raw = (defs.get(theme) or defs.get("light")) if defs else m.group(2)
			if raw:
				out += self.resolve(raw, theme, depth + 1)
		rest = re.sub(r"var\([^()]*(?:\([^()]*\))?[^()]*\)", " ", value)
		for tok in re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|\bwhite\b|\bblack\b", rest):
			c = parse_color(tok)
			if c:
				out.append(c)
			else:
				self.skipped += 1
		return out

	def check(self, path, line, where, d, themes):
		fg_raw = d.get("color")
		if not fg_raw or re.search(r":disabled|\.disabled", where):
			return
		bg_raw = d.get("background-color") or d.get("background")
		size = re.search(r"([\d.]+)px", d.get("font-size", ""))
		bold = d.get("font-weight", "") in ("bold", "600", "700", "800", "900")
		large = size and (float(size.group(1)) >= 24 or (float(size.group(1)) >= 18.66 and bold))
		need = 3.0 if large else self.min
		for theme in themes:
			fgs = self.resolve(fg_raw, theme)
			bgs = self.resolve(bg_raw, theme) if bg_raw else []
			assumed = not bgs
			if assumed:
				if bg_raw and bg_raw.strip() not in ("none", "transparent"):
					continue  # có nền nhưng không đo được (alpha / biến ngoài) → bỏ
				bg = self.bg_dark if theme == "dark" else self.bg_default
				if not bg:
					continue
				bgs = [bg]
			if not fgs:
				continue
			worst = min(((ratio(f, b), f, b) for f in fgs for b in bgs), key=lambda x: x[0])
			if worst[0] < need or self.show_all:
				self.findings.append((path, line, theme, where, worst, need, assumed))

	def scan_file(self, path):
		self.vars = {}  # biến CSS chỉ có nghĩa trong từng file
		text = open(path, encoding="utf-8").read()
		line_of = lambda off: text.count("\n", 0, off) + 1
		if path.endswith(".css"):
			css_parts = [(text, 0)]
		else:
			# .html: CSS trong <style>; .js: <style> nhúng trong template literal (nếu có)
			css_parts = [(m.group(1), m.start(1)) for m in re.finditer(r"<style[^>]*>(.*?)</style>", text, re.S)]
		blocks = [b for part, off in css_parts for b in css_blocks(part, off)]
		has_dark = False
		for chain, body, _ in blocks:  # lượt 1: biến
			for k, v in decls(body).items():
				if k.startswith("--"):
					t = theme_of(chain)
					has_dark |= t == "dark"
					self.vars.setdefault(k, {}).setdefault(t, v)
		all_themes = ["light", "dark"] if has_dark else ["light"]
		for chain, body, off in blocks:  # lượt 2: cặp chữ / nền
			t = theme_of(chain)
			self.check(path, line_of(off), " ".join(chain)[-60:], decls(body), [t] if t == "dark" else all_themes)
		for m in re.finditer(r"""style\s*[=:]\s*(["'`])(.*?)\1""", text, re.S):
			self.check(path, line_of(m.start()), "inline style", decls(m.group(2)), ["light"])

	def report(self):
		counts = {}
		for group, title in ((False, "ĐO CHẮC CHẮN (chữ + nền cùng khối)"), (True, "NỀN GIẢ ĐỊNH — kiểm lại bằng `pair` với nền thật")):
			rows = [f for f in self.findings if f[6] == group]
			print(f"── {title}: {len(rows)}")
			for path, line, theme, where, (r, fg, bg), need, _ in rows:
				flag = "OK " if r >= need else "LOW"
				print(f"{flag} {r:5.2f}/{need:g}  {fg} trên {bg}  [{theme}]  {path}:{line}  {where}")
			counts[group] = sum(1 for f in rows if f[4][0] < f[5])
		print(f"\n{counts[False]} cặp chắc chắn dưới chuẩn · {counts[True]} cặp nền giả định · bỏ qua {self.skipped} màu có alpha/không đo được")
		return counts[False]


def main(argv):
	if len(argv) >= 3 and argv[0] == "pair":
		fg, bg = parse_color(argv[1]), parse_color(argv[2])
		r = ratio(fg, bg)
		print(f"{r:.2f}:1  {fg} trên {bg}  →  chữ thường {'ĐẠT' if r >= 4.5 else 'TRƯỢT'} · chữ lớn/viền/icon {'ĐẠT' if r >= 3 else 'TRƯỢT'}")
		return 0
	if len(argv) >= 3 and argv[0] == "fix":
		fg, bgs = parse_color(argv[1]), [parse_color(x) for x in argv[2:]]
		cand = suggest(fg, bgs)
		print(f"{fg}: {', '.join(f'{ratio(fg, b):.2f}' for b in bgs)}  →  {cand}: {', '.join(f'{ratio(cand, b):.2f}' for b in bgs)}" if cand else "không tìm được màu cùng tông đạt chuẩn")
		return 0
	if len(argv) >= 2 and argv[0] == "scan":
		files, bg, bg_dark, min_ratio, show_all = [], "#ffffff", None, 4.5, False
		it = iter(argv[1:])
		for a in it:
			if a == "--bg":
				bg = parse_color(next(it))
			elif a == "--bg-dark":
				bg_dark = parse_color(next(it))
			elif a == "--min":
				min_ratio = float(next(it))
			elif a == "--all":
				show_all = True
			else:
				files.append(a)
		s = Scanner(bg, bg_dark, min_ratio, show_all)
		for f in files:
			s.scan_file(f)
		return 1 if s.report() else 0
	print(__doc__)
	return 2


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
