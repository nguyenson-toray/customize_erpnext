/**
 * Shared photo processing utilities for employee photos.
 * Used by: index.html (batch processing) and photo_editor.html (single editor)
 */
(function () {
    'use strict';

    // ── Internal helpers ──
    function _cv(v) { return Math.max(0, Math.min(255, Math.round(v))); }
    function _clampV(mn, mx, v) { return Math.max(mn, Math.min(mx, v)); }

    function _boxBlur(data, w, h, r) {
        const t = new Uint8ClampedArray(data.length), o = new Uint8ClampedArray(data.length);
        for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
            let sr = 0, sg = 0, sb = 0, c = 0;
            for (let dx = -r; dx <= r; dx++) { const nx = Math.max(0, Math.min(w - 1, x + dx)), idx = (y * w + nx) * 4; sr += data[idx]; sg += data[idx + 1]; sb += data[idx + 2]; c++; }
            const i = (y * w + x) * 4; t[i] = sr / c; t[i + 1] = sg / c; t[i + 2] = sb / c; t[i + 3] = data[i + 3];
        }
        for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
            let sr = 0, sg = 0, sb = 0, c = 0;
            for (let dy = -r; dy <= r; dy++) { const ny = Math.max(0, Math.min(h - 1, y + dy)), idx = (ny * w + x) * 4; sr += t[idx]; sg += t[idx + 1]; sb += t[idx + 2]; c++; }
            const i = (y * w + x) * 4; o[i] = sr / c; o[i + 1] = sg / c; o[i + 2] = sb / c; o[i + 3] = data[i + 3];
        }
        return o;
    }

    window.PhotoProcessingUtils = {

        /**
         * Detect if a pixel is likely skin tone (YCbCr + RGB heuristic).
         */
        isSkin(r, g, b) {
            if (r < 40) return false;
            const Y = 0.299 * r + 0.587 * g + 0.114 * b;
            const Cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b;
            const Cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b;
            const ycc = Y > 50 && Cb >= 74 && Cb <= 132 && Cr >= 128 && Cr <= 180;
            const rgb = r > 95 && g > 40 && b > 20 && r > g && r > b && (r - Math.min(g, b)) > 15 && Math.abs(r - g) > 10;
            return ycc || rgb;
        },

        /**
         * Frequency separation skin smooth + micro-brightening.
         * @param {ImageData} id
         * @param {number} level
         * @returns {ImageData}
         */
        skinSmooth(id, level) {
            const w = id.width, h = id.height, src = id.data;
            const r2 = Math.min(Math.ceil(level * 0.5), 4), str = level / 18;
            const blur = _boxBlur(src, w, h, r2);
            const out = new Uint8ClampedArray(src);
            const skinLift = Math.round(level * 0.3);
            for (let i = 0; i < src.length; i += 4) {
                if (src[i + 3] < 10) continue;
                if (this.isSkin(src[i], src[i + 1], src[i + 2])) {
                    const nr = _cv(blur[i] * str + src[i] * (1 - str) + (src[i] - blur[i]) * 0.18);
                    const ng = _cv(blur[i + 1] * str + src[i + 1] * (1 - str) + (src[i + 1] - blur[i + 1]) * 0.18);
                    const nb = _cv(blur[i + 2] * str + src[i + 2] * (1 - str) + (src[i + 2] - blur[i + 2]) * 0.18);
                    out[i] = _cv(nr + skinLift * 0.8); out[i + 1] = _cv(ng + skinLift * 0.6); out[i + 2] = _cv(nb + skinLift * 0.4);
                }
            }
            return new ImageData(out, w, h);
        },

        /**
         * Shadows/highlights adjustment via luminance mask.
         * @param {ImageData} id
         * @param {number} shadowBoost
         * @param {number} highlightBoost
         * @returns {ImageData}
         */
        shadowsHighlights(id, shadowBoost, highlightBoost) {
            const d = id.data, out = new Uint8ClampedArray(d);
            for (let i = 0; i < d.length; i += 4) {
                if (d[i + 3] < 10) { out[i] = d[i]; out[i + 1] = d[i + 1]; out[i + 2] = d[i + 2]; out[i + 3] = d[i + 3]; continue; }
                let r = d[i], g = d[i + 1], b = d[i + 2];
                const L = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
                const sMask = Math.pow(Math.max(0, 1 - L * 2), 1.5);
                const hMask = Math.pow(Math.max(0, (L - 0.5) * 2), 1.5);
                const adj = sMask * (shadowBoost / 100) * 80 - hMask * (highlightBoost / 100) * 80;
                out[i] = _cv(r + adj); out[i + 1] = _cv(g + adj); out[i + 2] = _cv(b + adj); out[i + 3] = d[i + 3];
            }
            return new ImageData(out, id.width, id.height);
        },

        /**
         * Unsharp mask sharpening.
         * @param {ImageData} id
         * @param {number} level
         * @returns {ImageData}
         */
        unsharpMask(id, level) {
            const w = id.width, h = id.height, src = id.data;
            const blur = _boxBlur(src, w, h, 1);
            const out = new Uint8ClampedArray(src); const amt = level * 0.16;
            for (let i = 0; i < src.length; i += 4) {
                out[i] = _cv(src[i] + amt * (src[i] - blur[i]));
                out[i + 1] = _cv(src[i + 1] + amt * (src[i + 1] - blur[i + 1]));
                out[i + 2] = _cv(src[i + 2] + amt * (src[i + 2] - blur[i + 2]));
                out[i + 3] = src[i + 3];
            }
            return new ImageData(out, w, h);
        },

        /**
         * Deep image analysis for portrait enhancement.
         * Returns parameters suitable for applyFilters().
         * @param {ImageData} imageData
         * @returns {Object} params
         */
        analyzeDeep(imageData) {
            const d = imageData.data, W = imageData.width, H = imageData.height;
            const fX0 = Math.floor(W * 0.25), fX1 = Math.floor(W * 0.75);
            const fY0 = Math.floor(H * 0.08), fY1 = Math.floor(H * 0.62);
            const sX0 = Math.floor(W * 0.20), sX1 = Math.floor(W * 0.80);
            const sY0 = Math.floor(H * 0.05), sY1 = Math.floor(H * 0.80);
            let histFace = new Array(256).fill(0), faceOp = 0, allOp = 0;
            let skinN = 0, skinLums = [], faceHighN = 0, faceShadN = 0;
            for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
                const i = (y * W + x) * 4;
                const r = d[i], g = d[i + 1], b = d[i + 2], a = d[i + 3];
                if (a < 80) continue;
                const lumV = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
                allOp++;
                const inFace = (x >= fX0 && x <= fX1 && y >= fY0 && y <= fY1);
                if (inFace) { histFace[lumV]++; faceOp++; if (lumV > 215) faceHighN++; if (lumV < 55) faceShadN++; }
                if (x >= sX0 && x <= sX1 && y >= sY0 && y <= sY1 && this.isSkin(r, g, b)) {
                    skinN++; if (skinLums.length < 10000) skinLums.push(lumV);
                }
            }
            if (allOp === 0) return { brightness: 5, contrast: 5, saturation: 3, smooth: 3, sharpness: 3, warmth: 0, highlights: 0, shadows: 0, _skin: 0, _lum: 128 };
            const H2 = faceOp > 100 ? histFace : new Array(256).fill(0);
            const HOp = faceOp > 100 ? faceOp : 1;
            let skinMeanLum = skinLums.length > 80 ? skinLums.reduce((a, b) => a + b, 0) / skinLums.length : 128;
            const meanLum = skinMeanLum;
            let cum = 0, p5 = 0, p95 = 240;
            for (let i = 0; i < 256; i++) { cum += H2[i]; if (cum / HOp >= 0.05 && p5 === 0) p5 = i; if (cum / HOp >= 0.95) { p95 = i; break; } }
            const range = p95 - p5;
            let brightness = 0;
            if (meanLum < 60) brightness = Math.round((120 - meanLum) * 0.70);
            else if (meanLum < 90) brightness = Math.round((125 - meanLum) * 0.58);
            else if (meanLum < 110) brightness = Math.round((125 - meanLum) * 0.42);
            else if (meanLum < 125) brightness = Math.round((128 - meanLum) * 0.28);
            else if (meanLum <= 190) brightness = 3;
            else if (meanLum <= 210) brightness = Math.round((195 - meanLum) * 0.25);
            else brightness = Math.round((200 - meanLum) * 0.35);
            brightness = _clampV(-15, 40, brightness);
            let contrast = 0;
            if (range < 80) contrast = Math.round((155 - range) / 4.2);
            else if (range < 120) contrast = Math.round((152 - range) / 5.0);
            else if (range < 155) contrast = Math.round((150 - range) / 7.0);
            else if (range > 230) contrast = -Math.round((range - 230) / 12);
            contrast = _clampV(-8, 20, contrast);
            const faceHighRatio = faceHighN / Math.max(faceOp, 1);
            const faceShadRatio = faceShadN / Math.max(faceOp, 1);
            const highlights = faceHighRatio > 0.15 ? -Math.round(faceHighRatio * 50) : faceHighRatio > 0.08 ? -Math.round(faceHighRatio * 30) : 0;
            const shadows = faceShadRatio > 0.18 ? Math.round(faceShadRatio * 30) : faceShadRatio > 0.08 ? Math.round(faceShadRatio * 18) : 0;
            const skinRatio = skinN / allOp;
            let smooth = 0;
            if (skinLums.length > 50) {
                const sMean = skinLums.reduce((a, b) => a + b, 0) / skinLums.length;
                const sStd = Math.sqrt(skinLums.reduce((s, v) => s + (v - sMean) ** 2, 0) / skinLums.length);
                if (sStd > 22) smooth = Math.round(3 + (sStd - 22) * 0.18);
                else if (sStd > 14) smooth = Math.round(1 + (sStd - 14) * 0.18);
                else if (sStd > 8) smooth = 1;
                if (skinRatio > 0.04) smooth = Math.max(smooth, 2); else if (skinRatio > 0.02) smooth = Math.max(smooth, 1);
                smooth = _clampV(0, 4, smooth);
            } else if (skinN > 50) { smooth = 1; }
            return {
                brightness, contrast, saturation: 3, smooth, sharpness: 3, warmth: 0, highlights, shadows,
                _skin: Math.round(skinRatio * 100), _lum: Math.round(skinMeanLum)
            };
        },

        /**
         * Apply filter pipeline to ImageData (no vignette — add separately for editor).
         * @param {ImageData} imageData - source (will not be mutated)
         * @param {Object} params - {brightness, contrast, saturation, smooth, sharpness, warmth, highlights, shadows}
         * @returns {ImageData}
         */
        applyFilters(imageData, params) {
            const B = params.brightness || 0, C = params.contrast || 0;
            const S = params.saturation || 0, Sm = params.smooth || 0;
            const Sh = params.sharpness || 0, W2 = params.warmth || 0;
            const Hi = params.highlights || 0, Sh2 = params.shadows || 0;
            let id = new ImageData(new Uint8ClampedArray(imageData.data), imageData.width, imageData.height);
            if (Sm > 0) id = this.skinSmooth(id, Sm);
            if (Hi !== 0 || Sh2 !== 0) id = this.shadowsHighlights(id, Sh2, Hi);
            const dd = id.data;
            for (let i = 0; i < dd.length; i += 4) {
                if (dd[i + 3] < 10) continue;
                let r = dd[i], g = dd[i + 1], b = dd[i + 2];
                if (W2 !== 0) { r = _cv(r + W2 * 1.6); b = _cv(b - W2 * 1.1); g = _cv(g + W2 * 0.1); }
                const bf = B / 100;
                if (bf > 0) { r = _cv(r + (255 - r) * bf * 0.85); g = _cv(g + (255 - g) * bf * 0.85); b = _cv(b + (255 - b) * bf * 0.85); }
                else { r = _cv(r * (1 + bf)); g = _cv(g * (1 + bf)); b = _cv(b * (1 + bf)); }
                const cf = Math.pow((C + 100) / 100, 1.1);
                r = _cv(((r / 255 - 0.45) * cf + 0.45) * 255);
                g = _cv(((g / 255 - 0.45) * cf + 0.45) * 255);
                b = _cv(((b / 255 - 0.45) * cf + 0.45) * 255);
                const lumP = 0.299 * r + 0.587 * g + 0.114 * b;
                const sf = (S + 100) / 100;
                r = _cv(lumP + (r - lumP) * sf); g = _cv(lumP + (g - lumP) * sf); b = _cv(lumP + (b - lumP) * sf);
                dd[i] = r; dd[i + 1] = g; dd[i + 2] = b;
            }
            if (Sh > 0) id = this.unsharpMask(id, Sh);
            return id;
        },

        /**
         * Detect if image has a white/near-white background.
         * Samples 8 points: 4 corners + 4 edge midpoints.
         * @param {ImageData} imageData
         * @param {number} [threshold=240]
         * @returns {boolean}
         */
        isWhiteBackground(imageData, threshold) {
            const thr = threshold !== undefined ? threshold : 240;
            const d = imageData.data, w = imageData.width, h = imageData.height;
            const points = [
                [0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1],
                [Math.floor(w / 2), 0], [Math.floor(w / 2), h - 1],
                [0, Math.floor(h / 2)], [w - 1, Math.floor(h / 2)]
            ];
            for (const [x, y] of points) {
                const i = (y * w + x) * 4;
                if (d[i] < thr || d[i + 1] < thr || d[i + 2] < thr) return false;
            }
            return true;
        }
    };
})();
