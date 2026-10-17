#!/usr/bin/env python3
"""Phần dùng chung của các sơ đồ trong docs/flowchart.

Hai script build_erpnext_flowchart.py và build_hrms_flowchart.py chỉ khai báo
dữ liệu (khung module, ô, mũi tên, bằng chứng trong source) rồi gọi `main()` ở
đây. Toàn bộ việc tính toạ độ, rải điểm neo, sinh XML, grep đối chiếu source,
ghi file .md và chặn ghi đè bản sửa tay nằm trong file này.

Vì sao tự vẽ XML thay vì dùng thư viện: file .drawio để XML trần, không nén,
để git diff đọc được từng dòng — bản .drawio cũ nén base64 nên mỗi lần sửa chỉ
thấy một khối ký tự vô nghĩa.
"""

import hashlib
import html
import os
import re
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.realpath(os.path.join(HERE, "..", "docs", "flowchart"))

# ── hằng số bố cục — sửa ở đây là cả sơ đồ giãn theo ──────────────────────
NODE_W, NODE_H = 210, 46
V_GAP = 44          # khoảng hở dọc giữa hai ô = độ dài mũi tên nhìn thấy
H_GAP = 86          # khoảng hở ngang giữa hai khung module
GROUP_W = NODE_W + 40
HEAD = 50           # chỗ cho tên module
PAD_B = 20
COL = [40 + i * (GROUP_W + H_GAP) for i in range(8)]

# ── màu từng khung module ────────────────────────────────────────────────
C = {
    "crm":      ("#e8f0fe", "#3b6fd4"),
    "selling":  ("#e7f6ec", "#1e8e4e"),
    "stock":    ("#fff4e5", "#d97706"),
    "buying":   ("#f3ecfb", "#7c4dbd"),
    "mfg":      ("#fdecef", "#c2405a"),
    "sub":      ("#fdf3e7", "#b06a00"),
    "project":  ("#e9f6f8", "#0f7d8c"),
    "support":  ("#f1f3f6", "#5b6675"),
    "asset":    ("#eef7e8", "#4a7c2f"),
    "quality":  ("#f6f0e8", "#8a6d3b"),
    "accounts": ("#e6eefc", "#23478a"),
}

EDGE_STYLE = {
    "doc":  "strokeColor=#7d879a;endArrow=blockThin;endFill=1;strokeWidth=1.4;",
    "data": "strokeColor=#b6bdc8;dashed=1;endArrow=open;endFill=0;",
    "gl":   "strokeColor=#23478a;endArrow=blockThin;endFill=1;strokeWidth=1.8;",
}

# ── chú giải các loại mũi tên, giống nhau ở mọi sơ đồ ─────────────────────
# (kiểu, mô tả hình thức mũi tên, tên, giải thích)
LEGEND = [
    ("doc", "Grey solid arrow", "Creates the next document",
     "Press Create on the first document and %(app)s opens the next one, already filled in. "
     "The two documents stay linked, so quantities and amounts are carried over and tracked."),
    ("data", "Grey dashed arrow", "Supplies data only",
     "The document at the tip reads master data, a rule or a plan from the one at the tail. "
     "Nothing is created and nothing is posted."),
    ("gl", "Blue solid arrow", "Posts to the General Ledger",
     "Submitting the document writes its accounting entries by itself. "
     "Cancel the document and the entries are reversed."),
]
LEG_ROW = 62
KIND_VN = {"doc": "tạo chứng từ tiếp theo", "data": "chỉ lấy dữ liệu",
           "gl": "ghi vào sổ cái"}


def esc(t):
    return html.escape(t, quote=True)


class Flowchart:
    """Khai báo một sơ đồ. Xem build_erpnext_flowchart.py để biết cách dùng."""

    def __init__(self, *, key, title, subtitle, app, version, src,
                 modules, edges, band=None, group_edges=(), overhead=None,
                 evidence=None, omitted=(), quirks=(), rows=None, legend_col=None,
                 legend_y=None, legend_w=None):
        self.key = key                  # tên file: <key>.drawio + <key>.md
        self.title = title
        self.subtitle = subtitle
        self.app = app                  # "ERPNext" / "HRMS", dùng trong câu chữ
        self.version = version
        self.src = src                  # thư mục source để grep bằng chứng
        self.edges = list(edges)
        self.group_edges = list(group_edges)
        self.overhead = dict(overhead or {})
        self.evidence = dict(evidence or {})
        self.omitted = list(omitted)
        self.quirks = list(quirks)      # chỗ cố ý vẽ khác source, giải thích trong .md

        # khung module: (gid, title, colour, cột, hàng, [(id ô, nhãn), ...])
        row1 = (rows or (100, None))[0]
        self.groups, self.nodes = [], []
        self.members = {}               # gid -> [id ô], để vẽ subgraph mermaid
        tallest = 0
        for gid, gtitle, colour, col, row, items in modules:
            gh = HEAD + len(items) * (NODE_H + V_GAP) - V_GAP + PAD_B
            if row == 0:
                tallest = max(tallest, gh)
        row2 = (rows or (None, None))[1] or (row1 + tallest + 84)
        self.rows = (row1, row2)
        for gid, gtitle, colour, col, row, items in modules:
            gh = HEAD + len(items) * (NODE_H + V_GAP) - V_GAP + PAD_B
            gx, gy = COL[col], self.rows[row]
            self.groups.append((gid, gtitle, colour, gx, gy, GROUP_W, gh))
            self.members[gid] = [nid for nid, _ in items]
            for i, (nid, label) in enumerate(items):
                self.nodes.append((nid, label, colour, gx + 20,
                                   gy + HEAD + i * (NODE_H + V_GAP), NODE_W, NODE_H))

        self.ncol = max(m[3] for m in modules) + 1
        # dải ngang cuối sơ đồ: các cặp ô trải đều, ô cuối to gấp đôi
        if band:
            bid, btitle, bcolour, columns, wide = band
            by = max(g[4] + g[6] for g in self.groups) + 90
            bw = COL[self.ncol - 1] + GROUP_W - COL[0]
            self.groups.append((bid, btitle, bcolour, COL[0], by, bw,
                                HEAD + 2 * (NODE_H + V_GAP) - V_GAP + PAD_B))
            step = (bw - 60 - 40) // (len(columns) + 1)
            self.members[bid] = [nid for pair in columns for nid, _ in pair] + [wide[0]]
            for i, pair in enumerate(columns):
                for k, (nid, label) in enumerate(pair):
                    self.nodes.append((nid, label, bcolour, COL[0] + 30 + i * step,
                                       by + HEAD + k * (NODE_H + V_GAP), NODE_W, NODE_H))
            self.nodes.append((wide[0], wide[1], bcolour,
                               COL[0] + 30 + len(columns) * step, by + HEAD,
                               NODE_W + 90, 2 * NODE_H + V_GAP))

        # chú giải đặt vào khoảng trống, mặc định hai cột cuối của hàng dưới
        lc = self.ncol - 2 if legend_col is None else legend_col
        self.leg_x = COL[lc]
        self.leg_w = legend_w or COL[self.ncol - 1] + GROUP_W - COL[lc]
        self.leg_h = 48 + len(LEGEND) * LEG_ROW + 34
        self.leg_y = self.rows[1] + 180 if legend_y is None else legend_y

    # ── mũi tên ──────────────────────────────────────────────────────────
    def all_arrows(self):
        """EDGES + GROUP_EDGES; thứ tự này quyết định luôn id e0, e1, ... trong file."""
        return ([(a, b, lbl, kind) for a, b, lbl, kind in self.edges]
                + [(a, b, lbl, "gl") for a, b, lbl in self.group_edges])

    def labels(self):
        out = {n[0]: re.sub(r"&amp;", "&", n[1]) for n in self.nodes}
        out.update({g[0]: re.sub(r"&amp;", "&", g[1]) + " (cả khung)" for g in self.groups})
        return out

    # ── sinh mermaid ─────────────────────────────────────────────────────
    def mermaid(self):
        """Cùng nội dung với file .drawio, dạng mermaid để tab Flowchart ở /dev-tool vẽ được.

        Tab đó chỉ đọc khối ```mermaid trong .md; không có khối này thì nó báo
        "Không tìm thấy khối mermaid nào". Bố cục do mermaid tự xếp, không giống
        hệt bản draw.io, nhưng đủ ô, đủ mũi tên và cùng ba kiểu mũi tên.
        """
        def q(t):
            return '"%s"' % html.unescape(t).replace('"', "#quot;")

        # tiền tố n_ để id ô không đụng từ khoá mermaid (end, graph, ...)
        nid = {n[0]: "n_" + n[0] for n in self.nodes}
        nid.update({g[0]: g[0] for g in self.groups})
        label = {n[0]: n[1] for n in self.nodes}

        L = ["flowchart TB"]
        for gid, gtitle, colour, *_ in self.groups:
            L.append("    subgraph %s[%s]" % (gid, q(gtitle)))
            L.append("        direction TB")
            L += ["        %s[%s]" % (nid[m], q(label[m])) for m in self.members[gid]]
            L.append("    end")
            fill, stroke = C[colour]
            L.append("    style %s fill:%s,stroke:%s" % (gid, fill, stroke))

        arrow = {"doc": "-->", "data": "-.->", "gl": "==>"}
        gl_idx = []
        for i, (a, b, lbl, kind) in enumerate(self.all_arrows()):
            mid = "|%s|" % q(lbl) if lbl else ""
            L.append("    %s %s%s %s" % (nid[a], arrow[kind], mid, nid[b]))
            if kind == "gl":
                gl_idx.append(str(i))
        if gl_idx:
            L.append("    linkStyle %s stroke:%s" % (",".join(gl_idx), C["accounts"][1]))
        return "\n".join(L)

    # ── sinh XML ─────────────────────────────────────────────────────────
    def render(self):
        mx = ET.Element("mxGraphModel", {
            "dx": "1400", "dy": "900", "grid": "1", "gridSize": "10", "guides": "1",
            "tooltips": "1", "connect": "1", "arrows": "1", "fold": "1", "page": "1",
            "pageScale": "1", "pageWidth": "1169", "pageHeight": "826",
            "math": "0", "shadow": "0",
        })
        root = ET.SubElement(mx, "root")
        ET.SubElement(root, "mxCell", {"id": "0"})
        ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

        def cell(cid, value, style, x, y, w, h):
            c = ET.SubElement(root, "mxCell", {
                "id": cid, "value": value, "style": style, "vertex": "1", "parent": "1",
            })
            ET.SubElement(c, "mxGeometry", {
                "x": str(x), "y": str(y), "width": str(w), "height": str(h),
                "as": "geometry",
            })

        lx, ly, lw, lh = self.leg_x, self.leg_y, self.leg_w, self.leg_h
        cell("lg_box", "", "rounded=1;whiteSpace=wrap;html=1;fillColor=#ffffff;"
             "strokeColor=#c7cfdb;strokeWidth=1.5;arcSize=4;", lx, ly, lw, lh)
        cell("lg_head", "Reading the arrows",
             "text;html=1;align=left;verticalAlign=middle;fontSize=14;fontStyle=1;"
             "fontColor=#23262b;", lx + 18, ly + 12, lw - 36, 22)
        for i, (kind, look, label, desc) in enumerate(LEGEND):
            y = ly + 48 + i * LEG_ROW
            cell("lg_l%d" % i, "", "endArrow=none;html=1;" + EDGE_STYLE[kind],
                 lx + 18, y + 20, 56, 0)
            cell("lg_t%d" % i, "<b>%s &#8212; %s</b><br>%s"
                 % (look, label, desc % {"app": self.app}),
                 "text;html=1;whiteSpace=wrap;align=left;verticalAlign=top;fontSize=11;"
                 "fontColor=#5b6675;", lx + 86, y, lw - 104, LEG_ROW - 6)
        cell("lg_note", "Every arrow was checked against the %s %s source code."
             % (self.app, self.version),
             "text;html=1;whiteSpace=wrap;align=left;verticalAlign=middle;fontSize=10;"
             "fontColor=#8a94a3;", lx + 18, ly + lh - 34, lw - 36, 26)

        cell("title", esc(self.title),
             "text;html=1;align=left;verticalAlign=middle;fontSize=22;fontStyle=1;"
             "fontColor=#23262b;", 40, 24, 900, 30)
        cell("subtitle", esc(self.subtitle),
             "text;html=1;align=left;verticalAlign=middle;fontSize=12;fontColor=#5b6675;",
             40, 54, 900, 20)

        # khung module vẽ trước để nằm dưới
        for gid, gtitle, colour, x, y, w, h in self.groups:
            fill, stroke = C[colour]
            cell(gid, esc(gtitle),
                 "rounded=1;whiteSpace=wrap;html=1;fillColor=%s;strokeColor=%s;strokeWidth=1.5;"
                 "verticalAlign=top;align=left;spacingLeft=12;spacingTop=8;arcSize=4;"
                 "fontSize=15;fontStyle=1;fontColor=#23262b;" % (fill, stroke), x, y, w, h)

        for nid, label, colour, x, y, w, h in self.nodes:
            stroke = C[colour][1]
            cell(nid, label,
                 "rounded=1;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=%s;"
                 "strokeWidth=1.4;fontSize=13;fontColor=#23262b;arcSize=14;" % stroke,
                 x, y, w, h)

        geo = {n[0]: (n[3], n[4], n[5], n[6]) for n in self.nodes}
        geo.update({g[0]: (g[3], g[4], g[5], g[6]) for g in self.groups})

        def side_of(a, b):
            """Cạnh nào của a hướng về b: 'R' phải, 'L' trái, 'D' dưới, 'U' trên."""
            ax, ay, aw, ah = geo[a]
            bx, by, bw, bh = geo[b]
            dx = (bx + bw / 2) - (ax + aw / 2)
            dy = (by + bh / 2) - (ay + ah / 2)
            if abs(dx) >= abs(dy):
                return "R" if dx > 0 else "L"
            return "D" if dy > 0 else "U"

        def center(n):
            x, y, w, h = geo[n]
            return x + w / 2, y + h / 2

        all_edges = self.all_arrows()

        # Nhiều mũi tên cùng thoát ra giữa một cạnh thì chúng đè lên nhau. Gom theo
        # (ô, cạnh) rồi rải đều các điểm neo dọc cạnh đó, thứ tự theo vị trí đầu kia
        # để các đường không bắt chéo nhau ngay tại chỗ thoát ra.
        # Gom CẢ đường ra lẫn đường vào của cùng một cạnh vào một rổ: nếu tách hai rổ
        # thì một cạnh vừa có đường ra vừa có đường vào sẽ cùng rơi vào điểm giữa.
        slots = {}
        for i, (a, b, _, _) in enumerate(all_edges):
            slots.setdefault((a, side_of(a, b)), []).append((i, "exit"))
            slots.setdefault((b, side_of(b, a)), []).append((i, "entry"))

        anchor = {i: [.5, .5, .5, .5] for i in range(len(all_edges))}
        for (node, sd), items in slots.items():
            def other(it):
                i, role = it
                return center(all_edges[i][1] if role == "exit" else all_edges[i][0])
            items.sort(key=lambda it: other(it)[1] if sd in "RL" else other(it)[0])
            n = len(items)
            for k, (i, role) in enumerate(items):
                t = round((k + 1) / (n + 1), 3)
                pos = {"R": (1, t), "L": (0, t), "D": (t, 1), "U": (t, 0)}[sd]
                if role == "exit":
                    anchor[i][0], anchor[i][1] = pos
                else:
                    anchor[i][2], anchor[i][3] = pos

        over_y = self.rows[0] - 14      # dải trống giữa phụ đề và hàng khung đầu

        def edge(eid, i, a, b, lbl, kind):
            ex, ey, nx, ny = anchor[i]
            if (a, b) in self.overhead:
                e_side, _, n_side, _ = self.overhead[(a, b)]
                ex, ey = (0, .5) if e_side == "L" else (1, .5)
                nx, ny = (0, .5) if n_side == "L" else (1, .5)
            # lệch bước nhảy đầu tiên để hai đường song song không nằm đè lên nhau
            jetty = 10 + (i % 5) * 7
            e = ET.SubElement(root, "mxCell", {
                "id": eid, "value": esc(lbl),
                "style": ("edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;orthogonalLoop=1;"
                          "jettySize=%d;fontSize=9;fontColor=#5b6675;labelBackgroundColor=#ffffff;"
                          "exitX=%.3f;exitY=%.3f;exitDx=0;exitDy=0;"
                          "entryX=%.3f;entryY=%.3f;entryDx=0;entryDy=0;"
                          % (jetty, ex, ey, nx, ny)) + EDGE_STYLE[kind],
                "edge": "1", "parent": "1", "source": a, "target": b,
            })
            g = ET.SubElement(e, "mxGeometry", {"relative": "1", "as": "geometry"})
            if (a, b) in self.overhead:
                _, gx_a, _, gx_b = self.overhead[(a, b)]
                pts = ET.SubElement(g, "Array", {"as": "points"})
                for gx in (gx_a, gx_b):
                    ET.SubElement(pts, "mxPoint", {"x": str(int(gx)), "y": str(over_y)})

        for i, (a, b, lbl, kind) in enumerate(all_edges):
            assert a in geo, a
            assert b in geo, b
            edge("e%d" % i, i, a, b, lbl, kind)

        return mx

    # ── đối chiếu source ─────────────────────────────────────────────────
    def check_evidence(self):
        """Grep lại từng mũi tên trong source đang cài.

        Trả về danh sách (nguồn, đích, loại, nghĩa, "file:dòng" hoặc None).
        """
        label = self.labels()
        rows = []
        for a, b, _lbl, kind in self.all_arrows():
            ev = self.evidence.get((a, b))
            if not ev:
                rows.append((label.get(a, a), label.get(b, b), kind, "", None))
                continue
            rel, pat, note = ev
            hit = None
            full = os.path.join(self.src, rel)
            if os.path.isfile(full):
                with open(full, encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        if re.search(pat, line):
                            hit = "%s:%d" % (rel, i)
                            break
            rows.append((label.get(a, a), label.get(b, b), kind, note, hit))
        return rows

    # ── tài liệu đi kèm ──────────────────────────────────────────────────
    def write_doc(self, rows):
        out = os.path.join(DOCS, self.key + ".md")
        app_dir = os.path.relpath(self.src, os.path.dirname(os.path.dirname(self.src)))
        L = ["# %s" % self.title, ""]
        L.append("Sơ đồ: `%s.drawio` — mở bằng [draw.io](https://app.diagrams.net) hoặc "
                 "extension Draw.io Integration của VS Code. File để XML trần (không nén) "
                 "nên git diff đọc được." % self.key)
        L += ["",
              "Sinh lại: `python3 scripts/build_%s_flowchart.py`" % self.key,
              "Chỉ đối chiếu source, không ghi đè: "
              "`python3 scripts/build_%s_flowchart.py --check`" % self.key,
              "",
              "> Script từ chối ghi đè nếu file .drawio đã được sửa tay. "
              "Muốn bỏ qua thì thêm `--force` (mất hết phần sửa tay).",
              "", "## Sơ đồ", "",
              "Bản mermaid của cùng sơ đồ, để tab Flowchart ở `/dev-tool` vẽ ngay trên trình duyệt. "
              "Bố cục do mermaid tự xếp; bản trình bày chuẩn vẫn là file `.drawio`.", "",
              "```mermaid", self.mermaid(), "```",
              "", "## Ba loại mũi tên", ""]
        for kind, look, title, desc in LEGEND:
            L.append("- **%s — %s** (%s) — %s"
                     % (look, title, KIND_VN[kind], desc % {"app": self.app}))
        L += ["", "## Đối chiếu với source %s %s" % (self.app, self.version), "",
              "Mỗi mũi tên dưới đây lấy từ source đang cài chứ không vẽ theo trí nhớ. "
              "Cột cuối là chỗ chứng minh, tính từ `%s/`." % app_dir, "",
              "| Từ | Đến | Loại | Nghĩa | Bằng chứng |", "| --- | --- | --- | --- | --- |"]
        for a, b, kind, note, hit in sorted(rows, key=lambda r: (r[2], r[0])):
            L.append("| %s | %s | %s | %s | %s |"
                     % (a, b, KIND_VN[kind], note,
                        "`%s`" % hit if hit else "**chưa kiểm được**"))
        if self.quirks:
            L += ["", "## Những chỗ cố ý đặt khác module thật", ""]
            L += ["- %s" % q for q in self.quirks]
        if self.omitted:
            L += ["", "## Có trong %s nhưng cố ý không vẽ" % self.version, "",
                  "Sơ đồ dành cho người quản lý nhìn tổng thể, nên các nhánh phụ sau bị lược bỏ:",
                  ""]
            L += ["- %s — `%s`" % (what, where) for what, where in self.omitted]
        L.append("")
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(L))
        return out


def hash_of(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main(spec, argv=None):
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    rows = spec.check_evidence()
    ok = sum(1 for r in rows if r[4])
    print("đối chiếu source: %d/%d mũi tên có bằng chứng" % (ok, len(rows)))
    for a, b, _k, _n, hit in rows:
        if not hit:
            print("  ! không grep ra bằng chứng: %s -> %s" % (a, b))

    if "--check" in args:
        return 0 if ok == len(rows) else 1

    out = os.path.join(DOCS, spec.key + ".drawio")
    stamp = os.path.join(DOCS, "." + spec.key + ".drawio.sha256")
    if os.path.isfile(out) and "--force" not in args:
        # Người dùng có sửa tay file .drawio thì đừng ghi đè công sức của họ.
        prev = open(stamp).read().strip() if os.path.isfile(stamp) else ""
        if prev and prev != hash_of(out):
            print("\nDỪNG: %s đã bị sửa tay sau lần sinh gần nhất." % os.path.basename(out))
            print("Chạy lại với --force nếu chấp nhận mất phần sửa tay đó.")
            return 1

    body = ET.tostring(spec.render(), encoding="unicode")
    xml = ('<mxfile host="app.diagrams.net" type="device" version="24.7.17">\n'
           '  <diagram id="%s-%s" name="%s %s">\n    %s\n  </diagram>\n'
           '</mxfile>\n' % (spec.key, spec.version, spec.app, spec.version, body))
    with open(out, "w", encoding="utf-8") as f:
        f.write(xml)
    with open(stamp, "w", encoding="utf-8") as f:
        f.write(hash_of(out) + "\n")
    doc = spec.write_doc(rows)
    print("%s: %d khung, %d ô, %d mũi tên, %d KB"
          % (os.path.relpath(out, HERE), len(spec.groups), len(spec.nodes),
             len(spec.all_arrows()), len(xml) // 1024))
    print("%s: bảng đối chiếu %d dòng" % (os.path.relpath(doc, HERE), len(rows)))
    return 0
