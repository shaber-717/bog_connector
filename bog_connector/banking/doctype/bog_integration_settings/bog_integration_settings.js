// Copyright (c) 2026, Talorim and contributors
// For license information, please see license.txt

frappe.ui.form.on("BOG Integration Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Connection"), () => {
			frappe.show_alert({ message: __("Contacting Bank of Georgia..."), indicator: "blue" });
			frm.call("test_connection").then((r) => {
				frm.reload_doc();
				if (r.message && r.message.success) {
					frappe.msgprint({
						title: __("Connection OK"),
						indicator: "green",
						message: r.message.message,
					});
				} else {
					frappe.msgprint({
						title: __("Connection Failed"),
						indicator: "red",
						message: (r.message && r.message.message) || __("Unknown error"),
					});
				}
			});
		});

		frm.add_custom_button(__("Sync Now"), () => {
			frappe.show_alert({ message: __("Starting sync..."), indicator: "blue" });
			frm.call("sync_now").then((r) => {
				frm.reload_doc();
				frappe.msgprint({
					title: __("Sync Finished"),
					indicator: "green",
					message: (r.message && r.message.message) || __("Sync complete. See BOG Sync Log for details."),
				});
			});
		});

		frm.add_custom_button(__("View Sync Logs"), () => {
			frappe.set_route("List", "BOG Sync Log");
		});

		frm.add_custom_button(__("View Account Mappings"), () => {
			frappe.set_route("List", "BOG Account Mapping");
		});
	},
});
