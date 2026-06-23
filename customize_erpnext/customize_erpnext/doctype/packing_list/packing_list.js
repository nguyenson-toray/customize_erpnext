// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Packing List", {
	refresh(frm) {
		frm.add_custom_button(__("Generate Carton Detail"), () => generate_cartons(frm));
		frm.add_custom_button(__("Edit Mix"), () => open_mix_dialog(frm));
		frm.add_custom_button(__("Hướng dẫn"), () => show_packing_guide());
		update_carton_summary(frm);
		update_size_color_summary(frm);
	},

	generate_btn(frm) {
		generate_cartons(frm);
	},

	items_text(frm) {
		update_size_color_summary(frm);
	},
});

// Parse the combined Items table (Color, Size, Quantity, ...) the same way the
// server does (tab- or 2+-space separated; duplicate color+size rows summed).
function parse_items_matrix(text) {
	const rawlines = (text || "").split(/\r?\n/).filter((l) => l.trim());
	if (!rawlines.length) return null;
	const split_row = (ln) =>
		ln.includes("\t") ? ln.split("\t") : ln.replace(/\s+$/, "").split(/\s{2,}/);
	const colors = [];
	const sizes = [];
	const qty = {};
	rawlines.forEach((ln) => {
		const c = split_row(ln).map((x) => x.trim());
		if (c.length < 3) return;
		const color = c[0],
			size = c[1];
		if (!color || !size) return;
		if (color.toLowerCase() === "color" || size.toLowerCase() === "size") return;
		const n = parseInt(c[2], 10) || 0;
		if (!(color in qty)) {
			qty[color] = {};
			colors.push(color);
		}
		if (!sizes.includes(size)) sizes.push(size);
		qty[color][size] = (qty[color][size] || 0) + n;
	});
	if (!sizes.length) return null;
	return { sizes, colors, qty };
}

function update_size_color_summary(frm) {
	const field = frm.fields_dict.size_color_summary;
	if (!field) return;
	const m = parse_items_matrix(frm.doc.items_text);
	if (!m) {
		frm.set_df_property("size_color_summary", "options", "");
		frm.refresh_field("size_color_summary");
		return;
	}

	const esc = (s) => frappe.utils.escape_html(String(s == null ? "" : s));
	const num = (n) => (n > 0 ? n : "-");
	const cs = "border:1px solid #c0c8d0;padding:4px 10px;text-align:center";
	const cs_l = cs + ";text-align:left";
	const b = ";font-weight:700";

	const col_tot = {};
	m.sizes.forEach((s) => (col_tot[s] = 0));
	let grand = 0;

	let h = '<table style="border-collapse:collapse;font-size:12px">';
	h += `<tr><th style="${cs_l}${b}">&nbsp;</th>`;
	m.sizes.forEach((s) => (h += `<th style="${cs}${b}">${esc(s)}</th>`));
	h += `<th style="${cs}${b}">${__("Total")}</th></tr>`;

	m.colors.forEach((c) => {
		let rt = 0;
		h += `<tr><td style="${cs_l}${b}">${esc(c)}</td>`;
		m.sizes.forEach((s) => {
			const v = m.qty[c][s] || 0;
			rt += v;
			col_tot[s] += v;
			h += `<td style="${cs}">${num(v)}</td>`;
		});
		grand += rt;
		h += `<td style="${cs}${b}">${num(rt)}</td></tr>`;
	});

	h += `<tr><td style="${cs_l}${b}">${__("Total")}</td>`;
	m.sizes.forEach((s) => (h += `<td style="${cs}${b}">${num(col_tot[s])}</td>`));
	h += `<td style="${cs}${b}">${num(grand)}</td></tr></table>`;

	frm.set_df_property("size_color_summary", "options", h);
	frm.refresh_field("size_color_summary");
}

function show_packing_guide() {
	// Sample data (also used for the Copy button).
	const sample_rows = [
		["Boundary Black", "SM", "39", "200333-116-SM", "196926047493"],
		["Boundary Black", "MD", "130", "200333-116-MD", "196926047509"],
		["Boundary Black", "LG", "170", "200333-116-LG", "196926047516"],
		["Boundary Black", "XL", "107", "200333-116-XL", "196926047523"],
		["Boundary Black", "XXL", "37", "200333-116-XXL", "196926047530"],
		["Mountain Shadow", "SM", "50", "200333-410-SM", "196926047646"],
		["Mountain Shadow", "MD", "157", "200333-410-MD", "196926047653"],
		["Mountain Shadow", "LG", "203", "200333-410-LG", "196926047660"],
		["Mountain Shadow", "XL", "120", "200333-410-XL", "196926047677"],
		["Mountain Shadow", "XXL", "38", "200333-410-XXL", "196926047684"],
		["Redrock", "SM", "12", "200333-610-MD", "196926311679"],
		["Redrock", "MD", "56", "200333-610-LG", "196926311686"],
		["Redrock", "LG", "77", "200333-610-XL", "196926311693"],
		["Redrock", "XL", "44", "200333-610-XXL", "196926311709"],
		["Redrock", "XXL", "11", "200333-610-SM", "196926311662"],
	];
	const sample_head = ["Color", "Size", "Quantity", "SKU", "UPC"];
	const sample_tsv = [sample_head.join("\t")]
		.concat(sample_rows.map((r) => r.join("\t")))
		.join("\n");
	const cell = "border:1px solid #c0c8d0;padding:2px 8px;white-space:nowrap";
	let sample_table = '<table style="border-collapse:collapse;font-size:12px"><tr>';
	sample_head.forEach((h) => (sample_table += `<th style="${cell};font-weight:700">${h}</th>`));
	sample_table += "</tr>";
	sample_rows.forEach((r) => {
		sample_table += "<tr>";
		r.forEach((v, i) => (sample_table += `<td style="${cell}${i === 2 ? ';text-align:right' : ''}">${v}</td>`));
		sample_table += "</tr>";
	});
	sample_table += "</table>";

	const html = `
<div style="font-size:13px;line-height:1.6">
  <h4 style="margin:0 0 6px">📦 Cách sử dụng</h4>
  <ol style="padding-left:18px;margin:0 0 12px">
    <li><b>Loại thùng (Carton Types):</b> khai báo từng loại thùng — Dài×Rộng×Cao (cm), số cái tối đa/thùng, khối lượng thùng rỗng (kg).
      Có thể khai báo 1 hoặc nhiều loại (vd thùng lớn & thùng nhỏ).</li>
    <li><b>Dán 2 bảng</b> (copy thẳng từ Excel, các cột cách nhau bằng <b>Tab</b>):
      <ul style="padding-left:16px">
        <li><b>1. Items:</b> mỗi dòng = 1 (màu + size): <code>Color · Size · Quantity · SKU · UPC</code> (SKU/UPC tùy chọn).</li>
        <li><b>2. Net Weight:</b> khối lượng 1 cái theo từng size.</li>
      </ul>
    </li>
    <li><b>Chọn cách ghép</b> (Combine) và <b>ngưỡng thùng nhỏ</b> (nếu có nhiều loại thùng).</li>
    <li>Bấm <b>Generate Carton Detail</b> → hệ thống tự xếp thùng.</li>
    <li>Bấm <b>Edit Mix</b> để chỉnh tay các <b>thùng ghép</b> (nếu muốn) — số lượng luôn được giữ đúng tổng.</li>
  </ol>

  <h4 style="margin:0 0 6px">⚙️ Thuật toán xếp thùng</h4>
  <ol style="padding-left:18px;margin:0">
    <li><b>Thùng nguyên (đầy):</b> mỗi (màu + size) chia thành các thùng đầy = số cái tối đa/thùng.</li>
    <li><b>Hàng lẻ</b> (phần dư chưa đủ 1 thùng) được <b>ghép</b> theo lựa chọn:
      <ul style="padding-left:16px">
        <li><b>No Combine:</b> mỗi phần lẻ đóng 1 thùng riêng.</li>
        <li><b>By Color:</b> ghép các size <b>cùng màu</b> vào chung thùng.</li>
        <li><b>By Size:</b> ghép các màu <b>cùng size</b> vào chung thùng.</li>
        <li><b>By Color & Size:</b> ghép tất cả để ít thùng nhất.</li>
      </ul>
      👉 <b>Không bao giờ xé lẻ 1 size ra 2 thùng</b> — giữ nguyên cụm của mỗi (màu, size).
    </li>
    <li><b>Chọn loại thùng</b> (khi có ≥ 2 loại): thùng <b>đầy → thùng lớn</b>; thùng <b>chưa đầy → thùng nhỏ</b>.
      Ô <i>"Use Small Carton When Pcs ≤"</i>: thùng có tổng ≤ giá trị này thì dùng thùng nhỏ (0 = mọi thùng chưa đầy đều dùng thùng nhỏ).</li>
    <li><b>Tính toán mỗi thùng:</b> Net = Σ(số cái × khối lượng size); Gross = Net + thùng rỗng; CBM = D×R×C/1.000.000.
      Số container = TỔNG CBM ÷ dung tích loại container.</li>
  </ol>

  <h4 style="margin:12px 0 6px">📋 Bảng chi tiết</h4>
  <ul style="padding-left:18px;margin:0">
    <li><b>Thứ tự:</b> thùng nguyên (theo màu → size) trước → thùng ghép xếp sau, gom theo loại thùng (kích thước 1 → kích thước 2).</li>
    <li><b>Thùng nguyên:</b> 1 màu + 1 size, cột Contents để trống.</li>
    <li><b>Thùng ghép:</b> cột Color/Size/SKU/UPC/Contents liệt kê từng mục, mỗi mục 1 dòng.</li>
    <li><b>Net Weight</b> = Σ(số cái × khối lượng 1 cái theo size); <b>Gross</b> = Net + thùng rỗng.</li>
    <li><b>Gross Weight</b> sửa tay được (vd nhập từ cân điện tử); tổng tự cập nhật khi lưu.</li>
  </ul>

  <h4 style="margin:12px 0 6px">📑 Dữ liệu mẫu cho ô "1. Items"
    <button class="btn btn-xs btn-default copy-sample" style="margin-left:8px">📋 ${__("Copy")}</button>
  </h4>
  <div style="overflow:auto">${sample_table}</div>
</div>`;
	const d = new frappe.ui.Dialog({
		title: __("Hướng dẫn xếp thùng"),
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "guide" }],
	});
	d.fields_dict.guide.$wrapper.html(html);
	d.$wrapper.find(".modal-dialog").css({ "max-width": "960px", width: "80vw" });
	d.$wrapper.find(".copy-sample").on("click", () => {
		frappe.utils.copy_to_clipboard(sample_tsv);
		frappe.show_alert({ message: __("Đã copy dữ liệu mẫu"), indicator: "green" }, 4);
	});
	d.show();
}

// A carton is "mixed" when its Contents holds more than one item line.
function is_mixed_row(d) {
	const c = d.contents || "";
	return c.includes("\n") || c.includes(", ");
}

function update_carton_summary(frm) {
	const field = frm.fields_dict.total_carton_detail;
	if (!field) return;

	const rows = frm.doc.details || [];
	let whole = 0,
		mixed = 0,
		whole_pcs = 0,
		mixed_pcs = 0;
	rows.forEach((d) => {
		if (is_mixed_row(d)) {
			mixed += 1;
			mixed_pcs += cint(d.pcs);
		} else {
			whole += 1;
			whole_pcs += cint(d.pcs);
		}
	});

	const cell = (label, n, pcs, color) =>
		`<div style="flex:1;min-width:120px;border:1px solid #d1d8dd;border-radius:6px;padding:8px 12px">
			<div style="font-size:11px;color:#6c7680;text-transform:uppercase">${label}</div>
			<div style="font-size:18px;font-weight:600;color:${color}">${n}</div>
			<div style="font-size:11px;color:#6c7680">${pcs} ${__("pcs")}</div>
		</div>`;

	const html = `<div style="display:flex;gap:8px;flex-wrap:wrap">
		${cell(__("Whole cartons"), whole, whole_pcs, "#1f272e")}
		${cell(__("Mixed cartons"), mixed, mixed_pcs, "#b9560a")}
		${cell(__("Total cartons"), whole + mixed, whole_pcs + mixed_pcs, "#1f272e")}
	</div>`;

	frm.set_df_property("total_carton_detail", "options", html);
	frm.refresh_field("total_carton_detail");
}

function generate_cartons(frm) {
	frappe.call({
		method: "customize_erpnext.customize_erpnext.doctype.packing_list.packing_list.generate_detail",
		args: { doc: frm.doc },
		freeze: true,
		freeze_message: __("Generating cartons..."),
		callback(r) {
			if (!r.message) return;
			apply_result(frm, r.message);
			frappe.show_alert(
				{ message: __("Generated {0} cartons", [frm.doc.total_carton]), indicator: "green" },
				5
			);
		},
	});
}

function apply_result(frm, message) {
	frm.clear_table("details");
	(message.details || []).forEach((d) => {
		Object.assign(frm.add_child("details"), d);
	});
	frm.set_value(message.totals || {});
	frm.refresh_field("details");
	update_carton_summary(frm);
	update_size_color_summary(frm);
	frm.dirty();
}

// ----------------------------------------------------------------------- //
// Edit Mix dialog
// ----------------------------------------------------------------------- //
function box_label(ct) {
	return `${Math.trunc(ct.length)}*${Math.trunc(ct.width)}*${Math.trunc(ct.height)}`;
}

function parse_contents(s) {
	const out = [];
	(s || "")
		.replace(/, /g, "\n")
		.split(/\n/)
		.forEach((seg) => {
			seg = seg.trim();
			if (!seg) return;
			const ci = seg.lastIndexOf(":");
			if (ci < 0) return;
			const pcs = parseInt(seg.slice(ci + 1), 10); // "5 Pcs" -> 5
			const cs = seg.slice(0, ci);
			const di = cs.lastIndexOf("-");
			if (di < 0 || !pcs) return;
			out.push({ color: cs.slice(0, di).trim(), size: cs.slice(di + 1).trim(), pcs: pcs });
		});
	return out;
}

function open_mix_dialog(frm) {
	const mixed = (frm.doc.details || []).filter((d) => is_mixed_row(d));
	if (!mixed.length) {
		frappe.msgprint(__("There are no mixed cartons to edit. Use a Combine mode, then Generate."));
		return;
	}

	// Columns = the distinct (color, size) pieces in the current mixed cartons.
	const colMap = {};
	const columns = [];
	mixed.forEach((d) =>
		parse_contents(d.contents).forEach((ln) => {
			const key = ln.color + "␟" + ln.size;
			if (!(key in colMap)) {
				colMap[key] = columns.length;
				columns.push({ key, color: ln.color, size: ln.size, need: 0 });
			}
			columns[colMap[key]].need += ln.pcs;
		})
	);

	// Box options + capacity map.
	const boxMax = {};
	(frm.doc.carton_types || []).forEach((ct) => (boxMax[box_label(ct)] = Math.trunc(ct.max_items)));
	const boxOptions = Object.keys(boxMax);
	mixed.forEach((d) => {
		if (d.carton_type && !(d.carton_type in boxMax)) {
			boxMax[d.carton_type] = 0; // unknown cap -> only server validates
			boxOptions.push(d.carton_type);
		}
	});

	// Initial cartons from current mixed details.
	const cartons = mixed.map((d) => {
		const cells = {};
		parse_contents(d.contents).forEach((ln) => (cells[ln.color + "␟" + ln.size] = ln.pcs));
		return { carton_type: d.carton_type || boxOptions[0], cells };
	});

	const dialog = new frappe.ui.Dialog({
		title: __("Edit Carton Mix"),
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "grid" }],
		primary_action_label: __("Apply"),
		primary_action() {
			const payload = cartons
				.map((c) => ({
					carton_type: c.carton_type,
					lines: columns
						.filter((col) => (c.cells[col.key] || 0) > 0)
						.map((col) => ({ color: col.color, size: col.size, pcs: c.cells[col.key] })),
				}))
				.filter((c) => c.lines.length);
			frappe.call({
				method: "customize_erpnext.customize_erpnext.doctype.packing_list.packing_list.apply_mix",
				args: { doc: frm.doc, cartons: payload },
				freeze: true,
				freeze_message: __("Applying..."),
				callback(r) {
					if (!r.message) return;
					apply_result(frm, r.message);
					dialog.hide();
					frappe.show_alert({ message: __("Mix updated"), indicator: "green" }, 5);
				},
			});
		},
	});

	// Widen the modal beyond the extra-large preset for easier editing.
	dialog.$wrapper.find(".modal-dialog").css({ "max-width": "96vw", width: "96vw" });

	const $wrap = dialog.fields_dict.grid.$wrapper;

	function esc(s) {
		return frappe.utils.escape_html(String(s == null ? "" : s));
	}

	function render() {
		let h =
			'<div style="overflow:auto;max-height:65vh"><table class="table table-bordered" style="font-size:13px">';
		h += "<thead><tr><th>#</th><th>" + __("Carton Type") + "</th>";
		columns.forEach((col) => (h += `<th class="text-center">${esc(col.color)}<br>${esc(col.size)}</th>`));
		h += "<th class='text-center'>" + __("Total") + "</th><th></th></tr></thead><tbody>";

		cartons.forEach((c, i) => {
			h += `<tr data-row="${i}"><td>${i + 1}</td><td><select class="form-control input-xs ct-box" data-row="${i}">`;
			boxOptions.forEach(
				(o) =>
					(h += `<option value="${esc(o)}" ${o === c.carton_type ? "selected" : ""}>${esc(o)}</option>`)
			);
			h += "</select></td>";
			columns.forEach((col) => {
				const v = c.cells[col.key] || 0;
				h += `<td><input type="number" min="0" class="form-control input-xs ct-cell text-right" data-row="${i}" data-key="${esc(
					col.key
				)}" value="${v || ""}" style="width:60px"></td>`;
			});
			h += `<td class="text-right ct-rowtot" data-row="${i}"></td>`;
			h += `<td><button class="btn btn-xs btn-danger ct-del" data-row="${i}">&times;</button></td></tr>`;
		});

		h += "</tbody><tfoot><tr><th colspan='2' class='text-right'>" + __("Placed / Needed") + "</th>";
		columns.forEach((col) => (h += `<th class="text-center ct-foot" data-key="${esc(col.key)}"></th>`));
		h += "<th></th><th></th></tr></tfoot></table></div>";
		h +=
			'<button class="btn btn-xs btn-default ct-add" style="margin-top:6px">+ ' +
			__("Add carton") +
			'</button> <span class="ct-status" style="margin-left:12px"></span>';

		$wrap.html(h);
		bind();
		recompute();
	}

	function bind() {
		$wrap.find(".ct-cell").on("input", function () {
			const i = +$(this).data("row");
			const key = $(this).data("key");
			cartons[i].cells[key] = parseInt(this.value, 10) || 0;
			recompute();
		});
		$wrap.find(".ct-box").on("change", function () {
			cartons[+$(this).data("row")].carton_type = this.value;
			recompute();
		});
		$wrap.find(".ct-del").on("click", function () {
			cartons.splice(+$(this).data("row"), 1);
			if (!cartons.length) cartons.push({ carton_type: boxOptions[0], cells: {} });
			render();
		});
		$wrap.find(".ct-add").on("click", function () {
			cartons.push({ carton_type: boxOptions[0], cells: {} });
			render();
		});
	}

	function recompute() {
		let balanced = true;
		// Per-column placed totals.
		columns.forEach((col) => {
			let placed = 0;
			cartons.forEach((c) => (placed += c.cells[col.key] || 0));
			const ok = placed === col.need;
			if (!ok) balanced = false;
			$wrap
				.find(`.ct-foot[data-key="${CSS.escape(col.key)}"]`)
				.html(`${placed} / ${col.need}`)
				.css("color", ok ? "" : "#c0392b");
		});
		// Per-row totals vs capacity.
		cartons.forEach((c, i) => {
			let tot = 0;
			columns.forEach((col) => (tot += c.cells[col.key] || 0));
			const max = boxMax[c.carton_type] || 0;
			const over = max && tot > max;
			if (over) balanced = false;
			$wrap
				.find(`.ct-rowtot[data-row="${i}"]`)
				.html(max ? `${tot} / ${max}` : `${tot}`)
				.css("color", over ? "#c0392b" : "");
		});
		$wrap
			.find(".ct-status")
			.html(balanced ? __("Balanced ✓") : __("Not balanced — fix the red cells"))
			.css("color", balanced ? "#27ae60" : "#c0392b");
		dialog.get_primary_btn().prop("disabled", !balanced);
	}

	render();
	dialog.show();
}
