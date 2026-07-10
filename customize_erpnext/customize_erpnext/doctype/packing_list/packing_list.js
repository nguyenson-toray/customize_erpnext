// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Packing List", {
	refresh(frm) {
		frm.add_custom_button(__("Generate Carton Detail"), () => generate_cartons(frm));
		frm.add_custom_button(__("Edit Mix"), () => open_mix_dialog(frm));
		frm.add_custom_button(__("📷 Chụp / Cân"), () => carton_action(frm));
		frm.add_custom_button(__("⬇ Download Photo"), () => download_all_carton_photos(frm));
		frm.add_custom_button(__("Hướng dẫn"), () => show_packing_guide());
		// Đọc cân trực tiếp qua Web Serial (chỉ Chrome/Edge + HTTPS).
		if (window.plScale && plScale.supported()) {
			frm.add_custom_button(__("⚙️ Scale Settings"), () => plScale.settingsDialog(), __("Cân"));
			scale_indicator(frm);
			plScale.tryReconnect(); // tự nối lại cổng đã cấp quyền
		}
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

// Reverse weight: when Gross is entered (from scale) in "Gross to Net" mode,
// derive Net = Gross - empty carton, and refresh the weight totals live.
frappe.ui.form.on("Packing List Detail", {
	gross_weight(frm, cdt, cdn) {
		if ((frm.doc.weight_mode || "") !== "Gross to Net") return;
		const row = locals[cdt][cdn];
		row.net_weight = flt(flt(row.gross_weight) - flt(row.empty_weight), 3);
		frm.refresh_field("details");
		sum_weight_totals(frm);
	},
});

function sum_weight_totals(frm) {
	let net = 0,
		gross = 0;
	(frm.doc.details || []).forEach((d) => {
		net += flt(d.net_weight);
		gross += flt(d.gross_weight);
	});
	frm.set_value("total_net_weight", flt(net, 3));
	frm.set_value("total_gross_weight", flt(gross, 3));
}

// Lưu gom (coalesce): tránh nhiều frm.save() chồng nhau khi cân/chụp liên tiếp
// (save đang chạy mà gọi tiếp -> lỗi "Document has been modified").
function pl_save(frm) {
	if (frm.__pl_saving) {
		frm.__pl_save_again = true;
		return frm.__pl_saving;
	}
	frm.__pl_saving = frm
		.save()
		.catch(() => {})
		.finally(() => {
			frm.__pl_saving = null;
			if (frm.__pl_save_again) {
				frm.__pl_save_again = false;
				pl_save(frm);
			}
		});
	return frm.__pl_saving;
}

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

  <h4 style="margin:12px 0 6px">📷 Chụp ảnh & Cân (sau khi đã chốt thùng)</h4>
  <ul style="padding-left:18px;margin:0">
    <li><b>Weight Source</b> (chỉ khi Weight Mode = <i>Gross to Net</i>): <b>Scale</b> = đọc từ cân điện tử;
      <b>OCR</b> = đọc số trên ảnh. Cả 2 đều cho nhập kg tay.</li>
    <li>Bấm <b>📷 Chụp / Cân</b>: tích 1 thùng (hoặc bỏ tích → nhập số thùng bắt đầu). Trong dialog chọn <b>Chế độ</b>:
      <b>Chụp ảnh + Cân</b> / <b>Chỉ chụp ảnh</b> / <b>Chỉ cân</b>.</li>
    <li>Tick <b>Liên tiếp (tự sang thùng kế)</b> để làm cả loạt không phải chọn từng thùng.
      Với <i>Chỉ cân</i>: đặt thùng lên cân → số ổn định (ST) tự điền → <b>Enter</b> ghi & sang thùng kế; <b>Esc</b> thoát.</li>
    <li><b>Scale:</b> cân trước — số cân hiện trực tiếp; <b>📷 Chụp & Lưu</b> lưu ảnh + ghi Gross cùng lúc.
      <b>OCR:</b> chụp xong tự đọc số trên ảnh; nếu sai bấm <b>📷 Chụp cận màn hình cân</b> để đọc lại (ảnh cận không lưu).</li>
    <li>Cấu hình cổng cân ở <b>⚙️ Scale Settings</b> (Chrome/Edge + HTTPS). <b>⬇ Download Photo</b> tải toàn bộ ảnh (zip).</li>
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
	const run = (force) =>
		frappe.call({
			method: "customize_erpnext.customize_erpnext.doctype.packing_list.packing_list.generate_detail",
			args: { doc: frm.doc, force: force ? 1 : 0 },
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

	if ((frm.doc.details || []).some((d) => d.photo)) {
		frappe.confirm(
			__("The carton image has been taken — recreating it will DELETE all previously taken images and weight data. Continue ?"),
			() => run(true) // Yes
		);
		return;
	}
	run(false);
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

// ----------------------------------------------------------------------- //
// Carton photos: capture -> crop -> resize/compress -> save; download all
// ----------------------------------------------------------------------- //
const PL_CAM_KEY = "pl_camera_id";
const PL_MODE_KEY = "pl_capture_mode";
const PL_CONT_KEY = "pl_capture_cont";
const M_BOTH = "Chụp ảnh + Cân";
const M_PHOTO = "Chỉ chụp ảnh";
const M_SCALE = "Chỉ cân";

// Thùng kế tiếp theo carton_no.
function next_carton(frm, no) {
	return (frm.doc.details || []).find((r) => r.carton_no === no + 1) || null;
}

// Thùng đầu tiên cần xử lý: chưa có ảnh; nếu tất cả đã có ảnh -> chưa có Gross; else #1.
function first_carton_needing(frm) {
	const rows = (frm.doc.details || []).slice().sort((a, b) => a.carton_no - b.carton_no);
	if (!rows.length) return null;
	return (
		rows.find((r) => !r.photo) ||
		rows.find((r) => !flt(r.gross_weight)) ||
		rows[0]
	);
}

// Nút gộp "Chụp / Cân": xác định thùng bắt đầu (đã tích, hoặc nhập số thùng — mặc định
// thùng cần xử lý) rồi mở dialog. Trong dialog có "Liên tiếp" để tự sang thùng kế.
function carton_action(frm) {
	if (frm.is_new()) {
		frappe.msgprint(__("Lưu Packing List trước khi chụp/cân."));
		return;
	}
	if (!(frm.doc.details || []).length) {
		frappe.msgprint(__("Chưa có thùng nào — bấm Generate Carton Detail trước."));
		return;
	}
	const sel = frm.fields_dict.details.grid.get_selected_children();
	if (sel.length > 1) {
		frappe.msgprint(__("Chỉ tích 1 dòng thùng (hoặc bỏ tích để chọn theo số thùng)."));
		return;
	}
	if (sel.length === 1) return open_capture_dialog(frm, sel[0]);
	// Chưa chọn thùng -> nhập số thùng bắt đầu (mặc định thùng cần xử lý).
	const start = first_carton_needing(frm);
	frappe.prompt(
		[
			{
				fieldtype: "Int",
				fieldname: "carton_no",
				label: __("Bắt đầu từ thùng số (Carton No)"),
				default: start ? start.carton_no : 1,
				reqd: 1,
			},
		],
		(v) => {
			const row = (frm.doc.details || []).find((r) => cint(r.carton_no) === cint(v.carton_no));
			if (!row) {
				frappe.msgprint(__("Không tìm thấy thùng #{0}.", [v.carton_no]));
				return;
			}
			select_next_carton(frm, row.carton_no);
			open_capture_dialog(frm, row);
		},
		__("Chọn thùng để chụp / cân"),
		__("Tiếp tục")
	);
}

// 1 dialog gộp cho 1 thùng: chụp ảnh và/hoặc đọc cân theo Chế độ (nhớ lựa chọn).
// force_continuous: khi mở lại tự động cho thùng kế (giữ trạng thái Liên tiếp).
function open_capture_dialog(frm, row, force_continuous) {
	// Panel cân chỉ khi Gross to Net + weight_source = Scale + trình duyệt hỗ trợ.
	const scale_available =
		(frm.doc.weight_mode || "") === "Gross to Net" &&
		(frm.doc.weight_source || "OCR") === "Scale" &&
		window.plScale &&
		plScale.supported();
	const has_cam = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

	let curRow = row; // thùng đang xử lý (đổi khi Liên tiếp sang thùng kế)
	const modes = [M_BOTH, M_PHOTO];
	if (scale_available) modes.push(M_SCALE);
	let mode = localStorage.getItem(PL_MODE_KEY) || M_BOTH;
	if (!modes.includes(mode)) mode = M_BOTH;
	const cont_default = force_continuous || localStorage.getItem(PL_CONT_KEY) === "1" ? 1 : 0;

	const d = new frappe.ui.Dialog({
		title: __("Chụp / Cân — thùng #{0}", [curRow.carton_no]),
		fields: [
			{ fieldtype: "Select", fieldname: "mode", label: __("Chế độ"), options: modes.join("\n"), default: mode },
			{
				fieldtype: "Check",
				fieldname: "continuous",
				label: __("Liên tiếp (tự sang thùng kế)"),
				default: cont_default,
			},
			{ fieldtype: "HTML", fieldname: "cam" },
			{ fieldtype: "HTML", fieldname: "picker" },
			{ fieldtype: "HTML", fieldname: "scale_live" },
			{ fieldtype: "Float", fieldname: "scale_weight", label: __("Số cân / Gross (kg)"), precision: 3 },
		],
		primary_action_label: __("Thực hiện"),
		primary_action() {
			do_action();
		},
	});
	// Đổi tiêu đề + số thùng hiển thị khi sang thùng kế.
	const update_target = () => {
		d.set_title(__("Chụp / Cân — thùng #{0}", [curRow.carton_no]));
		d.$wrapper.find(".sc-cn").text(curRow.carton_no);
	};

	let stream = null;
	let offScale = null;
	let closed = false; // dialog đã đóng chưa (chặn race getUserMedia resolve sau khi đóng)
	const stop_cam = () => {
		if (stream) {
			stream.getTracks().forEach((t) => t.stop());
			stream = null;
		}
	};
	const stop_scale = () => {
		if (offScale) {
			offScale();
			offScale = null;
		}
	};
	const cleanup = () => {
		closed = true;
		stop_cam();
		stop_scale();
	};
	d.onhide = cleanup;

	// ---------- Camera ----------
	d.fields_dict.cam.$wrapper.html(
		has_cam
			? '<video autoplay playsinline muted style="width:100%;max-height:55vh;background:#000"></video>'
			: `<div class="text-muted small" style="padding:8px">${__(
					"Camera trong dialog cần HTTPS. Bấm Chụp & Lưu để mở camera thiết bị / chọn ảnh."
			  )}</div>`
	);
	const refresh_devices = () =>
		navigator.mediaDevices.enumerateDevices().then((list) => {
			const cams = list.filter((x) => x.kind === "videoinput");
			if (cams.length < 2) {
				d.fields_dict.picker.$wrapper.html("");
				return;
			}
			const cur =
				(stream && stream.getVideoTracks()[0] && stream.getVideoTracks()[0].getSettings().deviceId) ||
				localStorage.getItem(PL_CAM_KEY) ||
				"";
			const opts = cams
				.map(
					(c, i) =>
						`<option value="${c.deviceId}"${c.deviceId === cur ? " selected" : ""}>${frappe.utils.escape_html(
							c.label || __("Camera {0}", [i + 1])
						)}</option>`
				)
				.join("");
			d.fields_dict.picker.$wrapper.html(
				`<label class="small text-muted" style="display:block;margin-top:6px">${__("Chọn camera")}</label>
				<select class="form-control input-sm pl-cam-sel">${opts}</select>`
			);
		});
	const start_stream = (deviceId) => {
		if (!has_cam || closed) return Promise.resolve();
		stop_cam();
		const constraints = deviceId
			? { video: { deviceId: { exact: deviceId } } }
			: { video: { facingMode: { ideal: "environment" } } };
		return navigator.mediaDevices
			.getUserMedia(constraints)
			.then((s) => {
				// Dialog đã đóng trong lúc chờ quyền camera -> tắt ngay, tránh leak.
				if (closed) {
					s.getTracks().forEach((t) => t.stop());
					return;
				}
				stream = s;
				const v = d.fields_dict.cam.$wrapper.find("video")[0];
				if (v) v.srcObject = s;
				return refresh_devices();
			})
			.catch(() => {
				if (deviceId) {
					frappe.show_alert(
						{ message: __("Không mở được webcam đã chọn, dùng camera mặc định."), indicator: "orange" },
						4
					);
					localStorage.removeItem(PL_CAM_KEY);
					return start_stream(null);
				}
				frappe.show_alert({ message: __("Không mở được camera trong dialog."), indicator: "orange" }, 4);
			});
	};
	d.$wrapper.on("change", ".pl-cam-sel", function () {
		localStorage.setItem(PL_CAM_KEY, this.value);
		start_stream(this.value);
	});

	// ---------- Cân ----------
	d.fields_dict.scale_live.$wrapper.html(
		`<div class="text-center" style="padding:2px 0">
			<span class="sc-flag small text-muted">${__("Đang chờ cân…")}</span>
			<span class="sc-num" style="font-size:28px;font-weight:700;margin-left:8px">--</span>
			<button class="btn btn-xs btn-default sc-reweigh" style="margin-left:8px">🔄 ${__("Cân lại")}</button>
			<div class="small text-muted">${__("Thùng")} #<b class="sc-cn">${curRow.carton_no}</b></div>
		</div>`
	);
	const read_stable = () =>
		plScale
			.readStableWeight({ timeoutMs: 8000, needConsecutive: 3 })
			.then((w) => d.set_value("scale_weight", flt(w, 3)))
			.catch(() => {});
	d.$wrapper.on("click", ".sc-reweigh", read_stable);
	const start_scale = () => {
		if (offScale) return;
		offScale = plScale.onReading((p) => {
			if (!p) return;
			d.$wrapper.find(".sc-num").text(p.weight.toFixed(3)).css("color", p.stable ? "#27ae60" : "#c0392b");
			d.$wrapper.find(".sc-flag").text(p.stable ? "ST — ổn định" : "US — chưa ổn định");
			// ST -> tự điền số cân (weighing liên tiếp mượt); vẫn sửa tay được khi cân đứng yên.
			if (p.stable) d.set_value("scale_weight", flt(p.weight, 3));
		});
		ensure_scale().then((ok) => {
			if (ok) read_stable();
			else
				frappe.show_alert(
					{ message: __("Chưa kết nối cân — nhập tay hoặc mở ⚙️ Scale Settings."), indicator: "orange" },
					5
				);
		});
	};

	// ---------- Đổi chế độ: bật/tắt panel + camera + cân + nhãn nút ----------
	const apply_mode = () => {
		const m = d.get_value("mode");
		const usePhoto = m !== M_SCALE;
		const useScale = m !== M_PHOTO && scale_available;
		d.fields_dict.cam.$wrapper.toggle(usePhoto);
		d.fields_dict.picker.$wrapper.toggle(usePhoto);
		d.fields_dict.scale_live.$wrapper.toggle(useScale);
		d.fields_dict.scale_weight.$wrapper.toggle(useScale);
		if (usePhoto && !stream) start_stream(localStorage.getItem(PL_CAM_KEY) || null);
		if (!usePhoto) stop_cam();
		if (useScale) start_scale();
		else stop_scale();
		d.get_primary_btn().text(m === M_SCALE ? __("⚖️ Ghi số cân") : __("📷 Chụp & Lưu"));
	};
	d.fields_dict.mode.df.onchange = () => apply_mode();

	// ---------- Thực hiện ----------
	let busy = false; // chặn double-trigger (Enter + click / bấm nhanh) làm nhảy 2 thùng
	function do_action() {
		if (busy) return;
		busy = true;
		setTimeout(() => {
			busy = false;
		}, 350);
		const m = d.get_value("mode");
		const continuous = !!cint(d.get_value("continuous"));
		localStorage.setItem(PL_MODE_KEY, m);
		localStorage.setItem(PL_CONT_KEY, continuous ? "1" : "0");

		// Chỉ cân: ghi Gross, không ảnh. Liên tiếp -> giữ dialog, sang thùng kế.
		if (m === M_SCALE) {
			const v = flt(d.get_value("scale_weight"));
			if (!v) {
				frappe.msgprint(__("Chưa có số cân."));
				return;
			}
			const done_no = curRow.carton_no;
			apply_gross(frm, curRow.doctype, curRow.name, v);
			pl_save(frm); // gom save, tránh đua nhau khi bấm nhanh
			const nxt = next_carton(frm, done_no);
			select_next_carton(frm, done_no + 1);
			if (continuous && nxt) {
				curRow = nxt;
				update_target();
				d.set_value("scale_weight", 0);
				frappe.show_alert(
					{ message: __("Ghi #{0} → sang #{1}", [done_no, nxt.carton_no]), indicator: "green" },
					2
				);
			} else {
				cleanup();
				d.hide();
				frappe.show_alert(
					{ message: __("Đã ghi Gross thùng #{0}", [done_no]), indicator: "green" },
					3
				);
			}
			return;
		}

		// Chụp ảnh (photo / both). gross truyền vào crop dialog:
		//   false       -> chỉ chụp (không đụng cân/OCR)
		//   number(>=0) -> both + có cân phần cứng (áp nếu >0, focus nếu 0)
		//   null        -> both nhưng không có cân -> OCR/Manual theo weight_source
		const finish_photo = (data_url) => {
			let gross;
			if (m === M_PHOTO) gross = false;
			else if (scale_available) gross = flt(d.get_value("scale_weight"));
			else gross = null;
			const target = curRow;
			const done_no = target.carton_no;
			cleanup();
			d.hide();
			// Sau khi lưu ảnh xong: nếu Liên tiếp -> mở tiếp thùng kế.
			carton_crop_dialog(frm, target, data_url, gross, () => {
				if (!continuous) return;
				const nxt = next_carton(frm, done_no);
				if (nxt) open_capture_dialog(frm, nxt, true);
				else
					frappe.show_alert(
						{ message: __("Đã xử lý thùng cuối cùng"), indicator: "green" },
						3
					);
			});
		};
		if (!has_cam) {
			carton_file_input(finish_photo);
			return;
		}
		const video = d.fields_dict.cam.$wrapper.find("video")[0];
		if (!video || !video.videoWidth) {
			frappe.msgprint(__("Camera chưa sẵn sàng."));
			return;
		}
		const cv = document.createElement("canvas");
		cv.width = video.videoWidth;
		cv.height = video.videoHeight;
		cv.getContext("2d").drawImage(video, 0, 0);
		finish_photo(cv.toDataURL("image/jpeg", 0.92));
	}

	// Enter = thực hiện (đặc biệt cho cân liên tiếp không rời bàn phím); Esc = đóng.
	d.$wrapper.on("keydown", (e) => {
		if (e.key === "Enter" && d.get_value("mode") === M_SCALE) {
			e.preventDefault();
			do_action();
		} else if (e.key === "Escape") {
			d.hide();
		}
	});

	d.show();
	apply_mode();
}

function carton_file_input(on_image) {
	const inp = document.createElement("input");
	inp.type = "file";
	inp.accept = "image/*";
	inp.setAttribute("capture", "environment");
	inp.onchange = () => {
		const f = inp.files && inp.files[0];
		if (!f) return;
		const r = new FileReader();
		r.onload = () => on_image(r.result);
		r.readAsDataURL(f);
	};
	inp.click();
}

// Camera nhẹ chỉ để lấy 1 ảnh (không lưu) — dùng cho chụp cận màn hình cân đọc OCR.
function quick_camera(on_image) {
	if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) return carton_file_input(on_image);
	const d = new frappe.ui.Dialog({
		title: __("📷 Chụp cận màn hình cân (chỉ đọc số, không lưu ảnh)"),
		fields: [
			{ fieldtype: "HTML", fieldname: "cam" },
			{ fieldtype: "HTML", fieldname: "picker" },
		],
		primary_action_label: __("📷 Chụp & Đọc"),
		primary_action() {
			const video = d.fields_dict.cam.$wrapper.find("video")[0];
			if (!video || !video.videoWidth) {
				frappe.msgprint(__("Camera chưa sẵn sàng."));
				return;
			}
			const cv = document.createElement("canvas");
			cv.width = video.videoWidth;
			cv.height = video.videoHeight;
			cv.getContext("2d").drawImage(video, 0, 0);
			cleanup();
			d.hide();
			on_image(cv.toDataURL("image/jpeg", 0.92));
		},
	});
	let stream = null;
	let closed = false;
	const stop = () => {
		if (stream) {
			stream.getTracks().forEach((t) => t.stop());
			stream = null;
		}
	};
	const cleanup = () => {
		closed = true;
		stop();
	};
	const refresh_devices = () =>
		navigator.mediaDevices.enumerateDevices().then((list) => {
			const cams = list.filter((x) => x.kind === "videoinput");
			if (cams.length < 2) {
				d.fields_dict.picker.$wrapper.html("");
				return;
			}
			const cur =
				(stream && stream.getVideoTracks()[0] && stream.getVideoTracks()[0].getSettings().deviceId) ||
				localStorage.getItem(PL_CAM_KEY) ||
				"";
			const opts = cams
				.map(
					(c, i) =>
						`<option value="${c.deviceId}"${c.deviceId === cur ? " selected" : ""}>${frappe.utils.escape_html(
							c.label || __("Camera {0}", [i + 1])
						)}</option>`
				)
				.join("");
			d.fields_dict.picker.$wrapper.html(
				`<label class="small text-muted" style="display:block;margin-top:6px">${__("Chọn camera")}</label>
				<select class="form-control input-sm pl-cam-sel">${opts}</select>`
			);
		});
	const start_stream = (deviceId) => {
		stop();
		const constraints = deviceId
			? { video: { deviceId: { exact: deviceId } } }
			: { video: { facingMode: { ideal: "environment" } } };
		return navigator.mediaDevices
			.getUserMedia(constraints)
			.then((s) => {
				if (closed) {
					s.getTracks().forEach((t) => t.stop());
					return;
				}
				stream = s;
				const v = d.fields_dict.cam.$wrapper.find("video")[0];
				if (v) v.srcObject = s;
				return refresh_devices();
			})
			.catch(() => {
				if (deviceId) {
					localStorage.removeItem(PL_CAM_KEY);
					return start_stream(null);
				}
				d.hide();
				carton_file_input(on_image);
			});
	};
	d.onhide = cleanup;
	d.fields_dict.cam.$wrapper.html(
		'<video autoplay playsinline muted style="width:100%;max-height:55vh;background:#000"></video>'
	);
	d.$wrapper.on("change", ".pl-cam-sel", function () {
		localStorage.setItem(PL_CAM_KEY, this.value);
		start_stream(this.value);
	});
	start_stream(localStorage.getItem(PL_CAM_KEY) || null);
	d.show();
}

// Chụp cận màn hình cân -> OCR đọc kg (ảnh KHÔNG lưu). on_result(m) với m từ read_scale_ocr.
function closeup_ocr_read(on_result) {
	quick_camera((data_url) => {
		frappe.call({
			method: "customize_erpnext.customize_erpnext.doctype.packing_list.packing_list.read_scale_ocr",
			args: { image: data_url, decimals: 2 },
			freeze: true,
			freeze_message: __("Đang đọc số cân (ảnh cận)..."),
			callback: (r) => on_result(r.message || {}),
		});
	});
}

// gross: số cân đã đọc trong dialog chụp (cân trước, chụp sau).
//   false -> chế độ "Chỉ chụp ảnh": lưu ảnh, KHÔNG đụng cân/OCR (giữ kg cũ).
//   null  -> chưa cân trong dialog (OCR/Manual) -> after_photo_weight lo tiếp.
//   >0    -> áp ngay vào Gross; nếu verify thì đối chiếu OCR ảnh (cảnh báo nếu lệch).
//   0     -> đã bật cân nhưng chưa lấy được số -> để user nhập tay (focus Gross).
// on_after(): gọi sau khi hoàn tất 1 thùng (áp Gross xong) — dùng cho Liên tiếp.
function carton_crop_dialog(frm, row, data_url, gross, on_after) {
	const d = new frappe.ui.Dialog({
		title: __("Cắt ảnh — thùng #{0}", [row.carton_no]),
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "crop" }],
		primary_action_label: __("Lưu ảnh"),
		primary_action() {
			if (!d._cropper) return;
			// Resize to a resolution that keeps the carton and the scale digits
			// readable, then JPEG-compress (not the raw full-size photo).
			const canvas = d._cropper.getCroppedCanvas({
				maxWidth: 1600,
				maxHeight: 1600,
				imageSmoothingQuality: "high",
			});
			if (!canvas) {
				frappe.msgprint(__("Chưa chọn được vùng ảnh, thử lại."));
				return;
			}
			const out = canvas.toDataURL("image/jpeg", 0.88);
			frappe.call({
				method: "customize_erpnext.customize_erpnext.doctype.packing_list.packing_list.save_carton_photo",
				args: {
					packing_list: frm.doc.name,
					carton_no: row.carton_no,
					color: row.color,
					size: row.size,
					image: out,
				},
				freeze: true,
				freeze_message: __("Đang lưu ảnh..."),
				callback(r) {
					if (!r.message) return;
					// Re-capture: the old photo file is replaced server-side; clear the
					// old weight so a stale kg can't linger if OCR is skipped.
					const re_capture = !!row.photo;
					const photo_only = gross === false;
					const weighed = typeof gross === "number" && flt(gross) > 0;
					frappe.model.set_value(row.doctype, row.name, "photo", r.message);
					if (weighed) {
						// Đã cân trong dialog chụp -> áp Gross ngay (không cần dialog cân sau).
						apply_gross(frm, row.doctype, row.name, flt(gross, 3));
					} else if (!photo_only && re_capture) {
						// OCR/Manual chụp lại -> xóa kg cũ (chỉ-chụp thì GIỮ nguyên kg).
						frappe.model.set_value(row.doctype, row.name, "gross_weight", 0);
						frappe.model.set_value(row.doctype, row.name, "net_weight", 0);
					}
					d.hide();
					const next_no = row.carton_no + 1;
					frm.save().then(() => {
						frappe.show_alert(
							{ message: __("Đã lưu ảnh thùng #{0}", [row.carton_no]), indicator: "green" },
							5
						);
						// Clear the checkbox and pre-select the next carton.
						select_next_carton(frm, next_no);
						if (weighed || photo_only) {
							// Gross đã áp (hoặc chỉ chụp) -> xong thùng này.
							if (on_after) on_after();
						} else if (gross === 0) {
							// Bật cân nhưng chưa lấy được số -> nhập tay (dừng liên tiếp).
							focus_gross(frm, row.doctype, row.name);
						} else {
							// OCR / chưa cân trong dialog -> điều phối; xong thì on_after.
							after_photo_weight(frm, row.doctype, row.name, data_url, on_after);
						}
					});
				},
			});
		},
	});
	d.fields_dict.crop.$wrapper.html(
		`<img class="pl-crop-img" src="${data_url}" style="max-width:100%;display:block">`
	);
	d.$wrapper.find(".modal-dialog").css({ "max-width": "820px", width: "90vw" });
	// Destroy the cropper when the dialog closes (avoids stale instances / id clashes).
	d.onhide = () => {
		if (d._cropper) {
			d._cropper.destroy();
			d._cropper = null;
		}
	};
	d.show();
	setTimeout(() => {
		if (typeof Cropper === "undefined") {
			frappe.msgprint(__("Cropper.js chưa được tải."));
			return;
		}
		// Query the image inside THIS dialog's wrapper (not a global id).
		const img = d.fields_dict.crop.$wrapper.find("img.pl-crop-img")[0];
		if (img) {
			d._cropper = new Cropper(img, { viewMode: 1, autoCropArea: 1, background: false });
		}
	}, 250);
}

function download_all_carton_photos(frm) {
	if (frm.is_new()) {
		frappe.msgprint(__("Lưu Packing List trước."));
		return;
	}
	if (!(frm.doc.details || []).some((d) => d.photo)) {
		frappe.msgprint(__("Chưa có ảnh thùng nào để tải."));
		return;
	}
	window.open(
		"/api/method/customize_erpnext.customize_erpnext.doctype.packing_list.packing_list.download_all_photos?packing_list=" +
		encodeURIComponent(frm.doc.name)
	);
}

// Crop the scale digits from the capture, OCR the weight, apply to Gross.

// Auto-detect & read the red scale digits from the captured photo (no manual
// crop — hard on mobile). User verifies/edits the number before applying.
function scale_ocr_dialog(frm, cdt, cdn, source, on_after) {
	const row = () => locals[cdt][cdn];
	const d = new frappe.ui.Dialog({
		title: __("Số cân (Gross) — thùng #{0}", [row().carton_no]),
		fields: [
			{ fieldtype: "HTML", fieldname: "preview" },
			{ fieldtype: "Float", fieldname: "weight", label: __("Số cân / Gross (kg)"), precision: 3 },
			{ fieldtype: "HTML", fieldname: "note" },
		],
		primary_action_label: __("Áp dụng vào Gross"),
		primary_action() {
			const v = flt(d.get_value("weight"));
			if (!v) {
				frappe.msgprint(__("Chưa có số cân — nhập tay hoặc Đọc lại."));
				return;
			}
			apply_gross(frm, cdt, cdn, v);
			d.hide();
			frm.save().then(() => {
				frappe.show_alert(
					{ message: __("Đã cập nhật Gross thùng #{0}", [row().carton_no]), indicator: "green" },
					4
				);
				if (on_after) on_after();
			});
		},
		secondary_action_label: __("Bỏ qua"),
		secondary_action() {
			d.hide();
		},
	});
	d.fields_dict.preview.$wrapper.html(
		`<img src="${source}" style="max-width:100%;max-height:36vh;display:block;margin:0 auto">
		<div style="text-align:center;margin-top:6px">
			<button class="btn btn-sm btn-default ocr-redo">🔄 ${__("Đọc lại số cân")}</button>
			<button class="btn btn-sm btn-default ocr-closeup" style="margin-left:6px">📷 ${__(
				"Chụp cận màn hình cân"
			)}</button>
		</div>`
	);
	// Hiện kết quả OCR (dùng chung cho đọc ảnh gốc & ảnh cận).
	const render_ocr = (m, tag) => {
		if (m && m.ok && m.value != null) {
			d.set_value("weight", m.value);
			const warn = m.confident === false;
			d.fields_dict.note.$wrapper.html(
				`<div class="small" style="color:${warn ? "#c0392b" : "#27ae60"}">${warn ? "⚠ " : "✓ "}${
					tag ? tag + " " : ""
				}OCR: ${frappe.utils.escape_html(String(m.raw || ""))} → <b>${m.value} kg</b>${
					warn ? " — " + __("chưa chắc chắn, kiểm tra kỹ") : ""
				}</div>`
			);
		} else {
			d.fields_dict.note.$wrapper.html(
				`<div class="small text-muted">${__("Không đọc được số — thử chụp cận hoặc nhập tay.")}</div>`
			);
		}
	};
	const run_ocr = () => {
		frappe.call({
			method: "customize_erpnext.customize_erpnext.doctype.packing_list.packing_list.read_scale_ocr",
			args: { image: source, decimals: 2 },
			freeze: true,
			freeze_message: __("Đang đọc số cân..."),
			callback: (r) => render_ocr(r.message || {}),
		});
	};
	d.$wrapper.on("click", ".ocr-redo", run_ocr);
	// Chụp cận màn hình cân để đọc lại (chỉ đọc kg, KHÔNG lưu ảnh này).
	d.$wrapper.on("click", ".ocr-closeup", () =>
		closeup_ocr_read((m) => render_ocr(m, __("(ảnh cận)")))
	);
	d.show();
	run_ocr(); // auto-read on open
}

// Clear all detail checkboxes and pre-select the next carton (by carton_no).
function select_next_carton(frm, next_no) {
	const grid = frm.fields_dict.details && frm.fields_dict.details.grid;
	if (!grid || !grid.grid_rows) return;
	grid.grid_rows.forEach((gr) => {
		const want = gr.doc && gr.doc.carton_no === next_no;
		gr.doc.__checked = want ? 1 : 0;
		const cb = gr.row_check && gr.row_check.find("input[type=checkbox]");
		if (cb && cb.length) cb.prop("checked", !!want);
	});
}

/* ==================== Đọc cân trực tiếp (Web Serial) ==================== */

// Badge trạng thái cân trên dashboard form; tự cập nhật theo sự kiện.
function scale_indicator(frm) {
	if (frm.__scale_off) frm.__scale_off();
	const badge = frm.dashboard.add_indicator(__("Cân: chưa kết nối"), "red");
	frm.__scale_off = plScale.onStatus((s) => {
		const map = {
			connected: [__("Cân: đã kết nối"), "green"],
			disconnected: [__("Cân: chưa kết nối"), "red"],
			reading: [__("Cân: đang đọc…"), "orange"],
		};
		const [txt, color] = map[s] || map.disconnected;
		if (badge && badge.length)
			badge.text(txt).removeClass("green red orange gray blue").addClass(color);
	});
}

// Ghi Gross vào 1 dòng thùng; nếu Gross to Net thì tính lại Net = Gross - tare.
function apply_gross(frm, cdt, cdn, value) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "gross_weight", value);
	if ((frm.doc.weight_mode || "") === "Gross to Net")
		frappe.model.set_value(cdt, cdn, "net_weight", flt(value - flt(row.empty_weight), 3));
	sum_weight_totals(frm);
}

// Đảm bảo có kết nối cân (không cần gesture nếu cổng đã cấp quyền).
function ensure_scale() {
	if (!(window.plScale && plScale.supported())) return Promise.resolve(false);
	if (plScale.isConnected()) return Promise.resolve(true);
	return plScale
		.tryReconnect()
		.then((ok) => ok || plScale.connect().then(() => true).catch(() => false))
		.catch(() => false);
}

// Manual: chỉ đưa con trỏ vào ô Gross của dòng thùng (không dialog).
function focus_gross(frm, cdt, cdn) {
	const grid = frm.fields_dict.details && frm.fields_dict.details.grid;
	if (!grid) return;
	const gr = (grid.grid_rows || []).find((g) => g.doc && g.doc.name === cdn);
	if (!gr) return;
	gr.toggle_view(true);
	setTimeout(() => {
		const f = gr.grid_form && gr.grid_form.fields_dict && gr.grid_form.fields_dict.gross_weight;
		if (f && f.$input) f.$input.focus();
	}, 250);
}

// Điều phối lấy Gross sau khi lưu ảnh, theo weight_source (Scale / OCR — cả 2 nhập tay được).
// on_after(): gọi khi xong (áp Gross) để Liên tiếp sang thùng kế.
function after_photo_weight(frm, cdt, cdn, data_url, on_after) {
	// Chỉ có ý nghĩa khi Gross to Net (Net to Gross: Gross suy ra từ Net).
	if ((frm.doc.weight_mode || "") !== "Gross to Net") {
		if (on_after) on_after();
		return;
	}
	if ((frm.doc.weight_source || "OCR") === "Scale") return scale_after_photo(frm, cdt, cdn, on_after);
	return scale_ocr_dialog(frm, cdt, cdn, data_url, on_after); // OCR
}

// Sau lưu ảnh với weight_source = Scale (khi chưa cân trong dialog chụp).
function scale_after_photo(frm, cdt, cdn, on_after) {
	const row = () => locals[cdt][cdn];
	ensure_scale().then((ok) => {
		if (!ok) {
			// Không kết nối được cân -> nhập Gross tay (dừng liên tiếp).
			frappe.msgprint(
				__("Không kết nối được cân. Mở ⚙️ Scale Settings để kết nối, hoặc nhập Gross tay.")
			);
			focus_gross(frm, cdt, cdn);
			return;
		}
		const d = new frappe.ui.Dialog({
			title: __("⚖️ Số cân (Gross) — thùng #{0}", [row().carton_no]),
			fields: [
				{ fieldtype: "HTML", fieldname: "live" },
				{ fieldtype: "Float", fieldname: "weight", label: __("Số cân / Gross (kg)"), precision: 3 },
				{ fieldtype: "HTML", fieldname: "note" },
			],
			primary_action_label: __("Áp dụng vào Gross"),
			primary_action() {
				const v = flt(d.get_value("weight"));
				if (!v) {
					frappe.msgprint(__("Chưa có số cân."));
					return;
				}
				apply_gross(frm, cdt, cdn, v);
				d.hide();
				frm.save().then(() => {
					frappe.show_alert(
						{ message: __("Đã cập nhật Gross thùng #{0}", [row().carton_no]), indicator: "green" },
						4
					);
					if (on_after) on_after();
				});
			},
			secondary_action_label: __("Bỏ qua"),
			secondary_action() {
				d.hide();
			},
		});
		d.fields_dict.live.$wrapper.html(
			`<div class="text-center" style="padding:4px">
				<div class="sc-flag small text-muted">${__("Đang chờ cân ổn định…")}</div>
				<div class="sc-num" style="font-size:40px;font-weight:700;line-height:1.1">--</div>
			</div>`
		);
		// Hiển thị số cân nhảy live.
		const off = plScale.onReading((p) => {
			if (!p) return;
			d.$wrapper.find(".sc-num").text(p.weight.toFixed(3)).css("color", p.stable ? "#27ae60" : "#c0392b");
			d.$wrapper.find(".sc-flag").text(p.stable ? "ST — ổn định" : "US — chưa ổn định");
		});
		d.onhide = () => off();
		// Đọc số cân ổn định (mặc định lấy số này); lỗi -> vẫn cho nhập tay.
		plScale
			.readStableWeight({ timeoutMs: 8000, needConsecutive: 3 })
			.then((w) => d.set_value("weight", flt(w, 3)))
			.catch((err) => {
				d.fields_dict.note.$wrapper.html(
					`<div class="small" style="color:#c0392b">⚠ ${frappe.utils.escape_html(err.message || "")}</div>`
				);
			});
		d.show();
	});
}

