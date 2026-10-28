// Web Worker giải mã QR CCCD cho máy quét của form.js (28/10/2026).
// Giải mã ZXing-WASM mất ~150–200ms / lần trên điện thoại tầm trung; chạy trên luồng chính thì hình camera giật
// (đo: luồng chính bị khoá ~420ms mỗi giây). Ở đây giải mã trong luồng riêng, luồng chính chỉ cắt khung ngắm thành
// ImageBitmap (createImageBitmap) rồi chuyển sang (transfer, không chép).
// Tin nhắn: {type:"init", lib, wasm, engine} → {type:"ready", kind} | {type:"error", message}
//           {type:"detect", id, bitmap}       → {type:"result", id, values:[rawValue…], ms}
let detector = null;

self.onmessage = async (ev) => {
  const m = ev.data || {};
  if (m.type === "init") {
    try {
      let kind = "";
      if (m.engine !== "wasm" && "BarcodeDetector" in self) {
        try {
          const formats = await self.BarcodeDetector.getSupportedFormats();
          if (formats.includes("qr_code")) { detector = new self.BarcodeDetector({ formats: ["qr_code"] }); kind = "native"; }
        } catch (e) { /* có API nhưng không dùng được → ZXing */ }
      }
      if (!detector) {
        importScripts(m.lib);
        const lib = self.BarcodeDetectionAPI;
        await lib.prepareZXingModule({
          overrides: { locateFile: (path, prefix) => (path.endsWith(".wasm") ? m.wasm : prefix + path) },
          fireImmediately: true,
        });
        detector = new lib.BarcodeDetector({ formats: ["qr_code"] });
        kind = "wasm";
      }
      self.postMessage({ type: "ready", kind });
    } catch (e) {
      self.postMessage({ type: "error", message: String((e && e.message) || e) });
    }
    return;
  }
  if (m.type === "detect") {
    const t = performance.now();
    let values = [];
    try {
      const found = await detector.detect(m.bitmap);
      values = (found || []).map((r) => r.rawValue || "");
    } catch (e) { /* khung lỗi → rỗng */ }
    try { m.bitmap.close(); } catch (e) { }
    self.postMessage({ type: "result", id: m.id, values, ms: performance.now() - t });
  }
};
