// Copyright (c) 2026, IT Team - TIQN and contributors
// Door Alert Setting: buttons + status panel. Server side: customize_erpnext.api.door_alerts

const DA_API = "customize_erpnext.api.door_alerts.";

frappe.ui.form.on("Door Alert Setting", {
	refresh(frm) {
		render_status(frm);
		frm.add_custom_button(__("Open Door Control"), () => window.open("/door_control", "_blank"));
	},

	send_test_message(frm) {
		if (frm.is_dirty()) {
			frappe.msgprint(__("Save the settings first, then send the test message."));
			return;
		}
		frappe.call({
			method: DA_API + "send_test_message",
			freeze: true,
			freeze_message: __("Sending..."),
			callback(r) {
				const res = (r.message && r.message.results) || [];
				const lines = res.map(x => `${frappe.utils.escape_html(x.label || x.chat_id)}: ${x.ok ? "✅ " + __("Sent") : "❌ " + frappe.utils.escape_html(x.error || "")}`);
				frappe.msgprint({
					title: __("Test Message"),
					message: lines.join("<br>") || __("No enabled recipient"),
					indicator: res.length && res.every(x => x.ok) ? "green" : "red",
				});
				render_status(frm);
			},
		});
	},

	check_now(frm) {
		if (frm.is_dirty()) {
			frappe.msgprint(__("Save the settings first."));
			return;
		}
		frappe.call({
			method: DA_API + "check_now",
			freeze: true,
			freeze_message: __("Checking doors..."),
			callback(r) {
				const o = r.message || {};
				let msg;
				if (o.muted) msg = __("Checked. Alerts are muted, nothing was sent.");
				else if (!o.events) msg = __("Checked. No new event.");
				else if (o.sent_ok) msg = __("Checked. {0} event(s) sent.", [o.events]);
				else msg = __("Checked. {0} event(s) found but sending failed — see Last Error.", [o.events]);
				frappe.show_alert({ message: msg, indicator: o.sent_ok === false ? "red" : "green" }, 7);
				frm.reload_doc();
			},
		});
	},

	read_sensors(frm) {
		frappe.call({
			method: DA_API + "read_sensors",
			freeze: true,
			freeze_message: __("Reading sensors..."),
			callback(r) {
				const o = r.message || {};
				const esc = frappe.utils.escape_html;
				const state = x => (x.state === "closed" ? __("Door closed") : x.state === "open" ? __("Door open") : "—");
				const rows = (o.doors || []).map(x => `<tr>
					<td><b>${esc(x.door)}</b>${x.sensor_installed ? "" : `<div class="text-muted small">${__("Sensor Installed is off")}</div>`}</td>
					<td>${x.online ? (x.raw ?? "—") : `<span class="text-danger" title="${esc(x.error || "")}">${__("Offline")}</span>`}</td>
					<td>${esc(x.device_sensor_mode || "—")}${x.online && !x.mode_matches ? ` <span class="text-warning">≠ ${esc(x.sensor_type || "")}</span>` : ""}</td>
					<td>${x.online ? state(x) : "—"}</td></tr>`).join("");
				frappe.msgprint({
					title: __("Door Sensors"),
					wide: true,
					message: `<table class="table table-sm"><thead><tr><th>${__("Door")}</th><th>${__("Raw Value")}</th>
						<th>${__("Door Sensor Mode (device)")}</th><th>${__("Means")}</th></tr></thead><tbody>${rows}</tbody></table>
						<div class="small text-muted">${__("Read once with the door closed and once open: the raw value must change. The value while closed is 'Sensor Value When Closed' (now {0}).", [o.closed_value])}</div>`,
				});
			},
		});
	},

	get_chat_ids(frm) {
		if (frm.is_dirty()) {
			frappe.msgprint(__("Save the settings first (the Bot Token must be saved)."));
			return;
		}
		frappe.call({
			method: DA_API + "get_chat_ids",
			freeze: true,
			freeze_message: __("Reading Telegram..."),
			callback(r) {
				const data = r.message || {};
				const fresh = (data.chats || []).filter(c => !c.added);
				if (!fresh.length) {
					frappe.msgprint({
						title: __("Get Chat ID"),
						message: __("No new chat found. Add the bot to the group, send {0} in the group, then press Get Chat ID again.",
							[`<code>/start@${frappe.utils.escape_html(data.bot || "bot")}</code>`]),
					});
					return;
				}
				const d = new frappe.ui.Dialog({
					title: __("Add Recipients"),
					fields: [{
						fieldname: "chats", fieldtype: "MultiCheck", label: __("Chats seen by the bot"),
						options: fresh.map(c => ({
							label: `${c.title} (${c.type}) · ${c.chat_id}`, value: c.chat_id, checked: 1,
						})),
					}],
					primary_action_label: __("Add"),
					primary_action(values) {
						(values.chats || []).forEach(id => {
							const c = fresh.find(x => x.chat_id === id);
							const row = frm.add_child("recipients");
							row.label = c ? c.title : id;
							row.chat_id = id;
							row.enabled = 1;
						});
						frm.refresh_field("recipients");
						d.hide();
						frappe.show_alert({ message: __("Added. Save to keep them."), indicator: "blue" }, 5);
					},
				});
				d.show();
			},
		});
	},
});

function render_status(frm) {
	const wrap = frm.fields_dict.status_html && frm.fields_dict.status_html.$wrapper;
	if (!wrap) return;
	wrap.html(`<div class="text-muted small">${__("Loading...")}</div>`);
	frappe.call({
		method: DA_API + "get_status",
		callback(r) {
			const s = r.message;
			if (!s) return;
			const esc = frappe.utils.escape_html;
			const pill = (color, text) => `<span class="indicator-pill ${color}" style="margin-right:6px">${esc(text)}</span>`;
			const when = v => (v ? frappe.datetime.str_to_user(v) : "—");
			let head = s.enabled ? pill("green", __("Enabled")) : pill("gray", __("Disabled"));
			if (s.muted_until) head += pill("orange", __("Muted until {0}", [frappe.datetime.str_to_user(s.muted_until)]));
			head += pill(s.in_work_hours ? "blue" : "purple", s.in_work_hours ? __("Now: working hours") : __("Now: after hours"));
			if (!s.recipients) head += pill("red", __("No recipient"));

			// IP column only when the server sends IPs (Administrator role)
			const showIp = (s.doors || []).some(d => d.ip_address);
			const rows = (s.doors || []).map(d => `
				<tr>
					<td><b>${esc(d.location || d.device_name)}</b>${d.location ? `<div class="text-muted small">${esc(d.device_name)}</div>` : ""}</td>
					${showIp ? `<td class="text-muted" style="font-family:var(--font-mono, monospace)">${esc(d.ip_address)}</td>` : ""}
					<td>${d.online ? pill("green", __("Online")) : pill("red", __("Offline"))}</td>
					<td>${d.watched ? pill("blue", __("Watched")) : pill("gray", __("Not watched"))}</td>
					${s.use_lock_sensor ? `<td>${d.sensor === "closed" ? pill("green", __("Closed")) : d.sensor === "open" ? pill("orange", __("Open")) : "—"}</td>` : ""}
				</tr>`).join("");
			const doors = rows
				? `<table class="table table-sm" style="margin:8px 0"><thead><tr><th>${__("Door")}</th>${showIp ? "<th>IP</th>" : ""}<th>${__("Connection")}</th><th>${__("Alerts")}</th>${s.use_lock_sensor ? `<th>${__("Door Sensor")}</th>` : ""}</tr></thead><tbody>${rows}</tbody></table>`
				: `<div class="text-muted">${__("No door controller is enabled")}</div>`;

			wrap.html(`
				<div style="margin-bottom:6px">${head}</div>
				${doors}
				<div class="small text-muted">
					${__("Last check")}: <b>${when(s.last_check_at)}</b> ·
					${__("Last sent")}: <b>${when(s.last_sent_at)}</b> ·
					${__("Messages sent today")}: <b>${s.sent_today || 0}</b>
				</div>
				${s.last_error ? `<div class="small" style="color:var(--red-600);margin-top:4px">${__("Last error")}: ${esc(s.last_error)}</div>` : ""}
			`);
		},
	});
}
