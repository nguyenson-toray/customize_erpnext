import frappe
from frappe import _
from frappe.model.document import Document


class UniformSetting(Document):
    def validate(self):
        self._validate_rules()

    def _validate_rules(self):
        """Catch rule misconfiguration early — the category drives how an item is
        resolved, so the item must match the category's shape."""
        for r in self.rules or []:
            if not r.item or not r.category:
                continue
            has_variants = frappe.db.get_value("Item", r.item, "has_variants")
            variant_of = frappe.db.get_value("Item", r.item, "variant_of")

            if r.category in ("Shirt", "Shoe"):
                if not has_variants:
                    frappe.throw(_("Row {0}: {1} item must be a template (has variants), got {2}.").format(
                        r.idx, r.category, r.item))
            elif r.category == "Cap":
                if not variant_of:
                    frappe.throw(_("Row {0}: Cap item must be an exact variant, got template {1}.").format(
                        r.idx, r.item))
