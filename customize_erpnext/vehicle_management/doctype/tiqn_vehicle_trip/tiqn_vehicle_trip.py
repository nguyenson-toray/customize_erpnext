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


class TIQNVehicleTrip(Document):
	def validate(self):
		self.set_default_driver()
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

	def set_default_driver(self):
		"""Pick a vehicle and the driver follows.

		Every driver has one default vehicle, so the pairing is already in the data
		and asking a dispatcher to repeat it is just a chance to get it wrong.

		This lives in the controller rather than in the dispatch page so it holds
		for EVERY route into a trip: the page, the Desk form, the Zalo Mini App, the
		06:30/17:00 scheduler, an import. `driver` is reqd on the DocType and the
		mandatory check runs after validate(), so filling it here is enough to
		satisfy it.

		Only fills a blank - a stand-in driver the user typed is never overwritten.
		"""
		if self.driver or not self.vehicle:
			return

		self.driver = frappe.db.get_value(
			"TIQN Driver",
			{"assigned_vehicle": self.vehicle, "is_active": 1},
			"name",
			order_by="creation asc",
		)

	# ------------------------------------------------------------- validation
	def validate_status_transition(self):
		if self.is_new():
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

		if self.status == "confirmed" and not self.confirmed_at:
			self.confirmed_at = now_datetime()
		elif self.status == "in_progress" and not self.checkin_time:
			self.checkin_time = now_datetime()
		elif self.status == "completed" and not self.checkout_time:
			self.checkout_time = now_datetime()

	def set_total_km(self):
		if flt(self.km_start) and flt(self.km_end):
			self.total_km = flt(self.km_end) - flt(self.km_start)
		else:
			self.total_km = 0

	def build_trip_name(self):
		parts = [p for p in (self.from_location, self.to_location) if p]
		route = " - ".join(parts) if parts else _("Trip")
		return f"{route} {self.depart_time or ''} {self.trip_date or ''}".strip()

	# ----------------------------------------------------------- side effects
	def sync_vehicle_status(self, excluding_self=False):
		"""Keep TIQN Vehicle.status in step with the trips of that vehicle.

		Only "in_trip" <-> "available" is touched. A vehicle parked in
		maintenance / broken is left alone: a manager put it there on purpose.
		"""
		if not self.vehicle:
			return

		current = frappe.db.get_value("TIQN Vehicle", self.vehicle, "status")
		if current in ("maintenance", "broken"):
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
