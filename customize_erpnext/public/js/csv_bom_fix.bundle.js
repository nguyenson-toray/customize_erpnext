// Override frappe.tools.downloadify to prepend a UTF-8 BOM.
//
// Frappe builds the CSV Blob with type "text/csv;charset=UTF-8", but the charset
// in a MIME type is lost once the file is on disk. Excel then guesses the encoding
// from the Windows system codepage and mangles Vietnamese diacritics. The BOM is
// the only in-band signal Excel honours for CSV.
//
// Upstream: frappe/public/js/frappe/utils/tools.js
// Patches the Download button on child table grids and dashboard chart widgets.

frappe.provide("frappe.tools");

frappe.tools.downloadify = function (data, roles, title) {
	if (roles && roles.length && !has_common(roles, roles)) {
		frappe.msgprint(
			__("Export not allowed. You need {0} role to export.", [frappe.utils.comma_or(roles)])
		);
		return;
	}

	const BOM = "\uFEFF";
	const filename = title + ".csv";
	const csv_data = frappe.tools.to_csv(data);
	const a = document.createElement("a");

	if ("download" in a) {
		const blob_object = new Blob([BOM, csv_data], { type: "text/csv;charset=UTF-8" });
		a.href = URL.createObjectURL(blob_object);
		a.download = filename;
	} else {
		a.href = "data:attachment/csv," + encodeURIComponent(BOM + csv_data);
		a.download = filename;
		a.target = "_blank";
	}

	document.body.appendChild(a);
	a.click();
	document.body.removeChild(a);

	if (a.href.startsWith("blob:")) {
		URL.revokeObjectURL(a.href);
	}
};
