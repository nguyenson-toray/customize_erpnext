# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


from collections.abc import Iterator
from operator import itemgetter

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, get_datetime

from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos

Filters = frappe._dict


def execute(filters: Filters = None) -> tuple:
	to_date = filters["to_date"]
	filters.ranges = [num.strip() for num in filters.range.split(",") if num.strip().isdigit()]
	columns = get_columns(filters)

	item_details = FIFOSlots(filters).generate()
	data = format_report_data(filters, item_details, to_date)

	chart_data = get_chart_data(data, filters)

	return columns, data, None, chart_data


def format_report_data(filters: Filters, item_details: dict, to_date: str) -> list[dict]:
	"Returns ordered, formatted data with ranges."
	_func = itemgetter(1)
	data = []

	precision = cint(frappe.db.get_single_value("System Settings", "float_precision", cache=True))

	for key, item_dict in item_details.items():
		if not flt(item_dict.get("total_qty"), precision):
			continue

		earliest_age, latest_age = 0, 0
		details = item_dict["details"]

		fifo_queue = sorted(filter(_func, item_dict["fifo_queue"]), key=_func)

		if not fifo_queue:
			continue

		average_age = get_average_age(fifo_queue, to_date)
		earliest_age = date_diff(to_date, fifo_queue[0][1])
		latest_age = date_diff(to_date, fifo_queue[-1][1])
		range_values = get_range_age(filters, fifo_queue, to_date, item_dict)

		check_and_replace_valuations_if_moving_average(
			range_values, details.valuation_method, details.valuation_rate
		)

		# Get invoice number for this specific grouping
		invoice_number = get_invoice_number_for_key(key, filters)

		row = [details.name, details.item_name, details.description, details.item_group]

		# Add variant attributes if enabled
		if filters.get("show_variant_attributes"):
			variant_attributes = get_variant_attributes(details.name)
			row.extend(variant_attributes)

		if filters.get("show_warehouse_wise_stock"):
			row.append(details.warehouse)

		# Add Invoice Numbers column
		row.append(invoice_number)

		row.extend([
			flt(item_dict.get("total_qty"), precision),
			average_age,
		])

		# Add range values based on show_value setting
		row.extend(range_values)

		row.extend([
			earliest_age,
			latest_age,
			details.stock_uom,
		])

		data.append(row)

	return data


def get_invoice_number_for_key(key, filters):
	"""Get invoice number based on key structure"""
	if filters.get("show_warehouse_wise_stock"):
		# Key: (item_code, warehouse, invoice_number)
		return key[2] if len(key) > 2 else ""
	else:
		# Key: (item_code, invoice_number)
		return key[1] if len(key) > 1 else ""


def get_variant_attributes(item_code):
	"""Get variant attributes for the item if it's a variant"""
	try:
		# Get item variant attributes ordered by specific sequence
		variant_attrs = frappe.db.sql("""
			SELECT attribute, attribute_value 
			FROM `tabItem Variant Attribute`
			WHERE parent = %s
			ORDER BY FIELD(attribute, 'Color', 'Size', 'Brand', 'Season', 'Info'), idx
		""", item_code, as_dict=1)
		
		# Create a dict for easier lookup
		attr_dict = {attr.attribute: attr.attribute_value for attr in variant_attrs}
		
		# Define the order of attributes
		attribute_order = ['Color', 'Size', 'Brand', 'Season', 'Info']
		
		# Get values in the specified order
		attr_values = []
		for attr_name in attribute_order:
			value = attr_dict.get(attr_name, "")
			# Hide "Blank" or "(blank)" values by setting them to empty with special formatting
			if value.lower() in ["blank", "(blank)"]:
				value = f'<span style="color: white;">{value}</span>'
			attr_values.append(value)
		
		return attr_values  # Return all 5 attributes
	except Exception:
		return ["", "", "", "", ""]  # Return 5 empty strings for all attributes


def check_and_replace_valuations_if_moving_average(range_values, item_valuation_method, valuation_rate):
	if item_valuation_method == "Moving Average" or (
		not item_valuation_method
		and frappe.db.get_single_value("Stock Settings", "valuation_method") == "Moving Average"
	):
		if len(range_values) > 1:  # Ensure we have value columns
			for i in range(1, len(range_values), 2):  # Only process value columns (odd indices)
				if i < len(range_values):
					range_values[i] = range_values[i - 1] * valuation_rate


def get_average_age(fifo_queue: list, to_date: str) -> float:
	batch_age = age_qty = total_qty = 0.0
	for batch in fifo_queue:
		batch_age = date_diff(to_date, batch[1])

		if isinstance(batch[0], (int, float)):
			age_qty += batch_age * batch[0]
			total_qty += batch[0]
		else:
			age_qty += batch_age * 1
			total_qty += 1

	return flt(age_qty / total_qty, 2) if total_qty else 0.0


def get_range_age(filters: Filters, fifo_queue: list, to_date: str, item_dict: dict) -> list:
	precision = cint(frappe.db.get_single_value("System Settings", "float_precision", cache=True))
	
	# Calculate number of ranges + 1 (for above range)
	num_ranges = len(filters.ranges) + 1
	
	if filters.get("show_value"):
		# Each range has qty and value = 2 columns per range
		range_values = [0.0] * (num_ranges * 2)
	else:
		# Only quantity columns
		range_values = [0.0] * num_ranges

	for item in fifo_queue:
		age = flt(date_diff(to_date, item[1]))
		qty = flt(item[0]) if not item_dict["has_serial_no"] else 1.0
		stock_value = flt(item[2])

		range_index = None
		# Find which range this item belongs to
		for i, age_limit in enumerate(filters.ranges):
			if age <= flt(age_limit):
				range_index = i
				break
		
		if range_index is None:
			# Item is older than all ranges, put in last range
			range_index = len(filters.ranges)

		# Add to appropriate range
		if filters.get("show_value"):
			qty_index = range_index * 2
			value_index = qty_index + 1
			if qty_index < len(range_values):
				range_values[qty_index] = flt(range_values[qty_index] + qty, precision)
			if value_index < len(range_values):
				range_values[value_index] = flt(range_values[value_index] + stock_value, precision)
		else:
			if range_index < len(range_values):
				range_values[range_index] = flt(range_values[range_index] + qty, precision)

	return range_values


def get_columns(filters: Filters) -> list[dict]:
	columns = [
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 100,
		},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 100},
		{"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 200},
		{
			"label": _("Item Group"),
			"fieldname": "item_group",
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 100,
		},
	]

	# Add variant attribute columns if enabled
	if filters.get("show_variant_attributes"):
		columns.extend([
			{"label": _("Color"), "fieldname": "color", "fieldtype": "Data", "width": 80},
			{"label": _("Size"), "fieldname": "size", "fieldtype": "Data", "width": 80},
			{"label": _("Brand"), "fieldname": "brand", "fieldtype": "Data", "width": 80},
			{"label": _("Season"), "fieldname": "season", "fieldtype": "Data", "width": 80},
			{"label": _("Info"), "fieldname": "info", "fieldtype": "Data", "width": 100},
		])

	if filters.get("show_warehouse_wise_stock"):
		columns.append({
			"label": _("Warehouse"),
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 100,
		})

	# Add Invoice Numbers column
	columns.append({
		"label": _("Invoice Numbers"),
		"fieldname": "invoice_numbers", 
		"fieldtype": "Data",
		"width": 150
	})

	columns.extend([
		{"label": _("Available Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 100},
		{"label": _("Average Age"), "fieldname": "average_age", "fieldtype": "Float", "width": 100},
	])
	
	# Add range columns
	setup_ageing_columns(filters, columns)
	
	columns.extend([
		{"label": _("Earliest"), "fieldname": "earliest", "fieldtype": "Int", "width": 80},
		{"label": _("Latest"), "fieldname": "latest", "fieldtype": "Int", "width": 80},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 100},
	])

	return columns


def get_chart_data(data: list, filters: Filters) -> dict:
	if not data:
		return []

	labels, datapoints = [], []

	if filters.get("show_warehouse_wise_stock"):
		return {}

	# Calculate the correct index for average_age column
	# Base columns: Item Code, Item Name, Description, Item Group = 4
	average_age_index = 4
	
	# Add variant attributes columns if enabled
	if filters.get("show_variant_attributes"):
		average_age_index += 5  # Color, Size, Brand, Season, Info
	
	# Add warehouse column if enabled  
	if filters.get("show_warehouse_wise_stock"):
		average_age_index += 1
		
	# Add invoice numbers column
	average_age_index += 1
	
	# Add available qty column
	average_age_index += 1
	
	# Now average_age_index points to the Average Age column

	data.sort(key=lambda row: row[average_age_index], reverse=True)

	if len(data) > 10:
		data = data[:10]

	for row in data:
		labels.append(row[0])
		datapoints.append(row[average_age_index])

	return {
		"data": {"labels": labels, "datasets": [{"name": _("Average Age"), "values": datapoints}]},
		"type": "bar",
	}


def setup_ageing_columns(filters: Filters, columns: list):
	prev_range_value = 0
	ranges = []
	for range_val in filters.ranges:
		ranges.append(f"{prev_range_value} - {range_val}")
		prev_range_value = cint(range_val) + 1

	ranges.append(f"{prev_range_value} - Above")

	for i, label in enumerate(ranges):
		fieldname = "range" + str(i + 1)
		add_column(columns, label=_("Age ({0})").format(label), fieldname=fieldname)
		
		# Only add value columns if show_value is enabled
		if filters.get("show_value"):
			add_column(columns, label=_("Value ({0})").format(label), fieldname=fieldname + "value")


def add_column(columns: list, label: str, fieldname: str, fieldtype: str = "Float", width: int = 140):
	columns.append(dict(label=label, fieldname=fieldname, fieldtype=fieldtype, width=width))


class FIFOSlots:
	"Returns FIFO computed slots of inwarded stock as per date."

	def __init__(self, filters: dict | None = None, sle: list | None = None):
		self.item_details = {}
		self.transferred_item_details = {}
		self.serial_no_batch_purchase_details = {}
		self.filters = filters
		self.sle = sle

	def generate(self) -> dict:
		"""
		Returns dict of the foll.g structure:
		Key = Item A / (Item A, Warehouse A) / (Item A, Invoice A) / (Item A, Warehouse A, Invoice A)
		Key: {
		        'details' -> Dict: ** item details **,
		        'fifo_queue' -> List: ** list of lists containing entries/slots for existing stock,
		                consumed/updated and maintained via FIFO. **
		}
		"""

		try:
			from erpnext.stock.doctype.serial_and_batch_bundle.test_serial_and_batch_bundle import (
				get_serial_nos_from_bundle,
			)
		except ImportError:
			# Fallback if the import fails
			def get_serial_nos_from_bundle(bundle_name):
				return []

		stock_ledger_entries = self.sle

		bundle_wise_serial_nos = frappe._dict({})
		if stock_ledger_entries is None:
			bundle_wise_serial_nos = self.__get_bundle_wise_serial_nos()

		with frappe.db.unbuffered_cursor():
			if stock_ledger_entries is None:
				stock_ledger_entries = self.__get_stock_ledger_entries()

			for d in stock_ledger_entries:
				key, fifo_queue, transferred_item_key = self.__init_key_stores(d)

				if d.voucher_type == "Stock Reconciliation":
					# get difference in qty shift as actual qty
					prev_balance_qty = self.item_details[key].get("qty_after_transaction", 0)
					d.actual_qty = flt(d.qty_after_transaction) - flt(prev_balance_qty)
					
					# Always prioritize custom_receive_date over posting_date for age calculation
					if d.get("custom_receive_date"):
						d.posting_date = d.custom_receive_date

				serial_nos = get_serial_nos(d.serial_no) if d.serial_no else []
				if d.serial_and_batch_bundle and d.has_serial_no:
					if bundle_wise_serial_nos:
						serial_nos = bundle_wise_serial_nos.get(d.serial_and_batch_bundle) or []
					else:
						serial_nos = get_serial_nos_from_bundle(d.serial_and_batch_bundle) or []

				if d.actual_qty > 0:
					self.__compute_incoming_stock(d, fifo_queue, transferred_item_key, serial_nos)
				else:
					self.__compute_outgoing_stock(d, fifo_queue, transferred_item_key, serial_nos)

				self.__update_balances(d, key)

			# Note that stock_ledger_entries is an iterator, you can not reuse it like a list
			del stock_ledger_entries

		if not self.filters.get("show_warehouse_wise_stock"):
			# Always aggregate by (Item, Invoice) - keep separate entries for different invoice numbers
			self.item_details = self.__aggregate_details_by_item_and_invoice(self.item_details)

		return self.item_details

	def __init_key_stores(self, row: dict) -> tuple:
		"Initialise keys and FIFO Queue."

		# Always group by invoice number
		invoice_number = row.get("custom_invoice_number", "")
		if self.filters.get("show_warehouse_wise_stock"):
			key = (row.name, row.warehouse, invoice_number)
		else:
			key = (row.name, invoice_number)

		self.item_details.setdefault(key, {"details": row, "fifo_queue": []})
		fifo_queue = self.item_details[key]["fifo_queue"]

		transferred_item_key = (row.voucher_no, row.name, row.warehouse, row.get("custom_invoice_number", ""))
		self.transferred_item_details.setdefault(transferred_item_key, [])

		return key, fifo_queue, transferred_item_key

	def __compute_incoming_stock(self, row: dict, fifo_queue: list, transfer_key: tuple, serial_nos: list):
		"Update FIFO Queue on inward stock."

		transfer_data = self.transferred_item_details.get(transfer_key)
		if transfer_data:


			
			# inward/outward from same voucher, item & warehouse
			# eg: Repack with same item, Stock reco for batch item
			# consume transfer data and add stock to fifo queue
			self.__adjust_incoming_transfer_qty(transfer_data, fifo_queue, row)
		else:
			if not serial_nos and not row.get("has_serial_no"):
				if fifo_queue and flt(fifo_queue[0][0]) <= 0:
					# neutralize 0/negative stock by adding positive stock
					fifo_queue[0][0] += flt(row.actual_qty)
					fifo_queue[0][1] = row.posting_date
					fifo_queue[0][2] += flt(row.stock_value_difference)
					# Ensure slot has 4 elements
					if len(fifo_queue[0]) <= 3:
						fifo_queue[0].append(row.get("custom_invoice_number", ""))
					else:
						fifo_queue[0][3] = row.get("custom_invoice_number", "")
				else:
					fifo_queue.append([
						flt(row.actual_qty), 
						row.posting_date, 
						flt(row.stock_value_difference),
						row.get("custom_invoice_number", "")
					])
				return

			valuation = row.stock_value_difference / row.actual_qty if row.actual_qty else 0
			for serial_no in serial_nos:
				if self.serial_no_batch_purchase_details.get(serial_no):
					fifo_queue.append([
						serial_no, 
						self.serial_no_batch_purchase_details.get(serial_no), 
						valuation,
						row.get("custom_invoice_number", "")
					])
				else:
					self.serial_no_batch_purchase_details.setdefault(serial_no, row.posting_date)
					fifo_queue.append([
						serial_no, 
						row.posting_date, 
						valuation,
						row.get("custom_invoice_number", "")
					])

	def __compute_outgoing_stock(self, row: dict, fifo_queue: list, transfer_key: tuple, serial_nos: list):
		"Update FIFO Queue on outward stock."
		if serial_nos:
			fifo_queue[:] = [serial_no for serial_no in fifo_queue if serial_no[0] not in serial_nos]
			return

		qty_to_pop = abs(row.actual_qty)
		stock_value = abs(row.stock_value_difference)

		while qty_to_pop:
			slot = fifo_queue[0] if fifo_queue else [0, None, 0, ""]
			if 0 < flt(slot[0]) <= qty_to_pop:
				# qty to pop >= slot qty
				# if +ve and not enough or exactly same balance in current slot, consume whole slot
				qty_to_pop -= flt(slot[0])
				stock_value -= flt(slot[2])
				self.transferred_item_details[transfer_key].append(fifo_queue.pop(0))
			elif not fifo_queue:
				# negative stock, no balance but qty yet to consume
				fifo_queue.append([-(qty_to_pop), row.posting_date, -(stock_value), row.get("custom_invoice_number", "")])
				self.transferred_item_details[transfer_key].append([
					qty_to_pop, row.posting_date, stock_value, row.get("custom_invoice_number", "")
				])
				qty_to_pop = 0
				stock_value = 0
			else:
				# qty to pop < slot qty, ample balance
				# consume actual_qty from first slot
				slot[0] = flt(slot[0]) - qty_to_pop
				slot[2] = flt(slot[2]) - stock_value
				self.transferred_item_details[transfer_key].append([
					qty_to_pop, slot[1], stock_value, slot[3] if len(slot) > 3 else ""
				])
				qty_to_pop = 0
				stock_value = 0

	def __adjust_incoming_transfer_qty(self, transfer_data: dict, fifo_queue: list, row: dict):
		"Add previously removed stock back to FIFO Queue."
		transfer_qty_to_pop = flt(row.actual_qty)
		stock_value = flt(row.stock_value_difference)

		def add_to_fifo_queue(slot):
			if fifo_queue and flt(fifo_queue[0][0]) <= 0:
				# neutralize 0/negative stock by adding positive stock
				fifo_queue[0][0] += flt(slot[0])
				fifo_queue[0][1] = slot[1]
				fifo_queue[0][2] += flt(slot[2])
				# Ensure proper slot structure
				if len(fifo_queue[0]) <= 3:
					fifo_queue[0].append(slot[3] if len(slot) > 3 else "")
				else:
					fifo_queue[0][3] = slot[3] if len(slot) > 3 else ""
			else:
				fifo_queue.append(slot)

		while transfer_qty_to_pop:
			if transfer_data and 0 < transfer_data[0][0] <= transfer_qty_to_pop:
				# bucket qty is not enough, consume whole
				transfer_qty_to_pop -= transfer_data[0][0]
				stock_value -= transfer_data[0][2]
				add_to_fifo_queue(transfer_data.pop(0))
			elif not transfer_data:
				# transfer bucket is empty, extra incoming qty
				add_to_fifo_queue([
					transfer_qty_to_pop, 
					row.posting_date, 
					stock_value, 
					row.get("custom_invoice_number", "")
				])
				transfer_qty_to_pop = 0
				stock_value = 0
			else:
				# ample bucket qty to consume
				transfer_data[0][0] -= transfer_qty_to_pop
				transfer_data[0][2] -= stock_value
				add_to_fifo_queue([
					transfer_qty_to_pop, 
					transfer_data[0][1], 
					stock_value,
					transfer_data[0][3] if len(transfer_data[0]) > 3 else ""
				])
				transfer_qty_to_pop = 0
				stock_value = 0

	def __update_balances(self, row: dict, key: tuple | str):
		self.item_details[key]["qty_after_transaction"] = row.qty_after_transaction

		if "total_qty" not in self.item_details[key]:
			self.item_details[key]["total_qty"] = row.actual_qty
		else:
			self.item_details[key]["total_qty"] += row.actual_qty

		self.item_details[key]["has_serial_no"] = row.has_serial_no
		self.item_details[key]["details"].valuation_rate = row.valuation_rate

	def __aggregate_details_by_item_and_invoice(self, wh_wise_data: dict) -> dict:
		"Aggregate Item-Wh wise data by Item and Invoice Number."
		item_invoice_aggregated_data = {}
		for key, row in wh_wise_data.items():
			# Key structure: (item_code, warehouse, invoice_number) or (item_code, invoice_number)
			if len(key) >= 3:  # (item_code, warehouse, invoice_number)
				item = key[0]
				invoice_number = key[2]
			else:  # (item_code, invoice_number)
				item = key[0]
				invoice_number = key[1] if len(key) > 1 else ""
			
			# Create new key as (item_code, invoice_number)
			new_key = (item, invoice_number)
			
			if not item_invoice_aggregated_data.get(new_key):
				item_invoice_aggregated_data.setdefault(
					new_key,
					{
						"details": frappe._dict(),
						"fifo_queue": [],
						"qty_after_transaction": 0.0,
						"total_qty": 0.0,
					},
				)
			item_row = item_invoice_aggregated_data.get(new_key)
			item_row["details"].update(row["details"])
			item_row["fifo_queue"].extend(row["fifo_queue"])
			item_row["qty_after_transaction"] += flt(row["qty_after_transaction"])
			item_row["total_qty"] += flt(row["total_qty"])
			item_row["has_serial_no"] = row["has_serial_no"]

		return item_invoice_aggregated_data

	def __get_stock_ledger_entries(self) -> Iterator[dict]:
		sle = frappe.qb.DocType("Stock Ledger Entry")
		item = self.__get_item_query()  # used as derived table in sle query
		to_date = get_datetime(self.filters.get("to_date") + " 23:59:59")

		# Check if custom fields exist
		custom_invoice_field = "sle.custom_invoice_number"
		custom_receive_field = "sle.custom_receive_date"
		
		try:
			# Test if custom fields exist by checking table structure
			frappe.db.sql("SELECT custom_invoice_number FROM `tabStock Ledger Entry` LIMIT 1")
			has_custom_invoice = True
		except Exception:
			has_custom_invoice = False
			
		try:
			frappe.db.sql("SELECT custom_receive_date FROM `tabStock Ledger Entry` LIMIT 1")
			has_custom_receive = True
		except Exception:
			has_custom_receive = False

		sle_query = (
			frappe.qb.from_(sle)
			.from_(item)
			.select(
				item.name,
				item.item_name,
				item.item_group,
				item.description,
				item.stock_uom,
				item.has_serial_no,
				item.valuation_method,
				sle.actual_qty,
				sle.stock_value_difference,
				sle.valuation_rate,
				sle.posting_date,
				sle.voucher_type,
				sle.voucher_no,
				sle.serial_no,
				sle.batch_no,
				sle.qty_after_transaction,
				sle.serial_and_batch_bundle,
				sle.warehouse,
			)
			.where(
				(sle.item_code == item.name)
				& (sle.company == self.filters.get("company"))
				& (sle.posting_datetime <= to_date)
				& (sle.is_cancelled != 1)
			)
		)

		# Add custom fields if they exist
		if has_custom_invoice:
			sle_query = sle_query.select(sle.custom_invoice_number)
		if has_custom_receive:
			sle_query = sle_query.select(sle.custom_receive_date)

		if self.filters.get("warehouse"):
			sle_query = self.__get_warehouse_conditions(sle, sle_query)
		elif self.filters.get("warehouse_type"):
			warehouses = frappe.get_all(
				"Warehouse",
				filters={"warehouse_type": self.filters.get("warehouse_type"), "is_group": 0},
				pluck="name",
			)

			if warehouses:
				sle_query = sle_query.where(sle.warehouse.isin(warehouses))

		sle_query = sle_query.orderby(sle.posting_datetime, sle.creation)

		# Execute query and add custom fields if they don't exist
		results = sle_query.run(as_dict=True, as_iterator=True)
		
		for row in results:
			if not has_custom_invoice:
				row['custom_invoice_number'] = ""
			if not has_custom_receive:
				row['custom_receive_date'] = None
			yield row

	def __get_bundle_wise_serial_nos(self) -> dict:
		bundle = frappe.qb.DocType("Serial and Batch Bundle")
		entry = frappe.qb.DocType("Serial and Batch Entry")

		query = (
			frappe.qb.from_(bundle)
			.join(entry)
			.on(bundle.name == entry.parent)
			.select(bundle.name, entry.serial_no)
			.where(
				(bundle.docstatus == 1)
				& (entry.serial_no.isnotnull())
				& (bundle.company == self.filters.get("company"))
				& (bundle.posting_date <= self.filters.get("to_date"))
			)
		)

		for field in ["item_code"]:
			if self.filters.get(field):
				query = query.where(bundle[field] == self.filters.get(field))

		if self.filters.get("warehouse"):
			query = self.__get_warehouse_conditions(bundle, query)

		bundle_wise_serial_nos = frappe._dict({})
		for bundle_name, serial_no in query.run():
			bundle_wise_serial_nos.setdefault(bundle_name, []).append(serial_no)

		return bundle_wise_serial_nos

	def __get_item_query(self) -> str:
		item_table = frappe.qb.DocType("Item")

		item = frappe.qb.from_("Item").select(
			"name",
			"item_name",
			"description",
			"stock_uom",
			"item_group",
			"has_serial_no",
			"valuation_method",
		)

		if self.filters.get("item_code"):
			item = item.where(item_table.item_code == self.filters.get("item_code"))

		return item

	def __get_warehouse_conditions(self, sle, sle_query) -> str:
		warehouse = frappe.qb.DocType("Warehouse")
		lft, rgt = frappe.db.get_value("Warehouse", self.filters.get("warehouse"), ["lft", "rgt"])

		warehouse_results = (
			frappe.qb.from_(warehouse)
			.select("name")
			.where((warehouse.lft >= lft) & (warehouse.rgt <= rgt))
			.run()
		)
		warehouse_results = [x[0] for x in warehouse_results]

		return sle_query.where(sle.warehouse.isin(warehouse_results))