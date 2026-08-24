/* Dev Tool — tab Flowchart.
 *
 * Đọc file .md trong customize_erpnext/docs/flowchart qua api/docs_reader.py,
 * tách từng diagram theo đúng format skill `erpnext-flowchart-sync` sinh ra:
 *
 *     ## <N>. <Vai trò> — từ <A> đến <B>
 *     ```mermaid ... ```
 *     > Nguồn: <file>(<hàm>) · ...
 *
 * Render bằng Mermaid.js chứ không qua draw.io: draw.io khi import Mermaid sẽ
 * bỏ classDef/style/inline style (đã thử, set lại rồi apply vẫn mất), Mermaid.js
 * tự vẽ SVG nên giữ nguyên 100%. draw.io chỉ dùng khi cần kéo tay layout.
 *
 * Gọi mermaid.render() cho từng diagram (không dùng mermaid.init) để một diagram
 * sai cú pháp chỉ hỏng đúng card của nó, không kéo sập cả trang.
 */
(function () {
    'use strict';

    const CATEGORY = 'flowchart';

    let files = [];
    let sections = [];
    let currentFile = null;
    let currentMtime = null;   // mtime lúc mở file, gửi lại khi lưu để chống ghi đè
    let canEdit = false;
    let mainEl = null;
    let renderToken = 0;   // bỏ kết quả render của lần bấm cũ khi người dùng bấm liên tiếp

    /* ─────────────── parser ─────────────── */

    function parseMarkdown(md) {
        const lines = String(md || '').split('\n');
        const out = [];
        let current = null;
        let inMermaid = false;
        let buf = [];

        for (const line of lines) {
            const trimmed = line.trim();

            if (!inMermaid && /^##\s+/.test(line)) {
                if (current) out.push(current);
                current = { title: line.replace(/^##\s+/, '').trim(), mermaid: '', source: '' };
                continue;
            }
            if (!inMermaid && /^```mermaid/.test(trimmed)) {
                inMermaid = true;
                buf = [];
                // Khối mermaid đứng trước heading đầu tiên vẫn nhận, để ô "dán trực
                // tiếp" chấp nhận cả mermaid trần lẫn .md đầy đủ
                if (!current) current = { title: '', mermaid: '', source: '' };
                continue;
            }
            if (inMermaid && /^```/.test(trimmed)) {
                inMermaid = false;
                if (current) current.mermaid = buf.join('\n');
                continue;
            }
            if (inMermaid) {
                buf.push(line);
                continue;
            }
            if (current && /^>\s*Ngu[oồ]n\s*:/i.test(trimmed)) {
                current.source = trimmed.replace(/^>\s*/, '');
                continue;
            }
        }
        if (current) out.push(current);
        return out.filter(s => s.mermaid.trim().length > 0);
    }

    /** Mermaid trần (không có ```mermaid, không có ##) — dán thẳng từ draw.io. */
    function looksLikeBareMermaid(text) {
        return /^\s*(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram|erDiagram|journey|gantt|pie|mindmap|timeline)\b/
            .test(String(text || ''));
    }

    function parseInput(text) {
        const parsed = parseMarkdown(text);
        if (parsed.length) return parsed;
        if (looksLikeBareMermaid(text)) {
            return [{ title: '', mermaid: String(text).trim(), source: '' }];
        }
        return [];
    }

    /* ─────────────── sidebar ─────────────── */

    function buildSide(side, api) {
        side.innerHTML =
            '<div class="side-header">'
            + '<p class="eyebrow">erpnext-flowchart-sync</p>'
            + '<h1>Flowchart</h1>'
            + '<p>Render bằng Mermaid.js — giữ nguyên classDef, màu và label. '
            + 'draw.io chỉ cần khi muốn kéo tay layout.</p>'
            + '</div>'
            + '<div class="side-block">'
            + '<p class="block-title">Dán nội dung</p>'
            + '<textarea class="code" id="fc-input" spellcheck="false" '
            + 'placeholder="Dán .md (## + ```mermaid + > Nguồn:) hoặc mermaid trần…"></textarea>'
            + '<div class="btn-row">'
            + '<button class="primary" id="fc-render">Render</button>'
            + '<button class="ghost" id="fc-save">Lưu</button>'
            + '<button class="ghost" id="fc-clear">Xoá</button>'
            + '</div>'
            + '<p class="hint" id="fc-save-hint"></p>'
            + '</div>'
            + '<div class="side-scroll">'
            + '<p class="block-title" style="padding:0 8px 6px">docs/flowchart</p>'
            + '<div id="fc-files"><p class="hint" style="padding:0 8px">Đang tải…</p></div>'
            + '<p class="block-title" style="padding:14px 8px 6px">Mục lục</p>'
            + '<div id="fc-toc"></div>'
            + '</div>';

        side.querySelector('#fc-render').addEventListener('click', function () {
            // Render nội dung đang dán: không còn gắn với file nào nữa
            currentFile = null;
            currentMtime = null;
            markActiveFile();
            updateSaveState();
            renderInput(side.querySelector('#fc-input').value, api);
        });
        side.querySelector('#fc-clear').addEventListener('click', function () {
            side.querySelector('#fc-input').value = '';
            side.querySelector('#fc-input').focus();
        });
        side.querySelector('#fc-save').addEventListener('click', function () {
            saveFile(api);
        });

        // Ctrl+S trong ô soạn thảo: lưu, đừng để trình duyệt mở hộp thoại lưu trang
        side.querySelector('#fc-input').addEventListener('keydown', function (ev) {
            if ((ev.ctrlKey || ev.metaKey) && (ev.key === 's' || ev.key === 'S')) {
                ev.preventDefault();
                saveFile(api);
            }
        });

        updateSaveState();
    }

    /** Nút Lưu chỉ sáng khi có quyền VÀ đang mở một file thật (không phải nội dung dán). */
    function updateSaveState() {
        const btn = document.getElementById('fc-save');
        const hint = document.getElementById('fc-save-hint');
        if (!btn) return;

        const ok = canEdit && !!currentFile;
        btn.disabled = !ok;
        btn.style.opacity = ok ? '' : '.45';
        btn.style.cursor = ok ? '' : 'not-allowed';

        if (!hint) return;
        if (!canEdit) {
            hint.textContent = 'Chỉ Administrator mới lưu được file tài liệu.';
        } else if (!currentFile) {
            hint.textContent = 'Chọn một file bên dưới để lưu đè lên file đó. '
                + 'Nội dung dán trực tiếp thì chỉ render, không có file để ghi.';
        } else {
            hint.textContent = 'Lưu vào ' + currentFile + ' (Ctrl+S). Bản trước giữ ở .bak.';
        }
    }

    async function saveFile(api) {
        if (!canEdit || !currentFile) return;

        const input = document.getElementById('fc-input');
        const content = input ? input.value : '';
        if (!content.trim()) {
            api.toast('Nội dung rỗng, không lưu', true);
            return;
        }

        try {
            const r = await api.call('customize_erpnext.api.docs_reader.save_doc', {
                category: CATEGORY,
                filename: currentFile,
                content: content,
                known_mtime: currentMtime === null ? '' : currentMtime
            });
            currentMtime = r.mtime;
            api.toast('Đã lưu ' + r.name + ' (' + r.bytes + ' bytes)');
            updateSaveState();
            renderInput(content, api);   // vẽ lại đúng nội dung vừa ghi
            await loadFiles(api);        // cập nhật lại kích thước, giờ sửa
        } catch (e) {
            api.toast(e.message, true);
        }
    }

    function markActiveFile() {
        document.querySelectorAll('#fc-files .doc-link').forEach(function (el) {
            el.classList.toggle('active', el.dataset.file === currentFile);
        });
    }

    function renderFileList(api) {
        const box = document.getElementById('fc-files');
        if (!box) return;

        if (!files.length) {
            box.innerHTML = '<p class="hint" style="padding:0 8px">Chưa có file .md nào trong '
                + 'customize_erpnext/docs/flowchart/</p>';
            return;
        }

        box.innerHTML = '';
        files.forEach(function (f) {
            const btn = document.createElement('button');
            btn.className = 'doc-link';
            btn.dataset.file = f.name;
            btn.innerHTML = api.esc(f.title || f.name)
                + '<span class="meta">' + api.esc(f.name) + ' · ' + api.esc(f.modified) + '</span>';
            btn.addEventListener('click', function () { openFile(f.name, api); });
            box.appendChild(btn);
        });
        markActiveFile();
    }

    function renderTOC(api) {
        const toc = document.getElementById('fc-toc');
        if (!toc) return;
        toc.innerHTML = '';
        sections.forEach(function (sec, i) {
            const a = document.createElement('a');
            a.className = 'doc-link';
            a.href = '#fc-section-' + i;
            a.textContent = sec.title || ('Diagram ' + (i + 1));
            toc.appendChild(a);
        });
    }

    /* ─────────────── hiển thị: hướng vẽ + zoom ───────────────
       Sơ đồ `flowchart TD` là khối cao và hẹp: màn rộng thì thừa chỗ bên phải,
       còn cuộn dọc thì dài. Hai nút xử lý hai chuyện đó:
       - Hướng: đổi TD/TB -> LR khi hiển thị, dùng luôn bề ngang màn hình.
         Chỉ đổi bản đang xem, file .md giữ nguyên hướng tác giả viết.
       - Zoom: mặc định "Vừa khung" = thu/phóng để cả sơ đồ nằm gọn một màn.  */

    const MIN_SCALE = 0.2, MAX_SCALE = 4;
    let cards = [];

    function mermaidFor(card) {
        if (card.dir !== 'LR') return card.sec.mermaid;
        // chỉ thay từ khoá hướng ở dòng khai báo đầu tiên
        return card.sec.mermaid.replace(
            /^(\s*(?:flowchart|graph)[ \t]+)(TD|TB)\b/m, '$1LR');
    }

    const clampScale = (s) => Math.min(Math.max(s, MIN_SCALE), MAX_SCALE);

    /** Chiều cao khung nhìn: gần hết màn hình, chừa chỗ cho tiêu đề + nút + dòng Nguồn. */
    function viewportHeight() {
        const reserve = document.body.classList.contains('present') ? 150 : 320;
        return Math.max(300, (mainEl ? mainEl.clientHeight : 800) - reserve);
    }

    /** Đẩy vị trí + hệ số phóng hiện tại lên DOM. */
    function applyView(card) {
        if (!card.stage) return;
        card.stage.style.transform =
            'translate(' + card.tx + 'px, ' + card.ty + 'px) scale(' + card.scale + ')';
        if (card.zoomLabel) card.zoomLabel.textContent = Math.round(card.scale * 100) + '%';
        card.viewBtns.forEach(function (b) {
            b.classList.toggle('on', b.dataset.mode === card.mode || b.dataset.dir === card.dir);
        });
    }

    /** Tính lại hệ số + căn giữa theo chế độ 'fit' / 'width'. */
    function applyScale(card) {
        if (!card.natural || !card.wrap) return;

        card.wrap.style.height = viewportHeight() + 'px';

        const nw = card.natural.w, nh = card.natural.h;
        const vw = card.wrap.clientWidth, vh = card.wrap.clientHeight;
        const padded = 24;   // chừa mép cho sơ đồ không dính viền khung

        if (card.mode === 'fit' || card.mode === 'width') {
            const s = clampScale(card.mode === 'width'
                ? (vw - padded) / nw
                : Math.min((vw - padded) / nw, (vh - padded) / nh));
            card.scale = s;
            card.tx = (vw - nw * s) / 2;
            // cao hơn khung thì ghim mép trên, không thì căn giữa dọc
            card.ty = nh * s > vh ? padded / 2 : (vh - nh * s) / 2;
        }

        applyView(card);
    }

    /* Cuộn chuột = phóng to thu nhỏ, kéo = di chuyển — giống thao tác trên trang
       mindmap. Khác một chỗ: mindmap chỉ có một khung toàn màn hình, còn đây là
       nhiều card xếp dọc, nên khi đã chạm mức phóng tối đa/tối thiểu thì KHÔNG
       nuốt sự kiện nữa, để trang cuộn tiếp qua card khác. */
    function bindPanZoom(card) {
        const wrap = card.wrap;

        wrap.addEventListener('wheel', function (ev) {
            if (!card.natural) return;

            const next = clampScale(card.scale * (ev.deltaY < 0 ? 1.12 : 1 / 1.12));
            if (next === card.scale) return;   // hết cỡ rồi: nhường cho trang cuộn

            ev.preventDefault();

            // Neo đúng điểm dưới con trỏ: điểm đó phải nằm nguyên chỗ cũ sau khi
            // phóng. Với transform-origin 0 0 thì tx' = mx - (mx - tx) * k.
            const rect = wrap.getBoundingClientRect();
            const mx = ev.clientX - rect.left;
            const my = ev.clientY - rect.top;
            const k = next / card.scale;

            card.tx = mx - (mx - card.tx) * k;
            card.ty = my - (my - card.ty) * k;
            card.scale = next;
            card.mode = 'manual';
            applyView(card);
        }, { passive: false });

        wrap.addEventListener('mousedown', function (ev) {
            if (ev.button !== 0) return;
            panning = { card: card, x: ev.clientX, y: ev.clientY, tx: card.tx, ty: card.ty };
            wrap.classList.add('grabbing');
            ev.preventDefault();          // đừng bôi đen chữ trong sơ đồ khi kéo
        });
    }

    let panning = null;

    function onPanMove(ev) {
        if (!panning) return;
        const c = panning.card;
        c.tx = panning.tx + (ev.clientX - panning.x);
        c.ty = panning.ty + (ev.clientY - panning.y);
        c.mode = 'manual';
        applyView(c);
    }

    function onPanUp() {
        if (!panning) return;
        panning.card.wrap.classList.remove('grabbing');
        panning = null;
    }

    function measure(card) {
        const svg = card.stage ? card.stage.querySelector('svg') : null;
        card.natural = null;
        if (!svg) return;

        // viewBox là kích thước thật Mermaid tính ra; style inline của nó chặn phóng to
        const vb = (svg.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
        if (vb.length === 4 && vb[2] > 0 && vb[3] > 0) {
            card.natural = { w: vb[2], h: vb[3] };
        } else {
            const box = svg.getBoundingClientRect();
            card.natural = { w: box.width || 400, h: box.height || 300 };
        }

        // Stage giữ kích thước gốc 1:1; phóng to thu nhỏ do transform lo
        svg.removeAttribute('width');
        svg.removeAttribute('height');
        svg.style.maxWidth = 'none';
        svg.style.width = card.natural.w + 'px';
        svg.style.height = card.natural.h + 'px';
        card.stage.style.width = card.natural.w + 'px';
        card.stage.style.height = card.natural.h + 'px';
    }

    async function drawCard(card, token, api) {
        try {
            const res = await mermaid.render(
                'fc-mmd-' + token + '-' + card.index + '-' + (card.renders++), mermaidFor(card));
            if (token !== renderToken) return;

            card.wrap.innerHTML = '';
            card.stage = document.createElement('div');
            card.stage.className = 'diagram-stage';
            card.stage.innerHTML = res.svg;
            card.wrap.appendChild(card.stage);

            measure(card);
            applyScale(card);
        } catch (err) {
            if (token !== renderToken) return;
            card.wrap.innerHTML = '';
            card.stage = null;          // stage cũ đã bị xoá cùng innerHTML
            card.natural = null;
            card.wrap.style.height = '';
            const errEl = document.createElement('p');
            errEl.className = 'diagram-error';
            errEl.textContent = 'Lỗi cú pháp Mermaid: ' + (err && err.message ? err.message : err);
            card.wrap.appendChild(errEl);
            if (api) api.toast('Diagram "' + (card.sec.title || card.index + 1) + '" lỗi cú pháp', true);
        }
    }

    function buildViewBar(card, token, api) {
        const bar = document.createElement('div');
        bar.className = 'view-bar';
        card.viewBtns = [];

        function group() {
            const g = document.createElement('div');
            g.className = 'view-group';
            bar.appendChild(g);
            return g;
        }
        function btn(parent, text, title, setup) {
            const b = document.createElement('button');
            b.textContent = text;
            b.title = title;
            setup(b);
            parent.appendChild(b);
            return b;
        }

        const gDir = group();
        [['Dọc', 'TD'], ['Ngang', 'LR']].forEach(function (pair) {
            const b = btn(gDir, pair[0],
                pair[1] === 'LR'
                    ? 'Vẽ ngang (LR) — dùng hết bề ngang, đỡ phải cuộn dài'
                    : 'Vẽ dọc, đúng hướng trong file .md',
                function (el) { el.dataset.dir = pair[1]; });
            b.onclick = function () {
                if (card.dir === pair[1]) return;
                card.dir = pair[1];
                drawCard(card, token, api);
            };
            card.viewBtns.push(b);
        });

        const gZoom = group();
        [['Vừa khung', 'fit', 'Thu phóng để cả sơ đồ nằm gọn trong một màn hình'],
         ['Vừa ngang', 'width', 'Phóng cho vừa hết bề ngang']].forEach(function (t) {
            const b = btn(gZoom, t[0], t[2], function (el) { el.dataset.mode = t[1]; });
            b.onclick = function () { card.mode = t[1]; applyScale(card); };
            card.viewBtns.push(b);
        });
        btn(gZoom, '−', 'Thu nhỏ', function () {}).onclick = function () {
            card.mode = 'manual'; card.scale = card.scale / 1.2; applyScale(card);
        };
        card.zoomLabel = document.createElement('span');
        card.zoomLabel.className = 'zoom-label';
        card.zoomLabel.textContent = '100%';
        gZoom.appendChild(card.zoomLabel);
        btn(gZoom, '+', 'Phóng to', function () {}).onclick = function () {
            card.mode = 'manual'; card.scale = card.scale * 1.2; applyScale(card);
        };
        btn(gZoom, '1:1', 'Kích thước gốc Mermaid vẽ ra', function () {}).onclick = function () {
            card.mode = 'manual'; card.scale = 1; applyScale(card);
        };

        const hint = document.createElement('span');
        hint.className = 'view-hint';
        hint.textContent = 'Cuộn chuột để phóng · kéo để di chuyển · hướng chỉ đổi bản đang xem';
        bar.appendChild(hint);

        return bar;
    }

    /* ─────────────── render ─────────────── */

    async function renderAll(api) {
        const token = ++renderToken;
        cards = [];
        mainEl.innerHTML = '';

        if (!sections.length) {
            mainEl.innerHTML = '<p class="placeholder">Không tìm thấy khối ```mermaid nào. '
                + 'Chọn một file bên trái, hoặc dán nội dung rồi bấm Render.</p>';
            renderTOC(api);
            return;
        }

        const wrapper = document.createElement('div');
        wrapper.style.padding = '28px 32px 80px';
        mainEl.appendChild(wrapper);

        for (let i = 0; i < sections.length; i++) {
            if (token !== renderToken) return;    // đã có lần render mới, bỏ lần này
            const sec = sections[i];

            const el = document.createElement('div');
            el.className = 'diagram-card';
            el.id = 'fc-section-' + i;

            const h2 = document.createElement('h2');
            h2.textContent = sec.title || ('Diagram ' + (i + 1));
            el.appendChild(h2);

            const wrap = document.createElement('div');
            wrap.className = 'diagram-render';

            const card = {
                index: i, sec: sec, wrap: wrap, stage: null,
                dir: 'TD', mode: 'fit',
                scale: 1, tx: 0, ty: 0,      // transform hiện tại của stage
                natural: null, renders: 0, viewBtns: [], zoomLabel: null
            };
            cards.push(card);

            el.appendChild(buildViewBar(card, token, api));
            el.appendChild(wrap);
            bindPanZoom(card);

            const actions = document.createElement('div');
            actions.className = 'card-actions';

            const copyBtn = document.createElement('button');
            copyBtn.textContent = 'Copy mã Mermaid';
            copyBtn.onclick = function () { api.copyText(mermaidFor(card), copyBtn); };
            actions.appendChild(copyBtn);

            const mmdBtn = document.createElement('button');
            mmdBtn.textContent = 'Tải .mmd';
            mmdBtn.onclick = function () {
                api.downloadText(mermaidFor(card) + '\n', safeName(sec.title, i) + '.mmd', 'text/plain');
            };
            actions.appendChild(mmdBtn);

            const pngBtn = document.createElement('button');
            pngBtn.textContent = 'Tải PNG';
            pngBtn.title = 'Ảnh PNG nền trắng, gấp đôi độ phân giải — dán vào slide, Word, chat';
            pngBtn.onclick = function () { downloadPNG(card, safeName(sec.title, i), api); };
            actions.appendChild(pngBtn);

            const svgBtn = document.createElement('button');
            svgBtn.textContent = 'Tải SVG';
            svgBtn.title = 'Ảnh vector, phóng to bao nhiêu cũng nét';
            svgBtn.onclick = function () { downloadSVG(card, safeName(sec.title, i), api); };
            actions.appendChild(svgBtn);

            el.appendChild(actions);

            const note = document.createElement('p');
            note.className = 'card-note';
            note.textContent = 'Sau khi paste vào draw.io, có thể phải set lại Fill/Bold thủ công '
                + '— Mermaid style không phải lúc nào cũng giữ được khi import.';
            el.appendChild(note);

            if (sec.source) {
                const src = document.createElement('p');
                src.className = 'source-line';
                src.textContent = sec.source;
                el.appendChild(src);
            }

            wrapper.appendChild(el);
            await drawCard(card, token, api);
        }

        renderTOC(api);
    }

    // Đổi cỡ cửa sổ thì tính lại các card đang ở chế độ tự vừa khung
    let resizeTimer = null;
    function onResize() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function () {
            cards.forEach(function (c) {
                // khung nhìn phải cao lại theo cửa sổ dù đang ở chế độ nào
                if (c.wrap) c.wrap.style.height = viewportHeight() + 'px';
                if (c.mode === 'fit' || c.mode === 'width') applyScale(c);
            });
        }, 150);
    }

    function safeName(title, i) {
        const base = (title || ('diagram-' + (i + 1)))
            .replace(/[^\wÀ-ỹ\- ]+/g, '')
            .trim().replace(/\s+/g, '_');
        return (base || ('diagram-' + (i + 1))).slice(0, 60);
    }

    /** Chuỗi SVG độc lập: có xmlns, và kích thước ghi cứng theo viewBox. */
    function serializeSVG(card) {
        const svgEl = card.wrap.querySelector('svg');
        if (!svgEl) return null;

        const clone = svgEl.cloneNode(true);
        const nat = card.natural || { w: 800, h: 600 };
        clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
        clone.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');
        clone.setAttribute('width', nat.w);
        clone.setAttribute('height', nat.h);
        clone.style.maxWidth = '';

        return new XMLSerializer().serializeToString(clone);
    }

    function downloadSVG(card, name, api) {
        const source = serializeSVG(card);
        if (!source) { api.toast('Diagram chưa render được, không có SVG để tải', true); return; }
        api.downloadText(source, name + '.svg', 'image/svg+xml');
    }

    /* PNG: vẽ SVG lên canvas rồi xuất. Nhân 2 cho nét trên màn hình retina và
       khi chiếu máy chiếu. Nền trắng đục — PNG nền trong suốt dán vào slide hay
       Word sẽ thành chữ đen trên nền tối, khó đọc. */
    function downloadPNG(card, name, api) {
        const source = serializeSVG(card);
        if (!source) { api.toast('Diagram chưa render được, không có PNG để tải', true); return; }

        const nat = card.natural || { w: 800, h: 600 };
        const scale = 2;
        const img = new Image();

        // dùng data: URI thay vì blob: — Safari chặn canvas.toBlob sau khi nạp blob:
        const url = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(source);

        img.onload = function () {
            const canvas = document.createElement('canvas');
            canvas.width = Math.round(nat.w * scale);
            canvas.height = Math.round(nat.h * scale);

            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

            canvas.toBlob(function (blob) {
                if (!blob) { api.toast('Trình duyệt không xuất được PNG', true); return; }
                const href = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = href;
                a.download = name + '.png';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(href);
                api.toast('Đã tải ' + name + '.png (' + canvas.width + '×' + canvas.height + ')');
            }, 'image/png');
        };

        img.onerror = function () {
            api.toast('Không dựng được ảnh từ SVG — thử nút Tải SVG', true);
        };

        img.src = url;
    }

    function renderInput(text, api) {
        sections = parseInput(text);
        renderAll(api);
    }

    /* ─────────────── dữ liệu ─────────────── */

    async function loadFiles(api) {
        try {
            const r = await api.call('customize_erpnext.api.docs_reader.list_docs',
                { category: CATEGORY });
            files = (r && r.files) || [];
            canEdit = !!(r && r.can_edit);
        } catch (e) {
            files = [];
            api.toast('Không đọc được danh sách file: ' + e.message, true);
        }
        renderFileList(api);
        return files;
    }

    async function openFile(name, api) {
        try {
            const r = await api.call('customize_erpnext.api.docs_reader.get_doc_content',
                { category: CATEGORY, filename: name });
            currentFile = name;
            currentMtime = r.mtime;
            markActiveFile();
            updateSaveState();
            const input = document.getElementById('fc-input');
            if (input) input.value = r.content;
            renderInput(r.content, api);
        } catch (e) {
            api.toast('Không mở được ' + name + ': ' + e.message, true);
        }
    }

    /* ─────────────── vòng đời tab ─────────────── */

    window.DevTool.registerTab({
        id: 'flowchart',
        label: 'Flowchart',
        icon: '⇄',
        order: 20,

        // Kết quả tìm kiếm của khung Dev Tool trỏ tới một file trong docs/flowchart
        openDoc: function (req) {
            if (!req || !req.filename) return;
            Promise.resolve(openFile(req.filename, window.DevTool)).then(function () {
                if (!req.query) return;
                // Sơ đồ không có khái niệm dòng, nên tô chỗ khớp trong ô nguồn
                const input = document.getElementById('fc-input');
                if (!input) return;
                const strip = (t) => String(t || '').replace(/đ/g, 'd').replace(/Đ/g, 'D')
                    .normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
                const at = strip(input.value).indexOf(strip(req.query));
                if (at < 0) return;
                input.focus();
                input.setSelectionRange(at, at + req.query.length);
                const before = input.value.slice(0, at).split('\n').length - 1;
                const lh = parseFloat(getComputedStyle(input).lineHeight) || 18;
                input.scrollTop = Math.max(0, before * lh - input.clientHeight / 2);
            });
        },

        mount: async function (ctx) {
            mainEl = ctx.main;
            const api = ctx.api;

            buildSide(ctx.side, api);
            window.addEventListener('resize', onResize);
            window.addEventListener('mousemove', onPanMove);
            window.addEventListener('mouseup', onPanUp);
            mainEl.innerHTML = '<p class="placeholder">Đang tải…</p>';

            const list = await loadFiles(api);
            if (list.length) {
                await openFile(list[0].name, api);
            } else {
                sections = [];
                renderAll(api);
            }
        },

        unmount: function () {
            renderToken++;      // huỷ vòng render đang chạy dở
            window.removeEventListener('resize', onResize);
            window.removeEventListener('mousemove', onPanMove);
            window.removeEventListener('mouseup', onPanUp);
            clearTimeout(resizeTimer);
            panning = null;
            sections = [];
            cards = [];
            files = [];
            currentFile = null;
            currentMtime = null;
            mainEl = null;
        }
    });
})();
