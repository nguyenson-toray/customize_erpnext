// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Overtime Registration", {
    refresh(frm) {
        // Hide Print button if document is not submitted
        frappe.call({
            method: 'customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration_hooks.get_include_draft_ot'
        })
            .then(r => {
                const val = r.message;
                if (val === 0 && frm.doc.docstatus != 1) {
                    $("button[data-original-title=Print]").hide();
                    frm.page.menu.find('[data-label="Print"]').parent().parent().remove();
                }
            });
        // if (frm.doc.docstatus != 1) {

        //     $("button[data-original-title=Print]").hide();
        //     frm.page.menu.find('[data-label="Print"]').parent().parent().remove();
        // }
        // Add custom styling for the form
        // frm.page.add_inner_button(__('Get Employees'), function () {
        //     show_ot_registration_dialog(frm);
        // }, __('Actions'));

        // Add button to remove empty rows
        // frm.page.add_inner_button(__('Remove Empty Rows'), function () {
        //     remove_empty_overtime_rows(frm);
        // }, __('Actions'));


        // Guided tour (Form Tour "Overtime Registration"): prominent banner at
        // the top of the form (inner buttons collapse into the "..." menu on
        // phones); auto-runs once per browser on the first new registration
        render_ot_help_banner(frm);
        render_ot_inline_pivot_button(frm);
        add_sync_to_mongodb_button(frm);
        if (frm.is_new() && !ot_tour_seen()) {
            frappe.utils.sleep(600).then(() => start_ot_form_tour(frm));
        }

        // Reset validation flags when form refreshes
        frm.pre_save_check_done = false;
        frm.ot_continuity_validated = false;

        // New registration: group + approver of the logged-in user's employee
        // (the server sets the same from the doc owner on save)
        if (frm.is_new()) {
            frappe.xcall('frappe.client.get_value', {
                doctype: 'Employee',
                filters: { user_id: frappe.session.user },
                fieldname: ['name', 'custom_group']
            }).then(emp => {
                if (!emp || !emp.name) return;
                if (!frm.doc.request_by_group && emp.custom_group) {
                    frm.set_value('request_by_group', emp.custom_group);
                }
                set_approver_for_employee(frm, emp.name);
            }).catch(() => { /* no Employee read permission — server fills on save */ });
        }

    },
    get_employees_button(frm) {
        show_ot_registration_dialog(frm);
    },

    before_save(frm) {
        // Frappe runs before_save even when `validate` already failed (missing time,
        // duplicate row...): do not open the pre-save check on top of that error —
        // pressing its Save would move times and then fail validation again.
        if (frappe.validated === false) {
            frm.pre_save_check_done = false;
            return;
        }
        if (!frm.pre_save_check_done) {
            frappe.validated = false;
            check_all_before_save(frm);
            return false;
        }
        // One-shot: consume the flag so a save rejected by the server still
        // re-runs the pre-save check next time (it used to stay true until
        // refresh, so rows added after a failed save skipped the check).
        frm.pre_save_check_done = false;
    },

    validate(frm) {
        // Auto-remove empty rows before validation
        remove_empty_overtime_rows(frm, true);

        // Validate required fields
        if (!validate_required_fields(frm)) {
            return false;
        }

        // Validate time order: begin_time < end_time
        if (!validate_time_order(frm)) {
            return false;
        }

        // Validate duplicate rows within form
        if (!validate_duplicate_rows(frm)) {
            return false;
        }

        // Validate single post-shift entry per employee per day
        if (!validate_single_post_shift_entry(frm)) {
            return false;
        }
        // Totals / approver name are computed server-side
    }
});

// ---------------------------------------------------------------------------
// "Get Employees" dialog — single-screen overtime planner.
// Left pane: plan (group, week, days, time, reason). Right pane: team roster.
// Batch mode: "Add Selected" writes rows and keeps the dialog open; the footer
// accumulates the session total (batches · rows · man-hours) with undo.
// ---------------------------------------------------------------------------

// Tuần mặc định khi mở "Select Employees for Overtime Registration": 1 = Tuần +1
// (user chốt 12/11/2026 — tăng ca thường đăng ký cho tuần sau)
const OT_DEFAULT_WEEK_OFFSET = 1;

function _get_dialog_state(frm) {
    if (!frm._ot_dialog_state) {
        frm._ot_dialog_state = {
            currentDialog: null,
            selectedEmployees: new Map(), // employee id -> {name, employee_name, custom_group}
            employeeList: [],             // employees of the currently loaded group
            selectedDays: new Set(),      // 'monday'..'saturday'
            weekOffset: OT_DEFAULT_WEEK_OFFSET,
            searchTerm: '',
            loadingEmployees: false,
            addedBatches: [],             // batches written this session (for ledger + undo)
            otBlocked: {}                 // employee -> reason (maternity, no OT) — get_ot_blocked_employees
        };
    }
    return frm._ot_dialog_state;
}

// Function to get current user's filter value based on filter_employee_by field
function get_user_filter_value(frm) {
    const filterBy = frm.doc.filter_employee_by;

    if (!filterBy) {
        return Promise.resolve({ filterBy: null, filterValue: null });
    }

    return frappe.xcall('frappe.client.get_list', {
        doctype: 'Employee',
        fields: ['department', 'custom_section', 'custom_group'],
        filters: { 'user_id': frappe.session.user },
        limit_page_length: 1
    }).then(result => {
        if (result && result.length > 0) {
            return { filterBy, filterValue: result[0][filterBy] };
        }
        return { filterBy, filterValue: null };
    });
}

function ot_day_fields() {
    return ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
}

function ot_day_labels() {
    return [__('Mon'), __('Tue'), __('Wed'), __('Thu'), __('Fri'), __('Sat')];
}

function ot_esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
}

function ot_monday_of_week(weekOffset) {
    const today = new Date();
    const monday = new Date(today);
    monday.setDate(today.getDate() - today.getDay() + 1 + (weekOffset * 7));
    return monday;
}

function ot_format_dm(date) {
    return date.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit' });
}

// Local YYYY-MM-DD (toISOString would shift the date before 07:00 in UTC+7)
function ot_format_ymd(date) {
    return date.getFullYear() + '-'
        + String(date.getMonth() + 1).padStart(2, '0') + '-'
        + String(date.getDate()).padStart(2, '0');
}

// ── Thai sản: NV KHÔNG được tăng ca (user chốt 02/11/2026) ──────────────
// Nguồn: get_ot_blocked_employees — đọc đúng giá trị đang lưu trên hồ sơ thai sản:
// Status = Maternity Leave, hoặc Status = Pregnant và Overtime = Not Allowed.
function ot_hidden_reason(state, employee) {
    return state.otBlocked[employee] || null;
}

function ot_blocked_label(reason) {
    return reason === 'Maternity Leave' ? __('Maternity Leave') : __('Pregnant from 7th month');
}

function ot_time_to_minutes(time_str) {
    if (!time_str) return null;
    const parts = String(time_str).split(':');
    const h = parseInt(parts[0]);
    const m = parseInt(parts[1] || 0);
    if (isNaN(h) || isNaN(m)) return null;
    return h * 60 + m;
}

function ot_num(n) {
    return String(parseFloat(n.toFixed(2)));
}

function ot_highlight(text, term) {
    const safe = ot_esc(text);
    if (!term) return safe;
    const pattern = term.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    if (!pattern) return safe;
    return safe.replace(new RegExp('(' + ot_esc(pattern) + ')', 'gi'), '<mark>$1</mark>');
}

function ensure_ot_dialog_styles() {
    if (document.getElementById('ot-reg-dialog-css')) return;
    const style = document.createElement('style');
    style.id = 'ot-reg-dialog-css';
    style.textContent = `
.ot-reg-modal {
    --ot-accent: #b45309;
    --ot-accent-text: #92400e;
    --ot-wash: #fdf3e0;
    --ot-wash-border: #ecd3a4;
}
html[data-theme="dark"] .ot-reg-modal,
html[data-theme-mode="dark"] .ot-reg-modal {
    --ot-accent: #f5b83d;
    --ot-accent-text: #f7c96b;
    --ot-wash: rgba(245, 184, 61, 0.12);
    --ot-wash-border: rgba(245, 184, 61, 0.4);
}
.ot-reg-modal .modal-dialog { max-width: min(1060px, calc(100vw - 24px)); }
.ot-reg-modal .modal-footer {
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; flex-wrap: wrap;
}
/* Controls regrouped into rows by arrange_ot_dialog_rows(): Group + Week,
   Begin + End time. Wraps only when the column is too narrow for both. */
.ot-reg-modal .ot-row { display: flex; gap: 12px; align-items: flex-start; flex-wrap: wrap; }
.ot-reg-modal .ot-row > * { min-width: 0; }
.ot-reg-modal .ot-row-group > [data-fieldname="selected_group"] { flex: 1 1 150px; }
.ot-reg-modal .ot-row-group > [data-fieldname="week_html"] { flex: 2 1 250px; }
.ot-reg-modal .ot-row-time > .frappe-control { flex: 1 1 120px; }
.ot-reg-modal .ot-row-group .ot-seg { margin-bottom: 0; }
/* Tablet portrait (and phones): stack the plan pane above the roster so each
   row gets the full dialog width and stays on one line */
@media (max-width: 991px) {
    .ot-reg-modal .modal-body .form-column { flex: 0 0 100%; max-width: 100%; }
    .ot-reg-modal .form-column + .form-column { margin-top: 6px; }
}

.ot-step-no {
    display: inline-flex; align-items: center; justify-content: center;
    width: 18px; height: 18px; margin-right: 6px; border-radius: 50%;
    background: var(--ot-accent); color: #fff; font-size: 11px; font-weight: 600;
    line-height: 1; vertical-align: 1px;
}
html[data-theme="dark"] .ot-reg-modal .ot-step-no { color: #1c1c1c; }
.ot-reg-modal .btn-modal-primary .ot-step-no { background: rgba(255, 255, 255, 0.25); color: inherit; }
.ot-help-banner {
    display: flex; align-items: center; gap: 10px; margin: 0 0 12px;
    padding: 10px 12px; border-radius: 10px;
    background: #fdf3e0; border: 1px solid #ecd3a4; color: #92400e;
}
html[data-theme="dark"] .ot-help-banner {
    background: rgba(245, 184, 61, 0.12); border-color: rgba(245, 184, 61, 0.4); color: #f7c96b;
}
.ot-help-banner .ot-help-icon {
    flex: none; width: 26px; height: 26px; border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center;
    background: #b45309; color: #fff; font-weight: 700;
}
.ot-help-banner .ot-help-text { flex: 1; font-size: 13px; font-weight: 500; }
.ot-help-banner .ot-help-btn {
    flex: none; background: #b45309; border-color: #b45309; color: #fff;
    font-weight: 600; min-height: 36px; padding: 4px 16px;
}
.ot-help-banner .ot-help-btn:hover { background: #92400e; border-color: #92400e; color: #fff; }
/* "Add Employees" + "View Summary Table" + "Print" on one row */
.frappe-control[data-fieldname="get_employees_button"] .control-input {
    display: flex; flex-wrap: nowrap; align-items: stretch; gap: 8px;
}
.frappe-control[data-fieldname="get_employees_button"] .control-input .btn { margin: 0; }
@media (max-width: 991px), (pointer: coarse) {
    .frappe-control[data-fieldname="get_employees_button"] .control-input .btn {
        flex: 1 1 0; min-width: 0; min-height: 44px; padding: 6px 10px; font-size: 14px;
        white-space: normal; line-height: 1.2;
    }
}
.ot-mini-head { display: flex; align-items: center; justify-content: space-between; margin: 4px 0 6px; }
.ot-mini-head > span { font-size: var(--text-sm, 12px); color: var(--text-muted); }
.ot-linkbtn {
    background: none; border: none; padding: 0; font-size: 12px;
    color: var(--text-muted); text-decoration: underline; cursor: pointer;
}
.ot-linkbtn:hover { color: var(--text-color); }

.ot-seg { display: flex; gap: 6px; margin-bottom: 10px; }
.ot-seg button {
    flex: 1; border: 1px solid var(--border-color); background: transparent;
    border-radius: 8px; padding: 5px 4px; cursor: pointer;
    color: var(--text-muted); line-height: 1.25;
}
.ot-seg button .ot-seg-label { display: block; font-size: 12px; font-weight: 600; }
.ot-seg button .ot-seg-range { display: block; font-size: 11px; margin-top: 1px; }
.ot-seg button.active { background: var(--ot-wash); border-color: var(--ot-wash-border); color: var(--ot-accent-text); }

.ot-days { display: grid; grid-template-columns: repeat(6, 1fr); gap: 6px; margin-bottom: 10px; }
.ot-day {
    border: 1px solid var(--border-color); background: transparent; border-radius: 8px;
    padding: 6px 2px 8px; text-align: center; cursor: pointer;
    color: var(--text-color); position: relative;
}
.ot-day .ot-day-name { display: block; font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); }
.ot-day .ot-day-num { display: block; font-size: 17px; font-weight: 600; line-height: 1.3; }
.ot-day .ot-day-mon { display: block; font-size: 10px; color: var(--text-muted); }
.ot-day.selected { background: var(--ot-wash); border-color: var(--ot-accent); color: var(--ot-accent-text); }
.ot-day.selected .ot-day-name, .ot-day.selected .ot-day-mon { color: var(--ot-accent-text); }
.ot-day.today::after {
    content: ""; position: absolute; left: 50%; transform: translateX(-50%);
    bottom: 3px; width: 4px; height: 4px; border-radius: 50%; background: var(--ot-accent);
}

.ot-search {
    width: 100%; border: 1px solid var(--border-color);
    background: var(--control-bg, transparent); border-radius: 8px;
    padding: 6px 10px; font-size: 13px; color: var(--text-color); margin-bottom: 8px;
}
.ot-search:focus { outline: none; border-color: var(--ot-accent); }
.ot-roster { border: 1px solid var(--border-color); border-radius: 8px; max-height: 308px; overflow-y: auto; }
.ot-roster mark { background: var(--ot-wash); color: inherit; padding: 0; }
.ot-roster-head {
    position: sticky; top: 0; z-index: 1;
    background: var(--card-bg, var(--bg-color, #fff));
    border-bottom: 1px solid var(--border-color);
    display: flex; justify-content: space-between; align-items: center; padding: 6px 10px;
}
.ot-roster-head label {
    margin: 0; font-size: 12px; font-weight: 500;
    display: flex; gap: 6px; align-items: center; cursor: pointer;
}
.ot-roster-count { font-size: 11px; color: var(--text-muted); }
.ot-roster-row {
    display: flex; gap: 8px; align-items: center; padding: 5px 10px; margin: 0;
    cursor: pointer; font-weight: 400; border-bottom: 1px solid var(--border-color);
}
.ot-roster-row:last-child { border-bottom: none; }
.ot-roster-row:hover { background: var(--fg-hover-color, rgba(0, 0, 0, 0.03)); }
.ot-roster-row input { margin: 0; flex: none; }
.ot-emp-id { font-size: 12px; color: var(--text-muted); white-space: nowrap; }
.ot-roster-row.checked .ot-emp-id { color: var(--ot-accent-text); }
.ot-emp-name { font-size: 13px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ot-roster-empty { padding: 18px 12px; text-align: center; color: var(--text-muted); font-size: 13px; }
.ot-roster-hidden {
    padding: 5px 10px; font-size: 12px; cursor: help;
    color: var(--text-muted); background: var(--subtle-fg, rgba(0, 0, 0, 0.03));
    border-bottom: 1px solid var(--border-color);
}

.ot-chips-head { display: flex; justify-content: space-between; align-items: center; margin: 10px 0 6px; }
.ot-chips-head > span { font-size: var(--text-sm, 12px); color: var(--text-muted); }
.ot-team-count { color: var(--ot-accent-text); font-weight: 600; }
.ot-chips { display: flex; flex-wrap: wrap; gap: 4px; max-height: 88px; overflow-y: auto; }
.ot-chips-empty { color: var(--text-muted); font-size: 12px; }
.ot-chip {
    display: inline-flex; align-items: center; gap: 4px;
    background: var(--ot-wash); border: 1px solid var(--ot-wash-border);
    color: var(--text-color); border-radius: 999px; padding: 1px 4px 1px 8px; font-size: 11.5px;
}
.ot-chip button {
    border: none; background: none; padding: 0 4px; cursor: pointer;
    color: var(--text-muted); font-size: 13px; line-height: 1;
}
.ot-chip button:hover { color: var(--ot-accent-text); }

.ot-footer-info { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.ot-session {
    font-size: 11.5px; color: var(--text-muted);
    display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
}
.ot-session b { color: var(--ot-accent-text); font-weight: 600; }

.ot-pivot-summary { font-size: 12px; color: var(--text-muted); margin-bottom: 8px; }
.ot-pivot { max-height: 65vh; overflow: auto; border: 1px solid var(--border-color); border-radius: 8px; }
.ot-pivot table { border-collapse: separate; border-spacing: 0; width: 100%; font-size: 12.5px; }
.ot-pivot th, .ot-pivot td {
    border-bottom: 1px solid var(--border-color); border-right: 1px solid var(--border-color);
    padding: 4px 8px; text-align: center; white-space: nowrap;
}
.ot-pivot th {
    position: sticky; top: 0; z-index: 2;
    background: var(--card-bg, var(--bg-color, #fff)); font-weight: 600;
}
.ot-pivot .ot-pivot-no {
    position: sticky; left: 0; z-index: 1;
    background: var(--card-bg, var(--bg-color, #fff));
    width: 40px; min-width: 40px; max-width: 40px; box-sizing: border-box;
}
.ot-pivot .ot-pivot-emp {
    position: sticky; left: 40px; z-index: 1;
    background: var(--card-bg, var(--bg-color, #fff)); text-align: left;
}
.ot-pivot thead .ot-pivot-no, .ot-pivot thead .ot-pivot-emp { z-index: 3; }
.ot-pivot-off { color: var(--text-muted); opacity: 0.5; }
.ot-pivot-total { font-weight: 600; }
.ot-pivot-footrow td {
    font-weight: 600; border-top: 2px solid var(--border-color);
    position: sticky; bottom: 0; background: var(--card-bg, var(--bg-color, #fff));
}

.ot-day:focus-visible, .ot-seg button:focus-visible,
.ot-linkbtn:focus-visible, .ot-chip button:focus-visible {
    outline: 2px solid var(--ot-accent); outline-offset: 1px;
}
/* Touch devices (target: tablets) and phones: 44px+ touch targets, 16px
   inputs (no zoom-on-focus), action bar pinned to the bottom so "Add
   Selected" stays reachable while scrolling the roster */
@media (max-width: 767px), (pointer: coarse) {
    .ot-reg-modal .modal-footer {
        position: sticky; bottom: 0; z-index: 5; padding: 10px 14px;
        background: var(--modal-bg, var(--card-bg, #fff));
        border-top: 1px solid var(--border-color);
        box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.06);
    }
    .ot-reg-modal .modal-footer .standard-actions { display: flex; gap: 8px; margin: 0; }
    .ot-reg-modal .modal-footer .standard-actions .btn { min-height: 44px; min-width: 110px; font-size: 15px; margin: 0; }
    .ot-reg-modal [data-fieldname="reason"] textarea { height: 64px; min-height: 64px; }
    .ot-reg-modal input.form-control, .ot-reg-modal textarea.form-control { font-size: 16px; min-height: 40px; }

    .ot-seg button { padding: 8px 4px; min-height: 48px; }
    .ot-days { gap: 8px; }
    .ot-day { padding: 10px 2px 12px; }
    .ot-day .ot-day-name { font-size: 11px; }
    .ot-day .ot-day-num { font-size: 19px; }
    .ot-linkbtn { font-size: 13px; padding: 8px 0; }

    .ot-search { font-size: 16px; padding: 10px 12px; }
    .ot-roster { max-height: 50vh; }
    .ot-roster-head { padding: 8px 12px; }
    .ot-roster-head label { font-size: 14px; }
    .ot-roster-row { padding: 10px 12px; min-height: 48px; gap: 10px; }
    .ot-roster-row input, .ot-roster-head input { width: 20px; height: 20px; }
    .ot-emp-id { font-size: 13px; }
    .ot-emp-name { font-size: 15px; }
    .ot-chips { max-height: 80px; }
    .ot-chip { font-size: 13px; padding: 4px 4px 4px 10px; }
    .ot-chip button { font-size: 18px; padding: 0 8px; min-height: 28px; }

    .ot-pivot { max-height: calc(100dvh - 170px); -webkit-overflow-scrolling: touch; }
    .ot-help-banner .ot-help-btn { min-height: 44px; padding: 6px 20px; font-size: 14px; }
}

/* Narrow screens (phones, tablets in split view): full-screen sheet, stacked panes */
@media (max-width: 767px) {
    .ot-reg-modal .modal-dialog { margin: 0; max-width: 100%; width: 100%; min-height: 100%; }
    .ot-reg-modal .modal-content { border-radius: 0; border: none; min-height: 100vh; min-height: 100dvh; }
    .ot-reg-modal .modal-body { padding: 12px 14px; }
    .ot-reg-modal .ot-footer-info { width: 100%; }
    .ot-reg-modal .modal-footer .standard-actions { width: 100%; }
    .ot-reg-modal .modal-footer .standard-actions .btn { flex: 1; min-width: 0; }
    .ot-reg-modal .modal-footer .standard-actions .btn-modal-primary { flex: 2; }
    .ot-days { grid-template-columns: repeat(3, 1fr); }
    .ot-emp-name { white-space: normal; }

    .ot-pivot table { font-size: 12px; }
    .ot-pivot th, .ot-pivot td { padding: 4px 5px; }
    .ot-pivot .ot-pivot-no, .ot-pivot .ot-pivot-grp { display: none; }
    .ot-pivot .ot-pivot-emp { left: 0; min-width: 104px; max-width: 128px; white-space: normal; }
    .ot-pivot .ot-pivot-id { display: block; font-size: 11px; }
    .ot-pivot .ot-pivot-name { display: block; line-height: 1.25; }
    .ot-pivot .ot-t { display: block; }
    .ot-pivot .ot-t-dash { display: none; }
    .ot-pivot .ot-slot + .ot-slot { border-top: 1px dashed var(--border-color); margin-top: 2px; padding-top: 2px; }
}
@media (prefers-reduced-motion: no-preference) {
    .ot-day, .ot-seg button, .ot-chip { transition: background-color 0.12s ease, border-color 0.12s ease, color 0.12s ease; }
}
`;
    document.head.appendChild(style);
}

function show_ot_registration_dialog(frm) {
    const state = _get_dialog_state(frm);
    ensure_ot_dialog_styles();

    // Close any existing dialog first and start a fresh selection session
    if (state.currentDialog) {
        state.currentDialog.hide();
        state.currentDialog = null;
    }
    state.selectedEmployees.clear();
    state.selectedDays.clear();
    state.employeeList = [];
    state.weekOffset = OT_DEFAULT_WEEK_OFFSET;
    state.searchTerm = '';
    state.loadingEmployees = false;
    state.addedBatches = [];

    const locked_group = (frm.doc.filter_employee_by === 'custom_group' && frm.doc.request_by_group)
        ? frm.doc.request_by_group : null;

    const dialog = new frappe.ui.Dialog({
        title: __('Select Employees for Overtime Registration'),
        size: 'extra-large',
        // Frappe focuses the first input on open; on phones/tablets that pops
        // the on-screen keyboard over the dialog. Group is pre-filled anyway.
        no_focus: window.matchMedia('(max-width: 767px), (pointer: coarse)').matches,
        fields: [
            {
                fieldtype: 'Link',
                fieldname: 'selected_group',
                label: __('Group'),
                options: 'Group',
                reqd: 1,
                default: locked_group || undefined,
                get_query: function () {
                    if (locked_group) {
                        return { filters: { name: locked_group } };
                    }
                    return {};
                },
                onchange: function () {
                    on_dialog_group_changed(frm);
                }
            },
            { fieldtype: 'HTML', fieldname: 'week_html' },
            { fieldtype: 'HTML', fieldname: 'days_html' },
            {
                fieldtype: 'Time',
                fieldname: 'time_begin',
                label: __('Begin Time'),
                default: '17:00:00'
            },
            {
                fieldtype: 'Time',
                fieldname: 'time_end',
                label: __('End Time'),
                default: '19:00:00'
            },
            {
                fieldtype: 'Small Text',
                fieldname: 'reason',
                label: __('Reason'),
                reqd: 1
            },
            { fieldtype: 'Column Break' },
            { fieldtype: 'HTML', fieldname: 'team_html' }
        ],
        primary_action_label: __('Add Selected'),
        primary_action: function () {
            save_overtime_registration_native(frm);
        },
        secondary_action_label: __('Close'),
        secondary_action: function () {
            if (state.currentDialog) state.currentDialog.hide();
        }
    });

    state.currentDialog = dialog;
    dialog.show();
    dialog.$wrapper.addClass('ot-reg-modal');

    render_ot_week_segment(frm);
    render_ot_day_tiles(frm);
    render_ot_team_pane(frm);
    inject_ot_ledger(frm);
    arrange_ot_dialog_rows(dialog);
    add_ot_dialog_step_numbers(dialog);

    // A locked group is pre-filled, so load its roster immediately
    if (locked_group) {
        on_dialog_group_changed(frm);
    } else {
        // Pre-select the logged-in user's own group; set_value fires the
        // field's onchange, which loads the roster
        get_current_user_group(frm).then(group => {
            if (group && state.currentDialog === dialog && !dialog.get_value('selected_group')) {
                dialog.set_value('selected_group', group);
            }
        });
    }
}

// custom_group of the logged-in user's Employee (cached per form)
function get_current_user_group(frm) {
    if (frm._ot_user_group !== undefined) {
        return Promise.resolve(frm._ot_user_group);
    }
    return frappe.xcall('frappe.client.get_value', {
        doctype: 'Employee',
        filters: { user_id: frappe.session.user },
        fieldname: 'custom_group'
    }).then(r => {
        frm._ot_user_group = (r && r.custom_group) || null;
        return frm._ot_user_group;
    }).catch(() => null);
}

function render_ot_week_segment(frm) {
    const state = _get_dialog_state(frm);
    const $wrap = state.currentDialog.get_field('week_html').$wrapper;
    const labels = [__('Current Week'), __('Week +1'), __('Week +2')];

    let html = '<div class="ot-mini-head"><span>' + ot_step_badge(2) + ot_esc(__('Week')) + '</span></div><div class="ot-seg" role="group">';
    for (let i = 0; i < 3; i++) {
        const monday = ot_monday_of_week(i);
        const sunday = new Date(monday);
        sunday.setDate(monday.getDate() + 6);
        const active = state.weekOffset === i;
        html += `<button type="button" data-week="${i}" class="${active ? 'active' : ''}" aria-pressed="${active}">
            <span class="ot-seg-label">${ot_esc(labels[i])}</span>
            <span class="ot-seg-range">${ot_format_dm(monday)}–${ot_format_dm(sunday)}</span>
        </button>`;
    }
    html += '</div>';
    $wrap.html(html);

    $wrap.find('button[data-week]').on('click', function () {
        const newOffset = parseInt($(this).attr('data-week')) || 0;
        if (newOffset === state.weekOffset) return;
        state.weekOffset = newOffset;
        // Dates change meaning across weeks, so drop the day selection to avoid
        // registering the wrong week by accident
        state.selectedDays.clear();
        $wrap.find('button[data-week]').removeClass('active').attr('aria-pressed', 'false');
        $(this).addClass('active').attr('aria-pressed', 'true');
        render_ot_day_tiles(frm);
    });
}

function render_ot_day_tiles(frm) {
    const state = _get_dialog_state(frm);
    const $wrap = state.currentDialog.get_field('days_html').$wrapper;
    const monday = ot_monday_of_week(state.weekOffset);
    const names = ot_day_labels();
    const todayStr = new Date().toDateString();

    let html = '<div class="ot-mini-head"><span>' + ot_step_badge(3) + ot_esc(__('Day Selection')) + '</span>'
        + '<button type="button" class="ot-linkbtn ot-days-all">' + ot_esc(__('Select All')) + '</button></div>';
    html += '<div class="ot-days">';
    ot_day_fields().forEach((dayField, index) => {
        const date = new Date(monday);
        date.setDate(monday.getDate() + index);
        const selected = state.selectedDays.has(dayField);
        const today = date.toDateString() === todayStr;
        html += `<button type="button" class="ot-day${selected ? ' selected' : ''}${today ? ' today' : ''}"
                data-day="${dayField}" aria-pressed="${selected}"
                title="${ot_esc(names[index])} ${ot_format_dm(date)}">
            <span class="ot-day-name">${ot_esc(names[index])}</span>
            <span class="ot-day-num">${String(date.getDate()).padStart(2, '0')}</span>
            <span class="ot-day-mon">/${String(date.getMonth() + 1).padStart(2, '0')}</span>
        </button>`;
    });
    html += '</div>';
    $wrap.html(html);

    $wrap.find('.ot-day').on('click', function () {
        const day = $(this).attr('data-day');
        if (state.selectedDays.has(day)) {
            state.selectedDays.delete(day);
        } else {
            state.selectedDays.add(day);
        }
        $(this).toggleClass('selected', state.selectedDays.has(day))
            .attr('aria-pressed', String(state.selectedDays.has(day)));
    });

    $wrap.find('.ot-days-all').on('click', function () {
        const all_selected = state.selectedDays.size === ot_day_fields().length;
        state.selectedDays.clear();
        if (!all_selected) {
            ot_day_fields().forEach(d => state.selectedDays.add(d));
        }
        render_ot_day_tiles(frm);
    });
}

function render_ot_team_pane(frm) {
    const state = _get_dialog_state(frm);
    const $wrap = state.currentDialog.get_field('team_html').$wrapper;

    $wrap.html(`
        <div class="ot-mini-head"><span>${ot_step_badge(6)}${ot_esc(__('Employee Selection'))}</span></div>
        <input type="search" class="ot-search"
            placeholder="${ot_esc(__('Type employee name or ID to filter...'))}"
            aria-label="${ot_esc(__('Search Employees'))}">
        <div class="ot-roster"></div>
        <div class="ot-chips-head">
            <span>${ot_esc(__('Selected Employees'))}: <span class="ot-team-count">0</span></span>
            <button type="button" class="ot-linkbtn ot-clear-all">${ot_esc(__('Clear All Selected'))}</button>
        </div>
        <div class="ot-chips"></div>
    `);

    $wrap.find('.ot-search').on('input', function () {
        state.searchTerm = this.value;
        update_ot_roster(frm);
    });
    $wrap.find('.ot-clear-all').on('click', function () {
        clear_selected_employees(frm);
    });

    update_ot_roster(frm);
    update_ot_chips(frm);
}

function update_ot_roster(frm) {
    const state = _get_dialog_state(frm);
    if (!state.currentDialog) return;
    const $roster = state.currentDialog.get_field('team_html').$wrapper.find('.ot-roster');
    if (!$roster.length) return;

    if (!state.currentDialog.get_value('selected_group')) {
        $roster.html('<div class="ot-roster-empty">' + ot_esc(__('Please select a group first')) + '</div>');
        return;
    }
    if (state.loadingEmployees) {
        $roster.html('<div class="ot-roster-empty">' + ot_esc(__('Loading employees...')) + '</div>');
        return;
    }
    if (!state.employeeList.length) {
        $roster.html('<div class="ot-roster-empty">' + ot_esc(__('No active employees found in this group.')) + '</div>');
        return;
    }

    const hidden = state.employeeList.filter(emp => ot_hidden_reason(state, emp.name));
    const hidden_note = hidden.length
        ? `<div class="ot-roster-hidden" title="${ot_esc(hidden.map(e =>
            e.name + ' ' + (e.employee_name || '') + ' — ' + ot_blocked_label(ot_hidden_reason(state, e.name))).join('\n'))}">
            ${ot_esc(__('{0} employee(s) hidden: maternity leave / pregnant from 7th month', [hidden.length]))}</div>`
        : '';
    const available = state.employeeList.filter(emp => !ot_hidden_reason(state, emp.name));
    if (!available.length) {
        $roster.html(hidden_note + '<div class="ot-roster-empty">' + ot_esc(__('No employees available for overtime.')) + '</div>');
        return;
    }

    const term = (state.searchTerm || '').trim().toLowerCase();
    const employees = !term ? available : available.filter(emp => {
        const empName = (emp.employee_name || emp.name || '').toLowerCase();
        const empId = (emp.name || '').toLowerCase();
        return empName.includes(term) || empId.includes(term);
    });

    if (!employees.length) {
        $roster.html('<div class="ot-roster-empty">' + ot_esc(__('No employees match your search criteria.')) + '</div>');
        return;
    }

    const all_visible_selected = employees.every(e => state.selectedEmployees.has(e.name));
    let html = `<div class="ot-roster-head">
        <label><input type="checkbox" class="ot-roster-all" ${all_visible_selected ? 'checked' : ''}> ${ot_esc(__('Select All'))}</label>
        <span class="ot-roster-count">${ot_esc(__('Showing {0} employee(s)', [employees.length]))}</span>
    </div>` + hidden_note;

    employees.forEach(emp => {
        const checked = state.selectedEmployees.has(emp.name);
        html += `<label class="ot-roster-row${checked ? ' checked' : ''}" data-emp="${ot_esc(emp.name)}">
            <input type="checkbox" class="ot-roster-check" ${checked ? 'checked' : ''}>
            <span class="ot-emp-id">${ot_highlight(emp.name, state.searchTerm)}</span>
            <span class="ot-emp-name">${ot_highlight(emp.employee_name || emp.name, state.searchTerm)}</span>
        </label>`;
    });
    $roster.html(html);

    $roster.find('.ot-roster-check').on('change', function () {
        const $row = $(this).closest('.ot-roster-row');
        const empId = $row.attr('data-emp');
        const emp = state.employeeList.find(e => e.name === empId);
        if (this.checked && emp) {
            state.selectedEmployees.set(emp.name, {
                name: emp.name,
                employee_name: emp.employee_name || emp.name,
                custom_group: emp.custom_group,
                status: 'Active'
            });
        } else {
            state.selectedEmployees.delete(empId);
        }
        $row.toggleClass('checked', this.checked);
        $roster.find('.ot-roster-all').prop('checked', employees.every(e => state.selectedEmployees.has(e.name)));
        update_ot_chips(frm);
    });

    $roster.find('.ot-roster-all').on('change', function () {
        const check = this.checked;
        employees.forEach(emp => {
            if (check) {
                state.selectedEmployees.set(emp.name, {
                    name: emp.name,
                    employee_name: emp.employee_name || emp.name,
                    custom_group: emp.custom_group,
                    status: 'Active'
                });
            } else {
                state.selectedEmployees.delete(emp.name);
            }
        });
        update_ot_roster(frm);
        update_ot_chips(frm);
    });
}

function update_ot_chips(frm) {
    const state = _get_dialog_state(frm);
    if (!state.currentDialog) return;
    const $wrap = state.currentDialog.get_field('team_html').$wrapper;

    $wrap.find('.ot-team-count').text(state.selectedEmployees.size);

    const $chips = $wrap.find('.ot-chips');
    if (!state.selectedEmployees.size) {
        $chips.html('<span class="ot-chips-empty">' + ot_esc(__('No employees selected')) + '</span>');
        return;
    }

    let html = '';
    state.selectedEmployees.forEach(emp => {
        html += `<span class="ot-chip"><span class="ot-chip-id">${ot_esc(emp.name)}</span> ${ot_esc(emp.employee_name || '')}
            <button type="button" data-remove="${ot_esc(emp.name)}"
                title="${ot_esc(__('Remove'))}" aria-label="${ot_esc(__('Remove'))} ${ot_esc(emp.name)}">×</button></span>`;
    });
    $chips.html(html);

    $chips.find('button[data-remove]').on('click', function () {
        state.selectedEmployees.delete($(this).attr('data-remove'));
        update_ot_roster(frm);
        update_ot_chips(frm);
    });
}

function inject_ot_ledger(frm) {
    const state = _get_dialog_state(frm);
    const $footer = state.currentDialog.$wrapper.find('.modal-footer').first();
    if ($footer.length && !$footer.find('.ot-footer-info').length) {
        $footer.prepend(`<div class="ot-footer-info">
            <div class="ot-session" aria-live="polite" style="display: none;"></div>
        </div>`);
    }
}

function on_dialog_group_changed(frm) {
    const state = _get_dialog_state(frm);
    const dialog = state.currentDialog;
    if (!dialog) return;

    const groupValue = dialog.get_value('selected_group');
    state.employeeList = [];

    if (!groupValue) {
        state.loadingEmployees = false;
        update_ot_roster(frm);
        return;
    }

    state.loadingEmployees = true;
    update_ot_roster(frm);

    const load_with_filters = (filters) => {
        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Employee',
                fields: ['name', 'employee_name', 'custom_group', 'department', 'custom_section', 'status'],
                filters: filters,
                order_by: 'name',
                limit_page_length: 500
            },
            callback: function (r) {
                // Ignore stale responses if the group changed while loading
                if (dialog.get_value('selected_group') !== groupValue) return;
                const list = r.message || [];
                const done = (blocked) => {
                    if (dialog.get_value('selected_group') !== groupValue) return;
                    state.otBlocked = blocked || {};
                    state.loadingEmployees = false;
                    state.employeeList = list;
                    update_ot_roster(frm);
                };
                if (!list.length) return done({});
                frappe.xcall(
                    'customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration.get_ot_blocked_employees',
                    { employees: list.map(e => e.name) }
                ).then(done).catch(() => {
                    done({});
                    frappe.show_alert({
                        message: __('Could not check maternity status — pregnant / maternity leave employees are not filtered'),
                        indicator: 'red'
                    }, 10);
                });
            },
            error: function () {
                state.loadingEmployees = false;
                state.employeeList = [];
                update_ot_roster(frm);
                frappe.show_alert({ message: __('Error loading employees'), indicator: 'red' });
            }
        });
    };

    const base_filters = { 'custom_group': groupValue, 'status': 'Active' };

    if (frm.doc.filter_employee_by) {
        get_user_filter_value(frm).then(({ filterBy, filterValue }) => {
            if (!filterValue) {
                state.loadingEmployees = false;
                update_ot_roster(frm);
                frappe.show_alert({
                    message: __('Current user does not have a valid {0} value', [filterBy]),
                    indicator: 'red'
                });
                return;
            }
            if (filterBy === 'custom_group' && groupValue !== filterValue) {
                state.loadingEmployees = false;
                update_ot_roster(frm);
                frappe.show_alert({
                    message: __('You can only select employees from your own group: {0}', [filterValue]),
                    indicator: 'red'
                });
                return;
            }
            const filters = Object.assign({}, base_filters);
            filters[filterBy] = filterValue;
            load_with_filters(filters);
        });
    } else {
        load_with_filters(base_filters);
    }
}

function clear_selected_employees(frm) {
    const state = _get_dialog_state(frm);
    if (state.selectedEmployees.size === 0) {
        frappe.show_alert({
            message: __('No employees selected to clear'),
            indicator: 'orange'
        });
        return;
    }

    frappe.confirm(__('Are you sure you want to clear all selected employees?'), () => {
        state.selectedEmployees.clear();
        update_ot_roster(frm);
        update_ot_chips(frm);
        frappe.show_alert({
            message: __('All selected employees cleared'),
            indicator: 'blue'
        });
    });
}

function save_overtime_registration_native(frm) {
    const state = _get_dialog_state(frm);
    const dialog = state.currentDialog;
    if (!dialog) return;

    if (state.selectedEmployees.size === 0) {
        frappe.show_alert({
            message: __('Please select at least one employee'),
            indicator: 'red'
        });
        return;
    }

    const selectedDays = ot_day_fields().filter(d => state.selectedDays.has(d));
    if (selectedDays.length === 0) {
        frappe.show_alert({
            message: __('Please select at least one day'),
            indicator: 'red'
        });
        return;
    }

    const reason = dialog.get_value('reason');
    if (!reason) {
        frappe.show_alert({
            message: __('Please enter a reason for overtime'),
            indicator: 'red'
        });
        return;
    }

    const begin_time = dialog.get_value('time_begin');
    const end_time = dialog.get_value('time_end');
    const begin_minutes = ot_time_to_minutes(begin_time);
    const end_minutes = ot_time_to_minutes(end_time);
    if (begin_minutes === null || end_minutes === null || begin_minutes >= end_minutes) {
        frappe.show_alert({
            message: __('Begin Time must be before End Time'),
            indicator: 'red'
        });
        return;
    }

    const monday = ot_monday_of_week(state.weekOffset);
    const day_fields = ot_day_fields();
    const duration_hours = (end_minutes - begin_minutes) / 60;

    // Conflict = same employee + same date + identical/overlapping time vs an
    // existing row (earlier batch, manual entry, saved data): the user chooses
    // to replace the old rows or keep them. Adjacent times are not a conflict.
    const existing_rows = (frm.doc.ot_employees || [])
        .filter(d => d.employee && d.date && d.begin_time && d.end_time);
    const clean = [];
    const conflicts = [];
    state.selectedEmployees.forEach(employee => {
        selectedDays.forEach(day => {
            const date = new Date(monday);
            date.setDate(monday.getDate() + day_fields.indexOf(day));
            const date_str = ot_format_ymd(date);
            const matches = existing_rows.filter(d => d.employee === employee.name
                && d.date === date_str
                && times_overlap(begin_time, end_time, d.begin_time, d.end_time));
            if (matches.length) {
                conflicts.push({ employee: employee, date: date_str, matches: matches });
            } else {
                clean.push({ employee: employee, date: date_str });
            }
        });
    });

    const commit_batch = function (extra, remove_names, replaced_count) {
        const to_add = clean.concat(extra);
        if (!to_add.length) return;

        if (remove_names.size) {
            frm.doc.ot_employees = (frm.doc.ot_employees || []).filter(d => !remove_names.has(d.name));
        }

        const row_names = [];
        const added_employees = new Set();
        const added_dates = new Set();
        to_add.forEach(c => {
            const child = frm.add_child('ot_employees');
            child.employee = c.employee.name;
            child.employee_name = c.employee.employee_name || c.employee.name;
            if (c.employee.custom_group) {
                child.group = c.employee.custom_group;
            }
            child.date = c.date;
            child.begin_time = begin_time;
            child.end_time = end_time;
            child.reason = reason;
            row_names.push(child.name);
            added_employees.add(c.employee.name);
            added_dates.add(c.date);
        });

        frm.refresh_field('ot_employees');

        // Batch mode: stay open for the next batch without re-picking the group.
        // Days and employee selection reset; time + reason stay.
        state.addedBatches.push({
            rows: row_names,
            employees: added_employees.size,
            days: added_dates.size,
            man_hours: row_names.length * duration_hours
        });
        state.selectedDays.clear();
        state.selectedEmployees.clear();
        render_ot_day_tiles(frm);
        update_ot_roster(frm);
        update_ot_chips(frm);
        update_ot_session(frm);
        // On phones the day tiles are far above the roster — bring them back
        // into view for the next batch
        if (window.matchMedia('(max-width: 767px), (pointer: coarse)').matches) {
            state.currentDialog.$wrapper.animate({ scrollTop: 0 }, 200);
        }

        frappe.show_alert({
            message: __('Successfully added {0} employee(s) for {1} day(s)', [added_employees.size, added_dates.size]),
            indicator: 'green'
        });
        if (replaced_count) {
            frappe.show_alert({
                message: __('Replaced {0} existing row(s)', [replaced_count]),
                indicator: 'blue'
            });
        }
    };

    if (!conflicts.length) {
        commit_batch([], new Set(), 0);
        return;
    }

    const new_time = String(begin_time).slice(0, 5) + '-' + String(end_time).slice(0, 5);
    const items = conflicts.map(c => c.matches.map(m =>
        '<li><b>' + ot_esc(c.employee.name) + '</b> ' + ot_esc(c.employee.employee_name || '')
        + ' — ' + frappe.datetime.str_to_user(c.date) + ': '
        + __('old row #{0} ({1}-{2}) → new {3}', [
            m.idx,
            String(m.begin_time || '').slice(0, 5),
            String(m.end_time || '').slice(0, 5),
            new_time
        ])
        + '</li>').join('')).join('');

    frappe.confirm(
        '<p>' + __('{0} entry(ies) overlap existing rows (same employee, same date, same/overlapping time):', [conflicts.length]) + '</p>'
        + '<ul>' + items + '</ul>'
        + '<p><b>' + __('Replace the old row(s) with the new time?') + '</b></p>',
        function () {
            const remove_names = new Set();
            conflicts.forEach(c => c.matches.forEach(m => remove_names.add(m.name)));
            commit_batch(
                conflicts.map(c => ({ employee: c.employee, date: c.date })),
                remove_names,
                remove_names.size
            );
        },
        function () {
            if (clean.length) {
                commit_batch([], new Set(), 0);
            }
            frappe.show_alert({
                message: __('Kept existing rows — skipped {0} entry(ies)', [conflicts.length]),
                indicator: 'orange'
            });
        }
    );
}

function update_ot_session(frm) {
    const state = _get_dialog_state(frm);
    if (!state.currentDialog) return;
    const $session = state.currentDialog.$wrapper.find('.ot-session');
    if (!$session.length) return;

    if (!state.addedBatches.length) {
        $session.hide().empty();
        return;
    }

    const total_rows = state.addedBatches.reduce((sum, b) => sum + b.rows.length, 0);
    const total_hours = state.addedBatches.reduce((sum, b) => sum + b.man_hours, 0);
    $session.show().html(
        '<span>✓ ' + __('{0} batch(es) added · {1} row(s) · {2} man-hours', [
            '<b>' + state.addedBatches.length + '</b>',
            '<b>' + total_rows + '</b>',
            '<b>' + ot_num(total_hours) + '</b>'
        ]) + '</span>'
        + '<button type="button" class="ot-linkbtn ot-undo-batch">' + ot_esc(__('Undo last batch')) + '</button>'
    );
    $session.find('.ot-undo-batch').on('click', function () {
        undo_last_ot_batch(frm);
    });
}

function undo_last_ot_batch(frm) {
    const state = _get_dialog_state(frm);
    const batch = state.addedBatches.pop();
    if (!batch) return;

    const names = new Set(batch.rows);
    frm.doc.ot_employees = (frm.doc.ot_employees || []).filter(d => !names.has(d.name));
    frm.refresh_field('ot_employees');
    update_ot_session(frm);

    frappe.show_alert({
        message: __('Removed last batch ({0} row(s))', [batch.rows.length]),
        indicator: 'blue'
    });
}

// Pivot view: rows = employees, columns = dates, cells = time ranges.
// Reads the current (possibly unsaved) child table, so it also works while composing.
function show_ot_pivot_dialog(frm) {
    ensure_ot_dialog_styles();

    const entries = (frm.doc.ot_employees || []).filter(d => d.employee && d.date);
    if (!entries.length) {
        frappe.show_alert({
            message: __('No overtime entries yet'),
            indicator: 'orange'
        });
        return;
    }

    const dates = Array.from(new Set(entries.map(d => d.date))).sort();
    const byEmployee = new Map();
    entries.forEach(d => {
        if (!byEmployee.has(d.employee)) {
            byEmployee.set(d.employee, {
                employee_name: d.employee_name,
                group: d.group,
                cells: {},
                total: 0
            });
        }
        const emp = byEmployee.get(d.employee);
        const begin = ot_time_to_minutes(d.begin_time);
        const end = ot_time_to_minutes(d.end_time);
        const hours = (begin !== null && end !== null && end > begin) ? (end - begin) / 60 : 0;
        if (!emp.cells[d.date]) emp.cells[d.date] = [];
        emp.cells[d.date].push({
            time: (d.begin_time && d.end_time)
                ? '<span class="ot-t">' + ot_esc(String(d.begin_time).slice(0, 5)) + '</span>'
                + '<span class="ot-t-dash">-</span>'
                + '<span class="ot-t">' + ot_esc(String(d.end_time).slice(0, 5)) + '</span>'
                : '',
            hours: hours,
            reason: d.reason || ''
        });
        emp.total += hours;
    });

    const dayNames = [__('Sun'), __('Mon'), __('Tue'), __('Wed'), __('Thu'), __('Fri'), __('Sat')];
    const colTotals = {};
    let grand = 0;

    let head = '<tr><th class="ot-pivot-no">' + ot_esc(__('No.', null, 'OT summary row number')) + '</th>'
        + '<th class="ot-pivot-emp">' + ot_esc(__('Employee')) + '</th>'
        + '<th class="ot-pivot-grp">' + ot_esc(__('Group')) + '</th>'
        + '<th class="ot-pivot-note-h">' + ot_esc(__('Note', null, 'OT summary maternity note')) + '</th>';
    dates.forEach(dt => {
        const dobj = new Date(dt);
        head += '<th>' + ot_esc(dayNames[dobj.getDay()]) + '<br>' + ot_format_dm(dobj) + '</th>';
        colTotals[dt] = 0;
    });
    head += '<th>' + ot_esc(__('Total (h)')) + '</th></tr>';

    let body = '';
    Array.from(byEmployee.keys()).sort().forEach((empId, idx) => {
        const emp = byEmployee.get(empId);
        body += '<tr><td class="ot-pivot-no">' + (idx + 1) + '</td>'
            + '<td class="ot-pivot-emp"><b class="ot-pivot-id">' + ot_esc(empId) + '</b> '
            + '<span class="ot-pivot-name">' + ot_esc(emp.employee_name || '') + '</span></td>'
            + '<td class="ot-pivot-grp">' + ot_esc(emp.group || '') + '</td>'
            + '<td class="ot-pivot-note" data-emp="' + ot_esc(empId) + '"></td>';
        dates.forEach(dt => {
            const cell = emp.cells[dt];
            if (cell && cell.length) {
                const reasons = cell.map(c => c.reason).filter(Boolean).join('; ');
                body += '<td class="ot-pivot-on" title="' + ot_esc(reasons) + '">'
                    + cell.map(c => '<div class="ot-slot">' + c.time + '</div>').join('') + '</td>';
                colTotals[dt] += cell.reduce((sum, c) => sum + c.hours, 0);
            } else {
                body += '<td class="ot-pivot-off">–</td>';
            }
        });
        grand += emp.total;
        body += '<td class="ot-pivot-total">' + ot_num(emp.total) + '</td></tr>';
    });

    // One cell per leading column (no colspan): columns hidden on phones
    // would otherwise shift the totals under the wrong dates
    let foot = '<tr class="ot-pivot-footrow"><td class="ot-pivot-no"></td>'
        + '<td class="ot-pivot-emp">' + ot_esc(__('Total (h)')) + '</td>'
        + '<td class="ot-pivot-grp"></td><td class="ot-pivot-note-h"></td>';
    dates.forEach(dt => {
        foot += '<td>' + ot_num(colTotals[dt]) + '</td>';
    });
    foot += '<td class="ot-pivot-total">' + ot_num(grand) + '</td></tr>';

    const summary = __('{0} employee(s) · {1} day(s) · {2} row(s)',
        [byEmployee.size, dates.length, entries.length]);

    const dialog = new frappe.ui.Dialog({
        title: __('Summary Table') + (frm.doc.name ? ' — ' + frm.doc.name : ''),
        size: 'extra-large',
        fields: [{ fieldtype: 'HTML', fieldname: 'pivot_html' }]
    });
    dialog.show();
    dialog.$wrapper.addClass('ot-reg-modal');
    dialog.get_field('pivot_html').$wrapper.html(
        '<div class="ot-pivot-summary">' + ot_esc(summary) + '</div>'
        + '<div class="ot-pivot"><table><thead>' + head + '</thead><tbody>' + body + foot + '</tbody></table></div>'
    );

    // Note column: employees who finish the shift early (pregnant / maternity leave /
    // young child) on at least one of the pivot's OT dates — same rule as the
    // pre-save check (server: get_ot_maternity_benefits). Filled asynchronously.
    frappe.xcall(
        'customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration.get_ot_maternity_benefits',
        { employees: Array.from(byEmployee.keys()), dates: dates }
    ).then(res => {
        const by_emp = (res && res.employees) || {};
        const early = __('Shift ends {0} hour(s) early', [ot_num(flt((res && res.hours) || 1))]);
        const icons = {
            'Pregnant': ['\u{1F930}', __('Pregnant')],
            'Maternity Leave': ['\u{1F931}', __('Maternity Leave')],
            'Young Child': ['\u{1F476}', __('Young child under 12 months')]
        };
        dialog.$wrapper.find('.ot-pivot-note').each(function () {
            const phases = by_emp[$(this).attr('data-emp')];
            if (!phases) return;
            $(this).html(phases.filter(p => icons[p]).map(p =>
                '<span title="' + ot_esc(icons[p][1] + ' — ' + early) + '">' + icons[p][0] + '</span>'
            ).join(' '));
        });
    }).catch(() => { /* API error — leave the notes empty, the table still works */ });
}


// Validation functions
function validate_required_fields(frm) {
    let hasErrors = false;

    for (let d of frm.doc.ot_employees || []) {
        if (!d.date || !d.begin_time || !d.end_time) {
            frappe.msgprint(__(`Row #{0}: Employee, Date, Begin Time, and End Time are required.`, [d.idx]));
            hasErrors = true;
        }
    }

    if (hasErrors) {
        frappe.validated = false;
        return false;
    }
    return true;
}

// Validate time order: begin_time < end_time
function validate_time_order(frm) {
    for (let d of frm.doc.ot_employees || []) {
        if (d.begin_time && d.end_time) {
            // Convert time strings to Date objects for proper comparison
            const time_begin = new Date(`2000-01-01T${d.begin_time}`);
            const time_end = new Date(`2000-01-01T${d.end_time}`);

            if (time_begin >= time_end) {

                frappe.msgprint(__('Row #{0}: Begin Time ({1}) must be before End Time ({2})', [d.idx, d.begin_time, d.end_time]));
                frappe.validated = false;
                return false;
            }
        }
    }
    return true;
}

// Validate duplicate rows within form (same employee, date, time)
function validate_duplicate_rows(frm) {
    const entries = [];

    for (let d of frm.doc.ot_employees || []) {
        if (!d.employee || !d.date || !d.begin_time || !d.end_time) {
            continue;
        }

        entries.push({
            idx: d.idx,
            employee: d.employee,
            employee_name: d.employee_name,
            date: d.date,
            begin_time: d.begin_time,
            end_time: d.end_time
        });
    }

    // Check for duplicates
    for (let i = 0; i < entries.length; i++) {
        for (let j = i + 1; j < entries.length; j++) {
            const entry1 = entries[i];
            const entry2 = entries[j];

            // Same employee and date
            if (entry1.employee === entry2.employee && entry1.date === entry2.date) {
                // Check for exact match or time overlap
                if (times_overlap(entry1.begin_time, entry1.end_time, entry2.begin_time, entry2.end_time)) {
                    frappe.msgprint(__('Rows {0} and {1}: Duplicate OT for employee {2} on {3}',
                        [entry1.idx, entry2.idx, entry1.employee_name, entry1.date]));
                    frappe.validated = false;
                    return false;
                }
            }
        }
    }
    return true;
}

// Validate that each employee has only one post-shift OT entry per day in this form
// Multiple entries should be combined into one continuous entry
function validate_single_post_shift_entry(frm) {
    // Group entries by employee and date
    const employee_date_entries = {};

    for (let d of frm.doc.ot_employees || []) {
        if (!d.employee || !d.date || !d.begin_time || !d.end_time) {
            continue;
        }

        const key = `${d.employee}_${d.date}`;
        if (!employee_date_entries[key]) {
            employee_date_entries[key] = [];
        }
        employee_date_entries[key].push({
            idx: d.idx,
            employee: d.employee,
            employee_name: d.employee_name,
            date: d.date,
            begin_time: d.begin_time,
            end_time: d.end_time
        });
    }

    // Check each employee-date group
    for (let key in employee_date_entries) {
        const entries = employee_date_entries[key];

        // If only one entry, no need to check
        if (entries.length <= 1) {
            continue;
        }

        // If multiple entries, they should all be continuous (handled by Python validation)
        // But we should warn that multiple entries for same employee should be combined
        const rows = entries.map(e => e.idx).join(', ');
        const employee_name = entries[0].employee_name;
        const date = entries[0].date;

        frappe.msgprint({
            title: __('Warning'),
            message: __('Rows {0}: Employee {1} has {2} OT entries on {3}. Combine them into one continuous entry.',
                [rows, employee_name, entries.length, frappe.datetime.str_to_user(date)]),
            indicator: 'orange'
        });
        frappe.validated = false;
        return false;
    }

    return true;
}

// Dead code removed: validate_ot_continuity was not called from form validate method


function check_all_before_save(frm) {
    // Results are matched back to the ROW OBJECTS captured here, never to the grid
    // idx: Frappe renumbers idx when a row is removed (OTR-261112-0002, 12/11/2026 —
    // an empty top row was removed asynchronously after this list was sent, every
    // idx shifted by one and the 1-hour move landed on the wrong employee/day).
    const rows_to_check = (frm.doc.ot_employees || [])
        .filter(d => d.employee && d.date && d.begin_time && d.end_time);
    const entries_to_check = rows_to_check.map((d, i) => ({
            idx: i + 1,   // position key into rows_to_check — echoed back by the server
            employee: d.employee,
            employee_name: d.employee_name,
            date: d.date,
            begin_time: d.begin_time,
            end_time: d.end_time
        }));

    if (entries_to_check.length === 0) {
        frm.pre_save_check_done = true;
        frm.save();
        return;
    }

    Promise.all([
        frappe.xcall(
            'customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration.check_employees_with_maternity_benefits',
            { entries: entries_to_check }
        ),
        frappe.xcall(
            'customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration.check_overtime_conflicts',
            { entries: entries_to_check, current_doc_name: frm.doc.name || 'new' }
        )
    ]).then(([maternity_raw, conflict_raw]) => {
        // _row = the form row; idx = its CURRENT row number (for display)
        const bind = list => (list || []).map(r => {
            const row = rows_to_check[r.idx - 1];
            return row ? Object.assign({}, r, { _row: row, idx: row.idx }) : null;
        }).filter(Boolean);
        const maternity_results = bind(maternity_raw);
        const conflict_results = bind(conflict_raw);
        const has_maternity = maternity_results.length > 0;
        const has_conflicts = conflict_results.length > 0;

        if (!has_maternity && !has_conflicts) {
            frm.pre_save_check_done = true;
            frm.save();
            return;
        }

        show_ot_precheck_dialog(frm, has_maternity ? maternity_results : [], has_conflicts ? conflict_results : []);
    }).catch((e) => {
        console.error('Pre-save check failed — saving without it', e);
        frm.pre_save_check_done = true;
        frm.save();
    });
}

// ── Pre-save check dialog (thiết kế lại 12/11/2026) ─────────────────────────
// Thai sản / con nhỏ: chọn cách lùi giờ tăng ca bằng 3 thẻ, mỗi thẻ có dải thời
// gian minh hoạ (lấy dòng đầu làm ví dụ); bảng NV bên dưới đổi cột "Sau khi lưu"
// theo lựa chọn. Mặc định 'start' = chỉ dời giờ bắt đầu (user chốt 12/11/2026).

function ot_hm(minutes) {
    const m = ((Math.round(minutes) % 1440) + 1440) % 1440;
    return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
}

// OT of one flagged row after `mode` — minutes since midnight
function ot_precheck_result(row, mode) {
    const begin = ot_time_to_minutes(row.begin_time);
    const end = ot_time_to_minutes(row.end_time);
    const move = Math.round((row.adjust_hours || 1) * 60);
    // Chỉ 2 cách (user chốt 12/11/2026): tăng ca PHẢI liền ngay giờ hết ca đã giảm
    if (mode === 'both') return { begin: begin - move, end: end - move };
    return { begin: begin - move, end: end };   // 'start'
}

// Dải thời gian: [giờ làm][tăng ca] với mốc giờ bên dưới
function ot_precheck_timeline(row, mode) {
    const r = ot_precheck_result(row, mode);
    const work_end = ot_time_to_minutes(row.adjusted_shift_end);
    const from = work_end - 60;
    const to = Math.max(ot_time_to_minutes(row.end_time), r.end) + 30;
    const pos = m => ((m - from) / (to - from) * 100).toFixed(2);
    const seg = (a, b, cls) =>
        `<span class="otp-seg ${cls}" style="left:${pos(a)}%;width:${(pos(b) - pos(a)).toFixed(2)}%"></span>`;
    const tick = m => `<span class="otp-tick" style="left:${pos(m)}%">${ot_hm(m)}</span>`;

    const bar = seg(from, work_end, 'otp-work') + seg(r.begin, r.end, 'otp-ot');
    const ticks = [work_end, r.end];
    return `<div class="otp-tl" aria-hidden="true"><div class="otp-bar">${bar}</div>
        <div class="otp-ticks">${ticks.map(tick).join('')}</div></div>`;
}

function ensure_ot_precheck_styles() {
    if (document.getElementById('ot-precheck-css')) return;
    const style = document.createElement('style');
    style.id = 'ot-precheck-css';
    style.textContent = `
.otp-modal {
    --otp-accent: #b45309;
    --otp-accent-text: #92400e;
    --otp-wash: #fdf3e0;
    --otp-wash-border: #ecd3a4;
    --otp-work: #cbd5e1;
    --otp-ot: #d97706;
    --otp-danger: #dc2626;
}
html[data-theme="dark"] .otp-modal,
html[data-theme-mode="dark"] .otp-modal {
    --otp-accent: #f5b83d;
    --otp-accent-text: #f7c96b;
    --otp-wash: rgba(245, 184, 61, 0.12);
    --otp-wash-border: rgba(245, 184, 61, 0.45);
    --otp-work: rgba(255, 255, 255, 0.22);
    --otp-ot: #f5a524;
    --otp-danger: #f87171;
}
.otp-modal .modal-dialog { max-width: min(860px, calc(100vw - 24px)); }
.otp { color: var(--text-color); font-size: 14px; }
.otp-section + .otp-section { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border-color); }
.otp-title { font-size: 16px; font-weight: 600; margin: 0 0 4px; display: flex; gap: 8px; align-items: baseline; }
.otp-lead { color: var(--text-muted); margin: 0 0 14px; line-height: 1.45; }
.otp-lead b { color: var(--text-color); }
.otp-step { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
    color: var(--text-muted); margin: 14px 0 8px; display: flex; gap: 8px; align-items: center; }
.otp-step-no { display: inline-flex; width: 20px; height: 20px; border-radius: 50%; align-items: center;
    justify-content: center; background: var(--otp-accent); color: #fff; font-size: 11px; }
html[data-theme="dark"] .otp-step-no, html[data-theme-mode="dark"] .otp-step-no { color: #1c1c1c; }
.otp-example { font-size: 12px; color: var(--text-muted); margin: -2px 0 10px; }
.otp-legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 12px; color: var(--text-muted); margin-bottom: 10px; }
.otp-legend i { display: inline-block; width: 14px; height: 10px; border-radius: 3px; margin-right: 5px; vertical-align: -1px; }
.otp-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
.otp-card { position: relative; display: block; margin: 0; cursor: pointer; border: 1.5px solid var(--border-color);
    border-radius: 10px; padding: 12px 12px 10px; background: var(--card-bg, transparent); }
.otp-card:hover { border-color: var(--otp-wash-border); }
.otp-card input { position: absolute; opacity: 0; pointer-events: none; }
.otp-card.selected { border-color: var(--otp-accent); background: var(--otp-wash); }
.otp-card:focus-within { outline: 2px solid var(--otp-accent); outline-offset: 2px; }
.otp-card-head { display: flex; gap: 8px; align-items: flex-start; font-weight: 600; line-height: 1.3; }
.otp-dot { flex: 0 0 auto; width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--text-muted); margin-top: 1px; }
.otp-card.selected .otp-dot { border-color: var(--otp-accent); box-shadow: inset 0 0 0 3px var(--card-bg, #fff); background: var(--otp-accent); }
.otp-tag { font-size: 11px; font-weight: 600; color: var(--otp-accent-text); background: var(--otp-wash);
    border: 1px solid var(--otp-wash-border); border-radius: 999px; padding: 0 7px; margin-left: auto; white-space: nowrap; }
.otp-tl { margin: 12px 2px 4px; }
.otp-bar { position: relative; height: 16px; border-radius: 4px; background: transparent; }
.otp-seg { position: absolute; top: 0; bottom: 0; }
.otp-seg.otp-work { background: var(--otp-work); border-radius: 4px 0 0 4px; }
.otp-seg.otp-ot { background: var(--otp-ot); border-radius: 0 4px 4px 0; }
.otp-ticks { position: relative; height: 18px; font-size: 11px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
.otp-tick { position: absolute; top: 3px; transform: translateX(-50%); white-space: nowrap; }
.otp-result { margin-top: 6px; font-weight: 600; font-variant-numeric: tabular-nums; }
.otp-note { font-size: 12px; color: var(--text-muted); margin-top: 2px; line-height: 1.35; }
.otp-table-wrap { overflow-x: auto; border: 1px solid var(--border-color); border-radius: 8px; }
.otp-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.otp-table th { text-align: left; font-weight: 600; font-size: 12px; color: var(--text-muted);
    background: var(--subtle-fg, transparent); padding: 6px 10px; border-bottom: 1px solid var(--border-color); white-space: nowrap; }
.otp-table td { padding: 7px 10px; border-bottom: 1px solid var(--border-color); vertical-align: top; }
.otp-table tr:last-child td { border-bottom: 0; }
.otp-table .otp-num { font-variant-numeric: tabular-nums; white-space: nowrap; }
.otp-table .otp-changed { font-weight: 600; color: var(--otp-accent-text); }
.otp-badge { display: block; font-size: 12px; color: var(--text-muted); margin-top: 2px; white-space: normal; }
.otp-table td.otp-num { white-space: normal; }
.otp-after { display: block; margin-top: 2px; }
.otp-conflict-title { color: var(--otp-danger); }
.otp-muted { color: var(--text-muted); font-size: 12px; }
.otp-conflicts { display: flex; flex-direction: column; gap: 10px; }
.otp-conflict { border: 1px solid var(--border-color); border-radius: 10px; padding: 10px 12px; }
.otp-conflict-head { display: flex; gap: 8px; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; }
.otp-conflict-head .otp-muted { margin-left: 4px; }
.otp-conflict-times { margin: 6px 0 8px; line-height: 1.5; }
.otp-tag-duplicate, .otp-tag-covered { color: var(--otp-danger); border-color: currentColor; background: transparent; }
.otp-choices { display: flex; flex-wrap: wrap; gap: 6px; }
.otp-choice { position: relative; margin: 0; cursor: pointer; border: 1.5px solid var(--border-color);
    border-radius: 999px; padding: 4px 12px; font-size: 13px; font-weight: 500; }
.otp-choice input { position: absolute; opacity: 0; pointer-events: none; }
.otp-choice.selected { border-color: var(--otp-accent); background: var(--otp-wash); color: var(--otp-accent-text); }
.otp-choice:focus-within { outline: 2px solid var(--otp-accent); outline-offset: 2px; }
@media (max-width: 575px) {
    .otp-cards { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: no-preference) {
    .otp-card { transition: border-color 0.12s ease, background-color 0.12s ease; }
}
`;
    document.head.appendChild(style);
}

// Bước 1 trùng phiếu khác → bước 2 lùi giờ thai sản → lưu 1 lần (user chốt 12/11/2026).
function show_ot_precheck_dialog(frm, maternity_rows, conflict_rows) {
    ensure_ot_precheck_styles();
    const total_steps = (conflict_rows.length ? 1 : 0) + (maternity_rows.length ? 1 : 0);
    const save = () => {
        frm.pre_save_check_done = true;
        frm.save();
    };
    const open_maternity = () => {
        // Re-read the rows after step 1: deleted rows drop out, a shortened row that no
        // longer starts at the normal shift end needs no move, end times may have changed.
        const rows = frm.doc.ot_employees || [];
        const remaining = maternity_rows
            .filter(m => rows.includes(m._row)
                && ot_time_to_minutes(m._row.begin_time) === ot_time_to_minutes(m.shift_end))
            .map(m => Object.assign({}, m, {
                idx: m._row.idx, begin_time: m._row.begin_time, end_time: m._row.end_time
            }));
        if (!remaining.length) return save();
        show_ot_maternity_step(frm, remaining, total_steps, save);
    };
    if (conflict_rows.length) {
        show_ot_conflict_step(frm, conflict_rows, total_steps, maternity_rows.length > 0, open_maternity);
    } else {
        open_maternity();
    }
}

function ot_precheck_title(step, total_steps) {
    return total_steps > 1
        ? __('Pre-save check') + ' · ' + __('Step {0} of {1}', [step, total_steps])
        : __('Pre-save check');
}

function ot_precheck_dialog(title, html, primary_label, on_primary) {
    const dialog = new frappe.ui.Dialog({
        title: title,
        size: 'large',
        fields: [{ fieldtype: 'HTML', fieldname: 'body_html' }],
        primary_action_label: primary_label,
        primary_action: function () {
            dialog.hide();
            on_primary();
        },
        secondary_action_label: __('Back to edit'),
        secondary_action: function () {
            dialog.hide();   // user reviews manually, nothing saved
        }
    });
    dialog.$wrapper.addClass('otp-modal');
    const $body = dialog.get_field('body_html').$wrapper;
    $body.html(html);
    dialog.show();
    return { dialog, $body };
}

// Phần của dòng này CHƯA nằm trong các dòng đã đăng ký ở phiếu khác (phút).
// kind: 'duplicate' = trùng y hệt 1 dòng; 'covered' = bị phủ hết; 'trim' = còn phần trống.
function ot_conflict_plan(from, to, existing) {
    const exact = existing.some(([a, b]) => a === from && b === to);
    let free = [[from, to]];
    existing.forEach(([a, b]) => {
        free = free.flatMap(([x, y]) => {
            if (b <= x || a >= y) return [[x, y]];
            const out = [];
            if (a > x) out.push([x, a]);
            if (b < y) out.push([b, y]);
            return out;
        });
    });
    if (exact) return { kind: 'duplicate', suggestion: null };
    if (!free.length) return { kind: 'covered', suggestion: null };
    // one row per employee/day in this form → keep the longest free part (earlier on a tie)
    const best = free.reduce((p, c) => (c[1] - c[0] > p[1] - p[0] ? c : p));
    return { kind: 'trim', suggestion: best };
}

function show_ot_conflict_step(frm, conflict_rows, total_steps, has_next, on_done) {
    const span = (a, b) => ot_hm(a) + ' – ' + ot_hm(b);
    const fmt_date = d => frappe.datetime.str_to_user(d);
    const row_label = __('Row', null, 'OT row number');

    // one group per row of this form (a row can overlap several rows elsewhere)
    const groups = [];
    conflict_rows.forEach(c => {
        let g = groups.find(x => x.row === c._row);
        if (!g) {
            g = { row: c._row, info: c, others: [] };
            groups.push(g);
        }
        g.others.push(c);
    });
    groups.forEach((g, i) => {
        g.key = 'g' + i;
        g.from = ot_time_to_minutes(g.info.current_from);
        g.to = ot_time_to_minutes(g.info.current_to);
        g.plan = ot_conflict_plan(g.from, g.to, g.others.map(o =>
            [ot_time_to_minutes(o.existing_from), ot_time_to_minutes(o.existing_to)]));
        g.action = g.plan.kind === 'trim' ? 'change' : 'delete';
    });

    const kind_label = {
        duplicate: __('Exact duplicate'),
        covered: __('Already fully registered'),
        trim: __('Partly overlaps')
    };
    const choice = (g, value, label) => `<label class="otp-choice${g.action === value ? ' selected' : ''}">
        <input type="radio" name="otp-${g.key}" value="${value}" data-key="${g.key}"${g.action === value ? ' checked' : ''}>${label}</label>`;

    const html = `<div class="otp"><div class="otp-section">
        <p class="otp-title otp-conflict-title">${__('{0} row(s) overlap overtime already registered in another form', [groups.length])}</p>
        <p class="otp-lead">${__('Exact duplicates are deleted by default. Overlapping rows are changed to the part that is not registered yet.')}</p>
        <div class="otp-conflicts">${groups.map(g => `
            <div class="otp-conflict">
                <div class="otp-conflict-head">
                    <span><b>${row_label} ${g.row.idx}</b> · <b>${ot_esc(g.info.employee_name || '')}</b>
                        <span class="otp-muted">${ot_esc(g.info.employee)} · ${fmt_date(g.info.date)}</span></span>
                    <span class="otp-tag otp-tag-${g.plan.kind}">${kind_label[g.plan.kind]}</span>
                </div>
                <div class="otp-conflict-times">
                    <div>${__('This form')}: <b class="otp-num">${span(g.from, g.to)}</b></div>
                    ${g.others.map(o => `<div class="otp-muted">${__('Already registered in {0}, row {1}: {2}', [
                        `<a href="/app/overtime-registration/${encodeURIComponent(o.existing_doc)}" target="_blank">${ot_esc(o.existing_doc)}</a>`,
                        o.existing_idx,
                        '<span class="otp-num">' + span(ot_time_to_minutes(o.existing_from), ot_time_to_minutes(o.existing_to)) + '</span>'
                    ])}</div>`).join('')}
                </div>
                <div class="otp-choices">
                    ${g.plan.suggestion ? choice(g, 'change', __('Change to {0}', ['<b class="otp-num">' + span(g.plan.suggestion[0], g.plan.suggestion[1]) + '</b>'])) : ''}
                    ${choice(g, 'delete', __('Delete this row'))}
                    ${choice(g, 'keep', __('Keep as is'))}
                </div>
            </div>`).join('')}
        </div>
    </div></div>`;

    const { $body } = ot_precheck_dialog(ot_precheck_title(1, total_steps), html,
        has_next ? __('Continue') : __('Save'),
        () => {
            const hm = m => ot_hm(m) + ':00';
            groups.forEach(g => {
                if (g.action === 'delete') {
                    frappe.model.clear_doc(g.row.doctype, g.row.name);   // renumbers idx synchronously
                } else if (g.action === 'change' && g.plan.suggestion) {
                    g.row.begin_time = hm(g.plan.suggestion[0]);
                    g.row.end_time = hm(g.plan.suggestion[1]);
                }
            });
            frm.refresh_field('ot_employees');
            on_done();
        });

    $body.on('change', '.otp-choices input', function () {
        const g = groups.find(x => x.key === $(this).attr('data-key'));
        g.action = this.value;
        $(this).closest('.otp-choices').find('.otp-choice').each(function () {
            $(this).toggleClass('selected', $(this).find('input').val() === g.action);
        });
    });
}

function show_ot_maternity_step(frm, maternity_rows, total_steps, on_done) {
    const state = { mode: 'start' };
    const benefit_label = {
        'Pregnant': '\u{1F930} ' + __('Pregnant'),
        'Young Child': '\u{1F476} ' + __('Young Child'),
        'Maternity Leave': '\u{1F931} ' + __('Maternity Leave')
    };
    const fmt_date = d => frappe.datetime.str_to_user(d);
    const span = (a, b) => ot_hm(a) + ' – ' + ot_hm(b);
    const hours = (a, b) => ot_num((b - a) / 60);

    const ex = maternity_rows[0];
    const move_h = ot_num(ex.adjust_hours || 1);
    const same_shift = maternity_rows.every(r => r.shift_end === ex.shift_end);
    const reduced_end_b = '<b>' + ot_esc(ex.adjusted_shift_end) + '</b>';
    const shift_end_b = '<b>' + ot_esc(ex.shift_end) + '</b>';
    const lead = same_shift
        ? __('Their shift ends at {0} instead of {1}, so their overtime must start at {0}.', [reduced_end_b, shift_end_b])
        : __('Their shift ends {0} hour(s) earlier, so their overtime must start right after it.', [move_h]);

    const card = (mode, title, note, tag) => {
        const r = ot_precheck_result(ex, mode);
        return `<label class="otp-card${mode === state.mode ? ' selected' : ''}" data-mode="${mode}">
            <input type="radio" name="otp-mode" value="${mode}"${mode === state.mode ? ' checked' : ''}>
            <div class="otp-card-head"><span class="otp-dot"></span><span>${title}</span>${tag ? `<span class="otp-tag">${tag}</span>` : ''}</div>
            ${ot_precheck_timeline(ex, mode)}
            <div class="otp-result">${__('Overtime')} ${span(r.begin, r.end)} · ${__('{0} h', [hours(r.begin, r.end)])}</div>
            <div class="otp-note">${note}</div>
        </label>`;
    };

    const html = `<div class="otp"><div class="otp-section">
        <p class="otp-title">${__('{0} employee(s) finish their shift {1} hour(s) early', [new Set(maternity_rows.map(r => r.employee)).size, move_h])}</p>
        <p class="otp-lead">${__('Pregnant / young child')}: ${lead}</p>

        <div class="otp-step"><span class="otp-step-no">1</span>${__('Choose how to move their overtime')}</div>
        <div class="otp-example">${__('Illustration: row {0} — {1}, overtime entered {2}', [ex.idx, ot_esc(ex.employee_name || ex.employee), span(ot_time_to_minutes(ex.begin_time), ot_time_to_minutes(ex.end_time))])}</div>
        <div class="otp-legend">
            <span><i style="background:var(--otp-work)"></i>${__('Working hours')}</span>
            <span><i style="background:var(--otp-ot)"></i>${__('Overtime')}</span>
        </div>
        <div class="otp-cards">
            ${card('start', __('Move start time only'),
                __('Goes home with the team. Overtime is {0} hour(s) longer.', [move_h]), __('Default'))}
            ${card('both', __('Move start and end time'),
                __('Same overtime hours. Goes home {0} hour(s) earlier.', [move_h]))}
        </div>

        <div class="otp-step"><span class="otp-step-no">2</span>${__('Check the result')}</div>
        <div class="otp-table-wrap"><table class="otp-table">
            <thead><tr>
                <th>${__('Row', null, 'OT row number')}</th><th>${__('Employee')}</th><th>${__('Overtime')}</th>
            </tr></thead>
            <tbody>${maternity_rows.map((r, i) => {
                const b = ot_time_to_minutes(r.begin_time), e = ot_time_to_minutes(r.end_time);
                return `<tr>
                    <td class="otp-num">${r.idx}</td>
                    <td><b>${ot_esc(r.employee_name || '')}</b>
                        <span class="otp-badge">${ot_esc(r.employee)} · ${benefit_label[r.benefit_status] || ot_esc(r.benefit_status || '')} · ${fmt_date(r.date)}</span></td>
                    <td class="otp-num">
                        <span class="otp-badge">${__('Entered')}: ${span(b, e)}</span>
                        <span class="otp-after" data-i="${i}"></span>
                    </td>
                </tr>`;
            }).join('')}</tbody>
        </table></div>
    </div></div>`;

    const { $body } = ot_precheck_dialog(ot_precheck_title(total_steps, total_steps), html, __('Save'), () => {
        // always one of the 2 modes — no "keep as entered" (user 12/11/2026)
        adjust_maternity_employee_times(frm, maternity_rows, state.mode);
        on_done();
    });

    const render_after = () => {
        $body.find('.otp-card').each(function () {
            $(this).toggleClass('selected', $(this).attr('data-mode') === state.mode);
        });
        maternity_rows.forEach((r, i) => {
            const res = ot_precheck_result(r, state.mode);
            $body.find(`.otp-after[data-i="${i}"]`)
                .addClass('otp-changed')
                .text(__('After saving') + ': ' + span(res.begin, res.end) + ' (' + __('{0} h', [hours(res.begin, res.end)]) + ')');
        });
    };
    $body.on('change', 'input[name="otp-mode"]', function () {
        state.mode = this.value;
        render_after();
    });
    render_after();
}

// Adjust begin_time and end_time for employees with maternity benefits
// (offset comes from server: Attendance Calculation Setting → hour_reduction_hours)
// mode: 'both' = dời cả begin_time và end_time; 'start' = chỉ dời begin_time
// employees_to_adjust: results bound to their form row (`_row`) by check_all_before_save
function adjust_maternity_employee_times(frm, employees_to_adjust, mode) {
    const rows = frm.doc.ot_employees || [];
    const shifted = new Set();   // row names already moved — never move a row twice

    employees_to_adjust.forEach(emp => {
        const d = emp._row;
        if (!d || !rows.includes(d) || shifted.has(d.name)) return;
        const hours = emp.adjust_hours || 1;

        if (mode === 'start') {
            // Start only: the row now begins at the reduced shift end and still
            // ends where it did, so a following row stays continuous with it.
            d.begin_time = subtract_hours(d.begin_time, hours);
            shifted.add(d.name);
            return;
        }

        // Both: move the row, then every row of the same employee/date that
        // chains on from it (begin = previous row's original end) — otherwise
        // 17:00-18:00 + 18:00-19:00 became 16:00-17:00 + 18:00-19:00 and the
        // server rejected the 1-hour gap.
        let current = d;
        while (current) {
            const original_end = ot_time_to_minutes(current.end_time);
            current.begin_time = subtract_hours(current.begin_time, hours);
            current.end_time = subtract_hours(current.end_time, hours);
            shifted.add(current.name);
            current = rows.find(x => !shifted.has(x.name)
                && x.employee === d.employee && x.date === d.date
                && ot_time_to_minutes(x.begin_time) === original_end);
        }
    });

    // Refresh the child table
    frm.refresh_field('ot_employees');

    frappe.show_alert({
        // distinct employees, not rows (1 employee × 6 days used to read "6 employees")
        message: __('Adjusted OT time for {0} employee(s) with maternity benefits',
            [new Set(employees_to_adjust.map(e => e.employee)).size]),
        indicator: 'green'
    });
}

// Helper function to subtract N hours (can be fractional, e.g. 0.5) from time string
function subtract_hours(time_str, hours_to_subtract) {
    if (!time_str) return time_str;

    // Parse time string (format: HH:MM:SS or HH:MM)
    const parts = time_str.split(':');
    let hours = parseInt(parts[0]);
    let minutes = parseInt(parts[1]);
    let seconds = parts.length > 2 ? parseInt(parts[2]) : 0;

    let total_minutes = hours * 60 + minutes - Math.round((hours_to_subtract || 1) * 60);
    if (total_minutes < 0) {
        total_minutes += 24 * 60; // Wrap around to previous day
    }

    // Format back to string
    return String(Math.floor(total_minutes / 60)).padStart(2, '0') + ':' +
        String(total_minutes % 60).padStart(2, '0') + ':' +
        String(seconds).padStart(2, '0');
}

// Dead code removed: validate_duplicate_employees was superseded by validate_duplicate_rows


// Dead code removed: check_conflicts_with_submitted_records was not called from validate method


// Helper function to check if two time ranges overlap
function times_overlap(from1, to1, from2, to2) {
    // Convert time strings to Date objects for comparison
    const time1Start = new Date(`2000-01-01T${from1}`);
    const time1End = new Date(`2000-01-01T${to1}`);
    const time2Start = new Date(`2000-01-01T${from2}`);
    const time2End = new Date(`2000-01-01T${to2}`);

    // Check for overlap: start1 < end2 && start2 < end1
    // Adjacent periods (where one ends exactly when another begins) are NOT overlapping
    const condition1 = time1Start < time2End;
    const condition2 = time2Start < time1End;
    const overlap = condition1 && condition2;

    return overlap;
}

// Function to remove rows with empty employee
function remove_empty_overtime_rows(frm, silent = false) {
    var rows_to_remove = [];

    if (frm.doc.ot_employees) {
        frm.doc.ot_employees.forEach(function (row, index) {
            if (!row.employee) {
                rows_to_remove.push(row.name);
            }
        });
    }

    // Synchronous removal: grid_row.remove() runs clear_doc later (run_serially),
    // so idx was renumbered AFTER the pre-save check had read it (OTR-261112-0002).
    rows_to_remove.forEach(function (row_name) {
        frappe.model.clear_doc('Overtime Registration Detail', row_name);
    });

    if (rows_to_remove.length > 0) {
        frm.dirty();
        frm.refresh_field('ot_employees');

        if (!silent) {
            frappe.show_alert({
                message: __('Removed {0} empty rows', [rows_to_remove.length]),
                indicator: 'blue'
            });
        }
    } else if (!silent) {
        frappe.show_alert({
            message: __('No empty rows found'),
            indicator: 'orange'
        });
    }
}

// Approver = Leave Approver of the requester (Employee.leave_approver, else the
// department's first Leave Approver) — same rule the server applies on save.
function set_approver_for_employee(frm, employee) {
    if (!employee) {
        return;
    }
    frappe.call({
        method: 'hrms.hr.doctype.leave_application.leave_application.get_leave_approver',
        args: { employee: employee },
        callback: function (r) {
            frm.set_value('approver', (r && r.message) || '');
        },
        error: function () {
            frm.set_value('approver', '');
        }
    });
}

// ---------------------------------------------------------------------------
// Guided tour — steps live in the Form Tour doc "Overtime Registration"
// (customize_erpnext/form_tour/overtime_registration). The dialog sections are
// numbered ①–⑦ so the tour's step list maps 1:1 onto the dialog.
// ---------------------------------------------------------------------------

const OT_TOUR_SEEN_KEY = 'ot_registration_tour_seen';

function ot_tour_seen() {
    try {
        return localStorage.getItem(OT_TOUR_SEEN_KEY) === '1';
    } catch (e) {
        return true; // storage blocked: don't pop the tour on every new form
    }
}

function start_ot_form_tour(frm) {
    try {
        localStorage.setItem(OT_TOUR_SEEN_KEY, '1');
    } catch (e) { /* ignore */ }
    if (!frm.tour) return;
    frm.tour.init({ tour_name: 'Overtime Registration' }).then(() => {
        if (!frm.tour.tour || !frm.tour.tour.steps) return;
        drop_ot_tour_approval_steps(frm);
        apply_ot_tour_element_selectors(frm);
        frm.tour.start();
    });
}

// Workflow "Overtime Registration" inactive → no approver / "Actions → Submit"
// guidance (the form then shows the plain Submit button, nobody approves).
// Drops the approver step and the workflow-Actions step, then renumbers the
// "Bước N:" titles so the remaining steps stay 1..n.
function drop_ot_tour_approval_steps(frm) {
    if (frappe.model.has_workflow(frm.doctype)) return;
    const tour = frm.tour.tour;
    const is_approval_step = s =>
        (s.fieldname === 'approver' && !s.ui_tour)
        || (s.element_selector || '').includes('.actions-btn-group');
    tour.steps = tour.steps.filter(s => !is_approval_step(s));
    tour.steps.forEach((s, i) => {
        s.idx = i + 1;
        s.title = (s.title || '').replace(/^(\D*?)\d+(?=\s*:)/, `$1${i + 1}`);
    });
    frm.tour.build_steps();
    frm.tour.update_driver_steps();
}

// Frappe's FormTour only targets form fields. Steps flagged "UI Tour" in the
// Form Tour doc carry an element_selector instead (toolbar Save / workflow
// Actions); "a || b" = first visible match, else the toolbar itself.
function apply_ot_tour_element_selectors(frm) {
    const steps = (frm.tour.tour && frm.tour.tour.steps) || [];
    let changed = false;
    frm.tour.driver_steps.forEach(ds => {
        const step = steps.find(s => s.name === ds.name);
        if (!step || !step.element_selector) return;
        const candidates = step.element_selector.split('||').map(x => x.trim()).filter(Boolean);
        const found = candidates.map(sel => $(sel).filter(':visible').get(0)).find(Boolean);
        ds.element = found || $('.page-head:visible .page-actions').get(0) || ds.element;
        changed = true;
    });
    if (changed) frm.tour.update_driver_steps();
}

// Push this registration to the legacy MongoDB OtRegister (admin / HR only;
// the server checks the roles again). Re-sync replaces the previous push.
function add_sync_to_mongodb_button(frm) {
    if (frm.is_new() || frm.doc.docstatus === 2) return;
    if (!frappe.user.has_role(['System Manager', 'HR Manager', 'HR User'])) return;
    // Imported from MongoDB: same check as sync_to_mongodb, which refuses these on the server
    if ((frm.doc.ot_employees || []).some(row => (row.reason || '').includes('Request number:'))) return;
    frm.add_custom_button(__('Sync to MongoDB'), () => {
        if (frm.is_dirty()) {
            frappe.msgprint(__('Please save the document before syncing.'));
            return;
        }
        frappe.confirm(__('Push {0} to MongoDB? Rows already synced for this registration will be replaced.', [frm.doc.name]), () => {
            frappe.call({
                method: 'customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration_mongodb.sync_to_mongodb',
                args: { name: frm.doc.name },
                freeze: true,
                freeze_message: __('Syncing to MongoDB...'),
            }).then(r => {
                if (!r.message) return;
                frappe.show_alert({
                    message: __('Synced {0} row(s) to MongoDB', [r.message.inserted]),
                    indicator: 'green',
                });
                frm.reload_doc();
            });
        });
    });
}

// Pivot view of the OT list (employees × dates): button next to "Add Employees"
// (not a toolbar inner button — Frappe hides those on tablet portrait / phones)
function render_ot_inline_pivot_button(frm) {
    const field = frm.fields_dict.get_employees_button;
    if (!field || !field.$wrapper) return;
    ensure_ot_dialog_styles();
    const $w = field.$wrapper;
    if (!$w.find('.ot-inline-pivot').length) {
        $('<button type="button" class="btn btn-default btn-sm ot-inline-pivot"></button>')
            .text(__('View Summary Table'))
            .on('click', () => show_ot_pivot_dialog(frm))
            .insertAfter($w.find('button').first());
    }
    // "Print" right after "View Summary Table" (user 12/11/2026): opens the standard
    // print view with the default format (Overtime Registration V2). Hidden on a new,
    // never-saved form — there is nothing to print yet.
    if (!$w.find('.ot-inline-print').length) {
        $('<button type="button" class="btn btn-default btn-sm ot-inline-print"></button>')
            .text(__('Print', null, 'OT print form button'))
            .on('click', () => {
                if (frm.is_new() || frm.is_dirty()) {
                    frappe.msgprint(__('Please save the form before printing.'));
                    return;
                }
                frm.print_doc();
            })
            .insertAfter($w.find('.ot-inline-pivot'));
    }
    $w.find('.ot-inline-print').toggle(!frm.is_new());
}

// Help banner at the top of the form — only while the requester is composing
function render_ot_help_banner(frm) {
    const $wrapper = $(frm.layout.wrapper);
    let $banner = $wrapper.find('.ot-help-banner');
    const show = frm.doc.docstatus === 0 && (frm.is_new() || !frm.doc.workflow_state || frm.doc.workflow_state === 'Draft');
    if (!show) {
        $banner.remove();
        return;
    }
    if ($banner.length) return;
    ensure_ot_dialog_styles();
    $banner = $(`<div class="ot-help-banner" role="note">
        <span class="ot-help-icon" aria-hidden="true">?</span>
        <span class="ot-help-text">${ot_esc(__('First time? Follow the step-by-step guide.'))}</span>
        <button type="button" class="btn btn-sm ot-help-btn">${ot_esc(__('Help'))}</button>
    </div>`);
    $banner.find('.ot-help-btn').on('click', () => start_ot_form_tour(frm));
    $wrapper.prepend($banner);
}

function ot_step_badge(n) {
    return '<span class="ot-step-no">' + n + '</span>';
}

// Put Group + Week, and Begin + End time, side by side (a nested Section Break
// would break the dialog's 2-pane column layout, so regroup the DOM instead)
function arrange_ot_dialog_rows(dialog) {
    const wrap = (fieldnames, cls) => {
        const $controls = fieldnames.map(f => dialog.get_field(f).$wrapper);
        const $row = $('<div class="ot-row"></div>').addClass(cls).insertBefore($controls[0]);
        $controls.forEach($c => $row.append($c));
    };
    wrap(['selected_group', 'week_html'], 'ot-row-group');
    wrap(['time_begin', 'time_end'], 'ot-row-time');
}

function add_ot_dialog_step_numbers(dialog) {
    const label = (fieldname) => dialog.get_field(fieldname).$wrapper.find('.control-label').first();
    label('selected_group').prepend(ot_step_badge(1));
    label('time_begin').prepend(ot_step_badge(4));
    label('reason').prepend(ot_step_badge(5));
    dialog.get_primary_btn().prepend(ot_step_badge(7));
}
