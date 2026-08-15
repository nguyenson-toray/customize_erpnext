// Attendance Request list — bulk create requests for days with an incomplete check-in.
// Server counterpart: overrides/attendance_request/bulk_create.py + confirmation_form.py

const BULK_API = "customize_erpnext.overrides.attendance_request.bulk_create";
const FORM_API = "customize_erpnext.overrides.attendance_request.confirmation_form";

frappe.listview_settings["Attendance Request"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Bulk Create from Missing Check-ins"), () => {
			open_bulk_dialog();
		});

		// Top-level button next to Bulk Create, not buried in the Actions menu
		listview.page.add_inner_button(__("Print Confirmation Forms"), () => {
			const names = listview.get_checked_items(true);
			if (!names || !names.length) {
				frappe.msgprint({
					title: __("Nothing Selected"),
					message: __("Tick the requests you want to print, then press this button again."),
					indicator: "orange",
				});
				return;
			}
			download_forms(names);
		});
	},
};

function download_forms(names) {
	const url = `/api/method/${FORM_API}.download_confirmation_forms?names=${encodeURIComponent(
		JSON.stringify(names)
	)}`;
	window.open(url, "_blank");
}

function open_bulk_dialog() {
	const yesterday = frappe.datetime.add_days(frappe.datetime.get_today(), -1);

	const dialog = new frappe.ui.Dialog({
		title: __("Bulk Create Attendance Requests"),
		size: "extra-large",
		fields: [
			{
				fieldname: "from_date",
				label: __("From Date"),
				fieldtype: "Date",
				default: yesterday,
				reqd: 1,
			},
			{ fieldname: "cb1", fieldtype: "Column Break" },
			{
				fieldname: "to_date",
				label: __("To Date"),
				fieldtype: "Date",
				default: yesterday,
				reqd: 1,
			},
			{ fieldname: "cb2", fieldtype: "Column Break" },
			{
				fieldname: "reason",
				label: __("Reason"),
				fieldtype: "Select",
				options: ["Forget Check In/Out", "Machine Error", "First Working Day", "Other"].join("\n"),
				default: "Forget Check In/Out",
				reqd: 1,
			},
			{ fieldname: "sb1", fieldtype: "Section Break" },
			{
				fieldname: "explanation",
				label: __("Explanation"),
				fieldtype: "Small Text",
				depends_on: "eval:doc.reason == 'Other'",
				description: __("Mandatory when the reason is Other"),
			},
			{ fieldname: "sb2", fieldtype: "Section Break" },
			{ fieldname: "results", fieldtype: "HTML" },
		],
		primary_action_label: __("Find Missing Check-ins"),
		primary_action() {
			find_candidates(dialog);
		},
	});

	dialog.show();
	// frappe's biggest preset ("extra-large") is still ~900px, too narrow for a
	// 12-column grid with inline time pickers — widen the modal itself
	dialog.$wrapper.find(".modal-dialog").css({ "max-width": "96vw", width: "96vw" });
	dialog.$wrapper.find(".modal-body").css({ "max-height": "78vh", "overflow-y": "auto" });

	dialog.fields_dict.results.$wrapper.html(
		`<div class="text-muted">${__("Pick a date range and press Find.")}</div>`
	);
}

function find_candidates(dialog) {
	const { from_date, to_date } = dialog.get_values() || {};
	if (!from_date || !to_date) return;

	frappe.call({
		method: `${BULK_API}.get_incomplete_candidates`,
		type: "GET",
		args: { from_date, to_date },
		freeze: true,
		freeze_message: __("Scanning check-ins..."),
		callback(r) {
			const rows = (r.message && r.message.rows) || [];
			dialog.candidates = rows;
			render_candidates(dialog, rows);
		},
	});
}

function render_candidates(dialog, rows) {
	const $wrapper = dialog.fields_dict.results.$wrapper;

	if (!rows.length) {
		$wrapper.html(
			`<div class="text-muted">${__("No incomplete check-ins found in this period.")}</div>`
		);
		dialog.set_primary_action(__("Find Missing Check-ins"), () => find_candidates(dialog));
		return;
	}

	const skipped = rows.filter((x) => !x.selected).length;
	const body = rows
		.map((row, i) => {
			const warn = [];
			if (row.resolved) warn.push(__("Already complete — nothing missing"));
			if (row.already_manual) warn.push(__("Entered manually: {0}", [row.manual_checkins]));
			if (row.already_requested) warn.push(__("Already has a request"));

			return `<tr data-idx="${i}" class="${
				row.resolved ? "acr-done" : warn.length ? "acr-warn" : ""
			}">
				<td class="text-center">
					<input type="checkbox" class="acr-pick" ${row.selected ? "checked" : ""}>
				</td>
				<td>${frappe.utils.escape_html(row.employee)}</td>
				<td>${frappe.utils.escape_html(row.employee_name || "")}</td>
				<td>${frappe.utils.escape_html(row.custom_group || "")}</td>
				<td class="text-center">${frappe.utils.escape_html(
					frappe.datetime.str_to_user(row.date)
				)} <span class="text-muted">${frappe.utils.escape_html(row.day_of_week || "")}</span></td>
				<td>${frappe.utils.escape_html(row.shift || "")}</td>
				<td class="text-center">${frappe.utils.escape_html(
					(row.all_scans || []).join(", ") || "-"
				)}</td>
				<td class="text-center">${
					row.missing_side
						? `<span class="indicator-pill ${
								row.missing_side === "in" ? "orange" : "blue"
						  }">${row.missing_side === "in" ? __("Missing IN") : __("Missing OUT")}</span>`
						: row.resolved
						? `<span class="indicator-pill green">${__("Complete")}</span>`
						: `<span class="text-muted">?</span>`
				}</td>
				<td class="acr-cell-in"></td>
				<td class="acr-cell-out"></td>
				<td class="acr-cell-remark"></td>
				<td class="small text-muted">${frappe.utils.escape_html(warn.join("; "))}</td>
			</tr>`;
		})
		.join("");

	$wrapper.html(`
		<style>
			.acr-table { font-size: 12px; }
			.acr-table td, .acr-table th { padding: 4px 6px !important; vertical-align: middle !important; }
			.acr-table tr.acr-warn { background: var(--yellow-50, #fffbe6); }
			.acr-table tr.acr-done { background: var(--green-50, #f0fdf4); color: var(--text-muted); }
			.acr-table .form-control { height: 26px; padding: 2px 6px; font-size: 12px; }
			.acr-table .frappe-control { margin: 0 !important; }
			.acr-scroll { max-height: 58vh; overflow-y: auto; overflow-x: auto; }
		</style>
		<div class="flex justify-between align-center" style="margin-bottom:6px">
			<div><b>${__("{0} day(s) found", [rows.length])}</b>${
				skipped
					? ` <span class="text-muted">— ${__(
							"{0} unticked (already handled)",
							[skipped]
					  )}</span>`
					: ""
			}</div>
			<div>
				<button class="btn btn-xs btn-default acr-all">${__("Select all")}</button>
				<button class="btn btn-xs btn-default acr-none">${__("Select none")}</button>
			</div>
		</div>
		<div class="acr-scroll">
		<table class="table table-bordered acr-table">
			<thead><tr>
				<th style="width:32px"></th>
				<th>${__("Code")}</th>
				<th>${__("Name")}</th>
				<th>${__("Group")}</th>
				<th>${__("Date")}</th>
				<th>${__("Shift")}</th>
				<th>${__("All Check-ins")}</th>
				<th>${__("Missing")}</th>
				<th style="width:110px">${__("New In")}</th>
				<th style="width:110px">${__("New Out")}</th>
				<th style="width:130px">${__("Remark")}</th>
				<th>${__("Note")}</th>
			</tr></thead>
			<tbody>${body}</tbody>
		</table>
		</div>
	`);

	$wrapper.find(".acr-all").on("click", () => $wrapper.find(".acr-pick").prop("checked", true));
	$wrapper.find(".acr-none").on("click", () => $wrapper.find(".acr-pick").prop("checked", false));

	mount_controls(dialog, $wrapper, rows);

	dialog.set_primary_action(__("Create Draft Requests"), () => create_requests(dialog));
}

// Use frappe's own controls rather than raw <input type="time">: the Time control
// brings the standard time picker, the same parsing/formatting as every other
// form in the desk, and returns a clean "HH:MM:SS" regardless of browser locale.
function mount_controls(dialog, $wrapper, rows) {
	dialog.controls = [];

	$wrapper.find("tbody tr").each(function () {
		const $tr = $(this);
		const idx = parseInt($tr.data("idx"), 10);
		const row = rows[idx];

		dialog.controls[idx] = {
			new_in_time: make_cell_control($tr.find(".acr-cell-in"), "Time", row.new_in_time),
			new_out_time: make_cell_control($tr.find(".acr-cell-out"), "Time", row.new_out_time),
			remark: make_cell_control($tr.find(".acr-cell-remark"), "Data", null),
		};
	});
}

function make_cell_control($cell, fieldtype, value) {
	const control = frappe.ui.form.make_control({
		df: { fieldtype, fieldname: "v", label: "" },
		parent: $cell.get(0),
		render_input: true,
		only_input: true,
	});
	control.refresh();
	if (value) control.set_value(value);
	return control;
}

function collect_selected(dialog) {
	const $wrapper = dialog.fields_dict.results.$wrapper;
	const picked = [];

	$wrapper.find("tbody tr").each(function () {
		const $tr = $(this);
		if (!$tr.find(".acr-pick").is(":checked")) return;

		const idx = parseInt($tr.data("idx"), 10);
		const row = Object.assign({}, dialog.candidates[idx]);
		const controls = (dialog.controls || [])[idx] || {};

		row.new_in_time = normalize_time(controls.new_in_time && controls.new_in_time.get_value());
		row.new_out_time = normalize_time(controls.new_out_time && controls.new_out_time.get_value());
		row.remark = (controls.remark && controls.remark.get_value()) || null;

		if (row.new_in_time || row.new_out_time) picked.push(row);
	});

	return picked;
}

// The Time control may hand back "HH:MM" or "HH:MM:SS"; the server wants seconds
function normalize_time(value) {
	value = (value || "").trim();
	if (!value) return null;
	const parts = value.split(":");
	if (parts.length === 2) return `${value}:00`;
	return value;
}

function create_requests(dialog) {
	const values = dialog.get_values();
	if (!values) return;

	const rows = collect_selected(dialog);
	if (!rows.length) {
		frappe.msgprint({
			title: __("Nothing Selected"),
			message: __("Tick at least one row that has a New In or New Out time."),
			indicator: "orange",
		});
		return;
	}
	if (values.reason === "Other" && !(values.explanation || "").trim()) {
		frappe.msgprint({
			title: __("Explanation Required"),
			message: __("Explanation is mandatory when the reason is Other."),
			indicator: "orange",
		});
		return;
	}

	frappe.confirm(
		__("Create {0} draft request(s) for {1} day(s)?", [
			new Set(rows.map((r) => r.employee)).size,
			rows.length,
		]),
		() => {
			frappe.call({
				method: `${BULK_API}.bulk_create_requests`,
				args: {
					rows: JSON.stringify(rows),
					reason: values.reason,
					explanation: values.explanation,
				},
				freeze: true,
				freeze_message: __("Creating draft requests..."),
				callback(r) {
					if (!r.message) return;
					dialog.hide();
					show_result(r.message);
				},
			});
		}
	);
}

function show_result(result) {
	const created = result.created || [];
	const failed = result.failed || [];

	const links = created
		.map((n) => `<a href="/app/attendance-request/${encodeURIComponent(n)}">${n}</a>`)
		.join(", ");
	const errors = failed
		.map(
			(f) =>
				`<li>${frappe.utils.escape_html(f.employee)}: ${frappe.utils.escape_html(f.error)}</li>`
		)
		.join("");

	const d = new frappe.ui.Dialog({
		title: __("Draft Requests Created"),
		size: "large",
		fields: [
			{
				fieldname: "summary",
				fieldtype: "HTML",
				options: `
					<p>${__("Created {0} draft request(s).", [created.length])}</p>
					<p style="word-break:break-all">${links}</p>
					${
						errors
							? `<p class="text-danger">${__("{0} failed:", [failed.length])}</p><ul>${errors}</ul>`
							: ""
					}
					<p class="text-muted">${__(
						"They stay in Draft. Print the forms, collect the signatures, then submit."
					)}</p>`,
			},
		],
		primary_action_label: __("Download Signature Forms (PDF)"),
		primary_action() {
			if (created.length) download_forms(created);
		},
		secondary_action_label: __("Close"),
		secondary_action() {
			d.hide();
			if (cur_list) cur_list.refresh();
		},
	});

	d.show();
	if (!created.length) d.get_primary_btn().hide();
}
