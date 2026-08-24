/* Dev Tool — tab Hướng dẫn (tài liệu cho developer).
 *
 * Hai nguồn nội dung:
 *
 *  1. File .md nằm thẳng trong customize_erpnext/docs/user_manual — panel trái liệt kê.
 *  2. File "chỉ mục": một bài trong thư mục đó chỉ chứa đường dẫn tới README của
 *     các module khác trong app. Trang tự đọc đường dẫn, lấy tiêu đề, hiện thành
 *     danh sách bấm được, và làm các đường dẫn trong bài thành link.
 *     Đọc được mọi file .md trong app; ngoài app thì backend chặn.
 *
 * Chỉ đọc, không sửa. Khối ```mermaid trong bài vẫn được vẽ thành sơ đồ.
 */
(function () {
    'use strict';

    const CATEGORY = 'user_manual';

    let files = [];
    let links = [];          // đường dẫn bài hiện tại trỏ tới
    let pdfs = [];           // bản scan quy định gốc
    let currentPdf = null;
    let results = null;      // null = đang duyệt danh sách; mảng = đang xem kết quả tìm
    let searchTimer = null;
    let currentFile = null;  // file .md trong docs/user_manual đang mở
    let currentLink = null;  // file ngoài thư mục đang mở (nếu có)
    let mainEl = null;
    let renderToken = 0;

    /* ─────────────── sidebar ─────────────── */

    function buildSide(side) {
        side.innerHTML =
            '<div class="side-header">'
            + '<p class="eyebrow">docs/user_manual</p>'
            + '<h1>Hướng dẫn</h1>'
            + '</div>'
            + '<div class="side-block">'
            + '<input type="text" id="um-search" class="side-search" '
            + 'placeholder="Tìm trong toàn bộ tài liệu app…" autocomplete="off">'
            + '</div>'
            + '<div class="side-scroll">'
            + '<div id="um-files"><p class="hint" style="padding:0 8px">Đang tải…</p></div>'
            + '<div id="um-links"></div>'
            + '<div id="um-pdfs"></div>'
            + '</div>';

        // Gõ tới đâu tìm tới đó, chờ 250ms cho ngừng gõ rồi mới gọi máy chủ
        side.querySelector('#um-search').addEventListener('input', function () {
            const q = this.value;
            clearTimeout(searchTimer);
            searchTimer = setTimeout(function () { runSearch(q); }, 250);
        });
    }

    /** Tìm trong MỌI file .md của app, không chỉ thư mục docs/user_manual. */
    async function runSearch(query) {
        const api = window.DevTool;
        const q = (query || '').trim();

        if (q.length < 2) {          // 1 ký tự thì ra cả app, vô nghĩa
            results = null;
            renderFileList();
            renderLinkList();
            return;
        }

        try {
            const r = await api.call('customize_erpnext.api.docs_reader.search_docs',
                { query: q });
            results = (r && r.results) || [];
            renderResults(r ? r.total : 0, q);
        } catch (e) {
            api.toast('Tìm kiếm lỗi: ' + e.message, true);
        }
    }

    /** Tô đậm chỗ khớp trong đoạn trích — so sánh trên bản đã bỏ dấu. */
    function stripAccentsLower(t) {
        return String(t || '').replace(/đ/g, 'd').replace(/Đ/g, 'D')
            .normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    }

    function highlight(text, q) {
        const api = window.DevTool;
        const strip = stripAccentsLower;
        const i = strip(text).indexOf(strip(q));
        if (i < 0) return api.esc(text);
        return api.esc(text.slice(0, i))
            + '<mark>' + api.esc(text.slice(i, i + q.length)) + '</mark>'
            + api.esc(text.slice(i + q.length));
    }

    function renderResults(total, q) {
        const api = window.DevTool;
        const box = document.getElementById('um-files');
        const linkBox = document.getElementById('um-links');
        if (linkBox) linkBox.innerHTML = '';
        if (!box) return;

        if (!results.length) {
            box.innerHTML = '<p class="hint" style="padding:0 8px">Không tìm thấy "'
                + api.esc(q) + '" trong file .md nào của app.</p>';
            return;
        }

        box.innerHTML = '<p class="block-title" style="padding:0 8px 6px">'
            + results.length + (total > results.length ? ' / ' + total : '')
            + ' kết quả trong toàn app</p>';

        results.forEach(function (r) {
            const btn = document.createElement('button');
            btn.className = 'doc-link';
            let html = highlight(r.title, q)
                + '<span class="meta">' + highlight(r.rel, q) + '</span>';
            if (r.snippet) {
                html += '<span class="hit">L' + r.line + ': ' + highlight(r.snippet, q) + '</span>';
            }
            btn.innerHTML = html;
            btn.addEventListener('click', function () { openResult(r); });
            box.appendChild(btn);
        });
    }

    /** File trong docs/user_manual mở như bài thường; ngoài đó mở dạng liên kết. */
    function openResult(r) {
        if (r.in_manual) {
            openFile(r.rel.split('/').pop());
        } else {
            openLink(r.rel);
        }
    }

    function renderFileList(filter) {
        if (results) return;      // đang xem kết quả tìm, đừng vẽ đè lên
        const box = document.getElementById('um-files');
        if (!box) return;
        const api = window.DevTool;

        const q = (filter || '').trim().toLowerCase();
        const shown = q
            ? files.filter(f => (f.title + ' ' + f.name).toLowerCase().includes(q))
            : files;

        if (!files.length) {
            box.innerHTML = '<p class="hint" style="padding:0 8px">Chưa có file .md nào trong '
                + 'customize_erpnext/docs/user_manual/</p>';
            return;
        }
        if (!shown.length) {
            box.innerHTML = '<p class="hint" style="padding:0 8px">Không có bài nào khớp.</p>';
            return;
        }

        box.innerHTML = '';
        shown.forEach(function (f) {
            const btn = document.createElement('button');
            btn.className = 'doc-link'
                + (f.name === currentFile && !currentLink ? ' active' : '');
            btn.innerHTML = api.esc(f.title || f.name)
                + '<span class="meta">' + api.esc(f.name) + '</span>';
            btn.addEventListener('click', function () { openFile(f.name); });
            box.appendChild(btn);
        });
    }

    /** Bản scan quy định gốc — chỉ xem và tải, không sửa. */
    function renderPdfList() {
        if (results) return;      // đang xem kết quả tìm
        const box = document.getElementById('um-pdfs');
        if (!box) return;
        const api = window.DevTool;

        if (!pdfs.length) { box.innerHTML = ''; return; }

        box.innerHTML = '<p class="block-title" style="padding:16px 8px 6px">'
            + 'Quy định gốc — bản scan (' + pdfs.length + ')</p>';

        pdfs.forEach(function (f) {
            const row = document.createElement('div');
            row.className = 'pdf-row' + (f.name === currentPdf ? ' active' : '');

            const open = document.createElement('button');
            open.className = 'doc-link';
            open.innerHTML = '📄 ' + api.esc(f.name.replace(/\.pdf$/i, ''))
                + '<span class="meta">' + f.size_mb + ' MB · ' + api.esc(f.modified) + '</span>';
            open.addEventListener('click', function () { openPdf(f.name); });
            row.appendChild(open);

            const dl = document.createElement('a');
            dl.className = 'pdf-download';
            dl.href = pdfUrl(f.name, 1);
            dl.title = 'Tải ' + f.name;
            dl.textContent = '⭳';
            row.appendChild(dl);

            box.appendChild(row);
        });
    }

    /** URL của một PDF. download=1 thì trình duyệt tải về thay vì mở. */
    function pdfUrl(name, download) {
        return '/api/method/customize_erpnext.api.docs_reader.get_pdf'
            + '?filename=' + encodeURIComponent(name)
            + (download ? '&download=1' : '');
    }

    /** Mở PDF trong khung xem của trình duyệt, kèm nút tải. */
    function openPdf(name) {
        const api = window.DevTool;
        renderToken++;                 // huỷ mọi vòng render markdown đang chạy dở
        currentPdf = name;
        currentFile = null;
        currentLink = null;
        links = [];

        mainEl.innerHTML = '';
        const wrap = document.createElement('div');
        wrap.className = 'pdf-view';

        const bar = document.createElement('div');
        bar.className = 'md-crumb';
        const title = document.createElement('span');
        title.className = 'pdf-title';
        title.textContent = name;
        bar.appendChild(title);

        const dl = document.createElement('a');
        dl.className = 'pdf-btn';
        dl.href = pdfUrl(name, 1);
        dl.textContent = '⭳  Tải PDF';
        bar.appendChild(dl);

        const tab = document.createElement('a');
        tab.className = 'pdf-btn ghost';
        tab.href = pdfUrl(name, 0);
        tab.target = '_blank';
        tab.rel = 'noopener';
        tab.textContent = 'Mở tab mới';
        bar.appendChild(tab);

        wrap.appendChild(bar);

        // iframe: dùng trình đọc PDF sẵn có của trình duyệt, không nhúng thư viện nào
        const frame = document.createElement('iframe');
        frame.className = 'pdf-frame';
        frame.src = pdfUrl(name, 0);
        frame.title = name;
        wrap.appendChild(frame);

        mainEl.appendChild(wrap);
        renderFileList(document.getElementById('um-search').value);
        renderLinkList();
        renderPdfList();
    }

    /** Danh sách file mà bài đang mở trỏ tới. Rỗng thì giấu hẳn khối này. */
    function renderLinkList() {
        if (results) return;      // đang xem kết quả tìm
        const box = document.getElementById('um-links');
        if (!box) return;
        const api = window.DevTool;

        if (!links.length) { box.innerHTML = ''; return; }

        box.innerHTML = '<p class="block-title" style="padding:16px 8px 6px">'
            + 'Tài liệu bài này trỏ tới (' + links.length + ')</p>';

        links.forEach(function (l) {
            const btn = document.createElement('button');
            btn.className = 'doc-link' + (l.rel === currentLink ? ' active' : '');
            if (!l.exists) {
                btn.classList.add('doc-link-broken');
                btn.title = 'Không tìm thấy file này';
            }
            btn.innerHTML = api.esc(l.title)
                + '<span class="meta">' + api.esc(l.rel)
                + (l.exists ? '' : ' · không tìm thấy') + '</span>';
            btn.addEventListener('click', function () {
                if (!l.exists) { api.toast('Không tìm thấy: ' + l.path, true); return; }
                openLink(l.rel);
            });
            box.appendChild(btn);
        });
    }

    /* ─────────────── vùng đọc ─────────────── */

    /** Khung bài: cột nội dung + cột mục lục bên phải. */
    /** Tô sáng chỗ khớp đầu tiên trong bài rồi cuộn tới, dùng khi mở từ ô tìm kiếm. */
    function focusMatch(q) {
        const needle = stripAccentsLower(q);
        if (!needle || needle.length < 2) return false;
        const article = mainEl && mainEl.querySelector('.md-body');
        if (!article) return false;

        article.querySelectorAll('mark.find-hit').forEach(function (m) {
            m.replaceWith(document.createTextNode(m.textContent));
        });

        // Đi qua từng text node để không phá cấu trúc thẻ khi chèn <mark>
        const walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT, {
            acceptNode: function (node) {
                if (!node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
                const tag = node.parentNode && node.parentNode.nodeName;
                if (tag === 'SCRIPT' || tag === 'STYLE') return NodeFilter.FILTER_REJECT;
                return NodeFilter.FILTER_ACCEPT;
            }
        });

        let node;
        while ((node = walker.nextNode())) {
            const at = stripAccentsLower(node.nodeValue).indexOf(needle);
            if (at < 0) continue;

            const range = document.createRange();
            range.setStart(node, at);
            range.setEnd(node, Math.min(at + q.length, node.nodeValue.length));
            const mark = document.createElement('mark');
            mark.className = 'find-hit';
            try { range.surroundContents(mark); }
            catch (e) { return false; }        // khớp vắt qua nhiều thẻ thì bỏ qua

            mark.scrollIntoView({ block: 'center' });
            return true;
        }
        return false;
    }

    function buildArticle(html, crumb) {
        mainEl.innerHTML = '';

        const layout = document.createElement('div');
        layout.className = 'md-layout';

        const col = document.createElement('div');
        col.className = 'md-col';
        if (crumb) col.appendChild(crumb);

        const article = document.createElement('article');
        article.className = 'md-body';
        article.innerHTML = html;
        col.appendChild(article);

        const toc = document.createElement('nav');
        toc.className = 'md-toc';

        layout.appendChild(col);
        layout.appendChild(toc);
        mainEl.appendChild(layout);
        mainEl.scrollTop = 0;

        return { article: article, toc: toc };
    }

    /** Thanh cho biết đang đọc file ngoài thư mục, kèm nút quay lại. */
    function buildCrumb(rel, modified) {
        const api = window.DevTool;
        const bar = document.createElement('div');
        bar.className = 'md-crumb';

        const back = document.createElement('button');
        back.className = 'ghost';
        back.textContent = '← ' + (currentFile || 'danh sách');
        back.addEventListener('click', function () {
            if (currentFile) openFile(currentFile);
        });
        bar.appendChild(back);

        const where = document.createElement('span');
        where.className = 'md-crumb-path';
        where.textContent = rel + (modified ? '  ·  sửa ' + modified : '');
        bar.appendChild(where);

        return bar;
    }

    function buildTOC(article, toc) {
        const heads = article.querySelectorAll('h2, h3');
        if (heads.length < 2) { toc.remove(); return; }

        toc.innerHTML = '<p class="md-toc-title">Trong bài</p>';
        heads.forEach(function (h, i) {
            if (!h.id) h.id = 'um-h-' + i;
            const a = document.createElement('a');
            a.className = 'md-toc-link' + (h.tagName === 'H3' ? ' lv3' : '');
            a.href = '#' + h.id;
            a.textContent = h.textContent;
            a.addEventListener('click', function (ev) {
                ev.preventDefault();
                h.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
            toc.appendChild(a);
        });
    }

    /** markdown2 biến ```mermaid thành <pre><code class="mermaid">; vẽ chúng ra. */
    async function renderMermaidBlocks(root, token) {
        const blocks = root.querySelectorAll('code.mermaid, code.language-mermaid');
        for (let i = 0; i < blocks.length; i++) {
            if (token !== renderToken) return;
            const code = blocks[i];
            const holder = code.closest('pre') || code;
            try {
                const res = await mermaid.render('um-mmd-' + token + '-' + i, code.textContent);
                if (token !== renderToken) return;
                const box = document.createElement('div');
                box.className = 'md-diagram';
                box.innerHTML = res.svg;
                holder.replaceWith(box);
            } catch (err) {
                holder.classList.add('md-diagram-failed');   // giữ nguyên khối code
            }
        }
    }

    /** Biến các đường dẫn .md in trong bài thành link bấm được. */
    function linkifyPaths(article) {
        if (!links.length) return;
        const byText = {};
        links.forEach(function (l) { if (l.exists) byText[l.path] = l; });

        article.querySelectorAll('code').forEach(function (el) {
            const l = byText[el.textContent.trim()];
            if (!l) return;
            const a = document.createElement('a');
            a.className = 'md-path-link';
            a.href = '#';
            a.title = 'Mở ' + l.rel;
            a.textContent = el.textContent;
            a.addEventListener('click', function (ev) {
                ev.preventDefault();
                openLink(l.rel);
            });
            el.replaceWith(a);
        });
    }

    /* ─────────────── nạp dữ liệu ─────────────── */

    async function loadPdfs() {
        const api = window.DevTool;
        try {
            const r = await api.call('customize_erpnext.api.docs_reader.list_pdfs', {});
            pdfs = (r && r.files) || [];
        } catch (e) {
            pdfs = [];
        }
        renderPdfList();
    }

    async function loadFiles() {
        const api = window.DevTool;
        try {
            const r = await api.call('customize_erpnext.api.docs_reader.list_docs',
                { category: CATEGORY });
            files = (r && r.files) || [];
        } catch (e) {
            files = [];
            api.toast('Không đọc được danh sách bài: ' + e.message, true);
        }
        renderFileList();
        return files;
    }

    async function openFile(name) {
        const api = window.DevTool;
        const token = ++renderToken;
        try {
            const r = await api.call('customize_erpnext.api.docs_reader.get_doc_html',
                { category: CATEGORY, filename: name });
            if (token !== renderToken) return;

            currentFile = name;
            currentLink = null;
            currentPdf = null;

            const parts = buildArticle(r.html, null);
            await renderMermaidBlocks(parts.article, token);
            if (token !== renderToken) return;

            // đọc đường dẫn bài này trỏ tới, rồi mới linkify
            try {
                const lr = await api.call('customize_erpnext.api.docs_reader.list_linked_docs',
                    { category: CATEGORY, filename: name });
                links = (lr && lr.links) || [];
            } catch (e) {
                links = [];
            }
            if (token !== renderToken) return;

            linkifyPaths(parts.article);
            buildTOC(parts.article, parts.toc);
            renderFileList(document.getElementById('um-search').value);
            renderLinkList();
        } catch (e) {
            if (token !== renderToken) return;
            api.toast('Không mở được ' + name + ': ' + e.message, true);
        }
    }

    async function openLink(rel) {
        const api = window.DevTool;
        const token = ++renderToken;
        try {
            const r = await api.call('customize_erpnext.api.docs_reader.get_app_doc_html',
                { path: rel });
            if (token !== renderToken) return;

            currentLink = r.rel;
            currentPdf = null;
            const parts = buildArticle(r.html, buildCrumb(r.rel, r.modified));
            await renderMermaidBlocks(parts.article, token);
            if (token !== renderToken) return;

            buildTOC(parts.article, parts.toc);
            renderFileList(document.getElementById('um-search').value);
            renderLinkList();
        } catch (e) {
            if (token !== renderToken) return;
            api.toast('Không mở được ' + rel + ': ' + e.message, true);
        }
    }

    /* ─────────────── vòng đời tab ─────────────── */

    window.DevTool.registerTab({
        id: 'user-manual',
        label: 'Hướng dẫn',
        icon: '📖',
        order: 30,

        // Dùng lại đúng luật của ô tìm kiếm trong tab này: file thuộc
        // docs/user_manual mở như bài thường, còn lại mở dạng liên kết.
        openDoc: function (req) {
            if (!req || !req.rel) return;
            const done = req.appDoc ? openLink(req.rel) : openFile(req.filename);
            // Bài render xong (kể cả mermaid) mới tô sáng được
            Promise.resolve(done).then(function () {
                if (req.query) focusMatch(req.query);
            });
        },

        mount: async function (ctx) {
            mainEl = ctx.main;

            buildSide(ctx.side);
            mainEl.innerHTML = '<p class="placeholder">Đang tải…</p>';

            const list = await loadFiles();
            loadPdfs();          // chạy song song, không chặn bài đầu tiên
            if (list.length) {
                await openFile(list[0].name);
            } else {
                mainEl.innerHTML = '<p class="placeholder">Chưa có bài nào. '
                    + 'Thả file .md vào customize_erpnext/docs/user_manual/ rồi mở lại tab này.</p>';
            }
        },

        unmount: function () {
            renderToken++;
            clearTimeout(searchTimer);
            results = null;
            pdfs = [];
            currentPdf = null;
            files = [];
            links = [];
            currentFile = null;
            currentLink = null;
            mainEl = null;
        }
    });
})();
