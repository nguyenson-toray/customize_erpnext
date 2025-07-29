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
			"default": erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[1],
			//frappe.datetime.add_months(frappe.datetime.get_today(), -1),
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
			"fieldname": "summary_qty_by_invoice_number",
			"label": __("Group by Invoice Number"),
			"fieldtype": "Check",
			"default": 1,
			"description": __("Show stock balance grouped by Invoice Number")
		},
		{
			"fieldname": "show_stock_ageing_data",
			"label": __("Show Stock Ageing Data"),
			"fieldtype": "Check",
			"default": 0,
			"depends_on": "eval:doc.summary_qty_by_invoice_number"
		},
		{
			"fieldname": "range",
			"label": __("Ageing Range"),
			"fieldtype": "Data",
			"default": "180, 360, 720",
			"depends_on": "eval:doc.show_stock_ageing_data && doc.summary_qty_by_invoice_number"
		},
		{
			'fieldname': "include_zero_stock_items",
			'label': __("Include Zero Stock Items"),
			'fieldtype': "Check",
			'default': 1,
		},

		// {
		// 	"fieldname": "show_value",
		// 	"label": __("Show Value"),
		// 	"fieldtype": "Check",
		// 	"default": 0
		// },
		// {
		// 	"fieldname": "ignore_closing_balance",
		// 	"label": __("Ignore Closing Balance"),
		// 	"fieldtype": "Check",
		// 	"default": 0
		// },
		// {
		// 	"fieldname": "show_dimension_wise_stock",
		// 	"label": __("Show Dimension Wise Stock"),
		// 	"fieldtype": "Check",
		// 	"default": 0
		// }
	],

	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (!data) return value;

		// Color coding for balance quantities
		if (column.fieldname === "bal_qty") {
			if (data.bal_qty < 0) {
				value = "<span style='color: red; font-weight: bold;'>" + value + "</span>";
			} else if (data.bal_qty === 0) {
				value = "<span style='color: orange; font-weight: bold;'>" + value + "</span>";
			}
		}

		// Format invoice number column with blue color
		if (column.fieldname === "invoice_number" && data.invoice_number) {
			value = "<span style='font-weight: normal; color: #2490ef;'>" + data.invoice_number + "</span>";
		}

		// Color coding for movement quantities
		if (column.fieldname === "out_qty" && data.out_qty > 0) {
			value = "<span style='color: red;'>" + value + "</span>";
		}

		if (column.fieldname === "in_qty" && data.in_qty > 0) {
			value = "<span style='color: green;'>" + value + "</span>";
		}

		// Highlight age columns for aging analysis
		if (column.fieldname === "age" && data.age > 0) {
			if (data.age > 365) {
				value = "<span style='color: red;'>" + value + "</span>";
			} else if (data.age > 180) {
				value = "<span style='color: orange;'>" + value + "</span>";
			}
		}
		// Set text color white for columns [Color, Size, Brand, Season, Info] if value is "Blank"
		if (["Color", "Size", "Brand", "Season", "Info"].includes(column.fieldname) &&
			(data[column.fieldname] === "Blank" || data[column.fieldname] === "" || !data[column.fieldname])) {
			value = "<span style='color: white;'>Blank</span>";
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

					// Enable/disable bulk action buttons based on selection
					if (data && data.length > 0) {
						// Add custom actions for selected rows
						frappe.query_report.page.add_actions_menu_item(
							__("Export Selected"),
							function () {
								frappe.query_report.export_selected_rows(data);
							}
						);
					}
				}
			}
		});
	},

	onload: function (report) {
		// Add custom buttons for enhanced functionality
		report.page.add_inner_button(__("Refresh Aging Data"), function () {
			report.refresh();
		});

		// Add export options
		report.page.add_menu_item(__("Export with Aging"), function () {
			let filters = report.get_values();
			filters.show_stock_ageing_data = 1;

			frappe.query_report.refresh();
		});
	},

	// Custom function to export selected rows
	export_selected_rows: function (selected_data) {
		if (!selected_data || selected_data.length === 0) {
			frappe.msgprint(__("No rows selected"));
			return;
		}

		// Prepare data for export
		let export_data = selected_data.map(row => {
			return {
				"Item Code": row.item_code,
				"Item Name": row.item_name,
				"Warehouse": row.warehouse,
				"Invoice Number": row.invoice_number || "",
				"Balance Qty": row.bal_qty,
				"Age": row.age || 0
			};
		});

		// Convert to CSV and download
		let csv_content = this.convert_to_csv(export_data);
		this.download_csv(csv_content, "selected_stock_balance.csv");
	},

	// Helper function to convert data to CSV
	convert_to_csv: function (data) {
		if (!data || data.length === 0) return "";

		let headers = Object.keys(data[0]);
		let csv = headers.join(",") + "\n";

		data.forEach(row => {
			let values = headers.map(header => {
				let value = row[header] || "";
				// Escape commas and quotes
				if (typeof value === "string" && (value.includes(",") || value.includes('"'))) {
					value = '"' + value.replace(/"/g, '""') + '"';
				}
				return value;
			});
			csv += values.join(",") + "\n";
		});

		return csv;
	},

	// Helper function to download CSV
	download_csv: function (csv_content, filename) {
		let blob = new Blob([csv_content], { type: "text/csv;charset=utf-8;" });
		let link = document.createElement("a");

		if (link.download !== undefined) {
			let url = URL.createObjectURL(blob);
			link.setAttribute("href", url);
			link.setAttribute("download", filename);
			link.style.visibility = "hidden";
			document.body.appendChild(link);
			link.click();
			document.body.removeChild(link);
		}
	}
};