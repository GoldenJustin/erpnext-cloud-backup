import frappe

CLIENT_SCRIPT = """frappe.ui.form.on("Cloud Backup Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Connection"), () => {
			frappe.call({ method: "cloud_backup.api.check_connection", freeze: true, freeze_message: __("Testing rclone connection..."), callback: (r) => frappe.msgprint(r.message) });
		});
		frm.add_custom_button(__("Backup & Upload Now"), () => {
			frappe.call({ method: "cloud_backup.api.run_backup_and_push", freeze: true, freeze_message: __("Backing up and uploading..."), callback: (r) => { frappe.msgprint(__("Backup and upload complete.")); frm.reload_doc(); } });
		});
		frm.add_custom_button(__("Run Command"), () => {
			const cmd = frm.doc.console_command;
			if (!cmd) { frappe.msgprint(__("Type an rclone command in the Command field first.")); return; }
			frappe.call({ method: "cloud_backup.api.run_console_command", args: { command: cmd }, freeze: true, freeze_message: __("Running rclone command..."), callback: (r) => { frm.reload_doc(); frappe.msgprint({ title: __("rclone output"), message: r.message, indicator: "blue" }); } });
		});
	},
});
"""


def after_migrate():
    """Ensure the desk buttons exist as a Client Script on every install/migrate."""
    try:
        if not frappe.db.exists("DocType", "Cloud Backup Settings"):
            return
        if not frappe.db.exists("Client Script", {"dt": "Cloud Backup Settings"}):
            frappe.get_doc({
                "doctype": "Client Script",
                "name": "Cloud Backup Settings",
                "dt": "Cloud Backup Settings",
                "enabled": 1,
                "script": CLIENT_SCRIPT,
            }).insert(ignore_permissions=True)
            frappe.db.commit()
    except Exception:
        frappe.log_error(title="Cloud Backup client script", message=frappe.get_traceback())
