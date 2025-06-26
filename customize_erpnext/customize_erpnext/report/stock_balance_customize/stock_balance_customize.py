# stock_balance_customize.py
# Enhanced Stock Balance Report with Invoice Number Support
# Copyright (c) 2024, Custom Enhancement for ERPNext

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


SLEntry = dict[str, Any]


def execute(filters: StockBalanceFilter | None = None):
    return StockBalanceReportCustomized(filters).run()


def get_report_filters():
    """Define filters for the Stock Balance Report"""
    return [
        {
            "fieldname": "company",
            "label": _("Company"),
            "fieldtype": "Link",
            "options": "Company",
            "default": frappe.defaults.get_user_default("Company"),
            "reqd": 1,
            "width": 100
        },
        {
            "fieldname": "from_date",
            "label": _("From Date"),
            "fieldtype": "Date",
            "default": frappe.utils.add_months(frappe.utils.today(), -1),
            "reqd": 1,
            "width": 100
        },
        {
            "fieldname": "to_date",
            "label": _("To Date"), 
            "fieldtype": "Date",
            "default": frappe.utils.today(),
            "reqd": 1,
            "width": 100
        },
        {
            "fieldname": "item_group",
            "label": _("Item Group"),
            "fieldtype": "Link",
            "options": "Item Group",
            "width": 100
        },
        {
            "fieldname": "item",
            "label": _("Item"),
            "fieldtype": "Link", 
            "options": "Item",
            "width": 100
        },
        {
            "fieldname": "warehouse",
            "label": _("Warehouse"),
            "fieldtype": "Link",
            "options": "Warehouse",
            "get_query": lambda: {"filters": {"is_group": 0}},
            "width": 100
        },
        {
            "fieldname": "warehouse_type",
            "label": _("Warehouse Type"),
            "fieldtype": "Link",
            "options": "Warehouse Type",
            "width": 100
        },
        {
            "fieldname": "include_uom",
            "label": _("Include UOM"),
            "fieldtype": "Link",
            "options": "UOM",
            "width": 100
        },
        {
            "fieldname": "show_variant_attributes",
            "label": _("Show Variant Attributes"),
            "fieldtype": "Check",
            "default": 1
        },
        {
            "fieldname": "show_stock_ageing_data", 
            "label": _("Show Stock Ageing Data"),
            "fieldtype": "Check",
            "default": 0
        },
        {
            "fieldname": "summary_qty_by_invoice_number",
            "label": _("Group by Invoice Number"),
            "fieldtype": "Check", 
            "default": 1
        },
        {
            "fieldname": "show_value",
            "label": _("Show Value"),
            "fieldtype": "Check",
            "default": 0
        },
        {
            "fieldname": "include_zero_stock_items",
            "label": _("Include Zero Stock Items"),
            "fieldtype": "Check",
            "default": 0
        },
        {
            "fieldname": "ignore_closing_balance",
            "label": _("Ignore Closing Balance"),
            "fieldtype": "Check", 
            "default": 0
        }
    ]


class StockBalanceReportCustomized:
    def __init__(self, filters: StockBalanceFilter | None) -> None:
        self.filters = filters
        self.from_date = getdate(filters.get("from_date"))
        self.to_date = getdate(filters.get("to_date"))

        self.start_from = None
        self.data = []
        self.columns = []
        self.sle_entries: list[SLEntry] = []
        self.set_company_currency()

    def set_company_currency(self) -> None:
        # Use company from filters or default
        company = self.filters.get("company") or "Toray International, VietNam Company Limited - Quang Ngai Branch"
        self.company_currency = erpnext.get_company_currency(company)

    def run(self):
        self.float_precision = cint(frappe.db.get_default("float_precision")) or 3

        self.inventory_dimensions = self.get_inventory_dimension_fields()
        self.prepare_opening_data_from_closing_balance()
        self.prepare_stock_ledger_entries()
        self.prepare_new_data()

        if not self.columns:
            self.columns = self.get_columns()

        self.add_additional_uom_columns()

        return self.columns, self.data

    def prepare_opening_data_from_closing_balance(self) -> None:
        self.opening_data = frappe._dict({})

        closing_balance = self.get_closing_balance()
        if not closing_balance:
            return

        self.start_from = add_days(closing_balance[0].to_date, 1)
        res = frappe.get_doc("Closing Stock Balance", closing_balance[0].name).get_prepared_data()

        for entry in res.data:
            entry = frappe._dict(entry)

            # When grouping by invoice number, skip opening data as it doesn't have invoice breakdown
            if self.filters.get("summary_qty_by_invoice_number"):
                continue
            else:
                group_by_key = self.get_group_by_key(entry)
                if group_by_key not in self.opening_data:
                    self.opening_data.setdefault(group_by_key, entry)

    def prepare_new_data(self):
        self.item_warehouse_map = self.get_item_warehouse_map()

        if self.filters.get("show_stock_ageing_data"):
            self.filters["show_warehouse_wise_stock"] = True
            item_wise_fifo_queue = FIFOSlots(self.filters, self.sle_entries).generate()

        _func = itemgetter(1)

        del self.sle_entries

        sre_details = self.get_sre_reserved_qty_details()

        variant_values = {}
        if self.filters.get("show_variant_attributes"):
            variant_values = self.get_variant_values_for()

        for _key, report_data in self.item_warehouse_map.items():
            if variant_data := variant_values.get(report_data.item_code):
                # Clean variant data to prevent "nan" values
                cleaned_variant_data = {}
                for key, value in variant_data.items():
                    if value in [None, "", "None", "nan", "null"]:
                        cleaned_variant_data[key] = ""
                    else:
                        cleaned_variant_data[key] = str(value) if value else ""
                # FIXED: Use cleaned_variant_data instead of variant_data
                report_data.update(cleaned_variant_data)

            if self.filters.get("show_stock_ageing_data"):
                opening_fifo_queue = self.get_opening_fifo_queue(report_data) or []

                fifo_queue = []
                if fifo_queue := item_wise_fifo_queue.get((report_data.item_code, report_data.warehouse)):
                    fifo_queue = fifo_queue.get("fifo_queue")

                if fifo_queue:
                    opening_fifo_queue.extend(fifo_queue)

                stock_ageing_data = {"average_age": 0, "earliest_age": 0, "latest_age": 0}
                if opening_fifo_queue:
                    fifo_queue = sorted(filter(_func, opening_fifo_queue), key=_func)
                    if not fifo_queue:
                        continue

                    to_date = self.to_date
                    stock_ageing_data["average_age"] = get_average_age(fifo_queue, to_date)
                    stock_ageing_data["earliest_age"] = date_diff(to_date, fifo_queue[0][1])
                    stock_ageing_data["latest_age"] = date_diff(to_date, fifo_queue[-1][1])
                    stock_ageing_data["fifo_queue"] = fifo_queue

                report_data.update(stock_ageing_data)

            report_data.update(
                {"reserved_stock": sre_details.get((report_data.item_code, report_data.warehouse), 0.0)}
            )

            if (
                not self.filters.get("include_zero_stock_items")
                and report_data
                and report_data.bal_qty == 0
                and report_data.bal_val == 0
            ):
                continue

            self.data.append(report_data)

    def get_item_warehouse_map(self):
        item_warehouse_map = {}
        self.opening_vouchers = self.get_opening_vouchers()

        if self.filters.get("show_stock_ageing_data"):
            self.sle_entries = self.sle_query.run(as_dict=True)

        # HACK: This is required to avoid causing db query in flt
        _system_settings = frappe.get_cached_doc("System Settings")
        with frappe.db.unbuffered_cursor():
            if not self.filters.get("show_stock_ageing_data"):
                self.sle_entries = self.sle_query.run(as_dict=True, as_iterator=True)

            for entry in self.sle_entries:
                group_by_key = self.get_group_by_key(entry)
                if group_by_key not in item_warehouse_map:
                    self.initialize_data(item_warehouse_map, group_by_key, entry)

                self.prepare_item_warehouse_map(item_warehouse_map, entry, group_by_key)

                if self.opening_data.get(group_by_key):
                    del self.opening_data[group_by_key]

        for group_by_key, entry in self.opening_data.items():
            if group_by_key not in item_warehouse_map:
                self.initialize_data(item_warehouse_map, group_by_key, entry)

        item_warehouse_map = filter_items_with_no_transactions(
            item_warehouse_map, self.float_precision, self.inventory_dimensions
        )

        return item_warehouse_map

    def get_sre_reserved_qty_details(self) -> dict:
        from erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry import (
            get_sre_reserved_qty_for_items_and_warehouses as get_reserved_qty_details,
        )

        item_code_list, warehouse_list = [], []
        for d in self.item_warehouse_map:
            item_code_list.append(d[1])
            warehouse_list.append(d[2])

        return get_reserved_qty_details(item_code_list, warehouse_list)

    def prepare_item_warehouse_map(self, item_warehouse_map, entry, group_by_key):
        qty_dict = item_warehouse_map[group_by_key]
        for field in self.inventory_dimensions:
            qty_dict[field] = entry.get(field)

        if entry.voucher_type == "Stock Reconciliation" and (not entry.batch_no or entry.serial_no):
            qty_diff = flt(entry.qty_after_transaction) - flt(qty_dict.bal_qty)
        else:
            qty_diff = flt(entry.actual_qty)

        value_diff = flt(entry.stock_value_difference)

        if entry.posting_date < self.from_date or entry.voucher_no in self.opening_vouchers.get(
            entry.voucher_type, []
        ):
            qty_dict.opening_qty += qty_diff
            qty_dict.opening_val += value_diff

        elif entry.posting_date >= self.from_date and entry.posting_date <= self.to_date:
            if flt(qty_diff, self.float_precision) >= 0:
                qty_dict.in_qty += qty_diff
            else:
                qty_dict.out_qty += abs(qty_diff)

            if flt(value_diff, self.float_precision) >= 0:
                qty_dict.in_val += value_diff
            else:
                qty_dict.out_val += abs(value_diff)

        qty_dict.val_rate = entry.valuation_rate
        qty_dict.bal_qty += qty_diff
        qty_dict.bal_val += value_diff

    def initialize_data(self, item_warehouse_map, group_by_key, entry):
        opening_data = self.opening_data.get(group_by_key, {})

        # Extract invoice number correctly from group_by_key if invoice grouping is enabled
        invoice_number = ""
        if self.filters.get("summary_qty_by_invoice_number"):
            # Invoice number is the 4th element in group_by_key (company, item_code, warehouse, invoice_number)
            if len(group_by_key) >= 4:
                invoice_number = group_by_key[3] or ""

        item_warehouse_map[group_by_key] = frappe._dict(
            {
                "item_code": entry.item_code,
                "warehouse": entry.warehouse,
                "item_group": entry.item_group,
                "company": entry.company,
                "currency": self.company_currency,
                "stock_uom": entry.stock_uom,
                "item_name": entry.item_name,
                "invoice_number": invoice_number,
                "opening_qty": opening_data.get("bal_qty") or 0.0,
                "opening_val": opening_data.get("bal_val") or 0.0,
                "opening_fifo_queue": opening_data.get("fifo_queue") or [],
                "in_qty": 0.0,
                "in_val": 0.0,
                "out_qty": 0.0,
                "out_val": 0.0,
                "bal_qty": opening_data.get("bal_qty") or 0.0,
                "bal_val": opening_data.get("bal_val") or 0.0,
                "val_rate": 0.0,
            }
        )

    def get_group_by_key(self, row) -> tuple:
        group_by_key = [row.company, row.item_code, row.warehouse]

        # Add invoice number to group by if enabled
        if self.filters.get("summary_qty_by_invoice_number"):
            group_by_key.append(row.get("custom_invoice_number") or "")

        for fieldname in self.inventory_dimensions:
            if not row.get(fieldname):
                continue

            if self.filters.get(fieldname) or self.filters.get("show_dimension_wise_stock"):
                group_by_key.append(row.get(fieldname))

        return tuple(group_by_key)

    def get_closing_balance(self) -> list[dict[str, Any]]:
        if self.filters.get("ignore_closing_balance"):
            return []

        table = frappe.qb.DocType("Closing Stock Balance")
        
        # Use company from filters or default
        company = self.filters.get("company") or "Toray International, VietNam Company Limited - Quang Ngai Branch"

        query = (
            frappe.qb.from_(table)
            .select(table.name, table.to_date)
            .where(
                (table.docstatus == 1)
                & (table.company == company)
                & (table.to_date <= self.from_date)
                & (table.status == "Completed")
            )
            .orderby(table.to_date, order=Order.desc)
            .limit(1)
        )

        for fieldname in ["warehouse", "item_code", "item_group", "warehouse_type"]:
            if self.filters.get(fieldname):
                query = query.where(table[fieldname] == self.filters.get(fieldname))

        return query.run(as_dict=True)

    def prepare_stock_ledger_entries(self):
        sle = frappe.qb.DocType("Stock Ledger Entry")
        item_table = frappe.qb.DocType("Item")

        query = (
            frappe.qb.from_(sle)
            .inner_join(item_table)
            .on(sle.item_code == item_table.name)
            .select(
                sle.item_code,
                sle.warehouse,
                sle.posting_date,
                sle.actual_qty,
                sle.valuation_rate,
                sle.company,
                sle.voucher_type,
                sle.qty_after_transaction,
                sle.stock_value_difference,
                sle.item_code.as_("name"),
                sle.voucher_no,
                sle.stock_value,
                sle.batch_no,
                sle.serial_no,
                sle.serial_and_batch_bundle,
                sle.has_serial_no,
                sle.custom_invoice_number,
                item_table.item_group,
                item_table.stock_uom,
                item_table.item_name,
            )
            .where((sle.docstatus < 2) & (sle.is_cancelled == 0))
            .orderby(sle.posting_datetime)
            .orderby(sle.creation)
        )

        query = self.apply_inventory_dimensions_filters(query, sle)
        query = self.apply_warehouse_filters(query, sle)
        query = self.apply_items_filters(query, item_table)
        query = self.apply_date_filters(query, sle)

        # Filter by company from filters or default
        company = self.filters.get("company") or "Toray International, VietNam Company Limited - Quang Ngai Branch"
        query = query.where(sle.company == company)

        self.sle_query = query

    def apply_inventory_dimensions_filters(self, query, sle) -> str:
        inventory_dimension_fields = self.get_inventory_dimension_fields()
        if inventory_dimension_fields:
            for fieldname in inventory_dimension_fields:
                query = query.select(fieldname)
                if self.filters.get(fieldname):
                    query = query.where(sle[fieldname].isin(self.filters.get(fieldname)))

        return query

    def apply_warehouse_filters(self, query, sle) -> str:
        warehouse_table = frappe.qb.DocType("Warehouse")

        if self.filters.get("warehouse"):
            query = apply_warehouse_filter(query, sle, self.filters)
        elif warehouse_type := self.filters.get("warehouse_type"):
            query = (
                query.join(warehouse_table)
                .on(warehouse_table.name == sle.warehouse)
                .where(warehouse_table.warehouse_type == warehouse_type)
            )

        return query

    def apply_items_filters(self, query, item_table) -> str:
        if item_group := self.filters.get("item_group"):
            children = get_descendants_of("Item Group", item_group, ignore_permissions=True)
            query = query.where(item_table.item_group.isin([*children, item_group]))

        for field in ["item_code", "brand"]:
            if not self.filters.get(field):
                continue
            elif field == "item_code":
                query = query.where(item_table.name == self.filters.get(field))
            else:
                query = query.where(item_table[field] == self.filters.get(field))

        return query

    def apply_date_filters(self, query, sle) -> str:
        if not self.filters.ignore_closing_balance and self.start_from:
            query = query.where(sle.posting_date >= self.start_from)

        if self.to_date:
            query = query.where(sle.posting_date <= self.to_date)

        return query

    def get_columns(self):
        columns = [
            {
                "label": _("Item"),
                "fieldname": "item_code",
                "fieldtype": "Link",
                "options": "Item",
                "width": 100,
            },
            {"label": _("Item Name"), "fieldname": "item_name", "width": 150},
            {
                "label": _("Item Group"),
                "fieldname": "item_group",
                "fieldtype": "Link",
                "options": "Item Group",
                "width": 100,
            },
            {
                "label": _("Warehouse"),
                "fieldname": "warehouse",
                "fieldtype": "Link",
                "options": "Warehouse",
                "width": 100,
            },
        ]

        # Add invoice number column if enabled
        if self.filters.get("summary_qty_by_invoice_number"):
            columns.append({
                "label": _("Invoice Number"),
                "fieldname": "invoice_number",
                "fieldtype": "Data",
                "width": 140,
            })

        if self.filters.get("show_dimension_wise_stock"):
            for dimension in get_inventory_dimensions():
                columns.append(
                    {
                        "label": _(dimension.doctype),
                        "fieldname": dimension.fieldname,
                        "fieldtype": "Link",
                        "options": dimension.doctype,
                        "width": 110,
                    }
                )

        columns.extend([
            {
                "label": _("Stock UOM"),
                "fieldname": "stock_uom",
                "fieldtype": "Link",
                "options": "UOM",
                "width": 90,
            },
            {
                "label": _("Balance Qty"),
                "fieldname": "bal_qty",
                "fieldtype": "Float",
                "width": 100,
                "convertible": "qty",
            },
        ])

        # Add value columns if enabled
        if self.filters.get("show_value"):
            columns.extend([
                {
                    "label": _("Balance Value"),
                    "fieldname": "bal_val",
                    "fieldtype": "Currency",
                    "width": 100,
                    "options": "currency",
                },
            ])

        columns.extend([
            {
                "label": _("Opening Qty"),
                "fieldname": "opening_qty",
                "fieldtype": "Float",
                "width": 100,
                "convertible": "qty",
            },
        ])

        if self.filters.get("show_value"):
            columns.extend([
                {
                    "label": _("Opening Value"),
                    "fieldname": "opening_val",
                    "fieldtype": "Currency",
                    "width": 110,
                    "options": "currency",
                },
            ])

        columns.extend([
            {
                "label": _("In Qty"),
                "fieldname": "in_qty",
                "fieldtype": "Float",
                "width": 80,
                "convertible": "qty",
            },
        ])

        if self.filters.get("show_value"):
            columns.extend([
                {"label": _("In Value"), "fieldname": "in_val", "fieldtype": "Float", "width": 80},
            ])

        columns.extend([
            {
                "label": _("Out Qty"),
                "fieldname": "out_qty",
                "fieldtype": "Float",
                "width": 80,
                "convertible": "qty",
            },
        ])

        if self.filters.get("show_value"):
            columns.extend([
                {"label": _("Out Value"), "fieldname": "out_val", "fieldtype": "Float", "width": 80},
                {
                    "label": _("Valuation Rate"),
                    "fieldname": "val_rate",
                    "fieldtype": self.filters.valuation_field_type or "Currency",
                    "width": 90,
                    "convertible": "rate",
                    "options": "currency"
                    if self.filters.valuation_field_type == "Currency"
                    else None,
                },
            ])

        # columns.append({
        #     "label": _("Reserved Stock"),
        #     "fieldname": "reserved_stock",
        #     "fieldtype": "Float",
        #     "width": 80,
        #     "convertible": "qty",
        # })

        if self.filters.get("show_stock_ageing_data"):
            columns += [
                {"label": _("Average Age"), "fieldname": "average_age", "width": 100},
                {"label": _("Earliest Age"), "fieldname": "earliest_age", "width": 100},
                {"label": _("Latest Age"), "fieldname": "latest_age", "width": 100},
            ]

        if self.filters.get("show_variant_attributes"):
            # Specific order: Color, Size, Brand, Season, Info
            ordered_attributes = ["Color", "Size", "Brand", "Season", "Info"]
            all_attributes = get_variants_attributes()
            
            # Add ordered attributes first
            for att_name in ordered_attributes:
                if att_name in all_attributes:
                    columns.append({"label": att_name, "fieldname": att_name, "width": 100})
            
            # Add any remaining attributes
            for att_name in all_attributes:
                if att_name not in ordered_attributes:
                    columns.append({"label": att_name, "fieldname": att_name, "width": 100})

        return columns

    def add_additional_uom_columns(self):
        if not self.filters.get("include_uom"):
            return

        conversion_factors = self.get_itemwise_conversion_factor()
        add_additional_uom_columns(self.columns, self.data, self.filters.include_uom, conversion_factors)

    def get_itemwise_conversion_factor(self):
        items = []
        if self.filters.item_code or self.filters.item_group:
            items = [d.item_code for d in self.data]

        table = frappe.qb.DocType("UOM Conversion Detail")
        query = (
            frappe.qb.from_(table)
            .select(
                table.conversion_factor,
                table.parent,
            )
            .where((table.parenttype == "Item") & (table.uom == self.filters.include_uom))
        )

        if items:
            query = query.where(table.parent.isin(items))

        result = query.run(as_dict=1)
        if not result:
            return {}

        return {d.parent: d.conversion_factor for d in result}

    def get_variant_values_for(self):
        """Returns variant values for items with database-level cleaning and white text styling for hidden values."""
        attribute_map = {}
        items = []
        if self.filters.item_code or self.filters.item_group:
            items = [d.item_code for d in self.data]

        # Use SQL query with CASE statement to clean at database level
        condition = ""
        if items:
            condition = f"AND parent IN ({', '.join(['%s'] * len(items))})"
            values = items
        else:
            values = []

        query = f"""
            SELECT 
                parent,
                attribute,
                CASE 
                    WHEN attribute_value IS NULL THEN ''
                    WHEN TRIM(attribute_value) = '' THEN ''
                    WHEN LOWER(TRIM(attribute_value)) IN ('none', 'nan', 'null' ) THEN ''
                    ELSE TRIM(attribute_value)
                END as cleaned_attribute_value
            FROM `tabItem Variant Attribute`
            WHERE 1=1 {condition}
        """

        attribute_info = frappe.db.sql(query, values, as_dict=True)

        # Define values to hide with white text styling
        hidden_values = ["Blank","(blank)"]  # Add more values as needed

        for attr in attribute_info:
            attribute_map.setdefault(attr["parent"], {})
            cleaned_value = attr["cleaned_attribute_value"]
            
            # Apply white text styling for hidden values
            if cleaned_value and cleaned_value in hidden_values:
                styled_value = f'<span style="color: white; cursor: help;" title="Hidden Value: {cleaned_value}">{cleaned_value}</span>'
                attribute_map[attr["parent"]].update({
                    attr["attribute"]: styled_value
                })
            else:
                attribute_map[attr["parent"]].update({
                    attr["attribute"]: cleaned_value
                })

        return attribute_map

    def get_opening_vouchers(self):
        opening_vouchers = {"Stock Entry": [], "Stock Reconciliation": []}

        se = frappe.qb.DocType("Stock Entry")
        sr = frappe.qb.DocType("Stock Reconciliation")

        vouchers_data = (
            frappe.qb.from_(
                (
                    frappe.qb.from_(se)
                    .select(se.name, Coalesce("Stock Entry").as_("voucher_type"))
                    .where((se.docstatus == 1) & (se.posting_date <= self.to_date) & (se.is_opening == "Yes"))
                )
                + (
                    frappe.qb.from_(sr)
                    .select(sr.name, Coalesce("Stock Reconciliation").as_("voucher_type"))
                    .where(
                        (sr.docstatus == 1)
                        & (sr.posting_date <= self.to_date)
                        & (sr.purpose == "Opening Stock")
                    )
                )
            ).select("voucher_type", "name")
        ).run(as_dict=True)

        if vouchers_data:
            for d in vouchers_data:
                opening_vouchers[d.voucher_type].append(d.name)

        return opening_vouchers

    @staticmethod
    def get_inventory_dimension_fields():
        return [dimension.fieldname for dimension in get_inventory_dimensions()]

    @staticmethod
    def get_opening_fifo_queue(report_data):
        opening_fifo_queue = report_data.get("opening_fifo_queue") or []
        for row in opening_fifo_queue:
            row[1] = getdate(row[1])

        return opening_fifo_queue


def filter_items_with_no_transactions(
    iwb_map, float_precision: float, inventory_dimensions: list | None = None
):
    pop_keys = []
    for group_by_key in iwb_map:
        qty_dict = iwb_map[group_by_key]

        no_transactions = True
        for key, val in qty_dict.items():
            if inventory_dimensions and key in inventory_dimensions:
                continue

            if key in [
                "item_code",
                "warehouse",
                "item_name",
                "item_group",
                "project",
                "stock_uom",
                "company",
                "opening_fifo_queue",
                "invoice_number",
                "currency",
            ]:
                continue

            val = flt(val, float_precision)
            qty_dict[key] = val
            if key != "val_rate" and val:
                no_transactions = False

        if no_transactions:
            pop_keys.append(group_by_key)

    for key in pop_keys:
        iwb_map.pop(key)

    return iwb_map


def get_variants_attributes() -> list[str]:
    """Return all item variant attributes."""
    return frappe.get_all("Item Attribute", pluck="name")


# Enhanced hooks functions for Stock Entry and Stock Reconciliation

def update_stock_ledger_invoice_number(doc, method):
    """
    Enhanced update function with improved mapping logic
    """
    if doc.doctype == "Stock Entry":
        update_from_stock_entry_enhanced(doc)
    elif doc.doctype == "Stock Reconciliation":
        update_from_stock_reconciliation_enhanced(doc)


def update_from_stock_entry_enhanced(stock_entry):
    """Enhanced Stock Entry processing with improved sequential mapping"""
    
    # Get Stock Ledger Entries in creation order
    stock_ledger_entries = frappe.db.sql("""
        SELECT name, item_code, warehouse, posting_date, posting_time, 
               actual_qty, qty_after_transaction, voucher_detail_no, creation
        FROM `tabStock Ledger Entry`
        WHERE voucher_type = 'Stock Entry' 
        AND voucher_no = %s
        ORDER BY posting_date, posting_time, creation
    """, stock_entry.name, as_dict=1)
    
    # Create direct mapping from voucher_detail_no to invoice_number
    detail_to_invoice = {}
    for item in stock_entry.items:
        detail_to_invoice[item.name] = item.custom_invoice_number
    
    # Create sequential mapping for fallback
    item_sequences = defaultdict(list)
    for item in stock_entry.items:
        # For each item, store all its variations with invoice numbers
        sequence_key = f"{item.item_code}_{item.s_warehouse or ''}_{item.t_warehouse or ''}"
        item_sequences[sequence_key].append({
            'invoice_number': item.custom_invoice_number,
            'qty': item.qty,
            'idx': item.idx,
            'detail_name': item.name,
            'transfer_qty': item.transfer_qty or item.qty
        })
    
    # Sort sequences by idx to maintain order
    for key in item_sequences:
        item_sequences[key].sort(key=lambda x: x['idx'])
    
    # Process each Stock Ledger Entry
    for sle in stock_ledger_entries:
        invoice_number = None
        
        # Method 1: Direct mapping using voucher_detail_no (most reliable)
        if sle.voucher_detail_no and sle.voucher_detail_no in detail_to_invoice:
            invoice_number = detail_to_invoice[sle.voucher_detail_no]
        
        # Method 2: Sequential mapping based on item pattern
        if not invoice_number:
            # Determine the sequence key based on transaction direction
            if sle.actual_qty > 0:  # Incoming to warehouse
                sequence_key = f"{sle.item_code}__{sle.warehouse}"  # Target warehouse
            else:  # Outgoing from warehouse
                sequence_key = f"{sle.item_code}_{sle.warehouse}_"  # Source warehouse
            
            # Find matching sequence key
            matching_key = None
            for key in item_sequences:
                if (sle.actual_qty > 0 and key.endswith(f"_{sle.warehouse}")) or \
                   (sle.actual_qty < 0 and key.startswith(f"{sle.item_code}_{sle.warehouse}_")):
                    matching_key = key
                    break
            
            if matching_key and item_sequences[matching_key]:
                # Get the next item in sequence
                item_data = item_sequences[matching_key].pop(0)
                invoice_number = item_data['invoice_number']
        
        # Method 3: Fallback - find any remaining item with same item_code
        if not invoice_number:
            for key in list(item_sequences.keys()):
                if key.startswith(sle.item_code) and item_sequences[key]:
                    item_data = item_sequences[key].pop(0)
                    invoice_number = item_data['invoice_number']
                    break
        
        # Update Stock Ledger Entry
        if invoice_number:
            frappe.db.set_value(
                "Stock Ledger Entry",
                sle.name,
                "custom_invoice_number",
                invoice_number,
                update_modified=False
            )
        else:
            # Log missing mapping for debugging
            frappe.log_error(
                f"No invoice number mapping found for SLE {sle.name}, Item: {sle.item_code}, Warehouse: {sle.warehouse}",
                "Stock Entry Invoice Mapping"
            )


def update_from_stock_reconciliation_enhanced(stock_reconciliation):
    """Enhanced Stock Reconciliation processing"""
    
    # Get Stock Ledger Entries with voucher_detail_no
    stock_ledger_entries = frappe.db.sql("""
        SELECT name, item_code, warehouse, actual_qty, voucher_detail_no
        FROM `tabStock Ledger Entry`
        WHERE voucher_type = 'Stock Reconciliation' 
        AND voucher_no = %s
        ORDER BY creation
    """, stock_reconciliation.name, as_dict=1)
    
    # Create mapping with detail names
    detail_invoice_map = {}
    sequential_map = defaultdict(list)
    
    for item in stock_reconciliation.items:
        detail_invoice_map[item.name] = item.custom_invoice_number
        
        # Also create sequential mapping as backup
        key = f"{item.item_code}_{item.warehouse}"
        sequential_map[key].append({
            'invoice_number': item.custom_invoice_number,
            'idx': item.idx,
            'detail_name': item.name
        })
    
    # Update Stock Ledger Entries
    for sle in stock_ledger_entries:
        invoice_number = None
        
        # Try direct mapping with voucher_detail_no
        if sle.voucher_detail_no and sle.voucher_detail_no in detail_invoice_map:
            invoice_number = detail_invoice_map[sle.voucher_detail_no]
        
        # Fallback to sequential mapping
        if not invoice_number:
            key = f"{sle.item_code}_{sle.warehouse}"
            if key in sequential_map and sequential_map[key]:
                item_data = sequential_map[key].pop(0)
                invoice_number = item_data['invoice_number']
        
        # Update if invoice number found
        if invoice_number:
            frappe.db.set_value(
                "Stock Ledger Entry",
                sle.name,
                "custom_invoice_number",
                invoice_number,
                update_modified=False
            )


# Validation and utility functions

def validate_invoice_balance_consistency():
    """
    Validation function to check if invoice-level balances match item totals
    """
    validation_query = """
        WITH invoice_balances AS (
            SELECT 
                item_code,
                warehouse,
                custom_invoice_number,
                SUM(actual_qty) as invoice_balance
            FROM `tabStock Ledger Entry`
            WHERE is_cancelled = 0
            AND custom_invoice_number IS NOT NULL
            AND custom_invoice_number != ''
            GROUP BY item_code, warehouse, custom_invoice_number
        ),
        item_totals AS (
            SELECT 
                item_code,
                warehouse,
                SUM(actual_qty) as total_balance
            FROM `tabStock Ledger Entry`
            WHERE is_cancelled = 0
            GROUP BY item_code, warehouse
        ),
        invoice_totals AS (
            SELECT 
                item_code,
                warehouse,
                SUM(invoice_balance) as invoice_sum
            FROM invoice_balances
            GROUP BY item_code, warehouse
        )
        SELECT 
            it.item_code,
            it.warehouse,
            it.total_balance,
            COALESCE(int.invoice_sum, 0) as invoice_sum,
            (it.total_balance - COALESCE(int.invoice_sum, 0)) as difference
        FROM item_totals it
        LEFT JOIN invoice_totals int ON it.item_code = int.item_code AND it.warehouse = int.warehouse
        WHERE ABS(it.total_balance - COALESCE(int.invoice_sum, 0)) > 0.001
    """
    
    inconsistencies = frappe.db.sql(validation_query, as_dict=1)
    
    if inconsistencies:
        frappe.log_error(
            f"Invoice balance inconsistencies found: {inconsistencies}",
            "Stock Balance Validation"
        )
    
    return inconsistencies


def correct_existing_stock_ledger_invoice_numbers():
    """
    Function to correct invoice numbers for existing Stock Ledger Entries
    """
    # Get all Stock Entries with custom_invoice_number
    stock_entries = frappe.db.sql("""
        SELECT DISTINCT parent as name
        FROM `tabStock Entry Detail`
        WHERE custom_invoice_number IS NOT NULL
        AND custom_invoice_number != ''
    """, as_dict=1)
    
    corrected_count = 0
    for se in stock_entries:
        doc = frappe.get_doc("Stock Entry", se.name)
        if doc.docstatus == 1:  # Only process submitted entries
            # Clear existing invoice numbers
            frappe.db.sql("""
                UPDATE `tabStock Ledger Entry`
                SET custom_invoice_number = NULL
                WHERE voucher_type = 'Stock Entry'
                AND voucher_no = %s
            """, se.name)
            
            # Reapply mapping
            update_from_stock_entry_enhanced(doc)
            corrected_count += 1
    
    # Get all Stock Reconciliations
    stock_reconciliations = frappe.db.sql("""
        SELECT DISTINCT parent as name
        FROM `tabStock Reconciliation Item`
        WHERE custom_invoice_number IS NOT NULL
        AND custom_invoice_number != ''
    """, as_dict=1)
    
    for sr in stock_reconciliations:
        doc = frappe.get_doc("Stock Reconciliation", sr.name)
        if doc.docstatus == 1:
            # Clear existing invoice numbers
            frappe.db.sql("""
                UPDATE `tabStock Ledger Entry`
                SET custom_invoice_number = NULL
                WHERE voucher_type = 'Stock Reconciliation'
                AND voucher_no = %s
            """, sr.name)
            
            # Reapply mapping
            update_from_stock_reconciliation_enhanced(doc)
            corrected_count += 1
    
    frappe.db.commit()
    return corrected_count


def generate_invoice_balance_report(item_code=None, warehouse=None, from_date=None, to_date=None):
    """
    Generate detailed balance report showing both total and invoice-wise balances
    """
    conditions = ["sle.is_cancelled = 0"]
    values = []
    
    if item_code:
        conditions.append("sle.item_code = %s")
        values.append(item_code)
    
    if warehouse:
        conditions.append("sle.warehouse = %s")
        values.append(warehouse)
    
    if from_date:
        conditions.append("sle.posting_date >= %s")
        values.append(from_date)
    
    if to_date:
        conditions.append("sle.posting_date <= %s")
        values.append(to_date)
    
    where_clause = " AND ".join(conditions)
    
    query = f"""
        WITH invoice_wise_balance AS (
            SELECT 
                sle.item_code,
                sle.warehouse,
                sle.custom_invoice_number,
                SUM(sle.actual_qty) as invoice_balance,
                COUNT(*) as transaction_count
            FROM `tabStock Ledger Entry` sle
            WHERE {where_clause}
            AND sle.custom_invoice_number IS NOT NULL
            AND sle.custom_invoice_number != ''
            GROUP BY sle.item_code, sle.warehouse, sle.custom_invoice_number
        ),
        total_balance AS (
            SELECT 
                sle.item_code,
                sle.warehouse,
                SUM(sle.actual_qty) as total_balance,
                COUNT(*) as total_transactions
            FROM `tabStock Ledger Entry` sle
            WHERE {where_clause}
            GROUP BY sle.item_code, sle.warehouse
        ),
        invoice_summary AS (
            SELECT 
                item_code,
                warehouse,
                SUM(invoice_balance) as sum_of_invoices,
                COUNT(DISTINCT custom_invoice_number) as distinct_invoices
            FROM invoice_wise_balance
            GROUP BY item_code, warehouse
        )
        SELECT 
            tb.item_code,
            tb.warehouse,
            tb.total_balance,
            COALESCE(ins.sum_of_invoices, 0) as sum_of_invoices,
            (tb.total_balance - COALESCE(ins.sum_of_invoices, 0)) as difference,
            COALESCE(ins.distinct_invoices, 0) as distinct_invoices,
            tb.total_transactions,
            -- Detail breakdown
            GROUP_CONCAT(
                CONCAT(iwb.custom_invoice_number, ':', iwb.invoice_balance, '(', iwb.transaction_count, ')')
                SEPARATOR ' | '
            ) as invoice_breakdown
        FROM total_balance tb
        LEFT JOIN invoice_summary ins ON tb.item_code = ins.item_code AND tb.warehouse = ins.warehouse
        LEFT JOIN invoice_wise_balance iwb ON tb.item_code = iwb.item_code AND tb.warehouse = iwb.warehouse
        GROUP BY tb.item_code, tb.warehouse, tb.total_balance, ins.sum_of_invoices, ins.distinct_invoices, tb.total_transactions
        ORDER BY ABS(tb.total_balance - COALESCE(ins.sum_of_invoices, 0)) DESC, tb.item_code, tb.warehouse
    """
    
    return frappe.db.sql(query, values, as_dict=1)