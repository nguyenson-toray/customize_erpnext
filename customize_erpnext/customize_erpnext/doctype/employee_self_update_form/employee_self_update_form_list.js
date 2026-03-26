// Employee Self Update Form — List View customizations
frappe.listview_settings['Employee Self Update Form'] = {
	add_fields: ['status', 'employee_name', 'date_of_joining'],

	get_indicator: function(doc) {
		const map = {
			'Pending Review': ['Pending Review', 'orange'],
			'Approved':       ['Approved',       'green'],
			'Rejected':       ['Rejected',       'red'],
			'Synced':         ['Synced',          'blue'],
		};
		return map[doc.status] || [doc.status, 'grey'];
	},

	onload: function(listview) {
		const $btnApprove = listview.page.add_button(__('Approve Selected'), function() {
			const selected = listview.get_checked_items();
			if (!selected.length) return;
			const names = selected.map(r => r.name);
			frappe.call({
				method: 'customize_erpnext.api.self_update.self_update_api.approve_form_bulk',
				args: { names: JSON.stringify(names) },
				callback(r) {
					if (r.message) {
						const m = r.message;
						frappe.msgprint(__('Đã duyệt {0} form, bỏ qua {1}.', [m.approved_count, m.skipped_count]));
						listview.refresh();
					}
				}
			});
		}, 'primary');

		const $btnExcel = listview.page.add_button(__('Download Excel'), function() {
			const selected = listview.get_checked_items();
			if (!selected.length) return;
			const names = JSON.stringify(selected.map(r => r.name));
			frappe.call({
				method: 'customize_erpnext.api.self_update.self_update_api.download_excel',
				args: { names },
				callback(r) {
					if (r.message) {
						const { filename, data } = r.message;
						const a = document.createElement('a');
						a.href = 'data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,' + data;
						a.download = filename;
						a.click();
					}
				}
			});
		});

		const $btnCCCD = listview.page.add_button(__('Download CCCD Photos'), function() {
			const selected = listview.get_checked_items();
			if (!selected.length) return;
			const names = JSON.stringify(selected.map(r => r.name));
			frappe.call({
				method: 'customize_erpnext.api.self_update.self_update_api.download_cccd_photos',
				args: { names },
				callback(r) {
					if (r.message) {
						const { filename, data } = r.message;
						const a = document.createElement('a');
						a.href = 'data:application/zip;base64,' + data;
						a.download = filename;
						a.click();
					}
				}
			});
		});

		const $btnReopen = listview.page.add_button(__('Re-Open'), function() {
			const selected = listview.get_checked_items();
			if (!selected.length) return;
			const names = selected.map(r => r.name);
			frappe.confirm(
				__('Mở lại {0} form để nhân viên cập nhật lại? Dữ liệu hiện tại sẽ được giữ nguyên.', [names.length]),
				function() {
					frappe.call({
						method: 'customize_erpnext.api.self_update.self_update_api.reopen_form_bulk',
						args: { names: JSON.stringify(names) },
						callback(r) {
							if (r.message) {
								const m = r.message;
								frappe.msgprint(__('Đã mở lại {0} form, bỏ qua {1}.', [m.reopened_count, m.skipped_count]));
								listview.refresh();
							}
						}
					});
				}
			);
		});

		const $btnSync = listview.page.add_button(__('Sync to Employee'), function() {
			const selected = listview.get_checked_items();
			if (!selected.length) return;
			const names = selected.map(r => r.name);
			frappe.confirm(
				__('Đồng bộ {0} form sang Employee?', [names.length]),
				function() {
					let done = 0, failed = 0;
					const total = names.length;
					const next = (i) => {
						if (i >= total) {
							frappe.msgprint(__('Sync xong: {0} thành công, {1} lỗi.', [done, failed]));
							listview.refresh();
							return;
						}
						frappe.call({
							method: 'customize_erpnext.api.self_update.self_update_api.sync_to_employee',
							args: { form_name: names[i] },
							callback(r) { if (r.message && r.message.status === 'success') done++; else failed++; next(i + 1); },
							error()    { failed++; next(i + 1); }
						});
					};
					next(0);
				}
			);
		});

		// Disable all buttons initially, enable/disable on selection change
		function syncButtons() {
			const hasSelection = listview.get_checked_items().length > 0;
			[$btnApprove, $btnExcel, $btnCCCD, $btnSync, $btnReopen].forEach($btn => {
				$btn.prop('disabled', !hasSelection).toggleClass('disabled', !hasSelection);
			});
		}
		syncButtons();
		listview.$result.on('change', '.list-row-checkbox, .list-header-subject .checkbox', syncButtons);
		listview.$result.on('change', '#checkbox-select-all', syncButtons);
	}
};
