// Headless harness: runs hide_restricted_export_fields.js against a stubbed DOM/frappe.
const fs = require("fs"), vm = require("vm"), assert = require("assert");
const SRC = "/home/frappe/frappe-bench/apps/customize_erpnext/customize_erpnext/public/js/hide_restricted_export_fields.js";

function makeModal(spec) {
	// spec: { blocks: [{fieldname, doctype, rows:[{fieldname, checked}]}] }
	const blocks = spec.blocks.map((b) => {
		const control = { options: b.rows.map((r) => ({ value: r.fieldname })),
		                  selected_options: b.rows.filter((r) => r.checked).map((r) => r.fieldname) };
		const el = { attrs: { "data-fieldname": b.fieldname, "data-fieldtype": "MultiCheck" },
		             fieldobj: control, block: b };
		b.control = control; b.el = el;
		return b;
	});
	return { blocks };
}

function makeJQ(modal) {
	const wrap = (block) => ({
		remove() { block.block_removed = true; },
		find(sel) {
			const m = /data-unit="(.*)"\]$/.exec(sel);
			const fn = m && m[1];
			const row = block.rows.find((r) => r.fieldname === fn && !r.removed);
			if (!row) return { length: 0 };
			return {
				length: 1,
				prop(n, v) { if (v === undefined) return !!row.checked; row.checked = v; return this; },
				trigger() { block.control.selected_options =
					block.control.selected_options.filter((x) => x !== row.fieldname); return this; },
				closest(s) { return { length: s === ".unit-checkbox" ? 1 : 0,
				                      remove() { row.removed = true; } }; },
				remove() { row.removed = true; },
			};
		},
	});
	const $ = (el) => {
		if (el && el.attrs) return { attr: (n) => el.attrs[n] };
		if (el === "document" || el === undefined) return { on() {} };
		return { on() {} };
	};
	$.modal = {
		find(sel) {
			if (sel.includes("MultiCheck")) return { toArray: () => modal.blocks.map((b) => b.el) };
			return { first: () => ({ text: () => "Export Data" }) };
		},
	};
	modal.blocks.forEach((b) => { b.el.$w = wrap(b); });
	return $;
}

function run(name, { metas, perms, user, roles, config, spec, expect }) {
	const modal = makeModal(spec);
	const $ = makeJQ(modal);
	// patch: get_multicheck_controls builds {$wrapper: $(el)} — give it our wrapper instead
	const $orig = $;
	const $patched = (el) => (el && el.$w ? Object.assign({}, $orig(el), el.$w) : $orig(el));
	Object.assign($patched, $orig);

	const warns = [], errors = [];
	const sandbox = {
		console: { log() {}, warn: (...a) => warns.push(a.join(" ")), error: (...a) => errors.push(a.join(" ")) },
		cint: (v) => parseInt(v, 10) || 0,
		__: (s) => s,
		$: $patched,
		window: {},
		document: { __fake: true },
		fetch: () => (config === "BROKEN"
			? Promise.reject(new Error("boom"))
			: Promise.resolve({ ok: true, json: () => Promise.resolve(config || {}) })),
		frappe: {
			provide(ns) { let o = sandbox; ns.split(".").forEach((p) => (o = o[p] = o[p] || {})); },
			session: { user },
			user_roles: roles,
			boot: { developer_mode: 1 },
			get_meta: (dt) => metas[dt] || null,
			get_route: () => [],
			meta: { get_docfield: (dt, fn) => (metas[dt].table_fields || {})[fn] || null },
			model: { core_doctypes_list: ["User", "DocType"] },
			perm: { has_perm: (dt, lvl) => !!(perms[dt] || {})[lvl] },
		},
	};
	sandbox.window = sandbox;
	vm.createContext(sandbox);
	vm.runInContext(fs.readFileSync(SRC, "utf8"), sandbox);

	sandbox.customize_erpnext.export_field_perms.filter_export_dialog($.modal);

	return new Promise((res) => setImmediate(() => setImmediate(() => {
		const gone = {};
		modal.blocks.forEach((b) => { gone[b.doctype] = b.rows.filter((r) => r.removed).map((r) => r.fieldname); });
		const left_in_options = {};
		modal.blocks.forEach((b) => { left_in_options[b.doctype] = b.control.options.map((o) => o.value); });
		try {
			expect({ gone, left_in_options, warns, errors, modal });
			console.log(`  PASS  ${name}`);
			res(true);
		} catch (e) {
			console.log(`  FAIL  ${name}\n        ${e.message}`);
			res(false);
		}
	})));
}

// ---- fixtures ------------------------------------------------------------------
const TS_METAS = {
	Timesheet: {
		name: "Timesheet",
		permissions: [{ role: "Accounts User", permlevel: 1, read: 1 }],
		fields: [{ fieldname: "employee", permlevel: 0 }, { fieldname: "billing_details", permlevel: 1 }],
		table_fields: { time_logs: { fieldname: "time_logs", options: "Timesheet Detail" } },
	},
	"Timesheet Detail": {
		name: "Timesheet Detail",
		fields: [{ fieldname: "activity_type", permlevel: 0 }, { fieldname: "billing_rate", permlevel: 1 },
		         { fieldname: "costing_rate", permlevel: 1 }],
	},
};
const TS_SPEC = {
	blocks: [
		{ fieldname: "Timesheet", doctype: "Timesheet",
		  rows: [{ fieldname: "name", checked: true }, { fieldname: "employee" }, { fieldname: "billing_details" }] },
		{ fieldname: "time_logs", doctype: "Timesheet Detail",
		  rows: [{ fieldname: "name", checked: true }, { fieldname: "activity_type" },
		         { fieldname: "billing_rate", checked: true }, { fieldname: "costing_rate" }] },
	],
};
const EMP_METAS = {
	Employee: { name: "Employee", permissions: [{ role: "HR User", permlevel: 0, read: 1 }],
	            fields: [{ fieldname: "image", permlevel: 0 }, { fieldname: "scheduled_confirmation_date", permlevel: 0 },
	                     { fieldname: "employee_name", permlevel: 0 }], table_fields: {} },
};
const EMP_SPEC = { blocks: [{ fieldname: "Employee", doctype: "Employee",
	rows: [{ fieldname: "name", checked: true }, { fieldname: "image" },
	       { fieldname: "scheduled_confirmation_date" }, { fieldname: "employee_name" }] }] };

// ---- cases ---------------------------------------------------------------------
(async () => {
	const results = [];

	results.push(await run("pass1: HR User loses the 3 permlevel-1 fields (parent + child)", {
		metas: TS_METAS, perms: { Timesheet: { 0: 1 } }, user: "hr@x", roles: ["HR User", "All"],
		spec: JSON.parse(JSON.stringify(TS_SPEC)),
		expect: ({ gone, left_in_options }) => {
			assert.deepStrictEqual(gone["Timesheet"].sort(), ["billing_details"]);
			assert.deepStrictEqual(gone["Timesheet Detail"].sort(), ["billing_rate", "costing_rate"]);
			assert.ok(!left_in_options["Timesheet Detail"].includes("billing_rate"), "spliced from options");
			assert.ok(left_in_options["Timesheet Detail"].includes("name"), "ID kept");
		},
	}));

	results.push(await run("pass1: Accounts User keeps them (has read at level 1)", {
		metas: TS_METAS, perms: { Timesheet: { 0: 1, 1: 1 } }, user: "acc@x", roles: ["Accounts User", "All"],
		spec: JSON.parse(JSON.stringify(TS_SPEC)),
		expect: ({ gone }) => { assert.deepStrictEqual(gone["Timesheet"], []);
		                        assert.deepStrictEqual(gone["Timesheet Detail"], []); },
	}));

	results.push(await run("pass1: Administrator skipped entirely", {
		metas: TS_METAS, perms: { Timesheet: { 0: 1 } }, user: "Administrator", roles: ["All"],
		spec: JSON.parse(JSON.stringify(TS_SPEC)),
		expect: ({ gone }) => { assert.deepStrictEqual(gone["Timesheet Detail"], []); },
	}));

	results.push(await run("pass1: System Manager skipped entirely", {
		metas: TS_METAS, perms: { Timesheet: { 0: 1 } }, user: "sm@x", roles: ["System Manager", "All"],
		spec: JSON.parse(JSON.stringify(TS_SPEC)),
		expect: ({ gone }) => { assert.deepStrictEqual(gone["Timesheet Detail"], []); },
	}));

	results.push(await run("pass1: a checked restricted field is unchecked before removal", {
		metas: TS_METAS, perms: { Timesheet: { 0: 1 } }, user: "hr@x", roles: ["HR User"],
		spec: JSON.parse(JSON.stringify(TS_SPEC)),
		expect: ({ modal }) => {
			const child = modal.blocks[1];
			assert.ok(!child.control.selected_options.includes("billing_rate"),
				"billing_rate must leave selected_options");
			assert.ok(child.control.selected_options.includes("name"), "name stays selected");
		},
	}));

	results.push(await run("pass2: JSON list removes Employee.image + offer date", {
		metas: EMP_METAS, perms: { Employee: { 0: 1 } }, user: "hr@x", roles: ["HR User"],
		config: { Employee: ["image", "scheduled_confirmation_date"] },
		spec: JSON.parse(JSON.stringify(EMP_SPEC)),
		expect: ({ gone }) => assert.deepStrictEqual(gone["Employee"].sort(),
			["image", "scheduled_confirmation_date"]),
	}));

	results.push(await run("pass2: applies to Administrator too", {
		metas: EMP_METAS, perms: { Employee: { 0: 1 } }, user: "Administrator", roles: ["All"],
		config: { Employee: ["image"] }, spec: JSON.parse(JSON.stringify(EMP_SPEC)),
		expect: ({ gone }) => assert.deepStrictEqual(gone["Employee"], ["image"]),
	}));

	results.push(await run("pass2: 'name' refused, typo warned, __readme__ ignored", {
		metas: EMP_METAS, perms: { Employee: { 0: 1 } }, user: "hr@x", roles: ["HR User"],
		config: { __readme__: "note", Employee: ["name", "no_such_field", "image"] },
		spec: JSON.parse(JSON.stringify(EMP_SPEC)),
		expect: ({ gone, warns }) => {
			assert.deepStrictEqual(gone["Employee"], ["image"]);
			assert.ok(warns.some((w) => w.includes("ID column cannot be hidden")), "name refused");
			assert.ok(warns.some((w) => w.includes("not in the picker")), "typo warned");
		},
	}));

	results.push(await run("pass2: child DocType key hides in the child block", {
		metas: TS_METAS, perms: { Timesheet: { 0: 1, 1: 1 } }, user: "acc@x", roles: ["Accounts User"],
		config: { "Timesheet Detail": ["activity_type"] }, spec: JSON.parse(JSON.stringify(TS_SPEC)),
		expect: ({ gone }) => assert.deepStrictEqual(gone["Timesheet Detail"], ["activity_type"]),
	}));

	results.push(await run("robust: broken/unreachable JSON -> pass1 still applied, no throw", {
		metas: TS_METAS, perms: { Timesheet: { 0: 1 } }, user: "hr@x", roles: ["HR User"],
		config: "BROKEN", spec: JSON.parse(JSON.stringify(TS_SPEC)),
		expect: ({ gone, errors }) => {
			assert.deepStrictEqual(gone["Timesheet Detail"].sort(), ["billing_rate", "costing_rate"]);
			assert.deepStrictEqual(errors, []);
		},
	}));

	// ---- child-block fixtures ----
	const EMP2_METAS = {
		Employee: {
			name: "Employee",
			permissions: [{ role: "HR User", permlevel: 0, read: 1 }],
			fields: [
				{ fieldname: "image", permlevel: 0, fieldtype: "Attach Image" },
				{ fieldname: "custom_fingerprints", permlevel: 0, fieldtype: "Table" },
				{ fieldname: "secret_table", permlevel: 1, fieldtype: "Table" },
			],
			table_fields: {
				custom_fingerprints: { fieldname: "custom_fingerprints", fieldtype: "Table", options: "Fingerprint Data" },
				secret_table: { fieldname: "secret_table", fieldtype: "Table", options: "Secret Child" },
			},
		},
		"Fingerprint Data": { name: "Fingerprint Data", fields: [{ fieldname: "finger_index", permlevel: 0 },
		                                                         { fieldname: "template", permlevel: 0 }] },
		"Secret Child": { name: "Secret Child", fields: [{ fieldname: "amount", permlevel: 0 }] },
	};
	const EMP2_SPEC = () => JSON.parse(JSON.stringify({
		blocks: [
			{ fieldname: "Employee", doctype: "Employee",
			  rows: [{ fieldname: "name", checked: true }, { fieldname: "image" }] },
			{ fieldname: "custom_fingerprints", doctype: "Fingerprint Data",
			  rows: [{ fieldname: "name", checked: true }, { fieldname: "finger_index" }, { fieldname: "template" }] },
			{ fieldname: "secret_table", doctype: "Secret Child",
			  rows: [{ fieldname: "name", checked: true }, { fieldname: "amount" }] },
		],
	}));

	results.push(await run("pass2: Table fieldname wipes the WHOLE child block", {
		metas: EMP2_METAS, perms: { Employee: { 0: 1, 1: 1 } }, user: "hr@x", roles: ["HR User"],
		config: { Employee: ["custom_fingerprints"] }, spec: EMP2_SPEC(),
		expect: ({ modal, warns }) => {
			const fp = modal.blocks.find((b) => b.doctype === "Fingerprint Data");
			assert.ok(fp.block_removed, "child wrapper must be removed from the DOM");
			assert.deepStrictEqual(fp.control.options, [], "options emptied -> Select All cannot pick it");
			assert.deepStrictEqual(fp.control.selected_options, [], "selected_options emptied");
			assert.ok(!warns.some((w) => w.includes("not in the picker")), "no false typo warning");
		},
	}));

	results.push(await run("pass2: entries for a child DocType already wiped are not reported as typos", {
		metas: EMP2_METAS, perms: { Employee: { 0: 1, 1: 1 } }, user: "hr@x", roles: ["HR User"],
		config: { Employee: ["custom_fingerprints"], "Fingerprint Data": ["template"] }, spec: EMP2_SPEC(),
		expect: ({ modal, warns }) => {
			assert.ok(modal.blocks.find((b) => b.doctype === "Fingerprint Data").block_removed);
			assert.ok(!warns.some((w) => w.includes("not in the picker")), "dropped block is skipped, not warned");
		},
	}));

	results.push(await run("pass2: sibling child blocks and the parent survive", {
		metas: EMP2_METAS, perms: { Employee: { 0: 1, 1: 1 } }, user: "hr@x", roles: ["HR User"],
		config: { Employee: ["custom_fingerprints", "image"] }, spec: EMP2_SPEC(),
		expect: ({ modal, gone }) => {
			assert.ok(!modal.blocks.find((b) => b.doctype === "Secret Child").block_removed, "sibling kept");
			assert.ok(!modal.blocks.find((b) => b.doctype === "Employee").block_removed, "parent kept");
			assert.deepStrictEqual(gone["Employee"], ["image"], "plain field still removed in the same pass");
		},
	}));

	results.push(await run("pass1: a permlevel-restricted Table field wipes its child block", {
		metas: EMP2_METAS, perms: { Employee: { 0: 1 } }, user: "hr@x", roles: ["HR User"],
		spec: EMP2_SPEC(),
		expect: ({ modal }) => {
			assert.ok(modal.blocks.find((b) => b.doctype === "Secret Child").block_removed,
				"secret_table is permlevel 1 -> whole block goes");
			assert.ok(!modal.blocks.find((b) => b.doctype === "Fingerprint Data").block_removed,
				"permlevel 0 table stays");
		},
	}));

	results.push(await run("pass1 + pass2 together: both child blocks gone, no crash", {
		metas: EMP2_METAS, perms: { Employee: { 0: 1 } }, user: "hr@x", roles: ["HR User"],
		config: { Employee: ["custom_fingerprints"] }, spec: EMP2_SPEC(),
		expect: ({ modal, errors }) => {
			assert.ok(modal.blocks.find((b) => b.doctype === "Secret Child").block_removed);
			assert.ok(modal.blocks.find((b) => b.doctype === "Fingerprint Data").block_removed);
			assert.deepStrictEqual(errors, []);
		},
	}));

	const failed = results.filter((r) => !r).length;
	console.log(`\n${results.length - failed}/${results.length} passed`);
	process.exit(failed ? 1 : 0);
})();
