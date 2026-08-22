// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on('Resignation Application', {
    setup: function (frm) {
        // Chỉ hiện lý do thuộc nhóm đang chọn, và chỉ mục còn Active.
        // Đây là lọc HIỂN THỊ. Chốt chặn thật nằm ở `validate_reason()` phía server —
        // Data Import và API không đi qua đây.
        frm.set_query('reason_for_leaving_group_2', () => ({
            filters: {
                reason_for_leaving_group: frm.doc.reason_for_leaving_group || '',
                is_active: 1,
            },
        }));
        frm.set_query('reason_for_leaving_group', () => ({ filters: { is_active: 1 } }));

        // Đơn nghỉ chỉ có nghĩa với người còn đang làm.
        frm.set_query('employee', () => ({ filters: { status: ['!=', 'Left'] } }));
    },

    refresh: function (frm) {
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Withdraw'), () => show_withdraw_dialog(frm));
        }
        render_status_banner(frm);
    },

    reason_for_leaving_group: function (frm) {
        // Đổi nhóm thì lý do cũ gần như chắc chắn không còn thuộc nhóm mới.
        if (frm.doc.reason_for_leaving_group_2) frm.set_value('reason_for_leaving_group_2', '');
    },

    resignation_letter_date: function (frm) {
        warn_letter_date_locked(frm);
        set_notice_days(frm);
    },

    relieving_date: function (frm) {
        set_notice_days(frm);
    },
});

/**
 * Số ngày báo trước — tính lại ngay trên form để HR thấy trước khi lưu.
 * Server vẫn tính lại trong validate(); đây chỉ là phản hồi tức thì.
 */
function set_notice_days(frm) {
    if (frm.doc.resignation_letter_date && frm.doc.relieving_date) {
        frm.set_value(
            'notice_days',
            frappe.datetime.get_day_diff(frm.doc.relieving_date, frm.doc.resignation_letter_date)
        );
    }
}

/**
 * Số đơn phát ra ngay ở lần lưu đầu tiên và không đổi theo resignation_letter_date nữa.
 * Nói thẳng điều đó lúc HR sửa ngày trên bản đã lưu, thay vì để họ phát hiện sau.
 */
function warn_letter_date_locked(frm) {
    if (frm.is_new() || !frm.doc.name) return;
    frappe.show_alert({
        message: __('Document number keeps {0} — it was issued on first save.', [frm.doc.name]),
        indicator: 'orange',
    });
}

function render_status_banner(frm) {
    if (frm.doc.docstatus === 2 && frm.doc.withdrawal_date) {
        frm.dashboard.add_indicator(
            __('Withdrawn on {0}', [frappe.datetime.str_to_user(frm.doc.withdrawal_date)]),
            'orange'
        );
        return;
    }
    if (frm.doc.docstatus === 1 && frm.doc.relieving_date) {
        const left = frappe.datetime.get_day_diff(frm.doc.relieving_date, frappe.datetime.get_today());
        frm.dashboard.add_indicator(
            left > 0
                ? __('{0} day(s) until leaving date', [left])
                : __('Leaving date has passed'),
            left > 0 ? 'blue' : 'red'
        );
    }
}

/**
 * Rút đơn. Một request duy nhất tới server: ghi ngày/lý do rồi cancel.
 * Tách làm hai request thì nửa chừng lỗi sẽ để lại đơn có ngày rút mà vẫn đang submitted.
 */
function show_withdraw_dialog(frm) {
    const d = new frappe.ui.Dialog({
        title: __('Withdraw Resignation'),
        fields: [
            {
                fieldname: 'withdrawal_date',
                fieldtype: 'Date',
                label: __('Withdrawal Date'),
                reqd: 1,
                default: frappe.datetime.get_today(),
            },
            {
                fieldname: 'withdrawal_reason',
                fieldtype: 'Small Text',
                label: __('Withdrawal Reason'),
            },
            {
                fieldtype: 'HTML',
                options: `<div class="text-muted small">${__(
                    'This cancels the application and reverts Relieving Date and Reason for Leaving on the Employee record.'
                )}</div>`,
            },
        ],
        primary_action_label: __('Withdraw'),
        primary_action(values) {
            frappe.call({
                method:
                    'customize_erpnext.customize_erpnext.doctype.resignation_application.resignation_application.withdraw',
                args: { name: frm.doc.name, ...values },
                freeze: true,
                freeze_message: __('Withdrawing...'),
                callback: () => {
                    d.hide();
                    frm.reload_doc();
                    frappe.show_alert({ message: __('Resignation withdrawn'), indicator: 'green' });
                },
            });
        },
    });
    d.show();
}
