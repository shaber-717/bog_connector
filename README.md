# BOG Connector

A custom Frappe/ERPNext app that syncs Bank of Georgia "Business Online" account
statements into ERPNext `Bank Transaction` records automatically, every 15
minutes, via BOG's Open Banking API.

Built for Talorim's private Frappe Cloud bench. No marketplace app exists for
Bank of Georgia, so this app was written from scratch against BOG's published
API docs (https://api.bog.ge/docs/en/bonline/).

## What it does

- Authenticates to Bank of Georgia using OAuth2 `client_credentials` (your
  Client ID / Client Secret from the BOG Business Online API console).
- Every 15 minutes (configurable in `hooks.py` if you want a different
  cadence), pulls new statement entries for each account you map, and creates
  a matching ERPNext `Bank Transaction` for each one that isn't already there
  (deduplicated on BOG's own `EntryId`).
- Keeps a full audit trail in **BOG Sync Log** (one entry per sync attempt per
  account, success or failure).
- Never exposes your Client Secret or the OAuth access token anywhere in the
  UI, API responses, or logs - all of that stays server-side in Python.
- Includes a one-click **Test Connection** button so you can verify your
  credentials actually work before relying on the scheduled sync.

## What it does NOT do (yet)

- It does not touch, reconcile, or match transactions against invoices/Payment
  Entries - it only creates `Bank Transaction` records. Use ERPNext's own
  **Bank Reconciliation Tool** on top of the transactions this app creates.
  This was a deliberate scope decision: reconciliation logic is easy to get
  subtly wrong, and it's safer for you to review matches yourself the first
  few cycles.
- It only handles one bank (Bank of Georgia). It's built so a second app (or
  an extra module in this one) could add TBC or others later the same way,
  but that's out of scope for now.

## 1. Push this to GitHub

You (Shalva) are hosting this - create a new repository (private is fine) and
push everything in this folder to it, e.g.:

```bash
cd bog_connector
git init
git add .
git commit -m "Initial commit: BOG Connector app"
git branch -M main
git remote add origin https://github.com/<your-username>/bog_connector.git
git push -u origin main
```

## 2. Install the app on your Frappe Cloud bench

Your `talorim.com` site is now on a private bench (`bench-48260-000001-f9f`,
group "Talorim"), which supports custom apps from GitHub.

1. Frappe Cloud dashboard -> **Benches** -> your bench group ("Talorim") ->
   **Apps** tab -> **Add App**.
2. Choose **Add from GitHub**, paste the repo URL from step 1, click
   **Fetch Branches**, pick `main`.
3. Deploy the bench (Frappe Cloud will build a new bench image with the app
   installed - this takes a few minutes).
4. Once deployed: go to your **Site** (`talorim.com`) -> **Apps** -> **Install
   App** -> select `BOG Connector` -> Install.

If your bench group has other sites you do *not* want this on, only install it
on `talorim.com` at the site level (adding it to the bench just makes it
available, it doesn't force-install it everywhere).

## 3. Configure the account mapping

1. In ERPNext, go to **BOG Account Mapping** (new list) -> **New**.
2. Fill in:
   - **Company**: the Talorim company this account belongs to.
   - **ERPNext Bank Account**: your existing "Talorim - Main Account - Bank of
     Georgia" Bank Account record.
   - **BOG Account Number**: the account number as BOG shows it in Business
     Online (e.g. `GE23BG0000000533869093`).
   - **Currency**: GEL/USD/EUR/GBP as appropriate.
3. Leave **Enabled** checked, save.

You can add more than one mapping later if you connect more BOG accounts.

## 4. Enter and test your credentials

1. Go to **BOG Integration Settings** (Single doctype, one record for the
   whole site).
2. Enter your **Client ID** and **Client Secret** from the BOG Business Online
   API console. (Since these were listed as "untested so far", this step is
   where you'll find out if they actually work.)
3. Leave **Token URL** and **API Base URL** at their defaults unless BOG's
   docs/console tell you otherwise:
   - Token URL: `https://account.bog.ge/auth/realms/bog/protocol/openid-connect/token`
   - API Base URL: `https://api.businessonline.ge/api`
4. Save the document.
5. Click **Test Connection**. This will:
   - Try to obtain an OAuth token (proves Client ID/Secret + Token URL are
     correct).
   - If you've already created an account mapping, also try a real balance
     lookup on that account (proves the API Base URL and account number are
     correct too).
   - Show you a green "Connection OK" or a red "Connection Failed" with the
     actual error message from BOG - it never shows you the secret or token
     itself, just whether the call succeeded.
6. **If it fails:** the error message will tell you what failed (wrong
   credentials -> 401/403 on the token call; wrong base URL -> connection
   error or 404 on the balance call). The Token URL and API Base URL fields
   are editable specifically so you can correct them here without needing a
   new deploy, if BOG's actual endpoints turn out to differ slightly from
   what's in their public docs.

## 5. Sync

- **Automatic**: once `Enabled` is checked on BOG Integration Settings, the
  scheduler runs a sync every 15 minutes on its own - no further action
  needed.
- **Manual**: click **Sync Now** on BOG Integration Settings any time to run
  a sync immediately (useful right after setup, or to force a re-check).
- Check **BOG Sync Log** to see the result of every sync attempt (per
  account, with a record count and any error message).
- The first sync for a new mapping looks back **7 days** by default (change
  "Default Lookback (Days)" on BOG Integration Settings if you want more/less
  history pulled in on day one). Every sync after that only fetches from the
  day after the last successful sync, so it stays incremental.

## 6. Retire the old settings doctype

There's an older, manually-created **"Bank of Georgia Settings"** doctype from
before this app existed, with its own Client ID/Secret fields. It's no longer
used by anything - once you've entered your credentials into **BOG Integration
Settings** above and confirmed **Test Connection** works, that old doctype and
its stored credentials can be deleted. (Nothing in this app reads it.)

## Notes on rate limits

BOG's docs list a baseline of 5 requests/second, and daily-activity /
statement queries capped at roughly 800/day per account. A 15-minute sync
cadence (96 calls/day/account, one statement call each) is well inside that,
so this shouldn't need any tuning even with several accounts mapped.

## Files

```
bog_connector/                    - outer app directory (this is what you point Frappe Cloud at)
  bog_connector/                  - the actual importable Python package - hooks.py lives here.
                                     Frappe Cloud's "Add app from GitHub" validator specifically
                                     requires hooks.py at repo_root/<app_name>/<app_name>/hooks.py,
                                     so this extra level is intentional, not a packaging mistake.
    hooks.py                      - app config + scheduler registration (every 15 min)
    banking/                      - the app's one module (deliberately NOT named "bog_connector" -
                                     a module folder with the same name as the app package confused
                                     Frappe Cloud's validator in an earlier attempt, so this stays
                                     distinct)
      tasks.py                    - scheduler entry point (checks Enabled, calls sync_all)
      bog_api.py                  - all BOG API calls: auth, statement, balance, sync logic
      doctype/
        bog_integration_settings/ - Single: credentials, endpoints, Test Connection / Sync Now
        bog_account_mapping/      - list: which ERPNext Bank Account <-> which BOG account
        bog_sync_log/             - audit trail of every sync attempt
```
