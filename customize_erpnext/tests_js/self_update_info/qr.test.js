// Quét QR CCCD (28/10/2026): BarcodeDetector gốc / ZXing-WASM tự lưu, zoom + lấy nét, ?qrdebug=1, chụp ảnh CCCD.
// Camera, BarcodeDetector và thư viện ZXing đều giả lập — chỉ kiểm logic trang (form.js).
const { JSDOM } = require("jsdom");
const { pageHtml, stubBrowser, sleep, report } = require("./harness");

const html = pageHtml();
const results = [];
const check = (name, ok, detail) => results.push([!!ok, name, detail]);

const PAYLOAD = "051089009620|212869262|Nguyễn Văn Thử|04071989|Nam|Xóm 1, Bình Sơn, Quảng Ngãi|12082021";
const F = (fieldname, label, fieldtype = "Data") => ({ fieldname, label, fieldtype, widget: "Auto", width: "Full",
  required: false, read_only: false, auto_fill: true, validation: "", min_length: 0, max_length: 0 });
const config = {
  sections: [{ label: "CCCD", fields: [
    F("custom_id_card_no", "Số CCCD"), F("custom_id_card_date_of_issue", "Ngày cấp", "Date"),
    F("custom_id_card__date_of_expired", "Ngày hết hạn", "Date"), F("custom_id_card_cmnd_no", "Số CMND"),
    F("date_of_birth", "Ngày sinh", "Date"),
  ] }],
  allow_local_draft: false, lock_after_submit: false, save_file_type: "PDF", commitment_html: "Cam kết", documents: [],
};

// opts: native (BarcodeDetector gốc), lib ("preloaded" | "script" | "none"), caps, query, hits (số lần detect rỗng trước khi ra mã)
async function boot(opts = {}) {
  const env = { applied: [], detectCalls: 0, sources: [], prepared: null, stopped: false, getUserMedia: 0 };
  const hits = opts.hits ?? 2;
  const detect = async (source) => {
    env.detectCalls++;
    env.sources.push(source && source.tagName);
    return env.detectCalls > hits ? [{ rawValue: PAYLOAD, format: "qr_code" }] : [];
  };
  const dom = new JSDOM(html, {
    runScripts: "dangerously", pretendToBeVisual: true,
    url: "https://erp.test/employee-self-update-info" + (opts.query || ""),
    beforeParse(w) {
      stubBrowser(w);
      w.csrf_token = "x";
      w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
      w.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, { get: () => () => {} });
      w.HTMLMediaElement.prototype.play = () => Promise.resolve();
      Object.defineProperty(w.HTMLVideoElement.prototype, "videoWidth", { get: () => 1920 });
      Object.defineProperty(w.HTMLVideoElement.prototype, "videoHeight", { get: () => 1080 });
      const track = {
        stop() { env.stopped = true; },
        getCapabilities: () => opts.caps || {},
        applyConstraints: async (c) => { env.applied.push(c); },
      };
      const stream = { getVideoTracks: () => [track], getTracks: () => [track] };
      Object.defineProperty(w.navigator, "mediaDevices", { value: { getUserMedia: async () => { env.getUserMedia++; return stream; } } });
      if (opts.native) {
        w.BarcodeDetector = class { static async getSupportedFormats() { return ["qr_code", "ean_13"]; } detect(s) { return detect(s); } };
      }
      const lib = {
        prepareZXingModule: async (o) => { env.prepared = o; },
        BarcodeDetector: class { constructor(o) { env.libFormats = o.formats; } detect(s) { return detect(s); } },
      };
      if (opts.lib === "preloaded") w.BarcodeDetectionAPI = lib;
      if (opts.worker) {   // Web Worker giả: init → ready / error; detect → giống detect() ở trên
        env.workerUrls = []; env.transfers = [];
        w.OffscreenCanvas = class {};
        w.createImageBitmap = async (src, sx, sy, sw, sh) => ({ tagName: "BITMAP", sw, sh, close() {} });
        w.Worker = class {
          constructor(url) { env.workerUrls.push(url); }
          postMessage(msg, transfer) {
            setTimeout(async () => {
              if (msg.type === "init") {
                env.workerInit = msg;
                this.onmessage({ data: opts.worker === "fail" ? { type: "error", message: "boom" } : { type: "ready", kind: "wasm" } });
              } else if (msg.type === "detect") {
                env.transfers.push(transfer && transfer[0] === msg.bitmap);
                const found = await detect(msg.bitmap);
                this.onmessage({ data: { type: "result", id: msg.id, values: found.map(r => r.rawValue), ms: 5 } });
              }
            }, 5);
          }
          terminate() { env.workerTerminated = true; }
        };
      }
      env.lib = lib;
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
  await sleep(100);
  return { w, d: w.document, env };
}
const val = (d, fn) => (d.getElementById("f_" + fn) || {}).value;
// Chờ điều kiện thay vì ngủ cố định (chạy cả bộ test thì máy bận, thời gian dao động).
async function waitFor(cond, ms = 5000) {
  const t = Date.now();
  while (!cond() && Date.now() - t < ms) await sleep(25);
  return cond();
}
const filled = (d) => val(d, "custom_id_card_no") === "051089009620" && val(d, "custom_id_card_cmnd_no") === "212869262"
  && val(d, "custom_id_card_date_of_issue") === "2021-08-12" && val(d, "date_of_birth") === "1989-07-04";

(async () => {
  // 1. Trình duyệt có BarcodeDetector gốc (Chrome Android) + camera có zoom / lấy nét / đèn
  let { w, d, env } = await boot({ native: true, caps: { zoom: { min: 1, max: 8 }, focusMode: ["manual", "continuous"], torch: true } });
  check("có nút Quét; nút Chụp / chọn ảnh CCCD đang TẠM ẨN (comment)", d.querySelector(".qr-scan-btn")
    && !d.querySelector(".qr-scan-btn.alt") && !d.getElementById("cccd_photo_input")
    && !/Quét khó/.test(d.getElementById("fg_custom_id_card_no").textContent));
  w.eval("openQRScanner()");
  await waitFor(() => filled(d) && d.getElementById("qr_overlay").style.display === "none");
  check("native: không tải thư viện ZXing", !d.querySelector('script[src*="barcode-detector"]') && !env.prepared);
  check("native: đọc được mã → điền CCCD, CMND, ngày cấp, ngày sinh", filled(d),
    ["custom_id_card_no", "custom_id_card_cmnd_no", "custom_id_card_date_of_issue", "date_of_birth"].map(f => val(d, f)));
  check("tự tính ngày hết hạn từ ngày sinh + ngày cấp", val(d, "custom_id_card__date_of_expired") === "2029-07-04",
    val(d, "custom_id_card__date_of_expired"));
  check("camera: zoom 2x + lấy nét liên tục", env.applied.some(c => c.advanced && c.advanced[0].zoom === 2
    && c.advanced[0].focusMode === "continuous"), env.applied);
  check("có zoom → nhắc cách 15–20 cm", /15–20 cm/.test(d.getElementById("qr_hint").textContent), d.getElementById("qr_hint").textContent);
  check("giải mã vùng khung ngắm (canvas) là chính", env.sources[0] === "CANVAS", env.sources);
  check("đọc xong → tắt camera, đóng máy quét", env.stopped && d.getElementById("qr_overlay").style.display === "none");
  check("không có ?qrdebug → ẩn dòng chẩn đoán", d.getElementById("qr_debug").classList.contains("hidden"));

  // 2. Không có BarcodeDetector gốc (trình duyệt trong Zalo) — thư viện ZXing tải từ app
  ({ w, d, env } = await boot({ lib: "script", caps: {}, query: "?qrdebug=1", hits: 5 }));
  w.eval("openQRScanner()");
  await sleep(50);
  const s = d.querySelector('script[src*="barcode-detector"]');
  check("wasm: chèn script thư viện tự lưu (không CDN)", s && s.getAttribute("src") === "/assets/customize_erpnext/js/lib/zxing/barcode-detector-3.2.2-ponyfill.js",
    s && s.getAttribute("src"));
  check("đang tải → báo 'Đang tải bộ quét…'", /Đang tải bộ quét/.test(d.getElementById("qr_status").textContent));
  w.BarcodeDetectionAPI = env.lib;            // giả lập script đã chạy xong
  s.dispatchEvent(new w.Event("load"));
  await sleep(400);
  check("wasm: .wasm trỏ về file trong app", env.prepared && env.prepared.fireImmediately === true
    && env.prepared.overrides.locateFile("zxing_reader.wasm", "https://cdn/") === "/assets/customize_erpnext/js/lib/zxing/zxing_reader-3.1.3.wasm"
    && env.prepared.overrides.locateFile("x.js", "https://cdn/") === "https://cdn/x.js");
  check("wasm: chỉ quét QR", JSON.stringify(env.libFormats) === '["qr_code"]', env.libFormats);
  check("không zoom → không ép constraints, nhắc cách 10–15 cm", !env.applied.length
    && /10–15 cm/.test(d.getElementById("qr_hint").textContent), env.applied);
  const dbg = d.getElementById("qr_debug");
  check("?qrdebug=1 → dòng chẩn đoán: engine wasm, độ phân giải", !dbg.classList.contains("hidden")
    && /^wasm · 1920×1080 · zoom — · lấy nét — · đèn —/.test(dbg.textContent), dbg.textContent);
  check("~10 lần / giây (không chạy mỗi khung hình)", env.detectCalls >= 3 && env.detectCalls <= 6, env.detectCalls);
  check("cứ 4 lần có 1 lần thử cả khung (video)", env.sources.includes("VIDEO") && env.sources.filter(x => x === "CANVAS").length >= 3, env.sources);
  check("wasm: đọc được mã → điền field", await waitFor(() => filled(d)));

  // 3. Tải thư viện lỗi (mạng chặn) → báo nhập tay, không mở camera; mở lại thì thử tải lại
  ({ w, d, env } = await boot({ lib: "script" }));
  w.eval("openQRScanner()");
  await sleep(30);
  d.querySelector('script[src*="barcode-detector"]').dispatchEvent(new w.Event("error"));
  await sleep(50);
  check("thư viện lỗi → 'Không tải được bộ quét… nhập tay'", /Không tải được bộ quét.*nhập tay/.test(d.getElementById("qr_status").textContent)
    && env.getUserMedia === 0, d.getElementById("qr_status").textContent);
  w.eval("closeQRScanner(); openQRScanner()");
  await sleep(30);
  check("mở lại → thử tải thư viện lần nữa", d.querySelectorAll('script[src*="barcode-detector"]').length === 2);

  // 4. Đóng máy quét khi đang tải → camera mở xong thì tắt ngay, không quét
  ({ w, d, env } = await boot({ native: true, hits: 0 }));
  w.eval("openQRScanner(); closeQRScanner()");
  await sleep(300);
  check("đóng trong lúc tải → tắt camera, không điền gì", env.stopped && !filled(d) && env.detectCalls === 0, env);

  // 5. Chụp / chọn ảnh CCCD (nút đang ẩn, code giữ để bật lại): cả ảnh không ra → thử vùng cắt → điền field
  ({ w, d, env } = await boot({ lib: "preloaded", hits: 1 }));
  w.eval("_loadImage = async () => ({ naturalWidth: 4000, naturalHeight: 3000 })");
  await w.eval("onCccdPhoto({ target: { files: [{}], value: 'x' } })");
  await sleep(50);
  check("ảnh: cả ảnh rồi vùng cắt (canvas) → điền field", filled(d) && env.detectCalls === 2 && env.sources[1] === "CANVAS", env.sources);
  ({ w, d, env } = await boot({ lib: "preloaded", hits: 99 }));
  w.eval("_loadImage = async () => ({ naturalWidth: 4000, naturalHeight: 3000 })");
  await w.eval("onCccdPhoto({ target: { files: [{}], value: 'x' } })");
  await sleep(50);
  check("ảnh không có mã → nhắc chụp lại, thử đủ 12 vùng", /Không đọc được QR từ ảnh/.test(d.getElementById("toast").textContent)
    && env.detectCalls === 12 && !filled(d), [env.detectCalls, d.getElementById("toast").textContent]);

  // 6. Web Worker (28/10/2026): giải mã ngoài luồng chính — trình duyệt có Worker + createImageBitmap + OffscreenCanvas
  ({ w, d, env } = await boot({ worker: "ok", query: "?qrdebug=1", hits: 4 }));
  w.eval("openQRScanner()");
  check("worker: điền đúng field", await waitFor(() => filled(d)));
  check("worker: URL qr_worker.js cùng thư mục trang", env.workerUrls.length === 1 && env.workerUrls[0] === "/employee-self-update-info/qr_worker.js",
    env.workerUrls);
  check("worker: init gửi đường dẫn thư viện + wasm tự lưu", env.workerInit && env.workerInit.lib.endsWith("barcode-detector-3.2.2-ponyfill.js")
    && env.workerInit.wasm.endsWith("zxing_reader-3.1.3.wasm") && env.workerInit.engine === "auto", env.workerInit);
  check("worker: luồng chính KHÔNG tải thư viện ZXing", !d.querySelector('script[src*="barcode-detector"]') && !env.prepared);
  check("worker: gửi ImageBitmap (transfer, không chép)", env.sources.every(x => x === "BITMAP") && env.transfers.every(Boolean)
    && env.transfers.length >= 3, [env.sources, env.transfers]);
  ({ w, d, env } = await boot({ worker: "ok", query: "?qrdebug=1", hits: 99 }));
  w.eval("openQRScanner()");
  await waitFor(() => /lần\/s/.test(d.getElementById("qr_debug").textContent));
  check("?qrdebug=1 → engine 'wasm·worker'", /^wasm·worker · 1920×1080/.test(d.getElementById("qr_debug").textContent), d.getElementById("qr_debug").textContent);
  w.eval("closeQRScanner()");
  ({ w, d, env } = await boot({ worker: "fail", lib: "preloaded", hits: 2 }));
  w.eval("openQRScanner()");
  check("worker lỗi → quay về giải mã trên luồng chính, vẫn điền được", await waitFor(() => filled(d)) && env.workerTerminated
    && env.prepared, [env.workerTerminated, !!env.prepared]);
  ({ w, d, env } = await boot({ worker: "ok", lib: "preloaded", query: "?qrengine=wasm", hits: 1 }));
  w.eval("delete window.OffscreenCanvas; openQRScanner()");
  check("thiếu OffscreenCanvas (iOS cũ) → không tạo worker, dùng luồng chính", await waitFor(() => filled(d)) && env.workerUrls.length === 0);

  report(results);
})().catch(e => { console.error(e); process.exit(1); });
