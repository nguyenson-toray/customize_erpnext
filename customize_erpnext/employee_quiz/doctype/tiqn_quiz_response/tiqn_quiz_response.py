# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class TIQNQuizResponse(Document):
	# Created and graded only through customize_erpnext.employee_quiz.service.
	# Deleting one is how HR lets an employee redo the quiz.
	pass
