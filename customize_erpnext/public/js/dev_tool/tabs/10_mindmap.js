/* Dev Tool — tab Mindmap.
 *
 * Trang /mindmap là một bản dựng SVG riêng ~2.500 dòng (không dùng thư viện
 * ngoài) kèm sửa/lưu file, dịch EN-VI, in ấn. Nhúng nguyên trang đó vào khung
 * tab thay vì chép logic sang đây: chép lại là tạo bản thứ hai phải sửa song
 * song mỗi lần đổi, đúng kiểu lỗi mà skill flowchart-sync sinh ra để tránh.
 *
 * Phần đổi thật nằm ở backend: /mindmap giờ đọc file trong docs/mindmap qua
 * api/docs_reader.py (mindmap_docs.py gọi sang), chung một luật đường dẫn với
 * tab Flowchart.
 */
(function () {
    'use strict';

    const PAGE_URL = '/mindmap';

    let frame = null;
    let collapsedByUs = false;

    window.DevTool.registerTab({
        id: 'mindmap',
        label: 'Mindmap',
        icon: '◈',
        order: 10,

        mount: function (ctx) {
            // Tab này dùng trọn chiều ngang: panel trái để trống, sidebar riêng
            // của trang mindmap nằm sẵn bên trong iframe.
            ctx.side.innerHTML = '';

            ctx.main.innerHTML = '';
            ctx.main.style.overflow = 'hidden';

            frame = document.createElement('iframe');
            frame.src = PAGE_URL;
            frame.title = 'Mindmap';
            frame.style.cssText = 'width:100%;height:100%;border:0;display:block;';
            ctx.main.appendChild(frame);
        },

        // Trình chiếu: gập luôn ô soạn thảo bên trong trang mindmap. iframe cùng
        // origin nên bấm thẳng nút của trang đó, dùng chính logic nó có sẵn thay
        // vì tự gán class (nút còn gọi fit() vẽ lại cho vừa khung).
        onPresent: function (on) {
            const doc = frame && frame.contentDocument;
            const btn = doc && doc.getElementById('btn-toggle-editor');
            if (!btn) return;

            const hidden = doc.body.classList.contains('no-editor');
            if (on && !hidden) {
                btn.click();
                collapsedByUs = true;
            } else if (!on && hidden && collapsedByUs) {
                // chỉ mở lại nếu chính mình gập; người dùng tự gập thì tôn trọng
                btn.click();
                collapsedByUs = false;
            }
        },

        unmount: function () {
            // Gỡ src trước khi DOM bị xoá để trình duyệt dừng hẳn trang bên trong
            if (frame) { frame.src = 'about:blank'; frame = null; }
            collapsedByUs = false;
            const main = document.getElementById('tab-main');
            if (main) main.style.overflow = '';
        }
    });
})();
