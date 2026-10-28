// Setting "Start Screen Notes" (28/10/2026, Text Editor): HTML server đã làm sạch, hiện ở màn hình đầu trên thẻ "Chọn nhân viên".
const { JSDOM } = require("jsdom");
const { pageHtml, stubBrowser, sleep, report } = require("./harness");

const html = pageHtml();
const results = [];
const check = (name, ok, detail) => results.push([!!ok, name, detail]);

async function boot(notes, query = "") {
  const config = {
    sections: [{ label: "A", fields: [{ fieldname: "cell_number", label: "SĐT", fieldtype: "Data", widget: "Auto", width: "Full",
      required: false, read_only: false, auto_fill: true, validation: "", min_length: 0, max_length: 0 }] }],
    allow_local_draft: false, lock_after_submit: false, save_file_type: "PDF", commitment_html: "Cam kết", documents: [],
  };
  if (notes !== undefined) config.start_notes_html = notes;
  const dom = new JSDOM(html, {
    runScripts: "dangerously", url: "https://erp.test/employee-self-update-info" + query,
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
        else if (m === "get_form_data") message = { original: {}, values: {}, has_existing: false, status: null, employee_name: "A", is_hr: true, documents: [] };
        else if (m === "save_form_data") message = { status: "success", download_token: "t" };
        return { status: 200, json: async () => ({ message }) };
      };
    },
  });
  await sleep(80);
  return dom.window;
}

(async () => {
  const html = '<div class="ql-editor read-mode"><p>Chuẩn bị <strong>CCCD</strong></p><ul><li>Số BHXH</li></ul>'
    + '<p><a href="https://baohiemxahoi.gov.vn/tracuu/Pages/tra-cuu-ho-gia-dinh.aspx">tra cứu</a></p></div>';
  let w = await boot(html);
  let box = w.document.getElementById("start_notes");
  check("có ghi chú → hiện ngay màn hình đầu", !box.classList.contains("hidden"));
  check("nằm TRÊN thẻ Chọn nhân viên",
    box.compareDocumentPosition(w.document.getElementById("picker_card")) & w.Node.DOCUMENT_POSITION_FOLLOWING);
  check("giữ định dạng (đậm, danh sách)", box.querySelector("strong") && box.querySelector("ul li"), box.innerHTML);
  const a = box.querySelector("a");
  check("link mở tab mới, rel noopener", a && a.target === "_blank" && a.rel === "noopener noreferrer", box.innerHTML);
  check("không còn ghi chú mục đích viết cứng (#purpose_note)", !w.document.getElementById("purpose_note"));
  // Nút "Bắt đầu" (28/10/2026): có ghi chú → đọc trước, bấm mới hiện ô chọn NV
  const btn = w.document.getElementById("start_btn"), picker = w.document.getElementById("picker_card");
  check("có ghi chú → nút Bắt đầu ngay dưới ghi chú, ô chọn NV ẩn", !btn.classList.contains("hidden") && picker.classList.contains("hidden")
    && box.nextElementSibling === btn);
  btn.click();
  check("bấm Bắt đầu → hiện ô chọn NV, ẩn nút + ẩn ghi chú (đã đọc), focus ô tìm", !picker.classList.contains("hidden")
    && btn.classList.contains("hidden") && box.classList.contains("hidden")
    && w.document.activeElement === w.document.getElementById("emp_search"), w.document.activeElement && w.document.activeElement.id);
  w.eval(`S.config = null; loadForm("TIQN-1", "")`);
  await sleep(100);
  check("đang khai form → ghi chú vẫn ẩn (đã bấm Bắt đầu)", box.classList.contains("hidden"));
  await w.eval("submitForm()");
  await sleep(50);
  check("màn hình Đã gửi → ẩn ghi chú + nút Bắt đầu", box.classList.contains("hidden") && btn.classList.contains("hidden")
    && !w.document.getElementById("success_area").classList.contains("hidden"));
  w = await boot("");
  check("Setting trống → không hiện", w.document.getElementById("start_notes").classList.contains("hidden"));
  check("Setting trống → không có nút Bắt đầu, hiện ô chọn NV ngay", w.document.getElementById("start_btn").classList.contains("hidden")
    && !w.document.getElementById("picker_card").classList.contains("hidden"));
  w = await boot(html, "?emp=TIQN-1");
  await sleep(100);
  check("link ?emp= → không nút Bắt đầu, không ô chọn NV (mở thẳng NV)", w.document.getElementById("start_btn").classList.contains("hidden")
    && w.document.getElementById("picker_card").classList.contains("hidden"));
  w = await boot(undefined);
  check("server cũ (không có khoá) → không hiện", w.document.getElementById("start_notes").classList.contains("hidden"));
  report(results);
})().catch(e => { console.error(e); process.exit(1); });
