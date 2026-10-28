// So jsQR (pipeline hiện tại) vs ZXing-WASM trên ảnh của gen.py. node run.mjs [cases_dir]
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const jsQR = require("jsqr");
const { PNG } = require("pngjs");
const { readBarcodes } = await import("zxing-wasm/reader");

if (!globalThis.ImageData) {
  globalThis.ImageData = class ImageData {
    constructor(data, width, height) { this.data = data; this.width = width; this.height = height; this.colorSpace = "srgb"; }
  };
}

const DIR = process.argv[2] || path.join(path.dirname(new URL(import.meta.url).pathname), "cases");

function load(file) {
  const png = PNG.sync.read(fs.readFileSync(file));
  return new ImageData(new Uint8ClampedArray(png.data.buffer, png.data.byteOffset, png.data.length), png.width, png.height);
}

// đúng _boostContrast của form.js
function boost(img) {
  const d = new Uint8ClampedArray(img.data);
  let mn = 255, mx = 0;
  for (let i = 0; i < d.length; i += 4) { const g = (d[i] * 77 + d[i + 1] * 150 + d[i + 2] * 29) >> 8; if (g < mn) mn = g; if (g > mx) mx = g; }
  const range = mx - mn || 1;
  for (let i = 0; i < d.length; i += 4) { const g = Math.round((((d[i] * 77 + d[i + 1] * 150 + d[i + 2] * 29) >> 8) - mn) * 255 / range); d[i] = d[i + 1] = d[i + 2] = g; }
  return new ImageData(d, img.width, img.height);
}

// trường trang thật sự dùng (_parseVnCCCDQR → _fillFromCCCD): CCCD, CMND, ngày sinh, ngày cấp
const key = (t) => { const p = String(t || "").split("|"); return [p[0], p[1], p[3], p[6]].join("|"); };

const T = { jsqr: 0, zx: 0 }, N = { jsqr: 0, zx: 0 };
function jsqrRead(img) {
  const t = performance.now();
  const b = boost(img);
  const c = jsQR(b.data, b.width, b.height, { inversionAttempts: "attemptBoth" });
  T.jsqr += performance.now() - t; N.jsqr++;
  return c ? c.data : null;
}
async function zxRead(img) {
  const t = performance.now();
  const r = await readBarcodes(img, { formats: ["QRCode"], tryHarder: true, maxNumberOfSymbols: 1 });
  T.zx += performance.now() - t; N.zx++;
  return r.length ? r[0].text : null;
}

const rows = [];
for (const id of fs.readdirSync(DIR).sort()) {
  const d = path.join(DIR, id);
  const meta = JSON.parse(fs.readFileSync(path.join(d, "meta.json"), "utf8"));
  const want = key(meta.payload);
  const crops = [0, 1, 2].map((k) => load(path.join(d, `a${k}.png`)));
  const roi = load(path.join(d, "roi.png"));
  const ok = (t) => t !== null && key(t) === want;
  let A_jsqr = false, A_zx = false;
  for (const c of crops) { if (!A_jsqr && ok(jsqrRead(c))) A_jsqr = true; }
  for (const c of crops) { if (!A_zx && ok(await zxRead(c))) A_zx = true; }
  const B_jsqr = ok(jsqrRead(roi));
  const B_zx = ok(await zxRead(roi));
  rows.push({ ...meta, payload: undefined, A_jsqr, A_zx, B_jsqr, B_zx });
}

const pct = (arr, k) => arr.length ? Math.round(100 * arr.filter((r) => r[k]).length / arr.length) : 0;
const COLS = ["A_jsqr", "A_zx", "B_jsqr", "B_zx"];
const line = (label, arr) => console.log(label.padEnd(26), String(arr.length).padStart(4), ...COLS.map((k) => (pct(arr, k) + "%").padStart(8)));
console.log("nhóm".padEnd(26), "  n ", ...COLS.map((c) => c.padStart(8)));
line("TẤT CẢ", rows);
for (const [field, vals] of [["module_px", [1.5, 2, 2.5, 3, 4]], ["blur", [0, 0.8, 1.5]], ["glare", [false, true]], ["tilt", [0, 15]], ["ecc", ["L", "M"]]]) {
  for (const v of vals) line(`${field}=${v}`, rows.filter((r) => r[field] === v));
}
console.log(`\nthời gian TB / lần giải mã (máy chủ, điện thoại chậm hơn ~3–6x): jsQR+tăng tương phản ${(T.jsqr / N.jsqr).toFixed(1)}ms · ZXing ${(T.zx / N.zx).toFixed(1)}ms`);
fs.writeFileSync(path.join(path.dirname(DIR), "results.json"), JSON.stringify(rows, null, 1));
