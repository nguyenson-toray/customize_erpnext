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
        field("person_to_be_contacted", "Người liên hệ", "Auto", { validation: "Capitalize Each Word" }),
        field("village", "Chi tiết địa chỉ", "Auto"),
        field("personal_email", "Email", "Auto", { validation: "Email" }),
        field("custom_favorite_sport", "Môn thể thao", "Auto", { validation: "Capitalize Each Word" }),
        { ...field("custom_strengths", "Sở trường", "Auto", { validation: "Sentence Case" }), fieldtype: "Small Text" },
      ] },
    ],
    require_dob: false, allow_local_draft: false, lock_after_submit: false, save_file_type: "PDF",
    commitment_html: "Cam kết dòng 1<br>dòng 2 &amp; &lt;b&gt;",
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
        if (method.endsWith("get_field_config")) message = makeConfig(cfgOpts);
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

(async () => {
  // ---- 1. prefill đúng danh mục ----
  let { w, d, calls } = await boot({ p_prov: "Tỉnh Quảng Ngãi", p_ward: "Xã Ba Tơ", c_prov: "", c_ward: "" });
  const I = (fn) => d.getElementById("f_" + fn);
  { const ct = d.getElementById("commit_text");
    check("cam kết: xuống dòng = <br>, chữ <b> không thành thẻ", ct.querySelectorAll("br").length === 1 && !ct.querySelector("b") && ct.textContent === "Cam kết dòng 1dòng 2 & <b>", ct.innerHTML); }
  check("prefill tỉnh", I("p_prov").value === "Tỉnh Quảng Ngãi" && I("p_prov").dataset.code === "51");
  check("prefill xã (Ba Tơ, không nhầm Ba Tô)", I("p_ward").value === "Xã Ba Tơ" && I("p_ward").dataset.code === "510");
  check("ô xã bật khi có tỉnh", !I("p_ward").disabled);
  check("không tô 'đã đổi' lúc load", !d.getElementById("fg_p_prov").classList.contains("changed") && !d.getElementById("fg_p_ward").classList.contains("changed"));
  check("tỉnh trống + auto_fill → mặc định Quảng Ngãi", I("c_prov").value === "Tỉnh Quảng Ngãi");
  check("xã hiện tại trống, bật", I("c_ward").value === "" && !I("c_ward").disabled);
  check("API dùng chung vn_address_search", calls.some(c => c[0].includes("vn_address_search_api.get_province_options")) && calls.some(c => c[0].includes("vn_address_search_api.get_ward_options")));

  // ---- 2. lọc bỏ dấu ----
  w.addrOpen("p_ward", "ba to");
  let items = [...d.querySelectorAll('.addr-combo[data-fieldname="p_ward"] .combo-item')].map(e => e.textContent);
  check("gõ 'ba to' → Ba Tơ + Ba Tô", items.length === 2 && items.includes("Xã Ba Tơ") && items.includes("Xã Ba Tô"), items);
  w.addrOpen("p_ward", "truong quang");
  items = [...d.querySelectorAll('.addr-combo[data-fieldname="p_ward"] .combo-item')].map(e => e.textContent);
  check("gõ không dấu 'truong quang'", items.length === 1 && items[0] === "Phường Trương Quang Trọng", items);
  w.addrOpen("p_ward", "");
  items = d.querySelectorAll('.addr-combo[data-fieldname="p_ward"] .combo-item');
  check("ô trống → đủ danh sách", items.length === 4);
  check("dòng đang chọn được tô active", d.querySelector('.addr-combo[data-fieldname="p_ward"] .combo-item.active').textContent === "Xã Ba Tơ");

  // ---- 3. chọn bằng chạm ----
  w.addrOpen("p_ward", "ba to");
  const baTo = [...d.querySelectorAll('.addr-combo[data-fieldname="p_ward"] .combo-item')].find(e => e.textContent === "Xã Ba Tô");
  baTo.dispatchEvent(new w.Event("pointerdown", { bubbles: true, cancelable: true }));
  check("chạm chọn Xã Ba Tô", I("p_ward").dataset.value === "Xã Ba Tô" && I("p_ward").value === "Xã Ba Tô");
  check("đổi xã → tô 'đã đổi'", d.getElementById("fg_p_ward").classList.contains("changed"));
  check("list đóng sau khi chọn", d.querySelector('.addr-combo[data-fieldname="p_ward"] .combo-list').classList.contains("hidden"));

  // ---- 4. Enter chọn dòng đầu ----
  w.addrOpen("p_ward", "son ha");
  I("p_ward").dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  check("Enter chọn dòng đầu", I("p_ward").dataset.value === "Xã Sơn Hà");

  // ---- 5. gõ rác rồi rời ô → trả về giá trị cũ ----
  I("p_ward").value = "abc";
  I("p_ward").dispatchEvent(new w.Event("blur"));
  await sleep(200);
  check("rời ô với chữ rác → trả về giá trị cũ", I("p_ward").value === "Xã Sơn Hà" && I("p_ward").dataset.value === "Xã Sơn Hà");
  check("toast báo chọn trong danh sách", d.getElementById("toast").textContent.includes("chọn trong danh sách"));

  // ---- 6. gõ đúng nguyên tên có dấu rồi rời ô → nhận ----
  I("p_ward").value = "Xã Ba Tơ";
  I("p_ward").dispatchEvent(new w.Event("blur"));
  await sleep(200);
  check("gõ đúng tên có dấu → nhận", I("p_ward").dataset.value === "Xã Ba Tơ");
  // bỏ dấu KHÔNG tự đoán
  I("p_ward").value = "Xa Ba To";
  I("p_ward").dispatchEvent(new w.Event("blur"));
  await sleep(200);
  check("gõ không dấu rồi rời ô → không tự đoán", I("p_ward").dataset.value === "Xã Ba Tơ");

  // ---- 7. đổi tỉnh → xoá xã, nạp list mới ----
  w.addrOpen("p_prov", "ha noi");
  d.querySelector('.addr-combo[data-fieldname="p_prov"] .combo-item').dispatchEvent(new w.Event("pointerdown", { bubbles: true, cancelable: true }));
  await sleep(80);
  check("đổi tỉnh → Hà Nội", I("p_prov").dataset.value === "Thành phố Hà Nội" && I("p_prov").dataset.code === "01");
  check("đổi tỉnh → xã bị xoá", I("p_ward").dataset.value === "" && I("p_ward").value === "");
  w.addrOpen("p_ward", "");
  items = [...d.querySelectorAll('.addr-combo[data-fieldname="p_ward"] .combo-item')].map(e => e.textContent);
  check("list xã theo tỉnh mới", items.length === 2 && items[0] === "Phường Ba Đình", items);
  check("đổi tỉnh → cả 2 ô tô 'đã đổi'", d.getElementById("fg_p_prov").classList.contains("changed") && d.getElementById("fg_p_ward").classList.contains("changed"));
  check("đổi tỉnh KHÔNG đụng cặp địa chỉ hiện tại", I("c_prov").dataset.value === "Tỉnh Quảng Ngãi");

  // ---- 8. nút ✕ xoá tỉnh → xã xoá + khoá ----
  const clr = d.querySelector('.addr-combo[data-fieldname="p_prov"] .addr-clear');
  check("nút ✕ hiện khi có giá trị", !clr.classList.contains("hidden"));
  clr.dispatchEvent(new w.Event("pointerdown", { bubbles: true, cancelable: true }));
  await sleep(80);
  check("✕ xoá tỉnh", I("p_prov").dataset.value === "");
  check("xoá tỉnh → xã khoá + trống", I("p_ward").disabled && I("p_ward").dataset.value === "");
  check("nút ✕ ẩn khi trống", clr.classList.contains("hidden"));

  // ---- 9. currentValue = giá trị đã chọn, không phải chữ đang gõ ----
  I("c_ward").value = "đang gõ dở";
  check("currentValue bỏ qua chữ đang gõ", w.currentValue({ fieldname: "c_ward", widget: "Address Ward" }) === "");

  // ---- 10. dữ liệu cũ không có trong danh mục → trống, không lỗi ----
  ({ w, d } = await boot({ p_prov: "Tỉnh Quảng Nam", p_ward: "Xã Cũ", c_prov: "Tỉnh Quảng Ngãi", c_ward: "Xã Không Có" }));
  const J = (fn) => d.getElementById("f_" + fn);
  check("tỉnh cũ → ô trống", J("p_prov").value === "" && J("p_prov").dataset.value === "");
  check("tỉnh cũ → xã khoá", J("p_ward").disabled);
  check("xã cũ (tỉnh đúng) → xã trống, vẫn bật", J("c_ward").value === "" && !J("c_ward").disabled);

  // ---- 11. read_only ----
  ({ w, d } = await boot({ p_prov: "Tỉnh Quảng Ngãi", p_ward: "Xã Ba Tơ" }, { p_prov: { read_only: true }, p_ward: { read_only: true } }));
  const K = (fn) => d.getElementById("f_" + fn);
  check("read_only: tỉnh khoá nhưng hiện giá trị", K("p_prov").disabled && K("p_prov").value === "Tỉnh Quảng Ngãi");
  check("read_only: xã khoá nhưng hiện giá trị", K("p_ward").disabled && K("p_ward").value === "Xã Ba Tơ");
  check("read_only: không có nút ✕", d.querySelector('.addr-combo[data-fieldname="p_prov"] .addr-clear').classList.contains("hidden"));

  // ---- 12. auto_fill = 0 → không mặc định Quảng Ngãi ----
  ({ w, d } = await boot({ p_prov: "", p_ward: "" }, { p_prov: { auto_fill: false } }));
  check("auto_fill=0 → tỉnh trống", d.getElementById("f_p_prov").value === "");

  // ---- 13. ngày hết hạn CCCD tự tính ----
  ({ w, d, calls } = await boot({ p_prov: "Tỉnh Quảng Ngãi", p_ward: "Xã Ba Tơ",
    date_of_birth: "2001-07-29", custom_id_card_date_of_issue: "2023-08-12", custom_id_card__date_of_expired: "2099-01-01" }));
  const E = d.getElementById("f_custom_id_card__date_of_expired");
  const ISS = d.getElementById("f_custom_id_card_date_of_issue");
  const DOB = d.getElementById("f_date_of_birth");
  check("hết hạn: ô chỉ đọc", E.readOnly && E.classList.contains("auto-calc"));
  check("hết hạn: lúc mở form tính lại (bỏ giá trị cũ sai)", E.value === "2026-07-29", E.value);
  ISS.value = "2021-03-01"; ISS.dispatchEvent(new w.Event("input", { bubbles: true }));
  check("hết hạn: đổi ngày cấp → tính lại (mốc 25 vì cấp lúc 19 tuổi)", E.value === "2026-07-29", E.value);
  ISS.value = "2024-01-10"; ISS.dispatchEvent(new w.Event("change", { bubbles: true }));
  check("hết hạn: cấp lúc 22 tuổi → vẫn mốc 25", E.value === "2026-07-29", E.value);
  ISS.value = "2024-08-01"; ISS.dispatchEvent(new w.Event("change", { bubbles: true }));
  check("hết hạn: cấp lúc 23 tuổi (trong 2 năm trước mốc 25) → mốc 40", E.value === "2041-07-29", E.value);
  check("hết hạn: đổi → tô 'đã đổi'", d.getElementById("fg_custom_id_card__date_of_expired").classList.contains("changed"));
  ISS.value = "2021-01-01"; ISS.dispatchEvent(new w.Event("input", { bubbles: true }));
  DOB.value = "2000-02-29"; DOB.dispatchEvent(new w.Event("input", { bubbles: true }));
  check("hết hạn: sinh 29/02 → 28/02 năm không nhuận (bản cũ ra 2025-02-29)", E.value === "2025-02-28", E.value);
  DOB.value = "1960-01-01"; DOB.dispatchEvent(new w.Event("input", { bubbles: true }));
  check("hết hạn: cấp từ 58 tuổi → trống (không thời hạn)", E.value === "", E.value);
  // gửi: hết hạn trống (required) + quá hạn (Future) KHÔNG chặn
  d.getElementById("f__commit").checked = true;
  DOB.value = "1998-01-01"; DOB.dispatchEvent(new w.Event("input", { bubbles: true }));
  ISS.value = "2015-01-01"; ISS.dispatchEvent(new w.Event("input", { bubbles: true }));
  check("hết hạn: thẻ đã quá hạn hiện đúng ngày quá khứ", E.value === "2023-01-01", E.value);
  await sleep(50);   // SignPad.init chạy trong requestAnimationFrame
  const pad = d.getElementById("sign_pad");
  const pe = (t) => { const e = new w.MouseEvent(t, { bubbles: true, cancelable: true, clientX: 10, clientY: 10 }); e.pointerId = 1; return e; };
  pad.dispatchEvent(pe("pointerdown")); pad.dispatchEvent(pe("pointerup"));
  await w.submitForm();
  const sent = calls.find(c => c[0].endsWith("save_form_data"));
  check("gửi: thẻ quá hạn + Future/required KHÔNG chặn gửi", !!sent, d.getElementById("toast").textContent);

  // ---- 14. dân tộc mặc định "Kinh" ----
  ({ w, d } = await boot({ custom_ethnicity: "" }));
  check("dân tộc trống → điền sẵn Kinh", d.getElementById("f_custom_ethnicity").value === "Kinh");
  check("dân tộc điền sẵn không tô 'đã đổi' lúc load", !d.getElementById("fg_custom_ethnicity").classList.contains("changed"));
  ({ w, d } = await boot({ custom_ethnicity: "Tày" }));
  check("dân tộc đã có (Tày) → giữ nguyên", d.getElementById("f_custom_ethnicity").value === "Tày");
  ({ w, d } = await boot({ custom_ethnicity: "" }, { eth: { auto_fill: false } }));
  check("dân tộc auto_fill=0 → không điền", d.getElementById("f_custom_ethnicity").value === "");
  ({ w, d } = await boot({ custom_ethnicity: "" }, { eth: { read_only: true } }));
  check("dân tộc read_only → không điền", d.getElementById("f_custom_ethnicity").value === "");

  // ---- 15. tự chuẩn hoá chữ + bỏ ô Ghi chú thêm ----
  ({ w, d, calls } = await boot({ p_prov: "Tỉnh Quảng Ngãi", p_ward: "Xã Ba Tơ", custom_ethnicity: "Kinh" }));
  check("không còn ô 'Ghi chú thêm'", !d.getElementById("f__remarks") && !d.body.textContent.includes("Ghi chú thêm"));
  const blur = (id, v) => { const el = d.getElementById(id); el.value = v; el.dispatchEvent(new w.Event("change", { bubbles: true })); return el.value; };
  check("rời ô: tên người (Capitalize Each Word) → Hoa Đầu Mỗi Từ", blur("f_person_to_be_contacted", "đoàn  thanh phi") === "Đoàn Thanh Phi");
  check("rời ô: Sentence Case → hoa đầu mỗi câu",
    blur("f_custom_strengths", "tôi thích bóng đá. thích cả cầu lông!  còn gì nữa? (hát)\n nấu ăn. TP.HCM") === "Tôi thích bóng đá. Thích cả cầu lông! Còn gì nữa? (Hát)\nNấu ăn. TP.HCM",
    d.getElementById("f_custom_strengths").value);
  check("rời ô: hoa ký tự đầu + chữ–số", blur("f_village", "  xóm1   thôn tây ") === "Xóm 1 thôn tây");
  check("rời ô: Email chỉ bỏ khoảng trắng", blur("f_personal_email", " Abc@Gmail.com ") === "Abc@Gmail.com");
  check("rời ô: giữ mã TDP1", blur("f_village", "TDP1") === "TDP1");
  check("rời ô: Capitalize Each Word → hoa đầu mỗi từ, giữ phần còn lại",
    blur("f_custom_favorite_sport", " bóng   đá, cầu lông TDP1 ") === "Bóng Đá, Cầu Lông TDP1", d.getElementById("f_custom_favorite_sport").value);
  blur("f_village", "thôn 3, xóm đông");
  d.getElementById("f_person_to_be_contacted").value = "duong minh thang";   // gõ rồi bấm Gửi luôn (chưa rời ô)
  d.getElementById("f__commit").checked = true;
  await sleep(50);
  const pad2 = d.getElementById("sign_pad");
  const pe2 = (t) => { const e = new w.MouseEvent(t, { bubbles: true, cancelable: true, clientX: 10, clientY: 10 }); e.pointerId = 1; return e; };
  pad2.dispatchEvent(pe2("pointerdown")); pad2.dispatchEvent(pe2("pointerup"));
  await w.submitForm();
  const sent2 = calls.filter(c => c[0].endsWith("save_form_data")).pop();
  const payload = sent2 ? JSON.parse(sent2[1].data) : {};
  check("gửi: giá trị đã chuẩn hoá (kể cả chưa rời ô)", payload.person_to_be_contacted === "Duong Minh Thang" && payload.village === "Thôn 3, xóm đông", payload);
  check("gửi: không còn __remarks", sent2 && !("__remarks" in payload));

  report(results);
})().catch((e) => { console.error(e); process.exit(2); });
