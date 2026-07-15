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
        self._sync_photo_names()

    def _sync_photo_names(self):
        """Keep the kg in each photo filename in step with the current Gross.

        The name is only right if the weight was known when the photo was saved.
        In the OCR flow the photo is saved first, and a user who types the weight
        in the grid (or whose OCR was refused) never triggers a rename — the file
        would keep the theoretical Gross from Generate and quietly lie.

        Cheap: the wanted name is compared against the URL already on the row, so
        a list whose names are in step costs zero queries.
        """
        for d in (self.details or []):
            if not d.photo:
                continue
            want = _photo_name(self.name, d.carton_no, d.gross_weight, d.color, d.size)
            if d.photo.rsplit("/", 1)[-1] == want:
                continue
            try:
                new_url = rename_carton_photo(
                    self.name, d.carton_no, d.color, d.size, d.gross_weight
                )
            except Exception:
                continue  # never let a file rename break the save
            if new_url and new_url != d.photo:
                d.db_set("photo", new_url, update_modified=False)

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
            # No Gross yet (not weighed / cleared) means no Net — subtracting the
            # tare from 0 would quietly write a negative weight.
            if gross_to_net:
                d.net_weight = (
                    flt(flt(d.gross_weight) - flt(d.empty_weight), 3)
                    if flt(d.gross_weight) > 0
                    else 0
                )
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
def recalc_weights(doc):
    """Recompute Net from the weight table x pcs, and Gross = Net + tare.

    Rebuilds the weights WITHOUT re-packing, so carton numbers and photos survive
    (Generate would delete them). Needed because "Gross to Net" defines
    net = gross - tare: with no Gross yet that writes net = 0 and the theoretical
    net is gone for good — so it cannot be recovered from the rows, only from the
    weight table. Also lets a corrected weight table be applied to a packed list.

    Only for "Net to Gross": in "Gross to Net" the Net follows the scale, and
    _recalc_totals would immediately overwrite whatever we computed here.
    """
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)
    pl = frappe.get_doc(doc)
    if (pl.weight_mode or "") == "Gross to Net":
        frappe.throw(
            _("Weight Mode is Gross to Net: Net comes from the scale, not from the weight table.")
        )

    weight_map = pl._parse_weight()
    missing = set()
    for d in (pl.details or []):
        lines = (
            pl._parse_contents(d.contents)
            if d.contents
            else [(d.color, d.size, cint(d.pcs))]
        )
        net = 0.0
        for (_c, size, pcs) in lines:
            if size not in weight_map:
                missing.add(size)
            net += flt(weight_map.get(size, 0)) * pcs
        d.net_weight = flt(net, 3)
        d.gross_weight = flt(net + flt(d.empty_weight), 3)
    if missing:
        frappe.throw(
            _(
                "Net Weight per Piece (box 2) has no weight for size(s): {0}. "
                "Check it is tab-separated, one line per size: Size &lt;Tab&gt; Weight."
            ).format(", ".join(sorted(missing)))
        )
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


def _photo_prefix(packing_list, carton_no):
    """Stable prefix of a carton's photo: {No}_{CartonNo}_ (kg comes after, so a
    re-weigh still matches the same carton)."""
    return "{0}_{1}_".format(_clean_name(packing_list), cint(carton_no))


def _photo_name(packing_list, carton_no, gross, color, size):
    """{No}_{CartonNo}_{kg}kg_{Color}_{Size}.jpg — kg right after the carton no."""
    return "{0}{1}kg_{2}_{3}.jpg".format(
        _photo_prefix(packing_list, carton_no),
        f"{flt(gross):.2f}",
        _clean_name(color),
        _clean_name(size),
    )


@frappe.whitelist()
def save_carton_photo(packing_list, carton_no, color, size, image, gross=0):
    """Save a (cropped, resized) carton photo as {No}_{CartonNo}_{kg}kg_{Color}_{Size}.jpg."""
    import base64

    frappe.has_permission("Packing List", "write", doc=packing_list, throw=True)
    m = re.search(r"base64,(.*)$", image or "", re.S)
    if not m:
        frappe.throw(_("Invalid image data"))
    data = base64.b64decode(m.group(1))
    fname = _photo_name(packing_list, carton_no, gross, color, size)
    # Remove any previous photo of the same carton so re-capture doesn't pile up.
    prefix = _photo_prefix(packing_list, carton_no)
    for old in frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Packing List", "attached_to_name": packing_list},
        fields=["name", "file_name"],
        order_by="creation desc",
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
def rename_carton_photo(packing_list, carton_no, color, size, gross):
    """Rename an existing carton photo so the filename carries the current kg.

    Needed when the weight is known only AFTER the photo is saved (OCR flow) or
    when Gross is corrected later. Returns the new file_url, or None if no photo.
    """
    import os

    frappe.has_permission("Packing List", "write", doc=packing_list, throw=True)
    prefix = _photo_prefix(packing_list, carton_no)
    target = None
    for f in frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Packing List", "attached_to_name": packing_list},
        fields=["name", "file_name", "file_url"],
        order_by="creation desc",
    ):
        if (f.file_name or "").startswith(prefix):
            target = f
            break
    if not target:
        return None

    fname = _photo_name(packing_list, carton_no, gross, color, size)
    if target.file_name == fname:
        return target.file_url  # already correct

    folder = frappe.get_site_path("private", "files", "packing_list")
    os.makedirs(folder, exist_ok=True)
    old_disk = frappe.get_site_path((target.file_url or "").lstrip("/"))
    new_disk = os.path.join(folder, fname)
    new_url = "/private/files/packing_list/" + fname
    if os.path.exists(old_disk) and os.path.abspath(old_disk) != os.path.abspath(new_disk):
        if os.path.exists(new_disk):
            os.remove(new_disk)
        os.rename(old_disk, new_disk)
    frappe.db.set_value(
        "File", target.name, {"file_url": new_url, "file_name": fname}, update_modified=False
    )
    return new_url


@frappe.whitelist()
def delete_all_photos(packing_list):
    """Delete every carton photo of a Packing List.

    Removes the File records (which deletes the file on disk), clears the photo
    link on each detail row, and sweeps any stray file left in the folder for
    this packing list (orphans from an interrupted save).
    """
    import glob
    import os

    frappe.has_permission("Packing List", "write", doc=packing_list, throw=True)
    doc = frappe.get_doc("Packing List", packing_list)

    # 1) File records attached to this document (File.on_trash removes the disk file).
    deleted = 0
    for f in frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Packing List", "attached_to_name": packing_list},
        fields=["name"],
        order_by="creation desc",
    ):
        try:
            frappe.delete_doc("File", f.name, ignore_permissions=True, force=True)
            deleted += 1
        except Exception:
            pass

    # 2) Clear the link on the rows.
    for d in (doc.details or []):
        if d.photo:
            frappe.db.set_value(
                "Packing List Detail", d.name, "photo", "", update_modified=False
            )

    # 3) Sweep leftovers on disk: "{No}_" prefix is unique per packing list.
    swept = 0
    folder = frappe.get_site_path("private", "files", "packing_list")
    for p in glob.glob(os.path.join(folder, "{0}_*".format(_clean_name(packing_list)))):
        try:
            os.remove(p)
            swept += 1
        except Exception:
            pass

    return {"deleted": deleted, "swept": swept}


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
            # Name each zip entry from the CURRENT row data, so the kg is always
            # up to date even if the stored File was named before weighing.
            entry = _photo_name(doc.name, d.carton_no, d.gross_weight, d.color, d.size)
            z.writestr(entry, content)
            count += 1
    if not count:
        frappe.throw(_("No carton photos to download"))
    frappe.response["filename"] = "{0}_photos.zip".format(doc.name)
    frappe.response["filecontent"] = buf.getvalue()
    frappe.response["type"] = "download"


# ---------------------------------------------------------------------- #
# Scale OCR (red 7-segment display) — ssocr + image pipeline
#
# Robustness comes from three things, all optional/fallback-safe:
#   roi       – caller-supplied display box (fixed station calibrates once)
#   ensemble  – several ssocr variants + majority vote (fixes the weak '7')
#   expected  – theoretical gross from the packing data, used as an anchor
# ---------------------------------------------------------------------- #
SSOCR_THRESHOLDS = (50, 30, 70)
SSOCR_ANGLES = (0, -3, 3)
DIGIT_HEIGHT = 150  # normalise digit size so ssocr sees a consistent scale
# Below this many source pixels the digits carry too little information to read:
# upscaling cannot invent detail, and ssocr then returns confident garbage.
# Measured on real photos: 12-30px -> nonsense; a close-up (~250px) -> exact.
MIN_DIGIT_PX = 40


def _parse_roi(roi):
    """Normalised {x,y,w,h} in 0..1 → clamped dict, or None if unusable."""
    if not roi:
        return None
    if isinstance(roi, str):
        try:
            roi = frappe.parse_json(roi)
        except Exception:
            return None
    if not isinstance(roi, dict):
        return None
    x, y = flt(roi.get("x")), flt(roi.get("y"))
    w, h = flt(roi.get("w")), flt(roi.get("h"))
    x = max(0.0, min(1.0, x))
    y = max(0.0, min(1.0, y))
    w = min(w, 1.0 - x)
    h = min(h, 1.0 - y)
    if w <= 0.02 or h <= 0.02:  # too small to be a real selection
        return None
    return {"x": x, "y": y, "w": w, "h": h}


def _expected_gross(packing_list, carton_no):
    """Theoretical gross of a carton = Σ(pcs × net/size) + tare.

    Derived from the packing data (weight_text + the carton's lines), so it is
    independent of whatever is currently typed in gross_weight. Used only as a
    sanity anchor — never as the answer. Returns None when not derivable.
    """
    if not packing_list or not carton_no:
        return None
    try:
        doc = frappe.get_doc("Packing List", packing_list)
        row = next(
            (d for d in (doc.details or []) if cint(d.carton_no) == cint(carton_no)), None
        )
        if not row:
            return None
        wmap = doc._parse_weight()
        if not wmap:
            return None
        lines = (
            doc._parse_contents(row.contents)
            if row.contents
            else [(row.color, row.size, cint(row.pcs))]
        )
        net = sum(flt(wmap.get(s, 0)) * p for (_c, s, p) in lines)
        if net <= 0:
            return None
        return flt(net + flt(row.empty_weight), 3)
    except Exception:
        return None


def _red_mask(im):
    """Bright-red LED pixels only: redness = R - (G+B)/2."""
    import numpy as np

    a = np.asarray(im).astype(int)
    red = a[:, :, 0] - (a[:, :, 1] + a[:, :, 2]) // 2
    return red > 100


def _column_runs(region, frac=0.05):
    """Column runs of lit pixels: one run per digit (gaps separate the digits)."""
    colsum = region.sum(0)
    active = colsum > (region.shape[0] * frac)
    runs, start = [], None
    for i, v in enumerate(list(active) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i))
            start = None
    return runs


def _digit_runs(region):
    """Runs that are really digits, judged by HEIGHT — never by pixel count.

    A '1' lights only two segments, so it has few pixels but still spans the full
    digit height. Trimming by pixel count therefore ate leading ones and turned
    "11.79" into "179" (= 1.79). Noise specks and the decimal point are short, so
    height separates them cleanly from digits.
    """
    import numpy as np

    h = region.shape[0]
    out = []
    for (a, b) in _column_runs(region):
        rows = np.where(region[:, a:b].any(1))[0]
        if len(rows) and (rows.max() - rows.min() + 1) >= h * 0.5:
            out.append((a, b))
    return out


def _trim_columns(region):
    """Crop the strip to the digits, dropping specks / the decimal point."""
    runs = _digit_runs(region)
    if not runs:
        return None
    x0, x1 = min(a for a, b in runs), max(b for a, b in runs)
    return region[:, x0:x1]


def _digit_regions(mask, max_n=6):
    """Candidate digit strips, largest red cluster first.

    The display is NOT always the largest red thing in the frame — a warehouse
    has fire extinguishers, PCCC boxes, signs and red pipes (measured: such a
    photo has 5x more red pixels than the display alone). So hand back several
    candidates and let the caller keep the one that actually reads as digits.

    The dilation that glues the digits into one blob MUST scale with the image:
    the gap between digits grows with resolution, so a fixed 10px bridge silently
    stopped reaching on sharp photos — the number split into pieces, the biggest
    piece won, and "12.53" came back as "1.25". Measured: at 900x1600 the strip
    held 4 cells, the same shot at 2250x4000 held 3.
    """
    import numpy as np
    from scipy import ndimage as ndi

    # ~1% of the short side: 9 px at 900px wide, 22 px at 2250, 38 px at 4K.
    iters = max(6, int(round(min(mask.shape) / 100.0)))
    labels, n = ndi.label(ndi.binary_dilation(mask, iterations=iters))
    if n == 0:
        return []
    sizes = ndi.sum(mask, labels, np.arange(1, n + 1))
    out = []
    for idx in np.argsort(sizes)[::-1][:max_n]:
        if sizes[idx] < 40:
            continue
        core = mask & (labels == int(idx) + 1)
        ys0, xs0 = np.where(core)
        if not len(ys0):
            continue
        region = core[ys0.min(): ys0.max() + 1, xs0.min(): xs0.max() + 1]
        trimmed = _trim_columns(region)
        if trimmed is not None and trimmed.size:
            out.append(trimmed)
    return out


def _prep_image(sub, closing=False, angle=0):
    """Digit strip (bool) → PNG-ready image for ssocr (black digits on white).

    closing repairs broken LED strokes (the usual cause of 7→1 / 8→0);
    angle compensates a slightly tilted shot.
    """
    import numpy as np
    from PIL import Image, ImageOps
    from scipy import ndimage as ndi

    ys = np.where(sub.any(1))[0]
    if not len(ys):
        return None
    mono = (sub[ys.min(): ys.max() + 1] * 255).astype("uint8")
    img = Image.fromarray(mono)
    if img.height < 4 or img.width < 4:
        return None
    img = img.resize(
        (max(1, round(img.width * DIGIT_HEIGHT / img.height)), DIGIT_HEIGHT), Image.NEAREST
    )
    if angle:
        img = img.rotate(angle, resample=Image.BILINEAR, expand=True, fillcolor=0)
    if closing:
        arr = np.asarray(img) > 127
        arr = ndi.binary_closing(arr, structure=np.ones((3, 3)), iterations=2)
        img = Image.fromarray((arr * 255).astype("uint8"))
    padded = Image.new("L", (img.width + 40, img.height + 40), 0)
    padded.paste(img, (20, 20))
    return ImageOps.invert(padded)


def _count_digit_cells(sub):
    """How many digits are lit, counted from the gaps between them.

    Self-contained — no need to know the expected weight. This is what catches the
    dangerous failure: ssocr can return FEWER digits than are lit and still look
    perfectly clean ("1253" -> "125" turns 12.53 into 1.25). A clean-text check
    cannot see a MISSING character; the geometry can.

    Measured on real photos: "394" -> 3 runs [27,27,27]; "12.53" -> 4 runs
    [9,24,19,21] (the "1" is the narrow one). Counted by height like _digit_runs,
    so a thin '1' counts and the decimal point does not.
    """
    return len(_digit_runs(sub))


def _ssocr_read(img, threshold, ndigits=-1):
    """Run ssocr on a prepared image; '' on any failure.

    ndigits pins how many digits to find (-d): forcing the real count stops ssocr
    from quietly settling for fewer. -1 lets it guess.
    """
    import os
    import subprocess
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".png")
    try:
        os.close(fd)
        img.save(path)
        out = subprocess.run(
            ["ssocr", "-d", str(ndigits), "-t", str(threshold), "remove_isolated", path],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return (out.stdout or "").strip()
    except Exception:
        return ""
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def _value_of(digits, dec):
    return float(digits) / (10 ** dec) if dec > 0 else float(digits)


def _plausible(value, expected):
    """A reading is plausible when it is in the same ballpark as the theory.
    Wide band on purpose: it must catch 10x/decimal blunders, not small drift.
    """
    if not expected:
        return True
    return expected * 0.6 <= value <= expected * 1.5


def _read_strip(sub, dec, expected):
    """OCR one candidate digit strip. Returns a result dict, or None.

    Correctness rests on the DIGIT COUNT taken from the geometry, never on the
    expected weight: most lists are filled Gross-first (net derived from it), so
    the theoretical gross is often absent or rough and must not be load-bearing.
    """
    ncells = _count_digit_cells(sub)
    if ncells < 2 or ncells > 6:
        return None  # not a weight reading

    def attempt(closing, angle, thr):
        """Digits ONLY when ssocr read every character AND every lit cell.

        Two silent ways to be wrong:
          '9y2'  -> stripped to '92'   (0.92 instead of 9.42)
          '1253' -> read as '125'      (1.25 instead of 12.53)
        Clean-text catches the first; only the cell count catches the second —
        a clean string cannot reveal a MISSING character.
        """
        img = _prep_image(sub, closing, angle)
        if img is None:
            return None, None
        raw = _ssocr_read(img, thr, ncells)
        if not raw or not re.fullmatch(r"[0-9.]+", raw):
            return None, raw
        digits = re.sub(r"\D", "", raw)
        return (digits if len(digits) == ncells else None), raw

    # Fast path: a good shot reads cleanly on the first variant.
    digits, raw = attempt(True, 0, SSOCR_THRESHOLDS[0])
    if digits:
        return {
            "ok": True, "value": _value_of(digits, dec), "digits": digits, "raw": raw,
            "confident": True, "votes": 1, "cells": ncells, "expected": expected,
        }

    # Ensemble: vary stroke repair / tilt / threshold, then vote (clean reads only).
    votes = {}
    for closing in (True, False):
        for angle in SSOCR_ANGLES:
            for thr in SSOCR_THRESHOLDS:
                d, r = attempt(closing, angle, thr)
                if not d:
                    continue
                v = votes.setdefault(d, {"n": 0, "raw": r})
                v["n"] += 1
    if not votes:
        return None

    # Most-voted wins. The candidates already all have the right number of digits,
    # so no weight prior is needed to choose between them.
    digits, v = max(votes.items(), key=lambda it: it[1]["n"])
    return {
        "ok": True,
        "value": _value_of(digits, dec),
        "digits": digits,
        "raw": v["raw"],
        "confident": bool(v["n"] >= 2),
        "votes": v["n"],
        "cells": ncells,
        "expected": expected,
    }


def _ocr_image(im, dec, expected):
    """Full pipeline on one image. Returns a result dict, or None if unreadable.

    Tries each red cluster (biggest first) instead of betting on the largest one:
    in a warehouse the biggest red blob is often a fire extinguisher / PCCC box,
    not the display. Shape gates reject non-digit blobs before ssocr can turn
    them into confident nonsense.
    """
    mask = _red_mask(im)
    if mask.sum() < 40:
        return None
    diag = None  # first useful diagnosis, reported only if nothing reads
    for sub in _digit_regions(mask):
        # Too few pixels -> upscaling cannot invent detail; ask for a closer shot.
        if sub.shape[0] < MIN_DIGIT_PX:
            diag = diag or {
                "ok": False, "value": None, "raw": "", "reason": "too_small",
                "digit_px": int(sub.shape[0]), "need_px": MIN_DIGIT_PX, "expected": expected,
            }
            continue
        # A weight reading (>=2 seven-segment digits) is always wider than tall.
        if sub.shape[1] < sub.shape[0] * 1.2:
            diag = diag or {
                "ok": False, "value": None, "raw": "", "reason": "not_a_display",
                "expected": expected,
            }
            continue
        res = _read_strip(sub, dec, expected)
        if res:
            return res
    return diag


@frappe.whitelist()
def read_scale_ocr(image, decimals=2, roi=None, packing_list=None, carton_no=None):
    """Read the red 7-segment scale display and return the weight in kg.

    decimals is fixed by the scale (2 by default): ssocr reports digits only, so
    "943" → 9.43. roi/packing_list/carton_no are optional; without them this
    behaves exactly like the original full-frame reader.
    """
    import base64
    import io
    import shutil

    from PIL import Image

    if not shutil.which("ssocr"):
        frappe.throw(_("ssocr is not installed on the server (sudo apt-get install ssocr)."))
    m = re.search(r"base64,(.*)$", image or "", re.S)
    if not m:
        frappe.throw(_("Invalid image data"))

    im = Image.open(io.BytesIO(base64.b64decode(m.group(1)))).convert("RGB")
    dec = cint(decimals)
    expected = _expected_gross(packing_list, carton_no)

    # Try the calibrated display box first, then the whole frame as a fallback,
    # so a stale/misplaced ROI can never make things worse than before.
    tries = []
    r = _parse_roi(roi)
    if r:
        W, H = im.size
        box = (
            int(r["x"] * W), int(r["y"] * H),
            int((r["x"] + r["w"]) * W), int((r["y"] + r["h"]) * H),
        )
        if box[2] - box[0] >= 20 and box[3] - box[1] >= 20:
            tries.append(im.crop(box))
    tries.append(im)

    # A successful read wins immediately; otherwise keep the last diagnosis (e.g.
    # "too_small") but still let the next attempt try — a misplaced ROI must never
    # stop the full-frame fallback.
    last = None
    for t_im in tries:
        res = _ocr_image(t_im, dec, expected)
        if res and res.get("ok"):
            return res
        last = res or last
    return last or {"ok": False, "value": None, "raw": "", "expected": expected}
