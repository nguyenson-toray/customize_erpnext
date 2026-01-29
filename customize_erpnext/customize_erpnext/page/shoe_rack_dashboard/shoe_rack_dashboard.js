frappe.pages['shoe-rack-dashboard'].on_page_load = function(wrapper) {
    // Tạo root element
    wrapper.innerHTML = '<div id="shoe-rack-react-root"></div>';
    
    const basePath = '/assets/customize_erpnext/static';
    
    // Load CSS (tên file cố định)
    if (!document.querySelector(`link[href="${basePath}/css/main.css"]`)) {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = `${basePath}/css/main.css`;
        document.head.appendChild(link);
    }
    
    // Load JS (tên file cố định)
    if (!document.querySelector(`script[src="${basePath}/js/main.js"]`)) {
        const script = document.createElement('script');
        script.src = `${basePath}/js/main.js`;
        document.body.appendChild(script);
    }
};