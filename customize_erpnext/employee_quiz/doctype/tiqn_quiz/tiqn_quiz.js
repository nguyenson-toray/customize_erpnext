// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

const QUIZ_API = "customize_erpnext.api.employee_quiz.quiz_admin_api";
const PICKER_API = "customize_erpnext.api.employee_quiz.employee_picker";

frappe.ui.form.on("TIQN Quiz", {
	refresh(frm) {
		frm.trigger("setup_buttons");
		frm.trigger("render_qr");
		frm.trigger("setup_employee_tools");
		frm.trigger("render_results");
	},

	all_employees(frm) {
		frm.trigger("setup_employee_tools");
	},

	setup_buttons(frm) {
		if (frm.is_new()) return;
		const group = __("Quiz");

		if (frm.doc.status !== "Open") {
			frm.add_custom_button(__("Open Quiz"), () => set_status(frm, "Open"), group);
		}
		if (frm.doc.status === "Open") {
			frm.add_custom_button(__("Close Quiz"), () => set_status(frm, "Closed"), group);
		}
		frm.add_custom_button(
			__("Copy Link"),
			() => frappe.utils.copy_to_clipboard(frm.doc.quiz_link),
			group
		);
		frm.add_custom_button(
			__("Preview"),
			() => window.open(`/quiz?f=${encodeURIComponent(frm.doc.slug)}&preview=1`, "_blank"),
			group
		);
		const reports = __("Results");
		frm.add_custom_button(
			__("Result Report"),
			() => frappe.set_route("query-report", "TIQN Quiz Result", { quiz: frm.doc.name }),
			reports
		);
		frm.add_custom_button(
			__("Result Report (Detail)"),
			() => frappe.set_route("query-report", "TIQN Quiz Result", { quiz: frm.doc.name, detail: 1 }),
			reports
		);
	},

	render_qr(frm) {
		const $w = frm.fields_dict.quiz_qr.$wrapper;
		$w.empty();
		if (frm.is_new() || !frm.doc.quiz_link) return;
		frappe.call({
			method: `${QUIZ_API}.get_qr_svg`,
			args: { quiz: frm.doc.name },
			callback: ({ message: svg }) => {
				const href = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
				$w.html(`
					<div class="quiz-qr" style="display:flex;align-items:flex-end;gap:12px;margin-bottom:12px">
						<div class="quiz-qr-img" title="${__("Click to enlarge")}"
							style="width:140px;cursor:zoom-in;border:1px solid var(--border-color);border-radius:8px;padding:4px;background:#fff">
							${svg}
						</div>
						<a class="btn btn-xs btn-default" download="${frappe.utils.escape_html(frm.doc.name)}-qr.svg"
							href="${href}">${__("Download QR")}</a>
					</div>`);
				$w.find("svg").css({ width: "100%", height: "auto", display: "block" });
				$w.find(".quiz-qr-img").on("click", () => show_qr(frm, svg));
			},
		});
	},

	setup_employee_tools(frm) {
		const grid = frm.fields_dict.employees.grid;
		grid.clear_custom_buttons();
		const help = frm.fields_dict.employees_help.$wrapper;

		if (frm.doc.all_employees) {
			help.html(
				`<div class="text-muted small mb-3">${__(
					"All Active Employees is ticked: every active employee can take this quiz and this list is not used."
				)}</div>`
			);
			return;
		}
		help.html("");
		grid.add_custom_button(__("Add Employees"), () => add_employees_dialog(frm));
		grid.add_custom_button(__("Paste Codes"), () => paste_codes_dialog(frm));
	},

	render_results(frm) {
		const $w = frm.fields_dict.results_html.$wrapper;
		if (frm.is_new()) {
			$w.html("");
			return;
		}
		frappe.call({
			method: `${QUIZ_API}.get_results_summary`,
			args: { quiz: frm.doc.name },
			callback: ({ message: s }) => {
				$w.html(results_html(s));
				frm.set_intro("");
				if (s.submitted) {
					frm.set_intro(
						__(
							"Employees have already submitted this quiz: questions, points and correct answers are locked. Use Duplicate to make a new version."
						),
						"yellow"
					);
				}
			},
		});
	},
});

// Type + Correct letters are derived from the options and their Correct ticks
// (the server does the same on save — tiqn_quiz.py _validate_questions).
const QUIZ_LETTERS = ["a", "b", "c", "d", "e", "f"];

function derive_question_type(cdt, cdn) {
	const row = locals[cdt][cdn];
	const filled = QUIZ_LETTERS.filter((c) => (row["option_" + c] || "").trim());
	const correct = filled.filter((c) => row["is_correct_" + c]);
	frappe.model.set_value(cdt, cdn, {
		question_type: correct.length > 1 ? "Multiple choice" : "Single choice",
		correct_options: correct.map((c) => c.toUpperCase()).join(","),
	});
}

frappe.ui.form.on(
	"TIQN Quiz Question",
	Object.fromEntries(
		QUIZ_LETTERS.flatMap((c) => [
			["option_" + c, (frm, cdt, cdn) => derive_question_type(cdt, cdn)],
			["is_correct_" + c, (frm, cdt, cdn) => derive_question_type(cdt, cdn)],
		])
	)
);

function set_status(frm, status) {
	// Saves any pending edits together with the new status.
	frm.set_value("status", status);
	frm.save();
}

// Enlarged QR for the projector (the QR next to Quiz Link, clicked).
function show_qr(frm, svg) {
	const d = new frappe.ui.Dialog({ title: frm.doc.title, size: "large" });
	d.$body.html(`
		<div style="text-align:center">
			<div style="max-width:360px;margin:0 auto">${svg}</div>
			<div style="font-size:15px;margin:8px 0 18px;word-break:break-all">
				<a href="${frm.doc.quiz_link}" target="_blank">${frm.doc.quiz_link}</a>
			</div>
			${frm.doc.status !== "Open" ? `<div class="text-danger mt-3">${__("The quiz is not open yet.")}</div>` : ""}
		</div>`);
	d.$body.find("svg").css({ width: "100%", height: "auto" });
	d.show();
}

// Add Employees / Paste Codes only add rows to the form — no save needed first
// (an Open quiz with an empty list cannot be saved). The user saves once after.
function add_employee_rows(frm, rows) {
	const existing = new Set((frm.doc.employees || []).map((r) => r.employee));
	let added = 0;
	for (const r of rows) {
		if (existing.has(r.employee)) continue;
		frm.add_child("employees", r);
		existing.add(r.employee);
		added++;
	}
	frm.refresh_field("employees");
	if (added) frm.dirty();
	return added;
}

function not_listed(frm, rows) {
	const existing = new Set((frm.doc.employees || []).map((r) => r.employee));
	return rows.filter((r) => !existing.has(r.employee));
}

function add_employees_dialog(frm) {
	let d;
	let found = [];
	const search = frappe.utils.debounce(() => {
		frappe.call({
			method: `${PICKER_API}.find_employees`,
			args: d.get_values(true),
			callback: ({ message: rows }) => {
				found = rows || [];
				d.fields_dict.preview.$wrapper.html(
					`<div>${__("{0} matching active employee(s), {1} not in the list yet", [
						`<b>${found.length}</b>`,
						`<b>${not_listed(frm, found).length}</b>`,
					])}</div>`
				);
			},
		});
	}, 300);
	const filter = (df) => Object.assign(df, { onchange: () => search() });
	d = new frappe.ui.Dialog({
		title: __("Add Employees"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<div class="text-muted small">${__(
					"Adds active employees that match all filters. Employees already in the list are skipped."
				)}</div>`,
			},
			filter({
				fieldname: "date_from",
				fieldtype: "Date",
				label: __("Joined From"),
				default: frappe.datetime.add_days(frappe.datetime.get_today(), -14),
			}),
			filter({
				fieldname: "date_to",
				fieldtype: "Date",
				label: __("Joined To"),
				default: frappe.datetime.get_today(),
			}),
			{ fieldtype: "Column Break" },
			filter({ fieldname: "section", fieldtype: "Link", options: "Section", label: __("Section") }),
			filter({ fieldname: "group", fieldtype: "Link", options: "Group", label: __("Group") }),
			{ fieldtype: "Section Break" },
			{ fieldname: "preview", fieldtype: "HTML" },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			frappe.call({
				method: `${PICKER_API}.find_employees`,
				args: values,
				freeze: true,
				callback: ({ message: rows }) => {
					d.hide();
					const added = add_employee_rows(frm, rows || []);
					frappe.show_alert({
						message: __("{0} employee(s) added. Save the quiz to keep them.", [added]),
						indicator: "green",
					});
				},
			});
		},
	});
	d.show();
	search();
}

function paste_codes_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Paste Codes"),
		fields: [
			{
				fieldname: "codes",
				fieldtype: "Long Text",
				label: __("Employee Codes"),
				reqd: 1,
				description: __("One code per line (copy a column from Excel). TIQN-0148 or just 148."),
			},
		],
		primary_action_label: __("Add"),
		primary_action({ codes }) {
			frappe.call({
				method: `${PICKER_API}.resolve_codes`,
				args: { codes },
				freeze: true,
				callback: ({ message: r }) => {
					d.hide();
					const already = r.rows.length - not_listed(frm, r.rows).length;
					const added = add_employee_rows(frm, r.rows);
					const lines = [__("{0} employee(s) added. Save the quiz to keep them.", [added])];
					if (already) lines.push(__("{0} already in the list", [already]));
					if (r.not_found.length) lines.push(__("Not found: {0}", [r.not_found.join(", ")]));
					if (r.not_active.length) lines.push(__("Not active: {0}", [r.not_active.join(", ")]));
					frappe.msgprint(lines.join("<br>"), __("Paste Codes"));
				},
			});
		},
	});
	d.show();
}

function results_html(s) {
	const card = (label, value, color) => `
		<div class="col-sm-2 col-4 mb-3">
			<div class="text-muted small">${label}</div>
			<div style="font-size:24px;font-weight:600;${color ? `color:${color}` : ""}">${value}</div>
		</div>`;
	const pass_rate = s.submitted ? Math.round((s.passed / s.submitted) * 100) + "%" : "–";
	let html = `<div class="row">
		${card(__("Eligible"), s.eligible)}
		${card(__("Not Started"), s.not_started, "var(--red-600)")}
		${card(__("In Progress"), s.in_progress, "var(--orange-600)")}
		${card(__("Submitted"), s.submitted, "var(--green-600)")}
		${card(__("Pass Rate"), pass_rate)}
		${card(__("Average"), s.submitted ? s.average + "%" : "–")}
	</div>`;

	if (s.questions.length) {
		html += `<table class="table table-bordered table-sm mt-2">
			<thead><tr><th style="width:50px">#</th><th>${__("Question")}</th>
			<th style="width:120px">${__("Answered")}</th><th style="width:160px">${__("Correct")}</th></tr></thead><tbody>`;
		for (const q of s.questions) {
			const pct = q.correct_pct === null ? "–" : `${q.correct_pct}%`;
			const bar =
				q.correct_pct === null
					? ""
					: `<div style="height:6px;background:var(--gray-200);border-radius:3px;margin-top:4px">
						<div style="height:6px;width:${q.correct_pct}%;border-radius:3px;background:${
							q.correct_pct < 50 ? "var(--red-500)" : "var(--green-500)"
						}"></div></div>`;
			html += `<tr><td>${q.idx}</td><td>${frappe.utils.escape_html(q.question || "")}</td>
				<td>${q.total}</td><td>${pct}${bar}</td></tr>`;
		}
		html += `</tbody></table>`;
	}
	return html;
}
