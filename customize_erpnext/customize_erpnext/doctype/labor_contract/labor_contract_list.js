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

		// One-off go-live tool: rebuilds full contract history for pre-existing
		// employees. Administrator only — it writes thousands of records.
		if (frappe.session.user === 'Administrator') {
			list_view.page.add_menu_item(__('Seed Contract History'), function () {
				show_seed_contract_history(list_view);
			});
		}
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
				description: __('Run this once per intake batch. It creates the first probationary Labor Contract for Active employees who joined on the chosen day and don\'t have a contract yet — each contract starts on their Date of Joining, with the type taken from their Probation Days (30/60). Employees without Probation Days, or who already have a contract, are skipped.'),
			},
			{
				fieldtype: 'Select',
				fieldname: 'filter_by',
				label: __('Target'),
				options: [
					{ value: 'Date of Joining', label: __('By Date of Joining') },
					{ value: 'Employees', label: __('Specific Employees') },
				],
				default: 'Date of Joining',
				onchange: function () {
					const by_date = dialog.get_value('filter_by') === 'Date of Joining';
					dialog.set_df_property('date_of_joining', 'hidden', !by_date);
					dialog.set_df_property('date_of_joining', 'reqd', by_date);
					dialog.set_df_property('employees', 'hidden', by_date);
					dialog.set_df_property('employees', 'reqd', !by_date);
					refresh_preview(dialog);
				},
			},
			{
				fieldtype: 'Column Break',
			},
			{
				fieldtype: 'Date',
				fieldname: 'date_of_joining',
				label: __('Date of Joining'),
				description: __('The intake date — all new hires who started that day'),
				reqd: 1,
				default: frappe.datetime.get_today(),
				// Frappe applies dialog defaults asynchronously (field_group.make()
				// resolves set_values() a tick after show()). include_default makes
				// get_values() fall back to the default meanwhile, so the very first
				// preview call isn't sent with an empty date.
				include_default: 1,
				onchange: function () {
					refresh_preview(dialog);
				},
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
				label: __('Employees in this batch'),
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

	// Never hit the server with incomplete input — it throws on a missing date,
	// which would pop an error dialog just from opening this one.
	const hint = by_employees
		? (values.employees || []).length ? null : __('Select at least one employee.')
		: values.date_of_joining ? null : __('Pick the intake date.');
	if (hint) {
		$('#lc-bulk-preview').html(`<div class="text-muted">${hint}</div>`);
		return;
	}

	frappe.call({
		method: 'customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract.get_probation_contract_candidates',
		args: {
			filter_by: values.filter_by || 'Date of Joining',
			employees: by_employees ? JSON.stringify(values.employees || []) : null,
			date_of_joining: by_employees ? null : values.date_of_joining,
		},
		callback: function (r) {
			render_candidates($('#lc-bulk-preview'), r.message || []);
		},
	});
}

function render_candidates($target, rows) {
	if (!rows.length) {
		$target.html(`<div class="text-muted">${__('No employees joined on this date.')}</div>`);
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
			filter_by: values.filter_by || 'Date of Joining',
			employees: values.filter_by === 'Employees' ? JSON.stringify(values.employees || []) : null,
			date_of_joining: values.filter_by === 'Employees' ? null : values.date_of_joining || null,
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
// Seed Contract History (Administrator only)
// ---------------------------------------------------------------------------

function show_seed_contract_history(list_view) {
	frappe.call({
		method: 'customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract.get_contract_seeding_summary',
		freeze: true,
		freeze_message: __('Analysing employees...'),
		callback: function (r) {
			if (r.exc || !r.message) {
				return;
			}
			render_seeding_dialog(r.message, list_view);
		},
	});
}

function render_seeding_dialog(summary, list_view) {
	const stages = summary.by_current_stage || {};
	const stage_rows = Object.keys(stages)
		.map(
			(stage) =>
				`<tr><td>${frappe.utils.escape_html(stage)}</td><td>${stages[stage]}</td></tr>`
		)
		.join('');

	const dialog = new frappe.ui.Dialog({
		title: __('Seed Contract History'),
		size: 'large',
		fields: [
			{
				fieldtype: 'HTML',
				fieldname: 'summary',
				options: `
					<div style="padding: 12px; background: var(--bg-yellow, #fff3cd); border-radius: 6px; margin-bottom: 14px;">
						<strong>${__('One-off go-live tool')}</strong><br>
						${__('For every Active employee who has no Labor Contract yet, this rebuilds their whole contract chain starting from their Date of Joining — probation, then 1 year, then 3 years, then Indefinite-term — stopping at the stage they are on today. Past stages are recorded as Signed; the current stage is left for the daily job to carry forward.')}
					</div>

					<table class="table table-bordered" style="font-size: 13px;">
						<tr><td>${__('Employees without any contract')}</td><td><strong>${summary.candidates}</strong></td></tr>
						<tr><td>${__('Will be seeded')}</td><td><strong>${summary.eligible}</strong></td></tr>
						<tr><td>${__('Contracts that will be created')}</td><td><strong>${summary.total_contracts}</strong></td></tr>
						<tr><td>${__('Skipped — no probation period (0), create manually')}</td><td>${summary.no_probation_period || 0}</td></tr>
						<tr><td>${__('Skipped — no Probation Days set')}</td><td>${summary.missing_probation_days}</td></tr>
						<tr><td>${__('Skipped — no Date of Joining')}</td><td>${summary.missing_date_of_joining}</td></tr>
					</table>

					${stage_rows
						? `<div class="mt-3"><strong>${__('Resulting current stage')}:</strong>
							<table class="table table-bordered table-sm mt-2" style="font-size: 13px;">
								<thead><tr><th>${__('Contract Type')}</th><th>${__('Employees')}</th></tr></thead>
								<tbody>${stage_rows}</tbody>
							</table>
						   </div>`
						: ''}
				`,
			},
		],
		primary_action_label: __('Seed Now'),
		primary_action: function () {
			if (!summary.eligible) {
				frappe.msgprint(__('Nothing to seed.'));
				return;
			}
			frappe.confirm(
				__('This will create {0} Labor Contracts for {1} employees. Continue?', [
					summary.total_contracts,
					summary.eligible,
				]),
				function () {
					run_seed_contract_history(dialog, list_view);
				}
			);
		},
	});

	dialog.show();
}

function run_seed_contract_history(dialog, list_view) {
	frappe.call({
		method: 'customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract.seed_all_contract_history',
		freeze: true,
		freeze_message: __('Queueing...'),
		callback: function (r) {
			if (r.exc || !r.message) {
				return;
			}
			dialog.hide();

			if (!r.message.queued) {
				frappe.msgprint(__('Nothing to seed.'));
				return;
			}

			frappe.show_alert({
				message: __('Seeding {0} employees in the background...', [r.message.total]),
				indicator: 'blue',
			}, 10);

			frappe.realtime.off('labor_contract_seeding_complete');
			frappe.realtime.on('labor_contract_seeding_complete', function (result) {
				show_seeding_result(result);
				list_view.refresh();
			});
		},
	});
}

function show_seeding_result(result) {
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
		title: __('Seeding Completed'),
		indicator: result.employees_seeded > 0 ? 'green' : 'orange',
		message: `
			<div>${__('Employees seeded')}: <strong>${result.employees_seeded}</strong></div>
			<div>${__('Contracts created')}: <strong>${result.contracts_created}</strong></div>
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
		$('#lc-expiring-list').html(`<div class="text-muted">${__('Pick both dates.')}</div>`);
		return;
	}
	if (values.from_date > values.to_date) {
		$('#lc-expiring-list').html(
			`<div class="text-danger">${__('From Date cannot be after To Date')}</div>`
		);
		return;
	}

	frappe.call({
		method: 'customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract.get_expiring_contracts',
		args: { from_date: values.from_date, to_date: values.to_date },
		callback: function (r) {
			render_expiring($('#lc-expiring-list'), r.message || [], dialog);
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
		frappe.confirm(
			__('Mark {0} selected contract(s) as Signed?', [names.length]),
			() => run_mark_as_signed(names, null, list_view)
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
				description: __('Nothing was ticked in the list, so pick the contracts here. Marking a contract Signed also updates that employee\'s Employment Type to the contract type currently in effect.'),
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
		primary_action: function () {
			const names = get_picked_contracts();
			if (!names.length) {
				frappe.msgprint(__('Please select at least one contract'));
				return;
			}
			frappe.confirm(
				__('Mark {0} contract(s) as Signed?', [names.length]),
				() => run_mark_as_signed(names, dialog, list_view)
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
			render_sign_picker($('#lc-sign-picker'), r.message || []);
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
				<td>${frappe.utils.escape_html(row.contract_type || '')}</td>
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

function get_picked_contracts() {
	return $('#lc-sign-picker .lc-sign-check:checked')
		.map(function () {
			return $(this).data('name');
		})
		.get();
}

function run_mark_as_signed(names, dialog, list_view) {
	frappe.call({
		method: 'customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract.bulk_mark_signed',
		args: { contracts: JSON.stringify(names) },
		freeze: true,
		freeze_message: __('Marking as Signed...'),
		callback: function (r) {
			if (r.exc || !r.message) {
				return;
			}
			if (dialog) {
				dialog.hide();
			}
			frappe.msgprint({
				title: __('Done'),
				indicator: r.message.signed > 0 ? 'green' : 'orange',
				message: `<div>${__('Marked as Signed')}: <strong>${r.message.signed}</strong></div>
				          <div>${__('Skipped')}: <strong>${r.message.skipped}</strong></div>
				          <div class="text-muted" style="margin-top:6px;">${__('Employment Type updated on the matching employees.')}</div>`,
			});
			list_view.refresh();
		},
	});
}
