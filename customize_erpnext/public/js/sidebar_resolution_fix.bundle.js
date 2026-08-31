// Make the v16 workspace sidebar resolve deterministically for every route.
//
// Upstream: frappe/public/js/frappe/ui/sidebar/sidebar.js
//
// Symptom: opening a doctype from a workspace shows a sensible sidebar, but
// reaching the SAME doctype through the search bar (or a pasted URL) shows an
// unrelated one. Four upstream defects combine to produce it:
//
//   1. filter_sidebars_from_app() compares sidebar.app, but the 22 sidebars
//      auto-generated from Module Def (auto_generate_sidebar_from_module) never
//      set `app`, and 4 more ship it empty - 26 of 76 on this site. The app
//      filter therefore discards every candidate and resolution falls through.
//   2. resolve_sidebar() breaks ties with candidates[0], i.e. the key order of
//      frappe.boot.workspace_sidebar_item. 45 doctypes match several sidebars
//      (Item matches 8), so the winner is incidental.
//   3. The "remembered" map is written keyed by sidebar ITEM LABEL and read
//      keyed by ROUTE ENTITY, appended to without dedupe, and read back at
//      index [0] - so the first value ever recorded wins forever, even when it
//      names a sidebar that has nothing to do with the doctype.
//   4. choose_app_name() returns without touching frappe.current_app when it
//      cannot match an app, leaving the previously visited app in place. The
//      header subtitle and the app-switcher sibling icons then belong to
//      whichever app the user came from - the same sidebar renders differently
//      depending on how it was reached.
//
// The patch keeps upstream's resolution order (a sidebar already pointing at
// the entity wins, so click-through from a workspace still feels stable) and
// only makes each following step total and order-independent.

frappe.provide("frappe.ui");

(() => {
	const patch = () => {
		if (!frappe.ui.Sidebar) return false;
		const proto = frappe.ui.Sidebar.prototype;
		if (proto.__cx_sidebar_resolution_fix) return true;
		proto.__cx_sidebar_resolution_fix = true;

		// frappe.boot.module_app is keyed by the scrubbed module name; mirror the
		// exact expression upstream uses so both agree on the lookup key.
		const app_of_module = (module) =>
			module && frappe.boot.module_app[module.toLowerCase().replace(/[ -]/g, "_")];

		// The app a sidebar belongs to, falling back to its module when the
		// record carries no `app` (every auto-generated module sidebar).
		const app_of_sidebar = (title) => {
			const config = frappe.boot.workspace_sidebar_item[title.toLowerCase()];
			if (!config) return null;
			return config.app || app_of_module(config.module) || null;
		};

		// Upstream passes router.meta.module, but router.meta is only assigned
		// while parsing a doctype URL and is never cleared, so it goes stale on
		// workspace / report / page routes. The entity's own meta is authoritative
		// whenever the entity is a loaded doctype.
		const module_of_entity = (entity) => {
			if (!entity) return null;
			const meta = frappe.get_meta && frappe.get_meta(entity);
			return (meta && meta.module) || null;
		};

		proto.filter_sidebars_from_app = function (sidebars, app) {
			const filtered = [];
			(sidebars || []).forEach((sidebar) => {
				if (app_of_sidebar(sidebar) === app && !filtered.includes(sidebar)) {
					filtered.push(sidebar);
				}
			});
			return filtered;
		};

		proto.get_remembered_sidebar = function (entity) {
			try {
				const map = JSON.parse(localStorage.getItem("sidebar_item_map") || "{}");
				const value = map[entity];
				// legacy entries are append-only arrays: the newest one is the useful one
				return Array.isArray(value) ? value[value.length - 1] : value || null;
			} catch (e) {
				return null;
			}
		};

		proto.resolve_sidebar = function (entity, module) {
			module = module_of_entity(entity) || module;

			let candidates = Array.from(new Set(this.get_workspace_sidebars(entity)));
			this.preferred_sidebars = candidates;

			if (!candidates.length) {
				return module ? this.resolve_module_sidebar(module) : null;
			}

			// 1. the sidebar on screen already links to this entity -> keep it
			if (this.sidebar_title && candidates.includes(this.sidebar_title)) {
				return this.sidebar_title;
			}

			// 2. narrow to the app that owns the entity's module
			if (module) {
				const in_app = this.filter_sidebars_from_app(candidates, app_of_module(module));
				if (in_app.length) candidates = in_app;
			}
			if (candidates.length === 1) return candidates[0];

			// 3. a curated Workspace Sidebar always beats the flat module dump that
			//    auto_generate_sidebar_from_module() builds for module without a record
			const curated = candidates.filter(
				(c) => !(frappe.boot.workspace_sidebar_item[c.toLowerCase()] || {}).is_auto_generated
			);
			if (curated.length) candidates = curated;
			if (candidates.length === 1) return candidates[0];

			// 4. prefer the sidebar named after the module, then the ones declaring it
			if (module) {
				const exact = candidates.find((c) => c.toLowerCase() === module.toLowerCase());
				if (exact) return exact;

				const same_module = candidates.filter(
					(c) =>
						(frappe.boot.workspace_sidebar_item[c.toLowerCase()] || {}).module === module
				);
				if (same_module.length === 1) return same_module[0];
				if (same_module.length) candidates = same_module;
			}

			// 5. the user's remembered choice, but only while it is still a candidate
			const remembered = this.get_remembered_sidebar(entity);
			if (remembered && candidates.includes(remembered)) return remembered;

			// 6. stable tie-break: alphabetical, never boot-dict key order
			return candidates.slice().sort()[0];
		};

		// Key by route entity (what resolve_sidebar reads) and keep only the latest
		// choice, so the map can no longer pin an entity to an unrelated sidebar.
		// Only record a sidebar that actually links to the entity.
		proto.store_last_show_sidebar_for_item = function () {
			try {
				if (!this.sidebar_title) return;
				const route = frappe.get_route();
				if (!route || !route.length) return;

				const entity = this.entity_from_route(route);
				if (!entity) return;
				if (!this.get_workspace_sidebars(entity).includes(this.sidebar_title)) return;

				const map = JSON.parse(localStorage.getItem("sidebar_item_map") || "{}");
				map[entity] = [this.sidebar_title];
				this.item_sidebar_map = map;
				localStorage.setItem("sidebar_item_map", JSON.stringify(map));
			} catch (e) {
				// localStorage can be unavailable (private mode) - never break navigation
			}
		};

		// Always resolve the app, and never leave a stale frappe.current_app behind:
		// it drives the header subtitle and the app-switcher sibling icons.
		proto.choose_app_name = function () {
			if (frappe.boot.app_name_style === "Default") return;

			const app_data = frappe.boot.app_data || [];
			const app_name = app_of_sidebar(this.sidebar_title);

			let app = app_data.find((a) => (a.workspaces || []).includes(this.sidebar_title));
			if (!app && app_name) app = app_data.find((a) => a.app_name === app_name);

			if (app) {
				this.header_subtitle = app.app_title;
				this.app_logo_url = app.app_logo_url;
				frappe.current_app = app;
				return;
			}

			frappe.current_app = null;
			this.app_logo_url = null;

			if (this.sidebar_title === "My Workspaces") {
				this.header_subtitle = frappe.session.user;
				return;
			}
			const icon = (frappe.boot.desktop_icons || []).find(
				(i) => i.label === this.sidebar_title
			);
			this.header_subtitle = icon ? icon.parent_icon : frappe.session.user;
		};

		// One-off cleanup of maps written by the upstream (label-keyed, append-only)
		// implementation. Harmless without it - resolve_sidebar validates the value -
		// but it keeps the entry from growing forever.
		try {
			if (localStorage.getItem("sidebar_item_map_version") !== "cx1") {
				localStorage.removeItem("sidebar_item_map");
				localStorage.setItem("sidebar_item_map_version", "cx1");
			}
		} catch (e) {
			// ignore
		}

		return true;
	};

	if (!patch()) {
		$(document).ready(patch);
	}
})();
