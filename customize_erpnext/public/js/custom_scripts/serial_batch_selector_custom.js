// Thêm nút "Add Multiple Batch" vào dialog "Add Batch Nos" (Serial and Batch Bundle selector)
// — ngay sau section "Add Batch Nos via CSV File" — cho phép lọc & chọn 1 / nhiều / tất cả
// các Batch đã tạo cho item rồi thêm vào bảng entries.
// Phạm vi: Stock Entry, item có batch (không serial), giao dịch Inward (Receipt).

frappe.provide("erpnext");

(function () {
    if (!erpnext.SerialBatchPackageSelector || erpnext.SerialBatchPackageSelector.prototype._add_multiple_batch_patched) {
        return;
    }
    const proto = erpnext.SerialBatchPackageSelector.prototype;
    proto._add_multiple_batch_patched = true;

    // Chèn nút sau section CSV. get_attach_field VỐN chỉ được gọi ở nhánh Inward
    // (get_dialog_fields: Outward -> get_filter_fields; else -> get_attach_field), nên Material Issue
    // / Transfer (Outward) không bao giờ đi vào đây. Thêm guard chặt để tuyệt đối không ảnh hưởng
    // các luồng khác: CHỈ Stock Entry • purpose = Material Receipt • Inward • item batch (không serial).
    const _orig_get_attach_field = proto.get_attach_field;
    proto.get_attach_field = function () {
        let fields = _orig_get_attach_field.call(this);

        const is_receipt =
            this.frm?.doc?.doctype === "Stock Entry" &&
            this.frm?.doc?.purpose === "Material Receipt" &&
            this.item?.type_of_transaction !== "Outward";
        const is_batch_only = this.item?.has_batch_no && !this.item?.has_serial_no;

        if (is_receipt && is_batch_only) {
            fields.push({ fieldtype: "Section Break", label: __("Add Multiple Batch") });
            fields.push({
                fieldtype: "Button",
                fieldname: "add_multiple_batch",
                label: __("Add Multiple Batch"),
                click: () => this.show_multiple_batch_dialog(),
            });
        }
        return fields;
    };

    // Mở dialog chọn batch của item
    proto.show_multiple_batch_dialog = function () {
        let me = this;
        frappe.db
            .get_list("Batch", {
                filters: { item: this.item.item_code, disabled: 0 },
                fields: [
                    "name",
                    "custom_lot_number",
                    "custom_roll_number",
                    "custom_color",
                    "custom_initial_quantity",
                    "batch_qty",
                ],
                order_by: "creation desc",
                limit: 0,
            })
            .then((batches) => {
                if (!batches || !batches.length) {
                    frappe.msgprint(__("No batches found for item {0}", [this.item.item_code]));
                    return;
                }
                batches.forEach((b) => {
                    b.batch_no = b.name;
                    b.__checked = 0;
                    // Điền sẵn Quantity từ Initial Quantity của Batch (vẫn sửa được)
                    b.qty = flt(b.custom_initial_quantity) || 0;
                });
                me._render_multiple_batch_dialog(batches);
            });
    };

    proto._render_multiple_batch_dialog = function (all_batches) {
        let me = this;

        const d = new frappe.ui.Dialog({
            title: __("Add Multiple Batch — {0}", [this.item.item_code]),
            size: "extra-large",
            fields: [
                {
                    fieldtype: "Data",
                    fieldname: "filter",
                    label: __("Filter (Batch / Lot / Roll / Color)"),
                    onchange: () => apply_filter(),
                },
                {
                    fieldtype: "Float",
                    fieldname: "default_qty",
                    label: __("Default Quantity"),
                    description: __("Chỉ áp cho dòng được chọn mà Quantity đang trống (Quantity mặc định lấy từ Initial Quantity của Batch)"),
                },
                { fieldtype: "Section Break" },
                {
                    fieldtype: "HTML",
                    fieldname: "actions",
                    options: `
                        <button class="btn btn-xs btn-default sbx-select-all">${__("Select All (filtered)")}</button>
                        <button class="btn btn-xs btn-default sbx-clear-all" style="margin-left:5px;">${__("Clear All")}</button>
                        <span class="text-muted sbx-count" style="margin-left:10px;"></span>`,
                },
                {
                    fieldtype: "Table",
                    fieldname: "batches",
                    cannot_add_rows: true,
                    cannot_delete_rows: true,
                    in_place_edit: false,
                    data: all_batches,
                    fields: [
                        { fieldtype: "Data", fieldname: "batch_no", label: __("Batch No"), in_list_view: 1, columns: 4, read_only: 1 },
                        { fieldtype: "Data", fieldname: "custom_lot_number", label: __("Lot"), in_list_view: 1, columns: 1, read_only: 1 },
                        { fieldtype: "Data", fieldname: "custom_roll_number", label: __("Roll"), in_list_view: 1, columns: 1, read_only: 1 },
                        { fieldtype: "Data", fieldname: "custom_color", label: __("Color"), in_list_view: 1, columns: 2, read_only: 1 },
                        { fieldtype: "Float", fieldname: "qty", label: __("Quantity"), in_list_view: 1, columns: 2 },
                    ],
                },
            ],
            primary_action_label: __("Add Selected"),
            primary_action: () => {
                let default_qty = flt(d.get_value("default_qty"));
                let selected = all_batches.filter((b) => b.__checked);
                if (!selected.length) {
                    frappe.msgprint(__("Please select at least one batch"));
                    return;
                }

                let entries = me.dialog.fields_dict.entries.df.data || [];
                let by_batch = {};
                entries.forEach((e) => { if (e.batch_no) by_batch[e.batch_no] = e; });

                let added = 0;
                let updated = 0;
                selected.forEach((b) => {
                    let qty = flt(b.qty) || default_qty || 0;
                    if (by_batch[b.batch_no]) {
                        by_batch[b.batch_no].qty = qty;
                        updated++;
                    } else {
                        let row = { batch_no: b.batch_no, qty: qty };
                        entries.push(row);
                        by_batch[b.batch_no] = row;
                        added++;
                    }
                });

                me.dialog.fields_dict.entries.df.data = entries;
                me.dialog.fields_dict.entries.grid.refresh();
                d.hide();
                frappe.show_alert(
                    { message: __("Added {0}, updated {1} batch(es)", [added, updated]), indicator: "green" },
                    5
                );
            },
        });

        function get_grid() {
            return d.fields_dict.batches.grid;
        }

        function update_count() {
            let n = all_batches.filter((b) => b.__checked).length;
            d.$wrapper.find(".sbx-count").text(__("{0} selected", [n]));
        }

        function apply_filter() {
            let q = (d.get_value("filter") || "").toLowerCase().trim();
            let data = !q
                ? all_batches
                : all_batches.filter((b) =>
                      [b.batch_no, b.custom_lot_number, b.custom_roll_number, b.custom_color].some((v) =>
                          (v || "").toString().toLowerCase().includes(q)
                      )
                  );
            d.fields_dict.batches.df.data = data;
            get_grid().refresh();
        }

        d.show();
        d.$wrapper.find(".modal-dialog").css({ "max-width": "90%", width: "1100px" });

        d.$wrapper.find(".sbx-select-all").on("click", () => {
            (d.fields_dict.batches.df.data || []).forEach((r) => { r.__checked = 1; });
            get_grid().refresh();
            update_count();
        });
        d.$wrapper.find(".sbx-clear-all").on("click", () => {
            all_batches.forEach((r) => { r.__checked = 0; });
            get_grid().refresh();
            update_count();
        });
        // Cập nhật số đếm khi tick tay
        d.$wrapper.on("change", ".grid-row-check", () => setTimeout(update_count, 50));
        update_count();
    };
})();
