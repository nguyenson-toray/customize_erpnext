# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import copy
from collections import defaultdict

import frappe
from frappe import _
from frappe.query_builder.functions import CombineDatetime, Sum
from frappe.utils import cint, flt, get_datetime

# Handle inventory dimensions import - may not exist in all ERPNext versions
try:
	from erpnext.stock.doctype.inventory_dimension.inventory_dimension import get_inventory_dimensions
except ImportError:
	def get_inventory_dimensions():
		return []
from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos
from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import get_stock_balance_for
from erpnext.stock.doctype.warehouse.warehouse import apply_warehouse_filter
from erpnext.stock.utils import (
	is_reposting_item_valuation_in_progress,
	update_included_uom_in_report,
)


def execute(filters=None):
	is_reposting_item_valuation_in_progress()
	include_uom = filters.get("include_uom")
	columns = get_columns(filters)
	items = get_items(filters)
	sl_entries = get_stock_ledger_entries(filters, items)
	item_details = get_item_details(items, sl_entries, include_uom, filters)
	opening_row = get_opening_balance(filters, columns, sl_entries)

	precision = cint(frappe.db.get_single_value("System Settings", "float_precision"))

	data = []
	conversion_factors = []
	if opening_row:
		data.append(opening_row)
		conversion_factors.append(0)

	actual_qty = 0
	if opening_row:
		actual_qty = opening_row.get("qty_after_transaction")

	inventory_dimension_filters_applied = check_inventory_dimension_filters_applied(filters)

	# Get variant values if show_variant_attributes is enabled
	variant_values = {}
	if filters.get("show_variant_attributes"):
		variant_values = get_variant_values_for(sl_entries)

	for sle in sl_entries:
		item_detail = item_details[sle.item_code]
		sle.update(item_detail)

		# Add invoice number from either source
		invoice_number = sle.get("se_detail_invoice_number") or sle.get("sr_custom_invoice_number")
		sle["custom_invoice_number"] = invoice_number

		# Add variant attributes if enabled
		if filters.get("show_variant_attributes") and variant_values.get(sle.item_code):
			variant_data = variant_values.get(sle.item_code)
			# Filter out None, empty values, and "nan" values
			clean_variant_data = {}
			for k, v in variant_data.items():
				if v and v != "nan" and str(v).lower() not in ["nan", "none", ""]:
					clean_variant_data[k] = v
			if clean_variant_data:
				sle.update(clean_variant_data)

		if inventory_dimension_filters_applied:
			actual_qty += flt(sle.actual_qty, precision)

			if sle.voucher_type == "Stock Reconciliation" and not sle.actual_qty:
				actual_qty = sle.qty_after_transaction

			sle.update({"qty_after_transaction": actual_qty})

		sle.update({"in_qty": max(sle.actual_qty, 0), "out_qty": min(sle.actual_qty, 0)})

		data.append(sle)

		if include_uom:
			conversion_factors.append(item_detail.conversion_factor)

	update_included_uom_in_report(columns, data, include_uom, conversion_factors)
	return columns, data


def get_segregated_bundle_entries(sle, bundle_details, batch_balance_dict, filters):
	segregated_entries = []
	qty_before_transaction = sle.qty_after_transaction - sle.actual_qty

	for row in bundle_details:
		new_sle = copy.deepcopy(sle)
		new_sle.update(row)
		new_sle.update(
			{
				"in_qty": row.qty if row.qty > 0 else 0,
				"out_qty": row.qty if row.qty < 0 else 0,
				"qty_after_transaction": qty_before_transaction + row.qty,
			}
		)

		if filters.get("batch_no") and row.batch_no:
			if not batch_balance_dict.get(row.batch_no):
				batch_balance_dict[row.batch_no] = [0]

			batch_balance_dict[row.batch_no][0] += row.qty

			new_sle.update(
				{
					"qty_after_transaction": batch_balance_dict[row.batch_no][0],
				}
			)

		qty_before_transaction += row.qty

		segregated_entries.append(new_sle)

	return segregated_entries


def get_serial_batch_bundle_details(sl_entries, filters=None):
	bundle_details = []
	for sle in sl_entries:
		if sle.serial_and_batch_bundle:
			bundle_details.append(sle.serial_and_batch_bundle)

	if not bundle_details:
		return frappe._dict({})

	query_filers = {"parent": ("in", bundle_details)}
	if filters.get("batch_no"):
		query_filers["batch_no"] = filters.batch_no

	_bundle_details = frappe._dict({})
	batch_entries = frappe.get_all(
		"Serial and Batch Entry",
		filters=query_filers,
		fields=["parent", "qty", "batch_no", "serial_no"],
		order_by="parent, idx",
	)
	for entry in batch_entries:
		_bundle_details.setdefault(entry.parent, []).append(entry)

	return _bundle_details


def update_available_serial_nos(available_serial_nos, sle):
	serial_nos = get_serial_nos(sle.serial_no)
	key = (sle.item_code, sle.warehouse)
	if key not in available_serial_nos:
		stock_balance = get_stock_balance_for(
			sle.item_code, sle.warehouse, sle.posting_date, sle.posting_time
		)
		serials = get_serial_nos(stock_balance["serial_nos"]) if stock_balance["serial_nos"] else []
		available_serial_nos.setdefault(key, serials)

	existing_serial_no = available_serial_nos[key]
	for sn in serial_nos:
		if sle.actual_qty > 0:
			if sn in existing_serial_no:
				existing_serial_no.remove(sn)
			else:
				existing_serial_no.append(sn)
		else:
			if sn in existing_serial_no:
				existing_serial_no.remove(sn)
			else:
				existing_serial_no.append(sn)

	sle.balance_serial_no = "\n".join(existing_serial_no)


def get_variant_values_for(sl_entries):
	"""Get variant attribute values for items in stock ledger entries"""
	attribute_map = {}
	items = list(set(d.item_code for d in sl_entries)) if sl_entries else []
	
	if not items:
		return attribute_map

	filters = {"parent": ("in", items)}
	attribute_info = frappe.get_all(
		"Item Variant Attribute",
		fields=["parent", "attribute", "attribute_value"],
		filters=filters,
	)

	for attr in attribute_info:
		# Skip if attribute_value is None, empty, or "nan"
		attr_value = attr.get("attribute_value")
		if not attr_value or str(attr_value).lower() in ["nan", "none", ""]:
			continue
			
		attribute_map.setdefault(attr["parent"], {})
		attribute_map[attr["parent"]].update({attr["attribute"]: attr_value})

	return attribute_map


def get_variants_attributes():
	"""Get all item attribute names"""
	return frappe.get_all("Item Attribute", pluck="name")


def get_variant_attributes():
	"""Get all item variant attributes"""
	return frappe.get_all(
		"Item Attribute", 
		fields=["name", "item_attribute_name"], 
		order_by="name"
	)


def get_columns(filters):
	columns = [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Datetime", "width": 150},
		{
			"label": _("Item"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 100,
		},
		{"label": _("Item Name"), "fieldname": "item_name", "width": 100},
		{
			"label": _("Stock UOM"),
			"fieldname": "stock_uom",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 90,
		},
	]

	try:
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
	except:
		pass

	columns.extend(
		[
			{
				"label": _("In Qty"),
				"fieldname": "in_qty",
				"fieldtype": "Float",
				"width": 80,
				"convertible": "qty",
			},
			{
				"label": _("Out Qty"),
				"fieldname": "out_qty",
				"fieldtype": "Float",
				"width": 80,
				"convertible": "qty",
			},
			{
				"label": _("Balance Qty"),
				"fieldname": "qty_after_transaction",
				"fieldtype": "Float",
				"width": 100,
				"convertible": "qty",
			},
			{
				"label": _("Warehouse"),
				"fieldname": "warehouse",
				"fieldtype": "Link",
				"options": "Warehouse",
				"width": 150,
			},
			{
				"label": _("Invoice Number"),
				"fieldname": "custom_invoice_number",
				"fieldtype": "Data",
				"width": 160,
			},
			{
				"label": _("Item Group"),
				"fieldname": "item_group",
				"fieldtype": "Link",
				"options": "Item Group",
				"width": 100,
			},
			{"label": _("Description"), "fieldname": "description", "width": 200},
			{"label": _("Voucher Type"), "fieldname": "voucher_type", "width": 110},
			{
				"label": _("Voucher #"),
				"fieldname": "voucher_no",
				"fieldtype": "Dynamic Link",
				"options": "voucher_type",
				"width": 100,
			},
			
			{
				"label": _("Note"),
				"fieldname": "note",
				"fieldtype": "Text",
				"width": 200,
			},
		]
	)

	# Add variant attribute columns if enabled
	if filters.get("show_variant_attributes"):
		# Define fixed order for variant attributes
		fixed_order_attributes = ["Color", "Size", "Brand", "Season", "Info"]
		variant_attributes = get_variants_attributes()
		
		# Add attributes in fixed order first
		for attr_name in fixed_order_attributes:
			if attr_name in variant_attributes:
				columns.append({
					"label": _(attr_name),
					"fieldname": attr_name,
					"fieldtype": "Data",
					"width": 100,
				})
		
		# Add any remaining attributes not in the fixed order
		for attr_name in variant_attributes:
			if attr_name not in fixed_order_attributes:
				columns.append({
					"label": _(attr_name),
					"fieldname": attr_name,
					"fieldtype": "Data",
					"width": 100,
				})

	return columns


def get_stock_ledger_entries(filters, items):
	from_date = get_datetime(filters.from_date + " 00:00:00")
	to_date = get_datetime(filters.to_date + " 23:59:59")

	sle = frappe.qb.DocType("Stock Ledger Entry")
	se = frappe.qb.DocType("Stock Entry")
	se_detail = frappe.qb.DocType("Stock Entry Detail")
	sr_item = frappe.qb.DocType("Stock Reconciliation Item")
	
	query = (
		frappe.qb.from_(sle)
		.left_join(se)
		.on((sle.voucher_type == "Stock Entry") & (sle.voucher_no == se.name))
		.left_join(se_detail)
		.on(
			(sle.voucher_type == "Stock Entry") 
			& (sle.voucher_no == se_detail.parent)
			& (sle.item_code == se_detail.item_code)
		)
		.left_join(sr_item)
		.on(
			(sle.voucher_type == "Stock Reconciliation")
			& (sle.voucher_no == sr_item.parent)
			& (sle.item_code == sr_item.item_code)
			& (sle.warehouse == sr_item.warehouse)
		)
		.select(
			sle.item_code,
			sle.posting_datetime.as_("date"),
			sle.warehouse,
			sle.posting_date,
			sle.posting_time,
			sle.actual_qty,
			sle.company,
			sle.voucher_type,
			sle.qty_after_transaction,
			sle.voucher_no,
			se.custom_note.as_("note"),
			se_detail.custom_invoice_number.as_("se_detail_invoice_number"),
			sr_item.custom_invoice_number.as_("sr_custom_invoice_number"),
		)
		.where((sle.docstatus < 2) & (sle.is_cancelled == 0) & (sle.posting_datetime[from_date:to_date]))
		.orderby(sle.posting_datetime)
		.orderby(sle.creation)
	)

	inventory_dimension_fields = get_inventory_dimension_fields()
	if inventory_dimension_fields:
		for fieldname in inventory_dimension_fields:
			query = query.select(sle[fieldname])
			if fieldname in filters and filters.get(fieldname):
				query = query.where(sle[fieldname].isin(filters.get(fieldname)))

	if items:
		query = query.where(sle.item_code.isin(items))

	for field in ["voucher_no", "company"]:
		if filters.get(field) and field not in inventory_dimension_fields:
			query = query.where(sle[field] == filters.get(field))

	# Filter by Stock Entry Type
	if filters.get("stock_entry_type"):
		query = query.where(
			(sle.voucher_type == "Stock Entry") & 
			(se.stock_entry_type == filters.get("stock_entry_type"))
		)

	query = apply_warehouse_filter(query, sle, filters)

	return query.run(as_dict=True)


def get_serial_and_batch_bundles(filters):
	SBB = frappe.qb.DocType("Serial and Batch Bundle")
	SBE = frappe.qb.DocType("Serial and Batch Entry")

	query = (
		frappe.qb.from_(SBE)
		.inner_join(SBB)
		.on(SBE.parent == SBB.name)
		.select(SBE.parent)
		.where(
			(SBB.docstatus == 1)
			& (SBB.has_batch_no == 1)
			& (SBB.voucher_no.notnull())
			& (SBE.batch_no == filters.batch_no)
		)
	)

	return query.run(pluck=SBE.parent)


def get_inventory_dimension_fields():
	try:
		return [dimension.fieldname for dimension in get_inventory_dimensions()]
	except:
		return []


def get_items(filters):
	item = frappe.qb.DocType("Item")
	query = frappe.qb.from_(item).select(item.name)
	conditions = []

	if item_code := filters.get("item_code"):
		conditions.append(item.name == item_code)
	else:
		if brand := filters.get("brand"):
			conditions.append(item.brand == brand)
		if item_group := filters.get("item_group"):
			if condition := get_item_group_condition(item_group, item):
				conditions.append(condition)

	items = []
	if conditions:
		for condition in conditions:
			query = query.where(condition)
		items = [r[0] for r in query.run()]

	return items


def get_item_details(items, sl_entries, include_uom, filters):
	item_details = {}
	if not items:
		items = list(set(d.item_code for d in sl_entries))

	if not items:
		return item_details

	item = frappe.qb.DocType("Item")
	query = (
		frappe.qb.from_(item)
		.select(item.name, item.item_name, item.description, item.item_group, item.stock_uom)
		.where(item.name.isin(items))
	)

	if include_uom:
		ucd = frappe.qb.DocType("UOM Conversion Detail")
		query = (
			query.left_join(ucd)
			.on((ucd.parent == item.name) & (ucd.uom == include_uom))
			.select(ucd.conversion_factor)
		)

	res = query.run(as_dict=True)

	for item in res:
		item_details.setdefault(item.name, item)

	return item_details


def get_sle_conditions(filters):
	conditions = []
	if filters.get("warehouse"):
		warehouse_condition = get_warehouse_condition(filters.get("warehouse"))
		if warehouse_condition:
			conditions.append(warehouse_condition)
	if filters.get("voucher_no"):
		conditions.append("voucher_no=%(voucher_no)s")
	if filters.get("batch_no"):
		conditions.append("batch_no=%(batch_no)s")
	if filters.get("project"):
		conditions.append("project=%(project)s")

	for dimension in get_inventory_dimensions():
		if filters.get(dimension.fieldname):
			conditions.append(f"{dimension.fieldname} in %({dimension.fieldname})s")

	return "and {}".format(" and ".join(conditions)) if conditions else ""


def get_opening_balance(filters, columns, sl_entries):
	if not (filters.item_code and filters.warehouse and filters.from_date):
		return

	from erpnext.stock.stock_ledger import get_previous_sle

	# Apply stock entry type filter if specified
	warehouse_condition = get_warehouse_condition(filters.warehouse)
	
	# Get previous SLE considering stock entry type filter
	if filters.get("stock_entry_type"):
		# Query with stock entry type filter
		sle_table = frappe.qb.DocType("Stock Ledger Entry")
		se_table = frappe.qb.DocType("Stock Entry")
		
		query = (
			frappe.qb.from_(sle_table)
			.left_join(se_table)
			.on((sle_table.voucher_type == "Stock Entry") & (sle_table.voucher_no == se_table.name))
			.select(
				sle_table.qty_after_transaction,
				sle_table.posting_date,
				sle_table.posting_time
			)
			.where(
				(sle_table.item_code == filters.item_code) &
				(sle_table.posting_date < filters.from_date) &
				(sle_table.is_cancelled == 0) &
				(sle_table.docstatus < 2) &
				(sle_table.voucher_type == "Stock Entry") &
				(se_table.stock_entry_type == filters.get("stock_entry_type"))
			)
			.orderby(sle_table.posting_date, order=frappe.qb.desc)
			.orderby(sle_table.posting_time, order=frappe.qb.desc)
			.orderby(sle_table.creation, order=frappe.qb.desc)
			.limit(1)
		)
		
		if warehouse_condition:
			# Apply warehouse condition manually since we can't use the helper with custom query
			warehouse_details = frappe.db.get_value("Warehouse", filters.warehouse, ["lft", "rgt"], as_dict=1)
			if warehouse_details:
				wh_table = frappe.qb.DocType("Warehouse")
				query = query.where(
					frappe.qb.from_(wh_table)
					.select(wh_table.name)
					.where(
						(wh_table.lft >= warehouse_details.lft) &
						(wh_table.rgt <= warehouse_details.rgt) &
						(sle_table.warehouse == wh_table.name)
					).exists()
				)
		
		result = query.run(as_dict=True)
		last_entry = result[0] if result else {}
	else:
		last_entry = get_previous_sle(
			{
				"item_code": filters.item_code,
				"warehouse_condition": warehouse_condition,
				"posting_date": filters.from_date,
				"posting_time": "00:00:00",
			}
		)

	# check if any SLEs are actually Opening Stock Reconciliation
	for sle in list(sl_entries):
		if (
			sle.get("voucher_type") == "Stock Reconciliation"
			and sle.posting_date == filters.from_date
			and frappe.db.get_value("Stock Reconciliation", sle.voucher_no, "purpose") == "Opening Stock"
		):
			last_entry = sle
			sl_entries.remove(sle)

	row = {
		"item_code": _("'Opening'"),
		"qty_after_transaction": last_entry.get("qty_after_transaction", 0),
	}

	return row


def get_warehouse_condition(warehouse):
	warehouse_details = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt"], as_dict=1)
	if warehouse_details:
		return f" exists (select name from `tabWarehouse` wh \
			where wh.lft >= {warehouse_details.lft} and wh.rgt <= {warehouse_details.rgt} and warehouse = wh.name)"

	return ""


def get_item_group_condition(item_group, item_table=None):
	item_group_details = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"], as_dict=1)
	if item_group_details:
		if item_table:
			ig = frappe.qb.DocType("Item Group")
			return item_table.item_group.isin(
				frappe.qb.from_(ig)
				.select(ig.name)
				.where(
					(ig.lft >= item_group_details.lft)
					& (ig.rgt <= item_group_details.rgt)
					& (item_table.item_group == ig.name)
				)
			)
		else:
			return f"item.item_group in (select ig.name from `tabItem Group` ig \
				where ig.lft >= {item_group_details.lft} and ig.rgt <= {item_group_details.rgt} and item.item_group = ig.name)"


def check_inventory_dimension_filters_applied(filters) -> bool:
	try:
		for dimension in get_inventory_dimensions():
			if dimension.fieldname in filters and filters.get(dimension.fieldname):
				return True
	except:
		pass
	return False