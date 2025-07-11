# stock_balance_customize.py
# Refactored Stock Balance Report with Invoice Number Support

from operator import itemgetter
from typing import Any, TypedDict
from collections import defaultdict

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder.functions import Coalesce
from frappe.utils import add_days, cint, date_diff, flt, getdate
from frappe.utils.nestedset import get_descendants_of

import erpnext
from erpnext.stock.doctype.inventory_dimension.inventory_dimension import get_inventory_dimensions
from erpnext.stock.doctype.warehouse.warehouse import apply_warehouse_filter
from erpnext.stock.report.stock_ageing.stock_ageing import FIFOSlots, get_average_age
from erpnext.stock.utils import add_additional_uom_columns


class StockBalanceFilter(TypedDict):
    company: str | None
    from_date: str
    to_date: str
    item_group: str | None
    item: str | None
    warehouse: str | None
    warehouse_type: str | None
    include_uom: str | None
    show_stock_ageing_data: bool
    show_variant_attributes: bool
    summary_qty_by_invoice_number: bool
    show_value: bool
    range: str | None


SLEntry = dict[str, Any]


def execute(filters: StockBalanceFilter | None = None):
    return StockBalanceReportCustomized(filters).run()


class StockBalanceReportCustomized:
    def __init__(self, filters: StockBalanceFilter | None) -> None:
        self.filters = filters or {}
        self.from_date = getdate(self.filters.get("from_date"))
        self.to_date = getdate(self.filters.get("to_date"))
        
        self.start_from = None
        self.data = []
        self.columns = []
        self.sle_entries: list[SLEntry] = []
        self.opening_data = frappe._dict({})
        self.company_currency = self._get_company_currency()
        self.float_precision = cint(frappe.db.get_default("float_precision")) or 3
        self.inventory_dimensions = self._get_inventory_dimension_fields()

    def _get_company_currency(self) -> str:
        """Get company currency with fallback"""
        company = self.filters.get("company") or frappe.defaults.get_user_default("Company")
        return erpnext.get_company_currency(company) if company else "VND"

    @staticmethod
    def _get_inventory_dimension_fields():
        """Get inventory dimension fields"""
        return [dimension.fieldname for dimension in get_inventory_dimensions()]

    def run(self):
        """Main execution flow"""
        self._prepare_opening_data_from_closing_balance()
        self._prepare_stock_ledger_entries()
        self._prepare_report_data()
        
        if not self.columns:
            self.columns = self._get_columns()
            
        self._add_additional_uom_columns()
        return self.columns, self.data

    def _prepare_opening_data_from_closing_balance(self) -> None:
        """Load opening data from closing balance if available"""
        closing_balance = self._get_closing_balance()
        if not closing_balance:
            return

        self.start_from = add_days(closing_balance[0].to_date, 1)
        res = frappe.get_doc("Closing Stock Balance", closing_balance[0].name).get_prepared_data()

        for entry in res.data:
            entry = frappe._dict(entry)
            if not self.filters.get("summary_qty_by_invoice_number"):
                group_by_key = self._get_group_by_key(entry)
                if group_by_key not in self.opening_data:
                    self.opening_data[group_by_key] = entry

    def _prepare_report_data(self):
        """Prepare final report data with aging and variant information"""
        self.item_warehouse_map = self._get_item_warehouse_map()
        
        # Generate FIFO queue for aging calculation
        self.filters["show_warehouse_wise_stock"] = True
        item_wise_fifo_queue = CustomizedFIFOSlots(self.filters, self.sle_entries).generate()
        
        # Setup aging ranges if needed
        if self.filters.get("show_stock_ageing_data") and not self.filters.get("range"):
            self.filters["range"] = "180, 360, 720"
        if self.filters.get("range"):
            self.filters["ranges"] = [num.strip() for num in self.filters["range"].split(",") if num.strip().isdigit()]

        # Get variant attributes and reserved stock
        variant_values = self._get_variant_values() if self.filters.get("show_variant_attributes") else {}
        sre_details = self._get_sre_reserved_qty_details()
        
        # Process each item-warehouse combination
        for _key, report_data in self.item_warehouse_map.items():
            self._process_report_row(report_data, item_wise_fifo_queue, variant_values, sre_details)
            
            # Skip items with no balance and no transactions
            if (report_data.bal_qty == 0 and report_data.bal_val == 0 and 
                report_data.in_qty == 0 and report_data.out_qty == 0 and 
                report_data.opening_qty == 0):
                continue
                
            self.data.append(report_data)

    def _process_report_row(self, report_data, item_wise_fifo_queue, variant_values, sre_details):
        """Process individual report row with aging and variant data"""
        # Add variant attributes
        if variant_data := variant_values.get(report_data.item_code):
            cleaned_variant_data = {
                key: str(value) if value not in [None, "", "None", "nan", "null"] else ""
                for key, value in variant_data.items()
            }
            report_data.update(cleaned_variant_data)

        # Calculate aging data
        fifo_key = self._get_fifo_key(report_data)
        if fifo_data := item_wise_fifo_queue.get(fifo_key):
            fifo_queue = fifo_data.get("fifo_queue", [])
            if fifo_queue:
                aging_data = self._calculate_aging_data(fifo_queue)
                report_data.update(aging_data)
        else:
            report_data.update({"age": 0, "average_age": 0, "earliest_age": 0, "latest_age": 0})

        # Add reserved stock
        report_data["reserved_stock"] = sre_details.get((report_data.item_code, report_data.warehouse), 0.0)

    def _get_fifo_key(self, report_data):
        """Get FIFO key based on grouping settings"""
        if self.filters.get("summary_qty_by_invoice_number"):
            return (report_data.item_code, report_data.warehouse, report_data.invoice_number or "")
        return (report_data.item_code, report_data.warehouse)

    def _calculate_aging_data(self, fifo_queue):
        """Calculate aging data from FIFO queue"""
        _func = itemgetter(1)
        filtered_queue = sorted(filter(_func, fifo_queue), key=_func)
        
        if not filtered_queue:
            return {"age": 0, "average_age": 0, "earliest_age": 0, "latest_age": 0}
            
        to_date = self.to_date
        average_age = get_average_age(filtered_queue, to_date)
        earliest_age = date_diff(to_date, filtered_queue[0][1])
        latest_age = date_diff(to_date, filtered_queue[-1][1])
        
        aging_data = {
            "age": average_age,
            "average_age": average_age,
            "earliest_age": earliest_age,
            "latest_age": latest_age,
        }
        
        # Add range values if stock aging is enabled
        if self.filters.get("show_stock_ageing_data"):
            aging_data.update(self._get_range_age_values(filtered_queue, to_date))
            
        return aging_data

    def _get_item_warehouse_map(self):
        """Build item-warehouse mapping with transactions"""
        item_warehouse_map = {}
        self.opening_vouchers = self._get_opening_vouchers()
        self.sle_entries = self.sle_query.run(as_dict=True)

        # Process each SLE entry
        for entry in self.sle_entries:
            group_by_key = self._get_group_by_key(entry)
            if group_by_key not in item_warehouse_map:
                self._initialize_warehouse_data(item_warehouse_map, group_by_key, entry)
            self._process_sle_entry(item_warehouse_map, entry, group_by_key)
            
            # Remove processed opening data
            if group_by_key in self.opening_data:
                del self.opening_data[group_by_key]

        # Add remaining opening data
        for group_by_key, entry in self.opening_data.items():
            if group_by_key not in item_warehouse_map:
                self._initialize_warehouse_data(item_warehouse_map, group_by_key, entry)

        return self._filter_items_with_no_transactions(item_warehouse_map)

    def _process_sle_entry(self, item_warehouse_map, entry, group_by_key):
        """Process single Stock Ledger Entry"""
        qty_dict = item_warehouse_map[group_by_key]
        
        # Update inventory dimensions
        for field in self.inventory_dimensions:
            qty_dict[field] = entry.get(field)

        # Calculate quantity and value differences
        if entry.voucher_type == "Stock Reconciliation" and (not entry.batch_no or entry.serial_no):
            qty_diff = flt(entry.qty_after_transaction) - flt(qty_dict.bal_qty)
        else:
            qty_diff = flt(entry.actual_qty)

        value_diff = flt(entry.stock_value_difference)

        # Check if this is an opening stock entry
        is_opening_stock = (entry.voucher_type == 'Stock Entry' and 
                           getattr(entry, 'custom_is_opening_stock', 0) == 1)

        # Categorize as opening or period transaction
        if (entry.posting_date < self.from_date or 
            entry.voucher_no in self.opening_vouchers.get(entry.voucher_type, []) or
            is_opening_stock):
            qty_dict.opening_qty += qty_diff
            qty_dict.opening_val += value_diff
        elif self.from_date <= entry.posting_date <= self.to_date:
            if qty_diff >= 0:
                qty_dict.in_qty += qty_diff
                qty_dict.in_val += value_diff
            else:
                qty_dict.out_qty += abs(qty_diff)
                qty_dict.out_val += abs(value_diff)

        # Update running totals
        qty_dict.val_rate = entry.valuation_rate
        qty_dict.bal_qty += qty_diff
        qty_dict.bal_val += value_diff

    def _initialize_warehouse_data(self, item_warehouse_map, group_by_key, entry):
        """Initialize warehouse data structure"""
        opening_data = self.opening_data.get(group_by_key, {})
        
        # Extract invoice number from group key
        invoice_number = ""
        if self.filters.get("summary_qty_by_invoice_number") and len(group_by_key) >= 4:
            invoice_number = group_by_key[3] or ""

        item_warehouse_map[group_by_key] = frappe._dict({
            "item_code": entry.item_code,
            "warehouse": entry.warehouse,
            "item_group": entry.item_group,
            "company": entry.company,
            "currency": self.company_currency,
            "stock_uom": entry.stock_uom,
            "item_name": entry.item_name,
            "invoice_number": invoice_number,
            "opening_qty": opening_data.get("bal_qty", 0.0),
            "opening_val": opening_data.get("bal_val", 0.0),
            "in_qty": 0.0,
            "in_val": 0.0,
            "out_qty": 0.0,
            "out_val": 0.0,
            "bal_qty": opening_data.get("bal_qty", 0.0),
            "bal_val": opening_data.get("bal_val", 0.0),
            "val_rate": 0.0,
            "age": 0.0,
        })

    def _get_group_by_key(self, row) -> tuple:
        """Generate grouping key for report data"""
        group_by_key = [row.company, row.item_code, row.warehouse]

        if self.filters.get("summary_qty_by_invoice_number"):
            group_by_key.append(row.get("custom_invoice_number") or "")

        for fieldname in self.inventory_dimensions:
            if row.get(fieldname) and (self.filters.get(fieldname) or self.filters.get("show_dimension_wise_stock")):
                group_by_key.append(row.get(fieldname))

        return tuple(group_by_key)

    def _get_closing_balance(self) -> list[dict[str, Any]]:
        """Get latest closing balance"""
        if self.filters.get("ignore_closing_balance"):
            return []

        table = frappe.qb.DocType("Closing Stock Balance")
        company = self.filters.get("company") or frappe.defaults.get_user_default("Company")

        query = (
            frappe.qb.from_(table)
            .select(table.name, table.to_date)
            .where(
                (table.docstatus == 1) &
                (table.company == company) &
                (table.to_date <= self.from_date) &
                (table.status == "Completed")
            )
            .orderby(table.to_date, order=Order.desc)
            .limit(1)
        )

        # Apply additional filters
        for fieldname in ["warehouse", "item_code", "item_group", "warehouse_type"]:
            if self.filters.get(fieldname):
                query = query.where(table[fieldname] == self.filters.get(fieldname))

        return query.run(as_dict=True)

    def _prepare_stock_ledger_entries(self):
        """Build Stock Ledger Entry query"""
        sle = frappe.qb.DocType("Stock Ledger Entry")
        item_table = frappe.qb.DocType("Item")

        query = (
            frappe.qb.from_(sle)
            .inner_join(item_table).on(sle.item_code == item_table.name)
            .select(
                sle.item_code, sle.warehouse, sle.posting_date, sle.actual_qty,
                sle.valuation_rate, sle.company, sle.voucher_type, sle.qty_after_transaction,
                sle.stock_value_difference, sle.voucher_no, sle.batch_no, sle.serial_no,
                sle.custom_invoice_number, sle.custom_receive_date, sle.custom_is_opening_stock,
                item_table.item_group, item_table.stock_uom, item_table.item_name,
            )
            .where((sle.docstatus < 2) & (sle.is_cancelled == 0))
            .orderby(sle.posting_datetime, sle.creation)
        )

        query = self._apply_filters(query, sle, item_table)
        self.sle_query = query

    def _apply_filters(self, query, sle, item_table):
        """Apply all filters to the query"""
        # Company filter
        company = self.filters.get("company") or frappe.defaults.get_user_default("Company")
        if company:
            query = query.where(sle.company == company)

        # Date filters
        if not self.filters.get("ignore_closing_balance") and self.start_from:
            query = query.where(sle.posting_date >= self.start_from)
        if self.to_date:
            query = query.where(sle.posting_date <= self.to_date)

        # Inventory dimension filters
        for fieldname in self.inventory_dimensions:
            query = query.select(fieldname)
            if self.filters.get(fieldname):
                query = query.where(sle[fieldname].isin(self.filters.get(fieldname)))

        # Warehouse filters
        if self.filters.get("warehouse"):
            query = apply_warehouse_filter(query, sle, self.filters)
        elif warehouse_type := self.filters.get("warehouse_type"):
            warehouse_table = frappe.qb.DocType("Warehouse")
            query = (query.join(warehouse_table).on(warehouse_table.name == sle.warehouse)
                    .where(warehouse_table.warehouse_type == warehouse_type))

        # Item filters
        if item_group := self.filters.get("item_group"):
            children = get_descendants_of("Item Group", item_group, ignore_permissions=True)
            query = query.where(item_table.item_group.isin([*children, item_group]))

        for field in ["item_code", "brand"]:
            if self.filters.get(field):
                if field == "item_code":
                    query = query.where(item_table.name == self.filters.get(field))
                else:
                    query = query.where(item_table[field] == self.filters.get(field))

        return query

    def _get_columns(self):
        """Generate report columns"""
        columns = [
            {"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 100},
            {"label": _("Item Name"), "fieldname": "item_name", "width": 150},
            {"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 100},
            {"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 100},
        ]

        # Invoice number column
        if self.filters.get("summary_qty_by_invoice_number"):
            columns.append({"label": _("Invoice Number"), "fieldname": "invoice_number", "fieldtype": "Data", "width": 140})

        # Dimension columns
        if self.filters.get("show_dimension_wise_stock"):
            for dimension in get_inventory_dimensions():
                columns.append({
                    "label": _(dimension.doctype), "fieldname": dimension.fieldname,
                    "fieldtype": "Link", "options": dimension.doctype, "width": 110
                })

        # Quantity columns
        columns.extend([
            {"label": _("Stock UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 90},
            {"label": _("Balance Qty"), "fieldname": "bal_qty", "fieldtype": "Float", "width": 100, "convertible": "qty"},
        ])

        # Value columns (conditional)
        if self.filters.get("show_value"):
            columns.append({"label": _("Balance Value"), "fieldname": "bal_val", "fieldtype": "Currency", "width": 100, "options": "currency"})

        columns.extend([
            {"label": _("Opening Qty"), "fieldname": "opening_qty", "fieldtype": "Float", "width": 100, "convertible": "qty"},
        ])

        if self.filters.get("show_value"):
            columns.append({"label": _("Opening Value"), "fieldname": "opening_val", "fieldtype": "Currency", "width": 110, "options": "currency"})

        columns.extend([
            {"label": _("In Qty"), "fieldname": "in_qty", "fieldtype": "Float", "width": 80, "convertible": "qty"},
        ])

        if self.filters.get("show_value"):
            columns.append({"label": _("In Value"), "fieldname": "in_val", "fieldtype": "Float", "width": 80})

        columns.extend([
            {"label": _("Out Qty"), "fieldname": "out_qty", "fieldtype": "Float", "width": 80, "convertible": "qty"},
        ])

        if self.filters.get("show_value"):
            columns.extend([
                {"label": _("Out Value"), "fieldname": "out_val", "fieldtype": "Float", "width": 80},
                {"label": _("Valuation Rate"), "fieldname": "val_rate", "fieldtype": "Currency", "width": 90, "options": "currency"},
            ])

        # Age columns - only show when invoice grouping is enabled
        if self.filters.get("summary_qty_by_invoice_number"):
            columns.append({"label": _("Age"), "fieldname": "age", "width": 80})

            # Stock aging columns
            if self.filters.get("show_stock_ageing_data"):
                self._add_aging_columns(columns)

        # Variant attribute columns
        if self.filters.get("show_variant_attributes"):
            self._add_variant_columns(columns)

        return columns

    def _add_aging_columns(self, columns):
        """Add stock aging columns to report"""
        if self.filters.get("range"):
            ranges = []
            prev_range = 0
            for range_val in self.filters.get("ranges", []):
                ranges.append(f"{prev_range} - {range_val}")
                prev_range = int(range_val) + 1
            ranges.append(f"{prev_range} - Above")

            for i, label in enumerate(ranges):
                fieldname = f"range{i + 1}"
                columns.append({"label": _(f"Age ({label})"), "fieldname": fieldname, "fieldtype": "Float", "width": 140})
                if self.filters.get("show_value"):
                    columns.append({"label": _(f"Value ({label})"), "fieldname": f"{fieldname}value", "fieldtype": "Float", "width": 140})
        else:
            columns.extend([
                {"label": _("Average Age"), "fieldname": "average_age", "width": 100},
                {"label": _("Earliest Age"), "fieldname": "earliest_age", "width": 100},
                {"label": _("Latest Age"), "fieldname": "latest_age", "width": 100},
            ])

    def _add_variant_columns(self, columns):
        """Add variant attribute columns"""
        ordered_attributes = ["Color", "Size", "Brand", "Season", "Info"]
        all_attributes = self._get_variant_attributes()
        
        # Add ordered attributes first
        for att_name in ordered_attributes:
            if att_name in all_attributes:
                columns.append({"label": att_name, "fieldname": att_name, "width": 100})
        
        # Add remaining attributes
        for att_name in all_attributes:
            if att_name not in ordered_attributes:
                columns.append({"label": att_name, "fieldname": att_name, "width": 100})

    def _add_additional_uom_columns(self):
        """Add UOM conversion columns if needed"""
        if not self.filters.get("include_uom"):
            return

        conversion_factors = self._get_itemwise_conversion_factor()
        add_additional_uom_columns(self.columns, self.data, self.filters.include_uom, conversion_factors)

    def _get_itemwise_conversion_factor(self):
        """Get UOM conversion factors"""
        items = [d.item_code for d in self.data] if self.filters.get("item_code") or self.filters.get("item_group") else []
        
        table = frappe.qb.DocType("UOM Conversion Detail")
        query = (
            frappe.qb.from_(table)
            .select(table.conversion_factor, table.parent)
            .where((table.parenttype == "Item") & (table.uom == self.filters.include_uom))
        )

        if items:
            query = query.where(table.parent.isin(items))

        result = query.run(as_dict=1)
        return {d.parent: d.conversion_factor for d in result} if result else {}

    def _get_variant_values(self):
        """Get variant attribute values for items"""
        items = [d.item_code for d in self.data] if self.filters.get("item_code") or self.filters.get("item_group") else []
        
        conditions = "AND parent IN ({})".format(', '.join(['%s'] * len(items))) if items else ""
        values = items if items else []

        query = f"""
            SELECT parent, attribute,
                CASE 
                    WHEN attribute_value IS NULL THEN ''
                    WHEN TRIM(attribute_value) = '' THEN ''
                    WHEN LOWER(TRIM(attribute_value)) IN ('none', 'nan', 'null') THEN ''
                    ELSE TRIM(attribute_value)
                END as cleaned_attribute_value
            FROM `tabItem Variant Attribute`
            WHERE 1=1 {conditions}
        """

        attribute_info = frappe.db.sql(query, values, as_dict=True)
        attribute_map = {}
        
        for attr in attribute_info:
            attribute_map.setdefault(attr["parent"], {})
            attribute_map[attr["parent"]][attr["attribute"]] = attr["cleaned_attribute_value"]

        return attribute_map

    @staticmethod
    def _get_variant_attributes() -> list[str]:
        """Get all item variant attributes"""
        return frappe.get_all("Item Attribute", pluck="name")

    def _get_sre_reserved_qty_details(self) -> dict:
        """Get reserved stock quantities"""
        try:
            from erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry import (
                get_sre_reserved_qty_for_items_and_warehouses as get_reserved_qty_details,
            )
            
            item_codes = [d[1] for d in self.item_warehouse_map]
            warehouses = [d[2] for d in self.item_warehouse_map]
            return get_reserved_qty_details(item_codes, warehouses)
        except ImportError:
            return {}

    def _get_opening_vouchers(self):
        """Get opening vouchers (Stock Entry and Stock Reconciliation)"""
        opening_vouchers = {"Stock Entry": [], "Stock Reconciliation": []}

        se = frappe.qb.DocType("Stock Entry")
        sr = frappe.qb.DocType("Stock Reconciliation")

        vouchers_data = (
            frappe.qb.from_(
                (frappe.qb.from_(se).select(se.name, Coalesce("Stock Entry").as_("voucher_type"))
                 .where((se.docstatus == 1) & (se.posting_date <= self.to_date) & (se.is_opening == "Yes"))) +
                (frappe.qb.from_(sr).select(sr.name, Coalesce("Stock Reconciliation").as_("voucher_type"))
                 .where((sr.docstatus == 1) & (sr.posting_date <= self.to_date) & (sr.purpose == "Opening Stock")))
            ).select("voucher_type", "name")
        ).run(as_dict=True)

        for d in vouchers_data:
            opening_vouchers[d.voucher_type].append(d.name)

        return opening_vouchers

    def _get_range_age_values(self, fifo_queue, to_date):
        """Calculate age range values for stock aging"""
        if not self.filters.get("ranges"):
            return {}
        
        precision = self.float_precision
        num_ranges = len(self.filters.ranges) + 1
        range_values = [0.0] * (num_ranges * 2 if self.filters.get("show_value") else num_ranges)

        for item in fifo_queue:
            age = flt(date_diff(to_date, item[1]))
            qty = flt(item[0])
            stock_value = flt(item[2]) if len(item) > 2 else 0

            # Find appropriate range
            range_index = len(self.filters.ranges)  # Default to last range
            for i, age_limit in enumerate(self.filters.ranges):
                if age <= flt(age_limit):
                    range_index = i
                    break

            # Add to range
            if self.filters.get("show_value"):
                qty_index = range_index * 2
                value_index = qty_index + 1
                if qty_index < len(range_values):
                    range_values[qty_index] = flt(range_values[qty_index] + qty, precision)
                if value_index < len(range_values):
                    range_values[value_index] = flt(range_values[value_index] + stock_value, precision)
            else:
                if range_index < len(range_values):
                    range_values[range_index] = flt(range_values[range_index] + qty, precision)

        # Convert to dictionary
        result = {}
        for i in range(num_ranges):
            if self.filters.get("show_value"):
                qty_index = i * 2
                value_index = qty_index + 1
                result[f"range{i + 1}"] = range_values[qty_index] if qty_index < len(range_values) else 0
                result[f"range{i + 1}value"] = range_values[value_index] if value_index < len(range_values) else 0
            else:
                result[f"range{i + 1}"] = range_values[i] if i < len(range_values) else 0
        
        return result

    def _filter_items_with_no_transactions(self, iwb_map):
        """Remove items with no meaningful transactions"""
        pop_keys = []
        for group_by_key, qty_dict in iwb_map.items():
            has_transactions = False
            for key, val in qty_dict.items():
                if key in ["item_code", "warehouse", "item_name", "item_group", "stock_uom", "company", "invoice_number", "currency"]:
                    continue
                if key in self.inventory_dimensions:
                    continue
                    
                val = flt(val, self.float_precision)
                qty_dict[key] = val
                if key != "val_rate" and val:
                    has_transactions = True

            if not has_transactions:
                pop_keys.append(group_by_key)

        for key in pop_keys:
            iwb_map.pop(key)

        return iwb_map


class CustomizedFIFOSlots(FIFOSlots):
    """Enhanced FIFOSlots with invoice number support and custom_receive_date prioritization"""
    
    def generate(self) -> dict:
        """Generate FIFO slots with invoice grouping support"""
        try:
            from erpnext.stock.doctype.serial_and_batch_bundle.test_serial_and_batch_bundle import get_serial_nos_from_bundle
        except ImportError:
            def get_serial_nos_from_bundle(bundle_name):
                return []

        stock_ledger_entries = self.sle or self._get_stock_ledger_entries()
        bundle_wise_serial_nos = frappe._dict({}) if self.sle else self._get_bundle_wise_serial_nos()

        with frappe.db.unbuffered_cursor():
            for d in stock_ledger_entries:
                key, fifo_queue, transferred_item_key = self._init_key_stores(d)

                if d.voucher_type == "Stock Reconciliation":
                    prev_balance_qty = self.item_details[key].get("qty_after_transaction", 0)
                    d.actual_qty = flt(d.qty_after_transaction) - flt(prev_balance_qty)

                # Prioritize custom_receive_date
                if d.get("custom_receive_date"):
                    d.posting_date = d.custom_receive_date

                # Handle serial numbers
                serial_nos = self._get_serial_numbers(d, bundle_wise_serial_nos, get_serial_nos_from_bundle)

                if d.actual_qty > 0:
                    self._compute_incoming_stock(d, fifo_queue, transferred_item_key, serial_nos)
                else:
                    self._compute_outgoing_stock(d, fifo_queue, transferred_item_key, serial_nos)

                self._update_balances(d, key)

        if not self.filters.get("show_warehouse_wise_stock"):
            self.item_details = self._aggregate_details_by_item_and_invoice(self.item_details)

        return self.item_details

    def _init_key_stores(self, row: dict) -> tuple:
        """Initialize keys with invoice number grouping"""
        invoice_number = row.get("custom_invoice_number", "")
        
        if self.filters.get("show_warehouse_wise_stock"):
            key = (row.item_code, row.warehouse, invoice_number) if self.filters.get("summary_qty_by_invoice_number") else (row.item_code, row.warehouse)
        else:
            key = (row.item_code, invoice_number) if self.filters.get("summary_qty_by_invoice_number") else (row.item_code,)

        self.item_details.setdefault(key, {"details": row, "fifo_queue": []})
        fifo_queue = self.item_details[key]["fifo_queue"]

        transferred_item_key = (row.voucher_no, row.item_code, row.warehouse, invoice_number)
        self.transferred_item_details.setdefault(transferred_item_key, [])

        return key, fifo_queue, transferred_item_key

    def _get_serial_numbers(self, entry, bundle_wise_serial_nos, get_serial_nos_from_bundle):
        """Get serial numbers from various sources"""
        serial_nos = []
        
        if entry.serial_no:
            from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos
            serial_nos = get_serial_nos(entry.serial_no)
        elif entry.serial_and_batch_bundle and entry.has_serial_no:
            if bundle_wise_serial_nos:
                serial_nos = bundle_wise_serial_nos.get(entry.serial_and_batch_bundle) or []
            else:
                serial_nos = get_serial_nos_from_bundle(entry.serial_and_batch_bundle) or []
                
        return serial_nos

    def _compute_incoming_stock(self, row: dict, fifo_queue: list, transfer_key: tuple, serial_nos: list):
        """Process incoming stock with invoice tracking"""
        transfer_data = self.transferred_item_details.get(transfer_key)
        if transfer_data:
            self._adjust_incoming_transfer_qty(transfer_data, fifo_queue, row)
        else:
            if not serial_nos and not row.get("has_serial_no"):
                if fifo_queue and flt(fifo_queue[0][0]) <= 0:
                    fifo_queue[0][0] += flt(row.actual_qty)
                    fifo_queue[0][1] = row.posting_date
                    fifo_queue[0][2] += flt(row.stock_value_difference)
                    if len(fifo_queue[0]) <= 3:
                        fifo_queue[0].append(row.get("custom_invoice_number", ""))
                    else:
                        fifo_queue[0][3] = row.get("custom_invoice_number", "")
                else:
                    fifo_queue.append([
                        flt(row.actual_qty), row.posting_date, flt(row.stock_value_difference),
                        row.get("custom_invoice_number", "")
                    ])
                return

            valuation = row.stock_value_difference / row.actual_qty if row.actual_qty else 0
            for serial_no in serial_nos:
                fifo_queue.append([serial_no, row.posting_date, valuation, row.get("custom_invoice_number", "")])

    def _compute_outgoing_stock(self, row: dict, fifo_queue: list, transfer_key: tuple, serial_nos: list):
        """Process outgoing stock with FIFO logic"""
        if serial_nos:
            fifo_queue[:] = [serial_no for serial_no in fifo_queue if serial_no[0] not in serial_nos]
            return

        qty_to_pop = abs(row.actual_qty)
        stock_value = abs(row.stock_value_difference)

        while qty_to_pop:
            slot = fifo_queue[0] if fifo_queue else [0, None, 0, ""]
            if 0 < flt(slot[0]) <= qty_to_pop:
                qty_to_pop -= flt(slot[0])
                stock_value -= flt(slot[2])
                self.transferred_item_details[transfer_key].append(fifo_queue.pop(0))
            elif not fifo_queue:
                fifo_queue.append([-(qty_to_pop), row.posting_date, -(stock_value), row.get("custom_invoice_number", "")])
                self.transferred_item_details[transfer_key].append([qty_to_pop, row.posting_date, stock_value, row.get("custom_invoice_number", "")])
                qty_to_pop = 0
                stock_value = 0
            else:
                slot[0] = flt(slot[0]) - qty_to_pop
                slot[2] = flt(slot[2]) - stock_value
                self.transferred_item_details[transfer_key].append([qty_to_pop, slot[1], stock_value, slot[3] if len(slot) > 3 else ""])
                qty_to_pop = 0
                stock_value = 0

    def _adjust_incoming_transfer_qty(self, transfer_data: dict, fifo_queue: list, row: dict):
        """Add previously removed stock back to FIFO Queue"""
        transfer_qty_to_pop = flt(row.actual_qty)
        stock_value = flt(row.stock_value_difference)

        def add_to_fifo_queue(slot):
            if fifo_queue and flt(fifo_queue[0][0]) <= 0:
                fifo_queue[0][0] += flt(slot[0])
                fifo_queue[0][1] = slot[1]
                fifo_queue[0][2] += flt(slot[2])
                if len(fifo_queue[0]) <= 3:
                    fifo_queue[0].append(slot[3] if len(slot) > 3 else "")
                else:
                    fifo_queue[0][3] = slot[3] if len(slot) > 3 else ""
            else:
                fifo_queue.append(slot)

        while transfer_qty_to_pop:
            if transfer_data and 0 < transfer_data[0][0] <= transfer_qty_to_pop:
                transfer_qty_to_pop -= transfer_data[0][0]
                stock_value -= transfer_data[0][2]
                add_to_fifo_queue(transfer_data.pop(0))
            elif not transfer_data:
                add_to_fifo_queue([transfer_qty_to_pop, row.posting_date, stock_value, row.get("custom_invoice_number", "")])
                transfer_qty_to_pop = 0
                stock_value = 0
            else:
                transfer_data[0][0] -= transfer_qty_to_pop
                transfer_data[0][2] -= stock_value
                add_to_fifo_queue([transfer_qty_to_pop, transfer_data[0][1], stock_value, transfer_data[0][3] if len(transfer_data[0]) > 3 else ""])
                transfer_qty_to_pop = 0
                stock_value = 0

    def _update_balances(self, row: dict, key: tuple | str):
        """Update balance tracking"""
        self.item_details[key]["qty_after_transaction"] = row.qty_after_transaction

        if "total_qty" not in self.item_details[key]:
            self.item_details[key]["total_qty"] = row.actual_qty
        else:
            self.item_details[key]["total_qty"] += row.actual_qty

        self.item_details[key]["has_serial_no"] = row.get("has_serial_no", False)
        self.item_details[key]["details"].valuation_rate = row.valuation_rate

    def _aggregate_details_by_item_and_invoice(self, wh_wise_data: dict) -> dict:
        """Aggregate warehouse-wise data by item and invoice"""
        item_invoice_aggregated_data = {}
        
        for key, row in wh_wise_data.items():
            if self.filters.get("summary_qty_by_invoice_number"):
                new_key = (key[0], key[2] if len(key) >= 3 else key[1] if len(key) > 1 else "")
            else:
                new_key = (key[0],)

            if new_key not in item_invoice_aggregated_data:
                item_invoice_aggregated_data[new_key] = {
                    "details": frappe._dict(),
                    "fifo_queue": [],
                    "qty_after_transaction": 0.0,
                    "total_qty": 0.0,
                }
            
            item_row = item_invoice_aggregated_data[new_key]
            item_row["details"].update(row["details"])
            item_row["fifo_queue"].extend(row["fifo_queue"])
            item_row["qty_after_transaction"] += flt(row["qty_after_transaction"])
            item_row["total_qty"] += flt(row["total_qty"])
            item_row["has_serial_no"] = row.get("has_serial_no", False)

        return item_invoice_aggregated_data


# Hook functions for Stock Entry and Stock Reconciliation
def update_stock_ledger_invoice_number(doc, method):
    """Update Stock Ledger Entry invoice numbers when documents are submitted"""
    if doc.doctype == "Stock Entry":
        _update_from_stock_entry(doc)
    elif doc.doctype == "Stock Reconciliation":
        _update_from_stock_reconciliation(doc)


def _update_from_stock_entry(stock_entry):
    """Update invoice numbers for Stock Entry"""
    # Get detail to invoice mapping
    detail_to_invoice = {item.name: item.custom_invoice_number for item in stock_entry.items}
    
    # Update SLE entries
    sle_entries = frappe.db.sql("""
        SELECT name, voucher_detail_no FROM `tabStock Ledger Entry`
        WHERE voucher_type = 'Stock Entry' AND voucher_no = %s
    """, stock_entry.name, as_dict=1)
    
    for sle in sle_entries:
        invoice_number = detail_to_invoice.get(sle.voucher_detail_no)
        if invoice_number:
            frappe.db.set_value("Stock Ledger Entry", sle.name, "custom_invoice_number", invoice_number, update_modified=False)


def _update_from_stock_reconciliation(stock_reconciliation):
    """Update invoice numbers for Stock Reconciliation"""
    # Get detail to invoice mapping
    detail_to_invoice = {item.name: item.custom_invoice_number for item in stock_reconciliation.items}
    
    # Update SLE entries
    sle_entries = frappe.db.sql("""
        SELECT name, voucher_detail_no FROM `tabStock Ledger Entry`
        WHERE voucher_type = 'Stock Reconciliation' AND voucher_no = %s
    """, stock_reconciliation.name, as_dict=1)
    
    for sle in sle_entries:
        invoice_number = detail_to_invoice.get(sle.voucher_detail_no)
        if invoice_number:
            frappe.db.set_value("Stock Ledger Entry", sle.name, "custom_invoice_number", invoice_number, update_modified=False)