import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate

from customize_erpnext.uniform_control.utils import get_item_available_qty


class UniformDemandForecast(Document):
    def validate(self):
        if not self.warehouse:
            self.warehouse = frappe.db.get_single_value("Uniform Setting", "uniform_warehouse")
        # Dates only matter for Re-issue / Both (hidden in New Hires)
        if self.mode in ("Re-issue", "Both"):
            if self.from_date and self.to_date and getdate(self.to_date) < getdate(self.from_date):
                frappe.throw(_("To Date ({0}) cannot be before From Date ({1}).").format(
                    self.to_date, self.from_date))
            if self.to_date and getdate(self.to_date) < getdate(frappe.utils.today()):
                frappe.msgprint(_("To Date is in the past — re-issue demand may be empty."),
                                indicator="orange", alert=True)
        # Block duplicate designations in the recruitment plan (would double-count)
        seen, dups = set(), []
        for row in self.lines or []:
            if row.designation and row.designation in seen:
                dups.append(row.designation)
            seen.add(row.designation)
        if dups:
            frappe.throw(
                _("Duplicate designation(s) in the Recruitment Plan: {0}. "
                  "Enter each designation only once (combine the headcount).").format(
                    ", ".join(sorted(set(dups)))))
        # Refresh current stock so shortfall stays accurate on every save (L4),
        # then keep totals in sync with manual edits to forecast_qty.
        # est_for_leavers is stored NEGATIVE; row Total = forecast_qty + est;
        # Shortfall follows the Total (net) figure.
        total_forecast = total_est = total_shortfall = 0
        for row in self.items or []:
            if self.warehouse and row.item_code:
                row.current_stock = int(get_item_available_qty(row.item_code, self.warehouse))
            row.total_qty = cint(row.forecast_qty) + cint(row.est_for_leavers)
            total_forecast += cint(row.forecast_qty)
            total_est += cint(row.est_for_leavers)
            total_shortfall += max(0, cint(row.total_qty) - cint(row.current_stock))
        self.total_forecast_qty = total_forecast
        self.total_est_for_leavers = total_est
        self.total_shortfall = total_shortfall
