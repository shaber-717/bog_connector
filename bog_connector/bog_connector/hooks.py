app_name = "bog_connector"
app_title = "BOG Connector"
app_publisher = "Talorim"
app_description = "Bank of Georgia Business Online API integration: syncs account statements into ERPNext Bank Transaction records."
app_email = "shalva@talorim.com"
app_license = "mit"

# Scheduled Tasks
# ---------------
# Runs every 15 minutes. The task itself checks the "Enabled" checkbox on
# BOG Integration Settings and exits immediately if syncing is switched off,
# so this cron entry does not need to change when the user toggles the
# integration on or off from the UI.
scheduler_events = {
	"cron": {
		"*/15 * * * *": [
			"bog_connector.banking.tasks.scheduled_sync"
		]
	}
}

# Fixtures (none needed - doctypes ship as normal app doctypes)
