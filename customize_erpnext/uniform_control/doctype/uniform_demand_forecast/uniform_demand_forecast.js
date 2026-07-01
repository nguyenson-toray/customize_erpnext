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
			const basis = frm._ratio_basis || 'Company';
			window.open('/api/method/customize_erpnext.uniform_control.api.forecast.export_forecast_excel?forecast='
				+ encodeURIComponent(frm.doc.name) + '&basis=' + basis);
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
					// Friendly, people-oriented review notes (each = a real gap HR must handle).
					const CAT = { Shirt: __('shirt'), Cap: __('cap'), Shoe: __('shoe'), Bottle: __('water bottle') };
					const warnings = [];
					if ((m.unmapped || []).length) {
						warnings.push(
							`<b>${__('Designations with no current employees')}</b><br>`
							+ __('There are no current employees in these roles, so their needs could not be estimated. Add the items manually:')
							+ '<br>' + m.unmapped.map((u) => `&nbsp;&nbsp;• ${u.designation} — ${u.headcount} ${__('people')}`).join('<br>')
						);
					}
					if ((m.coverage_gaps || []).length) {
						const gap_lines = m.coverage_gaps.map((g) => {
							// who/why: designation + the grade that has no rule (blank grade → shirts)
							const who = (g.detail || []).map((x) =>
								`&nbsp;&nbsp;&nbsp;&nbsp;– ${x.designation} (${__('grade')}: ${x.grade || '—'}): ${x.count} ${__('people')}`
							).join('<br>');
							return `&nbsp;&nbsp;• ${__('missing')} ${CAT[g.category] || g.category}: ${g.uncovered} ${__('people')}`
								+ (who ? '<br>' + who : '');
						}).join('<br>');
						warnings.push(
							`<b>${__('People with no matching rule')}</b><br>`
							+ __('These new hires match no rule for the item type below (usually a blank Grade). Set Grade on the plan line, add a Uniform Rule, or enter manually:')
							+ '<br>' + gap_lines
						);
					}
					if ((m.missing_variants || []).length) {
						warnings.push(
							`<b>${__('Sizes with no product variant')}</b><br>`
							+ __('These sizes have no item variant yet — create the variant, then click Forecast again:')
							+ '<br>' + m.missing_variants.map((x) => `&nbsp;&nbsp;• ${x.template} — ${__('size')} ${x.size}: ${x.qty}`).join('<br>')
						);
					}
					if (warnings.length) {
						frappe.msgprint({
							title: __('Please review — some hires are not fully covered'),
							indicator: 'orange',
							message: warnings.join('<br><br>'),
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
// HR picks the scope: Company (whole org) or Recruited (only plan designations).
function render_current_ratio(frm, basis) {
	const field = frm.fields_dict.current_ratio_html;
	if (!field) return;
	if (frm.is_new()) {
		field.$wrapper.html('');
		return;
	}
	basis = basis || frm._ratio_basis || 'Recruited';
	frm._ratio_basis = basis;
	frappe.call({
		method: 'customize_erpnext.uniform_control.api.forecast.current_shirt_ratio',
		args: { forecast: frm.doc.name, basis },
		callback(r) {
			const msg = r.message || {};
			// Scope toggle — Recruited = the actual basis of Forecast Items (default).
			const hint = msg.basis === 'Recruited'
				? __('basis of Forecast Items')
				: __('general reference');
			const toggle = `<div style="margin-bottom:6px;">
				<div class="btn-group btn-group-xs" role="group">
					<button class="btn btn-xs ${msg.basis === 'Recruited' ? 'btn-primary' : 'btn-default'}" data-ratio-basis="Recruited">${__('Recruited designations')}</button>
					<button class="btn btn-xs ${msg.basis === 'Company' ? 'btn-primary' : 'btn-default'}" data-ratio-basis="Company">${__('Company-wide')}</button>
				</div>
				<span class="text-muted" style="margin-left:8px;">${hint} · ${__('As of {0}', [frappe.datetime.str_to_user(msg.as_of) || msg.as_of])}</span>
			</div>`;
			const rows = (msg.rows || []).map((x) => ({
				item_code: x.template, template: x.template, size: x.size, forecast_qty: x.qty,
			}));
			const body = rows.length
				? shirt_tables_html(rows)
				: `<span class="text-muted">${__('No current employee data.')}</span>`;
			field.$wrapper.html(toggle + body);
			field.$wrapper.find('[data-ratio-basis]').off('click').on('click', function () {
				render_current_ratio(frm, $(this).attr('data-ratio-basis'));
			});
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

// Hướng dẫn cho HR (tiếng Việt, dễ hiểu).
function show_forecast_help() {
	const d = new frappe.ui.Dialog({
		title: __('Dự toán nhu cầu đồng phục — Hướng dẫn'),
		size: 'extra-large',
		primary_action_label: __('OK'),
		primary_action: () => d.hide(),
	});
	d.$body.html(`
			<div style="line-height:1.8; font-size:var(--text-md); padding:6px 8px;">
				<p><b>Mục đích</b><br>
				Dự toán <b>số lượng đồng phục cần chuẩn bị</b> để lập kế hoạch mua / nhập kho trước.</p>

				<p><b>Ba chế độ tính (Mode)</b></p>
				<ul style="padding-left:18px; margin:4px 0;">
					<li><b>Người mới (New Hires)</b> — dự toán đồng phục cho <b>nhân viên dự kiến tuyển</b>, khai báo tại bảng <i>Chức danh cần tuyển</i>.</li>
					<li><b>Cấp lại (Re-issue)</b> — dự toán đồng phục <b>cấp lại định kỳ</b> cho nhân viên hiện tại, tính <b>đủ số kỳ đến hạn</b> cho tới ngày <i>To Date</i>.</li>
					<li><b>Cả hai (Both)</b> — tổng của Người mới và Cấp lại.</li>
				</ul>

				<p><b>Các bước thực hiện</b></p>
				<ol style="padding-left:18px; margin:4px 0;">
					<li>Chọn <b>Mode</b>:
						<ul style="padding-left:16px;">
							<li>Người mới → khai báo bảng <i>Chức danh cần tuyển</i>: Chức danh + Cấp bậc (tùy chọn) + Số lượng tuyển.</li>
							<li>Cấp lại → chọn <i>To Date</i> (mặc định: hôm nay + 1 năm).</li>
						</ul>
					</li>
					<li>Bấm nút <b>Forecast</b> (góc trên bên phải) — hệ thống lập bảng <i>Forecast Items</i>: nhu cầu theo từng <b>biến thể</b> (từng kích cỡ áo, từng màu mũ, dép, bình nước…) kèm <b>tồn kho hiện tại</b>.</li>
					<li>Rà soát, có thể <b>điều chỉnh cột SL dự toán</b> rồi <b>Lưu</b>. Sử dụng bảng này làm cơ sở lập kế hoạch mua sắm / nhập kho.</li>
					<li>Bấm <b>Tải Excel</b> để xuất báo cáo (2 sheet: Forecast và Tỉ lệ áo).</li>
				</ol>

				<p><b>Cơ chế tính chế độ "Người mới"</b></p>
				<ol style="padding-left:18px; margin:4px 0;">
					<li>Với mỗi chức danh, số lượng tuyển được phân bổ theo <b>cơ cấu nhân viên hiện tại</b> cùng chức danh —
						theo bốn tiêu chí: <b>Cấp bậc / Giới tính / Nhóm / Bộ phận</b>.</li>
					<li>Áp <b>Quy tắc cấp phát (Uniform Rules)</b> cho từng nhóm để xác định loại đồng phục và số lượng cấp lần đầu.
						Trong đó <b>Giới tính quyết định áo Nam hay Nữ</b> (và các món phân theo giới nếu có); Cấp bậc quyết định
						áo sơ mi; Nhóm / Bộ phận quyết định màu mũ…</li>
					<li>Riêng <b>áo</b> được phân bổ tiếp theo <b>tỉ lệ kích cỡ (size)</b> của nhân viên hiện tại cùng giới tính —
						mỗi người một kích cỡ, đúng số lượng cấp lần đầu.</li>
				</ol>

				<p><b>Lưu ý — Cấp bậc (Grade)</b><br>
				<b>Áo sơ mi được cấp theo Cấp bậc.</b> Với <b>chức danh mới hoàn toàn</b> (chưa có nhân viên để suy cơ cấu),
				cần khai báo <b>Cấp bậc</b> tại dòng tuyển; nếu để trống, hệ thống không xác định được cấp bậc và sẽ
				<b>cảnh báo để khai báo bổ sung</b>.</p>

				<p><b>Bảng "Tỉ lệ áo hiện tại" (chỉ tham khảo)</b><br>
				Thể hiện cơ cấu áo của nhân viên hiện tại theo Giới tính × Kích cỡ. Có hai phạm vi:
				<b>"Chức danh tuyển"</b> (mặc định — đúng cơ sở tính của bảng Forecast) và <b>"Toàn công ty"</b>
				(tham khảo chung). <b>Bảng này không ảnh hưởng kết quả</b>: Forecast Items luôn được tính theo từng
				chức danh, không thay đổi khi chuyển phạm vi.</p>

				<p><b>Khi xuất hiện cảnh báo "Vui lòng rà soát"</b><br>
				Một số nhân viên chưa được dự toán đầy đủ, thường do: <b>thiếu Cấp bậc</b>, <b>thiếu Quy tắc cấp phát</b>,
				hoặc <b>kích cỡ chưa có biến thể sản phẩm</b>. Cảnh báo nêu rõ chức danh và số lượng liên quan để bổ sung,
				sau đó bấm <b>Forecast</b> lại.</p>
			</div>`);
	d.show();
}
