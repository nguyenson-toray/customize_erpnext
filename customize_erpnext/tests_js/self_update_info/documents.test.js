// Hồ sơ nộp kèm (Setting → Document Checklist, 27/10/2026): thẻ tick, nháp, gửi kèm `documents`.
const { JSDOM } = require("jsdom");
const { pageHtml, stubBrowser, sleep, report } = require("./harness");

const html = pageHtml();
const results = [];
const check = (name, ok, detail) => results.push([!!ok, name, detail]);

function makeDom(config, formData) {
  const calls = [];
  const dom = new JSDOM(html, {
    runScripts: "dangerously", url: "https://erp.test/employee-self-update-info",
    beforeParse(w) {
      stubBrowser(w);
      w.csrf_token = "x";
      w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
      w.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, { get: () => () => {} });
      w.fetch = async (url, opts) => {
        const m = url.split("/api/method/")[1].split(".").pop();
        const args = {};
        if (opts && opts.body && opts.body.forEach) opts.body.forEach((v, k) => args[k] = v);
        calls.push([m, args]);
        let message = null;
        if (m === "get_field_config") message = config;
        else if (m === "get_eligible_employees") message = [{ employee_id: "TIQN-1", display_name: "A", submitted: false }];
        else if (m === "get_form_data") message = formData;
        else if (m === "save_form_data") message = { status: "success", download_token: "t" };
        else if (m === "get_access_info") message = { submitted: false, locked: false };
        return { status: 200, json: async () => ({ message }) };
      };
    },
  });
  return { dom, w: dom.window, calls };
}

const baseCfg = {
  sections: [{ label: "A", fields: [{ fieldname: "cell_number", label: "SĐT", fieldtype: "Data", required: false, read_only: false, auto_fill: true, widget: "Auto" }] }],
  allow_local_draft: true, commitment_html: "Cam kết", save_file_type: "PDF",
  documents: [{ document: "CCCD <b>", required: 1 }, { document: "GPLX", required: 0 }, { document: "Khám SK", required: 1 }],
};
const fd = { original: {}, values: { cell_number: "09" }, has_existing: true, status: "Submitted", employee_name: "A", is_hr: true, documents: ["GPLX"] };

(async () => {
  let { w, calls } = makeDom(baseCfg, fd);
  await sleep(50);
  w.eval(`S.config = null; loadForm("TIQN-1", "")`);
  await sleep(100);
  const doc = w.document;
  const card = doc.getElementById("doc_card");
  const boxes = [...doc.querySelectorAll("#doc_list input[type=checkbox]")];
  check("thẻ hồ sơ hiện khi Setting có hồ sơ", card && !card.classList.contains("hidden"));
  check("3 ô tick theo Setting", boxes.length === 3, boxes.length);
  check("tick sẵn hồ sơ lần gửi trước", boxes.map(b => b.checked).join() === "false,true,false");
  check("escape tên hồ sơ + dấu * bắt buộc", doc.getElementById("doc_list").innerHTML.includes("CCCD &lt;b&gt; <span class=\"req\">*</span>")
    && !doc.getElementById("doc_list").innerHTML.includes("GPLX <span class=\"req\""));
  check("thẻ hồ sơ nằm trước thẻ cam kết", card.compareDocumentPosition(doc.getElementById("sign_card")) & w.Node.DOCUMENT_POSITION_FOLLOWING);
  boxes[0].checked = true; boxes[0].dispatchEvent(new w.Event("change", { bubbles: true }));
  await sleep(500);
  const draft = JSON.parse(w.localStorage.getItem([...Array(w.localStorage.length).keys()].map(i => w.localStorage.key(i)).find(k => /TIQN-1/.test(k)) || "null") || "{}");
  check("nháp lưu hồ sơ đã tick", JSON.stringify(draft.docs) === JSON.stringify(["CCCD <b>", "GPLX"]), draft);
  await w.eval(`submitForm()`);
  await sleep(50);
  const save = calls.find(c => c[0] === "save_form_data");
  check("gửi phiếu kèm documents (thiếu Khám SK vẫn gửi được)", save && save[1].documents === JSON.stringify(["CCCD <b>", "GPLX"]), save && save[1]);

  // khôi phục nháp: nháp thắng giá trị server
  ({ w, calls } = makeDom(baseCfg, { ...fd, documents: [] }));
  w.eval(`localStorage.setItem(draftKey("TIQN-1"), JSON.stringify({ t: Date.now(), values: {}, docs: ["Khám SK"] }))`);
  w.eval(`S.config = null; loadForm("TIQN-1", "")`);
  await sleep(100);
  check("khôi phục nháp: tick theo nháp", [...w.document.querySelectorAll("#doc_list input")].map(b => b.checked).join() === "false,false,true");

  // Setting trống → ẩn thẻ, gửi documents = []
  ({ w, calls } = makeDom({ ...baseCfg, documents: [] }, fd));
  w.eval(`S.config = null; loadForm("TIQN-1", "")`);
  await sleep(100);
  check("Setting trống → ẩn thẻ", w.document.getElementById("doc_card").classList.contains("hidden"));
  await w.eval(`submitForm()`);
  await sleep(50);
  const s2 = calls.find(c => c[0] === "save_form_data");
  check("Setting trống → documents = []", s2 && s2[1].documents === "[]", s2 && s2[1]);

  report(results);
})().catch(e => { console.error(e); process.exit(1); });
