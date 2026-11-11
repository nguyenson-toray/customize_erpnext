// Print Settings > "Print the PDF" loads the PDF into a hidden iframe and calls print() on it.
// Chrome/Edge on Android cannot do this and show "Could not prepare the PDF for printing".
// On Android only, use Frappe's standard /printview route, which opens the browser print dialog
// in one tap. Print formats used on tablets should set @page size/margins in their CSS.
(() => {
	if (!/Android/i.test(navigator.userAgent)) return;

	frappe.ui.form.PrintView.prototype.print_pdf = function () {
		this.render_page("/printview?", true);
	};
})();
