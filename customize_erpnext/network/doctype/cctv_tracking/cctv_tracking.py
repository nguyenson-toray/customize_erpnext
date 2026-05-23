import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class CCTVTracking(Document):
    def autoname(self):
        dt = now_datetime()
        nvr_slug = (self.nvr or "NVR").replace(" ", "-")
        self.name = dt.strftime("%y%m%d%H%M") + "-" + nvr_slug
