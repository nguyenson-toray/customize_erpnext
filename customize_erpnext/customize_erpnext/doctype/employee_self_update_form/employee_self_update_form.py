# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class EmployeeSelfUpdateForm(Document):
	def before_insert(self):
		self.status = "Pending Review"

	def validate(self):
		if self.status in ("Approved", "Synced"):
			old = self.get_doc_before_save()
			if old and old.status in ("Approved", "Synced"):
				data_fields = [
					"id_card_no", "id_card_date_of_issue", "id_card_place_of_issue",
					"id_card_cmnd_no", "id_card_cmnd_date_of_issue", "id_card_cmnd_place_of_issue",
					"marital_status", "bank_ac_no", "bank_branch",
					"education_level", "university", "major",
					"current_address_province", "current_address_commune",
					"current_address_village", "current_address_full",
					"permanent_address_province", "permanent_address_commune",
					"permanent_address_village", "permanent_address_full",
				]
				for f in data_fields:
					if self.get(f) != old.get(f):
						frappe.throw(
							_("Cannot edit this form after it has been {0}.").format(_(old.status))
						)

		# Auto-assemble addresses from parts
		def _join(*parts):
			return ", ".join(p for p in parts if p)

		self.current_address_full = _join(
			self.current_address_village, self.current_address_commune, self.current_address_province
		)
		self.permanent_address_full = _join(
			self.permanent_address_village, self.permanent_address_commune, self.permanent_address_province
		)
		self.place_of_origin_full = _join(
			self.place_of_origin_village, self.place_of_origin_commune, self.place_of_origin_province
		)
