/**
 * Hide permlevel-restricted fields from the "Export Data" dialog.
 *
 * PROBLEM
 * -------
 * `frappe.data_import.DataExporter` (apps/frappe/frappe/public/js/frappe/data_import/data_exporter.js)
 * builds the column picker from `get_columns_for_picker()`, which filters only on
 * fieldtype / is_virtual / lft-rgt. It never looks at `permlevel`.
 * The server DOES enforce permlevel (Meta.get_permitted_fieldnames() -> get_permlevel_access(),
 * see apps/frappe/frappe/model/meta.py), so a user without Read at that level can tick the column
 * and gets an empty column back. Confusing. This script removes those columns from the picker.
 *
 * THIS IS UI-ONLY. It is NOT a security layer — the server keeps enforcing permlevel regardless.
 *
 * WHY DOM MANIPULATION INSTEAD OF MONKEY-PATCHING FRAPPE INTERNALS
 * ----------------------------------------------------------------
 * The alternative would be to override `frappe.data_import.DataExporter.prototype.get_multicheck_options`
 * or `get_columns_for_picker`. We deliberately do NOT do that:
 *   1. Those are internal names with no stability contract; Frappe renames/reshapes them between
 *      versions (get_columns_for_picker only became an exported function in v14+), so a patch
 *      silently stops working — or worse, throws — after `bench update`.
 *   2. `get_columns_for_picker` is an ES module export, not a namespaced global: it cannot be
 *      reliably replaced from an `app_include_js` file at all.
 *   3. Overriding the class would fight with any other app doing the same, and would have to be
 *      re-verified on every Frappe upgrade.
 * The DOM contract we rely on instead is far more stable and is what every Frappe UI already uses:
 *   - dialogs are `.modal` with an `<h4 class="modal-title">` (frappe.get_modal, dom.js)
 *   - every control wrapper is `.frappe-control[data-fieldtype][data-fieldname]` with the control
 *     object attached as `wrapper.fieldobj` (form/controls/base_control.js)
 *   - every MultiCheck row is `.checkbox.unit-checkbox` holding `input[data-unit="<fieldname>"]`
 *     (form/controls/multicheck.js)
 * If any of that ever changes, this script no-ops (guarded everywhere) instead of breaking export.
 *
 * Scope: the "Export Data" dialog only. Form view, list view and other dialogs are untouched.
 */

frappe.provide("customize_erpnext.export_field_perms");

(function () {
	// Fields Frappe always treats as permitted server-side (frappe/model/__init__.py :: default_fields)
	// plus the synthetic "ID" row the picker prepends. Never hide these.
	const ALWAYS_VISIBLE = new Set([
		"name",
		"owner",
		"creation",
		"modified",
		"modified_by",
		"docstatus",
		"idx",
		"parent",
		"parentfield",
		"parenttype",
	]);

	// frappe.model.core_doctypes_list (model.js) is missing 3 names that the SERVER's
	// core_doctypes_list (frappe/model/__init__.py) has. get_permitted_fields() short-circuits on
	// the server list, so mirror that one to avoid hiding a column the server would actually export.
	const EXTRA_CORE_DOCTYPES = ["DefaultValue", "DocType Action", "DocType Link"];

	/**
	 * Administrator and System Manager keep the default behaviour (see all columns).
	 * Note: only Administrator truly bypasses permlevel server-side — for System Manager this is a
	 * deliberate UI choice so admins can still see the full field list; the export itself is still
	 * filtered by the server if they lack the level.
	 */
	function should_skip_filtering() {
		const roles = frappe.user_roles || [];
		return (
			frappe.session.user === "Administrator" ||
			roles.includes("Administrator") ||
			roles.includes("System Manager")
		);
	}

	/**
	 * Read permission for `permlevel` on `doctype`, aggregated across ALL roles of the user
	 * (frappe.perm.get_role_permissions ORs every Role Permission row whose role the user has).
	 */
	function can_read_permlevel(doctype, permlevel) {
		try {
			return !!frappe.perm.has_perm(doctype, permlevel, "read");
		} catch (e) {
			// Never let a perm lookup break the dialog — fail open (server still enforces).
			return true;
		}
	}

	function escape_attr_value(value) {
		return String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
	}

	/** All MultiCheck controls inside the dialog, in DOM order (parent doctype first). */
	function get_multicheck_controls($modal) {
		return $modal
			.find('.frappe-control[data-fieldtype="MultiCheck"]')
			.toArray()
			.map((el) => ({
				fieldname: $(el).attr("data-fieldname"),
				control: el.fieldobj,
				$wrapper: $(el),
			}))
			.filter((item) => item.fieldname);
	}

	/**
	 * The DocType being exported.
	 * Primary source: DataExporter names its first MultiCheck field after the parent doctype
	 * (`fieldname: this.doctype`) and the child ones after the Table fieldname — see make_dialog().
	 * Fallbacks: the current route (List view) / the open Data Import doc.
	 */
	function get_export_doctype(controls) {
		if (controls.length && frappe.get_meta(controls[0].fieldname)) {
			return controls[0].fieldname;
		}

		const route = frappe.get_route() || [];
		if (route[0] === "List" && route[1] && frappe.get_meta(route[1])) {
			return route[1];
		}
		if (
			route[0] === "Form" &&
			route[1] === "Data Import" &&
			window.cur_frm &&
			cur_frm.doc &&
			cur_frm.doc.reference_doctype
		) {
			return cur_frm.doc.reference_doctype;
		}
		return null;
	}

	/**
	 * Drop one column from a MultiCheck: remove its row from the DOM *and* from the control's
	 * options array.
	 * Hiding with .hide() alone is not enough:
	 *   - DataExporter.select_all() does `$wrapper.find(":checkbox").prop("checked", true)` — jQuery
	 *     `:checkbox` still matches hidden inputs, so a merely hidden column would still be exported.
	 *   - frappe.utils.setup_search() (the dialog's search box) calls `$(row).toggle(match)` on every
	 *     `.unit-checkbox` and would show the row again on the next keystroke.
	 * `control.options` is the same array instance as `control.df.options` (multicheck.js ::
	 * parse_df_options), so splicing it also keeps any later re-render correct.
	 */
	function drop_option(item, fieldname) {
		const selector = `input:checkbox[data-unit="${escape_attr_value(fieldname)}"]`;
		const $checkbox = item.$wrapper.find(selector);
		if (!$checkbox.length) return false;

		// Uncheck first: setup_on_page_show() -> select_mandatory() may have pre-checked it.
		if ($checkbox.prop("checked")) {
			$checkbox.prop("checked", false).trigger("change");
		}

		let $row = $checkbox.closest(".unit-checkbox");
		if (!$row.length) $row = $checkbox.closest("label");
		($row.length ? $row : $checkbox).remove();

		const control = item.control;
		if (control) {
			if (Array.isArray(control.options)) {
				const idx = control.options.findIndex((o) => o && o.value === fieldname);
				if (idx > -1) control.options.splice(idx, 1);
			}
			if (Array.isArray(control.selected_options)) {
				const sel = control.selected_options.indexOf(fieldname);
				if (sel > -1) control.selected_options.splice(sel, 1);
			}
		}
		return true;
	}

	function filter_export_dialog($modal) {
		if (should_skip_filtering()) return;

		const controls = get_multicheck_controls($modal);
		if (!controls.length) return;

		const parent_doctype = get_export_doctype(controls);
		if (!parent_doctype) return;

		const parent_meta = frappe.get_meta(parent_doctype);
		if (!parent_meta) return;

		// Mirror the server's own escape hatches (frappe/model/__init__.py :: get_permitted_fields):
		// core doctypes are never permlevel-filtered, and a doctype with no Role Permission rows
		// at all exposes every field.
		const core_doctypes = (frappe.model.core_doctypes_list || []).concat(EXTRA_CORE_DOCTYPES);
		if (core_doctypes.includes(parent_doctype)) return;
		if (!(parent_meta.permissions || []).length) return;

		let removed = 0;

		controls.forEach((item) => {
			// Parent MultiCheck is named after the doctype; the others after the Table fieldname.
			let target_doctype = parent_doctype;
			if (item.fieldname !== parent_doctype) {
				const table_df = frappe.meta.get_docfield(parent_doctype, item.fieldname);
				if (!table_df || !table_df.options) return;
				target_doctype = table_df.options;
			}

			const meta = frappe.get_meta(target_doctype);
			if (!meta || !meta.fields) return;

			meta.fields.forEach((df) => {
				if (ALWAYS_VISIBLE.has(df.fieldname)) return;

				const permlevel = cint(df.permlevel);
				// Level 0 is the base level: if it were denied the user could not open the list at all.
				if (!permlevel) return;

				// Child table fields are checked against the PARENT doctype's Role Permissions —
				// child DocTypes carry no permissions of their own (Meta.get_permissions(parenttype)).
				if (can_read_permlevel(parent_doctype, permlevel)) return;

				if (drop_option(item, df.fieldname)) removed++;
			});
		});

		if (removed && window.console && frappe.boot && frappe.boot.developer_mode) {
			console.log(
				`[customize_erpnext] Export Data: hid ${removed} field(s) restricted by permlevel on ${parent_doctype}`
			);
		}
	}

	// Bind exactly once per page load, delegated on document, so reopening the dialog any number of
	// times never stacks listeners. Frappe v16 ships Bootstrap 4 modals (`data-dismiss`, see
	// frappe.get_modal in dom.js), so `shown.bs.modal` is the correct event; it bubbles, and it fires
	// after the dialog's own handler has run on_page_show() -> select_mandatory().
	//
	// Known cosmetic limitation: `shown.bs.modal` fires only once the modal's fade transition has
	// finished, so restricted rows are painted for the ~150ms of the fade before being removed.
	// Bootstrap's earlier `show.bs.modal` cannot be used: it is triggered BEFORE _showElement()
	// attaches the modal to <body>, so a delegated handler on `document` would never receive it.
	if (!customize_erpnext.export_field_perms.bound) {
		customize_erpnext.export_field_perms.bound = true;

		// NOTE: bind the bare "shown.bs.modal" — adding our own extra jQuery namespace
		// (e.g. "shown.bs.modal.customize") would make the handler NEVER fire, because jQuery only
		// runs a namespaced handler when the triggered event carries all of its namespaces.
		$(document).on("shown.bs.modal", ".modal", function () {
			const $modal = $(this);
			// Dialog.set_title() writes with .html(), so read it back with .text(). Accept both the
			// translated title and the English source string: if a site ships a partial vi.csv the
			// dialog may still render the English literal.
			const title = ($modal.find(".modal-title").first().text() || "").trim();
			if (title !== __("Export Data") && title !== "Export Data") return;

			try {
				filter_export_dialog($modal);
			} catch (e) {
				// Never block the export dialog because of this cosmetic filter.
				console.error("[customize_erpnext] hide_restricted_export_fields failed", e);
			}
		});
	}

	// Exposed for manual testing from the browser console.
	customize_erpnext.export_field_perms.filter_export_dialog = filter_export_dialog;
})();
