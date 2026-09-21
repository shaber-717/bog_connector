# Copyright (c) 2026, Talorim and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class BOGIntegrationSettings(Document):
	@frappe.whitelist()
	def test_connection(self):
		"""Try to get an OAuth token (and, if any account mapping exists,
		one balance lookup) and report success/failure. Never returns the
		access token or secret to the caller."""
		from bog_connector.banking.bog_api import test_connection

		return test_connection()

	@frappe.whitelist()
	def sync_now(self):
		"""Manually trigger a sync of all enabled account mappings,
		regardless of the scheduler cadence."""
		from bog_connector.banking.bog_api import sync_all

		summary = sync_all(manual=True)
		return {"message": summary}
