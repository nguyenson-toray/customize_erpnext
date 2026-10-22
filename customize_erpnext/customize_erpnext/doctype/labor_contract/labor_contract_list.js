// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.listview_settings['Labor Contract'] = {
	get_indicator: function (doc) {
		if (doc.status === 'Signed') {
			return [__('Signed'), 'green', 'status,=,Signed'];
		}
		if (doc.status === 'Overdue') {
			return [__('Overdue'), 'red', 'status,=,Overdue'];
		}
		return [__('Upcoming'), 'orange', 'status,=,Upcoming'];
	},

	onload: function (list_view) {
		if (!frappe.perm.has_perm('Labor Contract', 0, 'create')) {
			return;
		}
		list_view.page.add_inner_button(__('Create Probation Contracts'), function () {
			show_bulk_create_probation_contracts(list_view);
		});

		list_view.page.add_inner_button(__('Review Expiring Contracts'), function () {
			show_review_expiring_contracts(list_view);
		});

		list_view.page.add_inner_button(__('Mark as Signed'), function () {
			show_mark_as_signed(list_view);
		});

		// Scans live in the ⋯ menu — the toolbar is for the renewal workflow
		list_view.page.add_menu_item(__('1. Upload Signed Scans'), function () {
			show_upload_scans(list_view);
		});

		list_view.page.add_menu_item(__('2. Download Signed Scans'), function () {
			download_signed_scans(list_view);
		});
	},
};

function show_bulk_create_probation_contracts(list_view) {
	const dialog = new frappe.ui.Dialog({
		title: __('Create Probation Contracts'),
		size: 'large',
		fields: [
			{
				fieldtype: 'Section Break',
				label: __('Target Employees'),
				description: __('Lists every Active employee who has no Labor Contract yet and creates their first probationary contract — each contract starts on their Date of Joining, with the type taken from their Probation Days (30/60). Employees without Probation Days hold special designations that don\'t need a contract and are not listed.'),
			},
			{
				fieldtype: 'Select',
				fieldname: 'filter_by',
				label: __('Target'),
				options: [
					{ value: 'Missing Contract', label: __('All Employees Missing a Contract') },
					{ value: 'Employees', label: __('Specific Employees') },
				],
				default: 'Missing Contract',
				onchange: function () {
					const by_employees = dialog.get_value('filter_by') === 'Employees';
					dialog.set_df_property('employees', 'hidden', !by_employees);
					dialog.set_df_property('employees', 'reqd', by_employees);
					refresh_preview(dialog);
				},
			},
			{
				fieldtype: 'Column Break',
			},
			{
				fieldtype: 'MultiSelectList',
				fieldname: 'employees',
				label: __('Employees'),
				hidden: 1,
				get_data: function (txt) {
					return frappe.db.get_link_options('Employee', txt, { status: 'Active' });
				},
				onchange: function () {
					refresh_preview(dialog);
				},
			},
			{
				fieldtype: 'Section Break',
				label: __('Employees to Process'),
			},
			{
				fieldtype: 'HTML',
				fieldname: 'preview',
				options: `<div id="lc-bulk-preview" class="text-muted">${__('Loading...')}</div>`,
			},
		],
		primary_action_label: __('Create'),
		primary_action: function (values) {
			run_bulk_create_probation_contracts(values, dialog, list_view);
		},
	});

	dialog.show();
	refresh_preview(dialog);
}

function refresh_preview(dialog) {
	const values = dialog.get_values(true) || {};
	const by_employees = values.filter_by === 'Employees';

	// Never hit the server with an empty pick — it throws, which would pop an
	// error dialog just from switching the target.
	if (by_employees && !(values.employees || []).length) {
		dialog.$wrapper
			.find('#lc-bulk-preview')
			.html(`<div class="text-muted">${__('Select at least one employee.')}</div>`);
		return;
	}

	frappe.call({
		method: 'customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract.get_probation_contract_candidates',
		args: {
			filter_by: values.filter_by || 'Missing Contract',
			employees: by_employees ? JSON.stringify(values.employees || []) : null,
		},
		callback: function (r) {
			render_candidates(dialog.$wrapper.find('#lc-bulk-preview'), r.message || []);
		},
	});
}

function render_candidates($target, rows) {
	if (!rows.length) {
		$target.html(`<div class="text-muted">${__('Every Active employee already has a Labor Contract.')}</div>`);
		return;
	}

	const will_create = rows.filter((row) => row.will_create).length;

	const body = rows
		.map((row) => {
			const note = row.will_create
				? frappe.utils.escape_html(row.contract_type)
				: `<span class="text-muted">${frappe.utils.escape_html(row.reason || '')}</span>`;
			return `<tr class="${row.will_create ? '' : 'text-muted'}">
				<td>${frappe.utils.escape_html(row.employee)}</td>
				<td>${frappe.utils.escape_html(row.employee_name || '')}</td>
				<td>${frappe.utils.escape_html(row.designation || '')}</td>
				<td>${row.date_of_joining ? frappe.datetime.str_to_user(row.date_of_joining) : ''}</td>
				<td>${note}</td>
			</tr>`;
		})
		.join('');

	$target.html(`
		<div style="margin-bottom: 8px;">
			${__('{0} of {1} employees will get a contract', [`<strong>${will_create}</strong>`, rows.length])}
		</div>
		<div style="max-height: 320px; overflow-y: auto;">
			<table class="table table-bordered table-sm" style="font-size: 13px;">
				<thead>
					<tr>
						<th>${__('Employee')}</th>
						<th>${__('Name')}</th>
						<th>${__('Designation')}</th>
						<th>${__('Date of Joining')}</th>
						<th>${__('Contract Type / Skip Reason')}</th>
					</tr>
				</thead>
				<tbody>${body}</tbody>
			</table>
		</div>
	`);
}

function run_bulk_create_probation_contracts(values, dialog, list_view) {
	frappe.call({
		method: 'customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract.bulk_create_probation_contracts',
		args: {
			filter_by: values.filter_by || 'Missing Contract',
			employees: values.filter_by === 'Employees' ? JSON.stringify(values.employees || []) : null,
		},
		freeze: true,
		freeze_message: __('Processing...'),
		callback: function (r) {
			if (r.exc || !r.message) {
				frappe.msgprint({
					title: __('Error'),
					indicator: 'red',
					message: __('Failed to create Labor Contracts. Check Error Log.'),
				});
				return;
			}

			dialog.hide();

			if (r.message.queued) {
				frappe.show_alert({
					message: __('Queued: creating contracts for {0} employees in the background...', [r.message.total]),
					indicator: 'blue',
				}, 7);

				frappe.realtime.off('labor_contract_bulk_create_complete');
				frappe.realtime.on('labor_contract_bulk_create_complete', function (result) {
					show_bulk_create_result(result);
					list_view.refresh();
				});
				return;
			}

			show_bulk_create_result(r.message);
			list_view.refresh();
		},
	});
}

function show_bulk_create_result(result) {
	const errors = result.errors || [];
	let errors_html = '';
	if (errors.length) {
		const rows = errors
			.slice(0, 20)
			.map(
				(e) =>
					`<tr><td>${frappe.utils.escape_html(e.employee)}</td>` +
					`<td>${frappe.utils.escape_html(e.error)}</td></tr>`
			)
			.join('');
		errors_html = `
			<div class="mt-3">
				<strong>${__('Skipped')}:</strong>
				<table class="table table-bordered table-sm mt-2">
					<thead><tr><th>${__('Employee')}</th><th>${__('Reason')}</th></tr></thead>
					<tbody>${rows}</tbody>
				</table>
				${errors.length > 20 ? `<small class="text-muted">${__('...and {0} more', [errors.length - 20])}</small>` : ''}
			</div>`;
	}

	frappe.msgprint({
		title: __('Bulk Create Completed'),
		indicator: result.created > 0 ? 'green' : 'orange',
		message: `
			<div>${__('Created')}: <strong>${result.created}</strong></div>
			<div>${__('Skipped')}: <strong>${result.skipped}</strong></div>
			${errors_html}
		`,
		wide: true,
	});
}

// ---------------------------------------------------------------------------
// Review Expiring Contracts — month-at-a-time renewal workflow
// ---------------------------------------------------------------------------

function show_review_expiring_contracts(list_view) {
	const dialog = new frappe.ui.Dialog({
		title: __('Review Expiring Contracts'),
		size: 'extra-large',
		fields: [
			{
				fieldtype: 'Section Break',
				label: __('Contracts ending between'),
				description: __('Lists every contract whose End Date falls in this range. Creating drafts adds the next contract in the sequence (starting the day after the old one ends) with status Upcoming, ready for HR to mark Signed once the paperwork is done.'),
			},
			{
				fieldtype: 'Date',
				fieldname: 'from_date',
				label: __('From Date'),
				reqd: 1,
				default: frappe.datetime.month_start(),
				include_default: 1,
				onchange: function () {
					refresh_expiring(dialog);
				},
			},
			{
				fieldtype: 'Column Break',
			},
			{
				fieldtype: 'Date',
				fieldname: 'to_date',
				label: __('To Date'),
				reqd: 1,
				default: frappe.datetime.month_end(),
				include_default: 1,
				onchange: function () {
					refresh_expiring(dialog);
				},
			},
			{
				fieldtype: 'Section Break',
				label: __('Expiring Contracts'),
			},
			{
				fieldtype: 'HTML',
				fieldname: 'result',
				options: `<div id="lc-expiring-list" class="text-muted">${__('Loading...')}</div>`,
			},
		],
		primary_action_label: __('Create Drafts'),
		primary_action: function (values) {
			run_draft_expiring_contracts(values, dialog, list_view);
		},
	});

	dialog.show();
	refresh_expiring(dialog);
}

function refresh_expiring(dialog) {
	const values = dialog.get_values(true) || {};
	if (!values.from_date || !values.to_date) {
		dialog.$wrapper.find('#lc-expiring-list').html(`<div class="text-muted">${__('Pick both dates.')}</div>`);
		return;
	}
	if (values.from_date > values.to_date) {
		dialog.$wrapper.find('#lc-expiring-list').html(
			`<div class="text-danger">${__('From Date cannot be after To Date')}</div>`
		);
		return;
	}

	frappe.call({
		method: 'customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract.get_expiring_contracts',
		args: { from_date: values.from_date, to_date: values.to_date },
		callback: function (r) {
			render_expiring(dialog.$wrapper.find('#lc-expiring-list'), r.message || [], dialog);
		},
	});
}

function render_expiring($target, rows, dialog) {
	const ready = rows.filter((row) => row.can_draft).length;

	// Nothing to draft -> don't let the user fire a no-op
	if (ready) {
		dialog.enable_primary_action();
	} else {
		dialog.disable_primary_action();
	}

	if (!rows.length) {
		$target.html(`<div class="text-muted">${__('No contracts end in this range.')}</div>`);
		return;
	}

	const body = rows
		.map((row) => {
			const action = row.can_draft
				? `<span style="color: var(--green-600, green);">${__('Will create')}: ${frappe.utils.escape_html(row.next_contract_type)}</span>`
				: `<span class="text-muted">${frappe.utils.escape_html(row.reason || '')}</span>`;
			return `<tr class="${row.can_draft ? '' : 'text-muted'}">
				<td>${frappe.utils.escape_html(row.employee)}</td>
				<td>${frappe.utils.escape_html(row.employee_name || '')}</td>
				<td>${frappe.utils.escape_html(row.contract_type || '')}</td>
				<td>${frappe.datetime.str_to_user(row.end_date)}</td>
				<td>${frappe.utils.escape_html(row.status || '')}</td>
				<td>${row.next_sign_date ? frappe.datetime.str_to_user(row.next_sign_date) : ''}</td>
				<td>${action}</td>
			</tr>`;
		})
		.join('');

	$target.html(`
		<div style="margin-bottom: 8px;">
			${__('{0} of {1} contracts are ready to renew', [`<strong>${ready}</strong>`, rows.length])}
		</div>
		<div style="max-height: 380px; overflow-y: auto;">
			<table class="table table-bordered table-sm" style="font-size: 13px;">
				<thead>
					<tr>
						<th>${__('Employee')}</th>
						<th>${__('Name')}</th>
						<th>${__('Current Contract')}</th>
						<th>${__('End Date')}</th>
						<th>${__('Status')}</th>
						<th>${__('Next Sign Date')}</th>
						<th>${__('Action')}</th>
					</tr>
				</thead>
				<tbody>${body}</tbody>
			</table>
		</div>
	`);
}

function run_draft_expiring_contracts(values, dialog, list_view) {
	frappe.confirm(
		__('Create the follow-up contracts for all ready rows between {0} and {1}?', [
			frappe.datetime.str_to_user(values.from_date),
			frappe.datetime.str_to_user(values.to_date),
		]),
		function () {
			frappe.call({
				method: 'customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract.draft_expiring_contracts',
				args: { from_date: values.from_date, to_date: values.to_date },
				freeze: true,
				freeze_message: __('Creating drafts...'),
				callback: function (r) {
					if (r.exc || !r.message) {
						return;
					}
					dialog.hide();
					frappe.msgprint({
						title: __('Drafts Created'),
						indicator: r.message.created > 0 ? 'green' : 'orange',
						message: `<div>${__('Created')}: <strong>${r.message.created}</strong></div>
						          <div>${__('Failed')}: <strong>${r.message.skipped}</strong></div>`,
					});
					list_view.refresh();
				},
			});
		}
	);
}

// ---------------------------------------------------------------------------
// Mark as Signed (bulk)
// ---------------------------------------------------------------------------
// Same interaction as the fingerprint sync tools: act on ticked rows straight
// away, otherwise open a picker.

function show_mark_as_signed(list_view) {
	const selected = (list_view.get_checked_items() || []).filter(
		(row) => row.status !== 'Signed'
	);

	if (selected.length) {
		const names = selected.map((row) => row.name);
		frappe.prompt(
			[
				{
					fieldtype: 'Date',
					fieldname: 'signed_on',
					label: __('Signed On'),
					default: frappe.datetime.get_today(),
					reqd: 1,
					description: __('Actual signing date'),
				},
			],
			(values) => run_mark_as_signed(names, values.signed_on, null, list_view),
			__('Mark {0} selected document(s) as Signed', [names.length]),
			__('Mark as Signed')
		);
		return;
	}

	show_pick_contracts_to_sign(list_view);
}

function show_pick_contracts_to_sign(list_view) {
	const dialog = new frappe.ui.Dialog({
		title: __('Mark as Signed'),
		size: 'extra-large',
		fields: [
			{
				fieldtype: 'Section Break',
				label: __('Unsigned Contracts'),
				description: __('Nothing was ticked in the list, so pick the contracts and appendices here. Marking a contract Signed also updates that employee\'s Employment Type to the contract type currently in effect.'),
			},
			{
				fieldtype: 'Date',
				fieldname: 'signed_on',
				label: __('Signed On'),
				default: frappe.datetime.get_today(),
				reqd: 1,
				description: __('Actual signing date'),
			},
			{
				fieldtype: 'Column Break',
			},
			{
				fieldtype: 'MultiSelectList',
				fieldname: 'employees',
				label: __('Employees'),
				description: __('Leave empty for all employees'),
				get_data: function (txt) {
					return frappe.db.get_link_options('Employee', txt, { status: 'Active' });
				},
				onchange: function () {
					reload_unsigned(dialog);
				},
			},
			{
				fieldtype: 'Section Break',
			},
			{
				fieldtype: 'HTML',
				fieldname: 'picker',
				options: `<div id="lc-sign-picker" class="text-muted">${__('Loading...')}</div>`,
			},
		],
		primary_action_label: __('Mark as Signed'),
		primary_action: function (values) {
			const names = get_picked_contracts(dialog);
			if (!names.length) {
				frappe.msgprint(__('Please select at least one contract'));
				return;
			}
			frappe.confirm(
				__('Mark {0} document(s) as Signed on {1}?', [names.length, frappe.datetime.str_to_user(values.signed_on)]),
				() => run_mark_as_signed(names, values.signed_on, dialog, list_view)
			);
		},
	});

	dialog.show();
	reload_unsigned(dialog);
}

function reload_unsigned(dialog) {
	const values = dialog.get_values(true) || {};
	frappe.call({
		method: 'customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract.get_unsigned_contracts',
		args: {
			employees: (values.employees || []).length ? JSON.stringify(values.employees) : null,
		},
		callback: function (r) {
			render_sign_picker(dialog.$wrapper.find('#lc-sign-picker'), r.message || []);
		},
	});
}

function render_sign_picker($target, rows) {
	if (!rows.length) {
		$target.html(`<div class="text-muted">${__('No unsigned contracts found.')}</div>`);
		return;
	}

	const body = rows
		.map(
			(row) => `<tr>
				<td><input type="checkbox" class="lc-sign-check" data-name="${frappe.utils.escape_html(row.name)}"></td>
				<td>${frappe.utils.escape_html(row.employee)}</td>
				<td>${frappe.utils.escape_html(row.employee_name || '')}</td>
				<td>${frappe.utils.escape_html(row.name)}</td>
				<td>${frappe.utils.escape_html(row.document_type === 'Appendix' ? __('Appendix') : row.contract_type || '')}</td>
				<td>${frappe.datetime.str_to_user(row.start_date)}</td>
				<td>${row.end_date ? frappe.datetime.str_to_user(row.end_date) : ''}</td>
				<td>${frappe.utils.escape_html(row.status || '')}</td>
			</tr>`
		)
		.join('');

	// Server caps the picker at 500 rows — say so instead of silently hiding the rest
	const capped = rows.length >= 500
		? `<span class="text-danger" style="margin-left: 8px;">${__('Showing the first 500 only — filter by employee to see the rest.')}</span>`
		: '';

	$target.html(`
		<div style="margin-bottom: 8px;">
			<button class="btn btn-xs btn-default lc-sign-all">${__('Select All')}</button>
			<button class="btn btn-xs btn-default lc-sign-none">${__('Clear')}</button>
			<span class="text-muted" style="margin-left: 8px;">${__('{0} contracts', [rows.length])}</span>
			${capped}
		</div>
		<div style="max-height: 380px; overflow-y: auto;">
			<table class="table table-bordered table-sm" style="font-size: 13px;">
				<thead>
					<tr>
						<th style="width: 32px;"></th>
						<th>${__('Employee')}</th>
						<th>${__('Name')}</th>
						<th>${__('Document No')}</th>
						<th>${__('Contract Type')}</th>
						<th>${__('Start Date')}</th>
						<th>${__('End Date')}</th>
						<th>${__('Status')}</th>
					</tr>
				</thead>
				<tbody>${body}</tbody>
			</table>
		</div>
	`);

	$target.find('.lc-sign-all').on('click', () => $target.find('.lc-sign-check').prop('checked', true));
	$target.find('.lc-sign-none').on('click', () => $target.find('.lc-sign-check').prop('checked', false));
}

// Scoped to this dialog: every button click builds a new Dialog and the old
// ones stay (hidden) in the DOM with the same ids, so a global $('#…') lookup
// would hit a stale dialog.
function get_picked_contracts(dialog) {
	return dialog.$wrapper.find('#lc-sign-picker .lc-sign-check:checked')
		.map(function () {
			return $(this).data('name');
		})
		.get();
}

function run_mark_as_signed(names, signed_on, dialog, list_view) {
	frappe.call({
		method: 'customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract.bulk_mark_signed',
		args: { contracts: JSON.stringify(names), signed_on: signed_on },
		freeze: true,
		freeze_message: __('Marking as Signed...'),
		callback: function (r) {
			if (r.exc || !r.message) {
				return;
			}
			if (dialog) {
				dialog.hide();
			}
			const skipped_rows = (r.message.errors || [])
				.map((e) => `<tr><td>${frappe.utils.escape_html(e.contract)}</td><td>${frappe.utils.escape_html(e.error)}</td></tr>`)
				.join('');
			frappe.msgprint({
				title: __('Done'),
				indicator: r.message.signed > 0 ? 'green' : 'orange',
				message: `<div>${__('Marked as Signed')}: <strong>${r.message.signed}</strong></div>
				          <div>${__('Skipped')}: <strong>${r.message.skipped}</strong></div>
				          ${skipped_rows ? `<table class="table table-bordered table-sm mt-2"><tbody>${skipped_rows}</tbody></table>` : ''}
				          <div class="text-muted" style="margin-top:6px;">${__('Employment Type updated on the matching employees.')}</div>`,
			});
			list_view.refresh();
		},
	});
}

// ---------------------------------------------------------------------------
// Upload Signed Scans (bulk)
// ---------------------------------------------------------------------------
// Each file goes to the record whose document number its name starts with
// (TIQN-2548-HD1.pdf -> TIQN-2548-HD1). Preview first, then upload one by one
// through upload_file + upload_scan, which re-checks every file on the server.

const SCAN_METHOD = 'customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract';

function show_upload_scans(list_view) {
	let files = [];
	let matches = [];
	let uploaded = 0;

	const dialog = new frappe.ui.Dialog({
		title: __('Upload Signed Scans'),
		size: 'extra-large',
		fields: [
			{
				fieldtype: 'HTML',
				fieldname: 'picker',
				options: `<div>
					<p class="text-muted">${__('Name each file after its document number, e.g. {0} or {1}. PDF, JPG or PNG; stored as private files.', ['<b>TIQN-2548-HD1.pdf</b>', '<b>PL-TIQN-2548-2610.pdf</b>'])}</p>
					<input type="file" class="lc-scan-input" multiple accept=".pdf,.jpg,.jpeg,.png">
				</div>`,
			},
			{
				fieldtype: 'Section Break',
			},
			{
				fieldtype: 'Check',
				fieldname: 'mark_signed',
				label: __('Also mark unsigned documents as Signed'),
				default: 1,
				onchange: () => dialog.set_df_property('signed_on', 'hidden', !dialog.get_value('mark_signed')),
			},
			{
				fieldtype: 'Column Break',
			},
			{
				fieldtype: 'Date',
				fieldname: 'signed_on',
				label: __('Signed On'),
				default: frappe.datetime.get_today(),
				description: __('Actual signing date'),
			},
			{
				fieldtype: 'Section Break',
			},
			{
				fieldtype: 'HTML',
				fieldname: 'preview',
				options: '<div class="lc-scan-preview"></div>',
			},
		],
		primary_action_label: __('Upload'),
		primary_action: async (values) => {
			const ready = matches.filter((m) => !m.error && !m.done);
			if (!ready.length) {
				frappe.msgprint(__('No file is ready to upload.'));
				return;
			}
			if (values.mark_signed && !values.signed_on) {
				frappe.msgprint(__('Please set Signed On'));
				return;
			}
			dialog.disable_primary_action();
			for (const [i, m] of ready.entries()) {
				frappe.show_progress(__('Uploading scans'), i, ready.length, m.file_name);
				try {
					const result = await upload_scan_file(files[m.index], values);
					m.done = true;
					m.result = result.note
						? __('Uploaded, not signed: {0}', [result.note])
						: __('Uploaded') + (result.status === 'Signed' ? ` · ${__('Signed')}` : '');
					uploaded += 1;
				} catch (e) {
					m.error = e.message;
				}
				render_scan_preview(dialog, matches);
			}
			frappe.hide_progress();
			dialog.enable_primary_action();
			if (uploaded) {
				list_view.refresh();
			}
			frappe.show_alert({
				message: __('{0} scan(s) uploaded', [uploaded]),
				indicator: uploaded ? 'green' : 'orange',
			});
		},
	});

	dialog.$wrapper.find('.lc-scan-input').on('change', function () {
		files = Array.from(this.files || []);
		uploaded = 0;
		if (!files.length) {
			matches = [];
			render_scan_preview(dialog, matches);
			return;
		}
		frappe.call({
			method: `${SCAN_METHOD}.match_scan_files`,
			args: { file_names: JSON.stringify(files.map((f) => f.name)) },
			callback: (r) => {
				matches = (r.message || []).map((m, index) => ({ ...m, index }));
				// two files for one record: only the first can be attached
				const seen = new Set();
				for (const m of matches) {
					if (m.contract && !m.error) {
						if (seen.has(m.contract)) {
							m.error = __('Another selected file is already going to {0}', [m.contract]);
						}
						seen.add(m.contract);
					}
				}
				render_scan_preview(dialog, matches);
			},
		});
	});

	dialog.show();
}

function render_scan_preview(dialog, matches) {
	const $target = dialog.$wrapper.find('.lc-scan-preview');
	if (!matches.length) {
		$target.html('');
		return;
	}
	const esc = frappe.utils.escape_html;
	const ready = matches.filter((m) => !m.error && !m.done).length;
	const body = matches
		.map((m) => {
			let result;
			if (m.done) {
				result = `<span style="color: var(--green-600, green);">${esc(m.result)}</span>`;
			} else if (m.error) {
				result = `<span class="text-danger">${esc(m.error)}</span>`;
			} else {
				result = `<span class="text-muted">${__('Ready')}</span>`;
			}
			return `<tr>
				<td>${esc(m.file_name)}</td>
				<td>${m.contract ? `<a href="/app/labor-contract/${encodeURIComponent(m.contract)}" target="_blank">${esc(m.contract)}</a>` : ''}</td>
				<td>${esc(m.employee_name || '')}</td>
				<td>${esc(m.status ? __(m.status) : '')}</td>
				<td>${result}</td>
			</tr>`;
		})
		.join('');

	$target.html(`
		<div style="margin-bottom: 8px;">${__('{0} of {1} files ready to upload', [`<strong>${ready}</strong>`, matches.length])}</div>
		<div style="max-height: 380px; overflow-y: auto;">
			<table class="table table-bordered table-sm" style="font-size: 13px;">
				<thead>
					<tr>
						<th>${__('File')}</th>
						<th>${__('Document No')}</th>
						<th>${__('Employee Name')}</th>
						<th>${__('Status')}</th>
						<th>${__('Result')}</th>
					</tr>
				</thead>
				<tbody>${body}</tbody>
			</table>
		</div>
	`);
}

async function upload_scan_file(file, values) {
	const form_data = new FormData();
	form_data.append('file', file, file.name);
	form_data.append('is_private', 1);
	form_data.append('method', `${SCAN_METHOD}.upload_scan`);
	if (values.mark_signed) {
		form_data.append('mark_signed', 1);
		form_data.append('signed_on', values.signed_on);
	}
	const response = await fetch('/api/method/upload_file', {
		method: 'POST',
		headers: { Accept: 'application/json', 'X-Frappe-CSRF-Token': frappe.csrf_token },
		body: form_data,
	});
	const data = await response.json().catch(() => ({}));
	if (!response.ok) {
		throw new Error(server_error_text(data) || response.statusText);
	}
	return data.message || {};
}

function server_error_text(data) {
	try {
		return JSON.parse(data._server_messages)
			.map((m) => $('<div>').html(JSON.parse(m).message).text())
			.join(' ');
	} catch (e) {
		return data.exception || '';
	}
}

// ---------------------------------------------------------------------------
// Download Signed Scans (ZIP)
// ---------------------------------------------------------------------------
// Ticked rows, or every document matching the current list filters. Preview first:
// open_url_post leaves the page for a JSON error if the download itself throws.

function download_signed_scans(list_view) {
	const ticked = (list_view.get_checked_items() || []).map((row) => row.name);
	const args = ticked.length
		? { contracts: JSON.stringify(ticked) }
		: { filters: JSON.stringify(list_view.get_filters_for_args()) };

	frappe.call({
		method: `${SCAN_METHOD}.preview_scan_download`,
		args: args,
		freeze: true,
		callback: (r) => {
			const p = r.message;
			if (!p) {
				return;
			}
			const scope = ticked.length
				? __('{0} ticked document(s)', [ticked.length])
				: __('all documents matching the current filters');
			if (!p.count) {
				frappe.msgprint(__('None of {0} has a scan.', [scope]));
				return;
			}
			const missing = p.missing.length
				? `<div class="text-muted mt-2">${__('{0} document(s) without a scan are listed in _missing_scans.txt inside the ZIP.', [p.missing.length])}</div>`
				: '';
			frappe.confirm(
				`${__('Download {0} scan(s) ({1}) from {2}?', [p.count, frappe.form.formatters.FileSize(p.total_size), scope])}${missing}`,
				() => open_url_post(`/api/method/${SCAN_METHOD}.download_scans`, args)
			);
		},
	});
}
