// Tab xem trước thẻ nhân viên: HTML sửa được (contenteditable) + thanh chỉnh cỡ chữ + nút In.
// Cùng nội dung với open_employee_cards_html_tab() trong employee_list.js (Desk) — dùng ở trang /employee-photos.
// open() phải gọi ngay trong lúc người dùng bấm (trước khi chờ server) để trình duyệt không chặn popup.
(function () {
    const INJECT = `
<style>
    #ec-toolbar {
        position: fixed;
        top: 0; left: 0; right: 0;
        z-index: 9999;
        background: #f8f9fa;
        border-bottom: 1px solid #dee2e6;
        padding: 6px 16px;
        display: flex;
        align-items: center;
        gap: 10px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        font-size: 13px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }
    #ec-toolbar .tb-title {
        font-weight: 600;
        color: #343a40;
    }
    #ec-toolbar .tb-sep {
        color: #ced4da;
        font-size: 18px;
        line-height: 1;
    }
    #ec-toolbar label { color: #495057; }
    #ec-fs {
        width: 54px;
        padding: 3px 6px;
        border: 1px solid #ced4da;
        border-radius: 4px;
        font-size: 13px;
        text-align: center;
    }
    #ec-fs-hint { color: #6c757d; font-size: 12px; }
    #ec-btn-apply {
        padding: 4px 14px;
        background: #0d6efd;
        color: #fff;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 13px;
    }
    #ec-btn-apply:hover { background: #0b5ed7; }
    #ec-msg {
        color: #dc3545;
        font-size: 12px;
        display: none;
    }
    #ec-btn-print {
        padding: 4px 16px;
        background: #198754;
        color: #fff;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 13px;
    }
    #ec-btn-print:hover { background: #146c43; }
    @media screen { body { padding-top: 44px; } }
    @media print {
        #ec-toolbar { display: none !important; }
        body { padding-top: 0 !important; margin: 0 !important; }
    }
</style>
<div id="ec-toolbar">
    <span class="tb-title">Employee Cards Preview</span>
    <span class="tb-sep">|</span>
    <label for="ec-fs">Font size:</label>
    <input id="ec-fs" type="number" value="18" min="6" max="72">
    <span style="color:#495057">pt</span>
    <button id="ec-btn-apply" onmousedown="event.preventDefault()" onclick="applyFS()">Apply</button>
    <span id="ec-msg">Select text first</span>
    <span class="tb-sep">|</span>
    <span id="ec-fs-hint">Select text, set size, click Apply (or Enter)</span>
    <span style="flex:1"></span>
    <button id="ec-btn-print" onclick="window.print()">Print</button>
</div>
<script>
function applyFS() {
    var pt = parseInt(document.getElementById('ec-fs').value, 10);
    var msg = document.getElementById('ec-msg');
    if (!pt || pt < 1) return;
    var sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) {
        msg.style.display = 'inline';
        setTimeout(function() { msg.style.display = 'none'; }, 2500);
        return;
    }
    msg.style.display = 'none';
    var range = sel.getRangeAt(0);
    // Flatten existing font-size spans inside selection to avoid nesting conflicts
    var frag = range.extractContents();
    var tmp = document.createElement('div');
    tmp.appendChild(frag);
    tmp.querySelectorAll('span[style]').forEach(function(s) {
        s.style.fontSize = '';
        if (!s.getAttribute('style')) s.removeAttribute('style');
    });
    var span = document.createElement('span');
    span.style.fontSize = pt + 'pt';
    while (tmp.firstChild) span.appendChild(tmp.firstChild);
    range.insertNode(span);
    sel.removeAllRanges();
    var newRange = document.createRange();
    newRange.selectNodeContents(span);
    sel.addRange(newRange);
}
document.getElementById('ec-fs').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') { e.preventDefault(); applyFS(); }
});
</script>`;

    function open() {
        const tab = window.open('', '_blank');
        if (tab) {
            tab.document.write('<title>Thẻ nhân viên</title><p style="font:14px sans-serif;padding:24px;color:#555">Đang tạo thẻ nhân viên…</p>');
        }
        return tab;
    }

    function write(tab, html) {
        const editable = html.replace(/<body([^>]*)>/, (_m, attrs) => `<body${attrs} contenteditable="true">${INJECT}`);
        tab.document.open();
        tab.document.write(editable);
        tab.document.close();
    }

    window.EmployeeCardsPreview = { open, write };
})();
