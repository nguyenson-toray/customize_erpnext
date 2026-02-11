$(() => {
    const query_params = frappe.utils.get_query_params();
    update_ui_with_filters();
    update_filter_count();

    $(".desktop-filters").change(function () {
        update_params(get_new_params(".desktop-filters"));
    });

    $("#apply-filters").on("click", function () {
        update_params(get_new_params(".mobile-filters"));
    });

    $("[name=clear-filters]").on("click", function () {
        update_params();
    });

    $("#filter").click(function () {
        $("#filters-drawer").addClass("active");
        $("#overlay").addClass("active");
        $("html, body").css({ overflow: "hidden", height: "100%" });
    });

    $("[name=close-filters-drawer]").click(function () {
        $("#filters-drawer").removeClass("active");
        $("#overlay").removeClass("active");
        $("html, body").css({ overflow: "auto", height: "auto" });
    });

    $("#search-box").bind("search", function () {
        update_params(get_new_params(".desktop-filters"));
    });

    $("#search-box").keyup(function (e) {
        if (e.keyCode == 13) {
            $(this).trigger("search");
        }
    });

    $("#sort").on("click", function () {
        const filters = $(".desktop-filters").serialize();
        query_params.sort === "asc"
            ? update_params(filters)
            : update_params(filters + "&sort=asc");
    });

    $("[name=card]").on("click", function () {
        window.location.href = this.id;
    });

    $("[name=pagination]").on("click", function () {
        const filters = $(".desktop-filters").serialize();
        update_params(filters + "&page=" + this.id);
    });

    $("#previous").on("click", function () {
        const new_page = (Number(query_params?.page) || 1) - 1;
        const filters = $(".desktop-filters").serialize();
        update_params(filters + "&page=" + new_page);
    });

    $("#next").on("click", function () {
        const new_page = (Number(query_params?.page) || 1) + 1;
        const filters = $(".desktop-filters").serialize();
        update_params(filters + "&page=" + new_page);
    });

    $(".mobile-filters").change(function () {
        update_filter_count();
    });

    function update_ui_with_filters() {
        const allowed_filters = Object.keys(
            JSON.parse($("#data").data("filters").replace(/'/g, '"')),
        );

        for (const filter in query_params) {
            if (filter === "query") $("#search-box").val(query_params["query"]);
            else if (filter === "page") disable_inapplicable_pagination_buttons();
            else if (allowed_filters.includes(filter)) {
                if (typeof query_params[filter] === "string") {
                    $("#desktop-" + $.escapeSelector(query_params[filter])).prop("checked", true);
                    $("#mobile-" + $.escapeSelector(query_params[filter])).prop("checked", true);
                } else
                    for (const d of query_params[filter]) {
                        $("#desktop-" + $.escapeSelector(d)).prop("checked", true);
                        $("#mobile-" + $.escapeSelector(d)).prop("checked", true);
                    }
            }
        }
    }

    function disable_inapplicable_pagination_buttons() {
        const no_of_pages = JSON.parse($("#data").data("no-of-pages"));
        const page_no = Number(query_params["page"]);
        if (page_no === no_of_pages) {
            $("#next").prop("disabled", true);
        } else if (page_no > no_of_pages || page_no <= 1) {
            $("#previous").prop("disabled", true);
        }
    }

    function get_new_params(filter_group) {
        return "sort" in query_params
            ? $(filter_group).serialize() + "&" + $.param({ sort: query_params["sort"] })
            : $(filter_group).serialize();
    }

    function update_filter_count() {
        const checkedFilters = $(".mobile-filters:checked").not("#search-box").length;
        const badge = $(".jp-filter-badge");
        if (checkedFilters > 0) {
            badge.text(checkedFilters).show();
        } else {
            badge.hide();
        }
    }
});

function update_params(params = "") {
    if ($("#filters-drawer").hasClass("active")) {
        $("#filters-drawer").removeClass("active");
        $("#overlay").removeClass("active");
        $("html, body").css({ overflow: "auto", height: "auto" });
        setTimeout(() => {
            window.location.href = "/jobs?" + params;
        }, 250);
    } else {
        window.location.href = "/jobs?" + params;
    }
}
