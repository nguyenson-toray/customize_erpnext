# File: apps/customize_erpnext/customize_erpnext/override_methods/stock_reconciliation/custom_stock_reconciliation.py

import frappe
from frappe import _
from frappe.utils import flt
from frappe.model.utils import get_fetch_values
from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import StockReconciliation
from erpnext.stock.utils import get_stock_balance

class CustomStockReconciliation(StockReconciliation):
    def validate_data(self): 
        def _get_msg(row_num, msg):
            return _("Row # {0}:").format(row_num + 1) + " " + msg

        self.validation_messages = []
        item_warehouse_combinations = []

        default_currency = frappe.db.get_default("currency")

        for row_num, row in enumerate(self.items):
            # find duplicates - MODIFIED: Added custom_invoice_number and qty to key
            key = [row.item_code, row.warehouse, getattr(row, 'custom_invoice_number', ''), row.qty]
            
            for field in ["serial_no", "batch_no"]:
                if row.get(field):
                    key.append(row.get(field))

            if key in item_warehouse_combinations:
                self.validation_messages.append(
                    _get_msg(row_num, _("Same item, warehouse, invoice number and quantity combination already entered."))
                )
            else:
                item_warehouse_combinations.append(key)

            self.validate_item(row.item_code, row)

            if row.serial_no and not row.qty:
                self.validation_messages.append(
                    _get_msg(
                        row_num,
                        f"Quantity should not be zero for the {bold(row.item_code)} since serial nos are specified",
                    )
                )

            # validate warehouse
            if not frappe.db.get_value("Warehouse", row.warehouse):
                self.validation_messages.append(_get_msg(row_num, _("Warehouse not found in the system")))

            # if both not specified
            if row.qty in ["", None] and row.valuation_rate in ["", None]:
                self.validation_messages.append(
                    _get_msg(row_num, _("Please specify either Quantity or Valuation Rate or both"))
                )

            # do not allow negative quantity
            if flt(row.qty) < 0:
                self.validation_messages.append(_get_msg(row_num, _("Negative Quantity is not allowed")))

            # do not allow negative valuation
            if flt(row.valuation_rate) < 0:
                self.validation_messages.append(
                    _get_msg(row_num, _("Negative Valuation Rate is not allowed"))
                )

            if row.qty and row.valuation_rate in ["", None]:
                row.valuation_rate = get_stock_balance(
                    row.item_code,
                    row.warehouse,
                    self.posting_date,
                    self.posting_time,
                    with_valuation_rate=True,
                )[1]
                if not row.valuation_rate:
                    # try if there is a buying price list in default currency
                    buying_rate = frappe.db.get_value(
                        "Item Price",
                        {"item_code": row.item_code, "buying": 1, "currency": default_currency},
                        "price_list_rate",
                    )
                    if buying_rate:
                        row.valuation_rate = buying_rate
                    else:
                        # get valuation rate from Item
                        row.valuation_rate = frappe.get_value("Item", row.item_code, "valuation_rate")

        # throw all validation messages
        if self.validation_messages:
            for msg in self.validation_messages:
                frappe.msgprint(msg)
            raise frappe.ValidationError(self.validation_messages)