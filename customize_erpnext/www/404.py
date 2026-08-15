# Override of frappe/www/404.py
# Only difference from core: "Back to Home" links straight to /desk instead of "/",
# because "/" resolves to Website Settings.home_page and adds a pointless redirect hop.


def get_context(context):
	context.http_status_code = 404
