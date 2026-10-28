// Setting "Allow Receipt Download" (28/10/2026): tắt → màn hình "Đã gửi" không có nút / gợi ý / câu lưu phiếu.
// Cờ thiếu (server cũ) → vẫn hiện như trước.
const { JSDOM } = require("jsdom");
const { pageHtml, stubBrowser, sleep, report } = require("./harness");

const html = pageHtml();
const results = [];
const check = (name, ok, detail) => results.push([!!ok, name, detail]);

async function submitWith(flag) {
  const config = {
    sections: [{ label: "A", fields: [{ fieldname: "cell_number", label: "SĐT", fieldtype: "Data", widget: "Auto", width: "Full",
      required: false, read_only: false, auto_fill: true, validation: "", min_length: 0, max_length: 0 }] }],
    allow_local_draft: false, lock_after_submit: false, save_file_type: "PDF", commitment_html: "Cam kết", documents: [],
  };
  if (flag !== undefined) config.allow_receipt_download = flag;
  const dom = new JSDOM(html, {
    runScripts: "dangerously", url: "https://erp.test/employee-self-update-info",
    beforeParse(w) {
      stubBrowser(w);
      w.csrf_token = "x";
      w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
      w.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, { get: () => () => {} });
      w.fetch = async (url) => {
        const m = url.split("/api/method/")[1].split(".").pop();
        let message = null;
        if (m === "get_field_config") message = config;
        else if (m === "get_eligible_employees") message = [{ employee_id: "TIQN-1", display_name: "A", submitted: false }];
        else if (m === "get_form_data") message = { original: {}, values: { cell_number: "09" }, has_existing: false, status: null, employee_name: "A", is_hr: true, documents: [] };
        else if (m === "save_form_data") message = { status: "success", download_token: flag === false ? null : "t" };
        return { status: 200, json: async () => ({ message }) };
      };
    },
  });
  const w = dom.window;
  await sleep(50);
  w.eval(`S.config = null; loadForm("TIQN-1", "")`);
  await sleep(100);
  await w.eval("submitForm()");
  await sleep(50);
  const d = w.document;
  const shown = (id) => !d.getElementById(id).classList.contains("hidden");
  return { success: shown("success_area"), btn: shown("save_btn"), hint: shown("save_hint"), note: shown("save_note") };
}

(async () => {
  let r = await submitWith(true);
  check("bật: hiện nút tải + gợi ý + câu lưu phiếu", r.success && r.btn && r.hint && r.note, r);
  r = await submitWith(false);
  check("tắt: vẫn báo đã gửi, ẩn nút tải + gợi ý + câu lưu phiếu", r.success && !r.btn && !r.hint && !r.note, r);
  r = await submitWith(undefined);
  check("server cũ (không có cờ): hiện như trước", r.success && r.btn && r.note, r);
  report(results);
})().catch(e => { console.error(e); process.exit(1); });
