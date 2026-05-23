import json
import frappe


def setup_workspace_links():
	"""Add custom links to HRMS workspaces after migrate."""

	_setup_people_workspace()
	_setup_shift_attendance_workspace()


def _add_link_to_card(doc, card_label, link_label, link_to, link_type, is_query_report=0):
	"""Add a link under an existing Card Break if it doesn't already exist.

	Returns True if the link was added, False if it already existed.
	"""
	# Check if link already exists
	for link in doc.links:
		if link.type == "Link" and link.label == link_label:
			return False

	# Find the card break and the last link in that card
	card_idx = None
	insert_idx = None
	for i, link in enumerate(doc.links):
		if link.type == "Card Break" and link.label == card_label:
			card_idx = i
			insert_idx = i  # default: right after the card break
		elif card_idx is not None:
			if link.type == "Card Break":
				break  # reached next card
			insert_idx = i  # keep advancing within the card

	if card_idx is None:
		frappe.log_error(
			f"Workspace {doc.name}: Card Break '{card_label}' not found",
			"Workspace Setup",
		)
		return False

	# Insert after the last link in the card
	new_link = {
		"type": "Link",
		"label": link_label,
		"link_to": link_to,
		"link_type": link_type,
		"is_query_report": is_query_report,
		"onboard": 0,
		"hidden": 0,
	}
	doc.append("links", new_link)
	# Move the newly appended link to the correct position
	last = doc.links[-1]
	doc.links.pop()
	doc.links.insert(insert_idx + 1, last)

	# Update card break link_count
	doc.links[card_idx].link_count = (doc.links[card_idx].link_count or 0) + 1

	return True


def _add_card_with_link(doc, card_label, link_label, link_to, link_type, is_query_report=0):
	"""Add a new Card Break + Link at the end of the links table.

	Also adds the card to the content JSON. Returns True if added.
	"""
	# Check if card already exists
	for link in doc.links:
		if link.type == "Card Break" and link.label == card_label:
			return False

	doc.append("links", {
		"type": "Card Break",
		"label": card_label,
		"link_count": 1,
	})
	doc.append("links", {
		"type": "Link",
		"label": link_label,
		"link_to": link_to,
		"link_type": link_type,
		"is_query_report": is_query_report,
		"onboard": 0,
		"hidden": 0,
	})

	# Add card block to content JSON
	content = json.loads(doc.content or "[]")
	# Check if card already in content
	if not any(
		block.get("type") == "card" and block.get("data", {}).get("card_name") == card_label
		for block in content
	):
		content.append({
			"id": frappe.generate_hash(length=10),
			"type": "card",
			"data": {"card_name": card_label, "col": 4},
		})
		doc.content = json.dumps(content)

	return True


def _setup_people_workspace():
	"""Add Employee Maternity link and Employee Maternity Report to People workspace."""
	if not frappe.db.exists("Workspace", "People"):
		return

	doc = frappe.get_doc("Workspace", "People")
	changed = False

	# Card "Leaves": add "Employee Maternity" (DocType)
	if _add_link_to_card(doc, "Leaves", "Employee Maternity", "Employee Maternity", "DocType"):
		changed = True

	# Card "Other Reports": add "Employee Maternity Report" (Report)
	if _add_link_to_card(
		doc, "Other Reports", "Employee Maternity Report",
		"Employee Maternity Report", "Report", is_query_report=1,
	):
		changed = True

	if changed:
		doc.flags.ignore_permissions = True
		doc.save()
		frappe.db.commit()
		frappe.msgprint(f"Workspace 'People': custom links added.", alert=True)


def _fix_misplaced_links(doc):
	"""Fix links that were placed inside the wrong card due to ordering bug.

	Moves "Overtime Registration" into the "Overtime" card and
	"Shift Attendance Customize" into the "Reports" card if they are
	currently sitting inside a wrong card (e.g. "Attendance Machine").

	Uses direct SQL to swap idx values since doc.save() during migrate
	does not reliably reorder child table rows.
	"""
	corrections = {
		"Overtime Registration": "Overtime",
		"Shift Attendance Customize": "Reports",
	}

	fixed = False
	for link_label, target_card_label in corrections.items():
		# Find the link and what card it currently belongs to (by idx order)
		link_row = None
		current_card_label = None
		last_card_label = None
		for link in doc.links:
			if link.type == "Card Break":
				last_card_label = link.label
			elif link.type == "Link" and link.label == link_label:
				link_row = link
				current_card_label = last_card_label
				break

		if link_row is None or current_card_label is None:
			continue
		if current_card_label == target_card_label:
			continue  # already in the right card

		# Find the last link in the target card (by idx)
		target_card_row = None
		target_last_idx = None
		found_target = False
		for link in doc.links:
			if link.type == "Card Break" and link.label == target_card_label:
				target_card_row = link
				target_last_idx = link.idx
				found_target = True
			elif found_target:
				if link.type == "Card Break":
					break
				target_last_idx = link.idx

		if target_card_row is None:
			continue

		link_current_idx = link_row.idx
		new_idx = target_last_idx + 1

		if link_current_idx == new_idx:
			continue  # already at correct position

		# Use SQL to reorder: shift rows to make room and move the link
		parent = doc.name
		if link_current_idx > new_idx:
			# Moving link upward: shift rows between new_idx and current_idx down by 1
			# First, move our link out of the way
			frappe.db.sql("""
				UPDATE `tabWorkspace Link`
				SET idx = 0
				WHERE parent = %s AND idx = %s AND label = %s AND type = 'Link'
			""", (parent, link_current_idx, link_label))

			# Shift rows between new_idx and link_current_idx-1 down by 1
			frappe.db.sql("""
				UPDATE `tabWorkspace Link`
				SET idx = idx + 1
				WHERE parent = %s AND idx >= %s AND idx < %s
				ORDER BY idx DESC
			""", (parent, new_idx, link_current_idx))

			# Place our link at new_idx
			frappe.db.sql("""
				UPDATE `tabWorkspace Link`
				SET idx = %s
				WHERE parent = %s AND idx = 0 AND label = %s AND type = 'Link'
			""", (new_idx, parent, link_label))
		else:
			# Moving link downward: shift rows between current_idx+1 and new_idx up by 1
			frappe.db.sql("""
				UPDATE `tabWorkspace Link`
				SET idx = 0
				WHERE parent = %s AND idx = %s AND label = %s AND type = 'Link'
			""", (parent, link_current_idx, link_label))

			frappe.db.sql("""
				UPDATE `tabWorkspace Link`
				SET idx = idx - 1
				WHERE parent = %s AND idx > %s AND idx <= %s
				ORDER BY idx ASC
			""", (parent, link_current_idx, new_idx))

			frappe.db.sql("""
				UPDATE `tabWorkspace Link`
				SET idx = %s
				WHERE parent = %s AND idx = 0 AND label = %s AND type = 'Link'
			""", (new_idx, parent, link_label))

		frappe.db.commit()
		fixed = True

	# Reload the doc and recalculate all link_counts from actual positions
	if fixed:
		doc.reload()
		_recalculate_link_counts(doc)

	return fixed


def _recalculate_link_counts(doc):
	"""Recalculate link_count for all Card Breaks based on actual link positions."""
	card_breaks = []
	current_count = 0
	current_card_idx = None

	for i, link in enumerate(doc.links):
		if link.type == "Card Break":
			if current_card_idx is not None:
				card_breaks.append((current_card_idx, current_count))
			current_card_idx = i
			current_count = 0
		elif link.type == "Link":
			current_count += 1

	if current_card_idx is not None:
		card_breaks.append((current_card_idx, current_count))

	for card_idx, count in card_breaks:
		card = doc.links[card_idx]
		if card.link_count != count:
			frappe.db.sql("""
				UPDATE `tabWorkspace Link`
				SET link_count = %s
				WHERE parent = %s AND name = %s
			""", (count, doc.name, card.name))

	frappe.db.commit()
	doc.reload()


def _setup_shift_attendance_workspace():
	"""Add custom links to Shift & Attendance workspace."""
	if not frappe.db.exists("Workspace", "Shift & Attendance"):
		return

	doc = frappe.get_doc("Workspace", "Shift & Attendance")
	changed = False

	# Fix misplaced links from previous migrations: move links that
	# ended up inside the "Attendance Machine" card back to their
	# correct cards before making any additions.
	changed = _fix_misplaced_links(doc) or changed

	# New card "Attendance Machine" + link "Attendance Machine" (DocType)
	# Must be added BEFORE _add_link_to_card calls so that the "Overtime"
	# card is no longer the last card and its boundary is well-defined.
	if _add_card_with_link(
		doc, "Attendance Machine", "Attendance Machine",
		"Attendance Machine", "DocType",
	):
		changed = True

	# Card "Overtime": add "Overtime Registration" (DocType)
	if _add_link_to_card(
		doc, "Overtime", "Overtime Registration", "Overtime Registration", "DocType",
	):
		changed = True

	# Card "Reports": add "Shift Attendance Customize" (Report)
	if _add_link_to_card(
		doc, "Reports", "Shift Attendance Customize",
		"Shift Attendance Customize", "Report", is_query_report=1,
	):
		changed = True

	# Always recalculate link_counts to fix any accumulated drift
	doc.reload()
	_recalculate_link_counts(doc)

	if changed:
		doc.flags.ignore_permissions = True
		doc.save()
		frappe.db.commit()
		frappe.msgprint(f"Workspace 'Shift & Attendance': custom links added.", alert=True)


def drop_orphan_tables():
	"""Drop orphan database tables that have no corresponding DocType."""
	tables_to_drop = [] # "tabMaternity Leave"

	for table in tables_to_drop:
		if frappe.db.table_exists(table):
			frappe.db.sql_ddl(f"DROP TABLE `{table}`")
			frappe.db.commit()
			print(f"Dropped orphan table: {table}")
