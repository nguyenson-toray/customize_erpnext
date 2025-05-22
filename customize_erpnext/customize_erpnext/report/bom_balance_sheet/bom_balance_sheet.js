// Copyright (c) 2025, Your Company and contributors
// For license information, please see license.txt

frappe.query_reports["BOM Balance Sheet"] = {
	"filters": [
		{
			"fieldname": "sale_order",
			"label": __("Sale Order"),
			"fieldtype": "Link",
			"options": "Sales Order",
			"get_query": function () {
				return {
					filters: [
						["Sales Order", "docstatus", "=", 1]
					]
				};
			},
			"on_change": function () {
				// When sales order is selected, reset item_template and color filters
				const report = frappe.query_report;
				const sale_order = report.get_filter_value('sale_order');

				if (sale_order) {
					report.set_filter_value('item_template', '');
					report.set_filter_value('color', '');

					// Get related item templates from the sales order using the API
					frappe.call({
						method: "customize_erpnext.api.utilities.get_item_templates_from_sales_order",
						args: {
							sales_order: sale_order
						},
						callback: function (r) {
							if (r.message && r.message.length > 0) {
								const templates = r.message;

								// Update item_template filter options
								const item_template_filter = report.get_filter('item_template');
								item_template_filter.df.get_query = function () {
									return {
										filters: [
											["Item", "name", "in", templates],
											["Item", "has_variants", "=", 1],
											["Item", "is_sales_item", "=", 1],
											["Item", "disabled", "=", 0],
											["Item", "name", "like", "B-%"]  // B-Finished Goods
										]
									};
								};
								item_template_filter.refresh();
							}
						}
					});
				} else {
					// Reset item_template filter to show B-Finished Goods templates
					const item_template_filter = report.get_filter('item_template');
					item_template_filter.df.get_query = function () {
						return {
							filters: [
								["Item", "has_variants", "=", 1],
								["Item", "is_sales_item", "=", 1],
								["Item", "disabled", "=", 0],
								["Item", "name", "like", "B-%"]  // B-Finished Goods
							]
						};
					};
					item_template_filter.refresh();
				}
			}
		},
		{
			"fieldname": "item_template",
			"label": __("Item Template"),
			"fieldtype": "Link",
			"options": "Item",
			"reqd": 0,
			"get_query": function () {
				return {
					filters: [
						["Item", "has_variants", "=", 1],
						["Item", "is_sales_item", "=", 1],
						["Item", "disabled", "=", 0],
						["Item", "name", "like", "B-%"]  // B-Finished Goods
					]
				};
			},
			"on_change": function () {
				// Reset color filter and populate the color dropdown
				const report = frappe.query_report;
				const item_template = report.get_filter_value('item_template');

				if (item_template) {
					// Reset and update color filter options
					report.set_filter_value('color', '');

					// Use the existing function to get colors for the template
					frappe.call({
						method: "customize_erpnext.api.utilities.get_colors_for_template",
						args: {
							item_template: item_template
						},
						callback: function (r) {
							if (r.message) {
								const color_filter = frappe.query_report.get_filter('color');
								const color_options = [""].concat(r.message);
								color_filter.df.options = color_options;
								color_filter.refresh();
							}
						}
					});
				}
			}
		},
		{
			"fieldname": "color",
			"label": __("Color"),
			"fieldtype": "Select",
			"options": "",
			"depends_on": "eval:doc.item_template"
		},
		{
			"fieldname": "with_percent_lost",
			"label": __("Compare Qty Including Lost Percent"),
			"fieldtype": "Check",
			"default": 1,
			"on_change": function () {
				// Refresh report when this filter changes to rebuild columns
				frappe.query_report.refresh();
			}
		}
	],

	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		// Format stock quantity colors - compare with the right quantity based on with_percent_lost
		if (column.fieldname == "quantity_available_in_stock" && data) {
			const available = parseFloat(data.quantity_available_in_stock) || 0;
			let required = 0;

			// Check if with_percent_lost is enabled based on data or current filter
			const with_percent_lost = frappe.query_report.get_filter_value('with_percent_lost');

			if (with_percent_lost && data.quantity_require_include_lost_percent !== undefined) {
				required = parseFloat(data.quantity_require_include_lost_percent) || 0;
			} else {
				required = parseFloat(data.quantity_require) || 0;
			}

			// Display numeric value with color
			let displayValue = frappe.format(available, { fieldtype: "Float", precision: 3 });

			if (available < required) {
				value = `<span style="color: #d32f2f; font-weight: bold;">${displayValue}</span>`;
			} else {
				value = `<span style="color: #388e3c; font-weight: bold;">${displayValue}</span>`;
			}
		}

		// Format item code with link
		if (column.fieldname == "item" && data) {
			value = `<a href="/app/item/${data.item}" target="_blank" style="color: #1976d2; text-decoration: none;">${data.item}</a>`;
		}

		// Format lost percent
		if (column.fieldname == "lost_percent" && data && parseFloat(value) > 0) {
			value = `<span style="color: #f57c00; font-weight: 500;">${value}%</span>`;
		}






		return value;
	},

	"onload": function (report) {
		// Add custom buttons
		report.page.add_inner_button(__("Export to Excel"), function () {
			frappe.query_report.export_report("Excel");
		});

		report.page.add_inner_button(__("Print"), function () {
			frappe.query_report.print_report();
		});

		// Add refresh button
		report.page.add_inner_button(__("Refresh"), function () {
			frappe.query_report.refresh();
		});
	}
};