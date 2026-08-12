import frappe
from frappe import _


def _get_template_and_color(item_code):
    """Return (template_item_name, color) for a variant item.

    template_item_name = item_name of the template (variant_of) — the manufacturer's product code.
    color = value of the Color variant attribute (empty string if the item has none).
    """
    item = frappe.get_doc("Item", item_code)

    if item.variant_of:
        template_name = frappe.db.get_value("Item", item.variant_of, "item_name")
    else:
        template_name = item.item_name

    color = ""
    for attr in item.attributes:
        if attr.attribute == "Color":
            color = attr.attribute_value
            break

    return template_name, color


@frappe.whitelist()
def get_batch_id_components(item_code):
    frappe.has_permission("Item", "read", doc=item_code, throw=True)
    template_name, color = _get_template_and_color(item_code)
    return {"template_name": template_name, "color": color}


def _clean(value):
    """Lot/roll are kept exactly as entered (no zero-padding); just trim whitespace."""
    if value is None:
        return ""
    return str(value).strip()


def build_batch_id(template_name, color, lot, roll):
    """batch_id = {template}|{color}|{lot}|{roll} (single pipe). Color omitted if empty."""
    lot, roll = _clean(lot), _clean(roll)
    if color:
        return f"{template_name}|{color}|{lot}|{roll}"
    return f"{template_name}|{lot}|{roll}"


def set_batch_defaults(doc, method=None):
    """Batch before_insert hook.

    - Always populate `custom_color` from the item's Color attribute.
    - If `batch_id` is empty (e.g. Excel/Data Import) but item + lot + roll are present,
      auto-generate `batch_id` using the agreed rule so naming (autoname: field:batch_id) works.
      Runs before set_new_name(), so the generated batch_id becomes the Batch name.
    """
    if not doc.item:
        return

    doc.batch_id = _clean(doc.batch_id)

    template_name, color = _get_template_and_color(doc.item)

    if color:
        doc.custom_color = color

    if doc.batch_id:
        return

    lot, roll = _clean(doc.get("custom_lot_number")), _clean(doc.get("custom_roll_number"))

    if not lot and not roll:
        # Batches auto-created from documents (e.g. Purchase Receipt) legitimately
        # have no lot/roll — let ERPNext's naming series / hash naming handle them.
        return

    if not lot or not roll:
        frappe.throw(
            _("Cannot generate Batch ID: both Lot Number and Roll Number are required (Lot: {0}, Roll: {1})").format(
                lot or "—", roll or "—"
            )
        )

    if "|" in lot or "|" in roll:
        frappe.throw(_("Lot Number and Roll Number must not contain the character |"))

    if not template_name:
        frappe.throw(_("Cannot generate Batch ID: Item Name is empty for Item {0}").format(doc.item))

    batch_id = build_batch_id(template_name, color, lot, roll)

    if frappe.db.exists("Batch", batch_id):
        frappe.throw(_("Batch {0} already exists (Lot {1}, Roll {2})").format(batch_id, lot, roll))

    doc.batch_id = batch_id
