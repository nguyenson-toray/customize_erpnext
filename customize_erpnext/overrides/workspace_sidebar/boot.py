"""Flag which entries of ``bootinfo.workspace_sidebar_item`` are auto-generated.

``frappe.boot.get_sidebar_items`` merges two very different things into one dict:

* real ``Workspace Sidebar`` records - curated, grouped, an app maintains them;
* the output of ``auto_generate_sidebar_from_module()``, a flat dump of every
  Workspace/Dashboard/DocType/Report/Page of a Module Def, built on the fly for
  each module that has no record of its own (22 of 76 on this site).

Nothing in the payload tells the two apart, so the client-side resolver in
``sidebar_resolution_fix.bundle.js`` cannot express "only fall back to the
module dump when no curated sidebar covers this doctype". The flag added here
is what lets it. Auto-generated entries also carry ``app = None``, but so do a
few real records, which is why the app field cannot stand in for this.
"""

import frappe


def mark_auto_generated_sidebars(bootinfo):
	sidebars = bootinfo.get("workspace_sidebar_item")
	if not sidebars:
		return

	curated = set(frappe.get_all("Workspace Sidebar", pluck="name"))
	for config in sidebars.values():
		config["is_auto_generated"] = config.get("label") not in curated
