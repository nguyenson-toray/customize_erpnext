// Uniform Demand Forecast — estimate uniform demand for new hires and/or reissue.
frappe.ui.form.on('Uniform Demand Forecast', {
	onload(frm) {
		if (frm.is_new() && !frm.doc.to_date) {
			frm.set_value('to_date', frappe.datetime.add_days(frappe.datetime.get_today(), 365));
		}
	},
	refresh(frm) {
		render_shirt_breakdown(frm);
		render_current_ratio(frm);
		frm.add_custom_button(__('Help'), () => show_forecast_help());
		if (frm.is_new()) return;
		frm.add_custom_button(__('Download Excel'), () => {
			window.open('/api/method/customize_erpnext.uniform_control.api.forecast.export_forecast_excel?forecast='
				+ encodeURIComponent(frm.doc.name));
		});
		frm.add_custom_button(__('Forecast'), () => {
			frappe.dom.freeze(__('Computing demand...'));
			frappe.call({
				method: 'customize_erpnext.uniform_control.api.forecast.compute',
				args: { forecast: frm.doc.name },
				callback(r) {
					frappe.dom.unfreeze();
					frm.reload_doc();
					const m = r.message || {};
					frappe.show_alert({
						message: __('Forecast: {0} items, shortfall {1}', [m.total_forecast || 0, m.total_shortfall || 0]),
						indicator: 'green',
					});
					// Warn about designations with no current staff to infer from
					if ((m.unmapped || []).length) {
						const lines = m.unmapped
							.map((u) => `• ${u.designation} (${u.headcount})`)
							.join('<br>');
						frappe.msgprint({
							title: __('Not forecast — add manually'),
							indicator: 'orange',
							message: __('These designations have no current employees to infer from, so no demand was generated. Add their items manually:') + '<br>' + lines,
						});
					}
				},
				error: () => frappe.dom.unfreeze(),
			});
		}).addClass('btn-primary');
	},
});

// Forecast breakdown by shirt type (Áo sơ mi / Áo thun) × gender × size.
function render_shirt_breakdown(frm) {
	const field = frm.fields_dict.shirt_breakdown_html;
	if (!field) return;
	const shirts = (frm.doc.items || []).filter((r) => r.category === 'Shirt');
	field.$wrapper.html(shirts.length ? shirt_tables_html(shirts) : '');
}

// Current employees' shirt distribution — the ratio used to spread the forecast.
function render_current_ratio(frm) {
	const field = frm.fields_dict.current_ratio_html;
	if (!field) return;
	if (frm.is_new()) {
		field.$wrapper.html('');
		return;
	}
	frappe.call({
		method: 'customize_erpnext.uniform_control.api.forecast.current_shirt_ratio',
		args: { forecast: frm.doc.name },
		callback(r) {
			const msg = r.message || {};
			const rows = (msg.rows || []).map((x) => ({
				item_code: x.template, template: x.template, size: x.size, forecast_qty: x.qty,
			}));
			if (!rows.length) {
				field.$wrapper.html(`<span class="text-muted">${__('No current employee data.')}</span>`);
				return;
			}
			const caption = `<div class="text-muted" style="margin-bottom:6px;">${__('As of {0}', [frappe.datetime.str_to_user(msg.as_of) || msg.as_of])}</div>`;
			field.$wrapper.html(caption + shirt_tables_html(rows));
		},
	});
}

// Group rows by shirt type and render one gender × size table per type.
function shirt_tables_html(rows) {
	const types = {}; // type label -> [rows]
	rows.forEach((r) => {
		const txt = (r.item_code || r.template || '').toLowerCase();
		const type = txt.indexOf('sơ mi') !== -1 ? __('Dress shirt (Áo sơ mi)')
			: txt.indexOf('thun') !== -1 ? __('T-shirt (Áo thun)')
			: __('Shirt');
		(types[type] = types[type] || []).push(r);
	});
	// Two columns side by side: Áo thun | Áo sơ mi (wrap on narrow screens).
	const cols = Object.keys(types).sort()
		.map((label) => `<div style="flex:1 1 240px; min-width:240px;">${shirt_type_table(label, types[label])}</div>`)
		.join('');
	return `<div style="display:flex; gap:16px; flex-wrap:wrap;">${cols}</div>`;
}

// One gender × size table for a single shirt type.
function shirt_type_table(label, rows) {
	const sizes = [];
	const grid = {}; // size -> {male, female, total}
	let tMale = 0, tFemale = 0, tAll = 0;
	rows.forEach((r) => {
		const txt = (r.item_code || r.template || '').toLowerCase();
		const female = txt.indexOf('nữ') !== -1;
		const male = !female && txt.indexOf('nam') !== -1;
		const size = r.size || '—';
		const qty = r.forecast_qty || 0;
		if (!(size in grid)) { grid[size] = { male: 0, female: 0, total: 0 }; sizes.push(size); }
		if (female) { grid[size].female += qty; tFemale += qty; }
		else if (male) { grid[size].male += qty; tMale += qty; }
		grid[size].total += qty;
		tAll += qty;
	});
	sizes.sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' }));

	const pct = (n) => (tAll ? Math.round((n / tAll) * 1000) / 10 : 0);
	const cell = (n) => (n ? `${n} <span class="text-muted">(${pct(n)}%)</span>` : '0');

	let body = '';
	sizes.forEach((s) => {
		const g = grid[s];
		body += `<tr>
			<td>${frappe.utils.escape_html(s)}</td>
			<td class="text-right">${cell(g.male)}</td>
			<td class="text-right">${cell(g.female)}</td>
			<td class="text-right"><b>${cell(g.total)}</b></td>
		</tr>`;
	});

	return `
		<div class="text-muted" style="margin-bottom:4px;">
			<b>${frappe.utils.escape_html(label)}</b>: ${tAll} &nbsp;—&nbsp;
			${__('Male')} ${tMale} (${pct(tMale)}%) / ${__('Female')} ${tFemale} (${pct(tFemale)}%)
		</div>
		<table class="table table-sm table-bordered" style="margin-bottom:0;">
			<thead><tr>
				<th>${__('Size')}</th>
				<th class="text-right">${__('Male')}</th>
				<th class="text-right">${__('Female')}</th>
				<th class="text-right">${__('Total')}</th>
			</tr></thead>
			<tbody>${body}</tbody>
			<tfoot><tr style="font-weight:600;">
				<td>${__('Total')}</td>
				<td class="text-right">${cell(tMale)}</td>
				<td class="text-right">${cell(tFemale)}</td>
				<td class="text-right">${tAll}</td>
			</tr></tfoot>
		</table>`;
}

// Explanation dialog for HR.
function show_forecast_help() {
	frappe.msgprint({
		title: __('Uniform Demand Forecast — Guide'),
		indicator: 'blue',
		message: `
			<div style="line-height:1.6;">
				<p><b>${__('Purpose')}:</b> ${__('Estimate uniform demand so stock can be prepared in advance. Modes: New Hires (recruitment plan), Re-issue (current staff, every cycle up to To Date), Both.')}</p>
				<p><b>${__('Steps')}:</b></p>
				<ol style="padding-left:18px;">
					<li>${__('Choose Mode; for New Hires fill the Recruitment Plan (designation + headcount); for Re-issue set To Date. Save.')}</li>
					<li>${__('Click "Forecast".')}</li>
					<li>${__('Review / edit the Forecast Qty column, then Save. Use it to plan stock purchases.')}</li>
				</ol>
				<p><b>${__('How it is calculated')}:</b> ${__('For each designation, the planned headcount is spread across the grade / gender / group / section mix of current employees in that designation (a brand-new "…-Trainee" falls back to its base designation). Uniform Rules then give the items and first-issue quantity; shirt quantities are split into sizes using the size distribution of current staff.')}</p>
				<p><b>${__('Current Shirt Ratio')}:</b> ${__('The reference distribution that drives the split — always covers both Áo sơ mi & Áo thun, computed company-wide as of the forecast creation date.')}</p>
				<p><b>${__('Download Excel')}:</b> ${__('Exports two sheets — Forecast and Current Ratio.')}</p>
			</div>`,
	});
}
