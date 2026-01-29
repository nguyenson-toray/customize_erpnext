// Copyright (c) 2025, IT Team - TIQN and contributors
// layout_manager.js
// Path: customize_erpnext/page/layout_manager/layout_manager.js

frappe.pages['layout-manager'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Shoe Rack Layout Manager',
        single_column: true
    });
    
    new ShoeRackLayoutManager(page);
}

class ShoeRackLayoutManager {
    constructor(page) {
        this.page = page;
        this.wrapper = $(page.body);
        this.rows = [];
        this.draggedBlock = null;
        this.draggedFrom = null;
        
        this.setup_page();
        this.load_layout();
    }
    
    setup_page() {
        // Add action buttons
        this.page.add_inner_button(__('Add Row'), () => this.show_add_row_dialog());
        this.page.add_inner_button(__('Save Layout'), () => this.save_layout());
        this.page.add_inner_button(__('Refresh'), () => this.load_layout());
        this.page.add_inner_button(__('Export JSON'), () => this.export_json());
        
        // Setup HTML wrapper with styles
        this.wrapper.html(this.get_html_template());
    }
    
    get_html_template() {
        return `
            <div class="layout-manager-container">
                <style>
                    .layout-manager-container {
                        padding: 20px;
                        background: #f5f7fa;
                        min-height: calc(100vh - 120px);
                    }
                    
                    .stats-bar {
                        display: flex;
                        gap: 15px;
                        margin-bottom: 30px;
                        flex-wrap: wrap;
                    }
                    
                    .stat-card {
                        flex: 1;
                        min-width: 140px;
                        padding: 20px;
                        background: white;
                        border-radius: 10px;
                        border: 1px solid #e3e8ef;
                        text-align: center;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                        transition: all 0.2s;
                    }
                    
                    .stat-card:hover {
                        transform: translateY(-2px);
                        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                    }
                    
                    .stat-value {
                        font-size: 28px;
                        font-weight: bold;
                        color: #667eea;
                        margin-bottom: 5px;
                    }
                    
                    .stat-label {
                        font-size: 12px;
                        color: #6c757d;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                    }
                    
                    .row-section {
                        background: white;
                        border-radius: 12px;
                        padding: 20px;
                        margin-bottom: 24px;
                        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                    }
                    
                    .row-header {
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-bottom: 20px;
                        padding: 15px 20px;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        border-radius: 10px;
                    }
                    
                    .row-header-left {
                        display: flex;
                        align-items: center;
                        gap: 12px;
                    }
                    
                    .row-title {
                        font-size: 18px;
                        font-weight: 600;
                    }
                    
                    .row-info {
                        font-size: 13px;
                        background: rgba(255,255,255,0.25);
                        padding: 5px 12px;
                        border-radius: 15px;
                    }
                    
                    .row-actions {
                        display: flex;
                        gap: 8px;
                    }
                    
                    .row-actions .btn {
                        padding: 6px 14px;
                        font-size: 12px;
                        border-radius: 6px;
                    }
                    
                    .blocks-grid {
                        display: grid;
                        gap: 14px;
                    }
                    
                    .block-cell {
                        border: 3px dashed #d1d5db;
                        border-radius: 12px;
                        background: #f9fafb;
                        min-height: 200px;
                        display: flex;
                        flex-direction: column;
                        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                        position: relative;
                        overflow: hidden;
                    }
                    
                    .block-cell.filled {
                        border-color: #667eea;
                        border-style: solid;
                        background: linear-gradient(135deg, #f0f2ff 0%, #faf5ff 100%);
                        cursor: move;
                    }
                    
                    .block-cell.filled:hover {
                        transform: translateY(-6px) scale(1.02);
                        box-shadow: 0 12px 24px rgba(102, 126, 234, 0.3);
                        z-index: 10;
                    }
                    
                    .block-cell.empty {
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    }
                    
                    .block-cell.drag-over {
                        background: #e0e7ff;
                        border-color: #4f46e5;
                        border-style: solid;
                    }
                    
                    .add-block-btn {
                        width: 52px;
                        height: 52px;
                        border: none;
                        border-radius: 50%;
                        background: linear-gradient(135deg, #e5e7eb 0%, #d1d5db 100%);
                        color: #6b7280;
                        cursor: pointer;
                        font-size: 28px;
                        transition: all 0.3s;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    }
                    
                    .add-block-btn:hover {
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        transform: scale(1.15) rotate(90deg);
                    }
                    
                    .block-header {
                        display: flex;
                        align-items: center;
                        gap: 10px;
                        padding: 12px;
                        background: rgba(102, 126, 234, 0.12);
                        border-bottom: 2px solid rgba(102, 126, 234, 0.25);
                    }
                    
                    .drag-handle {
                        cursor: move;
                        color: #667eea;
                        font-size: 20px;
                        font-weight: bold;
                        line-height: 1;
                        opacity: 0.7;
                        transition: opacity 0.2s;
                    }
                    
                    .drag-handle:hover {
                        opacity: 1;
                    }
                    
                    .block-name {
                        flex: 1;
                        font-size: 14px;
                        font-weight: 600;
                        color: #667eea;
                    }
                    
                    .block-actions {
                        display: flex;
                        gap: 5px;
                    }
                    
                    .block-btn {
                        padding: 5px 10px;
                        border: none;
                        border-radius: 5px;
                        font-size: 11px;
                        font-weight: 500;
                        cursor: pointer;
                        transition: all 0.2s;
                    }
                    
                    .btn-view {
                        background: rgba(102, 126, 234, 0.15);
                        color: #667eea;
                    }
                    
                    .btn-view:hover {
                        background: #667eea;
                        color: white;
                    }
                    
                    .btn-remove {
                        background: rgba(220, 38, 38, 0.12);
                        color: #dc2626;
                    }
                    
                    .btn-remove:hover {
                        background: #dc2626;
                        color: white;
                    }
                    
                    .mini-rack-grid {
                        display: grid;
                        grid-template-columns: repeat(4, 1fr);
                        gap: 5px;
                        padding: 12px;
                        flex: 1;
                    }
                    
                    .mini-rack {
                        aspect-ratio: 1;
                        border-radius: 8px;
                        border: 2px solid #d1d5db;
                        transition: transform 0.2s;
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                        justify-content: center;
                        padding: 4px;
                        font-size: 10px;
                        position: relative;
                        cursor: pointer;
                    }
                    
                    .mini-rack:hover {
                        transform: scale(1.08);
                        z-index: 5;
                        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
                    }
                    
                    .mini-rack.status-empty {
                        background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
                        border-color: #28a745;
                    }
                    
                    .mini-rack.status-partial {
                        background: linear-gradient(135deg, #fff3cd 0%, #ffeeba 100%);
                        border-color: #ffc107;
                    }
                    
                    .mini-rack.status-full {
                        background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%);
                        border-color: #dc3545;
                    }
                    
                    .rack-label {
                        font-weight: bold;
                        font-size: 11px;
                        color: #1a1a1a;
                        margin-bottom: 2px;
                    }
                    
                    .rack-status {
                        font-size: 9px;
                        color: #4b5563;
                        margin-bottom: 2px;
                    }
                    
                    .rack-icons {
                        font-size: 10px;
                        opacity: 0.7;
                    }
                    
                    .block-stats {
                        padding: 10px 12px;
                        font-size: 11px;
                        color: #6b7280;
                        text-align: center;
                        border-top: 1px solid rgba(102, 126, 234, 0.2);
                        background: rgba(102, 126, 234, 0.05);
                        font-weight: 500;
                    }
                    
                    .empty-state {
                        text-align: center;
                        padding: 60px 20px;
                        color: #6c757d;
                    }
                    
                    .empty-state-icon {
                        font-size: 64px;
                        margin-bottom: 20px;
                        opacity: 0.3;
                    }
                    
                    .empty-state-text {
                        font-size: 16px;
                        margin-bottom: 10px;
                    }
                    
                    .empty-state-hint {
                        font-size: 13px;
                        color: #9ca3af;
                    }
                </style>
                
                <div class="stats-bar"></div>
                <div class="rows-container"></div>
            </div>
        `;
    }
    
    render() {
        this.render_stats();
        this.render_rows();
    }
    
    render_stats() {
        const total_rows = this.rows.length;
        const total_blocks = this.rows.reduce((sum, row) => 
            sum + row.blocks.filter(b => b !== null).length, 0
        );
        const total_slots = this.rows.reduce((sum, row) => sum + row.blocks.length, 0);
        const empty_slots = total_slots - total_blocks;
        
        const stats_html = `
            <div class="stat-card">
                <div class="stat-value">${total_rows}</div>
                <div class="stat-label">Total Rows</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${total_blocks}</div>
                <div class="stat-label">Total Blocks</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${empty_slots}</div>
                <div class="stat-label">Empty Slots</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${total_slots}</div>
                <div class="stat-label">Total Slots</div>
            </div>
        `;
        
        this.wrapper.find('.stats-bar').html(stats_html);
    }
    
    render_rows() {
        const container = this.wrapper.find('.rows-container');
        container.empty();
        
        if (this.rows.length === 0) {
            container.html(`
                <div class="empty-state">
                    <div class="empty-state-icon">📦</div>
                    <div class="empty-state-text">No rows configured yet</div>
                    <div class="empty-state-hint">Click "Add Row" button to create your first row</div>
                </div>
            `);
            return;
        }
        
        this.rows.forEach((row, rowIndex) => {
            const row_html = this.get_row_html(row, rowIndex);
            container.append(row_html);
            this.bind_row_events(rowIndex);
        });
    }
    
    get_row_html(row, rowIndex) {
        const blocks_html = row.blocks.map((block, blockIndex) => {
            if (block === null) {
                return `
                    <div class="block-cell empty" 
                         data-row="${rowIndex}" 
                         data-block="${blockIndex}">
                        <button class="add-block-btn">+</button>
                    </div>
                `;
            }
            
            const racks_html = this.get_racks_preview(block);
            
            return `
                <div class="block-cell filled" 
                     draggable="true"
                     data-row="${rowIndex}" 
                     data-block="${blockIndex}">
                    <div class="block-header">
                        <span class="drag-handle">⋮⋮</span>
                        <span class="block-name">${block.name}</span>
                        <div class="block-actions">
                            <button class="block-btn btn-view" data-action="view">👁 View</button>
                            <button class="block-btn btn-remove" data-action="remove">✕</button>
                        </div>
                    </div>
                    ${racks_html}
                    <div class="block-stats">
                        📍 ${block.start_rack} → ${block.end_rack}
                    </div>
                </div>
            `;
        }).join('');
        
        const filled_count = row.blocks.filter(b => b !== null).length;
        const total_count = row.blocks.length;
        
        return `
            <div class="row-section" data-row-index="${rowIndex}">
                <div class="row-header">
                    <div class="row-header-left">
                        <span class="row-title">${row.name}</span>
                        <span class="row-info">${row.cols} × ${row.row_count} | ${filled_count}/${total_count} filled</span>
                    </div>
                    <div class="row-actions">
                        <button class="btn btn-sm btn-secondary" onclick="layout_manager.edit_row(${rowIndex})">
                            ✏️ Edit
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="layout_manager.delete_row(${rowIndex})">
                            🗑️ Delete
                        </button>
                    </div>
                </div>
                <div class="blocks-grid" style="grid-template-columns: repeat(${row.cols}, 1fr)">
                    ${blocks_html}
                </div>
            </div>
        `;
    }
    
    get_racks_preview(block) {
        // Display detailed rack information in 4×4 grid
        // Shows: Rack Name, Status (0/2, 1/2, 2/2), Gender & User Type icons
        
        let html = '<div class="mini-rack-grid">';
        
        // Extract series prefix and start number
        const match = block.start_rack.match(/^([A-Z]+)-(\d+)$/);
        if (!match) {
            // Fallback for invalid format
            for (let i = 0; i < 16; i++) {
                html += `<div class="mini-rack status-empty">
                    <div class="rack-label">?</div>
                    <div class="rack-status">0/2</div>
                </div>`;
            }
            html += '</div>';
            return html;
        }
        
        const prefix = match[1];
        const startNum = parseInt(match[2]);
        
        // Generate 16 racks (4×4 grid)
        for (let i = 0; i < 16; i++) {
            const rackNum = startNum + i;
            
            // Display format: "A1", "G5", "J12", or just number for RACK series
            let displayName;
            if (prefix === 'RACK') {
                displayName = String(rackNum);
            } else {
                displayName = `${prefix}${rackNum}`;
            }
            
            // TODO: Fetch real data from server
            // For now, generate realistic mock data
            const statuses = ['0/2', '1/2', '2/2', '0/2', '0/2']; // More empty slots
            const status = statuses[Math.floor(Math.random() * statuses.length)];
            const statusClass = status === '0/2' ? 'status-empty' : 
                              status === '1/2' ? 'status-partial' : 'status-full';
            
            // Gender icons: ♂ (Male), ♀ (Female)
            const genders = ['♂', '♀'];
            const gender = genders[i % 2]; // Alternate for demo
            
            // User type icons: 👤 (Employee), 👥 (External)
            const userTypes = ['👤', '👥'];
            const userType = userTypes[Math.floor(Math.random() * userTypes.length)];
            
            const fullRackName = `${prefix}-${String(rackNum).padStart(4, '0')}`;
            
            html += `
                <div class="mini-rack ${statusClass}" 
                     data-rack="${fullRackName}"
                     title="${fullRackName}: ${status}">
                    <div class="rack-label">${displayName}</div>
                    <div class="rack-status">${status}</div>
                    <div class="rack-icons">${gender} ${userType}</div>
                </div>
            `;
        }
        
        html += '</div>';
        return html;
    }
    
    load_real_rack_data(block) {
        // Optional: Fetch real rack data from server
        // Call this method after rendering to update with real data
        
        frappe.call({
            method: 'customize_erpnext.customize_erpnext.page.layout_manager.layout_manager.get_block_racks',
            args: {
                start_rack: block.start_rack,
                end_rack: block.end_rack
            },
            callback: (r) => {
                if (r.message && r.message.success) {
                    // Update rack cells with real data
                    const racks = r.message.racks;
                    
                    // Find the block element and update rack cells
                    // ... implementation here if needed
                }
            }
        });
    }
    
    bind_row_events(rowIndex) {
        const row_el = this.wrapper.find(`.row-section[data-row-index="${rowIndex}"]`);
        
        // Add block button click
        row_el.find('.add-block-btn').on('click', (e) => {
            const block_idx = $(e.target).closest('.block-cell').data('block');
            this.show_add_block_dialog(rowIndex, block_idx);
        });
        
        // Rack cell click - view rack details
        row_el.find('.mini-rack').on('click', (e) => {
            e.stopPropagation();
            const rack_name = $(e.currentTarget).data('rack');
            if (rack_name) {
                this.view_rack_details(rack_name);
            }
        });
        
        // Block action buttons
        row_el.find('.block-btn').on('click', (e) => {
            e.stopPropagation();
            const action = $(e.target).data('action');
            const block_idx = $(e.target).closest('.block-cell').data('block');
            
            if (action === 'view') {
                this.view_block(rowIndex, block_idx);
            } else if (action === 'remove') {
                this.remove_block(rowIndex, block_idx);
            }
        });
        
        // Drag events
        row_el.find('.block-cell.filled').on('dragstart', (e) => {
            const block_idx = $(e.target).data('block');
            this.draggedBlock = this.rows[rowIndex].blocks[block_idx];
            this.draggedFrom = {rowIndex, blockIndex: block_idx};
            e.originalEvent.dataTransfer.effectAllowed = 'move';
            $(e.target).css('opacity', '0.5');
        });
        
        row_el.find('.block-cell.filled').on('dragend', (e) => {
            $(e.target).css('opacity', '1');
        });
        
        row_el.find('.block-cell').on('dragover', (e) => {
            e.preventDefault();
            e.originalEvent.dataTransfer.dropEffect = 'move';
            $(e.currentTarget).addClass('drag-over');
        });
        
        row_el.find('.block-cell').on('dragleave', (e) => {
            $(e.currentTarget).removeClass('drag-over');
        });
        
        row_el.find('.block-cell').on('drop', (e) => {
            e.preventDefault();
            $(e.currentTarget).removeClass('drag-over');
            
            const target_row = $(e.currentTarget).data('row');
            const target_block = $(e.currentTarget).data('block');
            
            this.swap_blocks(target_row, target_block);
        });
    }
    
    view_rack_details(rack_name) {
        // View individual rack details
        frappe.msgprint({
            title: __('Rack: {0}', [rack_name]),
            message: `
                <div style="padding: 15px;">
                    <p><strong>📍 Rack Name:</strong> ${rack_name}</p>
                    <p><strong>🔗 Quick Actions:</strong></p>
                    <button class="btn btn-primary btn-sm" onclick="frappe.set_route('Form', 'Shoe Rack', '${rack_name}')">
                        Open Rack Form
                    </button>
                    <button class="btn btn-secondary btn-sm" onclick="frappe.set_route('shoe-rack-dashboard')">
                        Go to Dashboard
                    </button>
                </div>
            `
        });
    }
    
    swap_blocks(targetRow, targetBlock) {
        if (!this.draggedBlock || !this.draggedFrom) return;
        
        const {rowIndex: sourceRow, blockIndex: sourceBlock} = this.draggedFrom;
        
        // Same position, do nothing
        if (sourceRow === targetRow && sourceBlock === targetBlock) {
            this.draggedBlock = null;
            this.draggedFrom = null;
            return;
        }
        
        // Get blocks
        const source = this.rows[sourceRow].blocks[sourceBlock];
        const target = this.rows[targetRow].blocks[targetBlock];
        
        // Swap
        this.rows[sourceRow].blocks[sourceBlock] = target;
        this.rows[targetRow].blocks[targetBlock] = source;
        
        // Reset drag state
        this.draggedBlock = null;
        this.draggedFrom = null;
        
        // Re-render
        this.render();
        
        frappe.show_alert({
            message: __('✓ Blocks swapped successfully'),
            indicator: 'green'
        }, 2);
    }
    
    show_add_row_dialog() {
        const dialog = new frappe.ui.Dialog({
            title: __('Add New Row'),
            fields: [
                {
                    fieldname: 'row_name',
                    fieldtype: 'Data',
                    label: __('Row Name'),
                    reqd: 1,
                    default: `Row ${this.rows.length + 1}`
                },
                {
                    fieldname: 'cols',
                    fieldtype: 'Int',
                    label: __('Columns (Blocks per row)'),
                    reqd: 1,
                    default: 9,
                    description: 'Number of blocks per row (1-20)'
                },
                {
                    fieldname: 'row_count',
                    fieldtype: 'Int',
                    label: __('Rows'),
                    reqd: 1,
                    default: 2,
                    description: 'Number of rows (1-5)'
                }
            ],
            primary_action_label: __('Create Row'),
            primary_action: (values) => {
                if (values.cols < 1 || values.cols > 20) {
                    frappe.msgprint(__('Columns must be between 1 and 20'));
                    return;
                }
                if (values.row_count < 1 || values.row_count > 5) {
                    frappe.msgprint(__('Rows must be between 1 and 5'));
                    return;
                }
                
                this.add_row(values);
                dialog.hide();
            }
        });
        
        dialog.show();
    }
    
    add_row(values) {
        const total_blocks = values.cols * values.row_count;
        
        const new_row = {
            name: values.row_name,
            cols: values.cols,
            row_count: values.row_count,
            blocks: Array(total_blocks).fill(null)
        };
        
        this.rows.push(new_row);
        this.render();
        
        frappe.show_alert({
            message: __('✓ Row added: {0}', [values.row_name]),
            indicator: 'green'
        }, 3);
    }
    
    show_add_block_dialog(rowIndex, blockIndex) {
        const dialog = new frappe.ui.Dialog({
            title: __('Add Block'),
            fields: [
                {
                    fieldname: 'block_name',
                    fieldtype: 'Data',
                    label: __('Block Name'),
                    reqd: 1,
                    default: `Block ${this.get_next_block_number()}`
                },
                {
                    fieldname: 'start_rack',
                    fieldtype: 'Data',
                    label: __('Start Rack'),
                    reqd: 1,
                    description: 'Format: RACK-1, J-1, G-1, or A-1'
                },
                {
                    fieldname: 'end_rack',
                    fieldtype: 'Data',
                    label: __('End Rack'),
                    reqd: 1,
                    description: 'Format: RACK-16, J-16, G-16, or A-16 (must be 16 racks total)'
                }
            ],
            primary_action_label: __('Add Block'),
            primary_action: (values) => {
                // Validate format
                const start_valid = /^[A-Z]+-\d+$/.test(values.start_rack);
                const end_valid = /^[A-Z]+-\d+$/.test(values.end_rack);
                
                if (!start_valid || !end_valid) {
                    frappe.msgprint(__('Invalid rack format. Use: RACK-1, J-1, G-1, or A-1'));
                    return;
                }
                
                this.add_block(rowIndex, blockIndex, values);
                dialog.hide();
            }
        });
        
        dialog.show();
    }
    
    get_next_block_number() {
        let max = 0;
        this.rows.forEach(row => {
            row.blocks.forEach(block => {
                if (block && block.name) {
                    const match = block.name.match(/Block (\d+)/);
                    if (match) {
                        max = Math.max(max, parseInt(match[1]));
                    }
                }
            });
        });
        return max + 1;
    }
    
    add_block(rowIndex, blockIndex, values) {
        this.rows[rowIndex].blocks[blockIndex] = {
            name: values.block_name,
            start_rack: values.start_rack,
            end_rack: values.end_rack,
            rack_name: values.start_rack
        };
        
        this.render();
        
        frappe.show_alert({
            message: __('✓ Block added: {0}', [values.block_name]),
            indicator: 'green'
        }, 3);
    }
    
    remove_block(rowIndex, blockIndex) {
        const block = this.rows[rowIndex].blocks[blockIndex];
        
        frappe.confirm(
            __('Remove block: {0}?', [block.name]),
            () => {
                this.rows[rowIndex].blocks[blockIndex] = null;
                this.render();
                
                frappe.show_alert({
                    message: __('Block removed'),
                    indicator: 'orange'
                }, 2);
            }
        );
    }
    
    view_block(rowIndex, blockIndex) {
        const block = this.rows[rowIndex].blocks[blockIndex];
        const row = this.rows[rowIndex];
        
        frappe.msgprint({
            title: __('Block Details'),
            message: `
                <div style="padding: 15px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
                    <p style="margin: 10px 0;"><strong>📦 Name:</strong> ${block.name}</p>
                    <p style="margin: 10px 0;"><strong>📍 Range:</strong> ${block.start_rack} → ${block.end_rack}</p>
                    <p style="margin: 10px 0;"><strong>🗂️ Row:</strong> ${row.name}</p>
                    <p style="margin: 10px 0;"><strong>📌 Position:</strong> Row ${rowIndex + 1}, Slot ${blockIndex + 1}</p>
                </div>
            `,
            primary_action_label: __('Go to Shoe Rack Dashboard'),
            primary_action: () => {
                frappe.set_route('shoe-rack-dashboard');
            }
        });
    }
    
    edit_row(rowIndex) {
        const row = this.rows[rowIndex];
        
        const dialog = new frappe.ui.Dialog({
            title: __('Edit Row'),
            fields: [
                {
                    fieldname: 'row_name',
                    fieldtype: 'Data',
                    label: __('Row Name'),
                    reqd: 1,
                    default: row.name
                }
            ],
            primary_action_label: __('Update'),
            primary_action: (values) => {
                row.name = values.row_name;
                this.render();
                dialog.hide();
                
                frappe.show_alert({
                    message: __('✓ Row updated'),
                    indicator: 'green'
                }, 2);
            }
        });
        
        dialog.show();
    }
    
    delete_row(rowIndex) {
        const row = this.rows[rowIndex];
        const filled_blocks = row.blocks.filter(b => b !== null).length;
        
        let message = __('Delete row: {0}?', [row.name]);
        if (filled_blocks > 0) {
            message += `<br><br><strong style="color: #dc2626;"> Warning: ${filled_blocks} block(s) will be removed!</strong>`;
        }
        
        frappe.confirm(
            message,
            () => {
                this.rows.splice(rowIndex, 1);
                this.render();
                
                frappe.show_alert({
                    message: __('✓ Row deleted'),
                    indicator: 'red'
                }, 2);
            }
        );
    }
    
    save_layout() {
        frappe.show_alert({
            message: __('Saving layout...'),
            indicator: 'blue'
        }, 2);
        
        frappe.call({
            method: 'customize_erpnext.customize_erpnext.page.layout_manager.layout_manager.save_layout',
            args: {
                layout_data: JSON.stringify(this.rows)
            },
            callback: (r) => {
                if (r.message && r.message.success) {
                    frappe.show_alert({
                        message: __('✓ Layout saved successfully'),
                        indicator: 'green'
                    }, 3);
                } else {
                    frappe.msgprint({
                        title: __('Error'),
                        message: r.message.message || __('Failed to save layout'),
                        indicator: 'red'
                    });
                }
            },
            error: (r) => {
                frappe.msgprint({
                    title: __('Error'),
                    message: __('Failed to save layout. Check console for details.'),
                    indicator: 'red'
                });
                console.error('Save error:', r);
            }
        });
    }
    
    load_layout() {
        frappe.show_alert({
            message: __('Loading layout...'),
            indicator: 'blue'
        }, 1);
        
        frappe.call({
            method: 'customize_erpnext.customize_erpnext.page.layout_manager.layout_manager.load_layout',
            callback: (r) => {
                if (r.message && r.message.layout_data) {
                    try {
                        const data = JSON.parse(r.message.layout_data);
                        this.rows = Array.isArray(data) ? data : [];
                        this.render();
                        
                        frappe.show_alert({
                            message: __('✓ Layout loaded ({0} rows)', [this.rows.length]),
                            indicator: 'green'
                        }, 2);
                    } catch (e) {
                        console.error('Failed to parse layout data:', e);
                        frappe.msgprint({
                            title: __('Error'),
                            message: __('Failed to parse layout data'),
                            indicator: 'red'
                        });
                        this.rows = [];
                        this.render();
                    }
                } else {
                    this.rows = [];
                    this.render();
                    
                    frappe.show_alert({
                        message: __('No saved layout found'),
                        indicator: 'orange'
                    }, 2);
                }
            },
            error: (r) => {
                console.error('Load error:', r);
                this.rows = [];
                this.render();
            }
        });
    }
    
    export_json() {
        if (this.rows.length === 0) {
            frappe.msgprint(__('No layout to export'));
            return;
        }
        
        const data = JSON.stringify(this.rows, null, 2);
        const blob = new Blob([data], {type: 'application/json'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `shoe-rack-layout-${frappe.datetime.now_date()}.json`;
        a.click();
        URL.revokeObjectURL(url);
        
        frappe.show_alert({
            message: __('✓ Layout exported to JSON file'),
            indicator: 'blue'
        }, 3);
    }
}

// Global reference for access from onclick handlers
var layout_manager;

frappe.pages['layout-manager'].on_page_show = function(wrapper) {
    if (!layout_manager) {
        const page = frappe.pages['layout-manager'];
        layout_manager = new ShoeRackLayoutManager(page);
    } else {
        // Refresh stats when page is shown again
        layout_manager.render_stats();
    }
}