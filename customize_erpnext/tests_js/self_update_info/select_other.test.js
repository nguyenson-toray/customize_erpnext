// 28/10/2026: (1) widget "Select + Other" (ăn chay: dropdown + "Khác" → ô nhập tự do, field Employee là Data);
// (2) bug: HR ký mà chưa tick cam kết vẫn gửi được → ký thì phải tick, kể cả HR.
const { JSDOM } = require("jsdom");
const { pageHtml, stubBrowser, sleep, report } = require("./harness");

const html = pageHtml();
const results = [];
const check = (name, ok, detail) => results.push([!!ok, name, detail]);

const VEG = {
  fieldname: "custom_vegetarian", label: "Ăn chay", fieldtype: "Select", widget: "Auto", width: "Full", allow_other: true,
  options: ["", "Không", "Ăn chay trường", "Ăn chay rằm & mồng 1"], option_labels: {},
  required: true, read_only: false, auto_fill: true, validation: "", min_length: 0, max_length: 0,
};

async function boot(values, isHR = false, fieldOver = {}) {
  const calls = [];
  const config = {
    sections: [{ label: "A", fields: [{ ...VEG, ...fieldOver }] }],
    allow_local_draft: false, lock_after_submit: false, save_file_type: "PDF", commitment_html: "Cam kết", documents: [],
    start_notes_html: "",
  };
  const dom = new JSDOM(html, {
    runScripts: "dangerously", url: "https://erp.test/employee-self-update-info",
    beforeParse(w) {
      stubBrowser(w);
      w.csrf_token = "x";
      w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
      w.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, { get: () => () => {} });
      w.fetch = async (url, opts) => {
        const m = url.split("/api/method/")[1].split(".").pop();
        const body = {};
        if (opts && opts.body && opts.body.forEach) opts.body.forEach((v, k) => { body[k] = v; });
        calls.push([m, body]);
        let message = null;
        if (m === "get_field_config") message = config;
        else if (m === "get_eligible_employees") message = [{ employee_id: "TIQN-1", display_name: "A", submitted: false }];
        else if (m === "get_form_data") message = { original: { ...values }, values: { ...values }, has_existing: false, status: null, employee_name: "A", is_hr: isHR, documents: [] };
        else if (m === "save_form_data") message = { status: "success", download_token: "t" };
        return { status: 200, json: async () => ({ message }) };
      };
    },
  });
  const w = dom.window;
  await sleep(80);
  w.eval(`S.config = null; loadForm("TIQN-1", "")`);
  await sleep(120);
  return { w, d: w.document, calls };
}

function sign(w, d) {
  const pad = d.getElementById("sign_pad");
  const pe = (t) => { const e = new w.MouseEvent(t, { bubbles: true, cancelable: true, clientX: 10, clientY: 10 }); e.pointerId = 1; return e; };
  pad.dispatchEvent(pe("pointerdown")); pad.dispatchEvent(pe("pointerup"));
}
const saved = (calls) => calls.filter((c) => c[0] === "save_form_data");
const payload = (calls) => { const s = saved(calls).pop(); return s ? JSON.parse(s[1].data) : null; };
const pick = (w, el, v) => { el.value = v; el.dispatchEvent(new w.Event("change", { bubbles: true })); };

(async () => {
  // ---- Select + Other ----
  let { w, d, calls } = await boot({ custom_vegetarian: "Ăn chay trường" });
  let sel = d.getElementById("f_custom_vegetarian"), other = d.getElementById("f_custom_vegetarian__other");
  check("dropdown có mục Khác ở cuối", sel && sel.options[sel.options.length - 1].textContent === "Khác"
    && sel.options[sel.options.length - 1].value === "__other__", sel && sel.innerHTML);
  check("giá trị trong danh sách → chọn đúng, ô Khác ẩn", sel.value === "Ăn chay trường" && other.classList.contains("hidden"));
  pick(w, sel, "__other__");
  check("chọn Khác → hiện ô nhập", !other.classList.contains("hidden"));
  d.getElementById("f__commit").checked = true;
  await sleep(30); sign(w, d);
  await w.submitForm();
  check("Khác + ô trống → chặn gửi, báo thiếu (Khác)", !saved(calls).length && /Ăn chay \(Khác\)/.test(d.getElementById("toast").textContent),
    d.getElementById("toast").textContent);
  other.value = "  ăn chay   thứ 6 "; other.dispatchEvent(new w.Event("input", { bubbles: true }));
  check("gõ ở ô Khác → tô 'đã đổi'", d.getElementById("fg_custom_vegetarian").classList.contains("changed"));
  other.dispatchEvent(new w.Event("change", { bubbles: true }));
  check("rời ô Khác → chuẩn hoá như field Data", other.value === "Ăn chay thứ 6", other.value);
  await w.submitForm();
  check("gửi: giá trị = chữ gõ ở Khác", payload(calls) && payload(calls).custom_vegetarian === "Ăn chay thứ 6", payload(calls));
  check("gửi: không lộ giá trị __other__", !JSON.stringify(payload(calls) || {}).includes("__other__"));

  ({ w, d, calls } = await boot({ custom_vegetarian: "Ăn chay thứ 6" }));
  sel = d.getElementById("f_custom_vegetarian"); other = d.getElementById("f_custom_vegetarian__other");
  check("giá trị ngoài danh sách (lần gửi trước) → chọn sẵn Khác + điền ô", sel.value === "__other__"
    && !other.classList.contains("hidden") && other.value === "Ăn chay thứ 6", [sel.value, other.value]);
  check("load không tô 'đã đổi'", !d.getElementById("fg_custom_vegetarian").classList.contains("changed"));
  pick(w, sel, "Không");
  check("đổi về mục có sẵn → ẩn ô Khác", other.classList.contains("hidden"));
  d.getElementById("f__commit").checked = true;
  await sleep(30); sign(w, d);
  await w.submitForm();
  check("gửi: mục có sẵn", payload(calls) && payload(calls).custom_vegetarian === "Không", payload(calls));

  ({ w, d, calls } = await boot({ custom_vegetarian: "" }, false, { required: false }));
  sel = d.getElementById("f_custom_vegetarian");
  pick(w, sel, "__other__");
  d.getElementById("f__commit").checked = true;
  await sleep(30); sign(w, d);
  await w.submitForm();
  check("field không bắt buộc nhưng chọn Khác mà trống → vẫn báo thiếu", !saved(calls).length, d.getElementById("toast").textContent);

  ({ w, d } = await boot({ custom_vegetarian: "Ăn chay thứ 6" }, false, { read_only: true }));
  check("read_only → dropdown + ô Khác đều khoá", d.getElementById("f_custom_vegetarian").disabled
    && d.getElementById("f_custom_vegetarian__other").disabled);

  ({ w, d } = await boot({ custom_vegetarian: "Ăn chay thứ 6" }, false, { allow_other: false }));
  check("Select thường (không allow_other) → không có Khác / ô nhập", !d.getElementById("f_custom_vegetarian__other")
    && ![...d.getElementById("f_custom_vegetarian").options].some((o) => o.value === "__other__"));

  // ---- cam kết ----
  ({ w, d, calls } = await boot({ custom_vegetarian: "Không" }, true));
  await sleep(30); sign(w, d);
  await w.submitForm();
  check("HR: đã ký nhưng chưa tick cam kết → chặn", !saved(calls).length && /cam kết/.test(d.getElementById("toast").textContent),
    d.getElementById("toast").textContent);
  d.getElementById("f__commit").checked = true;
  await w.submitForm();
  check("HR: ký + tick → gửi được, commitment=1", saved(calls).length === 1 && saved(calls)[0][1].commitment === "1",
    saved(calls).map((c) => c[1].commitment));

  ({ w, d, calls } = await boot({ custom_vegetarian: "Không" }, true));
  await w.submitForm();
  check("HR: không ký, không tick (sửa hộ) → vẫn gửi được", saved(calls).length === 1, d.getElementById("toast").textContent);

  ({ w, d, calls } = await boot({ custom_vegetarian: "Không" }, false));
  await sleep(30); sign(w, d);
  await w.submitForm();
  check("NV: ký mà chưa tick → chặn", !saved(calls).length);
  d.getElementById("f__commit").checked = true;
  d.getElementById("sign_clear") && d.getElementById("sign_clear").click();
  await w.eval("SignPad.clear()");
  await w.submitForm();
  check("NV: tick mà chưa ký → chặn", !saved(calls).length && /ký tên/.test(d.getElementById("toast").textContent),
    d.getElementById("toast").textContent);

  report(results);
})().catch((e) => { console.error(e); process.exit(2); });
