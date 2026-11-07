# ERPNext Cloud Backup

Backs up a whole ERPNext site to OneDrive or SharePoint, on a schedule. Each backup
covers the database, your custom app code, site files and site config, and uploads
them to your Microsoft 365 storage using rclone — the same tool you already use for
Odoo.

## Install

```bash
bench get-app https://github.com/GoldenJustin/erpnext-cloud-backup
bench --site your-site install-app cloud_backup
bench --site your-site migrate
bench --site your-site build --app cloud_backup
```

No `rclone` install needed — the app talks to Microsoft Graph directly. It reads your
connection from a pasted rclone.conf (see below), so it works on Frappe Cloud, plain
bench, and Docker/Coolify alike. There's an optional built-in rclone console for
environments that happen to have the rclone binary, but it isn't required.

## Quick start

1. Open **Cloud Backup Settings** in the desk (just search for it).
2. Get your rclone config: on the machine where you already use rclone (your Odoo
   box), run `rclone config show`, and copy the `[onedrive]` block.
3. Paste it into **"rclone Config (paste content)"**.
4. Set **rclone Remote** to the name in the square brackets — usually `onedrive`.
5. Set **Destination Folder** — e.g. `ERPNextBackups`.
6. Click **Test Connection**, then **Backup & Upload Now**.
7. Set **Backup Every (hours)** (e.g. `24` for daily) and **Backup Slots**, then Save.

That's it — it backs up on its own from then on.

## Settings, in plain words

- **Backup Every (hours)** — how often it backs up automatically. `24` = once a day,
  `12` = twice a day, `0` = automatic backup off (manual only).
- **Backup Slots (keep last N)** — how many recent backup folders to keep in the
  cloud. Each backup goes into its own timestamped folder; the oldest are deleted.
- **Backup Contents** — tick exactly which parts to back up: database (SQL), public
  site files, private files, site config, and custom app code.
- **Send Email After Each Backup** — on/off switch for notifications.
- **Email Recipients / Subject / Message** — who to notify (email addresses or
  ERPNext user names) and the message, using the site's outgoing email account. The
  subject and message are pre-filled with a template you can edit.

The form also has a small **rclone console** at the bottom for running commands like
`listremotes` or `lsd onedrive:` straight from the desk.

Full walkthrough (including where to click in Azure): [MANUAL.md](MANUAL.md).
