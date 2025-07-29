# Copyright (c) 2024, Your Company and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext.stock.report.stock_ageing_customize.stock_ageing_customize import FIFOSlots, format_report_data


class TestStockAgeingCustomize(FrappeTestCase):
	def setUp(self) -> None:
		self.filters = frappe._dict(
			company="_Test Company", 
			to_date="2024-12-10", 
			ranges=["180", "360", "720"],
			show_value=0,
			show_variant_attributes=0
		)

	def test_custom_receive_date_opening_stock(self):
		"""Test using custom_receive_date for Opening Stock entries"""
		sle = [
			frappe._dict(
				name="Flask Item",
				actual_qty=100,
				qty_after_transaction=100,
				stock_value_difference=100,
				warehouse="WH 1",
				posting_date="2024-01-01",  # This should be ignored
				custom_receive_date="2023-12-15",  # This should be used
				voucher_type="Stock Reconciliation",
				voucher_no="Opening Stock 001",
				has_serial_no=False,
				serial_no=None,
				custom_invoice_number="INV001",
			),
		]

		slots = FIFOSlots(self.filters, sle).generate()
		result = slots["Flask Item"]
		queue = result["fifo_queue"]

		# Check that custom_receive_date is used as posting_date
		self.assertEqual(queue[0][1], "2023-12-15")
		self.assertEqual(queue[0][3], "INV001")  # Check custom_invoice_number

	def test_custom_invoice_number_tracking(self):
		"""Test tracking of custom_invoice_number in FIFO queue"""
		sle = [
			frappe._dict(
				name="Flask Item",
				actual_qty=50,
				qty_after_transaction=50,
				stock_value_difference=50,
				warehouse="WH 1",
				posting_date="2024-01-01",
				voucher_type="Stock Entry",
				voucher_no="001",
				has_serial_no=False,
				serial_no=None,
				custom_invoice_number="INV001",
			),
			frappe._dict(
				name="Flask Item",
				actual_qty=30,
				qty_after_transaction=80,
				stock_value_difference=30,
				warehouse="WH 1",
				posting_date="2024-01-02",
				voucher_type="Stock Entry",
				voucher_no="002",
				has_serial_no=False,
				serial_no=None,
				custom_invoice_number="INV002",
			),
		]

		slots = FIFOSlots(self.filters, sle).generate()
		result = slots["Flask Item"]
		queue = result["fifo_queue"]

		# Check that both invoice numbers are tracked
		self.assertEqual(len(queue), 2)
		self.assertEqual(queue[0][3], "INV001")
		self.assertEqual(queue[1][3], "INV002")

	def test_show_value_filter(self):
		"""Test Show Value filter functionality"""
		sle = [
			frappe._dict(
				name="Flask Item",
				actual_qty=30,
				qty_after_transaction=30,
				stock_value_difference=300,
				warehouse="WH 1",
				posting_date="2024-01-01",
				voucher_type="Stock Entry",
				voucher_no="001",
				has_serial_no=False,
				serial_no=None,
				custom_invoice_number="INV001",
			),
		]

		# Test without show_value
		slots = FIFOSlots(self.filters, sle).generate()
		data_without_value = format_report_data(self.filters, slots, self.filters["to_date"])
		
		# Test with show_value
		self.filters.show_value = 1
		slots = FIFOSlots(self.filters, sle).generate()
		data_with_value = format_report_data(self.filters, slots, self.filters["to_date"])

		# Data with value should have more columns than without value
		self.assertGreater(len(data_with_value[0]), len(data_without_value[0]))

	def test_variant_attributes_display(self):
		"""Test Show Variant Attributes functionality"""
		# This test would require setting up item variants
		# For now, just test the function exists and doesn't crash
		from erpnext.stock.report.stock_ageing_customize.stock_ageing_customize import get_variant_attributes
		
		# Test with non-existent item (should return empty list with 5 empty strings)
		attributes = get_variant_attributes("Non-Existent Item")
		self.assertEqual(len(attributes), 5)
		self.assertEqual(attributes, ["", "", "", "", ""])

	def test_blank_value_hiding(self):
		"""Test that Blank and (blank) values are hidden with white color"""
		from erpnext.stock.report.stock_ageing_customize.stock_ageing_customize import get_variant_attributes
		
		# Mock data with blank values
		frappe.db.sql = lambda query, item_code, as_dict=1: [
			{"attribute": "Color", "attribute_value": "Red"},
			{"attribute": "Size", "attribute_value": "Blank"},
			{"attribute": "Brand", "attribute_value": "(blank)"},
			{"attribute": "Season", "attribute_value": "Summer"},
			{"attribute": "Info", "attribute_value": ""}
		] if item_code == "Test Item" else []
		
		attributes = get_variant_attributes("Test Item")
		self.assertEqual(len(attributes), 5)
		self.assertEqual(attributes[0], "Red")  # Normal value
		self.assertIn('style="color: white;"', attributes[1])  # Blank should be hidden
		self.assertIn('style="color: white;"', attributes[2])  # (blank) should be hidden
		self.assertEqual(attributes[3], "Summer")  # Normal value
		self.assertEqual(attributes[4], "")  # Empty value

	def test_new_age_ranges(self):
		"""Test new default age ranges (180, 360, 720)"""
		sle = [
			frappe._dict(
				name="Flask Item",
				actual_qty=100,
				qty_after_transaction=100,
				stock_value_difference=100,
				warehouse="WH 1",
				posting_date="2024-01-01",  # ~340 days old from to_date
				voucher_type="Stock Entry",
				voucher_no="001",
				has_serial_no=False,
				serial_no=None,
				custom_invoice_number="INV001",
			),
		]

		slots = FIFOSlots(self.filters, sle).generate()
		data = format_report_data(self.filters, slots, self.filters["to_date"])
		
		# Item should fall into second range (180-360)
		# Check that it's not in first range (0-180) at index 6
		# and is in second range (180-360) at index 7
		self.assertEqual(data[0][6], 0.0)  # First range should be 0
		self.assertEqual(data[0][7], 100.0)  # Second range should have the quantity

	def test_outgoing_stock_with_custom_invoice(self):
		"""Test outgoing stock preserves custom_invoice_number in transfer bucket"""
		sle = [
			frappe._dict(
				name="Flask Item",
				actual_qty=100,
				qty_after_transaction=100,
				stock_value_difference=100,
				warehouse="WH 1",
				posting_date="2024-01-01",
				voucher_type="Stock Entry",
				voucher_no="001",
				has_serial_no=False,
				serial_no=None,
				custom_invoice_number="INV001",
			),
			frappe._dict(
				name="Flask Item",
				actual_qty=-50,
				qty_after_transaction=50,
				stock_value_difference=-50,
				warehouse="WH 1",
				posting_date="2024-01-02",
				voucher_type="Stock Entry",
				voucher_no="002",
				has_serial_no=False,
				serial_no=None,
				custom_invoice_number="",
			),
		]

		fifo_slots = FIFOSlots(self.filters, sle)
		slots = fifo_slots.generate()
		result = slots["Flask Item"]
		queue = result["fifo_queue"]

		# Check remaining stock
		self.assertEqual(queue[0][0], 50.0)
		self.assertEqual(queue[0][3], "INV001")

		# Check transfer bucket
		transfer_key = ("002", "Flask Item", "WH 1")
		transfer_bucket = fifo_slots.transferred_item_details.get(transfer_key)
		self.assertTrue(transfer_bucket)
		self.assertEqual(transfer_bucket[0][0], 50.0)
		self.assertEqual(transfer_bucket[0][3], "INV001")

	def test_column_structure(self):
		"""Test column structure and Invoice Numbers position"""
		from erpnext.stock.report.stock_ageing_customize.stock_ageing_customize import get_columns
		
		# Test without variant attributes and warehouse-wise stock
		columns = get_columns(self.filters)
		column_names = [col["fieldname"] for col in columns]
		
		# Basic columns should be: item_code, item_name, description, item_group, invoice_numbers, qty, average_age, ranges..., earliest, latest, uom
		expected_start = ["item_code", "item_name", "description", "item_group", "invoice_numbers"]
		self.assertEqual(column_names[:5], expected_start)
		
		# Test with variant attributes enabled
		self.filters.show_variant_attributes = 1
		columns_with_attrs = get_columns(self.filters)
		column_names_with_attrs = [col["fieldname"] for col in columns_with_attrs]
		
		# Should include Color, Size, Brand, Season, Info
		expected_with_attrs = ["item_code", "item_name", "description", "item_group", 
							  "color", "size", "brand", "season", "info", "invoice_numbers"]
		self.assertEqual(column_names_with_attrs[:10], expected_with_attrs)
		
		# Test with warehouse-wise stock enabled
		self.filters.show_warehouse_wise_stock = 1
		columns_with_wh = get_columns(self.filters)
		column_names_with_wh = [col["fieldname"] for col in columns_with_wh]
		
		# Should include warehouse before invoice_numbers
		expected_with_wh = ["item_code", "item_name", "description", "item_group", 
						   "color", "size", "brand", "season", "info", "warehouse", "invoice_numbers"]
		self.assertEqual(column_names_with_wh[:11], expected_with_wh)

	def test_negative_stock_handling_with_invoice_number(self):
		"""Test negative stock handling preserves custom_invoice_number"""
		sle = [
			frappe._dict(
				name="Flask Item",
				actual_qty=-50,
				qty_after_transaction=-50,
				stock_value_difference=0,
				warehouse="WH 1",
				posting_date="2024-01-01",
				voucher_type="Stock Entry",
				voucher_no="001",
				has_serial_no=False,
				serial_no=None,
				custom_invoice_number="INV001",
			),
			frappe._dict(
				name="Flask Item",
				actual_qty=30,
				qty_after_transaction=-20,
				stock_value_difference=0,
				warehouse="WH 1",
				posting_date="2024-01-02",
				voucher_type="Stock Entry",
				voucher_no="002",
				has_serial_no=False,
				serial_no=None,
				custom_invoice_number="INV002",
			),
		]

		slots = FIFOSlots(self.filters, sle).generate()
		result = slots["Flask Item"]
		queue = result["fifo_queue"]

		# Should have negative stock
		self.assertEqual(result["total_qty"], -20.0)
		self.assertEqual(queue[0][0], -20.0)
		# Most recent invoice number should be used for the negative balance
		self.assertEqual(queue[0][3], "INV002")


def generate_item_and_item_wh_wise_slots(filters, sle):
	"Return results with and without 'show_warehouse_wise_stock'"
	item_wise_slots = FIFOSlots(filters, sle).generate()

	filters.show_warehouse_wise_stock = True
	item_wh_wise_slots = FIFOSlots(filters, sle).generate()
	filters.show_warehouse_wise_stock = False

	return item_wise_slots, item_wh_wise_slots