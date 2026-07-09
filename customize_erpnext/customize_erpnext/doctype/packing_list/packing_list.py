# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import math
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

# Usable (loadable) CBM capacity per container type (configurable here).
CONTAINER_CBM = {
    "20GP": 28.0,
    "40GP": 58.0,
    "42GP": 58.0,
    "40HC": 68.0,
    "45HC": 86.0,
}

class PackingList(Document):
    def validate(self):
        # Show CBM per carton-type row, and recompute totals from whatever rows
        # currently exist so manual edits (e.g. future electronic-scale gross
        # weights) stay consistent.
        for ct in (self.carton_types or []):
            ct.cbm = flt(
                flt(ct.length) * flt(ct.width) * flt(ct.height) / 1_000_000.0, 4
            )
        self._recalc_totals()

    def on_update(self):
        # autoname "format:{no}" only sets the ID on creation; keep the document
        # name in sync when the No is edited later (format: leaves `no` editable).
        if self.no and self.no != self.name:
            from frappe.model.rename_doc import rename_doc

            rename_doc(
                self.doctype,
                self.name,
                self.no,
                force=True,
                ignore_permissions=True,
                show_alert=False,
            )
            self.name = self.no

    # ------------------------------------------------------------------ #
    # Totals
    # ------------------------------------------------------------------ #
    def _recalc_totals(self):
        # CBM/net per row are set at generation time (they depend on each size's
        # carton type). Totals are a plain sum, so editing a gross weight (scale)
        # stays consistent without re-generating.
        rows = self.details or []
        gross_to_net = (self.weight_mode or "") == "Gross to Net"
        for d in rows:
            # Contents is only kept for mixed cartons; clear it on non-mixed rows.
            if not self._is_mixed(d):
                d.contents = ""
            # Reverse weight: Net = Gross - empty carton (Gross entered from scale).
            if gross_to_net:
                d.net_weight = flt(flt(d.gross_weight) - flt(d.empty_weight), 3)
        self.total_quantity = sum(cint(d.pcs) for d in rows)
        self.total_carton = len(rows)
        self.total_net_weight = flt(sum(flt(d.net_weight) for d in rows), 3)
        self.total_gross_weight = flt(sum(flt(d.gross_weight) for d in rows), 3)
        self.total_cbm = flt(sum(flt(d.cbm) for d in rows), 4)

        cap = CONTAINER_CBM.get(self.container_type)
        self.total_containers = (
            int(math.ceil(self.total_cbm / cap)) if cap and self.total_cbm else 0
        )

    def get_size_color_summary_html(self):
        """HTML pivot of quantity by size x color (for the print format).

        Computed server-side so it renders in print/PDF (the on-form table is
        built in JS and is not available during server rendering).
        """
        try:
            qty_map, sizes, colors, _sku = self._parse_items()
        except Exception:
            return ""
        if not sizes or not colors:
            return ""

        esc = frappe.utils.escape_html
        num = lambda n: n if n > 0 else "-"  # noqa: E731
        cs = "border:1px solid #000;padding:3px 8px;text-align:center"
        csl = cs + ";text-align:left"
        b = ";font-weight:700"

        col_tot = {s: 0 for s in sizes}
        grand = 0
        h = '<table style="border-collapse:collapse;font-size:12px">'
        h += f'<tr><th style="{csl}{b}">&nbsp;</th>'
        h += "".join(f'<th style="{cs}{b}">{esc(s)}</th>' for s in sizes)
        h += f'<th style="{cs}{b}">{_("Total")}</th></tr>'
        for c in colors:
            rt = 0
            h += f'<tr><td style="{csl}{b}">{esc(c)}</td>'
            for s in sizes:
                v = cint(qty_map.get((c, s), 0))
                rt += v
                col_tot[s] += v
                h += f'<td style="{cs}">{num(v)}</td>'
            grand += rt
            h += f'<td style="{cs}{b}">{num(rt)}</td></tr>'
        h += f'<tr><td style="{csl}{b}">{_("Total")}</td>'
        h += "".join(f'<td style="{cs}{b}">{num(col_tot[s])}</td>' for s in sizes)
        h += f'<td style="{cs}{b}">{num(grand)}</td></tr></table>'
        return h

    # ------------------------------------------------------------------ #
    # Carton generation
    # ------------------------------------------------------------------ #
    def build_cartons(self):
        qty_map, sizes, colors, sku_map = self._parse_items()
        weight_map = self._parse_weight()
        # Warn if the Net Weight table is missing / not tab-separated: sizes with
        # no weight would silently produce Net = 0.
        missing_w = [s for s in sizes if s not in weight_map]
        if missing_w:
            frappe.throw(
                _(
                    "Net Weight per Piece (box 2) has no weight for size(s): {0}. "
                    "Check it is tab-separated, one line per size: Size &lt;Tab&gt; Weight."
                ).format(", ".join(missing_w))
            )
        boxes, _by_label = self._get_boxes()
        big, small = self._big_small(boxes)
        cap = big["cap"]  # a full carton is packed in the larger box
        threshold = cint(self.small_carton_threshold)
        max_sizes = cint(self.max_size_per_mixed_carton) or 999

        cartons = []     # each carton is a list of (color, size, pcs) lines
        leftovers = []   # (color, size, rem)

        # Phase 1 - solid full cartons (1 color + 1 size), color-major then size.
        for color in colors:
            for size in sizes:
                q = cint(qty_map.get((color, size), 0))
                if q <= 0:
                    continue
                full, rem = divmod(q, cap)
                for _i in range(full):
                    cartons.append([(color, size, cap)])
                if rem > 0:
                    leftovers.append((color, size, rem))

        # Phase 2 - leftovers (all in the default box, so no per-box partition).
        mode = self.combine_mode or "No Combine"
        if mode == "No Combine" or not leftovers:
            for (color, size, rem) in leftovers:
                cartons.append([(color, size, rem)])
        else:
            cartons.extend(self._combine_leftovers(leftovers, cap, mode, max_sizes))

        # Assign a box to each carton (larger box for full cartons, smaller box
        # for not-yet-full cartons per the threshold).
        placed = []  # (lines, box)
        for lines in cartons:
            pcs = sum(p for (_c, _s, p) in lines)
            placed.append((lines, self._pick_box(pcs, cap, big, small, threshold)))

        # Order: solid/whole cartons first (by color & size, as built), then the
        # mixed cartons grouped by carton type (carton-type table order). Stable
        # sort keeps the existing order within each group.
        box_rank = {b["label"]: i for i, b in enumerate(boxes)}
        placed.sort(
            key=lambda lb: (
                1 if len(lb[0]) > 1 else 0,
                box_rank.get(lb[1]["label"], 0) if len(lb[0]) > 1 else 0,
            )
        )

        # Write child rows (renumber sequentially in the final order).
        self.set("details", [])
        for idx, (lines, box) in enumerate(placed, start=1):
            self.append("details", self._detail_row(idx, lines, box, sku_map, weight_map))

    def _detail_row(self, idx, lines, box, sku_map, weight_map):
        """Build a Packing List Detail dict from carton lines + its box.

        SKU / UPC / Contents keep one carton per row but list each item on its
        own line (newline). Contents reads "Color-Size: qty Pcs".
        """
        pcs = sum(p for (_c, _s, p) in lines)
        net = sum(flt(weight_map.get(s, 0)) * p for (_c, s, p) in lines)
        sku_list, upc_list, content_list = [], [], []
        for (cl, s, p) in lines:
            sk, up = sku_map.get((cl, s), ("", ""))
            sku_list.append(sk)
            upc_list.append(up)
            content_list.append(f"{cl}-{s}: {p} Pcs")
        if len(lines) == 1:
            color, size, _p = lines[0]
            contents = ""  # Contents is only shown for mixed cartons.
        else:
            # List the distinct colors / sizes (in order of appearance), comma-separated.
            color = ", ".join(dict.fromkeys(l[0] for l in lines))
            size = ", ".join(dict.fromkeys(l[1] for l in lines))
            contents = "\n".join(content_list)
        return {
            "carton_no": idx,
            "color": color,
            "size": size,
            "sku": "\n".join(sku_list),
            "upc": "\n".join(upc_list),
            "contents": contents,
            "pcs": pcs,
            "net_weight": flt(net, 3),
            "gross_weight": flt(net + box["empty"], 3),
            "empty_weight": box["empty"],
            "cbm": box["cbm"],
            "carton_type": box["label"],
        }

    def _combine_leftovers(self, leftovers, cap, mode, max_sizes=999):
        """Combine leftover remainders into mixed cartons (single box).

        Each whole (color, size) remainder is placed into one carton using
        First-Fit-Decreasing, so a size's leftover is never split across cartons.
        A mixed carton may hold at most `max_sizes` distinct sizes. The grouping
        key constrains what may share a carton:
          By Color        -> one color per carton (sizes mixed)
          By Size         -> one size per carton (colors mixed)
          By Color & Size -> anything may be mixed
        """
        def group_key(item):
            color, size, _rem = item
            if mode == "By Color":
                return color
            if mode == "By Size":
                return size
            return "__all__"

        groups = {}
        for item in leftovers:
            groups.setdefault(group_key(item), []).append(item)

        result = []
        for items in groups.values():
            # Largest remainders first, then drop each whole into the first
            # carton with room and within the distinct-size limit.
            pieces = sorted(items, key=lambda x: x[2], reverse=True)
            bins = []  # each: {"remaining": int, "sizes": set, "lines": [...]}
            for (color, size, rem) in pieces:
                target = next(
                    (
                        b
                        for b in bins
                        if b["remaining"] >= rem
                        and (size in b["sizes"] or len(b["sizes"]) < max_sizes)
                    ),
                    None,
                )
                if target is None:
                    target = {"remaining": cap, "sizes": set(), "lines": []}
                    bins.append(target)
                target["lines"].append((color, size, rem))
                target["sizes"].add(size)
                target["remaining"] -= rem
            for b in bins:
                result.append(b["lines"])
        return result

    # ------------------------------------------------------------------ #
    # Carton types & manual mix editing
    # ------------------------------------------------------------------ #
    @staticmethod
    def _box_label(length, width, height):
        return f"{cint(length)}*{cint(width)}*{cint(height)}"

    def _get_boxes(self):
        """Return (boxes, by_label). boxes[0] is the default carton type."""
        rows = self.carton_types or []
        if not rows:
            frappe.throw(_("Add at least one Carton Type"))
        boxes = []
        by_label = {}
        for ct in rows:
            cap = cint(ct.max_items)
            if cap <= 0:
                frappe.throw(_("Max Items/Carton must be greater than 0"))
            box = {
                "label": self._box_label(ct.length, ct.width, ct.height),
                "cap": cap,
                "cbm": flt(flt(ct.length) * flt(ct.width) * flt(ct.height) / 1_000_000.0, 4),
                "empty": flt(ct.empty_weight),
            }
            boxes.append(box)
            by_label.setdefault(box["label"], box)
        return boxes, by_label

    @staticmethod
    def _big_small(boxes):
        """Return (big, small) carton types by volume (CBM). Same object if one."""
        ordered = sorted(boxes, key=lambda b: (b["cbm"], b["cap"]))
        return ordered[-1], ordered[0]

    def _pick_box(self, pcs, cap, big, small, threshold):
        """Larger box for full cartons, smaller box for not-yet-full cartons.

        With a threshold > 0, a carton goes to the small box when pcs <= threshold;
        otherwise the small box is used for any non-full carton that fits it.
        """
        if small is big:
            return big
        limit = threshold if threshold > 0 else small["cap"]
        limit = min(limit, small["cap"])
        return small if (pcs < cap and pcs <= limit) else big

    @staticmethod
    def _is_mixed(detail):
        """A carton is 'mixed' when its Contents holds more than one item line."""
        c = detail.contents or ""
        return "\n" in c or ", " in c

    @staticmethod
    def _parse_contents(contents):
        """Parse 'Color-Size: qty Pcs' lines into [(color, size, pcs), ...].

        Items are newline-separated (older ", " separated values are also handled).
        Sizes never contain '-', so the last '-' separates color from size even if
        the color has dashes.
        """
        lines = []
        for seg in (contents or "").replace(", ", "\n").splitlines():
            seg = seg.strip()
            if not seg:
                continue
            cs, _, after = seg.rpartition(":")
            tokens = after.strip().split()  # "5 Pcs" -> ["5", "Pcs"]
            color, _, size = cs.rpartition("-")
            if color and size and tokens and tokens[0].isdigit():
                lines.append((color.strip(), size.strip(), int(tokens[0])))
        return lines

    def apply_mix_edit(self, cartons):
        """Replace the mixed cartons with a user-edited layout (conservation).

        `cartons` is a list of {"carton_type": label, "lines": [{color, size, pcs}]}.
        Solid/single cartons are kept; the edited mix must hold exactly the same
        pieces as the current mix, and no carton may exceed its box capacity.
        """
        weight_map = self._parse_weight()
        _qty, _sizes, _colors, sku_map = self._parse_items()
        boxes, by_label = self._get_boxes()
        default = boxes[0]

        # Current state: keep non-mixed cartons, collect the mixed pieces pool.
        kept = []  # (lines, box)
        pool = {}
        for d in (self.details or []):
            box = by_label.get(d.carton_type, default)
            if self._is_mixed(d):
                for (c, s, p) in self._parse_contents(d.contents):
                    pool[(c, s)] = pool.get((c, s), 0) + p
            else:
                # Non-mixed cartons have no Contents; rebuild from color/size/pcs.
                kept.append(([(d.color, d.size, cint(d.pcs))], box))

        # Validate the edited cartons.
        new_pool = {}
        new_cartons = []  # (lines, box)
        for c in cartons:
            box = by_label.get(c.get("carton_type"), default)
            lines = []
            total = 0
            for ln in (c.get("lines") or []):
                color = (ln.get("color") or "").strip()
                size = (ln.get("size") or "").strip()
                pcs = cint(ln.get("pcs"))
                if not color or not size or pcs <= 0:
                    continue
                lines.append((color, size, pcs))
                total += pcs
                new_pool[(color, size)] = new_pool.get((color, size), 0) + pcs
            if not lines:
                continue
            if total > box["cap"]:
                frappe.throw(
                    _("A carton has {0} pcs, over the max {1} for {2}").format(
                        total, box["cap"], box["label"]
                    )
                )
            new_cartons.append((lines, box))

        if new_pool != pool:
            diffs = []
            for key in sorted(set(pool) | set(new_pool)):
                a, b = pool.get(key, 0), new_pool.get(key, 0)
                if a != b:
                    diffs.append(f"{key[0]}-{key[1]}: {b}/{a}")
            frappe.throw(
                _("Edited mix must keep the same pieces (placed/needed): {0}").format(
                    ", ".join(diffs)
                )
            )

        # Rebuild: kept cartons first, then the edited mixed cartons.
        self.set("details", [])
        for idx, (lines, box) in enumerate(kept + new_cartons, start=1):
            self.append("details", self._detail_row(idx, lines, box, sku_map, weight_map))

    # ------------------------------------------------------------------ #
    # Parsers (tab-separated; falls back to runs of 2+ spaces)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _cells(line):
        parts = line.split("\t") if "\t" in line else re.split(r"\s{2,}", line.strip())
        return [p.strip() for p in parts]

    def _parse_items(self):
        """Parse the combined Items table (one row per color + size).

        Columns: Color <tab> Size <tab> Quantity <tab> SKU(optional) <tab> UPC(optional).
        Returns (qty_map, sizes, colors, sku_map) where order follows first
        appearance; duplicate (color, size) rows are summed.
        """
        lines = [ln for ln in (self.items_text or "").splitlines() if ln.strip()]
        if not lines:
            frappe.throw(_("Items table is empty"))

        qty_map, sku_map = {}, {}
        sizes, colors = [], []
        for ln in lines:
            cells = self._cells(ln)
            if len(cells) < 3:
                continue
            color, size, qty = cells[0].strip(), cells[1].strip(), cells[2].strip()
            if not color or not size:
                continue
            # Skip a header row like "Color  Size  Quantity  SKU  UPC".
            if color.lower() == "color" or size.lower() == "size":
                continue
            if color not in colors:
                colors.append(color)
            if size not in sizes:
                sizes.append(size)
            qty_map[(color, size)] = qty_map.get((color, size), 0) + cint(qty or 0)
            sku = cells[3].strip() if len(cells) > 3 else ""
            upc = cells[4].strip() if len(cells) > 4 else ""
            if sku or upc:
                sku_map[(color, size)] = (sku, upc)
        if not sizes:
            frappe.throw(_("Items table has no valid rows"))
        return qty_map, sizes, colors, sku_map

    def _parse_weight(self):
        out = {}
        for ln in (self.weight_text or "").splitlines():
            if not ln.strip():
                continue
            cells = self._cells(ln)
            if len(cells) < 2:
                continue
            try:
                out[cells[0]] = float(cells[1])  # non-numeric (header) is skipped
            except ValueError:
                continue
        return out

def _result(pl):
    return {
        "details": [
            {
                "carton_no": d.carton_no,
                "color": d.color,
                "size": d.size,
                "sku": d.sku,
                "upc": d.upc,
                "contents": d.contents,
                "pcs": d.pcs,
                "net_weight": d.net_weight,
                "gross_weight": d.gross_weight,
                "empty_weight": d.empty_weight,
                "cbm": d.cbm,
                "carton_type": d.carton_type,
            }
            for d in pl.details
        ],
        "totals": {
            "total_quantity": pl.total_quantity,
            "total_carton": pl.total_carton,
            "total_containers": pl.total_containers,
            "total_net_weight": pl.total_net_weight,
            "total_gross_weight": pl.total_gross_weight,
            "total_cbm": pl.total_cbm,
        },
    }


@frappe.whitelist()
def generate_detail(doc, force=0):
    """Build carton rows + totals from the (possibly unsaved) form data.

    Returns plain data; the client applies it to the form so it works before
    the document is saved.
    """
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)

    pl = frappe.get_doc(doc)
    photos = [d.get("photo") for d in (pl.details or []) if d.get("photo")]
    if photos and not cint(force):
        frappe.throw(
            _("Cartons already have photos — regenerating would lose them. Delete the photos first."),
            title=_("Photos exist"),
        )
    # Forced regenerate: delete the now-orphaned photo files.
    for url in photos:
        name = frappe.db.get_value("File", {"file_url": url}, "name")
        if name:
            frappe.delete_doc("File", name, ignore_permissions=True, force=True)
    pl.build_cartons()
    pl._recalc_totals()
    return _result(pl)


@frappe.whitelist()
def apply_mix(doc, cartons):
    """Apply a user-edited mixed-carton layout (from the Edit Mix dialog)."""
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)
    if isinstance(cartons, str):
        cartons = frappe.parse_json(cartons)

    pl = frappe.get_doc(doc)
    pl.apply_mix_edit(cartons)
    pl._recalc_totals()
    return _result(pl)


def _clean_name(s):
    return re.sub(r"[^A-Za-z0-9]+", "-", (s or "").strip()).strip("-") or "NA"


@frappe.whitelist()
def save_carton_photo(packing_list, carton_no, color, size, image):
    """Save a (cropped, resized) carton photo as File {No}_{CartonNo}_{Color}_{Size}.jpg."""
    import base64

    frappe.has_permission("Packing List", "write", doc=packing_list, throw=True)
    m = re.search(r"base64,(.*)$", image or "", re.S)
    if not m:
        frappe.throw(_("Invalid image data"))
    data = base64.b64decode(m.group(1))
    fname = "{0}_{1}_{2}_{3}.jpg".format(
        _clean_name(packing_list), cint(carton_no), _clean_name(color), _clean_name(size)
    )
    # Remove any previous photo of the same carton so re-capture doesn't pile up.
    prefix = "{0}_{1}_".format(_clean_name(packing_list), cint(carton_no))
    for old in frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Packing List", "attached_to_name": packing_list},
        fields=["name", "file_name"],
    ):
        if (old.file_name or "").startswith(prefix):
            frappe.delete_doc("File", old.name, ignore_permissions=True, force=True)

    # Let Frappe create the File (flat), then relocate it under
    # private/files/packing_list/ with the exact name.
    import os
    import shutil

    from frappe.utils.file_manager import save_file

    f = save_file(fname, data, "Packing List", packing_list, is_private=1)

    folder = frappe.get_site_path("private", "files", "packing_list")
    os.makedirs(folder, exist_ok=True)
    old_disk = frappe.get_site_path(f.file_url.lstrip("/"))
    new_url = "/private/files/packing_list/" + fname
    new_disk = os.path.join(folder, fname)
    if os.path.abspath(old_disk) != os.path.abspath(new_disk):
        if os.path.exists(new_disk):
            os.remove(new_disk)
        shutil.move(old_disk, new_disk)
    frappe.db.set_value(
        "File", f.name, {"file_url": new_url, "file_name": fname}, update_modified=False
    )
    return new_url


@frappe.whitelist()
def download_all_photos(packing_list):
    """Zip every carton photo of the packing list and stream it as a download."""
    import io
    import zipfile
    from frappe.utils.file_manager import get_file

    frappe.has_permission("Packing List", "read", doc=packing_list, throw=True)
    doc = frappe.get_doc("Packing List", packing_list)
    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d in doc.details:
            url = d.get("photo")
            if not url:
                continue
            try:
                _fname, content = get_file(url)
            except Exception:
                continue
            # Name each zip entry exactly No_CartonNo_Color_Size.jpg.
            entry = "{0}_{1}_{2}_{3}.jpg".format(
                _clean_name(doc.name), cint(d.carton_no), _clean_name(d.color), _clean_name(d.size)
            )
            z.writestr(entry, content)
            count += 1
    if not count:
        frappe.throw(_("No carton photos to download"))
    frappe.response["filename"] = "{0}_photos.zip".format(doc.name)
    frappe.response["filecontent"] = buf.getvalue()
    frappe.response["type"] = "download"


@frappe.whitelist()
def read_scale_ocr(image, decimals=2):
    """Read a red 7-segment scale display (cropped) via ssocr.

    Isolates the red digits (redness = R - (G+B)/2), drops noise specks, then
    runs ssocr and divides by 10**decimals (scales use a fixed decimal place).
    """
    import base64
    import io
    import os
    import shutil
    import subprocess
    import tempfile

    import numpy as np
    from PIL import Image, ImageOps

    if not shutil.which("ssocr"):
        frappe.throw(_("ssocr is not installed on the server (sudo apt-get install ssocr)."))
    m = re.search(r"base64,(.*)$", image or "", re.S)
    if not m:
        frappe.throw(_("Invalid image data"))

    im = Image.open(io.BytesIO(base64.b64decode(m.group(1)))).convert("RGB")
    a = np.asarray(im).astype(int)
    red = a[:, :, 0] - (a[:, :, 1] + a[:, :, 2]) // 2
    mask = red > 100  # bright-red LED pixels only
    if mask.sum() < 40:
        return {"ok": False, "value": None, "raw": ""}

    # Locate the display: dilate to merge the digit strokes, then keep the
    # largest red cluster. Robust to reddish cartons scattered across the frame.
    from scipy import ndimage as ndi

    labels, n = ndi.label(ndi.binary_dilation(mask, iterations=10))
    if n == 0:
        return {"ok": False, "value": None, "raw": ""}
    sizes = ndi.sum(mask, labels, np.arange(1, n + 1))
    core = mask & (labels == int(np.argmax(sizes)) + 1)
    ys0, xs0 = np.where(core)
    region = core[ys0.min(): ys0.max() + 1, xs0.min(): xs0.max() + 1]

    colsum = region.sum(0)
    active = colsum > (region.shape[0] * 0.10)
    runs, start = [], None
    for i, v in enumerate(list(active) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i))
            start = None
    sized = [(s, e, int(colsum[s:e].sum())) for (s, e) in runs]
    if not sized:
        return {"ok": False, "value": None, "raw": ""}
    peak = max(r[2] for r in sized)
    big = [(s, e) for (s, e, sm) in sized if sm > peak * 0.2]  # drop noise specks
    x0, x1 = min(s for s, e in big), max(e for s, e in big)

    sub = region[:, x0:x1]
    ys = np.where(sub.any(1))[0]
    mono = (sub[ys.min(): ys.max() + 1] * 255).astype("uint8")
    img = Image.fromarray(mono)
    # Scale to a consistent digit height so ssocr works regardless of distance.
    new_h = 150
    img = img.resize((max(1, round(img.width * new_h / img.height)), new_h), Image.NEAREST)
    padded = Image.new("L", (img.width + 40, img.height + 40), 0)
    padded.paste(img, (20, 20))
    proc = ImageOps.invert(padded)  # black digits on white for ssocr

    fd, path = tempfile.mkstemp(suffix=".png")
    try:
        os.close(fd)
        proc.save(path)
        out = subprocess.run(
            ["ssocr", "-d", "-1", "-t", "50", "remove_isolated", path],
            capture_output=True,
            text=True,
            timeout=20,
        )
        raw = (out.stdout or "").strip()
        digits = re.sub(r"\D", "", raw)
        if not digits:
            return {"ok": False, "value": None, "raw": raw or (out.stderr or "").strip()}
        dec = cint(decimals)
        value = float(digits) / (10 ** dec) if dec > 0 else float(digits)
        # "confident" only when ssocr recognised every character (no '_').
        confident = re.fullmatch(r"[0-9.]+", raw) is not None
        return {"ok": True, "value": value, "digits": digits, "raw": raw, "confident": confident}
    finally:
        try:
            os.remove(path)
        except Exception:
            pass
