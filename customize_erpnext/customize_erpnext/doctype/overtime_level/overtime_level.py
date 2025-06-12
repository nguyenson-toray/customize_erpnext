# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

# import frappe
import frappe
from frappe.model.document import Document
from frappe.utils import flt


class OvertimeLevel(Document):
	def validate(self):
		# Xử lý rate_multiplier để hỗ trợ cả dấu chấm và phẩy
		if self.rate_multiplier:
			# Chuyển đổi string thành float, hỗ trợ cả "1.5" và "1,5"
			if isinstance(self.rate_multiplier, str):
				# Thay dấu phẩy bằng dấu chấm nếu cần
				rate_str = str(self.rate_multiplier).replace(',', '.')
				self.rate_multiplier = flt(rate_str)
			else:
				self.rate_multiplier = flt(self.rate_multiplier)
				
		# Validation cho các field float khác
		if self.min_hours:
			self.min_hours = flt(self.min_hours)
		if self.max_hours:
			self.max_hours = flt(self.max_hours)
		if self.default_hours:
			self.default_hours = flt(self.default_hours)
		if self.max_per_week:
			self.max_per_week = flt(self.max_per_week)