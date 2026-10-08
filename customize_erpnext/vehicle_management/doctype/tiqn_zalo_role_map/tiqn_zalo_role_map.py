# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


# Zalo IDs seen on this site are 19 digits. The floor is set well below that so a
# genuine ID is never refused; it exists only to catch "34"-style placeholders.
MIN_ID_BY_OA_DIGITS = 10


class TIQNZaloRoleMap(Document):
	"""Một tài khoản Zalo = một bản ghi. Đây là bảng DANH TÍNH duy nhất của module.

	DocType `TIQN Driver` cũ đã bỏ (23/09/2026): tài xế giờ chính là một tài khoản Zalo
	được quản lý nâng vai trò và gán xe. Trước đây một người có HAI bản ghi - một Driver
	và một Role Map - và chúng lệch nhau được. Đã lệch thật: ba tài khoản Zalo khác nhau
	cùng trỏ `driver_ref` về một tài xế.

	Mọi người vào app lần đầu là `requester`; quản lý nâng lên `driver` hoặc `dispatcher`.
	"""

	def validate(self):
		self.zalo_user_id = (self.zalo_user_id or "").strip()
		if not self.zalo_user_id:
			frappe.throw(_("Zalo User ID is required"))

		if not self.role:
			self.role = "requester"

		if self.role == "driver" and not self.vehicle:
			frappe.throw(_("Vehicle is required when role is driver"))

		if self.role != "driver":
			# Xe và cờ tổ trưởng chỉ có nghĩa với tài xế. Để sót lại thì bộ lọc
			# "tài xế của xe X" sẽ nhặt phải một requester.
			self.vehicle = None
			self.is_leader = 0

		self.validate_id_by_oa()

	def validate_id_by_oa(self):
		"""Catch a placeholder typed into ID by OA before it reaches openChat().

		🔴 Seen for real 22/09/2026: the dispatcher row was saved with
		`id_by_oa = "34"`. Real Zalo IDs on this site are 19-digit numbers
		(4295057266797901281, 7664780689128284452). A value like "34" is not null,
		so `get_dispatcher_zalo_id()` happily returns it, the Mini App SHOWS the chat
		button, and the button does nothing - the exact silent failure the no-fallback
		rule was written to avoid, except this time the bad value came from the data
		rather than from the code.

		Deliberately a shape check, not a format spec: Zalo does not publish an ID
		length. Digits-only and at least MIN_DIGITS long rejects typos and
		placeholders while leaving every genuine ID alone.
		"""
		self.id_by_oa = (self.id_by_oa or "").strip() or None
		if not self.id_by_oa:
			return

		if not self.id_by_oa.isdigit() or len(self.id_by_oa) < MIN_ID_BY_OA_DIGITS:
			frappe.throw(
				_("ID by OA {0} does not look like a Zalo ID - it should be digits only, "
				  "at least {1} of them. This value comes from getUserInfo().idByOA in the "
				  "Mini App, not typed by hand.").format(self.id_by_oa, MIN_ID_BY_OA_DIGITS)
			)
