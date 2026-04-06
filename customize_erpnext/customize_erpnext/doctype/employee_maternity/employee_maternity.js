// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Maternity", {
	refresh(frm) {
		frm.set_df_property("leave_application", "read_only", 1);
		// Derived fields are read-only — computed by server on save
		frm.set_df_property("pregnant_to_date", "read_only", 1);
		frm.set_df_property("youg_child_from_date", "read_only", 1);
	},

	// ── Key input: pregnant start ──────────────────────────────────────────
	pregnant_from_date(frm) {
		_recalculate_derived(frm);
	},

	// ── Key input: maternity start (actual) ───────────────────────────────
	maternity_from_date(frm) {
		_recalculate_derived(frm);
	},

	// ── Key input: maternity start (estimate) ─────────────────────────────
	maternity_from_date_estimate(frm) {
		// Only recalculate if actual maternity_from_date is not set
		if (!frm.doc.maternity_from_date) {
			_recalculate_derived(frm);
		}
	},

	// ── Key input: estimated due date ─────────────────────────────────────
	estimated_due_date(frm) {
		// Affects pregnant_to_date when no maternity_from_date is set
		if (!frm.doc.maternity_from_date && !frm.doc.maternity_from_date_estimate) {
			frm.set_value("pregnant_to_date", frm.doc.estimated_due_date || "");
		}
	},

	// ── Maternity end override — cascade to young_child_from ──────────────
	maternity_to_date(frm) {
		_recalculate_young_child_from(frm);
		validate_pair(frm, "maternity_from_date", "maternity_to_date", __("Maternity Leave"));
	},

	// ── Key input: date of birth ───────────────────────────────────────────
	date_of_birth(frm) {
		if (frm.doc.date_of_birth) {
			frm.set_value("youg_child_to_date", frappe.datetime.add_days(frm.doc.date_of_birth, 364));
		}
	},

	youg_child_to_date(frm) {
		validate_pair(frm, "youg_child_from_date", "youg_child_to_date", __("Young Child"));
	},

	validate(frm) {
		if (!validate_all_pairs(frm)) {
			frappe.validated = false;
		}
	}
});

/**
 * Recalculate all derived fields based on current form state.
 * Mirrors calculate_derived_dates() in Python controller.
 */
function _recalculate_derived(frm) {
	const mat_from = frm.doc.maternity_from_date || frm.doc.maternity_from_date_estimate;

	// 1. pregnant_to_date = mat_from - 1  (fallback: estimated_due_date)
	if (frm.doc.pregnant_from_date) {
		if (mat_from) {
			frm.set_value("pregnant_to_date", frappe.datetime.add_days(mat_from, -1));
		} else {
			frm.set_value("pregnant_to_date", frm.doc.estimated_due_date || "");
		}
	}

	// 2. maternity_to_date = mat_from + 6 months  (only if empty)
	if (mat_from && !frm.doc.maternity_to_date) {
		const mat_to = frappe.datetime.add_months(mat_from, 6);
		frm.set_value("maternity_to_date", mat_to);
	}

	// 3. youg_child_from_date = maternity_to_date + 1
	_recalculate_young_child_from(frm);
}

/**
 * Recalculate youg_child_from_date = maternity_to_date + 1
 */
function _recalculate_young_child_from(frm) {
	const mat_to = frm.doc.maternity_to_date;
	if (mat_to) {
		frm.set_value("youg_child_from_date", frappe.datetime.add_days(mat_to, 1));
	} else {
		frm.set_value("youg_child_from_date", "");
	}
}

/**
 * Validate 1 cặp ngày: from < to
 */
function validate_pair(frm, from_field, to_field, label) {
	const from_date = frm.doc[from_field];
	const to_date = frm.doc[to_field];
	if (!from_date || !to_date) return true;

	if (frappe.datetime.str_to_obj(from_date) >= frappe.datetime.str_to_obj(to_date)) {
		frappe.msgprint({
			title: __("Invalid Date Range"),
			message: __("{0}: From Date must be before To Date", [label]),
			indicator: "red",
		});
		frm.set_value(to_field, "");
		return false;
	}
	return true;
}

/**
 * Validate tất cả 3 cặp ngày và kiểm tra overlap
 */
function validate_all_pairs(frm) {
	const pairs = [
		{ from: "pregnant_from_date",   to: "pregnant_to_date",   label: __("Pregnant") },
		{ from: "maternity_from_date",  to: "maternity_to_date",  label: __("Maternity Leave") },
		{ from: "youg_child_from_date", to: "youg_child_to_date", label: __("Young Child") },
	];

	for (const p of pairs) {
		if (!validate_pair(frm, p.from, p.to, p.label)) return false;
	}

	// Check overlap between phases
	const active = pairs
		.filter(p => frm.doc[p.from] && frm.doc[p.to])
		.map(p => ({
			label: p.label,
			from: frappe.datetime.str_to_obj(frm.doc[p.from]),
			to:   frappe.datetime.str_to_obj(frm.doc[p.to]),
		}));

	for (let i = 0; i < active.length; i++) {
		for (let j = i + 1; j < active.length; j++) {
			const a = active[i], b = active[j];
			if (a.from <= b.to && b.from <= a.to) {
				frappe.msgprint({
					title: __("Date Overlap"),
					message: __("Date periods overlap between {0} and {1}", [a.label, b.label]),
					indicator: "red",
				});
				return false;
			}
		}
	}
	return true;
}
