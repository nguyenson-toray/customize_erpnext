// Đo độ "lag" của máy quét QR trên trang THẬT (nginx), camera giả (y4m), CPU hãm như điện thoại.
import fs from "node:fs";
// node perf.mjs <video.y4m> <cpu_throttle> <seconds> [query]
import puppeteer from "puppeteer-core";

const [video, throttle = "4", seconds = "6", query = "?qrengine=wasm&qrdebug=1"] = process.argv.slice(2);
const F = (fieldname, label, fieldtype = "Data") => ({ fieldname, label, fieldtype, widget: "Auto", width: "Full",
  required: false, read_only: false, auto_fill: true, validation: "", min_length: 0, max_length: 0 });
const MOCK = {
  get_field_config: { sections: [{ label: "CCCD", fields: [F("custom_id_card_no", "Số CCCD"),
    F("custom_id_card_date_of_issue", "Ngày cấp", "Date"), F("custom_id_card_cmnd_no", "Số CMND"), F("date_of_birth", "Ngày sinh", "Date")] }],
    allow_local_draft: false, lock_after_submit: false, save_file_type: "PDF", commitment_html: "x", documents: [], start_notes_html: "" },
  get_eligible_employees: [{ employee_id: "TIQN-1", display_name: "A", submitted: false }],
  get_form_data: { original: {}, values: {}, has_existing: false, status: null, employee_name: "A", is_hr: true, documents: [] },
};

const browser = await puppeteer.launch({
  executablePath: "/home/frappe/frappe-bench/chromium/chrome-linux/headless_shell",
  headless: "shell",
  args: ["--no-sandbox", "--ignore-certificate-errors", "--host-resolver-rules=MAP erp.tiqn.local 127.0.0.1",
    "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", `--use-file-for-fake-video-capture=${video}`],
});
const page = await browser.newPage();
await page.setViewport({ width: 390, height: 800, deviceScaleFactor: 2, isMobile: true });
await page.setRequestInterception(true);
const DRAFT = process.env.DRAFT;   // thư mục bản nháp: thay form.js / qr_worker.js của trang thật
page.on("request", (req) => {
  const d = DRAFT && req.url().match(/\/employee-self-update-info\/(form\.js|qr_worker\.js)/);
  if (d) return req.respond({ status: 200, contentType: "application/javascript", body: fs.readFileSync(DRAFT + "/" + d[1], "utf8") });
  const m = req.url().match(/\/api\/method\/[\w.]+\.(\w+)/);
  if (m && MOCK[m[1]] !== undefined) return req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ message: MOCK[m[1]] }) });
  req.continue();
});
page.on("pageerror", (e) => console.log("[pageerror]", String(e).slice(0, 200)));
const cdp = await page.createCDPSession();
await page.goto("https://erp.tiqn.local:8888/employee-self-update-info" + query, { waitUntil: "networkidle0" });
await page.evaluate(() => { S.config = null; return loadForm("TIQN-1", ""); });
await new Promise((r) => setTimeout(r, 500));
await cdp.send("Emulation.setCPUThrottlingRate", { rate: Number(throttle) });

const res = await page.evaluate(async (secs) => {
  const long = [];
  const po = new PerformanceObserver((l) => l.getEntries().forEach((e) => long.push(e.duration)));
  po.observe({ type: "longtask", buffered: false });
  const t0 = performance.now();
  openQRScanner();
  // chờ bộ quét sẵn sàng (đã tải WASM + camera) rồi mới bắt đầu đo
  while (!/Sẵn sàng|ĐỌC|thành công/.test(document.getElementById("qr_status").textContent) && performance.now() - t0 < 20000)
    await new Promise((r) => setTimeout(r, 50));
  const ready = performance.now() - t0;
  long.length = 0;
  let frames = 0, worst = 0, last = performance.now();
  const tStart = performance.now();
  let filledAt = null;
  await new Promise((resolve) => {
    const tick = (now) => {
      frames++; worst = Math.max(worst, now - last); last = now;
      if (!filledAt && document.getElementById("f_custom_id_card_no").value) filledAt = now - tStart;
      if (now - tStart < secs * 1000) requestAnimationFrame(tick); else resolve();
    };
    requestAnimationFrame(tick);
  });
  po.disconnect();
  const dur = (performance.now() - tStart) / 1000;
  return { ready_ms: Math.round(ready), fps: +(frames / dur).toFixed(1), worst_frame_ms: Math.round(worst),
    longtask_ms_per_s: Math.round(long.reduce((a, b) => a + b, 0) / dur), longtasks: long.length,
    debug: document.getElementById("qr_debug").textContent, filled_ms: filledAt && Math.round(filledAt) };
}, Number(seconds));
console.log(JSON.stringify(res));
await browser.close();
