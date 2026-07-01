frappe.listview_settings['Employee Uniform Profile'] = {
	onload(listview) {
		listview.page.add_inner_button(__('Create Missing Profiles'), () => {
			frappe.confirm(
				__('Create Uniform Profiles for all Active employees who do not have one?'),
				() => {
					frappe.call({
						method: 'customize_erpnext.uniform_control.api.onboarding.backfill_uniform_profiles',
						freeze: true,
						freeze_message: __('Creating profiles...'),
						callback(r) {
							const m = r.message || {};
							frappe.msgprint(
								__('Created {0} profile(s) of {1} active employees.', [
									m.created || 0,
									m.active_employees || 0,
								])
							);
							listview.refresh();
						},
					});
				}
			);
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
				frappe.confirm(
					__('Add test Issuance Tracking (Bottle/Cap/Shoe, issued on joining date) to all profiles?'),
					() => {
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
					}
				);
			});
		}
	},
};
