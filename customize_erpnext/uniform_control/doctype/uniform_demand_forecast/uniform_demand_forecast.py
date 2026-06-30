import frappe
from frappe.model.document import Document
from frappe.utils import cint


class UniformDemandForecast(Document):
    def validate(self):
        if not self.warehouse:
            self.warehouse = frappe.db.get_single_value("Uniform Setting", "uniform_warehouse")
        # Totals stay in sync with manual edits to forecast_qty
        total_forecast = total_shortfall = 0
        for row in self.items or []:
            total_forecast += cint(row.forecast_qty)
            total_shortfall += max(0, cint(row.forecast_qty) - cint(row.current_stock))
        self.total_forecast_qty = total_forecast
        self.total_shortfall = total_shortfall
