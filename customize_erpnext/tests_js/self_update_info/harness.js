// Dùng chung cho các *.test.js: dựng trang www/employee-self-update-info thật trong jsdom.
// Bỏ cú pháp Jinja ({% raw %}, {{ csrf_token }}…); script ngoài cùng thư mục trang (form.js) được
// chèn thẳng vào HTML để jsdom chạy, không cần tải qua mạng.
const fs = require("fs");
const path = require("path");

const PAGE_DIR = path.join(__dirname, "..", "..", "www", "employee-self-update-info");

function pageHtml() {
  let html = fs.readFileSync(path.join(PAGE_DIR, "index.html"), "utf8")
    .replace(/\{%\s*(end)?raw\s*%\}/g, "").replace(/\{\{[^}]*\}\}/g, "");
  html = html.replace(/<script src="\/employee-self-update-info\/([\w.-]+)(\?[^"]*)?"><\/script>/g,
    (_m, file) => `<script>${fs.readFileSync(path.join(PAGE_DIR, file), "utf8")}</script>`);
  return html;
}

// Thứ jsdom chưa có — gọi trong beforeParse(w) của mỗi test.
function stubBrowser(w) {
  w.scrollTo = () => {};
  w.Element.prototype.scrollIntoView = function () {};
  w.Element.prototype.setPointerCapture = function () {};
  w.HTMLCanvasElement.prototype.toDataURL = () => "data:image/png;base64,AAAA";
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// In PASS/FAIL từng phép kiểm + dòng tổng "x/y passed" (run.js đọc dòng này); thoát 1 nếu có lỗi.
function report(results) {
  let fail = 0;
  for (const [ok, name, detail] of results) {
    if (!ok) fail++;
    console.log(`${ok ? "PASS" : "FAIL"}  ${name}  ${ok || detail === "" || detail === undefined ? "" : JSON.stringify(detail)}`);
  }
  console.log(`\n${results.length - fail}/${results.length} passed`);
  process.exit(fail ? 1 : 0);
}

module.exports = { pageHtml, stubBrowser, sleep, report };
