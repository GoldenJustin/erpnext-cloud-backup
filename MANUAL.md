# Cloud Backup — Operator Manual

This app backs up your **full ERPNext system** to OneDrive/SharePoint, unattended, every day.
Everything below is done from the ERPNext desk (System Manager). No SSH to the server.

---

## 1. What gets backed up

Every run produces these files and uploads them to your OneDrive/SharePoint:

| File | Contents |
|------|----------|
| `…-database.sql.gz` | **The database** — every doctype, record, transaction |
| `…-apps.tar.gz` | **The apps** — your custom app source code (icd_tz, gate_control, etc.) |
| `…-files.tar` | public site files (uploads) |
| `…-private-files.tar` | private files |
| `…-site_config_backup.json` | site configuration |

So a single backup is a full system restore point: **database + apps + files + config**.

---

## 2. The Console (in the settings form)

Open **Cloud Backup Settings**. At the bottom there is an **"rclone Console"** section:

- **Command** — a code editor box. Type an rclone command here.
- **Output** — read-only code box showing the result.
- **Run Command** button (top of the form) — executes the command.

Useful commands while connecting:

| Command | What it does |
|---------|--------------|
| `listremotes` | list the remotes defined by your pasted config |
| `config show` | print the config (check your paste is intact) |
| `lsd onedrive:` | list folders at the remote root |
| `about onedrive:` | show storage used / quota |
| `size onedrive:ERPNextBackups` | total size of your backup folder |

---

## 3. Get your OneDrive connection details

You need **one block of text** — the rclone config. Two ways to get it.

### Option A — copy it from your Odoo server (fastest, recommended)

Odoo is already connected, so the config already exists there.

1. On the Odoo server, run:
   ```bash
   rclone config show
   ```
2. Find the `[onedrive]` (or similarly named) section. Copy **the whole block** — from the
   `[name]` line down to just before the next `[section]`. It looks like:
   ```ini
   [onedrive]
   type = onedrive
   client_id = 12345678-1234-…
   client_secret = xxxxxxxx…
   token = {"access_token":"…","expiry":"…","refresh_token":"…"}
   drive_id = b!xxxxxxxx
   drive_type = business
   ```
3. Go to **ERPNext → Cloud Backup Settings → "rclone Config (paste content)"** and paste it.
4. In **"rclone Remote"**, type the name in the square brackets — e.g. `onedrive`.

Done. The token is already valid; no re-login needed.

### Option B — create your own app registration (if you want a fresh one)

Only needed if you can't reach the Odoo box or want a separate remote. Click-by-click:

1. Open **https://portal.azure.com** → **Microsoft Entra ID** (or "Azure Active Directory") → **App registrations** → **+ New registration**.
2. **Name**: `ERPNext Backup`.
3. **Supported account types**: *"Accounts in this organizational directory only"* (single tenant — your company).
4. **Redirect URI**: platform **Web**, value `http://localhost:53682/`.
5. Click **Register**.
6. On the app's Overview page, copy **Application (client) ID** → this is your `client_id`.
7. Copy **Directory (tenant) ID** → this is your `tenant`.
8. Left menu → **Certificates & secrets** → **+ New client secret** → (name, expiry) → **Add**.
   Copy the **Value** column (NOT the Secret ID) → this is your `client_secret`.
9. Left menu → **API permissions** → **+ Add a permission** → **Microsoft Graph** → **Delegated permissions** → tick:
   - `Files.ReadWrite`
   - `offline_access`
   - `User.Read`
   → **Add permissions**, then click **Grant admin consent for <your org>** (needs a Global Admin).
10. On any machine that has **rclone and a browser** (your laptop, or the Odoo server), run:
    ```bash
    rclone config create onedrive onedrive client_id=<client_id> client_secret=<client_secret> region=global
    rclone authorize onedrive
    ```
    The second command opens a browser → sign in with your Microsoft 365 account → approve.
11. After it finishes, run `rclone config show`, copy the `[onedrive]` block, and paste it into
    **Cloud Backup Settings → "rclone Config (paste content)"**.

---

## 4. Connect and test (in ERPNext)

1. Desk → search **Cloud Backup Settings**.
2. Fill in:
   - **rclone Config (paste content)** → the block from step 3.
   - **rclone Remote** → the name in the brackets, e.g. `onedrive`.
   - **Destination Folder** → e.g. `ERPNextBackups` (the OneDrive folder that holds the backup sub-folders).
   - **Backup Every (hours)** → how often the automatic backup runs, e.g. `24` (daily) or `12` (twice a day). Set `0` to turn automatic backup off (manual only).
   - **Backup Slots (keep last N)** → how many backup folders to keep, e.g. `3` (older ones are deleted automatically).
   - **Backup Contents** → tick which parts to include: database (SQL), public files, private files, site config, app code.
   - **Send Email After Each Backup** → tick to email after every run.
   - **Email Recipients** → addresses or ERPNext user names to email (uses the site's outgoing email account).
   - **Email Subject / Message** → pre-filled template you can edit (placeholders `{status}`, `{site}`, `{time}`, `{last_backup}`, `{last_upload}`, `{remote}`, `{files}`).
3. Click **Save**.
4. Click **Test Connection** → should show `Connected: …`.
   - If it errors, open the Console and run `listremotes` then `config show` to see what's wrong.
5. Click **Backup & Upload Now** → the app creates the full backup and uploads it.
   Check OneDrive for the `ERPNextBackups` folder with the `.sql.gz`, `.tar`, `.tar.gz` files.
6. Set **Backup Every (hours)** (e.g. `24`) and **Save** → it now runs automatically every
   **Backup Every (hours)**, and each run goes into its own timestamped sub-folder under
   `ERPNextBackups` (e.g. `ERPNextBackups/20261104_023000/`), keeping only the latest
   **N** folders.

---

## 5. Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| "rclone is not installed on this host" | the binary isn't in `apps-src/cloud_backup/bin/rclone` — ask whoever manages the server |
| Test Connection shows `config file not found` | you didn't paste the config, or the pasted block is incomplete |
| `Failed to configure token` | the `token` line in your paste is missing or expired — redo Option A/B |
| Upload fails with a 401/403 | your Microsoft consent was revoked or the secret expired — redo Option B, grant consent |
| `didn't find section in config file` | the **rclone Remote** name doesn't match the `[name]` in the pasted config |
| Backup runs but OneDrive is empty | **Destination Folder** path is wrong — run `lsd onedrive:` in the console to find the right folder |
