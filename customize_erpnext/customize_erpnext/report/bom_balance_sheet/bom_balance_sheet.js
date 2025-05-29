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
				// When sales order is selected, update item_template options from server
				const report = frappe.query_report;
				const sale_order = report.get_filter_value('sale_order');

				// Clear dependent filters
				report.set_filter_value('item_template', '');
				report.set_filter_value('color', '');

				// Update item_template options based on sales order
				update_item_template_options(report, sale_order);
				frappe.query_report.refresh();
			}
		},
		{
			"fieldname": "item_template",
			"label": __("Item Template"),
			"fieldtype": "Select",
			"options": "",
			"reqd": 0,
			"on_change": function () {
				// Reset color filter and populate the color dropdown
				const report = frappe.query_report;
				const item_template_raw = report.get_filter_value('item_template');

				if (item_template_raw) {
					// Extract item template name từ "name:label" format nếu cần
					const item_template = item_template_raw.includes(':') ?
						item_template_raw.split(':')[0] : item_template_raw;

					// Reset and update color filter options
					report.set_filter_value('color', '');

					// Use the existing function to get colors for the template
					frappe.call({
						method: "customize_erpnext.api.utilities.get_colors_for_template",
						args: {
							item_template: item_template  // Pass extracted name
						},
						callback: function (r) {
							if (r.message) {
								const color_filter = report.get_filter('color');
								const color_options = [""].concat(r.message);
								color_filter.df.options = color_options;
								color_filter.refresh();
							}
						}
					});
				} else {
					// Clear color filter when no item template is selected
					const color_filter = report.get_filter('color');
					color_filter.df.options = "";
					color_filter.refresh();
				}
				frappe.query_report.refresh();
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
		// Initialize item_template options on load
		update_item_template_options(report, null);
		// Add refresh button
		report.page.add_inner_button(__("Refresh"), function () {
			frappe.query_report.refresh();
		});
		// Add custom buttons
		report.page.add_inner_button(__("Export to Excel"), function () {
			frappe.query_report.export_report("Excel");
		});

		// report.page.add_inner_button(__("Print"), function () {
		// 	frappe.query_report.print_report();
		// });


	}
};

// Helper function to update item_template options via server-side filtering
function update_item_template_options(report, sale_order) {
	frappe.call({
		method: "customize_erpnext.customize_erpnext.report.bom_balance_sheet.bom_balance_sheet.get_filtered_item_templates",
		args: {
			sales_order: sale_order || null
		},
		callback: function (r) {
			if (r.message) {
				const item_template_filter = report.get_filter('item_template');

				// Create options string for Select field
				let options = "";
				if (r.message.length > 0) {
					// Add empty option first, then all templates với item_name để dễ nhận biết
					options = "\n" + r.message.map(item => {
						// Format as "value:label" for better display
						return `${item.name}:${item.item_name || item.name}`;
					}).join("\n");
				}

				// Update filter options
				item_template_filter.df.options = options;
				item_template_filter.refresh();

				// Show user feedback
				if (sale_order && r.message.length > 0) {
					frappe.show_alert({
						message: __(`Found ${r.message.length} item templates for Sales Order ${sale_order}`),
						indicator: 'blue'
					});
				} else if (sale_order && r.message.length === 0) {
					frappe.show_alert({
						message: __(`No item templates found for Sales Order ${sale_order}`),
						indicator: 'orange'
					});
				}
			} else {
				// Clear options if no data
				const item_template_filter = report.get_filter('item_template');
				item_template_filter.df.options = "";
				item_template_filter.refresh();
			}
		},
		error: function (r) {
			console.error('Error updating item template options:', r);
			frappe.show_alert({
				message: __('Error loading item templates'),
				indicator: 'red'
			});
		}
	});
}