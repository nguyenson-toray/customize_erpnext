// Job Application Form - Enhanced UI
// Loaded via web_include_js on all web pages.
// Only activates on the job_application web form page.

(function () {
    'use strict';

    if (!window.location.pathname.startsWith('/job_application')) return;

    frappe.ready(function () {
        enhanceFileUpload();
        enhanceValidation();
        scrollToFirstError();
        enhanceSubmitButton();
    });

    function enhanceFileUpload() {
        var fileInputs = document.querySelectorAll('input[type="file"]');
        fileInputs.forEach(function (input) {
            var wrapper = input.closest('.frappe-control');
            if (!wrapper) return;

            var uploadArea = document.createElement('div');
            uploadArea.className = 'file-upload-area';
            uploadArea.innerHTML =
                '<div class="upload-icon">' +
                '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/></svg>' +
                '</div>' +
                '<div class="upload-text">' + __("Click to upload or drag and drop") + '</div>' +
                '<div class="upload-hint">PDF, DOC, DOCX (Max 5MB)</div>';

            input.style.display = 'none';
            input.parentNode.insertBefore(uploadArea, input);

            uploadArea.addEventListener('click', function () { input.click(); });

            input.addEventListener('change', function (e) {
                var file = e.target.files[0];
                if (file) {
                    uploadArea.innerHTML =
                        '<div class="attached-file">' +
                        '<span class="attached-file-link">' + file.name + '</span>' +
                        '<span style="color: var(--ja-text-secondary); font-size: 0.8125rem;">' +
                        (file.size / 1024).toFixed(1) + ' KB</span></div>';
                }
            });

            uploadArea.addEventListener('dragover', function (e) {
                e.preventDefault();
                uploadArea.style.borderColor = 'var(--ja-primary)';
            });
            uploadArea.addEventListener('dragleave', function (e) {
                e.preventDefault();
                uploadArea.style.borderColor = 'var(--ja-border)';
            });
            uploadArea.addEventListener('drop', function (e) {
                e.preventDefault();
                uploadArea.style.borderColor = 'var(--ja-border)';
                if (e.dataTransfer.files.length > 0) {
                    input.files = e.dataTransfer.files;
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });
        });
    }

    function enhanceValidation() {
        document.querySelectorAll('input[type="email"]').forEach(function (input) {
            input.addEventListener('blur', function () {
                var email = input.value.trim();
                if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
                    showFieldError(input, __('Please enter a valid email address'));
                } else {
                    clearFieldError(input);
                }
            });
        });

        document.querySelectorAll('input[type="tel"]').forEach(function (input) {
            input.addEventListener('blur', function () {
                var phone = input.value.trim();
                if (phone && phone.length < 10) {
                    showFieldError(input, __('Please enter a valid phone number'));
                } else {
                    clearFieldError(input);
                }
            });
        });
    }

    function showFieldError(input, message) {
        var wrapper = input.closest('.frappe-control');
        if (!wrapper) return;
        var existing = wrapper.querySelector('.error-message');
        if (existing) existing.remove();
        wrapper.classList.add('has-error');
        var errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.textContent = message;
        input.parentNode.appendChild(errorDiv);
    }

    function clearFieldError(input) {
        var wrapper = input.closest('.frappe-control');
        if (!wrapper) return;
        wrapper.classList.remove('has-error');
        var errorMsg = wrapper.querySelector('.error-message');
        if (errorMsg) errorMsg.remove();
    }

    function scrollToFirstError() {
        var form = document.querySelector('.web-form form');
        if (!form) return;
        form.addEventListener('submit', function () {
            setTimeout(function () {
                var firstError = document.querySelector('.has-error, .invalid-feedback');
                if (firstError) {
                    firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            }, 100);
        });
    }

    function enhanceSubmitButton() {
        var submitBtn = document.querySelector('.web-form button[type="submit"], .web-form .btn-primary-dark');
        if (!submitBtn) return;
        var form = document.querySelector('.web-form form');
        if (!form) return;

        form.addEventListener('submit', function () {
            submitBtn.disabled = true;
            submitBtn.classList.add('disabled');
            var originalText = submitBtn.textContent;
            submitBtn.innerHTML =
                '<span style="display: inline-flex; align-items: center; gap: 0.5rem;">' +
                '<span class="ja-spinner"></span>' +
                __('Submitting...') + '</span>';

            if (!document.querySelector('#ja-spinner-style')) {
                var style = document.createElement('style');
                style.id = 'ja-spinner-style';
                style.textContent = '.ja-spinner{display:inline-block;width:16px;height:16px;border:2px solid white;border-top-color:transparent;border-radius:50%;animation:ja-spin .6s linear infinite}@keyframes ja-spin{to{transform:rotate(360deg)}}';
                document.head.appendChild(style);
            }

            setTimeout(function () {
                submitBtn.disabled = false;
                submitBtn.classList.remove('disabled');
                submitBtn.textContent = originalText;
            }, 10000);
        });
    }
})();
