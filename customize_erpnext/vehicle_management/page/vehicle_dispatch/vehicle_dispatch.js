// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt
//
// Điều hành xe — the desk counterpart of the Zalo Mini App dispatcher screen.
// Same KPI definitions, same colours, same wording, so a dispatcher holding a
// phone and one sitting at a PC never read two different numbers.
// KPI definitions are the ones both teams agreed: vehicle_management/API_CONTRACT.md mục 9.

frappe.pages['vehicle-dispatch'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Điều hành xe'),
		single_column: true,
	});

	new VehicleDashboard(page, wrapper);
};

const API = 'customize_erpnext.api.vehicle_management';
const PAGE_API =
	'customize_erpnext.vehicle_management.page.vehicle_dispatch.vehicle_dispatch';
const REFRESH_SECONDS = 30;
// Mirrors DUE_SOON_MINUTES in api/vehicle_management.py.
const DUE_SOON_MINUTES = 10;

// Agreed with the Mini App team. `scheduled` deliberately covers confirmed too:
// both mean "a vehicle is committed to this trip and it has not started yet".
const KPI_CONFIG = [
	{ key: 'requests', label: 'Chờ duyệt', icon: '⏳', color: '#FFA500', bg: '#FFF3E0' },
	{ key: 'scheduled', label: 'Đã xếp xe', icon: '📅', color: '#0068FF', bg: '#E3F2FD' },
	{ key: 'in_progress', label: 'Đang chạy', icon: '🚗', color: '#00C851', bg: '#E8F5E9' },
	{ key: 'completed', label: 'Hoàn thành', icon: '🏁', color: '#666666', bg: '#F5F5F5' },
];

const VEHICLE_STATUS = {
	available: { label: 'Đang đỗ', color: '#00C851' },
	in_trip: { label: 'Đang chạy', color: '#FF8800' },
	maintenance: { label: 'Bảo trì', color: '#9E9E9E' },
	broken: { label: 'Hỏng hóc', color: '#FF4444' },
};
const ASSIGNED_STATUS = { label: 'Đã xếp chuyến', color: '#0068FF' };

const TRIP_STATUS = {
	scheduled: { label: 'Chờ chạy', color: '#0068FF' },
	confirmed: { label: 'Đã xác nhận', color: '#0068FF' },
	in_progress: { label: 'Đang chạy', color: '#FF8800' },
	completed: { label: 'Hoàn thành', color: '#00C851' },
	cancelled: { label: 'Đã hủy', color: '#9E9E9E' },
};

const OPEN_STATUSES = ['scheduled', 'confirmed'];

class VehicleDashboard {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = wrapper;

		this.date = frappe.datetime.get_today();
		this.filter = null; // null | requests | scheduled | in_progress | completed
		this.vehicle = null; // vehicle docname
		this.trips = [];
		this.requests = [];
		this.vehicles = [];
		this.drivers = [];
		this.stats = {};
		this.combinable = [];
		this.countdown = REFRESH_SECONDS;

		this.render_shell();
		this.bind();
		this.setup_refresh();
		this.load_permissions();
		this.load();
	}

	// ------------------------------------------------------------------ shell
	render_shell() {
		// vehicle_dispatch.html is registered as a JS template by frappe's Page
		// loader (core/doctype/page/page.py -> html_to_js_template), keyed on the
		// FILE NAME - rename the file and this string has to follow.
		this.page.main.html(frappe.render_template('vehicle_dispatch', {}));
		this.$ = (name) => this.page.main.find(`[data-el="${name}"]`);

		this.setup_date_control();
		this.update_date_label();

		// Actions live as visible buttons in the toolbar (see vehicle_dispatch.html),
		// not behind the ⋯ menu - a dispatcher should see every command at a glance.
	}

	load_permissions() {
		// Only one control depends on this today - the demo-data reset - but the
		// endpoint answers for all of them, so the page asks once at startup rather
		// than guessing from roles in the browser.
		return frappe
			.call({ method: PAGE_API + '.get_page_context' })
			.then((r) => {
				const perms = (r && r.message) || {};
				this.page.main
					.find('[data-act="reset-demo"]')
					.prop('hidden', !perms.is_administrator);
			})
			.catch(() => {});
	}

	setup_date_control() {
		this.date_control = frappe.ui.form.make_control({
			parent: this.$('date-mount'),
			df: {
				fieldtype: 'Date',
				fieldname: 'trip_date',
				placeholder: __('Chọn ngày'),
				change: () => {
					// get_value() is YYYY-MM-DD no matter how the user's date format
					// is set, which is the whole reason for using the Frappe control
					// instead of a raw <input type="date">.
					const value = this.date_control.get_value();
					if (!value || value === this.date) return;
					this.date = value;
					this.update_date_label();
					this.load();
				},
			},
			render_input: true,
			only_input: true,
		});
		this.date_control.set_value(this.date);
	}

	bind() {
		const $root = this.page.main;

		// Event delegation rather than inline onclick: a location or an employee
		// name typed in the Mini App would otherwise end up inside an HTML
		// attribute, where one apostrophe breaks the handler and a crafted string
		// runs as script.
		$root.on('click', '[data-act="refresh"]', () => this.load());
		$root.on('click', '[data-act="clear-filter"]', () => {
			this.filter = null;
			this.vehicle = null;
			this.render();
		});
		$root.on('click', '[data-act="new-trip"]', () => this.new_trip_dialog());
		$root.on('click', '[data-act="vehicle-status"]', () => this.vehicle_status_dialog());
		$root.on('click', '[data-act="reset-demo"]', () => this.reset_demo_dialog());

		$root.on('click', '[data-kpi]', (e) => {
			const key = e.currentTarget.dataset.kpi;
			this.vehicle = null;
			this.filter = this.filter === key ? null : key;
			this.render();
		});

		$root.on('click', '[data-vehicle]', (e) => {
			const name = e.currentTarget.dataset.vehicle;
			if (this.vehicle === name) {
				this.vehicle = null;
				this.filter = null;
			} else {
				this.vehicle = name;
				this.filter = e.currentTarget.dataset.vehicleFilter || null;
			}
			this.render();
		});

		$root.on('click', '[data-trip-open]', (e) =>
			frappe.set_route('Form', 'TIQN Vehicle Trip', e.currentTarget.dataset.tripOpen)
		);
		$root.on('click', '[data-trip-cancel]', (e) => this.cancel_trip(e.currentTarget.dataset.tripCancel));
		$root.on('click', '[data-req-assign]', (e) => this.assign_dialog(e.currentTarget.dataset.reqAssign));
		$root.on('click', '[data-req-reject]', (e) => this.reject(e.currentTarget.dataset.reqReject));
	}

	setup_refresh() {
		this.on_update = () => this.load(true);
		frappe.realtime.on('tiqn_vehicle_dispatch_update', this.on_update);

		// The reset runs on a worker, so the answer arrives by realtime rather than
		// as the reply to the click.
		this.on_seed_done = (data) => this.on_reset_finished(data);
		frappe.realtime.on('tiqn_vehicle_seed_done', this.on_seed_done);

		// One second ticker drives both the countdown and the reload, so the label
		// can never drift out of step with the refresh that it is counting to.
		// Nothing happens while the page is off screen - a cached Desk page would
		// otherwise keep polling forever in a background tab.
		this.ticker = setInterval(() => {
			if (!this.is_visible()) return;
			this.countdown -= 1;
			if (this.countdown <= 0) {
				this.load(true);
			} else {
				this.$('auto-label').text(__('tự làm mới sau {0}s', [this.countdown]));
			}
		}, 1000);
	}

	is_visible() {
		return !!(this.wrapper && this.wrapper.offsetParent !== null);
	}

	// ------------------------------------------------------------------- data
	load(silent) {
		this.countdown = REFRESH_SECONDS;
		this.$('auto-label').text(__('đang tải...'));
		if (!silent) {
			this.$('trip-list').html(`<div class="vd-loading">⏳ ${__('Đang tải...')}</div>`);
		}

		return frappe
			.call({ method: `${API}.get_dispatch_overview`, args: { date: this.date } })
			.then((r) => {
				const data = (r && r.message) || {};
				this.stats = data.stats || {};
				this.vehicles = data.vehicles || [];
				this.drivers = data.drivers || [];
				this.requests = data.pending_requests || [];
				this.combinable = data.combinable || [];
				this.trips = (data.trips || []).sort((a, b) =>
					String(a.depart_time || '').localeCompare(String(b.depart_time || ''))
				);
				this.render();
			})
			.catch(() => {
				this.$('trip-list').html(
					`<div class="vd-empty"><div class="vd-empty-icon">⚠️</div>${__('Không tải được dữ liệu')}</div>`
				);
			});
	}

	// -------------------------------------------------------------- rendering
	render() {
		this.render_kpis();
		this.render_vehicles();
		this.render_trips();
		this.render_requests();
		this.$('auto-label').text(__('tự làm mới sau {0}s', [this.countdown]));
	}

	kpi_value(key) {
		if (key === 'requests') return this.requests.length;
		if (key === 'scheduled') return cint(this.stats.scheduled) + cint(this.stats.confirmed);
		// Trips in progress on the selected date - NOT vehicles flagged in_trip.
		// A vehicle can still be marked busy by a trip from another day; counting
		// vehicles would quietly report a different number from the Mini App.
		if (key === 'in_progress') return cint(this.stats.in_progress);
		if (key === 'completed') return cint(this.stats.completed);
		return 0;
	}

	render_kpis() {
		const html = KPI_CONFIG.map((k) => {
			const active = this.filter === k.key;
			return `
			<div class="vd-kpi" data-kpi="${k.key}" title="${__(k.label)}"
				style="background:${active ? k.color : k.bg};border-color:${active ? k.color : k.color + '30'}">
				<div class="vd-kpi-top">
					<span class="vd-kpi-icon">${k.icon}</span>
					<span class="vd-kpi-value" style="color:${active ? '#fff' : k.color}">${this.kpi_value(k.key)}</span>
				</div>
				<div class="vd-kpi-label" style="color:${active ? 'rgba(255,255,255,.85)' : 'var(--vd-muted)'}">
					${__(k.label)}
				</div>
			</div>`;
		}).join('');
		this.$('kpi-row').html(html);
	}

	render_vehicles() {
		if (!this.vehicles.length) {
			this.$('vehicle-strip').html(`<div class="vd-loading">${__('Chưa có dữ liệu xe')}</div>`);
			return;
		}

		const html = this.vehicles
			.map((v) => {
				// A parked vehicle that already has a trip booked today is neither
				// "free" nor "running" - the Mini App shows that third state and so
				// must this page, or the two disagree on screen.
				const booked =
					v.status === 'available'
						? this.trips.find((t) => t.vehicle === v.name && OPEN_STATUSES.includes(t.status))
						: null;
				const cfg = booked ? ASSIGNED_STATUS : VEHICLE_STATUS[v.status] || VEHICLE_STATUS.available;

				const filter = v.status === 'in_trip' ? 'in_progress' : booked ? 'scheduled' : '';
				const clickable = !!filter;
				const active = this.vehicle === v.name;

				// Status and depart time share a line - three stacked lines of text
				// would make the card taller than the KPI chips beside it.
				const depart = booked && booked.depart_time
					? ` <span class="vd-vehicle-depart">⏰ ${esc(booked.depart_time)}</span>`
					: '';

				return `
			<div class="vd-vehicle-card ${clickable ? 'clickable' : ''}"
				${clickable ? `data-vehicle="${esc(v.name)}" data-vehicle-filter="${filter}"` : ''}
				title="${esc(v.vehicle_name || v.name)} — ${esc(v.license_plate || '')}"
				style="border-color:${active ? cfg.color : cfg.color + '40'};
					   box-shadow:${active ? `0 4px 16px ${cfg.color}55` : ''}">
				<div class="vd-vehicle-img">
					<span>🚌</span>
					${v.image ? `<img src="${esc(v.image)}" alt="" onerror="this.remove()">` : ''}
					<div class="vd-status-dot" style="background:${cfg.color}"></div>
				</div>
				<div class="vd-vehicle-info">
					<div class="vd-vehicle-name">${esc(v.vehicle_name || v.name)}</div>
					<div class="vd-vehicle-plate">${esc(v.license_plate || '')}</div>
					<div class="vd-vehicle-status" style="color:${cfg.color}">${__(cfg.label)}${depart}</div>
				</div>
			</div>`;
			})
			.join('');

		this.$('vehicle-strip').html(html);
	}

	filtered_trips() {
		let trips = this.trips;
		if (this.vehicle) trips = trips.filter((t) => t.vehicle === this.vehicle);
		if (!this.filter || this.filter === 'requests') return trips;
		if (this.filter === 'scheduled') return trips.filter((t) => OPEN_STATUSES.includes(t.status));
		return trips.filter((t) => t.status === this.filter);
	}

	render_trips() {
		const active = KPI_CONFIG.find((k) => k.key === this.filter);
		const vehicle = this.vehicles.find((v) => v.name === this.vehicle);
		const has_filter = !!(this.filter || this.vehicle);

		let title;
		if (this.filter === 'requests') {
			title = `⏳ ${__('Chờ duyệt')} (${this.requests.length})`;
		} else if (active) {
			title = `${active.icon} ${__(active.label)}`;
		} else {
			title = `📋 ${__('Chuyến ngày')} ${frappe.datetime.str_to_user(this.date)} (${this.trips.length})`;
		}
		if (vehicle) title += ` — ${vehicle.vehicle_name || vehicle.name}`;

		this.$('trip-title').text(title);
		this.$('clear-filter').toggle(has_filter);

		if (this.filter === 'requests') {
			this.$('trip-list').html(
				`<div class="vd-empty">${__('Danh sách yêu cầu đang hiển thị ở cột bên phải.')}</div>`
			);
			return;
		}

		const trips = this.filtered_trips();
		if (!trips.length) {
			this.$('trip-list').html(
				`<div class="vd-empty"><div class="vd-empty-icon">📭</div>${__('Không có chuyến nào')}</div>`
			);
			return;
		}

		this.$('trip-list').html(this.trip_columns_html(trips));
	}

	trip_columns_html(trips) {
		// One column per vehicle. Reading down a column answers the question a
		// dispatcher actually asks - "what is this bus doing today" - which a single
		// merged list never does.
		const by_vehicle = new Map();
		trips.forEach((t) => {
			const key = t.vehicle || '';
			if (!by_vehicle.has(key)) by_vehicle.set(key, []);
			by_vehicle.get(key).push(t);
		});

		// Vehicle order comes from the fleet list, so the columns keep the same
		// left-to-right order as the cards above them even on a day when a vehicle
		// has no trips at all.
		const columns = this.vehicles
			.filter((v) => !this.vehicle || v.name === this.vehicle)
			.map((v) => ({
				key: v.name,
				name: v.vehicle_name || v.name,
				plate: v.license_plate || '',
				colour: (VEHICLE_STATUS[v.status] || VEHICLE_STATUS.available).color,
				trips: by_vehicle.get(v.name) || [],
			}));

		// A trip whose vehicle is not in the fleet list (deleted, or filtered out)
		// would otherwise vanish from the board without a trace.
		const known = new Set(this.vehicles.map((v) => v.name));
		const orphans = trips.filter((t) => !known.has(t.vehicle));
		if (orphans.length) {
			columns.push({
				key: '__orphan',
				name: __('Chưa rõ xe'),
				plate: '',
				colour: '#9E9E9E',
				trips: orphans,
			});
		}

		return `<div class="vd-trip-columns">${columns
			.map(
				(col) => `
			<div class="vd-trip-col">
				<div class="vd-trip-col-head" style="border-left-color:${col.colour}">
					<span class="vd-trip-col-name">${esc(col.name)}</span>
					<span class="vd-trip-col-plate">${esc(col.plate)}</span>
					<span class="vd-trip-col-count">${col.trips.length}</span>
				</div>
				${
					col.trips.length
						? col.trips.map((t) => this.trip_card_html(t)).join('')
						: `<div class="vd-col-empty">${__('Không có chuyến')}</div>`
				}
			</div>`
			)
			.join('')}</div>`;
	}

	trip_card_html(t) {
		const cfg = TRIP_STATUS[t.status] || { label: t.status, color: '#999' };
		const route = [t.from_location, t.to_location].filter(Boolean).map(esc).join(' → ') || '—';
		// KM is what TIQN actually pays the partner for, so it is on the card
		// rather than buried in the record.
		const km = flt(t.total_km)
			? `<div class="vd-trip-km">📍 ${format_number(t.total_km, null, 1)} km</div>`
			: '';
		const cancel = OPEN_STATUSES.includes(t.status)
			? `<button class="vd-btn-sm vd-btn-cancel" data-trip-cancel="${esc(t.name)}">${__('Hủy')}</button>`
			: '';

		return `
		<div class="vd-trip-card" style="border-left-color:${cfg.color}">
			<div class="vd-trip-head">
				<span class="vd-trip-time">${esc(t.depart_time || '—')}</span>
				<span class="vd-status-badge" style="background:${cfg.color}">${__(cfg.label)}</span>
				${t.route_changed ? `<span class="vd-status-badge" style="background:#FF4444">${__('Đổi tuyến')}</span>` : ''}
			</div>
			<div class="vd-trip-route">${route}</div>
			<div class="vd-trip-meta">👤 ${esc(t.driver_name || '—')}</div>
			${km}
			<div class="vd-trip-actions">
				<button class="vd-btn-sm vd-btn-detail" data-trip-open="${esc(t.name)}">${__('Chi tiết')}</button>
				${cancel}
			</div>
		</div>`;
	}

	render_requests() {
		this.$('req-count').text(this.requests.length);

		if (!this.requests.length) {
			this.$('request-list').html(
				`<div class="vd-empty"><div class="vd-empty-icon">✅</div>${__('Không có yêu cầu chờ duyệt')}</div>`
			);
			return;
		}

		const combinable = new Set();
		this.combinable.forEach((group) => group.forEach((n) => combinable.add(n)));

		const html = this.requests
			.map((r) => {
				const route =
					[r.from_location, r.to_location].filter(Boolean).map(esc).join(' → ') || '—';
				const urgency = request_urgency(r);
				// Purpose earns its own line: deciding which vehicle to send needs to
				// know what the trip is FOR, and a tooltip is not something anyone
				// finds. Notes stay in the tooltip - they are detail, not criteria.
				const tip = [r.purpose, r.notes].filter(Boolean).join(' — ');

				return `
			<div class="vd-req-card ${urgency.css}" title="${esc(tip)}">
				<div class="vd-req-top">
					<span class="vd-req-countdown" style="color:${urgency.colour}">
						${urgency.icon ? `${urgency.icon} ` : ''}${esc(urgency.relative || '')}
					</span>
					<span class="vd-req-when">${esc(short_when(r.request_time, this.date))}</span>
				</div>
				<div class="vd-req-who">
					${combinable.has(r.name) ? '<span class="vd-req-link" title="Có thể gom chung xe">🔗</span>' : ''}
					<b>${esc(r.employee_name || '—')}</b>
					<span class="vd-req-dept">${esc(r.employee_id_display || '')}</span>
					<span class="vd-req-pax" title="${__('Số người đi')}">👤 ${cint(r.passenger_count) || 1}</span>
				</div>
				<div class="vd-req-route">${route}</div>
				${r.purpose ? `<div class="vd-req-purpose">${esc(r.purpose)}</div>` : ''}
				<div class="vd-req-actions">
					<button class="vd-btn-sm vd-btn-approve" data-req-assign="${esc(r.name)}">${__('Xếp xe')}</button>
					<button class="vd-btn-sm vd-btn-reject" data-req-reject="${esc(r.name)}">${__('Từ chối')}</button>
				</div>
			</div>`;
			})
			.join('');

		this.$('request-list').html(html);
	}

	// ---------------------------------------------------------------- actions
	call(method, args, message) {
		return frappe
			.call({ method: `${API}.${method}`, type: 'POST', args, freeze: true, freeze_message: message })
			.then(() => this.load(true));
	}

	assign_dialog(name) {
		// "Xếp xe" IS the approval - there is no separate Duyệt step. Either the
		// request joins a trip that already exists, or a trip is created for it;
		// both land the request straight on `assigned`.
		const request = this.requests.find((r) => r.name === name) || {};
		const open_trips = this.trips.filter((t) =>
			['scheduled', 'confirmed', 'in_progress'].includes(t.status)
		);

		// request_time is "YYYY-MM-DD HH:MM:SS" on the wire, so the halves are taken
		// by position. Parsing it into a Date first would push it through the
		// browser's timezone and can land the trip on the wrong day.
		const [wanted_date, wanted_clock] = String(request.request_time || '').split(' ');
		const wanted = {
			date: wanted_date || this.date,
			time: clock_for_control(wanted_clock),
		};

		let d;
		d = new frappe.ui.Dialog({
			title: __('Xếp xe cho {0}', [request.employee_name || name]),
			fields: [
				{
					fieldname: 'mode',
					fieldtype: 'Select',
					label: __('Cách xếp'),
					reqd: 1,
					// Creating a trip is the default: it is what happens almost every
					// time. Joining an existing trip is the exception (car-pooling two
					// requests), so it is the second choice, not the first.
					default: 'new',
					options: [
						{ value: 'new', label: __('Tạo chuyến mới') },
						{ value: 'existing', label: __('Ghép vào chuyến đã có') },
					],
				},
				{
					fieldname: 'trip_name',
					fieldtype: 'Select',
					label: __('Chuyến'),
					depends_on: 'eval:doc.mode=="existing"',
					options: open_trips.map((t) => ({
						value: t.name,
						label: `${t.depart_time || ''} ${t.vehicle_name || t.vehicle} — ${t.from_location || ''} → ${t.to_location || ''}`,
					})),
				},
				{ fieldname: 'sb', fieldtype: 'Section Break', depends_on: 'eval:doc.mode=="new"' },
				// Pick the vehicle and you are done: the driver fills itself in from
				// that vehicle's default driver, and the date and time come from the
				// request. Everything stays editable for the odd case - a stand-in
				// driver, a time the dispatcher renegotiated - but the common case is
				// one click.
				...this.vehicle_and_driver_fields(() => d),
				{ fieldname: 'cb', fieldtype: 'Column Break' },
				{ fieldname: 'trip_date', fieldtype: 'Date', label: __('Ngày chạy'), default: wanted.date },
				{ fieldname: 'depart_time', fieldtype: 'Time', label: __('Giờ xuất phát'), default: wanted.time },
			],
			primary_action_label: __('Xếp xe'),
			primary_action: (values) => {
				if (values.mode === 'existing') {
					if (!values.trip_name) {
						frappe.msgprint(__('Hãy chọn một chuyến.'));
						return;
					}
					d.hide();
					this.call(
						'assign_request_to_trip',
						{ request_name: name, trip_name: values.trip_name },
						__('Đang xếp xe...')
					);
					return;
				}

				if (!values.vehicle) {
					frappe.msgprint(__('Hãy chọn xe.'));
					return;
				}
				// No driver check here either - see new_trip_dialog().
				d.hide();
				this.call(
					'combine_requests_to_trip',
					{
						request_names: JSON.stringify([name]),
						vehicle: values.vehicle,
						driver: values.driver,
						trip_date: values.trip_date,
						depart_time: values.depart_time,
					},
					__('Đang tạo chuyến và xếp xe...')
				);
			},
		});
		d.show();
	}

	reject(name) {
		// The server refuses `rejected` without a reason, so ask for it up front
		// instead of letting the click come back as a validation error.
		frappe.prompt(
			{ fieldname: 'rejection_reason', label: __('Lý do từ chối'), fieldtype: 'Small Text', reqd: 1 },
			(values) => this.call('update_request', { name, ...values }, __('Đang từ chối...')),
			__('Từ chối yêu cầu'),
			__('Từ chối')
		);
	}

	cancel_trip(name) {
		frappe.prompt(
			{ fieldname: 'cancelled_reason', label: __('Lý do hủy'), fieldtype: 'Small Text', reqd: 1 },
			(values) => this.call('cancel_trip', { name, ...values }, __('Đang hủy chuyến...')),
			__('Hủy chuyến {0}', [name]),
			__('Hủy chuyến')
		);
	}

	driver_for_vehicle(vehicle) {
		// Every driver is assigned a default vehicle, so picking the vehicle picks
		// the driver. Only active drivers count - an inactive one would be filled
		// in silently and the trip would be handed to somebody who has left.
		const match = this.drivers.find((d) => d.assigned_vehicle === vehicle && d.is_active);
		return match ? match.name : null;
	}

	vehicle_and_driver_fields(get_dialog) {
		// Shared by Tạo chuyến / Xếp xe / Gom yêu cầu so the three dialogs cannot
		// drift apart. The driver stays editable: a stand-in driver is normal.
		//
		// `get_dialog` is a getter rather than the dialog itself because these
		// fields are built BEFORE the dialog exists. Reaching for the dialog
		// through Frappe control internals worked too, but it breaks the day
		// those internals move.
		return [
			{
				fieldname: 'vehicle',
				fieldtype: 'Link',
				options: 'TIQN Vehicle',
				label: __('Xe'),
				onchange: () => {
					const dialog = get_dialog();
					if (!dialog) return;
					const driver = this.driver_for_vehicle(dialog.get_value('vehicle'));
					if (driver) dialog.set_value('driver', driver);
				},
			},
			{
				fieldname: 'driver',
				fieldtype: 'Link',
				options: 'TIQN Driver',
				label: __('Tài xế'),
				description: __('Tự điền theo xe. Chỉ sửa khi có người chạy thay.'),
			},
		];
	}

	new_trip_dialog() {
		// Two ways to start a trip:
		//   blank         - an ad-hoc run nobody requested (default; a requested
		//                   ride is usually started from its own "Xếp xe" button)
		//   from_requests - one or more pending requests ride together
		// The second mode absorbed the old "Gom yêu cầu" button: it does the same
		// job without limiting the dispatcher to the auto-detected groups, and two
		// buttons for one job is one too many.
		const pending = this.requests;
		const suggested = new Set();
		this.combinable.forEach((group) => group.forEach((n) => suggested.add(n)));

		let d;
		d = new frappe.ui.Dialog({
			title: __('Tạo chuyến'),
			size: 'large',
			fields: [
				{
					fieldname: 'mode',
					fieldtype: 'Select',
					label: __('Loại chuyến'),
					reqd: 1,
					default: 'blank',
					options: [
						{ value: 'blank', label: __('Chuyến mới hoàn toàn') },
						{ value: 'from_requests', label: __('Từ yêu cầu chờ duyệt') },
					],
					onchange: () => this.sync_trip_dialog_from_requests(d),
				},
				{
					fieldname: 'requests',
					fieldtype: 'MultiCheck',
					label: __('Chọn yêu cầu'),
					depends_on: 'eval:doc.mode=="from_requests"',
					columns: 1,
					// Keep the server's order (request_time ascending). MultiCheck
					// sorts by label unless told not to, which would shuffle the list
					// by whatever happens to be the first character.
					sort_options: false,
					options: pending.map((r) => {
						// Everything needed to decide goes on the one line: when the
						// vehicle is wanted, who wants it, and the route. Without the
						// time the dispatcher has to close the dialog to look it up.
						// 🔗 marks a request the server already spotted as shareable
						// with another one - same route, within 30 minutes.
						const urgency = request_urgency(r);
						const when = r.request_time
							? frappe.datetime.str_to_user(r.request_time)
							: __('chưa rõ giờ');
						const rel = urgency.relative ? ` <small>(${esc(urgency.relative)})</small>` : '';
						return {
							value: r.name,
							label: [
								suggested.has(r.name) ? '🔗' : '',
								`<b>${esc(when)}</b>${rel}`,
								'·',
								esc(r.employee_name || r.name),
								// Số người quyết định chọn xe nào - Kia 7 chỗ không chở
								// nổi 10 người - nên nó phải nằm ngay trên dòng chọn.
								`👤${cint(r.passenger_count) || 1}`,
								'·',
								`${esc(r.from_location || '—')} → ${esc(r.to_location || '—')}`,
							]
								.filter(Boolean)
								.join(' '),
							// MultiCheck colours the label itself from these two, so
							// the late/soon signal survives here without a second
							// styling scheme of our own.
							danger: urgency.css === 'is-late',
							warning: urgency.css === 'is-soon',
							description: r.purpose || '',
							checked: 0,
						};
					}),
					// 🔴 `on_change`, NOT `onchange`. MultiCheck binds its own checkbox
					// handler and calls `this.df.on_change` (multicheck.js:
					// bind_checkboxes) - every other control calls `df.onchange`, so
					// the usual spelling silently never fires here.
					on_change: () => this.sync_trip_dialog_from_requests(d),
				},
				{ fieldname: 'sb_veh', fieldtype: 'Section Break' },
				...this.vehicle_and_driver_fields(() => d).map((f) =>
					f.fieldname === 'vehicle' ? { ...f, reqd: 1 } : f
				),
				{ fieldname: 'cb', fieldtype: 'Column Break' },
				{ fieldname: 'trip_date', fieldtype: 'Date', label: __('Ngày chạy'), reqd: 1, default: this.date },
				{ fieldname: 'depart_time', fieldtype: 'Time', label: __('Giờ xuất phát') },
				{ fieldname: 'sb_route', fieldtype: 'Section Break' },
				{ fieldname: 'from_location', fieldtype: 'Data', label: __('Điểm đi') },
				{ fieldname: 'to_location', fieldtype: 'Data', label: __('Điểm đến') },
				{ fieldname: 'notes', fieldtype: 'Small Text', label: __('Ghi chú') },
			],
			primary_action_label: __('Tạo chuyến'),
			primary_action: (values) => {
				if (!values.vehicle) {
					frappe.msgprint(__('Hãy chọn xe.'));
					return;
				}
				// No driver check: the server fills the vehicle's default driver and
				// only complains if that vehicle genuinely has none.

				const chosen = values.mode === 'from_requests' ? values.requests || [] : [];
				if (values.mode === 'from_requests' && !chosen.length) {
					frappe.msgprint(__('Hãy chọn ít nhất một yêu cầu.'));
					return;
				}

				d.hide();

				if (chosen.length) {
					// combine_requests_to_trip creates the trip AND flips every chosen
					// request to `assigned` in one transaction - doing it in two steps
					// would leave requests stranded if the second one failed.
					this.call(
						'combine_requests_to_trip',
						{
							request_names: JSON.stringify(chosen),
							vehicle: values.vehicle,
							driver: values.driver,
							trip_date: values.trip_date,
							depart_time: values.depart_time,
							from_location: values.from_location,
							to_location: values.to_location,
							dispatcher_note: values.notes,
						},
						__('Đang tạo chuyến từ yêu cầu...')
					);
					return;
				}

				this.call(
					'create_trip',
					{
						vehicle: values.vehicle,
						driver: values.driver,
						trip_date: values.trip_date,
						depart_time: values.depart_time,
						from_location: values.from_location,
						to_location: values.to_location,
						notes: values.notes,
					},
					__('Đang tạo chuyến...')
				);
			},
		});
		d.show();
	}

	sync_trip_dialog_from_requests(dialog) {
		// Route, date and time follow the requests that were ticked, so picking the
		// vehicle is all that is left to do. Overwriting rather than only filling
		// blanks is deliberate: unticking one request and ticking another must move
		// the route with it, not leave the previous one behind.
		if (dialog.get_value('mode') !== 'from_requests') return;

		const chosen = dialog.get_value('requests') || [];
		if (!chosen.length) return;

		const rows = chosen
			.map((name) => this.requests.find((r) => r.name === name))
			.filter(Boolean)
			.sort((a, b) => String(a.request_time || '').localeCompare(String(b.request_time || '')));
		if (!rows.length) return;

		const first = rows[0];
		// "YYYY-MM-DD HH:MM:SS" split by position - parsing it into a Date pushes it
		// through the browser timezone and can land the trip on the wrong day.
		const [date, clock] = String(first.request_time || '').split(' ');

		dialog.set_value('from_location', first.from_location || '');
		dialog.set_value('to_location', first.to_location || '');
		if (date) dialog.set_value('trip_date', date);
		const time = clock_for_control(clock);
		if (time) dialog.set_value('depart_time', time);
	}

	reset_demo_dialog() {
		frappe.warn(
			__('Xoá toàn bộ dữ liệu và tạo lại?'),
			__(
				'Mọi <b>chuyến xe</b> và <b>yêu cầu</b> hiện có sẽ bị xoá vĩnh viễn, rồi dựng lại một tháng dữ liệu mẫu.<br><br>Xe, tài xế và lịch cố định được giữ nguyên. Không thể hoàn tác.'
			),
			() => this.start_reset(),
			__('Xoá và tạo lại')
			// 5th arg of frappe.warn is is_minimizable - deliberately left off:
			// this dialog should be answered, not parked in a corner.
		);
	}

	start_reset() {
		this.$('auto-label').text(__('đang tạo lại dữ liệu mẫu...'));
		frappe
			.call({
				method: PAGE_API + '.reset_demo_data',
				type: 'POST',
				freeze: true,
				freeze_message: __('Đang xếp hàng công việc...'),
			})
			.then((r) => {
				if (!r || !r.message) return;
				frappe.show_alert({
					message: __('Đang tạo lại dữ liệu mẫu ở chế độ nền. Trang sẽ tự cập nhật khi xong.'),
					indicator: 'orange',
				});
			});
	}

	on_reset_finished(data) {
		if (!data) return;
		if (data.success) {
			frappe.show_alert({
				message: __('Đã tạo lại {0} chuyến và {1} yêu cầu.', [data.trips, data.requests]),
				indicator: 'green',
			});
			this.load(true);
		} else {
			frappe.msgprint({
				title: __('Tạo lại dữ liệu thất bại'),
				message: `<pre>${frappe.utils.escape_html(data.error || '')}</pre>`,
				indicator: 'red',
			});
		}
	}

	vehicle_status_dialog() {
		const d = new frappe.ui.Dialog({
			title: __('Đổi trạng thái xe'),
			fields: [
				{ fieldname: 'name', fieldtype: 'Link', options: 'TIQN Vehicle', label: __('Xe'), reqd: 1 },
				{
					fieldname: 'status',
					fieldtype: 'Select',
					label: __('Trạng thái'),
					reqd: 1,
					// in_trip is owned by trip check in / check out and the server
					// refuses it here, so it is not offered.
					options: [
						{ value: 'available', label: __('Đang đỗ') },
						{ value: 'maintenance', label: __('Bảo trì') },
						{ value: 'broken', label: __('Hỏng hóc') },
					],
				},
			],
			primary_action_label: __('Lưu'),
			primary_action: (values) => {
				d.hide();
				this.call('update_vehicle', values, __('Đang cập nhật xe...'));
			},
		});
		d.show();
	}

	// ---------------------------------------------------------------- helpers
	update_date_label() {
		// Built from the YYYY-MM-DD parts. `new Date("2026-09-16")` is parsed as
		// UTC midnight, which lands on the previous day for anyone west of GMT.
		const [y, m, d] = String(this.date).split('-').map(Number);
		if (!y || !m || !d) return;
		const label = new Date(y, m - 1, d).toLocaleDateString('vi-VN', {
			weekday: 'long',
			day: '2-digit',
			month: '2-digit',
			year: 'numeric',
		});
		this.$('date-label').text(label);
	}
}

function request_urgency(request) {
	// `minutes_until` is computed server-side (see _flag_overdue): negative means
	// the vehicle was wanted already. Doing this subtraction in the browser would
	// compare site-local text against the visitor's clock.
	const minutes = request.minutes_until;
	if (minutes === null || minutes === undefined) {
		return { css: '', flag: '', style: '', icon: '', relative: '', colour: '' };
	}

	// The figure shows on EVERY request, not only the late and nearly-due ones.
	// A clock time alone makes the reader do the subtraction; "còn 3 giờ" is the
	// answer they were going to work out anyway.
	const late = minutes < 0;
	const relative = late
		? __('quá giờ {0}', [humanise_minutes(Math.abs(minutes))])
		: __('còn {0}', [humanise_minutes(minutes)]);

	if (late) {
		return {
			css: 'is-late',
			icon: '⚠️',
			style: 'color:#FF4444;font-weight:600',
			colour: '#FF4444',
			relative,
			flag: `<span class="vd-req-flag" style="background:#FF4444">${__('Quá giờ {0}', [
				humanise_minutes(Math.abs(minutes)),
			])}</span>`,
		};
	}

	if (minutes <= DUE_SOON_MINUTES) {
		return {
			css: 'is-soon',
			icon: '⏰',
			style: 'color:#FF8800;font-weight:600',
			colour: '#FF8800',
			relative,
			flag: `<span class="vd-req-flag" style="background:#FF8800">${__('Còn {0}', [
				humanise_minutes(minutes),
			])}</span>`,
		};
	}

	// Amber for a request that is simply waiting - the same amber as the
	// "Chờ duyệt" KPI chip, so the two read as one idea.
	return { css: '', flag: '', style: '', icon: '', colour: '#FFA500', relative };
}

function humanise_minutes(minutes) {
	if (minutes < 1) return __('dưới 1 phút');
	if (minutes < 60) return __('{0} phút', [minutes]);
	const hours = Math.floor(minutes / 60);
	if (hours < 24) {
		const rest = minutes % 60;
		return rest ? __('{0} giờ {1} phút', [hours, rest]) : __('{0} giờ', [hours]);
	}
	return __('{0} ngày', [Math.floor(hours / 24)]);
}

function short_when(request_time, viewing_date) {
	// "18:29" when it is the day being viewed, "17/09 08:00" otherwise. The year
	// and the seconds tell a dispatcher nothing and cost a third of the line.
	if (!request_time) return '';
	const [date, clock] = String(request_time).split(' ');
	const hhmm = (clock || '').slice(0, 5);
	if (date === viewing_date) return hhmm;
	const [, month, day] = date.split('-');
	return `${day}/${month} ${hhmm}`;
}

function clock_for_control(value) {
	// A Frappe Time control validates against sys_defaults.time_format, which is
	// HH:mm:ss - feeding it "14:00" is rejected with
	// "Time 14:00 must be in format: HH:mm:ss" and the field is wiped.
	// `_fmt_time` on the server trims to HH:MM for DISPLAY; anything going back
	// INTO a control has to carry the seconds.
	if (!value) return null;
	const parts = String(value).trim().split(':');
	if (parts.length < 2) return null;
	const pad = (n) => String(cint(n)).padStart(2, '0');
	return `${pad(parts[0])}:${pad(parts[1])}:${pad(parts[2] || 0)}`;
}

function esc(value) {
	return frappe.utils.escape_html(String(value === null || value === undefined ? '' : value));
}
