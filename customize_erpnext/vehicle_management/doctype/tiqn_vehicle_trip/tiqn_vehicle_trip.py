# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

# A trip never goes backwards. Enforced in the controller so the Desk form and
# the Mini App cannot disagree about what a status means.
ALLOWED_TRANSITIONS = {
	"scheduled": {"scheduled", "confirmed", "in_progress", "cancelled"},
	"confirmed": {"confirmed", "in_progress", "cancelled"},
	"in_progress": {"in_progress", "completed", "cancelled"},
	"completed": {"completed"},
	"cancelled": {"cancelled"},
}

OPEN_STATUSES = ("scheduled", "confirmed", "in_progress")

# A trip is born planned. Being able to CREATE one already `completed` is the same
# thing as being able to jump straight from scheduled to completed - the transition
# table just never sees it, because there is no previous row to compare against.
CREATE_STATUSES = {"scheduled", "confirmed"}


class TIQNVehicleTrip(Document):
	def validate(self):
		self.validate_status_transition()
		self.validate_km()
		self.validate_odometer_continuity()
		self.set_total_km()
		self.stamp_status_timestamps()

		if self.status != "cancelled":
			self.cancelled_reason = None

		if self.trip_type != "fixed":
			self.template_id = None

		if not self.trip_name:
			self.trip_name = self.build_trip_name()

	def on_update(self):
		self.sync_vehicle_status()
		self.sync_linked_requests()

	def on_trash(self):
		"""Deleting a running trip must release its vehicle.

		Frappe does not call on_update() on delete, so without this a vehicle whose
		in_progress trip is deleted stays "in_trip" forever, with nothing on the
		board to explain why. Seen for real: Kia sat busy with no trip at all.
		`self` is excluded from the recount because the row is about to go.
		"""
		self.sync_vehicle_status(excluding_self=True)

	# ------------------------------------------------------------- validation
	def validate_status_transition(self):
		if self.is_new():
			# 🔴 The transition table below only guards UPDATES. Without this, a
			# plain POST to /api/resource/TIQN Vehicle Trip could create a trip that
			# is ALREADY `completed`, with any km_start/km_end and any
			# additional_cost - no transition, no check, nothing in the log.
			# Proved on 22/09/2026 with the Mini App's own API key: one request
			# created a completed trip of 999,998 km and 50,000,000 VND.
			# TIQN pays for the actual kilometres of each trip, so this is the
			# billing record itself. create_trip() enforced the same rule, but a
			# rule that only lives in one endpoint is not a rule - the DocType is
			# reachable over REST by anyone holding the key that ships in the client.
			#
			# The seeders and any future backfill set `allow_backdated_status` to say
			# "I am writing history on purpose". Server code can; a client cannot.
			if self.status not in CREATE_STATUSES and not self.flags.allow_backdated_status:
				frappe.throw(
					_("A new trip can only start as {0}. To record a trip that has "
					  "already run, create it first and then move it along.").format(
						" or ".join(sorted(CREATE_STATUSES))
					)
				)
			return

		previous = self.get_doc_before_save()
		if not previous or previous.status == self.status:
			return

		allowed = ALLOWED_TRANSITIONS.get(previous.status, set())
		if self.status not in allowed:
			frappe.throw(
				_("Cannot change trip status from {0} to {1}").format(
					previous.status, self.status
				)
			)

	def validate_km(self):
		if self.km_start is not None and flt(self.km_start) < 0:
			frappe.throw(_("KM Start cannot be negative"))

		if self.km_end in (None, "") or not flt(self.km_end):
			return

		if not flt(self.km_start):
			frappe.throw(_("KM Start must be recorded before KM End"))

		if flt(self.km_end) <= flt(self.km_start):
			frappe.throw(
				_("KM End ({0}) must be greater than KM Start ({1})").format(
					flt(self.km_end), flt(self.km_start)
				)
			)

	def validate_odometer_continuity(self):
		"""A vehicle cannot start a trip below where it last finished one.

		Deliberately scoped to the moment KM Start is written on a trip that has
		not finished yet. Running it on every save would break the opposite case:
		re-saving an already completed morning trip after the afternoon trip has
		logged a higher KM End is perfectly legitimate, and an unscoped check
		would reject it.
		"""
		if self.status in ("completed", "cancelled") or not flt(self.km_start):
			return

		previous = self.get_doc_before_save()
		if previous and flt(previous.km_start) == flt(self.km_start):
			return  # KM Start is unchanged - nothing new to validate

		last = frappe.db.sql(
			"""
			SELECT name, km_end FROM `tabTIQN Vehicle Trip`
			WHERE vehicle = %(vehicle)s AND trip_date = %(trip_date)s
			  AND status = 'completed' AND name != %(name)s AND km_end > 0
			ORDER BY km_end DESC LIMIT 1
			""",
			{"vehicle": self.vehicle, "trip_date": self.trip_date, "name": self.name or ""},
			as_dict=True,
		)
		if last and flt(self.km_start) < flt(last[0].km_end):
			frappe.throw(
				_(
					"KM Start ({0}) is lower than KM End ({1}) of the previous trip {2} on this vehicle"
				).format(flt(self.km_start), flt(last[0].km_end), last[0].name)
			)

	def stamp_status_timestamps(self):
		"""Fill the timestamp that belongs to a status the moment it is reached.

		The Mini App may either call checkin_trip()/checkout_trip(), which set
		these explicitly, or push `status` through the generic update_trip().
		Stamping here means both routes produce the same record.
		"""
		previous = self.get_doc_before_save()
		was = previous.status if previous else None
		if was == self.status:
			return

		elif self.status == "in_progress" and not self.checkin_time:
			self.checkin_time = now_datetime()
		elif self.status == "completed" and not self.checkout_time:
			self.checkout_time = now_datetime()

	def set_total_km(self):
		if flt(self.km_start) and flt(self.km_end):
			self.total_km = flt(self.km_end) - flt(self.km_start)
		else:
			self.total_km = 0

	# `trip_name` is a Data column: 140 characters. Now that a combined trip can carry
	# several destinations joined into to_location, a long route can reach that limit,
	# and going over it makes the INSERT fail rather than shortening anything.
	TRIP_NAME_MAX = 140

	def build_trip_name(self):
		"""Just the route: "Toray VSIP → Sân bay Chu Lai".

		No time and no date. Both already have their own columns and both are shown
		next to the name everywhere it appears, so repeating them inside the label
		only made every trip title long enough to be cut off on a phone.
		"""
		parts = [p for p in (self.from_location, self.to_location) if p]
		if not parts:
			return _("Trip")

		name = " → ".join(parts)
		if len(name) > self.TRIP_NAME_MAX:
			name = name[: self.TRIP_NAME_MAX - 1].rstrip() + "…"
		return name

	# ----------------------------------------------------------- side effects
	def sync_vehicle_status(self, excluding_self=False):
		"""Keep TIQN Vehicle.status in step with the trips of that vehicle.

		Only "in_trip" <-> "available" is touched. A vehicle parked in
		Xe đang `not_available` thì để nguyên: có người cố ý đặt như vậy.

		Xe là của đối tác nên TIQN không theo dõi bảo dưỡng hay hư hỏng - chỉ cần biết
		dùng được hay không. Vì thế chỉ còn ba trạng thái, và `maintenance` + `broken`
		cũ gộp lại thành `not_available` (23/09/2026).
		"""
		if not self.vehicle:
			return

		current = frappe.db.get_value("TIQN Vehicle", self.vehicle, "status")
		if current == "not_available":
			return

		running = frappe.db.count(
			"TIQN Vehicle Trip",
			{"vehicle": self.vehicle, "status": "in_progress", "name": ("!=", self.name)},
		)
		if self.status == "in_progress" and not excluding_self:
			running += 1

		target = "in_trip" if running else "available"
		if current != target:
			frappe.db.set_value("TIQN Vehicle", self.vehicle, "status", target)

	def sync_linked_requests(self):
		"""Requests riding on this trip follow the trip: assigned, or back to
		approved when the trip is cancelled."""
		requests = [p.request for p in (self.passengers or []) if p.request]
		if not requests:
			return

		for request in set(requests):
			current = frappe.db.get_value("TIQN Vehicle Request", request, "status")
			if self.status == "cancelled":
				if current == "assigned":
					frappe.db.set_value(
						"TIQN Vehicle Request",
						request,
						{"status": "approved", "assigned_trip": None},
					)
			elif current in ("pending", "approved"):
				frappe.db.set_value(
					"TIQN Vehicle Request",
					request,
					{"status": "assigned", "assigned_trip": self.name},
				)


def get_open_trip_for_vehicle(vehicle, exclude=None):
	"""Name of the trip currently occupying a vehicle, if any."""
	filters = {"vehicle": vehicle, "status": "in_progress"}
	if exclude:
		filters["name"] = ("!=", exclude)
	return frappe.db.get_value("TIQN Vehicle Trip", filters, "name")
