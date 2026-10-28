# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from customize_erpnext.employee_portal import payslip_structure as pss
from customize_erpnext.employee_portal.utils import code_key, validate_period

ROLES = ("CnB", "System Manager")
QUEUE_THRESHOLD = 150


class TIQNPayslipStructure(Document):
	"""Lines of the payslip from `valid_from` until the next structure (see
	employee_portal/payslip_structure.py). Changing the lines of a month = Duplicate the
	previous structure, edit it, give it a new Valid From Period.

	Once payslips use a structure only the labels and the formula text can change -
	their snapshot keeps the old ones until "Apply Labels to Payslips".
	"""

	def validate(self):
		try:
			self.valid_from = validate_period(self.valid_from)
		except frappe.ValidationError:
			frappe.throw(_("Valid From Period must look like YYYY-MM."))
		for row in self.lines:
			pss.clean_line(row)
		self.lines.sort(key=lambda r: code_key(r.code) if pss.CODE_FORMAT.match(r.code or "") else [10**9])
		for i, row in enumerate(self.lines, start=1):
			row.idx = i
		pss.validate_lines(self.lines)
		self.block_locked_changes()
		self.block_periods_taken()

	def used(self):
		return not self.is_new() and frappe.db.exists(pss.PAYSLIP_DT, {"structure": self.name})

	def block_locked_changes(self):
		if not self.used():
			return
		before = self.get_doc_before_save()
		if before and (
			before.valid_from != self.valid_from
			or pss.structural_signature(before.lines) != pss.structural_signature(self.lines)
		):
			frappe.throw(
				_(
					"Payslips already use this structure: only the labels and the formula text can change. "
					"To add, remove or renumber lines, Duplicate it with a new Valid From Period "
					"(or delete the Draft payslips of its periods first)."
				)
			)

	def block_periods_taken(self):
		"""A new structure must not take over periods that already have payslips of another
		one - re-uploading a correction for one employee would then mix two structures."""
		if not (self.is_new() or self.has_value_changed("valid_from")):
			return
		next_from = frappe.db.get_value(
			pss.STRUCTURE_DT,
			{"valid_from": (">", self.valid_from), "name": ("!=", self.name or "")},
			"valid_from",
			order_by="valid_from asc",
		)
		# Payslips without a structure (before the migration patch fills them) take no period.
		filters = [["period", ">=", self.valid_from], ["structure", "is", "set"], ["structure", "!=", self.name or ""]]
		if next_from:
			filters.append(["period", "<", next_from])
		taken = sorted(frappe.get_all(pss.PAYSLIP_DT, filters, pluck="period", distinct=True))
		if taken:
			frappe.throw(
				_("Periods {0} already have payslips of another structure. Choose a later Valid From Period.").format(
					", ".join(taken)
				)
			)


@frappe.whitelist(methods=["GET"])
def get_label_changes(name):
	frappe.only_for(ROLES)
	changes = pss.label_changes(name)
	return {
		"payslips": frappe.db.count(pss.PAYSLIP_DT, {"structure": name}),
		"changes": [
			{"code": c, "field": frappe.get_meta("TIQN Payslip Structure Line").get_label(f), "old": o, "new": n, "payslips": k}
			for c, f, o, n, k in changes
		],
	}


@frappe.whitelist(methods=["POST"])
def apply_labels(name):
	"""Labels / formula text of the structure -> the snapshot of its payslips (Published
	included). Numbers, published_on and notifications are left alone."""
	frappe.only_for(ROLES)
	doc = frappe.get_doc(pss.STRUCTURE_DT, name)
	doc.check_permission("write")
	count = frappe.db.count(pss.PAYSLIP_DT, {"structure": name})
	if count > QUEUE_THRESHOLD and not frappe.flags.in_test:
		frappe.enqueue(_apply_labels_job, queue="long", timeout=1800, name=name, user=frappe.session.user)
		return {"queued": True, "payslips": count}
	return {"queued": False, "changed": _apply_labels_job(name, frappe.session.user)}


def _apply_labels_job(name, user):
	changed = pss.apply_labels(name)
	frappe.get_doc(pss.STRUCTURE_DT, name).add_comment(
		"Info", _("Labels applied to {0} payslip(s) by {1}.").format(changed, user)
	)
	if not frappe.flags.in_test:
		frappe.db.commit()
		frappe.publish_realtime("payslip_labels_applied", {"name": name, "changed": changed}, user=user, after_commit=True)
	return changed
