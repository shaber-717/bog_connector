# Copyright (c) 2026, Talorim and contributors
# For license information, please see license.txt
#
# Bank of Georgia "Business Online" API client.
#
# Docs used while building this (confirm against your own BOG Business Online
# API console, since bank APIs do change): https://api.bog.ge/docs/en/bonline/
#
#   Token endpoint  : POST https://account.bog.ge/auth/realms/bog/protocol/openid-connect/token
#                      (OAuth2 client_credentials grant, Keycloak-based)
#   API base        : https://api.businessonline.ge/api
#   Statement       : GET  {base}/statement/{accountNumber}/{currency}/{startDate}/{endDate}
#                      (max 1000 records per call - the bank's own limit)
#   Balance         : GET  {base}/accounts/{accountNumber}/{currency}
#
# Both the token URL and API base URL are stored on BOG Integration Settings
# rather than hard-coded, so they can be corrected from the UI the first time
# this is tested against the real bank, without a redeploy.

import json
from datetime import date, datetime, timedelta

import frappe
import requests
from frappe.utils import get_datetime, now_datetime
from frappe.utils.password import get_decrypted_password

CACHE_KEY = "bog_connector:access_token"
REQUEST_TIMEOUT = 30


class BOGAPIError(Exception):
	pass


def get_settings():
	return frappe.get_single("BOG Integration Settings")


def _get_client_secret(settings):
	# get_password() also works on the doc itself, but the explicit
	# get_decrypted_password call makes it unambiguous that this stays
	# server-side and is never put back on the response of a whitelisted call.
	return get_decrypted_password(
		"BOG Integration Settings", "BOG Integration Settings", "client_secret"
	)


def get_access_token(force_refresh=False):
	"""Return a valid OAuth2 access token, using a short-lived cache so we
	don't request a fresh token on every single API call."""
	if not force_refresh:
		cached = frappe.cache().get_value(CACHE_KEY)
		if cached:
			return cached

	settings = get_settings()
	client_id = settings.client_id
	client_secret = _get_client_secret(settings)

	if not client_id or not client_secret:
		raise BOGAPIError("Client ID / Client Secret are not set on BOG Integration Settings.")

	try:
		response = requests.post(
			settings.token_url,
			headers={"Content-Type": "application/x-www-form-urlencoded"},
			auth=(client_id, client_secret),
			data={
				"grant_type": "client_credentials",
				"client_id": client_id,
				"client_secret": client_secret,
			},
			timeout=REQUEST_TIMEOUT,
		)
	except requests.RequestException as e:
		raise BOGAPIError(f"Could not reach token URL: {e}")

	if response.status_code != 200:
		raise BOGAPIError(
			f"Token request failed ({response.status_code}): {_safe_body(response)}"
		)

	try:
		payload = response.json()
		token = payload["access_token"]
		expires_in = int(payload.get("expires_in", 60))
	except (ValueError, KeyError) as e:
		raise BOGAPIError(f"Unexpected token response shape: {e}")

	# Cache for a bit less than the real TTL so we refresh before it expires.
	ttl = max(expires_in - 30, 15)
	frappe.cache().set_value(CACHE_KEY, token, expires_in_sec=ttl)
	return token


def _safe_body(response, limit=500):
	try:
		return response.text[:limit]
	except Exception:
		return "<no body>"


def api_get(path, params=None):
	"""GET against the BOG API base URL, retrying once with a fresh token
	if the first attempt comes back 401 (token expired/revoked)."""
	settings = get_settings()
	url = settings.api_base_url.rstrip("/") + path

	for attempt in (1, 2):
		token = get_access_token(force_refresh=(attempt == 2))
		try:
			response = requests.get(
				url,
				params=params,
				headers={"Authorization": f"Bearer {token}"},
				timeout=REQUEST_TIMEOUT,
			)
		except requests.RequestException as e:
			raise BOGAPIError(f"Request to {path} failed: {e}")

		if response.status_code == 401 and attempt == 1:
			continue

		if response.status_code != 200:
			raise BOGAPIError(f"{path} failed ({response.status_code}): {_safe_body(response)}")

		try:
			return response.json()
		except ValueError:
			raise BOGAPIError(f"{path} did not return JSON: {_safe_body(response)}")

	raise BOGAPIError(f"{path} failed after token refresh (401 Unauthorized).")


def fetch_balance(account_number, currency):
	return api_get(f"/accounts/{account_number}/{currency}")


def fetch_statement(account_number, currency, start_date, end_date):
	"""start_date / end_date: date objects or 'YYYY-MM-DD' strings.
	BOG's own statement endpoint caps a single call at 1000 records - if you
	are doing a very large historical backfill, call this in smaller date
	windows rather than one huge range."""
	start_date = _as_date_str(start_date)
	end_date = _as_date_str(end_date)
	return api_get(f"/statement/{account_number}/{currency}/{start_date}/{end_date}")


def _as_date_str(d):
	if isinstance(d, (date, datetime)):
		return d.strftime("%Y-%m-%d")
	return str(d)


@frappe.whitelist()
def test_connection():
	"""Whitelisted: try to obtain a token, and if any enabled account
	mapping exists, one balance call too. Returns a plain success/message
	dict - the token and secret never leave the server."""
	settings = get_settings()
	result = {"success": False, "message": ""}

	try:
		get_access_token(force_refresh=True)
		message = "Authenticated with Bank of Georgia successfully."

		mapping = frappe.db.get_value(
			"BOG Account Mapping",
			{"enabled": 1},
			["name", "bog_account_number", "bog_currency"],
			as_dict=True,
		)
		if mapping:
			balance = fetch_balance(mapping.bog_account_number, mapping.bog_currency)
			message += (
				f" Balance check on {mapping.bog_account_number} ({mapping.bog_currency}) "
				f"also succeeded: {json.dumps(balance)[:300]}"
			)
		else:
			message += " No account mapping is set up yet, so balance/statement access was not tested."

		result["success"] = True
		result["message"] = message
	except BOGAPIError as e:
		result["message"] = str(e)
	except Exception as e:  # noqa: BLE001 - surface anything unexpected to the user too
		frappe.log_error(frappe.get_traceback(), "BOG Connector: test_connection")
		result["message"] = f"Unexpected error: {e}"

	settings.db_set("last_test_datetime", now_datetime(), update_modified=False)
	settings.db_set("last_test_result", result["message"], update_modified=False)
	return result


def _parse_entry_date(value):
	"""BOG's documented example fields don't pin down one exact date format,
	so try the common ones and fall back to frappe's own parser."""
	if not value:
		return None
	for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y"):
		try:
			return datetime.strptime(value, fmt).date()
		except ValueError:
			continue
	try:
		return get_datetime(value).date()
	except Exception:
		return None


def _record_amounts(record):
	"""Return (deposit, withdrawal) as positive floats from a BOG statement
	record, coping with a couple of plausible field shapes."""
	debit = record.get("EntryAmountDebit")
	credit = record.get("EntryAmountCredit")
	if debit or credit:
		return float(credit or 0), float(debit or 0)

	amount = float(record.get("EntryAmount") or 0)
	if amount >= 0:
		return amount, 0.0
	return 0.0, abs(amount)


def _entry_id(record):
	return str(record.get("EntryId") or record.get("Id") or "")


def sync_one_mapping(mapping_name, manual=False):
	"""Sync a single BOG Account Mapping. Never raises - failures are
	captured in the return dict and in a BOG Sync Log entry, so one bad
	account never stops the others in sync_all()."""
	mapping = frappe.get_doc("BOG Account Mapping", mapping_name)
	log = {
		"mapping": mapping.name,
		"bank_account": mapping.bank_account,
		"status": "Success",
		"transactions_created": 0,
		"message": "",
	}

	try:
		settings = get_settings()
		if mapping.last_synced_date:
			start_date = get_datetime(mapping.last_synced_date).date() + timedelta(days=1)
		else:
			lookback = settings.default_lookback_days or 7
			start_date = date.today() - timedelta(days=lookback)
		end_date = date.today()

		if start_date > end_date:
			log["message"] = "Already up to date (nothing to fetch)."
		else:
			data = fetch_statement(mapping.bog_account_number, mapping.bog_currency, start_date, end_date)
			records = data.get("Records") or data.get("records") or []
			created = 0
			for record in records:
				if _create_bank_transaction(mapping, record):
					created += 1
			log["transactions_created"] = created
			log["message"] = (
				f"Fetched {len(records)} record(s) for {start_date} .. {end_date}, "
				f"created {created} new Bank Transaction(s)."
			)

		mapping.db_set("last_synced_date", end_date, update_modified=False)
		mapping.db_set("last_sync_datetime", now_datetime(), update_modified=False)
		mapping.db_set("last_sync_status", log["message"], update_modified=False)

	except BOGAPIError as e:
		log["status"] = "Error"
		log["message"] = str(e)
		mapping.db_set("last_sync_datetime", now_datetime(), update_modified=False)
		mapping.db_set("last_sync_status", f"Error: {e}", update_modified=False)
	except Exception as e:  # noqa: BLE001
		frappe.log_error(frappe.get_traceback(), "BOG Connector: sync_one_mapping")
		log["status"] = "Error"
		log["message"] = f"Unexpected error: {e}"
		mapping.db_set("last_sync_datetime", now_datetime(), update_modified=False)
		mapping.db_set("last_sync_status", log["message"], update_modified=False)

	frappe.get_doc(
		{
			"doctype": "BOG Sync Log",
			"sync_datetime": now_datetime(),
			**log,
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()  # noqa: F821 - explicit commit: this runs from the scheduler, outside a request

	return log


def _create_bank_transaction(mapping, record):
	entry_id = _entry_id(record)
	if not entry_id:
		return False

	reference_number = f"BOG-{entry_id}"
	if frappe.db.exists(
		"Bank Transaction", {"bank_account": mapping.bank_account, "reference_number": reference_number}
	):
		return False

	entry_date = _parse_entry_date(record.get("EntryDate")) or date.today()
	deposit, withdrawal = _record_amounts(record)
	description = record.get("EntryComment") or record.get("DocumentNomination") or ""

	doc = frappe.get_doc(
		{
			"doctype": "Bank Transaction",
			"date": entry_date,
			"bank_account": mapping.bank_account,
			"company": mapping.company,
			"currency": mapping.bog_currency,
			"deposit": deposit,
			"withdrawal": withdrawal,
			"description": description[:280],
			"reference_number": reference_number,
		}
	)
	doc.insert(ignore_permissions=True)
	doc.submit()
	return True


def sync_all(manual=False):
	mappings = frappe.get_all("BOG Account Mapping", filters={"enabled": 1}, pluck="name")
	settings = get_settings()

	if not mappings:
		message = "No enabled BOG Account Mapping found - nothing to sync."
		settings.db_set("last_sync_datetime", now_datetime(), update_modified=False)
		settings.db_set("last_sync_result", message, update_modified=False)
		frappe.db.commit()  # noqa: F821
		return message

	results = [sync_one_mapping(name, manual=manual) for name in mappings]
	created_total = sum(r["transactions_created"] for r in results)
	errors = [r for r in results if r["status"] == "Error"]

	summary = f"Synced {len(mappings)} account(s), created {created_total} transaction(s)."
	if errors:
		summary += f" {len(errors)} account(s) had errors - see BOG Sync Log."

	settings.db_set("last_sync_datetime", now_datetime(), update_modified=False)
	settings.db_set("last_sync_result", summary, update_modified=False)
	frappe.db.commit()  # noqa: F821
	return summary
