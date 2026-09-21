# Copyright (c) 2026, Talorim and contributors
# For license information, please see license.txt
#
# Entry point for the scheduler hook registered in hooks.py
# ("bog_connector.banking.tasks.scheduled_sync"), run every 15 minutes
# by the Frappe scheduler. Kept deliberately tiny: all real logic lives in
# bog_api.py so it can also be called directly (e.g. from bench console) for
# debugging without going through the scheduler.

import frappe

from bog_connector.banking.bog_api import get_settings, sync_all


def scheduled_sync():
	"""Called by the Frappe scheduler every 15 minutes. Does nothing unless
	the "Enabled" checkbox on BOG Integration Settings is turned on, so the
	integration can be switched off from the UI without touching the cron
	registration or redeploying."""
	settings = get_settings()

	if not settings.enabled:
		return

	try:
		sync_all(manual=False)
	except Exception:
		# sync_all() already isolates per-mapping failures into BOG Sync Log
		# entries and never raises in normal operation. This is a last-resort
		# safety net so a truly unexpected error doesn't take down the whole
		# scheduler tick - it gets logged to the Error Log instead.
		frappe.log_error(frappe.get_traceback(), "BOG Connector: scheduled_sync")
