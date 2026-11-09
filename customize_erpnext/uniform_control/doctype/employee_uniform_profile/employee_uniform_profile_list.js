// Profiles are created automatically (Get Employees, the dashboard, the nightly
// job) and their Employee fields are refreshed every night — no bulk buttons.
// Profiles of employees who left stay as the issuance-history archive; the list
// opens on Active employees.
frappe.listview_settings['Employee Uniform Profile'] = {
	filters: [['employment_status', '=', 'Active']],
};
