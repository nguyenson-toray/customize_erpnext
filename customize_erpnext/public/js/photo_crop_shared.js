/**
 * Shared photo crop utilities for employee photos.
 * Used by: employee.js (Frappe form) and employee-photos/index.html (www page)
 */
window.PhotoCropUtils = {
    /**
     * Detect if a PNG image has transparent pixels.
     * Always returns false for non-PNG images.
     * Samples a downscaled version for performance.
     * @param {string} imageDataUrl
     * @returns {Promise<boolean>}
     */
    hasTransparency: function (imageDataUrl) {
        return new Promise(function (resolve) {
            if (!imageDataUrl || !imageDataUrl.startsWith('data:image/png')) {
                resolve(false);
                return;
            }
            var img = new Image();
            img.onload = function () {
                try {
                    var MAX = 300;
                    var ratio = Math.min(MAX / img.width, MAX / img.height, 1);
                    var w = Math.max(1, Math.round(img.width * ratio));
                    var h = Math.max(1, Math.round(img.height * ratio));
                    var canvas = document.createElement('canvas');
                    canvas.width = w;
                    canvas.height = h;
                    var ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, w, h);
                    var data = ctx.getImageData(0, 0, w, h).data;
                    for (var i = 3; i < data.length; i += 4) {
                        if (data[i] < 255) { resolve(true); return; }
                    }
                    resolve(false);
                } catch (e) {
                    resolve(false);
                }
            };
            img.onerror = function () { resolve(false); };
            img.src = imageDataUrl;
        });
    },

    /**
     * Fill transparent (and semi-transparent) pixels on a canvas with a background color.
     * Blends semi-transparent pixels against the background.
     * @param {HTMLCanvasElement} canvas
     * @param {string} color - CSS color string, e.g. '#ffffff'
     */
    fillBackground: function (canvas, color) {
        var ctx = canvas.getContext('2d');
        var imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        var data = imageData.data;

        // Parse CSS color to RGB via a 1x1 canvas
        var tmp = document.createElement('canvas');
        tmp.width = tmp.height = 1;
        var tc = tmp.getContext('2d');
        tc.fillStyle = color || '#ffffff';
        tc.fillRect(0, 0, 1, 1);
        var bg = tc.getImageData(0, 0, 1, 1).data;

        for (var i = 0; i < data.length; i += 4) {
            var alpha = data[i + 3];
            if (alpha < 255) {
                var a = alpha / 255;
                data[i]     = Math.round(data[i]     * a + bg[0] * (1 - a));
                data[i + 1] = Math.round(data[i + 1] * a + bg[1] * (1 - a));
                data[i + 2] = Math.round(data[i + 2] * a + bg[2] * (1 - a));
                data[i + 3] = 255;
            }
        }
        ctx.putImageData(imageData, 0, 0);
    },

    /**
     * HTML snippet for the background color picker row.
     * The element is hidden by default; call show() on it when transparency is detected.
     * @param {string} pickerId - id for the <input type="color"> element
     * @returns {string} HTML string
     */
    bgPickerHTML: function (pickerId) {
        return '<div id="' + pickerId + '-row" style="display:none; margin-top:10px; padding:10px 12px;' +
            ' background:#fff8e1; border:1px solid #ffe082; border-radius:5px;' +
            ' align-items:center; gap:10px; flex-wrap:wrap;">' +
            '<span style="font-size:13px; color:#5d4037;">⚠️ Ảnh PNG có nền trong suốt. Chọn màu nền thay thế:</span>' +
            '<input type="color" id="' + pickerId + '" value="#ffffff"' +
            ' style="width:36px; height:28px; padding:2px; border:1px solid #ccc; border-radius:3px; cursor:pointer;">' +
            '<span style="font-size:12px; color:#888;">(mặc định: trắng)</span>' +
            '</div>';
    }
};
