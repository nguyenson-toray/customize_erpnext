import frappe
from frappe import _
from frappe.model.document import Document


class UniformRule(Document):
    def validate(self):
        # The category drives how an item is resolved, so the item must match
        # the category's shape (moved here from Uniform Setting).
        if not self.item or not self.category:
            return
        has_variants = frappe.db.get_value("Item", self.item, "has_variants")
        variant_of = frappe.db.get_value("Item", self.item, "variant_of")
        if self.category in ("Shirt", "Shoe") and not has_variants:
            frappe.throw(_("{0} item must be a template (has variants), got {1}.").format(
                self.category, self.item))
        elif self.category == "Cap" and not variant_of:
            frappe.throw(_("Cap item must be an exact variant, got template {0}.").format(self.item))
        elif self.category == "Bottle" and has_variants:
            frappe.throw(_("Bottle item must be a single stock item, got template {0}.").format(self.item))

    def on_update(self):
        queue_tracking_refresh()

    def on_trash(self):
        queue_tracking_refresh()


def queue_tracking_refresh():
    """A rule change can move items and reissue cycles: re-sync every profile
    (Shirt / Cap without Manual Override, next due date, status) in the
    background once the change is committed. Idempotent, so repeated edits just
    run it again."""
    frappe.enqueue(
        "customize_erpnext.uniform_control.api.uniform_scheduler.run_tracking_refresh",
        queue="long",
        enqueue_after_commit=True,
    )
