// Attendance Request — supplement missing check in / check out.
// Server counterpart: overrides/attendance_request/attendance_request.py
//
// Mode is derived from `reason`. Keep SUPPLEMENT_REASONS identical to the tuple
// of the same name in the Python controller.

const SUPPLEMENT_REASONS = [
	"Forget Check In/Out",
	"Machine Error",
	"First Working Day",
	"Other",
];

const EXISTING_INFO_METHOD =
	"customize_erpnext.overrides.attendance_request.attendance_request.get_existing_attendance_info";

function is_supplement(frm) {
	return SUPPLEMENT_REASONS.includes(frm.doc.reason);
}

frappe.ui.form.on("Attendance Request", {
	refresh(frm) {
		toggle_supplement_ui(frm);

		if (!is_supplement(frm)) return;

		frm.dashboard.clear_headline();
		// Existing times are loaded on every refresh — including brand new,
		// never-saved forms — so the grid is never blank while the data exists
		load_existing(frm);

		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Refresh Existing Times"), () => {
				load_existing(frm, { freeze: true });
			});
		}
	},

	reason(frm) {
		toggle_supplement_ui(frm);
		if (is_supplement(frm)) rebuild(frm);
	},

	from_date(frm) {
		if (is_supplement(frm)) rebuild(frm);
	},

	to_date(frm) {
		if (is_supplement(frm)) rebuild(frm);
	},

	employee(frm) {
		if (is_supplement(frm)) rebuild(frm);
	},
});

function rebuild(frm) {
	build_rows(frm);
	load_existing(frm);
}

function toggle_supplement_ui(frm) {
	const supplement = is_supplement(frm);

	// Half day / holiday flags belong to the Work From Home & On Duty flow only
	frm.toggle_display("half_day", !supplement);
	frm.toggle_display("half_day_date", !supplement);
	frm.toggle_display("include_holidays", !supplement);

	frm.toggle_display("custom_supplement_section", supplement);
	frm.toggle_display("custom_checkin_details", supplement);
}

// Build one row per date client-side so the grid is usable before the first save.
// The server re-syncs authoritatively in sync_checkin_rows().
function build_rows(frm) {
	if (!frm.doc.from_date || !frm.doc.to_date) return;
	if (frm.doc.docstatus !== 0) return;

	// NEVER use Date.toISOString() here — it shifts to UTC and drops a day
	const days = [];
	let cursor = frm.doc.from_date;
	let guard = 0;
	while (frappe.datetime.get_diff(frm.doc.to_date, cursor) >= 0 && guard < 366) {
		days.push(cursor);
		cursor = frappe.datetime.add_days(cursor, 1);
		guard += 1;
	}

	const existing = {};
	(frm.doc.custom_checkin_details || []).forEach((row) => {
		if (row.date) existing[row.date] = row;
	});

	const kept = days.map((day) => existing[day] || { date: day });

	frm.clear_table("custom_checkin_details");
	kept.forEach((row) => {
		const child = frm.add_child("custom_checkin_details");
		Object.keys(row).forEach((key) => {
			if (!["name", "idx", "owner", "creation", "modified", "docstatus", "parent"].includes(key)) {
				child[key] = row[key];
			}
		});
	});
	frm.refresh_field("custom_checkin_details");
}

// Pull the existing attendance / check-ins straight from the server. Works on an
// unsaved form because the method takes plain arguments, not a document.
function load_existing(frm, opts = {}) {
	if (!is_supplement(frm)) return;
	if (!frm.doc.employee || !frm.doc.from_date || !frm.doc.to_date) return;

	frappe.call({
		method: EXISTING_INFO_METHOD,
		type: "GET",
		args: {
			employee: frm.doc.employee,
			from_date: frm.doc.from_date,
			to_date: frm.doc.to_date,
		},
		freeze: !!opts.freeze,
		freeze_message: __("Loading existing check-ins..."),
		callback(r) {
			if (!r.message) return;
			const days = r.message.days || [];
			apply_existing_times(frm, days);
			render_dashboard(frm, days);
		},
	});
}

function apply_existing_times(frm, days) {
	if (frm.doc.docstatus !== 0) return;

	const by_date = {};
	days.forEach((day) => (by_date[day.date] = day));

	(frm.doc.custom_checkin_details || []).forEach((row) => {
		const day = by_date[row.date];
		if (!day) return;
		row.day_of_week = day.day_of_week;
		row.existing_status = day.status || "-";
		row.existing_in_time = day.in_time;
		row.existing_out_time = day.out_time;
		row.existing_working_hours = day.working_hours;
	});
	frm.refresh_field("custom_checkin_details");
}

function render_dashboard(frm, days) {
	frm.dashboard.clear_headline();
	if (!days.length) return;

	const rows = days
		.map((day) => {
			const logs = (day.checkins || []).length
				? day.checkins
						.map(
							(c) =>
								`${frappe.utils.escape_html(c.time)} (${frappe.utils.escape_html(
									c.log_type || "-"
								)})`
						)
						.join(", ")
				: `<span class="text-muted">${__("No check-in")}</span>`;
			const attendance = day.attendance
				? `<a href="/app/attendance/${encodeURIComponent(day.attendance)}">${frappe.utils.escape_html(
						day.status || "-"
				  )}</a>`
				: `<span class="text-muted">${__("No attendance")}</span>`;
			return `<tr>
				<td>${frappe.utils.escape_html(frappe.datetime.str_to_user(day.date))}</td>
				<td>${frappe.utils.escape_html(day.day_of_week || "")}</td>
				<td>${attendance}</td>
				<td>${frappe.utils.escape_html(day.in_time || "-")}</td>
				<td>${frappe.utils.escape_html(day.out_time || "-")}</td>
				<td>${day.working_hours || 0}</td>
				<td>${logs}</td>
			</tr>`;
		})
		.join("");

	const html = `<div class="table-responsive">
		<table class="table table-bordered table-sm" style="margin-bottom:0">
			<thead>
				<tr>
					<th>${__("Date")}</th>
					<th>${__("Day of Week")}</th>
					<th>${__("Status")}</th>
					<th>${__("Check-in Time")}</th>
					<th>${__("Check-out Time")}</th>
					<th>${__("Hours")}</th>
					<th>${__("All Check-ins")}</th>
				</tr>
			</thead>
			<tbody>${rows}</tbody>
		</table>
	</div>`;

	frm.dashboard.reset();
	frm.dashboard.add_section(html, __("Existing Attendance & Check-ins"));
	frm.dashboard.show();
}
