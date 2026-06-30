// Uniform Control — Dashboard (Desk Page)
// Route: /app/uniform-dashboard
// Uses Frappe-native building blocks (frappe.DataTable, frappe.Chart) — only the
// summary cards are light custom HTML. Data comes from uniform_api / uniform_excel_api.

frappe.pages['uniform-dashboard'].on_page_load = function (wrapper) {
	const API = 'customize_erpnext.uniform_control.api';

	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Uniform Dashboard'),
		single_column: true,
	});

	page.set_primary_action(__('New Allocation'), () => frappe.new_doc('Uniform Allocation'), 'add');
	page.add_inner_button(__('Receive Stock'), () => {
		frappe.route_options = { stock_entry_type: 'Material Receipt' };
		frappe.new_doc('Stock Entry');
	});
	page.add_inner_button(__('Allocation History'), () => frappe.set_route('List', 'Uniform Allocation'));
	page.add_inner_button(__('Uniform Tracking'), () => frappe.set_route('query-report', 'Uniform Tracking'));
	page.add_inner_button(__('Demand Forecast'), () => frappe.set_route('List', 'Uniform Demand Forecast'));
	page.add_inner_button(__('Uniform Profiles'), () => frappe.set_route('List', 'Employee Uniform Profile'));
	page.add_inner_button(__('Shoe Rack Dashboard'), () => frappe.set_route('shoe-rack-dashboard'));
	page.add_inner_button(__('Export Excel'), () => {
		const due_before = $body.find('[data-due-before]').val() || '';
		const params = new URLSearchParams({ due_before });
		if (selected_forecasts.length) params.set('forecasts', JSON.stringify(selected_forecasts));
		window.open('/api/method/customize_erpnext.uniform_control.api.uniform_api.export_dashboard_excel?' + params.toString());
	});
	page.add_inner_button(__('Refresh'), () => load());

	const $body = $(`
		<div class="uniform-dashboard" style="padding: 0 var(--padding-md);">
			<div class="row" data-section="cards" style="margin-bottom: 15px;"></div>

			<!-- HERO: stock purchasing plan -->
			<div class="row"><div class="col-12">
				<div class="frappe-card" style="padding:15px; margin-bottom:15px;">
					<div class="d-flex justify-content-between align-items-center flex-wrap" style="gap:10px; margin-bottom:10px;">
						<h6 style="margin:0;">${__('Stock Plan')}
							<span class="text-muted" data-count="plan"></span></h6>
						<div class="d-flex align-items-center flex-wrap" style="gap:10px;">
							<span class="text-muted" style="font-size:var(--text-sm); white-space:nowrap;">${__('Reissue due on/before')}</span>
							<input type="date" class="form-control input-sm" data-due-before style="max-width:150px;">
							<button class="btn btn-xs btn-default" data-include-forecast>${__('Include Forecast Demand')}…</button>
						</div>
					</div>
					<div class="text-muted" data-forecast-note style="font-size:var(--text-sm); margin-bottom:6px;"></div>
					<div data-table="plan"></div>
				</div>
			</div></div>

			<!-- Collapsed: employees due for issue -->
			<div class="row"><div class="col-12">
				<div class="frappe-card" style="padding:15px; margin-bottom:15px;">
					<details data-section="due">
						<summary style="cursor:pointer; user-select:none;">
							<h6 style="display:inline; margin:0;">${__('Employees Due for Issue')}</h6>
							<span class="text-muted" data-count="due"></span>
						</summary>
						<div class="d-flex justify-content-end align-items-center" style="gap:12px; margin:8px 0;">
							<a href="#" data-open-tracking style="font-size:var(--text-sm); white-space:nowrap;">${__('Open in Uniform Tracking')} →</a>
						</div>
						<div data-table="due"></div>
					</details>
				</div>
			</div></div>

			<!-- Charts -->
			<div class="row">
				<div class="col-md-6"><div class="frappe-card" style="padding:15px; margin-bottom:15px;">
					<h6>${__('Issued Qty by Month')}</h6><div data-chart="month"></div>
				</div></div>
				<div class="col-md-6"><div class="frappe-card" style="padding:15px; margin-bottom:15px;">
					<h6>${__('Issued Qty by Group')}</h6><div data-chart="group"></div>
				</div></div>
			</div>
		</div>
	`).appendTo(page.main);

	const esc = frappe.utils.escape_html;

	// ── DataTables (Frappe native) ───────────────────────────────────────────
	const STATUS_COLOR = { Overdue: 'red', 'Due Soon': 'orange', Active: 'green', 'Not Issued': 'gray' };

	const plan_columns = [
		{ name: __('Uniform Type'), width: 150, editable: false },
		{ name: __('Item'), width: 200,
			format: (v) => `<a href="/app/item/${encodeURIComponent(v)}">${esc(v)}</a>` },
		{ name: __('Stock'), width: 90, align: 'right' },
		{ name: __('Reissue Need'), width: 120, align: 'right' },
		{ name: __('Forecast Need'), width: 120, align: 'right' },
		{ name: __('Total Need'), width: 100, align: 'right', format: (v) => `<b>${v || 0}</b>` },
		{ name: __('Shortfall'), width: 100, align: 'right',
			format: (v) => (flt(v) > 0 ? `<b style="color:var(--red-600)">${v}</b>` : '') },
	];

	const due_columns = [
		{ name: __('Employee'), width: 100,
			format: (v) => `<a href="/app/employee-uniform-profile/${encodeURIComponent(v)}">${esc(v)}</a>` },
		{ name: __('Employee Name'), width: 160 },
		{ name: __('Department'), width: 130 },
		{ name: __('Group'), width: 100 },
		{ name: __('Uniform Type'), width: 130 },
		{ name: __('Size'), width: 60 },
		{ name: __('Qty/Cycle'), width: 80, align: 'right' },
		{ name: __('Cycles'), width: 70, align: 'right' },
		{ name: __('Total Qty'), width: 80, align: 'right' },
		{ name: __('Next Due Date'), width: 110, format: (v) => frappe.datetime.str_to_user(v) || '' },
		{ name: __('Status'), width: 90,
			format: (v) => `<span class="indicator-pill ${STATUS_COLOR[v] || 'gray'}">${__(v)}</span>` },
	];

	// Columns are read-only (no inline editing) on this dashboard.
	const PLAN_COLS = plan_columns.map((c) => ({ editable: false, ...c }));
	const DUE_COLS = due_columns.map((c) => ({ editable: false, ...c }));

	function make_dt(el, columns) {
		return new frappe.DataTable(el, {
			columns, data: [],
			layout: 'fluid',
			inlineFilters: true,
			serialNoColumn: false,
			checkboxColumn: false,
			cellHeight: 34,
			noDataMessage: __('No data'),
		});
	}

	// ── Stock purchasing plan ────────────────────────────────────────────────
	let stock_rows = [];
	let needed_map = {};          // reissue demand (multi-cycle, from due items)
	let forecast_needed = {};     // optional new-hire demand (selected forecasts)
	let selected_forecasts = [];  // names of the included forecasts (for export)
	let plan_dt = null;

	function build_plan() {
		const data = stock_rows.map((x) => {
			const reissue = flt(needed_map[x.item_code]);
			const forecast = flt(forecast_needed[x.item_code]);
			const total = reissue + forecast;
			return [
				x.template || x.item_code, x.item_code, flt(x.actual_qty),
				reissue, forecast, total, total - flt(x.actual_qty),
			];
		});
		$body.find('[data-count="plan"]').text(data.length ? `(${data.length})` : '');
		if (!plan_dt) plan_dt = make_dt($body.find('[data-table="plan"]')[0], PLAN_COLS);
		plan_dt.refresh(data, PLAN_COLS);
	}

	// ── Employees due (lazy — built when the <details> is first opened, since a
	// DataTable needs a visible container to size itself) ──────────────────────
	let due_dt = null;
	let due_data = [];

	function render_due(rows) {
		$body.find('[data-count="due"]').text(rows.length ? `(${rows.length})` : '');
		due_data = rows.map((r) => [
			r.employee, r.employee_name, r.department, r.custom_group, r.item_template,
			r.size, r.qty_per_cycle, r.cycles, r.total_qty, r.next_due_date, r.status,
		]);
		refresh_due_dt();
	}

	function refresh_due_dt() {
		if (!$body.find('details[data-section="due"]').prop('open')) return;
		if (!due_dt) due_dt = make_dt($body.find('[data-table="due"]')[0], DUE_COLS);
		due_dt.refresh(due_data, DUE_COLS);
	}
	$body.find('details[data-section="due"]').on('toggle', refresh_due_dt);

	// ── Handlers ─────────────────────────────────────────────────────────────
	// Drill-down: KPI cards → Uniform Tracking report (pre-filtered).
	$body.on('click', '[data-route]', function () {
		frappe.route_options = JSON.parse($(this).attr('data-route'));
		frappe.set_route('query-report', 'Uniform Tracking');
	});

	$body.find('[data-open-tracking]').on('click', function (e) {
		e.preventDefault();
		frappe.set_route('query-report', 'Uniform Tracking');
	});

	// Reissue horizon filter: default = today (only items due now). Choosing a
	// forecast below sets this to that demand's To Date.
	$body.find('[data-due-before]')
		.val(frappe.datetime.get_today())
		.on('change', () => load_due());

	// Include selected Uniform Demand Forecast(s) into the plan's Forecast Need.
	$body.find('[data-include-forecast]').on('click', () => {
		const dialog = new frappe.ui.Dialog({
			title: __('Include Forecast Demand'),
			fields: [{
				fieldname: 'forecasts',
				fieldtype: 'MultiSelectList',
				label: __('Uniform Demand Forecast'),
				get_data: (txt) => frappe.db.get_link_options('Uniform Demand Forecast', txt),
			}],
			primary_action_label: __('Apply'),
			primary_action(values) {
				dialog.hide();
				const names = values.forecasts || [];
				selected_forecasts = names;
				const note = $body.find('[data-forecast-note]');
				if (!names.length) {
					// Cleared → back to today's reissue demand only
					forecast_needed = {};
					note.text('');
					$body.find('[data-due-before]').val(frappe.datetime.get_today());
					load_due();
					return;
				}
				frappe.call({
					method: `${API}.uniform_api.get_forecast_needed`,
					args: { forecasts: names },
				}).then((r) => {
					const msg = r.message || {};
					forecast_needed = msg.needed || {};
					// Take the forecast's quantities AND its due date (To Date) as horizon
					if (msg.to_date) $body.find('[data-due-before]').val(msg.to_date);
					note.text(`+ ${__('Forecast')}: ${names.join(', ')}`
						+ (msg.to_date ? ` — ${__('due')} ${frappe.datetime.str_to_user(msg.to_date)}` : ''));
					load_due();   // recompute reissue up to the forecast's To Date, then build_plan
				});
			},
		});
		dialog.show();
	});

	// ── Cards & charts ───────────────────────────────────────────────────────
	function card(label, value, color, route) {
		const attrs = route
			? ` data-route='${esc(JSON.stringify(route))}' style="padding:12px 15px; cursor:pointer;"`
			: ' style="padding:12px 15px;"';
		const hint = route
			? `<div class="text-muted" style="font-size:var(--text-xs);">${__('View in Uniform Tracking')} →</div>`
			: '';
		return `
			<div class="col" style="min-width:150px;">
				<div class="frappe-card"${attrs}>
					<div class="text-muted" style="font-size:var(--text-sm);">${label}</div>
					<div style="font-size:24px; font-weight:600; color:${color || 'var(--text-color)'};">${value}</div>
					${hint}
				</div>
			</div>`;
	}

	function render_cards(s) {
		$body.find('[data-section="cards"]').html(
			card(__('Variants in Stock'), s.total_variants_in_stock) +
			card(__('Low Stock'), s.low_stock_variants, s.low_stock_variants ? 'var(--red-500)' : 'var(--green-500)') +
			card(__('Due Soon'), s.employees_due_soon, s.employees_due_soon ? 'var(--orange-500)' : undefined, { status: 'Due Soon' }) +
			card(__('Overdue'), s.employees_overdue, s.employees_overdue ? 'var(--red-500)' : undefined, { status: 'Overdue' }) +
			card(__('Allocations (30 days)'), s.allocations_last_30_days)
		);
		if (!s.warehouse) {
			$body.find('[data-section="cards"]').prepend(
				`<div class="col-12"><div class="alert alert-warning">${__('Uniform Warehouse is not configured in Uniform Setting.')}</div></div>`
			);
		}
	}

	function render_chart(selector, rows, label_key) {
		const $el = $body.find(`[data-chart="${selector}"]`).empty();
		if (!rows.length) return $el.html(`<p class="text-muted">${__('No data')}</p>`);
		new frappe.Chart($el[0], {
			data: {
				labels: rows.map((r) => r[label_key] || '—'),
				datasets: [{ values: rows.map((r) => flt(r.total_qty)) }],
			},
			type: 'bar',
			height: 220,
			colors: ['#7cd6fd'],
		});
	}

	// ── Data loading ─────────────────────────────────────────────────────────
	function load_due() {
		const due_before = $body.find('[data-due-before]').val() || null;
		return frappe.call({
			method: `${API}.uniform_api.get_due_items`,
			args: { limit: 100000, due_before },
		}).then((r) => {
			const msg = r.message || {};
			needed_map = msg.needed || {};
			render_due(msg.rows || []);
			build_plan();   // refresh the Reissue Need column
		});
	}

	function load() {
		frappe.call({ method: `${API}.uniform_api.get_dashboard_summary` })
			.then((r) => render_cards(r.message || {}));

		load_due();

		frappe.call({ method: `${API}.uniform_excel_api.get_uniform_stock_excel` })
			.then((r) => {
				stock_rows = r.message || [];
				build_plan();
			});

		frappe.call({ method: `${API}.uniform_excel_api.get_uniform_cost_excel`, args: { group_by: 'period' } })
			.then((r) => {
				const rows = (r.message || []).sort((a, b) => (a.period > b.period ? 1 : -1));
				render_chart('month', rows, 'period');
			});

		frappe.call({ method: `${API}.uniform_excel_api.get_uniform_cost_excel`, args: { group_by: 'group' } })
			.then((r) => render_chart('group', r.message || [], 'custom_group'));
	}

	load();
};
