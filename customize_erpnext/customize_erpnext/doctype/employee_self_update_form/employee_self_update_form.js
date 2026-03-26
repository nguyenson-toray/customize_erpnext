// Employee Self Update Form — client script

frappe.ui.form.on('Employee Self Update Form', {
	refresh(frm) {
		_render_other_docs(frm);
		_render_cccd_photos(frm);

		if (!frm.is_new()) {
			// Approve — only for Pending Review
			if (frm.doc.status === 'Pending Review') {
				frm.add_custom_button(__('Approve'), function() {
					frappe.confirm(
						__('Duyệt form của <b>{0}</b>?', [frm.doc.employee_name || frm.doc.employee]),
						function() {
							frappe.call({
								method: 'customize_erpnext.api.self_update.self_update_api.approve_form_bulk',
								args: { names: JSON.stringify([frm.doc.name]) },
								callback(r) {
									if (r.message) {
										frappe.show_alert({ message: __('Đã duyệt thành công.'), indicator: 'green' });
										frm.reload_doc();
									}
								}
							});
						}
					);
				}, __('Actions'));
			}

			// Sync to Employee — only for Approved
			if (frm.doc.status === 'Approved') {
				frm.add_custom_button(__('Sync to Employee'), function() {
					frappe.confirm(
						__('Đồng bộ dữ liệu form sang Employee <b>{0}</b>?', [frm.doc.employee_name || frm.doc.employee]),
						function() {
							frappe.call({
								method: 'customize_erpnext.api.self_update.self_update_api.sync_to_employee',
								args: { form_name: frm.doc.name },
								callback(r) {
									if (r.message && r.message.status === 'success') {
										frappe.show_alert({ message: __('Đã sync sang Employee thành công.'), indicator: 'green' });
										frm.reload_doc();
									} else {
										frappe.msgprint(__('Sync thất bại. Vui lòng kiểm tra lại.'));
									}
								}
							});
						}
					);
				}, __('Actions'));
			}

			// Re-Open — for Approved (in Actions group) or Synced (direct button)
			if (['Approved', 'Synced'].includes(frm.doc.status)) {
				// Use Actions group only for Approved (where Sync is also present).
				// For Synced the Actions group has no other buttons, so add directly
				// to avoid Frappe hiding a single-item group.
				const reopenGroup = frm.doc.status === 'Approved' ? __('Actions') : null;
				frm.add_custom_button(__('Re-Open'), function() {
					frappe.confirm(
						__('Mở lại form của <b>{0}</b> để nhân viên cập nhật lại? Dữ liệu hiện tại sẽ được giữ nguyên.', [frm.doc.employee_name || frm.doc.employee]),
						function() {
							frappe.call({
								method: 'customize_erpnext.api.self_update.self_update_api.reopen_form_bulk',
								args: { names: JSON.stringify([frm.doc.name]) },
								callback(r) {
									if (r.message && r.message.reopened_count) {
										frappe.show_alert({ message: __('Đã mở lại form thành công.'), indicator: 'blue' });
										frm.reload_doc();
									}
								}
							});
						}
					);
				}, reopenGroup);
			}

			// Make Actions the primary button group for statuses that have a group
			if (['Pending Review', 'Approved'].includes(frm.doc.status)) {
				frm.page.set_inner_btn_group_as_primary(__('Actions'));
			}
		}
	},
});

function _render_other_docs(frm) {
	const field = frm.get_field('other_docs_json');
	if (!field) return;

	let urls = [];
	try {
		urls = JSON.parse(frm.doc.other_docs_json || '[]');
		if (!Array.isArray(urls)) urls = [];
	} catch (e) { return; }

	field.$wrapper.find('.other-docs-preview').remove();
	if (!urls.length) return;

	const thumbs = urls.map(url => `
		<a href="${url}" target="_blank" title="${url}" style="display:inline-block;margin:4px">
			<img src="${url}"
				style="width:130px;height:100px;object-fit:cover;border-radius:6px;
					border:1px solid #d1d5db;cursor:pointer"
				onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"
			/>
			<div style="display:none;width:130px;height:100px;background:#f3f4f6;
				border-radius:6px;border:1px solid #d1d5db;align-items:center;
				justify-content:center;font-size:11px;color:#9ca3af">
				Không tải được
			</div>
		</a>`).join('');

	field.$wrapper.append(`
		<div class="other-docs-preview" style="margin-top:8px;padding:8px;
			background:#f9fafb;border-radius:6px;border:1px solid #e5e7eb">
			<div style="font-size:12px;color:#6b7280;margin-bottom:6px">
				${urls.length} ảnh — nhấp để xem toàn màn hình
			</div>
			<div style="display:flex;flex-wrap:wrap;gap:4px">${thumbs}</div>
		</div>`);
}

function _render_cccd_photos(frm) {
	for (const side of ['id_card_front_photo', 'id_card_back_photo']) {
		const url = frm.doc[side];
		const field = frm.get_field(side);
		if (!field || !url) continue;

		field.$wrapper.find('.cccd-thumb').remove();
		field.$wrapper.append(`
			<div class="cccd-thumb" style="margin-top:6px">
				<a href="${url}" target="_blank">
					<img src="${url}"
						style="max-width:260px;max-height:160px;border-radius:6px;
							border:1px solid #d1d5db;cursor:pointer"
						onerror="this.parentElement.remove()"
					/>
				</a>
			</div>`);
	}
}
