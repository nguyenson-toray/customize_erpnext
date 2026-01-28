/**
 * Debug script to check Employee form customization
 * This will help identify why buttons are not showing
 */

console.log('🔍 DEBUG: Employee form customization loaded');

// Check if we're on an Employee form
if (window.location.pathname.includes('/app/employee/')) {
    console.log('📋 DEBUG: On Employee form page');
    console.log('🔗 URL:', window.location.href);
    
    // Check FingerprintScannerDialog availability
    setTimeout(() => {
        console.log('🧩 FingerprintScannerDialog available:', !!window.FingerprintScannerDialog);
        if (window.FingerprintScannerDialog) {
            console.log('📦 FingerprintScannerDialog methods:', Object.keys(window.FingerprintScannerDialog));
        }
        
        // Check if frappe form is available
        console.log('📝 Frappe cur_frm available:', !!frappe.cur_frm);
        if (frappe.cur_frm) {
            console.log('📄 Current form doctype:', frappe.cur_frm.doctype);
            console.log('🆔 Current form name:', frappe.cur_frm.doc.name);
            console.log('🆕 Is new record:', frappe.cur_frm.is_new());
            
            // Check for custom buttons
            const customButtons = frappe.cur_frm.custom_buttons;
            console.log('🔘 Custom buttons:', customButtons);
            
            // Check Actions menu
            const actionsMenu = frappe.cur_frm.page.btn_secondary;
            console.log('⚙️ Actions menu:', actionsMenu);
        }
    }, 2000);
}