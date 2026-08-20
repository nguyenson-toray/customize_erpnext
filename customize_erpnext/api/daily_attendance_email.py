# Daily Attendance email — the same figures as the Daily Attendance dashboard,
# rendered as plain HTML so they survive an email client.
#
# No <svg>, no JavaScript, no images: frappe-charts draws in the browser at
# runtime and Gmail strips inline SVG, so a chart cannot travel in an email body.
# wkhtmltoimage is installed but its Qt WebKit is too old to even evaluate the
# frappe-charts bundle (verified: the bundle throws on load and exports nothing),
# so server-side rasterising is not an option either. The columns here are table
# cells with pixel heights, which every client renders.
#
# Business rules live in docs/daily_attendance_dashboard_plan.md.

import os

import frappe
from frappe.utils import formatdate, getdate, nowdate

from customize_erpnext.api.daily_attendance_metrics import (
	ABSENT_COLOR,
	OVERTIME_COLOR,
	OVERTIME_TODAY_COLOR,
	PRESENT_COLOR,
	get_daily_metrics,
	get_overtime_registrations,
	get_trend,
)

def _split_recipients(value):
	"""Comma or newline separated addresses -> list, blanks dropped."""
	return [r.strip() for r in (value or "").replace("\n", ",").split(",") if r.strip()]


# The two configured lists drive the scheduled send only. Anything triggered by
# hand takes an explicit list typed into the dialog, so a manual test can never
# reach the real audience by accident.
#
# Read straight off the single doc rather than through get_attendance_settings():
# that helper only returns keys listed in its own DEFAULTS, so the recipient
# fields come back missing, and widening DEFAULTS would touch the settings the
# live 08:15 report depends on.
def _manager_recipients():
	"""Managers — summary only, no attachment."""
	return _split_recipients(
		frappe.db.get_single_value("Attendance Calculation Setting", "manager_recipients")
	)


def _hr_recipients():
	"""HR — same mail plus the detail workbook."""
	return _split_recipients(
		frappe.db.get_single_value("Attendance Calculation Setting", "hr_recipients")
	)


INK = "#1F2933"
INK_MUTED = "#6B7280"
LINE = "#E4E7EB"
SURFACE = "#F7F8FA"

# Plot area per chart. Three chart rows stack vertically, so every pixel here
# costs three on the page: 130 gives a ~937px mail, 60 fits one 727px screen.
# Kept tall on purpose — short bars read as squat and lose the shape the chart
# exists to show, and the exact figures are printed above each bar regardless.
_PLOT_HEIGHT = 130


def _kpi(label, value, color=INK, note=None):
	"""One KPI tile.

	The card is the <td> itself rather than a div inside it: cells in a table row
	are stretched to a common height automatically, whereas an inner div only
	grows to its own content, which is what left tiles carrying an explanatory
	note taller than their neighbours. The note line is also always rendered,
	blank when there is nothing to say, so it reserves the same space either way.
	"""
	return f"""
	<td width="25%" valign="top" bgcolor="#FFFFFF" style="background-color:#FFFFFF;
	    border:1px solid {LINE};border-radius:6px;padding:10px 14px">
	  <div style="font-size:11px;color:{INK_MUTED};text-transform:uppercase;
	       letter-spacing:.4px;line-height:1.3">{label}</div>
	  <div style="font-size:26px;font-weight:700;color:{color};padding-top:3px;
	       line-height:1.1">{value}</div>
	  <div style="font-size:10px;color:{INK_MUTED};padding-top:2px;
	       line-height:1.3">{note or "&nbsp;"}</div>
	</td>"""


def _panel(title, body):
	"""A titled white card. Returned bare so panels can sit side by side."""
	return f"""
	<div style="font-size:13px;font-weight:700;color:{INK};padding-bottom:6px">{title}</div>
	<div style="background:#FFFFFF;border:1px solid {LINE};border-radius:6px;padding:12px 14px">
	  {body}
	</div>"""


def _column_chart(rows, name_key, bar_width=32, label_size=11):
	"""Present/Absent stacked into one column per category, numbers never overlapping.

	No value is drawn inside a segment. The absent segment is often only a few
	pixels tall — one absence on a 34-person line comes out at a quarter of a
	pixel — so any text placed inside it would collide with the segment below or
	spill outside the column. Instead each figure gets its own table row: the
	group total above the column, and the present/absent split beneath the label.
	Overlap is impossible by construction, whatever the data does.
	"""
	peak = max([r["present"] + r["absent"] for r in rows] or [0]) or 1

	def seg(value, color, radius):
		"""One coloured segment, as a table row rather than a styled div.

		Outlook renders through the Word engine, which ignores `height` on a
		<div> — the bar survives the first delivery but collapses to nothing when
		the mail is forwarded and the HTML is re-serialised, leaving only the
		text. A <td> carrying the old-fashioned `height`/`bgcolor`/`width`
		attributes is honoured by every engine, CSS is kept alongside for the
		clients that prefer it.
		"""
		height = round(value * _PLOT_HEIGHT / peak)
		if value and height < 2:
			height = 2
		if not height:
			return ""
		return (
			f'<tr><td width="{bar_width}" height="{height}" bgcolor="{color}" '
			f'style="width:{bar_width}px;height:{height}px;background-color:{color};'
			f'font-size:0;line-height:0;border-radius:{radius}">&nbsp;</td></tr>'
		)

	def column(r):
		segments = seg(r["absent"], ABSENT_COLOR, "2px 2px 0 0") + seg(
			r["present"], PRESENT_COLOR, "0 0 2px 2px" if r["absent"] else "2px"
		)
		if not segments:
			return "&nbsp;"
		return (
			'<table cellpadding="0" cellspacing="0" border="0" align="center" '
			f'style="border-collapse:collapse;width:{bar_width}px">{segments}</table>'
		)

	totals, bars, labels, splits = [], [], [], []
	for r in rows:
		total = r["present"] + r["absent"]
		totals.append(
			f'<td align="center" valign="bottom" style="font-size:{label_size}px;'
			f'color:{INK};font-weight:700;padding-bottom:3px;line-height:1.2">{total}</td>'
		)
		bars.append(
			f'<td valign="bottom" align="center" height="{_PLOT_HEIGHT}">{column(r)}</td>'
		)
		labels.append(
			f'<td align="center" style="font-size:{label_size}px;color:{INK_MUTED};'
			f'padding:6px 2px 2px 2px;border-top:2px solid {LINE};line-height:1.3">'
			f'{r[name_key]}</td>'
		)
		splits.append(
			f'<td align="center" style="font-size:{label_size}px;line-height:1.3;'
			f'padding:0 2px">'
			f'<span style="color:{PRESENT_COLOR};font-weight:700">{r["present"]}</span>'
			f'<span style="color:{LINE}"> / </span>'
			f'<span style="color:{ABSENT_COLOR};font-weight:700">{r["absent"]}</span>'
			"</td>"
		)

	return (
		'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
		'style="border-collapse:collapse">'
		f'<tr>{"".join(totals)}</tr>'
		f'<tr>{"".join(bars)}</tr>'
		f'<tr>{"".join(labels)}</tr>'
		f'<tr>{"".join(splits)}</tr>'
		"</table>"
	)


def _single_column_chart(
	rows, name_key, value_key, color, bar_width=32, label_size=11, highlight_color=None
):
	"""One bar per category for a single measure — value above, label below.

	Kept separate from _column_chart rather than folded into it: that one is
	built around the present/absent pair and its split line, which would print a
	meaningless "n / 0" here.

	A row flagged `highlight` is drawn in `highlight_color`, larger and bolder.
	Emphasis is carried by shade, size and weight rather than a second hue — it
	is the same measure, just the column the reader is looking for. Three signals
	instead of one so the column still stands out if a mail client drops the
	background colour.
	"""
	peak = max([r[value_key] for r in rows] or [0]) or 1
	highlight_color = highlight_color or color
	lit_size = label_size + 4

	values, bars, labels = [], [], []
	for r in rows:
		value = r[value_key]
		lit = bool(r.get("highlight"))
		bar_color = highlight_color if lit else color
		size = lit_size if lit else label_size
		height = round(value * _PLOT_HEIGHT / peak)
		if value and height < 2:
			height = 2

		values.append(
			f'<td align="center" valign="bottom" style="font-size:{size}px;'
			f'color:{bar_color if lit else INK};font-weight:700;padding-bottom:3px;'
			f'line-height:1.2">{value}</td>'
		)
		bar = (
			'<table cellpadding="0" cellspacing="0" border="0" align="center" '
			f'style="border-collapse:collapse;width:{bar_width}px"><tr>'
			f'<td width="{bar_width}" height="{height}" bgcolor="{bar_color}" '
			f'style="width:{bar_width}px;height:{height}px;background-color:{bar_color};'
			'font-size:0;line-height:0;border-radius:2px">&nbsp;</td></tr></table>'
		) if height else "&nbsp;"
		bars.append(f'<td valign="bottom" align="center" height="{_PLOT_HEIGHT}">{bar}</td>')
		labels.append(
			f'<td align="center" style="font-size:{size}px;'
			f'color:{INK if lit else INK_MUTED};font-weight:{700 if lit else 400};'
			f'padding:6px 2px 0 2px;border-top:2px solid {LINE};line-height:1.3">'
			f'{r[name_key]}</td>'
		)

	return (
		'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
		'style="border-collapse:collapse">'
		f'<tr>{"".join(values)}</tr><tr>{"".join(bars)}</tr><tr>{"".join(labels)}</tr>'
		"</table>"
	)


def _legend():
	return f"""
	<table cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;
	       font-size:13px;color:{INK}">
	  <tr>
	    <td width="10" height="10" bgcolor="{PRESENT_COLOR}"
	        style="background-color:{PRESENT_COLOR};border-radius:2px;font-size:0;line-height:0">&nbsp;</td>
	    <td style="padding:0 16px 0 6px">Present</td>
	    <td width="10" height="10" bgcolor="{ABSENT_COLOR}"
	        style="background-color:{ABSENT_COLOR};border-radius:2px;font-size:0;line-height:0">&nbsp;</td>
	    <td style="padding-left:6px">Absent</td>
	  </tr>
	</table>"""


def _detail_workbook(date):
	"""Build the detailed Excel workbook for one day.

	Returns (path, filename). The detail never goes in the body: on Outlook and
	OWA there is no way to collapse it, so it would bury the summary the mail
	exists to deliver. The workbook carries it instead.

	Reads whatever Attendance holds right now; recalculating is the caller's
	decision because it changes the summary figures too.
	"""
	from customize_erpnext.customize_erpnext.report.shift_attendance_customize.scheduler import (
		collect_daily_report_context,
		generate_excel_report,
	)

	data, stats = collect_daily_report_context(date)
	return generate_excel_report(date, data, stats)


def build_email_html(date=None):
	"""The full email body for one day."""
	m = get_daily_metrics(date)
	trend = get_trend(end_date=m["date"])
	h, s = m["headcount"], m["status"]

	kpis = "".join(
		[
			_kpi("Net Headcount", h["net"], note="excl. maternity &amp; new joiners"),
			_kpi("Present", s["present"], PRESENT_COLOR),
			_kpi("Absent", s["absent"], ABSENT_COLOR),
			_kpi(
				"Attendance Rate",
				f'{m["attendance_rate"]}%',
				note=f'{s["present"]} present &divide; {h["net"]} net headcount',
			),
		]
	)

	# Shift 2 has not started yet, so it is neither present nor absent. Kept in
	# writing rather than dropped: without it Present + Absent does not add up to
	# Net Headcount and the mail reads like a miscalculation.
	def stat(label, value):
		return (
			f'<span style="color:{INK_MUTED}">{label}</span> '
			f'<b style="color:{INK}">{value}</b>'
		)

	notes = " &nbsp;&middot;&nbsp; ".join(
		[
			stat("New joiners today", h["new_joiners"]),
			stat("On maternity leave", h["maternity"]),
			stat("Active employees", h["active"]),
		]
	)

	# Shifts starting after the mail goes out have no attendance yet, so they
	# report their headcount as pending instead of a misleading 0 / n.
	shift_bits = []
	for row in m["by_shift"]:
		if row["pending"]:
			shift_bits.append(
				f'<span style="color:{INK_MUTED}">{row["shift"]}</span> '
				f'<b style="color:{INK}">not started</b> '
				f'<span style="color:{INK_MUTED}">({row["headcount"]})</span>'
			)
		else:
			shift_bits.append(
				f'<span style="color:{INK_MUTED}">{row["shift"]}</span> '
				f'<b style="color:{PRESENT_COLOR}">{row["present"]}</b>'
				f'<span style="color:{LINE}"> / </span>'
				f'<b style="color:{ABSENT_COLOR}">{row["absent"]}</b>'
			)
	shifts_line = " &nbsp;&middot;&nbsp; ".join(shift_bits)

	trend_rows = [
		{"label": formatdate(r["date"], "dd/MM"), "present": r["present"], "absent": r["absent"]}
		for r in trend
	]
	sewing = _panel("Sewing Lines", _column_chart(m["by_group"], "group", bar_width=26))
	by_group = _panel("By Group", _column_chart(m["by_bucket"], "bucket", bar_width=28))
	# The window runs into the future because overtime is registered in advance,
	# so the column for the day being reported on is picked out — otherwise the
	# reader has to count along the axis to find where "now" sits.
	ot_rows = [
		{
			"label": formatdate(r["date"], "dd/MM"),
			"qty": r["qty"],
			"highlight": r["date"] == m["date"],
		}
		for r in get_overtime_registrations()
	]
	overtime = _panel(
		"Overtime Registration Quantity",
		_single_column_chart(
			ot_rows, "label", "qty", OVERTIME_COLOR,
			bar_width=22, label_size=10, highlight_color=OVERTIME_TODAY_COLOR,
		),
	)
	last7 = _panel(
		"Last 14 Working Days",
		# Twice the columns in the same half-width panel, so the bars narrow to
		# keep the dd/MM labels from colliding.
		_column_chart(trend_rows, "label", bar_width=16, label_size=10),
	)

	return f"""
<div style="background:{SURFACE};padding:16px 0;font-family:Helvetica,Arial,sans-serif">
<table width="1040" cellpadding="0" cellspacing="0" border="0" align="center"
       style="border-collapse:collapse;max-width:1040px;margin:0 auto">
  <tr><td>
    <div style="font-size:19px;font-weight:700;color:{INK}">Daily Attendance Report</div>
    <div style="font-size:13px;color:{INK_MUTED};padding-top:2px">
      {formatdate(m["date"], "EEEE, dd MMMM yyyy")} &middot; as of {m["as_of"]}
    </div>
  </td></tr>

  <tr><td style="padding-top:8px">
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="border-collapse:separate;border-spacing:6px">
      <tr>{kpis}</tr>
    </table>
  </td></tr>

  <tr><td style="padding:2px 6px 0 6px">
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="border-collapse:collapse;font-size:13px;line-height:1.5">
      <tr>
        <td align="left" valign="top">{notes}</td>
        <td align="right" valign="top" style="padding-left:20px">
          <span style="color:{INK_MUTED};text-transform:uppercase;letter-spacing:.4px;
                font-size:10px">By shift &nbsp;</span>{shifts_line}
        </td>
      </tr>
    </table>
  </td></tr>

  <tr><td style="padding:6px 6px 0 6px">{_legend()}</td></tr>

  <tr><td style="padding-top:12px">{sewing}</td></tr>

  <tr><td style="padding-top:12px">
    <table width="100%" cellpadding="0" cellspacing="0" border="0"
           style="border-collapse:collapse">
      <tr>
        <td width="50%" valign="top" style="padding-right:7px">{by_group}</td>
        <td width="50%" valign="top" style="padding-left:7px">{last7}</td>
      </tr>
    </table>
  </td></tr>

  <tr><td style="padding-top:12px">{overtime}</td></tr>

</table>
</div>"""


@frappe.whitelist()
def send_daily_attendance_email(
	date=None,
	recipients=None,
	bypass_holiday_check=0,
	attach_detail=0,
	force_update_attendance=0,
):
	"""Validate the request, then hand the work to a background job.

	Recalculating attendance and building the workbook take long enough that
	doing them inside the web request leaves the user staring at a frozen dialog,
	so only the checks that can fail fast happen here — everything the caller
	needs to know is decided before returning.
	"""
	from customize_erpnext.customize_erpnext.report.shift_attendance_customize.scheduler import (
		_is_holiday_or_sunday,
	)

	date = str(getdate(date or nowdate()))

	if not int(bypass_holiday_check or 0) and _is_holiday_or_sunday(date):
		return {"status": "skipped", "message": f"{date} is a Sunday or holiday"}

	if isinstance(recipients, str):
		recipients = _split_recipients(recipients)
	if not recipients:
		return {"status": "skipped", "message": "No recipients given"}

	frappe.enqueue(
		_send_job,
		queue="long",
		timeout=1800,
		date=date,
		recipients=recipients,
		attach_detail=int(attach_detail or 0),
		force_update_attendance=int(force_update_attendance or 0),
	)
	return {"status": "queued", "recipients": recipients, "date": date}


def _send_job(date, recipients, attach_detail=0, force_update_attendance=0):
	"""Do the slow part: recalculate, build the workbook, send.

	Runs in a background worker, so failures land in the Error Log rather than in
	front of whoever pressed the button.
	"""
	# Recalculating rebuilds the Attendance records, which every figure in the
	# mail reads — the summary just as much as the workbook. So it runs on its
	# own here rather than as an argument to the workbook builder, where ticking
	# it without also asking for the attachment would have done nothing.
	if int(force_update_attendance or 0):
		from customize_erpnext.customize_erpnext.report.shift_attendance_customize.scheduler import (
			recalculate_attendance,
		)

		recalculate_attendance(date)

	excel_path = excel_name = None
	if int(attach_detail or 0):
		excel_path, excel_name = _detail_workbook(date)

	attachments = None
	if excel_path:
		with open(excel_path, "rb") as f:
			attachments = [{"fname": excel_name, "fcontent": f.read()}]

	m = get_daily_metrics(date)
	try:
		frappe.sendmail(
			recipients=recipients,
			subject=(
				f'Daily Attendance {formatdate(date, "dd/MM/yyyy")} | '
				f'Present {m["status"]["present"]} / Absent {m["status"]["absent"]}'
			),
			message=build_email_html(date),
			attachments=attachments,
			now=False,
		)
	finally:
		# The workbook is written to a temp file; drop it whether or not the
		# queueing succeeded so failures cannot silently fill the disk.
		if excel_path and os.path.exists(excel_path):
			try:
				os.remove(excel_path)
			except OSError:
				frappe.logger().warning(f"Could not remove temp workbook {excel_path}")

	return {
		"status": "sent",
		"recipients": recipients,
		"date": date,
		"attached": bool(excel_name),
	}


def send_daily_attendance_email_scheduled():
	"""Cron entry point.

	Managers get the summary, HR gets the same mail plus the detail workbook.
	Either list being empty simply means that audience is not subscribed yet, so
	it is skipped rather than falling back to some other address — a report of
	this kind must never guess who should receive it.
	"""
	from customize_erpnext.customize_erpnext.report.shift_attendance_customize.scheduler import (
		_is_holiday_or_sunday,
		recalculate_attendance,
	)

	date = str(getdate(nowdate()))
	if _is_holiday_or_sunday(date):
		return [{"status": "skipped", "message": f"{date} is a Sunday or holiday"}]

	audiences = [
		("Manager", _manager_recipients(), 0),
		("HR", _hr_recipients(), 1),
	]
	if not any(addresses for _label, addresses, _attach in audiences):
		return [{"status": "skipped", "message": "No Manager or HR recipients configured"}]

	# The scheduled run always rebuilds attendance first — it fires minutes after
	# the shift starts, so the check-ins it reports on have only just landed.
	# Done once here rather than per audience: it is the expensive step, and
	# running it twice would also let the two mails disagree.
	recalculate_attendance(date)

	results = []
	for label, addresses, attach in audiences:
		if not addresses:
			results.append({"audience": label, "status": "skipped", "message": "no recipients"})
			continue
		try:
			# Already inside a background worker, and attendance was rebuilt
			# above — call the job directly rather than enqueueing another one.
			res = _send_job(date=date, recipients=addresses, attach_detail=attach)
		except Exception:
			frappe.log_error(
				title=f"Daily Attendance Email Failed ({label})",
				message=frappe.get_traceback(),
			)
			# One audience failing must not stop the other from being sent.
			res = {"status": "error"}
		results.append({"audience": label, **res})
	return results
