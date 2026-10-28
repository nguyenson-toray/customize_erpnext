// Chạy JS thật của www/employee-self-update-info/index.html trong jsdom, API giả lập.
const { JSDOM } = require("jsdom");
const { pageHtml, stubBrowser, sleep, report } = require("./harness");

const HTML = pageHtml();

const PROV = [
  { value: "Tỉnh Quảng Ngãi", label: "Tỉnh Quảng Ngãi", code: "51" },
  { value: "Thành phố Hà Nội", label: "Thành phố Hà Nội", code: "01" },
];
const WARDS = {
  "51": ["Xã Ba Tơ", "Xã Ba Tô", "Xã Sơn Hà", "Phường Trương Quang Trọng"].map((n, i) => ({ value: n, label: n, code: "51" + i })),
  "01": ["Phường Ba Đình", "Phường Hoàn Kiếm"].map((n, i) => ({ value: n, label: n, code: "01" + i })),
};
const field = (fieldname, label, widget, extra = {}) => ({
  fieldname, label, widget, fieldtype: widget === "Auto" ? "Data" : "Autocomplete",
  required: false, read_only: false, auto_fill: true, validation: "", min_length: 0, max_length: 0, ...extra,
});
function makeConfig(opts = {}) {
  return {
    sections: [
      { label: "Địa chỉ thường trú", fields: [
        field("p_prov", "Tỉnh", "Address Province", opts.p_prov || {}),
        field("p_ward", "Xã", "Address Ward", opts.p_ward || {}),
      ] },
      { label: "Địa chỉ hiện tại", fields: [
        field("c_prov", "Tỉnh", "Address Province"),
        field("c_ward", "Xã", "Address Ward"),
      ] },
      { label: "CCCD", fields: [
        { ...field("date_of_birth", "Ngày sinh", "Auto"), fieldtype: "Date", validation: "Past" },
        { ...field("custom_id_card_date_of_issue", "Ngày cấp", "Auto"), fieldtype: "Date", validation: "Past" },
        { ...field("custom_id_card__date_of_expired", "Ngày hết hạn", "Auto"), fieldtype: "Date", validation: "Future", required: true },
      ] },
      { label: "Khác", fields: [
        field("custom_ethnicity", "Dân tộc", "Auto", opts.eth || {}),
        field("person_to_be_contacted", "Người liên hệ", "Auto", { validation: "Person Name" }),
        field("village", "Chi tiết địa chỉ", "Auto"),
        field("personal_email", "Email", "Auto", { validation: "Email" }),
      ] },
    ],
    require_dob: false, allow_local_draft: false, lock_after_submit: false, save_file_type: "PDF",
    commitment_text: "Cam kết",
  };
}

async function boot(values, cfgOpts) {
  const calls = [];
  const dom = new JSDOM(HTML, {
    runScripts: "dangerously", pretendToBeVisual: true, url: "https://erp.test/employee-self-update-info",
    beforeParse(w) {
      stubBrowser(w);
      w.HTMLCanvasElement.prototype.getContext = () => ({ scale() {}, beginPath() {}, arc() {}, fill() {}, moveTo() {}, lineTo() {}, stroke() {}, fillRect() {}, drawImage() {} });
      w.Element.prototype.scrollIntoView = function () {};
      w.Element.prototype.setPointerCapture = function () {};
      w.HTMLCanvasElement.prototype.toDataURL = () => "data:image/png;base64,AAAA";
      w.fetch = async (url, init) => {
        const method = url.split("/api/method/")[1];
        const args = {};
        if (init && init.body) for (const [k, v] of init.body.entries()) args[k] = v;
        calls.push([method, args]);
        let message = null;
        if (method.endsWith("get_field_config")) message = makeConfig2(cfgOpts);
        else if (method.endsWith("get_eligible_employees")) message = [{ employee_id: "TIQN-1", display_name: "Test" }];
        else if (method.endsWith("get_form_data")) message = { original: { ...values }, values: { ...values }, status: null, employee_name: "Test", remarks: "", is_hr: false };
        else if (method.endsWith("get_province_options")) message = PROV;
        else if (method.endsWith("get_ward_options")) message = WARDS[args.province] || [];
        return { status: 200, json: async () => ({ message }) };
      };
    },
  });
  const w = dom.window;
  await sleep(50);
  await w.loadForm("TIQN-1", "");
  await sleep(80);
  return { w, d: w.document, calls };
}

const results = [];
const check = (name, ok, detail = "") => results.push([!!ok, name, detail]);


const EDU = {
  fieldname: "education", label: "Trình độ học vấn", fieldtype: "Table", options: "Employee Education",
  widget: "Auto", required: true, read_only: false, auto_fill: true, validation: "", max_rows: 3,
  columns: [
    { fieldname: "school_univ", label: "Trường", fieldtype: "Small Text", options: null, required: false, placeholder: "" },
    { fieldname: "level", label: "Trình độ", fieldtype: "Select", options: ["", "THCS", "THPT", "Cao đẳng"], required: true, placeholder: "" },
    { fieldname: "year_of_passing", label: "Năm tốt nghiệp", fieldtype: "Int", options: null, required: false, placeholder: "" },
  ],
  required_if: { column: "level", values: ["Trung cấp", "Cao đẳng", "Đại học", "Sau đại học"], columns: ["school_univ", "year_of_passing"], required: ["school_univ"] },
};
function makeConfig2(opts = {}) {
  return {
    sections: [{ label: "Học vấn", fields: [{ ...EDU, ...(opts.edu || {}) }, ...(opts.extra || [])] }],
    require_dob: false, allow_local_draft: false, lock_after_submit: false, save_file_type: "PDF", commitment_text: "Cam kết",
  };
}
const fire = (w, el, t) => el.dispatchEvent(new w.Event(t, { bubbles: true }));
async function sign(w, d) {
  d.getElementById("f__commit").checked = true;
  await sleep(50);
  const pad = d.getElementById("sign_pad");
  const pe = (t) => { const e = new w.MouseEvent(t, { bubbles: true, cancelable: true, clientX: 10, clientY: 10 }); e.pointerId = 1; return e; };
  pad.dispatchEvent(pe("pointerdown")); pad.dispatchEvent(pe("pointerup"));
}
const lastSave = (calls) => { const c = calls.filter(x => x[0].endsWith("save_form_data")).pop(); return c && JSON.parse(c[1].data); };

(async () => {
  // 1. prefill từ Employee (kèm name), không tô "đã đổi"
  const orig = [{ name: "row1", school_univ: "Cao đẳng Dung Quất", level: "Cao đẳng", year_of_passing: "2015" }];
  let { w, d, calls } = await boot({ education: orig });
  const box = () => d.getElementById("f_education");
  check("prefill: 1 thẻ", box().querySelectorAll(".tbl-row").length === 1);
  check("prefill: giá trị ô", box().querySelector('[data-col="school_univ"]').value === "Cao đẳng Dung Quất"
    && box().querySelector('[data-col="level"]').value === "Cao đẳng");
  check("không tô 'đã đổi' lúc load", !d.getElementById("fg_education").classList.contains("changed"));
  check("nút ghi '+ Thêm' / '✕ Xoá' (không có chữ 'dòng')", box().querySelector(".tbl-add").textContent === "+ Thêm"
    && box().querySelector(".tbl-del").textContent === "✕ Xoá", [box().querySelector(".tbl-add").textContent]);

  // 2. sửa ô → đã đổi; chuẩn hoá khi rời ô
  const sch = box().querySelector('[data-col="school_univ"]');
  sch.value = "cao đẳng  dung quất"; fire(w, sch, "input"); fire(w, sch, "change");
  check("chuẩn hoá ô khi rời ô", sch.value === "Cao đẳng dung quất", sch.value);
  check("sửa → tô 'đã đổi'", d.getElementById("fg_education").classList.contains("changed"));

  // 3. thêm tới max_rows → ẩn nút
  box().querySelector(".tbl-add").click(); box().querySelector(".tbl-add").click();
  check("thêm 2 dòng → 3 thẻ", box().querySelectorAll(".tbl-row").length === 3);
  check("đủ max_rows → ẩn + Thêm dòng", !box().querySelector(".tbl-add"));
  check("đủ max_rows (3) → vẫn hiện 'Tối đa 3.'", /Tối đa 3\./.test(box().textContent), box().textContent);
  // giá trị ô đã nhập vẫn còn sau khi vẽ lại
  check("vẽ lại giữ giá trị", box().querySelector('[data-col="school_univ"]').value === "Cao đẳng dung quất");

  // 4. dòng 3 chỉ nhập năm (thiếu Trình độ bắt buộc) → chặn gửi; dòng 2 trống bị bỏ
  const yr3 = box().querySelectorAll('[data-col="year_of_passing"]')[2];
  yr3.value = "2020"; fire(w, yr3, "input");
  await sign(w, d);
  await w.submitForm();
  check("thiếu cột bắt buộc → chặn gửi", !lastSave(calls), d.getElementById("toast").textContent);
  const lv3 = box().querySelectorAll('[data-col="level"]')[2];
  lv3.value = "THPT"; fire(w, lv3, "change");
  await w.submitForm();
  const p = lastSave(calls);
  check("gửi: bỏ dòng trống, giữ name dòng cũ", p && p.education.length === 2 && p.education[0].name === "row1"
    && !("name" in p.education[1]), p && p.education);
  check("gửi: giá trị đã chuẩn hoá", p && p.education[0].school_univ === "Cao đẳng dung quất" && p.education[1].level === "THPT", p && p.education);

  // 5. xoá dòng
  ({ w, d, calls } = await boot({ education: orig }));
  box().querySelector(".tbl-del").click();
  check("xoá dòng duy nhất → còn 0 thẻ + nút thêm", box().querySelectorAll(".tbl-row").length === 0 && !!box().querySelector(".tbl-add"));
  check("xoá → tô 'đã đổi'", d.getElementById("fg_education").classList.contains("changed"));
  await sign(w, d);
  await w.submitForm();
  check("required + không còn dòng → chặn gửi", !lastSave(calls), d.getElementById("toast").textContent);

  // 6. Employee chưa có dòng → sẵn 1 thẻ trống; không đổi gì thì không tô
  ({ w, d, calls } = await boot({ education: [] }, { edu: { required: false } }));
  check("chưa có dòng → 1 thẻ trống", box().querySelectorAll(".tbl-row").length === 1);
  check("thẻ trống không tính là đã đổi", !d.getElementById("fg_education").classList.contains("changed"));
  await sign(w, d);
  await w.submitForm();
  const p6 = lastSave(calls);
  check("không required + thẻ trống → gửi list rỗng", p6 && Array.isArray(p6.education) && p6.education.length === 0, p6);

  // 7. năm không phải số → chặn
  ({ w, d, calls } = await boot({ education: orig }));
  const yr = box().querySelector('[data-col="year_of_passing"]');
  yr.type = "text"; yr.value = "abc"; fire(w, yr, "input");
  await sign(w, d);
  await w.submitForm();
  check("Int không hợp lệ → chặn", !lastSave(calls), d.getElementById("toast").textContent);

  // 9. bắt buộc có điều kiện (16/10/2026): Cao đẳng → Trường bắt buộc, Năm TN không; THPT → ẩn Trường/Năm
  ({ w, d, calls } = await boot({ education: [] }));
  const lbls = () => [...box().querySelectorAll(".tbl-lbl")].map(l => l.textContent.trim());
  check("chưa chọn trình độ: Trường không có *", lbls()[0] === "Trường", lbls());
  let lv = box().querySelector('[data-col="level"]');
  lv.value = "Cao đẳng"; fire(w, lv, "change");
  check("chọn Cao đẳng → Trường có *, Năm TN không", lbls()[0] === "Trường *" && lbls()[2] === "Năm tốt nghiệp", lbls());
  await sign(w, d);
  await w.submitForm();
  check("Cao đẳng thiếu Trường → chặn", !lastSave(calls), d.getElementById("toast").textContent);
  lv = box().querySelector('[data-col="level"]');
  lv.value = "THPT"; fire(w, lv, "change");
  check("đổi sang THPT → ẩn Trường / Năm TN", lbls().join() === "Trình độ *", lbls());
  await w.submitForm();
  const p9 = lastSave(calls);
  check("THPT không cần Trường/Năm → gửi được", p9 && p9.education.length === 1 && p9.education[0].level === "THPT", p9);

  // 10. Max Rows = 1 (Học vấn / Kinh nghiệm, 23/10/2026): 1 dòng → hết nút Thêm; KHÔNG hiện "Tối đa 1." (28/10/2026)
  ({ w, d, calls } = await boot({ education: [{ name: "row1", school_univ: "", level: "THPT", year_of_passing: "" }] }, { edu: { max_rows: 1 } }));
  check("max 1: đã có 1 dòng → không còn + Thêm", !box().querySelector(".tbl-add"));
  check("max 1: KHÔNG có dòng 'Tối đa 1.' (chỉ 1 thẻ — thừa)", !/Tối đa/.test(box().textContent), box().textContent);
  ({ w, d, calls } = await boot({ education: [] }, { edu: { max_rows: 1 } }));
  check("max 1: bảng trống → sẵn 1 thẻ trống, không có + Thêm", box().querySelectorAll(".tbl-row").length === 1 && !box().querySelector(".tbl-add"));
  box().querySelector(".tbl-del").click();
  check("max 1: xoá thẻ → hiện lại + Thêm", box().querySelectorAll(".tbl-row").length === 0 && !!box().querySelector(".tbl-add"));

  // 8. read_only → không có nút sửa, ô disabled
  ({ w, d, calls } = await boot({ education: orig }, { edu: { read_only: true } }));
  check("read_only: không nút thêm/xoá, ô disabled", !box().querySelector(".tbl-add") && !box().querySelector(".tbl-del")
    && box().querySelector('[data-col="school_univ"]').disabled);

  // 11. Select: nhãn tiếng Việt (option_labels), giá trị gửi đi vẫn tiếng Anh
  const MS = { fieldname: "marital_status", label: "Tình trạng hôn nhân", fieldtype: "Select", widget: "Auto",
    options: ["", "Single", "Married", "Divorced", "Widowed"], required: true, read_only: false, auto_fill: true, validation: "",
    option_labels: { Single: "Độc thân", Married: "Đã kết hôn", Divorced: "Đã ly hôn", Widowed: "Góa" } };
  const GD = { fieldname: "gender", label: "Giới tính", fieldtype: "Select", widget: "Auto", options: ["", "Male", "Female"],
    required: true, read_only: false, auto_fill: true, validation: "", option_labels: { Male: "Nam", Female: "Nữ" } };
  const eduLbl = { columns: EDU.columns.map(c => c.fieldname === "level" ? { ...c, options: ["", "THCS", "Graduate"], option_labels: { Graduate: "Tốt nghiệp" } } : c) };
  ({ w, d, calls } = await boot({ education: [{ name: "r1", level: "Graduate", school_univ: "X" }], marital_status: "Married", gender: "Female" },
    { extra: [MS, GD], edu: eduLbl }));
  const ms = d.getElementById("f_marital_status");
  const txt = (sel) => [...sel.options].map(o => o.textContent);
  check("Select: hiện nhãn tiếng Việt", JSON.stringify(txt(ms)) === JSON.stringify(["— Chọn —", "Độc thân", "Đã kết hôn", "Đã ly hôn", "Góa"]), txt(ms));
  check("Select: value vẫn tiếng Anh", JSON.stringify([...ms.options].map(o => o.value)) === JSON.stringify(["", "Single", "Married", "Divorced", "Widowed"]));
  check("Select: giá trị cũ 'Married' được chọn sẵn", ms.value === "Married" && ms.options[ms.selectedIndex].textContent === "Đã kết hôn");
  const gd = d.getElementById("f_gender");
  check("Giới tính: Nam / Nữ, chọn sẵn Female", JSON.stringify(txt(gd)) === JSON.stringify(["— Chọn —", "Nam", "Nữ"]) && gd.value === "Female", txt(gd));
  const lvl = box().querySelector('[data-col="level"]');
  check("bảng con: cột Select cũng hiện nhãn", lvl.options[lvl.selectedIndex].textContent === "Tốt nghiệp" && lvl.value === "Graduate");
  ms.value = "Divorced"; fire(w, ms, "change");
  await sign(w, d);
  await w.submitForm();
  const p11 = lastSave(calls);
  check("gửi đi giá trị tiếng Anh (Divorced / Female / Graduate)",
    p11 && p11.marital_status === "Divorced" && p11.gender === "Female" && p11.education[0].level === "Graduate",
    p11 || d.getElementById("toast").textContent);

  // 12. Size dép: nhãn 3 thông tin, lưu size công ty
  const SHOE = { fieldname: "custom_shoe_size", label: "Size dép", fieldtype: "Select", widget: "Auto",
    options: ["", "2-3", "6-7"], required: false, read_only: false, auto_fill: true, validation: "",
    option_labels: { "6-7": "Size 6-7 · dép thường 38-39 · chân 24.5-25 cm" } };
  // 13. GPLX + tình trạng chỉ hiện khi "Chưa", hiện thì bắt buộc
  const LIC = { fieldname: "custom_driving_license", label: "Giấy phép lái xe", fieldtype: "Select", widget: "Auto",
    options: ["", "Có", "Chưa", "Mất"], required: false, read_only: false, auto_fill: true, validation: "", option_labels: {} };
  const LST = { fieldname: "custom_driving_license_status", label: "Tình trạng GPLX", fieldtype: "Select", widget: "Auto",
    options: ["", "Chưa đăng ký", "Đang đợi cấp"], required: false, read_only: false, auto_fill: true, validation: "", option_labels: {},
    depends_on: { field: "custom_driving_license", values: ["Chưa"] } };
  ({ w, d, calls } = await boot({ education: orig, custom_shoe_size: "6-7", custom_driving_license: "Có", custom_driving_license_status: "Đang đợi cấp" },
    { extra: [SHOE, LIC, LST] }));
  const sh = d.getElementById("f_custom_shoe_size");
  check("size dép: hiện đủ 3 thông tin, value 6-7",
    sh.value === "6-7" && sh.options[sh.selectedIndex].textContent === "Size 6-7 · dép thường 38-39 · chân 24.5-25 cm");
  const fg = d.getElementById("fg_custom_driving_license_status");
  check("GPLX Có → ô tình trạng ẩn + bị xoá giá trị", fg.classList.contains("hidden") && d.getElementById("f_custom_driving_license_status").value === "");
  check("ô tình trạng có dấu * (bắt buộc khi hiện)", !!fg.querySelector(".req"));
  const lic = d.getElementById("f_custom_driving_license");
  lic.value = "Chưa"; fire(w, lic, "change");
  check("chọn Chưa → ô tình trạng hiện", !fg.classList.contains("hidden"));
  await sign(w, d);
  await w.submitForm();
  check("Chưa + chưa chọn tình trạng → chặn gửi", !lastSave(calls) && /Tình trạng GPLX/.test(d.getElementById("toast").textContent),
    d.getElementById("toast").textContent);
  const stEl = d.getElementById("f_custom_driving_license_status");
  stEl.value = "Đang đợi cấp"; fire(w, stEl, "change");
  await w.submitForm();
  let p13 = lastSave(calls);
  check("Chưa + Đang đợi cấp → gửi đủ", p13 && p13.custom_driving_license === "Chưa" && p13.custom_driving_license_status === "Đang đợi cấp", p13);
  ({ w, d, calls } = await boot({ education: orig, custom_driving_license: "Chưa", custom_driving_license_status: "Đang đợi cấp" }, { extra: [LIC, LST] }));
  const lic2 = d.getElementById("f_custom_driving_license");
  lic2.value = "Có"; fire(w, lic2, "change");
  await sign(w, d);
  await w.submitForm();
  p13 = lastSave(calls);
  check("đổi sang Có → ẩn và gửi tình trạng trống",
    d.getElementById("fg_custom_driving_license_status").classList.contains("hidden") && p13 && p13.custom_driving_license_status === "", p13);

  report(results);
})().catch((e) => { console.error(e); process.exit(2); });
