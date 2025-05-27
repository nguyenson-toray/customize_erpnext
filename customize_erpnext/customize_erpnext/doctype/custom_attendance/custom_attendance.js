// custom_attendance.js - Client Script
// Đặt trong apps/customize_erpnext/customize_erpnext/doctype/custom_attendance/custom_attendance.js

frappe.ui.form.on('Custom Attendance', {
  refresh: function (frm) {
    // Add custom button in toolbar
    if (!frm.doc.__islocal && frm.doc.docstatus === 0) {
      frm.add_custom_button(__('Sync from Check-in'), function () {
        frm.trigger('sync_button');
      }, __('Actions'));
    }

    // Set filters for linked fields
    frm.set_query('employee', function () {
      return {
        filters: {
          status: 'Active'
        }
      };
    });

    frm.set_query('shift', function () {
      // Check if Shift Type has 'disabled' field, otherwise no filter
      return {
        filters: {
          // Most Shift Types don't have disabled field, so no filter
        }
      };
    });
  },

  sync_button: function (frm) {
    if (!frm.doc.employee || !frm.doc.attendance_date) {
      frappe.msgprint(__('Please select Employee and Attendance Date first'));
      return;
    }

    frappe.call({
      method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.sync_attendance_from_checkin',
      args: {
        doc_name: frm.doc.name
      },
      freeze: true,
      freeze_message: __('Syncing attendance data...'),
      callback: function (r) {
        if (r.message) {
          frappe.show_alert({
            message: __('Attendance synced successfully'),
            indicator: 'green'
          });
          frm.reload_doc();
        }
      },
      error: function (r) {
        frappe.msgprint(__('Error occurred while syncing attendance'));
      }
    });
  },

  employee: function (frm) {
    if (frm.doc.employee) {
      // Auto-populate related fields
      frappe.call({
        method: 'frappe.client.get',
        args: {
          doctype: 'Employee',
          name: frm.doc.employee
        },
        callback: function (r) {
          if (r.message) {
            frm.set_value('employee_name', r.message.employee_name);
            frm.set_value('company', r.message.company);
            frm.set_value('department', r.message.department);

            if (r.message.default_shift) {
              frm.set_value('shift', r.message.default_shift);
            }
          }
        }
      });
    }
  },

  attendance_date: function (frm) {
    if (frm.doc.attendance_date && frm.doc.employee) {
      // Clear previous attendance data when date changes
      frm.set_value('check_in', '');
      frm.set_value('check_out', '');
      frm.set_value('in_time', '');
      frm.set_value('out_time', '');
      frm.set_value('working_hours', 0);
      frm.set_value('late_entry', 0);
      frm.set_value('early_exit', 0);
      frm.set_value('last_sync_time', '');
      frm.set_value('status', 'Absent');

      frappe.show_alert({
        message: __('Attendance data cleared for new date. Click "Sync from Check-in" to load data.'),
        indicator: 'blue'
      });
    }
  },

  check_in: function (frm) {
    frm.trigger('calculate_working_hours');
    frm.trigger('update_status');
  },

  check_out: function (frm) {
    frm.trigger('calculate_working_hours');
    frm.trigger('update_status');
  },

  calculate_working_hours: function (frm) {
    if (frm.doc.check_in && frm.doc.check_out) {
      let check_in = moment(frm.doc.check_in);
      let check_out = moment(frm.doc.check_out);

      if (check_out.isAfter(check_in)) {
        let duration = moment.duration(check_out.diff(check_in));
        let hours = duration.asHours();
        frm.set_value('working_hours', Math.round(hours * 100) / 100);

        // Set in_time and out_time
        frm.set_value('in_time', moment(frm.doc.check_in).format('HH:mm:ss'));
        frm.set_value('out_time', moment(frm.doc.check_out).format('HH:mm:ss'));
      } else {
        frappe.msgprint(__('Check-out time cannot be earlier than check-in time'));
        frm.set_value('check_out', '');
      }
    }
  },

  update_status: function (frm) {
    if (frm.doc.check_in) {
      if (!frm.doc.status || frm.doc.status === 'Absent') {
        frm.set_value('status', 'Present');
      }
    }
  },

  auto_sync_enabled: function (frm) {
    if (frm.doc.auto_sync_enabled && frm.doc.employee && frm.doc.attendance_date) {
      frappe.show_alert({
        message: __('Auto sync enabled. Attendance will be automatically updated from check-ins.'),
        indicator: 'blue'
      });
    }
  }
});

// List View customizations
frappe.listview_settings['Custom Attendance'] = {
  add_fields: ['status', 'working_hours', 'auto_sync_enabled'],
  get_indicator: function (doc) {
    if (doc.status === 'Present') {
      return [__('Present'), 'green', 'status,=,Present'];
    } else if (doc.status === 'Absent') {
      return [__('Absent'), 'red', 'status,=,Absent'];
    } else if (doc.status === 'Half Day') {
      return [__('Half Day'), 'orange', 'status,=,Half Day'];
    } else if (doc.status === 'Work From Home') {
      return [__('Work From Home'), 'blue', 'status,=,Work From Home'];
    } else if (doc.status === 'On Leave') {
      return [__('On Leave'), 'purple', 'status,=,On Leave'];
    }
  },
  onload: function (listview) {
    // Add bulk sync button
    listview.page.add_menu_item(__('Bulk Sync Selected'), function () {
      let selected_docs = listview.get_checked_items();
      if (selected_docs.length === 0) {
        frappe.msgprint(__('Please select attendance records to sync'));
        return;
      }

      frappe.confirm(
        __('Are you sure you want to sync {0} attendance records?', [selected_docs.length]),
        function () {
          bulk_sync_attendance(selected_docs);
        }
      );
    });
  }
};

function bulk_sync_attendance(selected_docs) {
  let promises = [];

  selected_docs.forEach(function (doc) {
    promises.push(
      frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.sync_attendance_from_checkin',
        args: {
          doc_name: doc.name
        }
      })
    );
  });

  Promise.all(promises).then(function () {
    frappe.show_alert({
      message: __('Bulk sync completed successfully'),
      indicator: 'green'
    });
    location.reload();
  }).catch(function (error) {
    frappe.msgprint(__('Some records failed to sync. Please check the error log.'));
  });
}