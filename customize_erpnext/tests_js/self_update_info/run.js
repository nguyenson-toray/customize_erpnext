// Chạy mọi *.test.js trong thư mục này, in tổng; exit 1 nếu có file lỗi.
//   cd apps/customize_erpnext/customize_erpnext/tests_js/self_update_info && npm install && node run.js
const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

let pass = 0, total = 0, failed = [];
for (const f of fs.readdirSync(__dirname).filter((x) => x.endsWith(".test.js")).sort()) {
  let out;
  try {
    out = execFileSync(process.execPath, [path.join(__dirname, f)], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
  } catch (e) {
    out = (e.stdout || "") + (e.stderr || "");
    failed.push(f);
  }
  const m = out.match(/(\d+)\/(\d+) passed/);
  if (m) { pass += +m[1]; total += +m[2]; } else if (!failed.includes(f)) failed.push(f);
  out.split("\n").filter((l) => l.startsWith("FAIL") || /Error/.test(l)).forEach((l) => console.log(`  ${f}: ${l}`));
  console.log(`${f}: ${m ? m[0] : "no summary"}`);
}
console.log(`\nTOTAL ${pass}/${total} passed${failed.length ? " — FAILED: " + failed.join(", ") : ""}`);
process.exit(failed.length ? 1 : 0);
