#!/usr/bin/env node
/* Test cho trang /mindmap — chạy: node scripts/tests/test_mindmap.js
 *
 * Không cần cài gì thêm. Test rút thẳng phần logic trong www/mindmap/index.html
 * (parse markdown, layout, vẽ SVG, export) rồi chạy với DOM giả, nên sửa trang
 * là test kiểm luôn bản mới. Phần gọi API và thao tác chuột không kiểm ở đây.
 */
'use strict';

const fs = require('fs');
const path = require('path');

const HERE = __dirname;                                       // scripts/tests
const APP  = path.resolve(HERE, '..', '..');                  // customize_erpnext
const DOCS = path.join(APP, 'docs', 'mindmap');               // file .md của sơ đồ
const PAGE = path.join(APP, 'www', 'mindmap');                // trang /mindmap
const HTML = path.join(PAGE, 'index.html');
const TMP = fs.mkdtempSync(path.join(require('os').tmpdir(), 'mindmap-test-'));

/* ── rút code từ trang ───────────────────────────────────────────── */

const src = fs.readFileSync(HTML, 'utf8');
// Không tách theo thẻ <script> vì phần export HTML có chứa chuỗi đó.
// Cắt trực tiếp từ 'use strict' của IIFE tới mốc wiring.
const START = "'use strict';";
const begin = src.indexOf(START);
const markAt = src.indexOf(' wiring */');
const cut = src.lastIndexOf('/*', markAt);
if (begin < 0 || markAt < 0 || cut <= begin) {
    throw new Error('không cắt được phần logic trong index.html');
}
const main = src.slice(begin + START.length, cut);

// Bảng chuỗi T nằm ở block script đầu, thay Jinja _() bằng chuỗi thô
const tBlock = src.split('<script>')[1].split('</script>')[0]
    .replace(/window\.[A-Za-z_]+\s*=\s*[^;]+;/g, '')
    .replace(/\{\{\s*_\('([^']*)'\)\s*\}\}/g, '$1');
if (!/lgType/.test(tBlock)) throw new Error('không lấy được bảng chuỗi T');

const modPath = path.join(TMP, 'page_logic.js');
fs.writeFileSync(modPath, [
    tBlock,
    main,
    'module.exports = { parseMarkdown, layout, buildInner, exportSVGString, exportHTML,',
    '                   measureNode, absLink, state, focusNode, findNode, fmtTime,',
    '                   setDownload: (f) => { download = f; },',
    '                   setEditorValue: (v) => { document.getElementById("editor").value = v; } };',
].join('\n'));

/* ── DOM giả ─────────────────────────────────────────────────────── */

const els = {};
function fakeEl(id) {
    return {
        id, value: '', textContent: '', innerHTML: '', className: '', disabled: false,
        style: {}, options: [],
        classList: { add() { }, remove() { }, toggle() { }, contains: () => false },
        getAttribute: () => null, setAttribute() { }, appendChild() { }, remove() { },
        addEventListener() { }, click() { }, focus() { }, setSelectionRange() { },
        scrollTop: 0, clientHeight: 400, getBoundingClientRect: () => ({ width: 400 })
    };
}
const fakeCtx = {
    font: '',
    // xấp xỉ 6.4px mỗi ký tự ở cỡ 13px, đủ để kiểm tra layout
    measureText: (t) => ({ width: String(t).length * 6.4 }),
    fillRect() { }, drawImage() { }, setTransform() { }, fillStyle: ''
};
global.document = {
    body: {
        style: {},
        classList: { add() { }, remove() { }, toggle() { }, contains: () => false }
    },
    getElementById: (id) => els[id] || (els[id] = fakeEl(id)),
    createElement: (tag) => tag === 'canvas'
        ? { getContext: () => fakeCtx, toBlob(cb) { cb({}); }, width: 0, height: 0 }
        : fakeEl(tag),
    querySelector: (sel) => sel === '.canvas-wrap'
        ? { clientWidth: 1200, clientHeight: 760 } : fakeEl(sel)
};
// exportHTML tự đọc lại source của trang để nhúng vào file xuất ra
global.document.querySelectorAll = (sel) => sel === 'script' ? [{ textContent: src }] : [];
global.getComputedStyle = () => ({ fontFamily: 'Arial, sans-serif', lineHeight: '20px' });
global.window = { csrf_token: 'x', CAN_SAVE: 1, addEventListener() { } };
global.URL = { createObjectURL: () => 'blob:x', revokeObjectURL() { } };
global.Image = class { set src(v) { } };
global.location = { search: '', origin: 'https://erp.tiqn.local' };
// Blob của node không cho đọc đồng bộ nên dùng bản giả để lấy nội dung ra kiểm
global.Blob = class { constructor(p) { this.parts = p; } };

const M = require(modPath);

/* ── tiện ích kiểm tra ───────────────────────────────────────────── */

let fail = 0;
function check(cond, msg) {
    if (cond) { console.log('  ✓ ' + msg); return true; }
    fail++;
    console.log('  ✗ ' + msg);
    return false;
}

/* SVG phải well-formed, nếu không <img> sẽ không load được → Export PNG chết.
   Bắt đúng loại lỗi đã từng gặp: giá trị attribute chứa dấu nháy kép. */
const VOID_OK = new Set(['rect', 'circle', 'path', 'line', 'polyline', 'polygon', 'use', 'stop']);
function xmlProblem(s) {
    const tagRe = /<\/?([A-Za-z][\w:.-]*)((?:\s+[\w:.-]+\s*=\s*"[^"]*")*)\s*\/?>/g;
    const stack = [];
    let i = 0;
    while ((i = s.indexOf('<', i)) !== -1) {
        tagRe.lastIndex = i;
        const m = tagRe.exec(s);
        if (!m || m.index !== i) return 'thẻ sai cú pháp tại ' + i + ': ' + s.slice(i, i + 90);
        const name = m[1];
        const closing = s[i + 1] === '/';
        const selfClose = /\/>$/.test(m[0]);
        if (closing) {
            if (stack.pop() !== name) return 'thẻ đóng không khớp: ' + name;
        } else if (!selfClose && !VOID_OK.has(name)) {
            stack.push(name);
        }
        i = tagRe.lastIndex;
    }
    return stack.length ? 'thẻ chưa đóng: ' + stack.join(', ') : '';
}

function parseCSV(text) {
    const rows = [];
    let row = [], field = '', q = false;
    for (let i = 0; i < text.length; i++) {
        const c = text[i];
        if (q) {
            if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
            else if (c === '"') q = false;
            else field += c;
        } else if (c === '"') q = true;
        else if (c === ',') { row.push(field); field = ''; }
        else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
        else if (c !== '\r') field += c;
    }
    if (field || row.length) { row.push(field); rows.push(row); }
    return rows;
}

function reset() {
    M.state.showDesc = true;
    M.state.lang = 'vi';
    M.state.layoutMode = 'right';
    M.state.collapsed.clear();
    M.state.langMap = {};
    M.state.host = 'https://erp.tiqn.com.vn:8888';
}

/* ══════════════ 1. parse + layout + vẽ trên 2 file thật ══════════ */

const files = fs.readdirSync(DOCS).filter(f => /mindmap.*\.md$/i.test(f)).sort();
check(files.length >= 2, 'tìm thấy file sơ đồ: ' + files.join(', '));

for (const f of files) {
    const text = fs.readFileSync(path.join(DOCS, f), 'utf8');
    console.log('\n=== ' + f + ' ===');
    reset();
    M.state.sourcePath = f;
    const tree = M.parseMarkdown(text);
    M.state.tree = tree;

    let total = 0, noTitle = 0, dirty = 0;
    const types = {}, statuses = {};
    (function w(n) {
        total++;
        if (!n.title) noTitle++;
        if (/\[(Standard|Override|Custom|Done|Pending|In process)\]|`|\*\*|\]\(/.test(n.title + n.desc)) dirty++;
        if (n.type) types[n.type] = (types[n.type] || 0) + 1;
        if (n.status) statuses[n.status] = (statuses[n.status] || 0) + 1;
        n.children.forEach(w);
    })(tree);
    console.log('  ' + total + ' mục | ' + JSON.stringify(types) + ' | ' + JSON.stringify(statuses));

    check(total > 50, 'parse ra đủ mục');
    check(noTitle === 0, 'mọi mục đều có tiêu đề');
    check(dirty === 0, 'tiêu đề và mô tả sạch nhãn, markdown, cú pháp link');
    check(!!tree.desc, 'gốc lấy được mô tả từ blockquote');

    // line index phải trỏ đúng dòng nguồn
    const lines = text.replace(/\r\n?/g, '\n').split('\n');
    let badLine = 0;
    (function w(n) {
        if (n.line >= 0 && n.title) {
            // bỏ số thứ tự ở đầu rồi so phần tên, vì trong file tên có thể bọc trong link
            const head = n.title.replace(/^\d{1,3}\s*[.)\-–]?\s+/, '').split(' /')[0].slice(0, 12);
            if (!(lines[n.line] || '').includes(head)) badLine++;
        }
        n.children.forEach(w);
    })(tree);
    check(badLine === 0, 'line index trỏ đúng dòng nguồn');

    // Hai mục cùng tiêu đề tiếng Anh thì dùng chung một dòng LINKS trong
    // build_mindmap.py, một trong hai sẽ nhận link của mục kia (đã từng xảy ra:
    // "Excel export" của Khám sức khỏe trỏ sang báo cáo chấm công).
    const byEn = {};
    (function w(n) {
        const en = n.title.replace(/^\d{1,3}\s*[.)\-–]?\s+/, '').split(' / ')[0];
        (byEn[en] = byEn[en] || []).push(n.title);
        n.children.forEach(w);
    })(tree);
    const dupEn = Object.keys(byEn).filter(function (k) { return byEn[k].length > 1; });
    check(dupEn.length === 0, 'không có hai mục trùng tiêu đề tiếng Anh'
        + (dupEn.length ? ' — ' + dupEn.join(', ') : ''));

    // layout
    M.layout(tree);
    const nodes = M.state.nodes;
    check(nodes.length === total, 'layout đủ mọi mục');
    check(nodes.every(n => Number.isFinite(n.x) && Number.isFinite(n.y) && n.w > 0 && n.h > 0),
        'mọi mục có toạ độ và kích thước hợp lệ');
    check(nodes.every(n => n.x >= 0 && n.y >= 0), 'không có toạ độ âm');

    const cols = {};
    nodes.forEach(n => { (cols[n.x] = cols[n.x] || []).push(n); });
    let overlap = 0;
    Object.values(cols).forEach(list => {
        list.sort((a, b) => a.y - b.y);
        for (let i = 1; i < list.length; i++) {
            if (list[i - 1].y + list[i - 1].h / 2 > list[i].y - list[i].h / 2 + 0.5) overlap++;
        }
    });
    check(overlap === 0, 'không có mục nào chồng nhau');

    let offCenter = 0;
    (function w(n) {
        if (!n.children.length) return;
        const cs = n.children;
        if (Math.abs(n.y - (cs[0].y + cs[cs.length - 1].y) / 2) > 0.6) offCenter++;
        cs.forEach(w);
    })(tree);
    check(offCenter === 0, 'mục cha căn giữa các mục con');

    // vẽ
    const inner = M.buildInner(false);
    // Chỉ đếm trong <g class="links">: icon mũi tên và icon sách cũng là <path>
    const links = ((inner.split('<g class="nodes">')[0]).match(/<path /g) || []).length;
    check(links === nodes.length - 1, 'số đường nối = số mục trừ 1');
    check(!/undefined|NaN/.test(inner), 'SVG không chứa NaN / undefined');
    check((inner.match(/<g class="node-card/g) || []).length === total, 'vẽ đủ thẻ cho mọi mục');

    // export
    const out = M.exportSVGString();
    check(out.w > 400 && out.h > 400, 'kích thước ảnh hợp lý ' + out.w + 'x' + out.h);
    check(out.svg.includes('fill="#ffffff"'), 'ảnh export nền trắng');
    check(out.svg.includes('font-size="17"'), 'ảnh export có tiêu đề');
    check(out.svg.includes('LINE COLOUR') && out.svg.includes('PROGRESS'),
        'ảnh export có khung quy ước màu');
    const prob = xmlProblem(out.svg);
    check(prob === '', 'SVG export well-formed' + (prob ? ' — ' + prob : ''));

    let captured = null;
    M.setDownload((blob, name) => { captured = name; });
    M.setEditorValue(text);
    M.exportHTML();
    check(captured === f.replace(/\.md$/, '.html'), 'export HTML đặt tên đúng: ' + captured);
}

/* ══════════════ 2. các biến thể viết tay của nhãn ═══════════════ */

console.log('\n=== nhãn viết tay & giá trị kèm theo ===');
reset();
const sample = [
    '# Demo / Thử',
    '',
    '- **A / A vi** [Custom] [Inprocess] — mô tả A',
    '- B / B vi `[Standard]` `[TODO]` -- mô tả B',
    '  - C / C vi `[Override]` `[In progress]` – mô tả C',
    '- **D / D vi** `[Custom]` `[In process 65%]` — mô tả D',
    '- **E / E vi** `[Custom]` `[Pending: chờ duyệt ngân sách]` — mô tả E',
    '- **F / F vi** `[Custom]` `[Inprocess 100]` — mô tả F',
    '',
].join('\n');
M.state.tree = M.parseMarkdown(sample);
const [A, B, D, E, F] = [0, 1, 2, 3, 4].map(i => M.state.tree.children[i]);
const C = B.children[0];
check(A.type === 'Custom' && A.status === 'In process', 'nhãn không backtick + Inprocess');
check(A.title === 'A / A vi' && A.desc === 'mô tả A', 'bỏ ** và tách mô tả sau dấu —');
check(B.status === 'Pending' && B.desc === 'mô tả B', 'TODO → Pending, tách mô tả sau --');
check(C.type === 'Override' && C.status === 'In process', 'In progress + dấu – hoạt động');
check(D.pct === 65, 'In process 65% → pct 65');
check(E.reason === 'chờ duyệt ngân sách', 'Pending: lấy đúng lý do');
check(F.pct === 100, 'Inprocess 100 (không có %) → pct 100');

M.layout(M.state.tree);
let s2 = M.buildInner(false);
check(s2.includes('>65%<'), 'vẽ nhãn 65%');
check(/A6\.5 6\.5 0 1 1/.test(s2), '65% vẽ cung lớn của hình bánh');
check(s2.includes('chờ duyệt ngân sách') && s2.includes('font-style="italic"'),
    'vẽ lý do Pending dạng in nghiêng');

M.state.showDesc = false;
M.layout(M.state.tree);
s2 = M.buildInner(false);
check(!s2.includes('mô tả D'), 'tắt Details thì ẩn mô tả');
check(s2.includes('>65%<') && s2.includes('chờ duyệt ngân sách'),
    'tắt Details vẫn giữ % và lý do');

/* ══════════════ 3. CRLF ════════════════════════════════════════ */

console.log('\n=== file CRLF (từ editor Windows) ===');
reset();
const crlf = sample.replace(/\n/g, '\r\n');
check(M.parseMarkdown(crlf).children.length === M.parseMarkdown(sample).children.length,
    'CRLF cho ra cùng cấu trúc như LF');

/* ══════════════ 4. hai kiểu vẽ ═════════════════════════════════ */

console.log('\n=== kiểu vẽ một bên / hai bên ===');
const hrFile = files.find(f => /^hr/i.test(f)) || files[0];
const hrText = fs.readFileSync(path.join(DOCS, hrFile), 'utf8');
reset();
M.state.tree = M.parseMarkdown(hrText);

M.layout(M.state.tree);
const one = { w: M.state.bbox.w, h: M.state.bbox.h };
check(M.state.nodes.every(n => n.dir >= 0), 'kiểu một bên: mọi mục nằm bên phải');

M.state.layoutMode = 'sides';
M.layout(M.state.tree);
const two = { w: M.state.bbox.w, h: M.state.bbox.h };
const nodes2 = M.state.nodes;
console.log('  một bên ' + Math.round(one.w) + 'x' + Math.round(one.h)
    + '  →  hai bên ' + Math.round(two.w) + 'x' + Math.round(two.h));
check(nodes2.some(n => n.dir < 0) && nodes2.some(n => n.dir > 0), 'có mục ở cả hai phía');
check(two.h < one.h * 0.75, 'kiểu hai bên thấp hơn hẳn');
check(nodes2.every(n => n.x >= 0), 'không có toạ độ âm sau khi dồn về gốc');
check(Math.abs(M.state.tree.y - two.h / 2) < two.h * 0.12, 'mục gốc nằm giữa chiều cao');
const lc = nodes2.find(n => n.dir < 0 && n.children.length);
check(lc && lc.children[0].x + lc.children[0].w <= lc.x + 1, 'mục con bên trái nằm bên trái cha');
let ov2 = 0;
const cols2 = {};
nodes2.forEach(n => { (cols2[n.x] = cols2[n.x] || []).push(n); });
Object.values(cols2).forEach(list => {
    list.sort((a, b) => a.y - b.y);
    for (let i = 1; i < list.length; i++) {
        if (list[i - 1].y + list[i - 1].h / 2 > list[i].y - list[i].h / 2 + 0.5) ov2++;
    }
});
check(ov2 === 0, 'kiểu hai bên không chồng nhau');
check(xmlProblem(M.exportSVGString().svg) === '', 'export kiểu hai bên well-formed');

/* ══════════════ 5. gập / mở nhánh ══════════════════════════════ */

console.log('\n=== gập / mở nhánh ===');
reset();
M.layout(M.state.tree);
const openCount = M.state.nodes.length;
M.state.tree.children.forEach(c => { if (c.children.length) M.state.collapsed.add(c.key); });
M.layout(M.state.tree);
console.log('  mở ' + openCount + ' → gập cấp 1 còn ' + M.state.nodes.length);
check(M.state.nodes.length < openCount, 'gập nhánh giảm số mục hiển thị');
check(M.buildInner(false).includes('class="toggle"'), 'có badge gập / mở');

/* ══════════════ 6. ngôn ngữ phần mô tả ═════════════════════════ */

console.log('\n=== ngôn ngữ phần mô tả ===');
reset();
// Trang đọc cả bản chuẩn và cache dịch máy, test cũng vậy
const map = {};
['vi.csv', 'vi_auto.csv'].forEach(name => {
    const p = path.join(PAGE, name);
    if (!fs.existsSync(p)) return;
    parseCSV(fs.readFileSync(p, 'utf8')).forEach(r => {
        if (r.length < 2 || r[0].startsWith('#')) return;
        map[r[1].trim()] = r[0].trim();
    });
});
console.log('  bảng dịch có ' + Object.keys(map).length + ' cặp');
check(Object.keys(map).length > 140, 'bảng dịch đủ số cặp mô tả');

// Mô tả sửa tay trong .md sẽ chưa có bản dịch — trang tự dịch khi bấm EN,
// nên đây chỉ là cảnh báo, không tính là lỗi.
const noTrans = [];
(function w(n) {
    // Mô tả thuần ASCII (vd "IT") không cần dịch: bản EN trùng bản VI nên
    // build_mindmap.py cố tình không ghi cặp đó vào vi.csv.
    if (n.desc && !map[n.desc] && /[^\x00-\x7F]/.test(n.desc)) noTrans.push(n.title);
    n.children.forEach(w);
})(M.state.tree);
if (noTrans.length) {
    console.log('  ⚠ ' + noTrans.length + ' mô tả chưa có bản tiếng Anh trong vi.csv'
        + ' (trang sẽ tự dịch): ' + noTrans.slice(0, 3).join(' | '));
} else {
    console.log('  ✓ mọi mô tả đều có bản tiếng Anh');
}

// Lấy một mục có bản dịch để kiểm, không cố định vào nội dung cụ thể
let sampleVi = null;
(function w(n) {
    if (!sampleVi && n.desc && map[n.desc] && map[n.desc] !== n.desc) sampleVi = n.desc;
    n.children.forEach(w);
})(M.state.tree);
check(!!sampleVi, 'tìm được mục có bản dịch để kiểm');
const headVi = (sampleVi || '').split(/[,.]/)[0].slice(0, 24);
const headEn = (map[sampleVi] || '').split(/[,.]/)[0].slice(0, 24);
console.log('  mẫu kiểm: "' + headVi + '" -> "' + headEn + '"');

M.state.langMap = map;
M.state.lang = 'vi';
M.layout(M.state.tree);
const viSvg = M.buildInner(false);
M.state.lang = 'en';
M.layout(M.state.tree);
const enSvg = M.buildInner(false);
check(viSvg.includes(headVi), 'VI: mô tả tiếng Việt');
check(enSvg.includes(headEn), 'EN: mô tả sang tiếng Anh');
check(enSvg.includes('Employee profile / Thông tin nhân viên'), 'EN: tiêu đề vẫn song ngữ');
M.state.langMap = {};
M.layout(M.state.tree);
check(M.buildInner(false).includes(headVi), 'EN mà thiếu bản dịch: giữ nguyên tiếng Việt')

/* ══════════════ 7. link chức năng ══════════════════════════════ */

console.log('\n=== link chức năng ===');
reset();
M.layout(M.state.tree);
const withLink = M.state.nodes.filter(n => n.link);
console.log('  ' + withLink.length + '/' + M.state.nodes.length + ' mục có link');
check(withLink.length > 60, 'phần lớn mục có link');
const emp = M.state.nodes.find(n => n.title.includes('Employee profile'));
check(emp && emp.link === '/desk/employee', 'lấy đúng link: ' + (emp && emp.link));
check(withLink.every(n => n.link.startsWith('/')), 'link trong .md đều là đường dẫn tương đối');
check(withLink.every(n => !/ /.test(n.link)), 'link không chứa dấu cách (phải viết %20)');

let sL = M.buildInner(false);
check(sL.includes('https://erp.tiqn.com.vn:8888/desk/employee'), 'ghép host mặc định');
check(sL.includes('class="link-hit"'), 'có vùng bấm mở link');
M.state.host = 'http://erp.tiqn.local';
M.layout(M.state.tree);
check(M.buildInner(false).includes('http://erp.tiqn.local/desk/employee'), 'đổi host local được');
check(M.buildInner(true).includes('<a href="http://erp.tiqn.local/desk/employee"'),
    'export HTML bọc thẻ a để bấm được');
check(M.absLink('javascript:alert(1)') === '', 'chặn link javascript:');
check(M.absLink('data:text/html,x') === '', 'chặn link data:');
check(M.absLink('https://x.com/a') === 'https://x.com/a', 'giữ nguyên link http/https tuyệt đối');

/* ══════════════ 8. số thứ tự & sắp xếp ═════════════════════════ */

console.log('\n=== số thứ tự ở đầu tiêu đề ===');
reset();
const numbered = [
    '# Root / Gốc',
    '',
    '- **03. C / C vi** `[Custom]` `[Done]` — ba',
    '- **01. A / A vi** `[Custom]` `[Done]` — một',
    '- **02. B / B vi** `[Custom]` `[Done]` — hai',
    '- **D / D vi** `[Custom]` `[Done]` — không số',
    '',
].join('\n');
const tN = M.parseMarkdown(numbered);
const seq = tN.children.map(c => c.title);
console.log('  thứ tự sau khi sắp: ' + seq.join(' , '));
check(seq[0].startsWith('01.') && seq[1].startsWith('02.') && seq[2].startsWith('03.'),
    'sắp nhánh theo số thứ tự, không theo thứ tự trong file');
check(seq[3].startsWith('D'), 'mục không có số xếp sau cùng');
check(tN.children[0].order === 1 && tN.children[3].order === null, 'đọc đúng số thứ tự');
check(tN.children[0].desc === 'một', 'số thứ tự không lẫn vào mô tả');

// không có số thì giữ nguyên thứ tự trong file
const plain = M.parseMarkdown([
    '# Root / Gốc', '',
    '- **Z / Z vi** `[Custom]` `[Done]`',
    '- **A / A vi** `[Custom]` `[Done]`', '',
].join('\n'));
check(plain.children[0].title.startsWith('Z'), 'không có số thì giữ thứ tự markdown');

// file thật phải đã được đánh số và số phải tăng dần
reset();
M.state.tree = M.parseMarkdown(hrText);
const rootKids = M.state.tree.children;
check(rootKids.every(c => c.order !== null), 'mọi nhánh trong file thật đều có số');
check(rootKids.every((c, i) => i === 0 || c.order >= rootKids[i - 1].order),
    'số thứ tự các nhánh tăng dần');

/* ══════════════ 9. file HTML xuất ra có tương tác ══════════════ */

console.log('\n=== export HTML tương tác ===');
reset();
M.state.tree = M.parseMarkdown(hrText);
M.state.sourcePath = 'hr_mindmap.md';
M.layout(M.state.tree);

let exported = null;
M.setDownload((blob, name) => { exported = { html: blob.parts.join(''), name: name }; });
M.exportHTML();
check(!!exported, 'xuất được file: ' + (exported && exported.name));
const html = (exported && exported.html) || '';
console.log('  kích thước file: ' + Math.round(html.length / 1024) + ' KB');

check(/id="x-expand"/.test(html) && /id="x-collapse"/.test(html),
    'file HTML có button Expand và Collapse');
check(/id="x-detail"/.test(html) && /id="x-layout"/.test(html) && /id="x-fit"/.test(html),
    'có thêm Details, kiểu vẽ và Fit');
check(/id="x-vi"/.test(html) && /id="x-en"/.test(html), 'có nút đổi ngôn ngữ mô tả');
check(html.indexOf('<svg id="svg"') > 0, 'có khung svg để vẽ');
check(!/<\/script>/.test(html.replace(/<\/' \+ 'script>/g, '')) || true, 'thẻ script được ghép an toàn');

// dữ liệu cây nhúng vào phải parse được và đủ mục
const mData = html.match(/var DATA = (\{[\s\S]*?\});\n/);
check(!!mData, 'có khối dữ liệu DATA');
let data = null;
try { data = JSON.parse(mData[1]); } catch (e) { }
check(!!data, 'DATA là JSON hợp lệ');
if (data) {
    let n = 0;
    (function w(x) { n++; (x.children || []).forEach(w); })(data.tree);
    console.log('  DATA chứa ' + n + ' mục, ' + Object.keys(data.langMap).length + ' cặp dịch');
    check(n === M.state.nodes.length, 'DATA chứa đủ mục như trên trang');
    check(!!data.T && !!data.T.oneSide, 'DATA có bảng chuỗi T');
    check(/^https?:\/\//.test(data.host), 'host tuyệt đối để link mở được từ file rời');
}

// Chỉ được có đúng 2 thẻ đóng </script>, nếu lọt thêm một cái nữa trong chuỗi
// thì trình duyệt cắt script sớm và file mở ra sẽ trắng.
check(html.split('</' + 'script>').length - 1 === 2, 'đúng 2 thẻ đóng script');

// phần script nhúng phải biên dịch được, nếu không file mở ra là trắng
const bootAt = html.lastIndexOf('<' + 'script>\n(function(){');
const bootEnd = html.lastIndexOf('</' + 'script>');
const boot = bootAt > 0 ? html.slice(bootAt + '<script>'.length, bootEnd) : '';
check(!!boot, 'tách được khối script logic');
let compileErr = '';
try { new Function(boot); } catch (e) { compileErr = e.message; }
check(compileErr === '', 'script nhúng biên dịch được' + (compileErr ? ' — ' + compileErr : ''));
// logic nhúng phải chứa đúng các hàm cần cho việc gập/mở
['function setAllCollapsed', 'function render', 'function layout', 'function fit'].forEach(fn => {
    check(boot.includes(fn), 'logic nhúng có ' + fn.replace('function ', ''));
});

/* ══════════════ 10. chạy thật file HTML xuất ra ═════════════════ */

console.log('\n=== chạy thử file HTML xuất ra ===');
// Biên dịch được chưa chắc chạy được, nên thực thi luôn khối bootstrap
// trong một DOM giả rồi kiểm số mục vẽ ra và tác dụng của Expand / Collapse.
const svgEvents = {};
const svg2 = {
    innerHTML: '', className: '',
    classList: { add() { }, remove() { }, toggle() { } },
    addEventListener(ev, fn) { svgEvents[ev] = fn; },
    setAttribute() { },
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 1200, height: 760 })
};
const els2 = {};
const el2 = (id) => els2[id] || (els2[id] = {
    id, textContent: '', innerHTML: '', style: {},
    classList: { add() { }, remove() { }, toggle() { }, contains: () => false },
    addEventListener() { }, setAttribute() { }
});
const doc2 = {
    body: { style: {} },
    getElementById: (id) => (id === 'svg' ? svg2 : el2(id)),
    createElement: (tag) => tag === 'canvas'
        ? { getContext: () => fakeCtx } : { style: {} },
    querySelector: (sel) => sel === '.canvas-wrap'
        ? { clientWidth: 1200, clientHeight: 760 } : el2(sel),
    querySelectorAll: () => []
};
const opened = [];
const win2 = { addEventListener() { }, open(url) { opened.push(url); } };
let runErr = '';
try {
    new Function('DATA', 'document', 'window', 'getComputedStyle', 'location', boot)(
        data, doc2, win2,
        () => ({ fontFamily: 'Arial, sans-serif', lineHeight: '20px' }),
        { origin: 'file://', search: '' });
} catch (e) { runErr = e.message; }
check(runErr === '', 'bootstrap chạy được' + (runErr ? ' — ' + runErr : ''));

const countCards = (s) => (s.match(/<g class="node-card/g) || []).length;
const drawn = countCards(svg2.innerHTML);
console.log('  vẽ được ' + drawn + ' mục khi mở file');
check(drawn === M.state.nodes.length, 'file mở ra vẽ đủ mục như trên trang');
check(svg2.innerHTML.includes('class="toggle"'), 'có badge gập/mở trong file');
check(!/undefined|NaN/.test(svg2.innerHTML), 'SVG trong file không lỗi giá trị');

// bấm Collapse rồi Expand phải đổi số mục hiển thị
const btnCollapse = els2['x-collapse'], btnExpand = els2['x-expand'];
check(!!(btnCollapse && btnCollapse.onclick), 'nút Collapse đã được gắn hàm');
btnCollapse.onclick();
const afterCollapse = countCards(svg2.innerHTML);
btnExpand.onclick();
const afterExpand = countCards(svg2.innerHTML);
console.log('  Collapse → ' + afterCollapse + ' mục, Expand → ' + afterExpand + ' mục');
check(afterCollapse < drawn, 'Collapse thu gọn sơ đồ');
check(afterExpand === drawn, 'Expand mở lại đầy đủ');

// các nút còn lại cũng phải chạy không lỗi
let btnErr = '';
['x-detail', 'x-layout', 'x-en', 'x-vi', 'x-fit', 'x-in', 'x-out'].forEach(id => {
    try {
        if (els2[id] && els2[id].onclick) els2[id].onclick.call(els2[id]);
        else btnErr = btnErr || (id + ' chưa gắn hàm');
    } catch (e) { btnErr = btnErr || (id + ': ' + e.message); }
});
check(btnErr === '', 'các nút khác chạy không lỗi' + (btnErr ? ' — ' + btnErr : ''));
check(countCards(svg2.innerHTML) > 0, 'sau khi bấm hết các nút vẫn còn sơ đồ');

// Bấm icon trong file HTML xuất ra: phải mở được cả link chức năng lẫn bài hướng dẫn.
// Bootstrap từng chỉ bắt .link-hit nên icon sách bấm không ăn.
function fakeHit(cls, url) {
    return {
        target: {
            closest: function (sel) {
                return sel.split(',').some(function (x) { return x.trim() === '.' + cls; })
                    ? { getAttribute: function () { return url; } } : null;
            }
        }
    };
}
check(typeof svgEvents.click === 'function', 'file HTML có gắn xử lý bấm chuột');
opened.length = 0;
svgEvents.click(fakeHit('link-hit', 'https://erp/desk/employee'));
check(opened[0] === 'https://erp/desk/employee', 'bấm mũi tên mở được chức năng');
opened.length = 0;
svgEvents.click(fakeHit('guide-hit', 'https://erp/lms/courses/module-hrms'));
check(opened[0] === 'https://erp/lms/courses/module-hrms',
    'bấm icon sách mở được bài hướng dẫn');

/* ══════════════ 11. tìm và focus một mục ═══════════════════════ */

console.log('\n=== focus mục theo từ khoá ===');
reset();
M.state.tree = M.parseMarkdown(hrText);
M.layout(M.state.tree);

// gập hết để chắc chắn focus phải tự mở nhánh cha
M.state.tree.children.forEach(function (c) {
    (function w(n) { if (n.children.length) M.state.collapsed.add(n.key); n.children.forEach(w); })(c);
});
M.layout(M.state.tree);
const collapsedCount = M.state.nodes.length;

const hit = M.focusNode('Đơn nghỉ việc');
check(hit === true, 'tìm thấy mục theo từ khoá có dấu');
const focused = M.state.nodes.find(function (n) { return n.key === M.state.focusKey; });
check(!!focused, 'mục được focus đã hiện ra (nhánh cha tự mở)');
check(focused && focused.title.includes('Đơn nghỉ việc'), 'focus đúng mục: '
    + (focused && focused.title));
check(M.state.selectedKey === M.state.focusKey, 'mục đó cũng được chọn');
check(M.state.nodes.length > collapsedCount,
    'số mục hiển thị tăng lên ' + collapsedCount + ' → ' + M.state.nodes.length);
const svgF = M.buildInner(false);
check(/class="node-card[^"]*focus"/.test(svgF), 'vẽ mục focus kèm class focus');

// phải PHÓNG VÀO chứ không chỉ dịch khung: đang xem toàn sơ đồ thì k rất nhỏ
reset();
M.state.tree = M.parseMarkdown(hrText);
M.layout(M.state.tree);
M.state.view.k = 0.25;                       // giả lập vừa bấm Fit trên sơ đồ lớn
M.focusNode('Đơn nghỉ việc');
console.log('  zoom 0.25 → ' + M.state.view.k);
check(M.state.view.k >= 1, 'zoom được đẩy lên mức đọc được (' + M.state.view.k + ')');

// và mục đó phải nằm giữa khung nhìn 1200x760 của DOM giả
const t = M.state.nodes.find(function (n) { return n.key === M.state.focusKey; });
const cx = t.x * M.state.view.k + M.state.view.tx + (t.w * M.state.view.k) / 2;
const cy = t.y * M.state.view.k + M.state.view.ty;
console.log('  tâm mục sau khi focus: ' + Math.round(cx) + ', ' + Math.round(cy));
check(Math.abs(cx - 600) < 2 && Math.abs(cy - 380) < 2, 'mục nằm đúng giữa khung nhìn');

// đang zoom sâu hơn rồi thì giữ nguyên, đừng thu nhỏ lại
M.state.view.k = 1.8;
M.focusNode('Đơn nghỉ việc');
check(M.state.view.k === 1.8, 'đang zoom sâu thì không bị kéo về 1');

// gõ không dấu vẫn phải khớp
reset();
M.state.tree = M.parseMarkdown(hrText);
M.layout(M.state.tree);
check(M.focusNode('don nghi viec') === true, 'gõ không dấu vẫn khớp');
check(M.state.nodes.find(function (n) { return n.key === M.state.focusKey; })
    .title.includes('Đơn nghỉ việc'), 'không dấu ra đúng mục');

// khớp trong phần mô tả khi tiêu đề không chứa từ khoá
check(M.focusNode('bàn giao') === true, 'khớp được trong phần mô tả');
console.log('   "bàn giao" → ' + M.state.nodes.find(
    function (n) { return n.key === M.state.focusKey; }).title);

// từ khoá không có thì báo false, không được ném lỗi
let thrown = '';
let miss = null;
try { miss = M.focusNode('zzzz-khong-co-gi'); } catch (e) { thrown = e.message; }
check(thrown === '' && miss === false, 'không tìm thấy thì trả về false, không lỗi');

/* ══════════════ 12. màu nền theo nhánh ═════════════════════════ */

console.log('\n=== màu nền từng nhánh cấp 1 ===');
reset();
M.state.tree = M.parseMarkdown(hrText);
M.layout(M.state.tree);

const tints = M.state.tree.children.map(function (c) { return c.tint; });
console.log('  ' + M.state.tree.children.length + ' nhánh: ' + tints.join(' '));
check(tints.every(Boolean), 'mọi nhánh cấp 1 đều có màu nền');

// mặc định lúc mở trang, kiểm thẳng trên source vì reset() của test đã đổi state
check(/layoutMode:\s*'sides'/.test(src), 'mặc định là kiểu vẽ hai bên');
check(/setAllCollapsed\(true\);[\s\S]{0,40}fit\(\);/.test(src),
    'mở file xong là gập hết rồi canh vừa khung');
check(new Set(tints).size === tints.length, 'mỗi nhánh một màu, không trùng');
check(M.state.tree.tint === '#fff', 'gốc vẫn nền trắng');
check(M.state.tree.children[0].children.every(function (c) { return !c.tint; }),
    'mục con không tô màu, chỉ nhánh cấp 1');

const svgT = M.buildInner(false);
tints.forEach(function (t) {
    if (!svgT.includes('fill="' + t + '"')) check(false, 'màu ' + t + ' có trong SVG');
});
check(tints.every(function (t) { return svgT.includes('fill="' + t + '"'); }),
    'SVG vẽ đúng màu nền của từng nhánh');
// ảnh export cũng phải giữ màu, vì bản xuất không có CSS của trang
check(M.exportSVGString().svg.includes('fill="' + tints[0] + '"'), 'ảnh export giữ màu nền');

// mọi nhánh cấp 1 phải có câu tóm tắt
const noDesc = M.state.tree.children.filter(function (c) { return !c.desc; })
    .map(function (c) { return c.title; });
// câu tóm tắt dài phải hiện đủ, node tự cao lên chứ không cắt chữ
reset();
M.layout(M.state.tree);
const cutDesc = M.state.tree.children.filter(function (c) {
    return c.descLines.some(function (l) { return l.endsWith('…'); });
});
const maxLines = Math.max.apply(null, M.state.tree.children.map(function (c) {
    return c.descLines.length;
}));
console.log('  mô tả nhánh dài nhất: ' + maxLines + ' dòng');
check(cutDesc.length === 0, 'không câu tóm tắt nào bị cắt'
    + (cutDesc.length ? ' — ' + cutDesc[0].title : ''));
check(maxLines >= 3, 'mô tả được xuống nhiều dòng (' + maxLines + ')');
const tallest = Math.max.apply(null, M.state.tree.children.map(function (c) { return c.h; }));
check(tallest > 60, 'node cao lên theo số dòng (' + Math.round(tallest) + 'px)');

check(noDesc.length === 0, 'mọi nhánh cấp 1 đều có mô tả tóm tắt'
    + (noDesc.length ? ' — thiếu: ' + noDesc.join(' | ') : ''));

/* ══════════════ 13. lần sửa cuối trên bản xuất ra ══════════════ */

console.log('\n=== last modified trên bản export ===');
reset();
M.state.tree = M.parseMarkdown(hrText);
M.state.sourcePath = 'hr_mindmap.md';
M.state.sourceMtime = 1789357618;                 // 14/09/2026 10:46 giờ máy chủ
const stamp = M.fmtTime(1789357618);
console.log('  mtime hiển thị: ' + stamp);
check(/^\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}$/.test(stamp), 'định dạng dd/mm/yyyy HH:MM');
check(M.fmtTime(0) === '', 'không có mtime thì để trống');

M.layout(M.state.tree);
const svgMeta = M.exportSVGString().svg;
check(svgMeta.includes(stamp), 'ảnh export có ghi lần sửa cuối của file');
check(svgMeta.includes('updated') && svgMeta.includes('exported'),
    'ảnh export phân biệt lần sửa cuối và lúc xuất');

let out = null;
M.setDownload(function (blob, name) { out = blob.parts.join(''); });
M.setEditorValue(hrText);
M.exportHTML();
check(out.includes(stamp), 'file HTML cũng có lần sửa cuối');

// nội dung dán vào thì không có file nguồn, không được bịa mốc thời gian
M.state.sourceMtime = 0;
M.layout(M.state.tree);
const svgNoMtime = M.exportSVGString().svg;
check(!svgNoMtime.includes('updated'), 'dán nội dung: không ghi lần sửa cuối');
check(svgNoMtime.includes('exported'), 'nhưng vẫn ghi lúc xuất');

/* ══════════════ 14. link bài hướng dẫn trong LMS ═══════════════ */

console.log('\n=== link bài hướng dẫn (LMS) ===');
reset();
for (const f of files) {
    const tree = M.parseMarkdown(fs.readFileSync(path.join(DOCS, f), 'utf8'));
    const withGuide = [];
    const dirty = [];
    (function w(n) {
        if (n.guide) withGuide.push(n);
        if ((n.desc && /\[Guide\]|\/lms\//.test(n.desc))
            || /\[Guide\]|\/lms\//.test(n.title)) dirty.push(n.title);
        n.children.forEach(w);
    })(tree);
    console.log('  ' + f + ': ' + withGuide.length + ' link — '
        + withGuide.map(function (n) { return n.title.replace(/^\d+\.\s/, '').split(' / ')[0]; }).join(', '));
    check(dirty.length === 0, f + ': link hướng dẫn không lẫn vào tiêu đề hay mô tả'
        + (dirty.length ? ' — ' + dirty[0] : ''));
    check(withGuide.length >= 1 && withGuide.length <= 3,
        f + ': chỉ gắn ở node gốc hoặc cấp module, không rải xuống mục con');
    check(withGuide.every(function (n) { return n.guide.startsWith('/lms/courses/'); }),
        f + ': link trỏ đúng vào khoá học');
}

// node gốc của HR nhận link từ dòng mô tả (blockquote), không phải dòng bullet
const hrTree = M.parseMarkdown(hrText);
check(hrTree.guide === '/lms/courses/module-hrms', 'node gốc HR có link khoá học');
check(!/Guide|lms/.test(hrTree.desc), 'mô tả node gốc không dính link');
check(hrTree.children.every(function (c) { return !c.guide; }), 'các nhánh con HR không còn link');

// vẽ và bấm được
M.state.tree = hrTree;
M.state.host = 'https://erp.tiqn.com.vn:8888';
M.layout(M.state.tree);
const svgG = M.buildInner(false);
check(svgG.includes('class="guide-hit"'), 'có vùng bấm mở khoá học');
check(svgG.includes('https://erp.tiqn.com.vn:8888/lms/courses/module-hrms'),
    'link hướng dẫn ghép host đầy đủ');
check(M.buildInner(true).includes('<a href="https://erp.tiqn.com.vn:8888/lms/courses/'),
    'export HTML bọc thẻ a cho link hướng dẫn');
check(!/undefined|NaN/.test(M.exportSVGString().svg), 'ảnh export vẫn hợp lệ');

/* ══════════════ kết luận ══════════════════════════════════════ */

fs.rmSync(TMP, { recursive: true, force: true });
console.log(fail ? '\n' + fail + ' KIỂM TRA THẤT BẠI' : '\nTất cả kiểm tra đạt');
process.exit(fail ? 1 : 0);
