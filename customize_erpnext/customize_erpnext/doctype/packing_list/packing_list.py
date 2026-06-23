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
        # Contents is only kept for mixed cartons; clear it on non-mixed rows
        # (also cleans up rows generated before this rule).
        for d in rows:
            if not self._is_mixed(d):
                d.contents = ""
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
        boxes, _by_label = self._get_boxes()
        big, small = self._big_small(boxes)
        cap = big["cap"]  # a full carton is packed in the larger box
        threshold = cint(self.small_carton_threshold)

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
            cartons.extend(self._combine_leftovers(leftovers, cap, mode))

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
            "cbm": box["cbm"],
            "carton_type": box["label"],
        }

    def _combine_leftovers(self, leftovers, cap, mode):
        """Combine leftover remainders into mixed cartons (single box).

        Each whole (color, size) remainder is placed into one carton using
        First-Fit-Decreasing, so a size's leftover is never split across cartons
        (different sizes/colors may still share a carton). The grouping key
        constrains what may share a carton:
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
            # carton with room.
            pieces = sorted(items, key=lambda x: x[2], reverse=True)
            bins = []  # each: {"remaining": int, "lines": [(color, size, pcs)]}
            for (color, size, rem) in pieces:
                target = next((b for b in bins if b["remaining"] >= rem), None)
                if target is None:
                    target = {"remaining": cap, "lines": []}
                    bins.append(target)
                target["lines"].append((color, size, rem))
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
def generate_detail(doc):
    """Build carton rows + totals from the (possibly unsaved) form data.

    Returns plain data; the client applies it to the form so it works before
    the document is saved.
    """
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)

    pl = frappe.get_doc(doc)
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
