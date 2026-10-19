// Chạy thử Page biometric-sync trên DOM giả (jsdom) — bắt lỗi khởi tạo / chuyển tab.
const fs = require("fs");
const { JSDOM } = require(process.argv[3]);
const src = fs.readFileSync(process.argv[2], "utf8");
const dom = new JSDOM(`<!doctype html><body><div id="page"></div></body>`, { runScripts: "outside-only", url: "https://erp.tiqn.local/desk" });
const w = dom.window;
const errors = [];
w.addEventListener("error", e => errors.push("error: " + e.message));
w.console.error = (...a) => errors.push("console.error: " + a.join(" "));
const calls = [];
w.fetch = async (url, opts) => {
  calls.push((opts && opts.method) || "GET " + url.split("?")[0].replace("/api/method/", ""));
  const m = url.split("?")[0].replace("/api/method/", "");
  let message = {};
  if (m.endsWith("get_log_files")) message = { status: "success", files: ["logs.log"] };
  else if (m.endsWith("get_log_content")) message = { status: "success", content: "2026-10-17 INFO ok\n2026-10-17 ERROR boom", lines: ["INFO ok", "ERROR boom"] };
  else if (m.includes("machines")) message = [{ name: "M1", device_name: "M1", ip_address: "10.0.1.50", enable: 1 }];
  return { status: 200, ok: true, json: async () => ({ message }) };
};
w.frappe = {
  provide: () => {}, pages: { "biometric-sync": {} }, csrf_token: "x",
  user: { has_role: () => true },
  utils: { escape_html: s => String(s) },
  msgprint: o => calls.push("msgprint"), confirm: (m, y, n) => { calls.push("confirm"); y(); },
};
w.bsync = {}; w.__ = s => s;
w.eval(src.replace("const BSYNC_HTML", "window.BSYNC_HTML"));
const root = w.document.getElementById("page");
root.innerHTML = w.BSYNC_HTML;
const bs = root.querySelector(".bsync");
w.bsync.setup(bs);
const tabs = [...bs.querySelectorAll(".tab-btn")].map(b => b.dataset.tab);
setTimeout(() => {
  for (const t of tabs) { try { w.bsync.switchTab(t); } catch (e) { errors.push(`switchTab(${t}): ${e.message}`); } }
  const active = bs.querySelector(".tab-panel.active");
  setTimeout(() => {
    console.log("tabs:", tabs.length, "| last active:", active && active.id, "| exported fns:", Object.keys(w.bsync).length);
    console.log("api calls:", [...new Set(calls)].join(", "));
    console.log(errors.length ? "ERRORS:\n  " + errors.join("\n  ") : "no JS errors");
  }, 300);
}, 300);

// ── luồng hộp thoại: thiếu ngày -> msgprint; No -> không gửi; Yes -> POST ──
setTimeout(async () => {
  const doc = w.document;
  doc.getElementById("rsMongoFrom").value = ""; doc.getElementById("rsMongoTo").value = "";
  calls.length = 0; await w.bsync.rsRunMongoResync(); const a = [...calls];
  doc.getElementById("rsMongoFrom").value = "2026-10-01"; doc.getElementById("rsMongoTo").value = "2026-10-02";
  calls.length = 0; w.frappe.confirm = (m, y, n) => { calls.push("confirm"); n(); };
  await w.bsync.rsRunMongoResync(); await new Promise(r => setTimeout(r, 100)); const b = [...calls];
  calls.length = 0; w.frappe.confirm = (m, y, n) => { calls.push("confirm"); y(); };
  await w.bsync.rsRunMongoResync(); await new Promise(r => setTimeout(r, 100));
  console.log("missing dates ->", a.join(",") || "-", "| No ->", b.join(",") || "-", "| Yes ->", calls.join(","));
  console.log(errors.length ? "ERRORS: " + errors.join(" | ") : "dialog flow: no JS errors");
}, 900);
