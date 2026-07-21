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

        // Pivot view of the OT list (employees × dates)
        frm.page.add_inner_button(__('Pivot View'), function () {
            show_ot_pivot_dialog(frm);
        });

        // Reset validation flags when form refreshes
        frm.pre_save_check_done = false;
        frm.ot_continuity_validated = false;

        // Auto-populate requested_by with current user's employee
        if (frm.is_new() && !frm.doc.requested_by) {
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Employee',
                    fields: ['name', 'employee_name'],
                    filters: {
                        'user_id': frappe.session.user
                    }
                },
                callback: function (r) {
                    if (r.message && r.message.length > 0) {
                        const employee = r.message[0];
                        frm.set_value('requested_by', employee.name);
                        // Auto-fill approver based on requested_by
                        set_approver_based_on_requested_by(frm, employee.name);
                    }
                }
            });
        }

        // Set query filter for approver field (same as Leave Application)
        frm.set_query("approver", function () {
            return {
                query: "hrms.hr.doctype.department_approver.department_approver.get_approvers",
                filters: {
                    employee: frm.doc.requested_by,
                    doctype: frm.doc.doctype,
                },
            };
        });


    },
    get_employees_button(frm) {
        show_ot_registration_dialog(frm);
    },

    before_save(frm) {
        if (!frm.pre_save_check_done) {
            frappe.validated = false;
            check_all_before_save(frm);
            return false;
        }
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

        // Calculate totals
        calculate_totals_and_apply_reason(frm);

        // Update registered groups summary
        update_registered_groups(frm);
    },

    requested_by(frm) {
        // Auto-fill approver when requested_by field changes
        if (frm.doc.requested_by) {
            set_approver_based_on_requested_by(frm, frm.doc.requested_by);
        } else {
            // Clear approver if requested_by is cleared
            frm.set_value('approver', '');
            frm.set_value('approver_full_name', '');
        }
    },

    approver(frm) {
        // Set approver full name when approver changes (get employee name, not user name)
        if (frm.doc.approver) {
            get_employee_name_from_user(frm, frm.doc.approver);
        } else {
            frm.set_value('approver_full_name', '');
        }
    }
});

// ---------------------------------------------------------------------------
// "Get Employees" dialog — single-screen overtime planner.
// Left pane: plan (group, week, days, time, reason). Right pane: team roster.
// Batch mode: "Add Selected" writes rows and keeps the dialog open; the footer
// accumulates the session total (batches · rows · man-hours) with undo.
// ---------------------------------------------------------------------------

function _get_dialog_state(frm) {
    if (!frm._ot_dialog_state) {
        frm._ot_dialog_state = {
            currentDialog: null,
            selectedEmployees: new Map(), // employee id -> {name, employee_name, custom_group}
            employeeList: [],             // employees of the currently loaded group
            selectedDays: new Set(),      // 'monday'..'saturday'
            weekOffset: 0,
            searchTerm: '',
            loadingEmployees: false,
            addedBatches: []              // batches written this session (for ledger + undo)
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
.ot-reg-modal [data-fieldname="time_begin"],
.ot-reg-modal [data-fieldname="time_end"] {
    display: inline-block; width: calc(50% - 5px); vertical-align: top;
}
.ot-reg-modal [data-fieldname="time_begin"] { margin-right: 6px; }

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
.ot-pivot-footrow .ot-pivot-emp { left: 0; }
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
@media (max-width: 640px) {
    .ot-days { grid-template-columns: repeat(3, 1fr); }
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
    state.weekOffset = 0;
    state.searchTerm = '';
    state.loadingEmployees = false;
    state.addedBatches = [];

    const locked_group = (frm.doc.filter_employee_by === 'custom_group' && frm.doc.request_by_group)
        ? frm.doc.request_by_group : null;

    const dialog = new frappe.ui.Dialog({
        title: __('Select Employees for Overtime Registration'),
        size: 'extra-large',
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

    // A locked group is pre-filled, so load its roster immediately
    if (locked_group) {
        on_dialog_group_changed(frm);
    }
}

function render_ot_week_segment(frm) {
    const state = _get_dialog_state(frm);
    const $wrap = state.currentDialog.get_field('week_html').$wrapper;
    const labels = [__('Current Week'), __('Week +1'), __('Week +2')];

    let html = '<div class="ot-mini-head"><span>' + ot_esc(__('Week')) + '</span></div><div class="ot-seg" role="group">';
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

    let html = '<div class="ot-mini-head"><span>' + ot_esc(__('Day Selection')) + '</span>'
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
        <div class="ot-mini-head"><span>${ot_esc(__('Employee Selection'))}</span></div>
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

    const term = (state.searchTerm || '').trim().toLowerCase();
    const employees = !term ? state.employeeList : state.employeeList.filter(emp => {
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
    </div>`;

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
                state.loadingEmployees = false;
                state.employeeList = r.message || [];
                update_ot_roster(frm);
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

        calculate_totals_and_apply_reason(frm);
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
    calculate_totals_and_apply_reason(frm);
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
                ? String(d.begin_time).slice(0, 5) + '-' + String(d.end_time).slice(0, 5) : '',
            hours: hours,
            reason: d.reason || ''
        });
        emp.total += hours;
    });

    const dayNames = [__('Sun'), __('Mon'), __('Tue'), __('Wed'), __('Thu'), __('Fri'), __('Sat')];
    const colTotals = {};
    let grand = 0;

    let head = '<tr><th class="ot-pivot-no">' + ot_esc(__('No.')) + '</th>'
        + '<th class="ot-pivot-emp">' + ot_esc(__('Employee')) + '</th>'
        + '<th>' + ot_esc(__('Group')) + '</th>'
        + '<th>' + ot_esc(__('Note')) + '</th>';
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
            + '<td class="ot-pivot-emp"><b>' + ot_esc(empId) + '</b> ' + ot_esc(emp.employee_name || '') + '</td>'
            + '<td>' + ot_esc(emp.group || '') + '</td>'
            + '<td class="ot-pivot-note" data-emp="' + ot_esc(empId) + '"></td>';
        dates.forEach(dt => {
            const cell = emp.cells[dt];
            if (cell && cell.length) {
                const reasons = cell.map(c => c.reason).filter(Boolean).join('; ');
                body += '<td class="ot-pivot-on" title="' + ot_esc(reasons) + '">'
                    + cell.map(c => ot_esc(c.time)).join('<br>') + '</td>';
                colTotals[dt] += cell.reduce((sum, c) => sum + c.hours, 0);
            } else {
                body += '<td class="ot-pivot-off">–</td>';
            }
        });
        grand += emp.total;
        body += '<td class="ot-pivot-total">' + ot_num(emp.total) + '</td></tr>';
    });

    let foot = '<tr class="ot-pivot-footrow"><td class="ot-pivot-emp" colspan="4">' + ot_esc(__('Total (h)')) + '</td>';
    dates.forEach(dt => {
        foot += '<td>' + ot_num(colTotals[dt]) + '</td>';
    });
    foot += '<td class="ot-pivot-total">' + ot_num(grand) + '</td></tr>';

    const summary = __('{0} employee(s) · {1} day(s) · {2} row(s)',
        [byEmployee.size, dates.length, entries.length]);

    const dialog = new frappe.ui.Dialog({
        title: __('Pivot View') + (frm.doc.name ? ' — ' + frm.doc.name : ''),
        size: 'extra-large',
        fields: [{ fieldtype: 'HTML', fieldname: 'pivot_html' }]
    });
    dialog.show();
    dialog.$wrapper.addClass('ot-reg-modal');
    dialog.get_field('pivot_html').$wrapper.html(
        '<div class="ot-pivot-summary">' + ot_esc(summary) + '</div>'
        + '<div class="ot-pivot"><table><thead>' + head + '</thead><tbody>' + body + foot + '</tbody></table></div>'
    );

    // Note column: maternity flags per employee, matched against the pivot's
    // OT dates (pregnant phase / child under 12 months). Filled asynchronously;
    // silently empty if the user cannot read Employee Maternity.
    frappe.xcall(
        'customize_erpnext.customize_erpnext.doctype.overtime_registration.overtime_registration.get_maternity_flags',
        { employees: Array.from(byEmployee.keys()) }
    ).then(records => {
        const flags_by_emp = {};
        (records || []).forEach(r => {
            const flags = flags_by_emp[r.employee] = flags_by_emp[r.employee] || { pregnant: false, young: false };
            dates.forEach(dt => {
                if (r.pregnant_from_date && r.pregnant_to_date
                    && dt >= r.pregnant_from_date && dt <= r.pregnant_to_date) {
                    flags.pregnant = true;
                }
                if (r.youg_child_from_date && r.youg_child_to_date
                    && dt >= r.youg_child_from_date && dt <= r.youg_child_to_date) {
                    flags.young = true;
                }
            });
        });
        dialog.$wrapper.find('.ot-pivot-note').each(function () {
            const flags = flags_by_emp[$(this).attr('data-emp')];
            if (!flags) return;
            let html = '';
            if (flags.pregnant) {
                html += '<span title="' + ot_esc(__('Pregnant')) + '">\u{1F930}</span>';
            }
            if (flags.young) {
                html += (html ? ' ' : '') + '<span title="' + ot_esc(__('Young child under 12 months')) + '">\u{1F476}</span>';
            }
            $(this).html(html);
        });
    }).catch(() => { /* no read permission on Employee Maternity — leave notes empty */ });
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
                [rows, employee_name, entries.length, date]),
            indicator: 'orange'
        });
        frappe.validated = false;
        return false;
    }

    return true;
}

// Dead code removed: validate_ot_continuity was not called from form validate method


function check_all_before_save(frm) {
    const entries_to_check = (frm.doc.ot_employees || [])
        .filter(d => d.employee && d.date && d.begin_time && d.end_time)
        .map(d => ({
            idx: d.idx,
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
    ]).then(([maternity_results, conflict_results]) => {
        const has_maternity = maternity_results && maternity_results.length > 0;
        const has_conflicts = conflict_results && conflict_results.length > 0;

        if (!has_maternity && !has_conflicts) {
            frm.pre_save_check_done = true;
            frm.save();
            return;
        }

        const fields = [];

        // --- Maternity section ---
        if (has_maternity) {
            const shift_end = maternity_results[0].shift_end;
            const adjusted_shift_end = maternity_results[0].adjusted_shift_end;
            const emp_list_html = maternity_results.map(emp => {
                const emp_link = `<a href="/app/employee/${emp.employee}" target="_blank">${emp.employee}</a>`;
                return `<li>${__('Row')} ${emp.idx}: <b>${emp.employee_name}</b> (${emp_link}) — ${emp.benefit_type}
                 &nbsp;|&nbsp; ${__('Shift')}: ${emp.shift_type}
                 &nbsp;|&nbsp; ${__('OT Date')}: ${frappe.datetime.str_to_user(emp.date)}</li>`;
            }).join('');
            fields.push({
                fieldtype: 'HTML',
                options: `<div style="margin-bottom:12px;">
                    <p style="color:#856404;background:#fff3cd;padding:8px;border-radius:4px;">
                        <b>⚠ ${__('Employees with maternity benefits')}</b>
                    </p>
                    <p>${__('The following employees start OT at {0} but are on maternity/childcare benefits:', ['<b>' + shift_end + '</b>'])}</p>
                    <ul style="font-size:13px;">${emp_list_html}</ul>
                    <p style="color:#6c757d;font-size:12px;">${__('Adjust time 1 hour earlier')}: ${shift_end} → ${adjusted_shift_end}</p>
                </div>`
            });
            fields.push({
                fieldtype: 'Check',
                fieldname: 'adjust_maternity',
                label: __('Adjust OT time 1 hour earlier for these employees'),
                default: 1
            });
        }

        // --- Conflicts section ---
        if (has_conflicts) {
            const rows_html = conflict_results.map(c => {
                const date_str = frappe.datetime.str_to_user(c.date);
                const emp_link = `<a href="/app/employee/${c.employee}" target="_blank">${c.employee}</a>`;
                const doc_link = `<a href="/app/overtime-registration/${c.existing_doc}" target="_blank">${c.existing_doc}</a>`;
                return `<tr>
                    <td style="padding:4px 8px;">${__('Row')} ${c.idx}</td>
                    <td style="padding:4px 8px;"><b>${c.employee_name}</b><br><small>${emp_link}</small></td>
                    <td style="padding:4px 8px;">${date_str}</td>
                    <td style="padding:4px 8px;">${c.current_from} – ${c.current_to}</td>
                    <td style="padding:4px 8px;">${doc_link}, ${__('Row')} ${c.existing_idx}: ${c.existing_from} – ${c.existing_to}</td>
                </tr>`;
            }).join('');

            if (has_maternity) {
                fields.push({ fieldtype: 'HTML', options: '<hr style="margin:12px 0;">' });
            }

            fields.push({
                fieldtype: 'HTML',
                options: `<div style="margin-bottom:12px;">
                    <p style="color:#721c24;background:#f8d7da;padding:8px;border-radius:4px;">
                        <b>✗ ${__('Conflicts with approved OT')}</b>
                    </p>
                    <div style="overflow-x:auto;">
                        <table style="width:100%;border-collapse:collapse;font-size:13px;">
                            <thead><tr style="background:#f5f5f5;">
                                <th style="padding:4px 8px;text-align:left;">${__('Row')}</th>
                                <th style="padding:4px 8px;text-align:left;">${__('Employee')}</th>
                                <th style="padding:4px 8px;text-align:left;">${__('Date')}</th>
                                <th style="padding:4px 8px;text-align:left;">${__('OT Time')}</th>
                                <th style="padding:4px 8px;text-align:left;">${__('Conflicts with')}</th>
                            </tr></thead>
                            <tbody>${rows_html}</tbody>
                        </table>
                    </div>
                </div>`
            });
            fields.push({
                fieldtype: 'Check',
                fieldname: 'remove_conflicts',
                label: __('Remove conflicting rows from this form'),
                default: 1
            });
        }

        const dialog = new frappe.ui.Dialog({
            title: __('Pre-save check'),
            fields: fields,
            primary_action_label: __('Save'),
            primary_action: function () {
                dialog.hide();
                if (has_maternity && dialog.get_value('adjust_maternity')) {
                    adjust_maternity_employee_times(frm, maternity_results);
                }
                if (has_conflicts && dialog.get_value('remove_conflicts')) {
                    const conflict_idxs = new Set(conflict_results.map(c => c.idx));
                    frm.doc.ot_employees = frm.doc.ot_employees.filter(d => !conflict_idxs.has(d.idx));
                    frm.refresh_field('ot_employees');
                }
                frm.pre_save_check_done = true;
                frm.save();
            },
            secondary_action_label: __('Cancel'),
            secondary_action: function () {
                dialog.hide();
                // User reviews manually, do not save
            }
        });

        dialog.show();
    }).catch(() => {
        frm.pre_save_check_done = true;
        frm.save();
    });
}

// Adjust begin_time and end_time for employees with maternity benefits
// (offset comes from server: Attendance Calculation Setting → maternity_benefit_hours)
function adjust_maternity_employee_times(frm, employees_to_adjust) {
    // Create a map of idx to adjustment hours
    const adjustment_map = new Map();
    employees_to_adjust.forEach(emp => {
        adjustment_map.set(emp.idx, emp.adjust_hours || 1);
    });

    // Adjust times in child table
    frm.doc.ot_employees.forEach(d => {
        if (adjustment_map.has(d.idx)) {
            const hours = adjustment_map.get(d.idx);
            d.begin_time = subtract_hours(d.begin_time, hours);
            d.end_time = subtract_hours(d.end_time, hours);
        }
    });

    // Refresh the child table
    frm.refresh_field('ot_employees');

    frappe.show_alert({
        message: __('Adjusted OT time for {0} employee(s) with maternity benefits', [employees_to_adjust.length]),
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


function calculate_totals_and_apply_reason(frm) {
    if (!frm.doc.ot_employees || frm.doc.ot_employees.length === 0) {
        frm.set_value('total_employees', 0);
        frm.set_value('total_hours', 0);
        return;
    }

    const distinct_employees = new Set();
    let total_hours = 0.0;
    const child_reasons = new Set();

    // First pass: calculate totals and gather unique, non-empty child reasons
    frm.doc.ot_employees.forEach(d => {
        if (d.employee) {
            distinct_employees.add(d.employee);
        }

        if (d.begin_time && d.end_time) {
            // Simple time difference calculation
            const from_parts = d.begin_time.split(':');
            const to_parts = d.end_time.split(':');
            const from_minutes = parseInt(from_parts[0]) * 60 + parseInt(from_parts[1]);
            const to_minutes = parseInt(to_parts[0]) * 60 + parseInt(to_parts[1]);
            const diff_hours = (to_minutes - from_minutes) / 60;
            total_hours += diff_hours;
        }

        if (d.reason && d.reason.trim()) {
            child_reasons.add(d.reason.trim());
        }
    });

    // Update totals
    frm.set_value('total_employees', distinct_employees.size);
    frm.set_value('total_hours', total_hours);

    // If general reason is empty, populate it from unique child reasons
    // Also update if child_reasons has multiple unique reasons
    if (child_reasons.size > 0 && (!frm.doc.reason_general || child_reasons.size > 1)) {
        const sorted_reasons = Array.from(child_reasons).sort();
        frm.set_value('reason_general', sorted_reasons.join(', '));
    }

    // If a general reason now exists (either provided by user or generated),
    // apply it to any child rows that have an empty reason.
    if (frm.doc.reason_general) {
        frm.doc.ot_employees.forEach(d => {
            if (!d.reason) {
                d.reason = frm.doc.reason_general;
            }
        });
        frm.refresh_field('ot_employees');
    }
}

function update_registered_groups(frm) {
    if (!frm.doc.ot_employees || frm.doc.ot_employees.length === 0) {
        frm.set_value('registered_groups', '');
        return;
    }

    const distinct_groups = new Set();

    // Collect unique groups from all rows
    frm.doc.ot_employees.forEach(d => {
        if (d.group && d.group.trim()) {
            distinct_groups.add(d.group.trim());
        }
    });

    // Update registered groups summary
    if (distinct_groups.size > 0) {
        const sorted_groups = Array.from(distinct_groups).sort();
        frm.set_value('registered_groups', sorted_groups.join(', '));
    } else {
        frm.set_value('registered_groups', '');
    }
}

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

    // Remove rows in reverse order to avoid index issues
    rows_to_remove.reverse().forEach(function (row_name) {
        var row = frm.doc.ot_employees.find(r => r.name === row_name);
        if (row) {
            frm.get_field('ot_employees').grid.grid_rows_by_docname[row_name].remove();
        }
    });

    if (rows_to_remove.length > 0) {
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

// Function to auto-fill approver based on requested_by employee using HRMS pattern
function set_approver_based_on_requested_by(frm, employee) {
    if (!employee) {
        return;
    }

    // Use the same method as Leave Application
    frappe.call({
        method: 'hrms.hr.doctype.leave_application.leave_application.get_leave_approver',
        args: {
            employee: employee
        },
        callback: function (r) {
            if (r && r.message) {
                frm.set_value('approver', r.message);

                // Set the approver full name (get employee name, not user name)
                if (r.message) {
                    get_employee_name_from_user(frm, r.message);
                }
            } else {
                frm.set_value('approver', '');
                frm.set_value('approver_full_name', '');
            }
        },
        error: function (r) {
            frm.set_value('approver', '');
            frm.set_value('approver_full_name', '');
        }
    });
}

// Helper function to get employee name from user ID for approver_full_name field
function get_employee_name_from_user(frm, user_id) {
    frappe.call({
        method: 'frappe.client.get_value',
        args: {
            doctype: 'Employee',
            fieldname: 'employee_name',
            filters: {
                'user_id': user_id
            }
        },
        callback: function (emp_r) {
            if (emp_r.message && emp_r.message.employee_name) {
                frm.set_value('approver_full_name', emp_r.message.employee_name);
            } else {
                // Fallback to user's full name if no employee record found
                frm.set_value('approver_full_name', frappe.user.full_name(user_id));
            }
        },
        error: function (r) {
            // Fallback to user's full name on error
            frm.set_value('approver_full_name', frappe.user.full_name(user_id));
        }
    });
}
