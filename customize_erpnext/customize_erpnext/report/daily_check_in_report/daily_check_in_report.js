frappe.query_reports["Daily Check-in Report"] = {
	"filters": [
		{
			"fieldname": "date",
			"label": __("Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname": "department",
			"label": __("Department"),
			"fieldtype": "Link",
			"options": "Department"
		},
		{
			"fieldname": "custom_group",
			"label": __("Group"),
			"fieldtype": "Link",
			"options": "Group"
		},
		{
			"fieldname": "status",
			"label": __("Status"),
			"fieldtype": "Select",
			"options": "All\nPresent\nAbsent",
			"default": "All"
		}
	]
};