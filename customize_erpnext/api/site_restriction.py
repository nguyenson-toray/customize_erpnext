# -*- coding: utf-8 -*-
# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from functools import wraps


# List of allowed sites for doc_events
ALLOWED_SITES = [
	"erp.tiqn.local",
	# Add more sites as needed
]


def only_for_sites(*allowed_sites):
	"""
	Decorator to restrict function execution to specific sites only.

	Usage:
		@only_for_sites("erp.tiqn.local")
		def my_event_handler(doc, method):
			# This will only run on specified sites
			pass
	"""
	def decorator(fn):
		@wraps(fn)
		def wrapper(*args, **kwargs):
			# Get current site
			current_site = frappe.local.site

			# Determine which sites to check
			sites_to_check = allowed_sites if allowed_sites else ALLOWED_SITES

			# Check if current site is in allowed list
			if current_site in sites_to_check:
				return fn(*args, **kwargs)
			else:
				# Silently skip execution on other sites
				frappe.logger().debug(
					f"Skipping {fn.__name__} on site {current_site} - not in allowed sites: {sites_to_check}"
				)
				return None

		return wrapper
	return decorator


def is_allowed_site(*allowed_sites):
	"""
	Check if current site is in the allowed list.

	Args:
		*allowed_sites: Site names to check. If empty, uses ALLOWED_SITES.

	Returns:
		bool: True if current site is allowed, False otherwise
	"""
	current_site = frappe.local.site
	sites_to_check = allowed_sites if allowed_sites else ALLOWED_SITES
	return current_site in tuple(sites_to_check)
