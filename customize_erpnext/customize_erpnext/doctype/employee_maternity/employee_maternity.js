// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Maternity", {
	setup(frm) {
		// Chỉ nhân viên nữ — server cũng chặn (validate_employee_gender) cho Data Import.
		frm.set_query("employee", () => ({ filters: { gender: "Female" } }));
	},

	// ── Gợi ý Con thứ mấy = số hồ sơ thai sản trước đó của NV + 1 ─────────
	// Chỉ cho hồ sơ MỚI, ô còn trống và NV đã có hồ sơ trước — HR sửa được. Lấy max(child_order)
	// nếu có, không thì đếm số hồ sơ (hồ sơ trước có thể chưa điền child_order).
	employee(frm) {
		if (!frm.is_new() || !frm.doc.employee || frm.doc.child_order) return;
		frappe.db
			.get_list("Employee Maternity", {
				filters: { employee: frm.doc.employee },
				fields: ["child_order"],
				limit: 0,
			})
			.then((rows) => {
				// Chưa có hồ sơ nào → để trống: NV có thể đã có con trước khi vào công ty.
				if (!rows.length || frm.doc.child_order || !frm.is_new()) return;
				const max_order = Math.max(0, ...rows.map((r) => cint(r.child_order)));
				frm.set_value("child_order", Math.max(max_order, rows.length) + 1);
			});
	},

	// ── Quy tắc (user chốt 07/10/2026) — mirror calculate_derived_dates() ─────
	// 3 giai đoạn LUÔN liên tục:
	//   Pregnant To trống → copy Estimated Due Date
	//   Maternity From = Pregnant To + 1  (HR nhập Maternity From → Pregnant To = -1)
	//   Maternity To   = Maternity From + Leave Months - 1 ngày
	//   Young Child    = Maternity To + 1 → Date of Birth + 364 (chưa có ngày sinh → trống)
	// Hai handler pregnant_to_date ⇄ maternity_from_date gọi lẫn nhau nhưng tự dừng:
	// set_value cùng giá trị thì Frappe không bắn lại sự kiện.
	pregnant_to_date(frm) {
		if (frm.doc.pregnant_to_date) {
			frm.set_value("maternity_from_date", frappe.datetime.add_days(frm.doc.pregnant_to_date, 1));
		}
		validate_pair(frm, "pregnant_from_date", "pregnant_to_date", __("Pregnant"));
	},

	maternity_from_date(frm) {
		if (frm.doc.maternity_from_date) {
			frm.set_value("pregnant_to_date", frappe.datetime.add_days(frm.doc.maternity_from_date, -1));
		}
		_recalculate_maternity_to(frm);
	},

	estimated_due_date(frm) {
		if (!frm.doc.pregnant_to_date && frm.doc.estimated_due_date) {
			frm.set_value("pregnant_to_date", frm.doc.estimated_due_date);
		}
	},

	// ── Số tháng được nghỉ → tính lại ngày kết thúc ───────────────────────
	leave_months(frm) {
		_recalculate_maternity_to(frm);
	},

	// ── Con thứ mấy / Sinh đôi → Leave Months mặc định (mirror default_leave_months()) ──
	// 6 tháng; con thứ 2 +1; sinh đôi +1 (con thứ 2 sinh đôi = 8). HR sửa tay sau đó được giữ.
	child_order(frm) {
		frm.set_value("leave_months", _default_leave_months(frm));
	},

	is_twins(frm) {
		frm.set_value("leave_months", _default_leave_months(frm));
	},

	// ── Sẩy thai: dialog nhập ngày → Pregnant To Date, xoá giai đoạn sau, ghi Note ──
	// Mirror apply_miscarriage() trong employee_maternity.py (server cũng áp khi lưu/import).
	is_miscarriage(frm) {
		if (frm._em_skip_miscarriage) return;
		if (frm.doc.is_miscarriage) {
			_ask_miscarriage_date(frm);
		} else {
			frappe.confirm(
				__("Unmark miscarriage? Maternity dates will be recalculated from Pregnant To Date."),
				() => {
					if (frm.doc.pregnant_to_date) {
						frm.set_value("maternity_from_date",
							frappe.datetime.add_days(frm.doc.pregnant_to_date, 1));
					}
				},
				() => _set_miscarriage_silently(frm, 1)
			);
		}
	},

	maternity_to_date(frm) {
		frm.set_value("youg_child_from_date",
			frm.doc.maternity_to_date ? frappe.datetime.add_days(frm.doc.maternity_to_date, 1) : "");
	},

	date_of_birth(frm) {
		frm.set_value("youg_child_to_date",
			frm.doc.date_of_birth ? frappe.datetime.add_days(frm.doc.date_of_birth, 364) : "");
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

function _set_miscarriage_silently(frm, value) {
	frm._em_skip_miscarriage = true;
	frm.set_value("is_miscarriage", value).then(() => (frm._em_skip_miscarriage = false));
}

function _ask_miscarriage_date(frm) {
	let confirmed = false;
	const d = new frappe.ui.Dialog({
		title: __("Miscarriage"),
		fields: [
			{
				fieldname: "miscarriage_date",
				fieldtype: "Date",
				label: __("Miscarriage Date"),
				reqd: 1,
				default: frm.doc.pregnant_to_date && frm.doc.pregnant_to_date <= frappe.datetime.get_today()
					? frm.doc.pregnant_to_date : frappe.datetime.get_today(),
			},
			{
				fieldtype: "HTML",
				options: `<p class="text-muted small">${__("This date becomes Pregnant To Date. Maternity Leave, Date of Birth and Young Child dates will be cleared.")}</p>`,
			},
		],
		primary_action_label: __("Confirm"),
		primary_action(values) {
			const day = values.miscarriage_date;
			if (frm.doc.pregnant_from_date && day < frm.doc.pregnant_from_date) {
				frappe.msgprint(__("Miscarriage Date cannot be before Pregnant From Date"));
				return;
			}
			if (day > frappe.datetime.get_today()) {
				frappe.msgprint(__("Miscarriage Date cannot be in the future"));
				return;
			}
			confirmed = true;
			d.hide();
			// Xoá Maternity From TRƯỚC khi đặt Pregnant To: handler pregnant_to_date sẽ điền lại
			// Maternity From = +1, nên cuối cùng xoá thêm một lần.
			const clear = ["maternity_from_date", "maternity_to_date", "date_of_birth",
				"youg_child_from_date", "youg_child_to_date"];
			frm.set_value("pregnant_to_date", day)
				.then(() => Promise.all(clear.map((f) => frm.set_value(f, ""))))
				.then(() => frm.set_value("note", _miscarriage_note(frm.doc.note, day)));
		},
	});
	d.onhide = () => {
		if (!confirmed) _set_miscarriage_silently(frm, 0);
	};
	d.show();
}

// Mirror miscarriage_note() trong employee_maternity.py — nội dung tiếng Việt do user chốt.
function _miscarriage_note(note, day) {
	const prefix = "Sẩy thai ngày";
	const line = `${prefix} ${moment(day).format("DD/MM/YYYY")}`;  // cố định dd/mm/yyyy như server
	// Bỏ mọi dòng ghi sẩy thai cũ, kể cả gõ tay khác hoa/thường.
	const rest = (note || "").split("\n").filter((l) => l.trim() && !l.trim().toLowerCase().startsWith("sẩy thai"));
	return [line, ...rest].join("\n");
}

function _default_leave_months(frm) {
	return 6 + (cint(frm.doc.child_order) === 2 ? 1 : 0) + (frm.doc.is_twins ? 1 : 0);
}

/**
 * Maternity To = Maternity From + Leave Months - 1 ngày (nghỉ từ 19/01, 6 tháng → hết 18/07).
 * Mirror maternity_end_date() trong employee_maternity.py.
 */
function _recalculate_maternity_to(frm) {
	const mat_from = frm.doc.maternity_from_date;
	const months = cint(frm.doc.leave_months) || 6; /* DEFAULT_LEAVE_MONTHS */
	frm.set_value("maternity_to_date",
		mat_from ? frappe.datetime.add_days(frappe.datetime.add_months(mat_from, months), -1) : "");
}

/**
 * Validate 1 cặp ngày: from <= to (phase có thể chỉ 1 ngày)
 */
function validate_pair(frm, from_field, to_field, label) {
	const from_date = frm.doc[from_field];
	const to_date = frm.doc[to_field];
	if (!from_date || !to_date) return true;

	if (frappe.datetime.str_to_obj(from_date) > frappe.datetime.str_to_obj(to_date)) {
		frappe.msgprint({
			title: __("Invalid Date Range"),
			message: __("{0}: From Date cannot be after To Date", [label]),
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
		{ from: "pregnant_from_date", to: "pregnant_to_date", label: __("Pregnant") },
		{ from: "maternity_from_date", to: "maternity_to_date", label: __("Maternity Leave") },
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
			to: frappe.datetime.str_to_obj(frm.doc[p.to]),
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
