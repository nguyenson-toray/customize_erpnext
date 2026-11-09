// Uniform Control — Dashboard (Desk Page)
// Route: /app/uniform-dashboard
// Uses Frappe-native building blocks (frappe.DataTable, frappe.Chart) — only the
// summary cards are light custom HTML. Data comes from uniform_api / uniform_excel_api.

frappe.pages['uniform-dashboard'].on_page_load = function (wrapper) {
	const API = 'customize_erpnext.uniform_control.api';

	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Uniform Dashboard: Re-Issue and Stock Plan'),
		single_column: true,
	});

	// Main action: a Uniform Allocation already filled with everyone due up to
	// the dashboard's "Reissue due on/before" date (+ new employees' first issue)
	page.set_primary_action(__('Create Allocation for Due'), () => {
		frappe.flags.uniform_auto_get = true;
		frappe.new_doc('Uniform Allocation', { due_before: due_before_ctl.get_value() || frappe.datetime.get_today() });
	}, 'add');
	page.add_inner_button(__('Receive Stock'), () => receive_stock_dialog());
	page.add_inner_button(__('Assignment Preview'), () => frappe.set_route('query-report', 'Uniform Assignment Preview'));
	page.add_inner_button(__('Shoe Rack Dashboard'), () => frappe.set_route('shoe-rack-dashboard'));
	page.add_inner_button(__('Export Excel'), () => {
		const due_before = due_before_ctl.get_value() || '';
		const params = new URLSearchParams({ due_before });
		window.open('/api/method/customize_erpnext.uniform_control.api.uniform_api.export_dashboard_excel?' + params.toString());
	});
	page.add_inner_button(__('Refresh'), () => load());

	const $body = $(`
		<div class="uniform-dashboard" style="padding: 0 var(--padding-md);">
			<div class="row" data-section="warnings"></div>
			<div class="row" data-section="cards" style="margin-bottom: 15px;"></div>

			<!-- Global filter bar — drives BOTH tables below (Stock Plan's Reissue
			     Need column and the Employees Due for Issue list). Kept OUTSIDE the
			     Stock Plan card so it doesn't read as a Stock-Plan-only filter. -->
			<div class="row"><div class="col-12">
				<div class="frappe-card" style="padding:10px 15px; margin-bottom:15px;">
					<div class="d-flex align-items-center flex-wrap" style="gap:10px;">
						<span style="font-size:var(--text-sm); font-weight:600; white-space:nowrap;">${__('Reissue due on/before')}</span>
						<div data-due-before style="width:150px;"></div>
						<span class="text-muted" style="font-size:var(--text-sm);">${__('This date filter drives both tables below. Attrition only affects the Est. for Leavers column in Stock Plan table.')}</span>
						<span data-attrition-note style="font-size:var(--text-sm); color:var(--orange-600);"></span>
					</div>
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

			<!-- HERO: stock purchasing plan (collapsible, open by default) -->
			<div class="row"><div class="col-12">
				<div class="frappe-card" style="padding:15px; margin-bottom:15px;">
					<details data-section="plan" open>
						<summary style="cursor:pointer; user-select:none;">
							<h6 style="display:inline; margin:0;">${__('Stock Plan')}
								<span class="text-muted" data-count="plan"></span></h6>
						</summary>
						<div data-table="plan" style="margin-top:10px;"></div>
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

	// Fixed plan columns: Reissue Need = gross tracking demand; Est. for Leavers
	// = NEGATIVE informational slice (red); Total = the two combined;
	// Shortfall = Total − Stock.
	const PLAN_COLS = [
		{ name: __('Uniform Type'), width: 150 },
		{
			name: __('Item'), width: 200,
			format: (v) => `<a href="/app/item/${encodeURIComponent(v)}">${esc(v)}</a>`
		},
		{ name: __('Stock'), width: 90, align: 'right' },
		{ name: __('Reissue Need'), width: 120, align: 'right' },
		{
			name: __('Est. for Leavers'), width: 130, align: 'right',
			format: (v) => (flt(v) < 0 ? `<span style="color:var(--red-600)">${v}</span>` : '0'),
		},
		{ name: __('Total'), width: 100, align: 'right', format: (v) => `<b>${v || 0}</b>` },
		{
			name: __('Shortfall'), width: 100, align: 'right',
			format: (v) => (flt(v) > 0 ? `<b style="color:var(--red-600)">${v}</b>` : '')
		},
	].map((c) => ({ editable: false, ...c }));

	const due_columns = [
		{
			name: __('Employee'), width: 100,
			format: (v) => `<a href="/app/employee/${encodeURIComponent(v)}">${esc(v)}</a>`
		},
		{
			// Profile name = employee id (autoname field:employee)
			name: __('Profile'), width: 80,
			format: (v) => (v ? `<a href="/app/employee-uniform-profile/${encodeURIComponent(v)}">${__('Open')} →</a>` : '')
		},
		{ name: __('Employee Name'), width: 160 },
		{ name: __('Section'), width: 120 },
		{ name: __('Group'), width: 100 },
		{ name: __('Uniform Type'), width: 130 },
		{ name: __('Size'), width: 60 },
		{ name: __('Qty/Cycle'), width: 80, align: 'right' },
		{ name: __('Cycles'), width: 70, align: 'right' },
		{ name: __('Total Qty'), width: 80, align: 'right' },
		{ name: __('Next Due Date'), width: 110, format: (v) => frappe.datetime.str_to_user(v) || '' },
		{
			name: __('Status'), width: 90,
			format: (v) => `<span class="indicator-pill ${STATUS_COLOR[v] || 'gray'}">${__(v)}</span>`
		},
	];

	// Columns are read-only (no inline editing) on this dashboard.
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

	// ── Stock purchasing plan (re-issue demand only) ─────────────────────────
	let stock_rows = [];
	let needed_gross = {};   // reissue demand (multi-cycle, from due items)
	let est_map = {};        // measured Est. for Leavers per variant (positive)
	let attrition_info = {}; // {enabled, months, persons, monthly_total, period_months}
	let plan_dt = null;
	let plan_data = [];

	function build_plan() {
		plan_data = stock_rows.map((x) => {
			const gross = flt(needed_gross[x.item_code]);
			const leavers = -flt(est_map[x.item_code]);   // ≤ 0
			const total = gross + leavers;
			const stock = flt(x.actual_qty);
			return [x.template || x.item_code, x.item_code, stock, gross, leavers, total, total - stock];
		});
		$body.find('[data-count="plan"]').text(plan_data.length ? `(${plan_data.length})` : '');
		refresh_plan_dt();
	}

	function render_attrition_note() {
		$body.find('[data-attrition-note]').text(
			attrition_info.enabled
				? __('Est. for Leavers (negative) is MEASURED: last {0} months, {1} leavers missed re-issues (avg {2}/month) × {3} month(s) of this horizon, rounded up. Total = Reissue Need + Est.; Shortfall = Total − Stock. The Employees Due list is never adjusted.',
					[attrition_info.months || 0, attrition_info.persons || 0,
					attrition_info.monthly_total || 0, attrition_info.period_months || 0])
				: __('Deduct Attrition is OFF in Uniform Setting — Est. for Leavers is 0 and Total equals Reissue Need.')
		);
	}

	// DataTable needs a visible container — rebuild when the <details> reopens.
	function refresh_plan_dt() {
		if (!$body.find('details[data-section="plan"]').prop('open')) return;
		if (!plan_dt) plan_dt = make_dt($body.find('[data-table="plan"]')[0], PLAN_COLS);
		plan_dt.refresh(plan_data, PLAN_COLS);
	}
	$body.find('details[data-section="plan"]').on('toggle', refresh_plan_dt);

	// ── Employees due (lazy — built when the <details> is first opened, since a
	// DataTable needs a visible container to size itself) ──────────────────────
	let due_dt = null;
	let due_data = [];

	function render_due(rows) {
		$body.find('[data-count="due"]').text(rows.length ? `(${rows.length})` : '');
		due_data = rows.map((r) => [
			r.employee, r.employee, r.employee_name, r.custom_section, r.custom_group, r.item_template,
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

	// Reissue horizon filter — native Frappe Date control (respects the user's
	// date format). Default = today (only items due now).
	const due_before_ctl = frappe.ui.form.make_control({
		parent: $body.find('[data-due-before]')[0],
		df: { fieldtype: 'Date', fieldname: 'due_before', placeholder: __('Today') },
		render_input: true,
	});
	due_before_ctl.set_value(frappe.datetime.get_today());
	due_before_ctl.$input.on('change', () => load_due());


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
			card(__('Low Stock'), s.low_stock_variants, s.low_stock_variants ? 'var(--red-500)' : 'var(--green-500)') +
			card(__('Due Soon'), s.employees_due_soon, s.employees_due_soon ? 'var(--orange-500)' : undefined, { status: 'Due Soon' }) +
			card(__('Overdue'), s.employees_overdue, s.employees_overdue ? 'var(--red-500)' : undefined, { status: 'Overdue' })
		);
		render_warnings(s);
	}

	// Data that blocks or changes an allocation, each with a way to fix it
	function render_warnings(s) {
		const notes = [];
		if (!s.warehouse) notes.push(`<span>${__('Uniform Warehouse is not configured in Uniform Setting.')}</span>`);
		if (s.missing_profiles) {
			notes.push(`<span>${__('{0} employee(s) have no uniform profile yet.', [s.missing_profiles])}
				<a href="#" data-action="create-profiles">${__('Create Profiles')}</a></span>`);
		}
		if (s.missing_shirt_size) {
			notes.push(`<span>${__('{0} employee(s) have no shirt size — their shirts are skipped.', [s.missing_shirt_size])}
				<a href="#" data-action="no-shirt-size">${__('Open Employees')}</a></span>`);
		}
		if (s.missing_shoe_size) {
			notes.push(`<span class="text-muted">${__('{0} employee(s) have no shoe size — they get Free Size.', [s.missing_shoe_size])}</span>`);
		}
		$body.find('[data-section="warnings"]').html(notes.length
			? `<div class="col-12"><div class="frappe-card" style="padding:10px 15px; margin-bottom:15px; border-left:3px solid var(--orange-500);">
				${notes.map((n) => `<div style="font-size:var(--text-sm); margin:2px 0;">${n}</div>`).join('')}</div></div>`
			: '');
		summary_prefix = s.prefix || '';
	}
	let summary_prefix = '';

	$body.on('click', '[data-action="create-profiles"]', (e) => {
		e.preventDefault();
		frappe.call({
			method: `${API}.uniform_api.create_missing_profiles`,
			freeze: true,
			freeze_message: __('Creating profiles...'),
		}).then((r) => {
			frappe.show_alert({ message: __('Created {0} profile(s).', [(r.message || {}).created || 0]), indicator: 'green' });
			load();
		});
	});
	$body.on('click', '[data-action="no-shirt-size"]', (e) => {
		e.preventDefault();
		const filters = { status: 'Active', custom_shirt_size: ['is', 'not set'] };
		if (summary_prefix) filters.name = ['like', `${summary_prefix}%`];
		frappe.set_route('List', 'Employee', filters);
	});

	// HR receives uniform stock here (Material Receipt created by the server —
	// no Stock Entry permission needed)
	function receive_stock_dialog() {
		frappe.db.get_single_value('Uniform Setting', 'uniform_item_group').then((group) => {
			const d = new frappe.ui.Dialog({
				title: __('Receive Stock'),
				size: 'large',
				fields: [
					{ fieldname: 'posting_date', fieldtype: 'Date', label: __('Date'), default: frappe.datetime.get_today(), reqd: 1 },
					{
						fieldname: 'items', fieldtype: 'Table', label: __('Items'), reqd: 1, in_place_edit: true,
						data: [], cannot_add_rows: false,
						fields: [
							{
								fieldname: 'item_code', fieldtype: 'Link', options: 'Item', label: __('Item (size / colour)'),
								in_list_view: 1, reqd: 1, columns: 5,
								get_query: () => ({ filters: Object.assign({ has_variants: 0, disabled: 0 }, group ? { item_group: group } : {}) }),
							},
							{ fieldname: 'qty', fieldtype: 'Int', label: __('Qty'), in_list_view: 1, reqd: 1, columns: 2 },
							{ fieldname: 'rate', fieldtype: 'Currency', label: __('Unit Price'), in_list_view: 1, reqd: 1, columns: 3 },
						],
					},
				],
				primary_action_label: __('Receive'),
				primary_action(values) {
					const items = (values.items || []).filter((r) => r.item_code);
					if (!items.length) return frappe.msgprint(__('Add at least one item.'));
					frappe.call({
						method: `${API}.uniform_api.receive_stock`,
						args: { items, posting_date: values.posting_date },
						freeze: true,
						freeze_message: __('Receiving stock...'),
					}).then((r) => {
						const m = r.message || {};
						d.hide();
						frappe.msgprint({
							title: __('Stock Received'),
							indicator: 'green',
							message: __('{0} pcs received (stock entry {1}).', [m.qty || 0, frappe.utils.escape_html(m.name || '')]),
						});
						load();
					});
				},
			});
			d.show();
		});
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
		// Cleared date = today, matching the field's "Today" placeholder and the
		// Excel export default (the server's own default would be today + 1 year).
		const due_before = due_before_ctl.get_value() || frappe.datetime.get_today();
		return frappe.call({
			method: `${API}.uniform_api.get_due_items`,
			args: { limit: 100000, due_before },
		}).then((r) => {
			const msg = r.message || {};
			needed_gross = msg.needed || {};
			est_map = msg.est_for_leavers || {};   // off → empty → slice 0
			attrition_info = msg.attrition || {};
			render_attrition_note();
			render_due(msg.rows || []);
			build_plan();
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
