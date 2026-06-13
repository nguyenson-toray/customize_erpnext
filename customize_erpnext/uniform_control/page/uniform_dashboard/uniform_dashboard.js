// Uniform Control — Dashboard (Desk Page)
// Route: /app/uniform-dashboard
// All data comes from uniform_api / uniform_excel_api — HR never opens raw stock reports.
// Labels are English wrapped in __() and translated via translations/vi.csv.

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
	page.add_inner_button(__('Uniform Profiles'), () => frappe.set_route('List', 'Employee Uniform Profile'));
	page.add_inner_button(__('Shoe Rack Dashboard'), () => frappe.set_route('shoe-rack-dashboard'));
	page.add_inner_button(__('Export Excel'), () => {
		window.open('/api/method/customize_erpnext.uniform_control.api.uniform_api.export_dashboard_excel');
	});
	page.add_inner_button(__('Refresh'), () => load());

	const $body = $(`
		<div class="uniform-dashboard" style="padding: 0 var(--padding-md);">
			<div class="row" data-section="cards" style="margin-bottom: 15px;"></div>
			<div class="row">
				<div class="col-md-6"><div class="frappe-card" style="padding:15px; margin-bottom:15px;">
					<h6>${__('Issued Qty by Month')}</h6><div data-chart="month"></div>
				</div></div>
				<div class="col-md-6"><div class="frappe-card" style="padding:15px; margin-bottom:15px;">
					<h6>${__('Issued Qty by Department')}</h6><div data-chart="dept"></div>
				</div></div>
			</div>
			<div class="row"><div class="col-12">
				<div class="frappe-card" style="padding:15px; margin-bottom:15px;">
					<details data-section="stock">
						<summary style="cursor:pointer; user-select:none;">
							<h6 style="display:inline; margin:0;">${__('Uniform Stock')}</h6>
							<span class="text-muted" data-count="stock"></span>
						</summary>
						<div class="d-flex justify-content-end" style="margin:8px 0;">
							<input type="text" class="form-control input-sm" data-filter="stock"
								placeholder="${__('Search')}..." style="max-width:240px;">
						</div>
						<div data-table="stock"></div>
					</details>
				</div>
			</div></div>
			<div class="row"><div class="col-12">
				<div class="frappe-card" style="padding:15px; margin-bottom:15px;">
					<div class="d-flex justify-content-between align-items-center" style="margin-bottom:8px;">
						<h6 style="margin:0;">${__('Employees Due for Issue')}
							<span class="text-muted" data-count="due"></span></h6>
						<input type="text" class="form-control input-sm" data-filter="due"
							placeholder="${__('Search')}..." style="max-width:240px;">
					</div>
					<div data-table="due"></div>
				</div>
			</div></div>
		</div>
	`).appendTo(page.main);

	const esc = frappe.utils.escape_html;
	const no_data = `<p class="text-muted">${__('No data')}</p>`;

	// ── Table definitions ────────────────────────────────────────────────────
	const TABLES = {
		due: {
			sort_by: 'employee',
			dir: 1,
			rows: [],
			columns: [
				{ key: 'employee', label: __('Employee'),
					render: (r) => `<a href="/app/employee-uniform-profile/${encodeURIComponent(r.employee)}">${esc(r.employee)}</a>` },
				{ key: 'employee_name', label: __('Employee Name') },
				{ key: 'department', label: __('Department') },
				{ key: 'custom_group', label: __('Group') },
				{ key: 'item_template', label: __('Uniform Type') },
				{ key: 'size', label: __('Size') },
				{ key: 'next_due_date', label: __('Next Due Date'),
					render: (r) => frappe.datetime.str_to_user(r.next_due_date) || '' },
				{ key: 'status', label: __('Status'),
					render: (r) => `<span class="indicator-pill ${r.status === 'Overdue' ? 'red' : 'orange'}">${__(r.status)}</span>` },
			],
		},
		stock: {
			sort_by: 'item_code',
			dir: 1,
			rows: [],
			columns: [
				{ key: 'item_code', label: __('Item'),
					render: (r) => `<a href="/app/item/${encodeURIComponent(r.item_code)}">${esc(r.item_code)}</a>` },
				{ key: 'item_name', label: __('Item Name') },
				{ key: 'actual_qty', label: __('Qty'), numeric: true },
				{ key: 'reorder_level', label: __('Reorder Level'), numeric: true,
					render: (r) => flt(r.reorder_level) || '' },
				{ key: 'stock_value', label: __('Stock Value'), numeric: true,
					render: (r) => format_currency(flt(r.stock_value)) },
			],
			row_style: (r) => (r.low_stock ? 'background: var(--red-50); color: var(--red-600); font-weight:600;' : ''),
		},
	};

	function sort_rows(t) {
		const { sort_by, dir } = t;
		const col = t.columns.find((c) => c.key === sort_by) || {};
		t.rows.sort((a, b) => {
			let va = a[sort_by], vb = b[sort_by];
			if (col.numeric) return (flt(va) - flt(vb)) * dir;
			va = (va === null || va === undefined) ? '' : String(va);
			vb = (vb === null || vb === undefined) ? '' : String(vb);
			return va.localeCompare(vb, undefined, { numeric: true, sensitivity: 'base' }) * dir;
		});
	}

	function render_table(key) {
		const t = TABLES[key];
		const $el = $body.find(`[data-table="${key}"]`);
		$body.find(`[data-count="${key}"]`).text(t.rows.length ? `(${t.rows.length})` : '');
		if (!t.rows.length) return $el.html(no_data);

		sort_rows(t);

		let html = `<div style="max-height:70vh; overflow:auto;">
			<table class="table table-sm" style="margin-bottom:0;"><thead><tr>`;
		t.columns.forEach((c) => {
			const arrow = t.sort_by === c.key ? (t.dir === 1 ? ' ▲' : ' ▼') : '';
			html += `<th data-sort="${c.key}" style="cursor:pointer; position:sticky; top:0;
				background: var(--card-bg); z-index:1; ${c.numeric ? 'text-align:right;' : ''}">${c.label}${arrow}</th>`;
		});
		html += '</tr></thead><tbody>';
		t.rows.forEach((r) => {
			const style = t.row_style ? t.row_style(r) : '';
			html += `<tr style="${style}">`;
			t.columns.forEach((c) => {
				const val = c.render ? c.render(r) : esc(r[c.key] === null || r[c.key] === undefined ? '' : String(r[c.key]));
				html += `<td ${c.numeric ? 'class="text-right"' : ''}>${val}</td>`;
			});
			html += '</tr>';
		});
		$el.html(html + '</tbody></table></div>');
		apply_filter(key);
	}

	// Click on header → toggle sort
	$body.on('click', 'th[data-sort]', function () {
		const key = $(this).closest('[data-table]').attr('data-table');
		const t = TABLES[key];
		const col = $(this).attr('data-sort');
		t.dir = t.sort_by === col ? -t.dir : 1;
		t.sort_by = col;
		render_table(key);
	});

	// Quick client-side filter: hide rows not matching the search text
	$body.find('[data-filter]').on('input', function () {
		const key = $(this).attr('data-filter');
		apply_filter(key);
	});

	function apply_filter(key) {
		const q = ($body.find(`[data-filter="${key}"]`).val() || '').toLowerCase();
		$body.find(`[data-table="${key}"] tbody tr`).each(function () {
			$(this).toggle($(this).text().toLowerCase().includes(q));
		});
	}

	// ── Cards & charts ───────────────────────────────────────────────────────
	function card(label, value, color) {
		return `
			<div class="col" style="min-width:150px;">
				<div class="frappe-card" style="padding:12px 15px;">
					<div class="text-muted" style="font-size:var(--text-sm);">${label}</div>
					<div style="font-size:24px; font-weight:600; color:${color || 'var(--text-color)'};">${value}</div>
				</div>
			</div>`;
	}

	function render_cards(s) {
		$body.find('[data-section="cards"]').html(
			card(__('Variants in Stock'), s.total_variants_in_stock) +
			card(__('Low Stock'), s.low_stock_variants, s.low_stock_variants ? 'var(--red-500)' : 'var(--green-500)') +
			card(__('Due Soon'), s.employees_due_soon, s.employees_due_soon ? 'var(--orange-500)' : undefined) +
			card(__('Overdue'), s.employees_overdue, s.employees_overdue ? 'var(--red-500)' : undefined) +
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
		if (!rows.length) return $el.html(no_data);
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
	function load() {
		frappe.call({ method: `${API}.uniform_api.get_dashboard_summary` })
			.then((r) => render_cards(r.message || {}));

		frappe.call({ method: `${API}.uniform_api.get_due_items`, args: { limit: 100000 } })
			.then((r) => {
				TABLES.due.rows = r.message || [];
				render_table('due');
			});

		frappe.call({ method: `${API}.uniform_excel_api.get_uniform_stock_excel` })
			.then((r) => {
				TABLES.stock.rows = r.message || [];
				// Auto-expand the collapsible section when low stock needs attention
				if (TABLES.stock.rows.some((x) => x.low_stock)) {
					$body.find('details[data-section="stock"]').attr('open', '');
				}
				render_table('stock');
			});

		frappe.call({ method: `${API}.uniform_excel_api.get_uniform_cost_excel`, args: { group_by: 'period' } })
			.then((r) => {
				const rows = (r.message || []).sort((a, b) => (a.period > b.period ? 1 : -1));
				render_chart('month', rows, 'period');
			});

		frappe.call({ method: `${API}.uniform_excel_api.get_uniform_cost_excel`, args: { group_by: 'department' } })
			.then((r) => render_chart('dept', r.message || [], 'department'));
	}

	load();
};
