frappe.ui.form.on('Stock Entry', {
  refresh: function (frm) {
    // Đợi DOM load xong
    setTimeout(function () {
      // Tìm input field của work_order
      var $workOrderInput = $(frm.fields_dict['work_order'].input);

      // Lắng nghe sự kiện tìm kiếm trước khi nó xảy ra
      $workOrderInput.on('click focus', function () {
        // Kiểm tra điều kiện Stock Entry Type
        var stockEntryType = frm.doc.stock_entry_type;
        // console.log("Current Stock Entry Type:", stockEntryType);

        // Chỉ áp dụng filter nếu Stock Entry Type là Material Transfer for Manufacture
        if (stockEntryType === "Material Transfer for Manufacture") {
          //   console.log("Applying filter for Material Transfer for Manufacture");
          // Gắn observer vào trường để theo dõi khi API được gọi
          var originalAjax = $.ajax;
          $.ajax = function (options) {
            // Kiểm tra xem có phải là API search_link không
            if (options.url && options.url.includes("frappe.desk.search.search_link")) {
              //   console.log("Detected search_link API call");
              // Kiểm tra nội dung yêu cầu
              var data = options.data;
              if (typeof data === 'string') {
                try {
                  data = JSON.parse(data);
                } catch (e) {
                  // Không phải JSON, thử parse từ query string
                  data = {};
                  options.data.split('&').forEach(function (part) {
                    var item = part.split('=');
                    data[decodeURIComponent(item[0])] = decodeURIComponent(item[1] || '');
                  });
                }
              }

              // Nếu là tìm kiếm Work Order, thêm filter
              if (data.doctype === "Work Order" && data.reference_doctype === "Stock Entry") {
                //  console.log("Adding filter to Work Order search");

                // Thêm filter
                data.filters = "{\"status\":[\"=\",\"Not Started\"]}" || {};

                // Cập nhật dữ liệu yêu cầu
                if (options.contentType && options.contentType.includes('application/json')) {
                  options.data = JSON.stringify(data);
                } else {
                  var queryString = Object.keys(data).map(function (key) {
                    return encodeURIComponent(key) + '=' + encodeURIComponent(data[key]);
                  }).join('&');
                  options.data = queryString;
                }

                // console.log("Modified request data:", options.data);
              }
            }

            // Khôi phục $.ajax để tránh vòng lặp vô hạn
            $.ajax = originalAjax;

            // Gọi phương thức gốc
            return originalAjax(options);
          };

          //  console.log("Ajax interceptor set up for Material Transfer for Manufacture");
        } else {
          //  console.log("Not applying filter, Stock Entry Type is not Material Transfer for Manufacture");
        }
      });
    }, 1000);
  },

  // Thêm handler cho sự kiện thay đổi Stock Entry Type
  stock_entry_type: function (frm) {
    // console.log("Stock Entry Type changed to:", frm.doc.stock_entry_type); 
    // Nếu cần thiết, có thể refresh field để áp dụng lại logic
    frm.refresh_field('work_order');
  }
});