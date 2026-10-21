// Override frappe.ui.Page.add_action_icon so the tooltip is not translated twice.
//
// Every core caller already passes a translated label (e.g. form sidebar passes
// __("Print")), but add_action_icon wraps it in __() again. In Vietnamese that
// chains "Print" -> "In" -> "Trong" (msgid "In" is the filter operator, so the
// vi.po entry must stay). Only the fallback label built from the icon name is
// untranslated, so translate that one alone.
//
// Upstream: frappe/public/js/frappe/ui/page.js

frappe.ui.Page.prototype.add_action_icon = function (icon, click, css_class = "", tooltip_label) {
	const button = $(`
		<button class="text-muted btn btn-default ${css_class} icon-btn">
			${frappe.utils.icon(icon)}
		</button>
	`);
	if (!tooltip_label) {
		tooltip_label = __(frappe.unscrub(icon));
	}

	button.appendTo(this.icon_group.removeClass("hide"));
	button.click(click);
	button
		.attr("title", tooltip_label)
		.tooltip({ delay: { show: 600, hide: 100 }, trigger: "hover" });

	return button;
};
