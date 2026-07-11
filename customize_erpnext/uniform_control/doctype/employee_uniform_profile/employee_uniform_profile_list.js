frappe.listview_settings['Employee Uniform Profile'] = {
	onload(listview) {
		listview.page.add_inner_button(__('Create Missing Profiles'), () => {
			const d = new frappe.ui.Dialog({
				title: __('Create Missing Profiles'),
				fields: [
					{
						fieldname: 'include_left',
						fieldtype: 'Check',
						label: __('Include left employees'),
						description: __(
							'Also create profiles for employees who have left — keeps their issuance history importable. Allocations to non-Active employees stay blocked.'
						),
					},
				],
				primary_action_label: __('Create'),
				primary_action(values) {
					d.hide();
					frappe.call({
						method: 'customize_erpnext.uniform_control.api.onboarding.backfill_uniform_profiles',
						args: { include_left: values.include_left ? 1 : 0 },
						freeze: true,
						freeze_message: __('Creating profiles...'),
						callback(r) {
							const m = r.message || {};
							frappe.msgprint(
								__('Created {0} profile(s) of {1} employees.', [
									m.created || 0,
									m.active_employees || 0,
								])
							);
							listview.refresh();
						},
					});
				},
			});
			d.show();
		});

		listview.page.add_inner_button(__('Recompute Due Dates'), () => {
			frappe.confirm(
				__('Recompute next due date & status on all profiles? Run this after changing a rule\'s Reissue Cycle (Months).'),
				() => {
					frappe.call({
						method: 'customize_erpnext.uniform_control.api.uniform_api.recompute_all_tracking',
						freeze: true,
						freeze_message: __('Recomputing due dates...'),
						callback(r) {
							const m = r.message || {};
							frappe.msgprint(
								__('Recomputed {0} of {1} profiles.', [m.recomputed || 0, m.profiles || 0])
							);
							listview.refresh();
						},
					});
				}
			);
		});

		listview.page.add_inner_button(__('Sync Shoe Rack Locations'), () => {
			frappe.confirm(
				__('Re-sync Shoe Rack Location on all profiles from Shoe Rack assignments?'),
				() => {
					frappe.call({
						method: 'customize_erpnext.uniform_control.api.shoe_rack_sync.backfill_shoe_rack_locations',
						freeze: true,
						freeze_message: __('Syncing...'),
						callback(r) {
							const m = r.message || {};
							frappe.msgprint(
								__('Updated {0} of {1} profiles ({2} employees have a rack).', [
									m.updated || 0,
									m.profiles || 0,
									m.employees_with_rack || 0,
								])
							);
							listview.refresh();
						},
					});
				}
			);
		});

		// Administrator-only: seed Issuance Tracking with test data
		if (frappe.session.user === 'Administrator') {
			listview.page.add_inner_button(__('Seed Test Tracking'), () => {
				const d = new frappe.ui.Dialog({
					title: __('Seed Test Tracking'),
					fields: [
						{
							fieldname: 'mode',
							fieldtype: 'Select',
							label: __('Action'),
							reqd: 1,
							default: 'Download Excel for import',
							options: ['Insert to DB', 'Download Excel for import'].join('\n'),
						},
						{
							fieldtype: 'HTML',
							options: `<p class="text-muted small">${__(
								'Shirt/Cap/Shoe/Bottle qty follows each rule (áo sơ mi = 4, áo thun = 2); áo sơ mi last issue date = 2026-01-01 (or joining if later), everything else = joining date. Existing rows are kept.'
							)}<br>${__(
								'Excel is laid out for Data Import into Employee Uniform Profile (Update Existing Records).'
							)}</p>`,
						},
					],
					primary_action_label: __('Run'),
					primary_action(values) {
						d.hide();
						if (values.mode === 'Download Excel for import') {
							window.open(
								'/api/method/customize_erpnext.uniform_control.api.onboarding.seed_test_tracking_excel'
							);
							return;
						}
						frappe.call({
							method: 'customize_erpnext.uniform_control.api.onboarding.seed_test_tracking',
							freeze: true,
							freeze_message: __('Seeding test data...'),
							callback(r) {
								const m = r.message || {};
								frappe.msgprint(
									__('Added {0} tracking rows to {1} of {2} profiles.', [
										m.added || 0,
										m.profiles_updated || 0,
										m.total_profiles || 0,
									])
								);
								listview.refresh();
							},
						});
					},
				});
				d.show();
			});
		}
	},
};
