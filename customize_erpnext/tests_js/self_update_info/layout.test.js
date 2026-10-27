// 2 field "Half" cùng 1 hàng (Setting → Width on Form, 27/10/2026): ghép cặp, Half lẻ / bạn cặp bị ẩn → cả hàng,
// Detail của Half nằm dưới ô nhập, nhãn trong cặp cao bằng nhau, màn hình < 360px không cân nhãn.
const { JSDOM } = require("jsdom");
const { pageHtml, stubBrowser, sleep, report } = require("./harness");

const html = pageHtml();
const results = [];
const check = (name, ok, detail) => results.push([!!ok, name, detail]);

const F = (fieldname, label, width, extra = {}) => ({
  fieldname, label, fieldtype: "Data", widget: "Auto", width, required: false, read_only: false, auto_fill: true,
  validation: "", min_length: 0, max_length: 0, detail: "", placeholder: "", ...extra,
});
const config = {
  sections: [
    { label: "Thông tin chung", fields: [
      F("gender", "Giới tính", "Half", { fieldtype: "Select", options: ["", "Male", "Female"] }),
      F("date_of_birth", "Ngày sinh", "Half", { fieldtype: "Date", detail: "Chọn từ lịch" }),
      F("custom_ethnicity", "Dân tộc", "Half"),
      F("cell_number", "Số điện thoại", "Full", { detail: "Số đang dùng" }),
      F("custom_religion", "Tôn giáo", "Half"),
    ] },
    { label: "Thông tin khác", fields: [
      F("custom_driving_license", "Giấy phép lái xe", "Half", { fieldtype: "Select", options: ["", "Có", "Chưa"] }),
      F("custom_driving_license_status", "Tình trạng GPLX (đang đợi cấp hay chưa thi)", "Half",
        { fieldtype: "Select", options: ["", "Đang đợi cấp"], depends_on: { field: "custom_driving_license", values: ["Chưa"] } }),
      F("bank_ac_no", "Số TK", "Half"),
      F("custom_bank_branch", "Chi nhánh", "Half"),
      { ...F("education", "Học vấn", "Half"), fieldtype: "Table", options: "Employee Education", max_rows: 1,
        columns: [{ fieldname: "level", label: "Trình độ", fieldtype: "Data", options: null, required: false, placeholder: "" }] },
    ] },
  ],
  require_dob: false, allow_local_draft: false, lock_after_submit: false, save_file_type: "PDF",
  commitment_html: "Cam kết", documents: [],
};

async function boot(width) {
  const dom = new JSDOM(html, {
    runScripts: "dangerously", pretendToBeVisual: true, url: "https://erp.test/employee-self-update-info",
    beforeParse(w) {
      stubBrowser(w);
      w.csrf_token = "x";
      w.innerWidth = width;
      w.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, { get: () => () => {} });
      // Chiều cao nhãn giả lập: nhãn dài (> 20 ký tự) xuống 2 dòng.
      Object.defineProperty(w.HTMLElement.prototype, "offsetHeight", {
        configurable: true, get() { return this.matches("label.fl") ? (this.textContent.trim().length > 20 ? 40 : 20) : 0; },
      });
      w.fetch = async (url) => {
        const m = url.split("/api/method/")[1].split(".").pop();
        let message = null;
        if (m === "get_field_config") message = config;
        else if (m === "get_eligible_employees") message = [{ employee_id: "TIQN-1", display_name: "A", submitted: false }];
        else if (m === "get_form_data") message = { original: {}, values: {}, has_existing: false, status: null, employee_name: "A", is_hr: true, documents: [] };
        return { status: 200, json: async () => ({ message }) };
      };
    },
  });
  const w = dom.window;
  await sleep(50);
  w.eval(`S.config = null; loadForm("TIQN-1", "")`);
  await sleep(120);
  return w;
}

(async () => {
  let w = await boot(400);
  const d = w.document;
  const box = (fn) => d.getElementById("fg_" + fn);
  const cls = (fn) => [...box(fn).classList].filter(c => c === "half" || c === "solo").join(" ");

  check("field nằm trong lưới .fgrid của thẻ", box("gender").parentElement.classList.contains("fgrid"));
  check("Half → class half; Full → không", cls("gender") === "half" && cls("cell_number") === "");
  check("bảng con không bao giờ Half (dù cấu hình Half)", cls("education") === "");
  check("cặp Giới tính | Ngày sinh: không solo", cls("gender") === "half" && cls("date_of_birth") === "half");
  check("Dân tộc đứng trước field Full → solo (cả hàng)", cls("custom_ethnicity") === "half solo", cls("custom_ethnicity"));
  check("Half cuối Section → solo", cls("custom_religion") === "half solo", cls("custom_religion"));
  const dob = box("date_of_birth");
  check("Half: Detail nằm DƯỚI ô nhập",
    dob.lastElementChild.classList.contains("field-detail") && dob.querySelector("input").compareDocumentPosition(dob.querySelector(".field-detail")) & w.Node.DOCUMENT_POSITION_FOLLOWING);
  const phone = box("cell_number");
  check("Full: Detail vẫn nằm dưới nhãn, trên ô nhập",
    phone.children[1].classList.contains("field-detail") && !phone.lastElementChild.classList.contains("field-detail"));

  // field "chỉ hiện khi…": Tình trạng GPLX ẩn → GPLX lẻ = solo; Số TK | Chi nhánh vẫn là 1 cặp
  check("bạn cặp đang ẩn → GPLX solo", box("custom_driving_license_status").classList.contains("hidden")
    && cls("custom_driving_license") === "half solo", cls("custom_driving_license"));
  check("cặp cố định: Số TK | Chi nhánh vẫn là 1 cặp (GPLX không ghép sang Số TK)",
    cls("bank_ac_no") === "half" && cls("custom_bank_branch") === "half", [cls("bank_ac_no"), cls("custom_bank_branch")]);
  const lic = d.getElementById("f_custom_driving_license");
  lic.value = "Chưa"; lic.dispatchEvent(new w.Event("change", { bubbles: true }));
  await sleep(20);
  check("chọn 'Chưa' → hiện Tình trạng GPLX, GPLX hết solo (ghép cặp)",
    !box("custom_driving_license_status").classList.contains("hidden") && cls("custom_driving_license") === "half"
    && cls("custom_driving_license_status") === "half", [cls("custom_driving_license"), cls("custom_driving_license_status")]);
  const l1 = box("custom_driving_license").querySelector("label.fl"), l2 = box("custom_driving_license_status").querySelector("label.fl");
  check("nhãn trong cặp cao bằng nhau (nhãn dài xuống dòng)", l1.style.minHeight === "40px" && l2.style.minHeight === "40px",
    [l1.style.minHeight, l2.style.minHeight]);
  lic.value = "Có"; lic.dispatchEvent(new w.Event("change", { bubbles: true }));
  await sleep(20);
  check("chọn lại 'Có' → GPLX solo, bỏ cân nhãn", cls("custom_driving_license") === "half solo" && l1.style.minHeight === "",
    [cls("custom_driving_license"), l1.style.minHeight]);

  // màn hình rất hẹp: vẫn ghép class (CSS @media cho cả hàng) nhưng không cân nhãn
  w = await boot(340);
  const g1 = w.document.getElementById("fg_gender").querySelector("label.fl");
  const lb = w.document.getElementById("fg_bank_ac_no").querySelector("label.fl");
  check("< 360px: không đặt min-height nhãn", g1.style.minHeight === "" && lb.style.minHeight === "");
  const css = require("fs").readFileSync(require("path").join(process.env.ESUI_PAGE_DIR
    || require("path").join(__dirname, "..", "..", "www", "employee-self-update-info"), "style.css"), "utf8");
  check("style.css: @media (max-width:359px) đưa Half về cả hàng", /@media \(max-width:359px\)\s*\{[^}]*\.field\.half\s*\{\s*grid-column:1 \/ -1;/.test(css));

  report(results);
})().catch(e => { console.error(e); process.exit(1); });
