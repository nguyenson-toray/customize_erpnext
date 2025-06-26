// stock_balance_customize.js
// Client script for Stock Balance Report with Invoice Number support

frappe.query_reports["Stock Balance Customize"] = {
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company"),
			"reqd": 1,
			"width": "100px"
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			"reqd": 1,
			"width": "100px"
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1,
			"width": "100px"
		},
		{
			"fieldname": "item_group",
			"label": __("Item Group"),
			"fieldtype": "Link",
			"options": "Item Group",
			"width": "100px"
		},
		{
			"fieldname": "item",
			"label": __("Item"),
			"fieldtype": "Link",
			"options": "Item",
			"width": "100px",
			"get_query": function () {
				var item_group = frappe.query_report.get_filter_value('item_group');
				if (item_group) {
					return {
						filters: {
							'item_group': item_group
						}
					};
				}
			}
		},
		{
			"fieldname": "warehouse",
			"label": __("Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": "100px",
			"get_query": function () {
				var company = frappe.query_report.get_filter_value('company');
				return {
					filters: {
						'company': company,
						'is_group': 0
					}
				};
			}
		},
		{
			"fieldname": "warehouse_type",
			"label": __("Warehouse Type"),
			"fieldtype": "Link",
			"options": "Warehouse Type",
			"width": "100px"
		},
		{
			"fieldname": "include_uom",
			"label": __("Include UOM"),
			"fieldtype": "Link",
			"options": "UOM",
			"width": "100px"
		},
		{
			"fieldname": "show_variant_attributes",
			"label": __("Show Variant Attributes"),
			"fieldtype": "Check",
			"default": 1
		},
		{
			"fieldname": "show_stock_ageing_data",
			"label": __("Show Stock Ageing Data"),
			"fieldtype": "Check",
			"default": 0
		},
		{
			"fieldname": "summary_qty_by_invoice_number",
			"label": __("Group by Invoice Number"),
			"fieldtype": "Check",
			"default": 1,
			"description": __("Show stock balance grouped by Invoice Number")
		},
		{
			"fieldname": "show_value",
			"label": __("Show Value"),
			"fieldtype": "Check",
			"default": 0
		},
		{
			"fieldname": "include_zero_stock_items",
			"label": __("Include Zero Stock Items"),
			"fieldtype": "Check",
			"default": 0
		},
		{
			"fieldname": "ignore_closing_balance",
			"label": __("Ignore Closing Balance"),
			"fieldtype": "Check",
			"default": 0
		},
		{
			"fieldname": "show_dimension_wise_stock",
			"label": __("Show Dimension Wise Stock"),
			"fieldtype": "Check",
			"default": 0
		}
	],

	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		// Highlight negative balances in red
		if (column.fieldname == "bal_qty" && data && data.bal_qty < 0) {
			value = "<span style='color:red'>" + value + "</span>";
		}

		// Highlight zero balances in orange
		if (column.fieldname == "bal_qty" && data && data.bal_qty == 0) {
			value = "<span style='color:orange'>" + value + "</span>";
		}

		// Format invoice number column
		if (column.fieldname == "invoice_number" && data && data.invoice_number) {
			value = "<span style='font-weight: normal; color: #2490ef;'>" + data.invoice_number + "</span>";
		}
		if (column.fieldname == "out_qty" && data && data.out_qty > 0) {
			value = "<span style='color:red'>" + value + "</span>";
		}
		if (column.fieldname == "in_qty" && data && data.in_qty > 0) {
			value = "<span style='color:green'>" + value + "</span>";
		}
		return value;
	},



	get_datatable_options(options) {
		return Object.assign(options, {
			checkboxColumn: true,
			events: {
				onCheckRow: function (data) {
					// Handle row selection for bulk operations
					console.log("Selected rows:", data);
				}
			}
		});
	}
};