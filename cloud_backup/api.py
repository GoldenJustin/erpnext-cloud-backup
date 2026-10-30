import configparser
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile

import frappe
import requests
from frappe.utils import now_datetime
from frappe.utils.backups import backup

GRAPH = "https://graph.microsoft.com/v1.0"

# rclone's built-in OneDrive OAuth app (public, shared). Used when the pasted
# rclone.conf has no explicit client_id/client_secret (the common default setup).
RCLONE_CLIENT_ID = "b15665d9-eda6-4092-8539-0eec376afd59"
RCLONE_CLIENT_SECRET = "qtyfaBBYA403=unZUP40~_#"


def _backups_dir():
    return frappe.utils.get_site_path("private", "backups")


def _backup_apps():
    """Tar the custom apps (apps-src) so the backup covers code as well as the DB."""
    apps_src = os.path.join(os.path.dirname(frappe.get_site_path()), "apps-src")
    if not os.path.isdir(apps_src):
        return None  # apps are managed elsewhere (standard bench / Frappe Cloud)
    ts = now_datetime().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(_backups_dir(), f"{ts}-apps.tar.gz")
    subprocess.run(
        [
            "tar", "czf", dest,
            "--exclude=bin", "--exclude=.git", "--exclude=__pycache__", "--exclude=*.pyc",
            "-C", os.path.dirname(apps_src), os.path.basename(apps_src),
        ],
        capture_output=True,
        check=True,
    )
    return dest


# --------------------------------------------------------------------------
# Microsoft Graph connection, parsed from the pasted rclone.conf
# --------------------------------------------------------------------------

def _conn(settings):
    """Parse the pasted rclone.conf into the Graph connection details."""
    content = (settings.rclone_config_content or "").strip()
    if not content:
        frappe.throw("Paste your rclone.conf into 'rclone Config (paste content)' first")
    cp = configparser.ConfigParser()
    try:
        cp.read_string(content)
    except configparser.Error as e:
        frappe.throw(f"Could not parse the pasted config: {e}")
    section = (settings.remote or "").strip().rstrip("/").split(":")[0].strip()
    if section not in cp.sections():
        frappe.throw(f"Remote '{section}' not found in the pasted config. Found: {cp.sections()}")
    sec = cp[section]
    try:
        token = json.loads(sec.get("token", "{}") or "{}")
    except json.JSONDecodeError:
        frappe.throw("The 'token' value in the pasted config is not valid JSON")
    conn = {
        "client_id": (sec.get("client_id") or "").strip() or RCLONE_CLIENT_ID,
        "client_secret": (sec.get("client_secret") or "").strip() or RCLONE_CLIENT_SECRET,
        "refresh_token": token.get("refresh_token") or "",
        "drive_type": (sec.get("drive_type") or "business").strip(),
        "drive_id": (sec.get("drive_id") or "").strip(),
    }
    if not conn["client_id"] or not conn["refresh_token"]:
        frappe.throw("The pasted config is missing a refresh token")
    return conn


def _get_token(settings):
    conn = _conn(settings)
    tenant = (settings.tenant or "").strip() or "common"
    data = {
        "grant_type": "refresh_token",
        "client_id": conn["client_id"],
        "refresh_token": conn["refresh_token"],
        "scope": "https://graph.microsoft.com/Files.ReadWrite offline_access",
    }
    if conn["client_secret"]:
        data["client_secret"] = conn["client_secret"]
    resp = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data=data,
        timeout=60,
    )
    if resp.status_code != 200:
        frappe.throw(f"Microsoft login failed ({resp.status_code}): {resp.text[:600]}")
    token = resp.json().get("access_token")
    if not token:
        frappe.throw("Microsoft login returned no access token")
    return token


def _root(conn):
    if conn["drive_type"] == "personal" or not conn["drive_id"]:
        return "me/drive"
    return f"drives/{conn['drive_id']}"


def _hdr(token, ctype="application/json"):
    h = {"Authorization": f"Bearer {token}"}
    if ctype:
        h["Content-Type"] = ctype
    return h


def _upload(token, root, path, local_path):
    dest = f"{GRAPH}/{root}/root:/{path}"
    size = os.path.getsize(local_path)
    if size < 4 * 1024 * 1024:
        with open(local_path, "rb") as f:
            r = requests.put(dest + ":/content", headers=_hdr(token, "application/octet-stream"), data=f.read(), timeout=900)
        if r.status_code not in (200, 201):
            frappe.throw(f"Upload failed ({r.status_code}): {r.text[:600]}")
        return
    r = requests.post(
        dest + ":/createUploadSession",
        headers=_hdr(token),
        json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
        timeout=120,
    )
    if r.status_code != 200:
        frappe.throw(f"Upload session failed ({r.status_code}): {r.text[:600]}")
    upload_url = r.json()["uploadUrl"]
    chunk = 8 * 1024 * 1024
    with open(local_path, "rb") as f:
        offset = 0
        while True:
            data = f.read(chunk)
            if not data:
                break
            end = offset + len(data) - 1
            r = requests.put(
                upload_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Length": str(len(data)),
                    "Content-Range": f"bytes {offset}-{end}/{size}",
                },
                data=data,
                timeout=900,
            )
            if r.status_code not in (200, 201, 202):
                frappe.throw(f"Chunk upload failed ({r.status_code}): {r.text[:600]}")
            offset += len(data)


def _list_folders(token, root, path):
    url = f"{GRAPH}/{root}/root:/{path}:/children"
    r = requests.get(url, headers=_hdr(token), timeout=120)
    if r.status_code == 404:
        return []  # folder doesn't exist yet
    if r.status_code != 200:
        frappe.throw(f"List folders failed ({r.status_code}): {r.text[:600]}")
    return [i["name"] for i in r.json().get("value", []) if "folder" in i]


def _purge(token, root, path):
    r = requests.delete(f"{GRAPH}/{root}/root:/{path}", headers=_hdr(token), timeout=300)
    if r.status_code not in (200, 204, 404):
        frappe.log_error(f"Purge failed ({r.status_code}): {r.text[:600]}")


# --------------------------------------------------------------------------
# Whitelisted methods
# --------------------------------------------------------------------------

@frappe.whitelist()
def check_connection():
    settings = frappe.get_single("Cloud Backup Settings")
    conn = _conn(settings)
    token = _get_token(settings)
    root = _root(conn)
    r = requests.get(f"{GRAPH}/{root}/root", headers=_hdr(token), timeout=60)
    if r.status_code in (200, 404):
        return "Connected OK — Microsoft 365 is reachable. Ready for your first backup."
    frappe.throw(f"Connection failed ({r.status_code}): {r.text[:600]}")


def _new_files(before):
    after = set(os.listdir(_backups_dir()))
    return sorted(after - before)


@frappe.whitelist()
def run_backup_and_push():
    settings = frappe.get_single("Cloud Backup Settings")
    if not settings.rclone_config_content:
        frappe.throw("Paste your rclone.conf into 'rclone Config (paste content)' first")
    before = set(os.listdir(_backups_dir()))
    try:
        backup(with_files=True)  # database dump + site files + private files
        _backup_apps()  # custom app code (where present)
        settings.last_backup = now_datetime()
        _push(settings, before)
        settings.last_upload = now_datetime()
        settings.last_status = "OK"
    except Exception:
        settings.last_status = "FAILED"
        frappe.log_error(title="Cloud Backup", message=frappe.get_traceback())
        raise
    finally:
        settings.save(ignore_permissions=True)
        frappe.db.commit()
        _send_email(settings)
    return "Backup and upload complete"


def _push(settings, before):
    files = _new_files(before)
    if not files:
        return
    ts = None
    for f in files:
        if "database.sql.gz" in f:
            ts = f.split("-", 1)[0]
            break
    if not ts:
        ts = now_datetime().strftime("%Y%m%d_%H%M%S")
    conn = _conn(settings)
    token = _get_token(settings)
    root = _root(conn)
    base = (settings.remote_path or "").strip().strip("/")
    folder = f"{base}/{ts}" if base else ts
    for f in files:
        _upload(token, root, f"{folder}/{f}", os.path.join(_backups_dir(), f))
    _retain(token, root, base, int(settings.num_backups or 3))


def _retain(token, root, base, n):
    """Keep only the latest N timestamped folders; purge the rest."""
    if n <= 0:
        return
    folders = sorted(_list_folders(token, root, base))
    for old in folders[:-n]:
        _purge(token, root, f"{base}/{old}" if base else old)


def _fill(template, ctx):
    for k, v in ctx.items():
        template = template.replace("{" + k + "}", str(v))
    return template


def _resolve_recipients(settings):
    raw = settings.email_recipients
    if not raw:
        return []
    values = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            values = parsed if isinstance(parsed, list) else re.split(r"[,\n;]", raw)
        except (json.JSONDecodeError, ValueError):
            values = re.split(r"[,\n;]", raw)
    emails = []
    for v in values or []:
        v = str(v).strip()
        if not v:
            continue
        if "@" in v:
            emails.append(v)
        else:
            email = frappe.db.get_value("User", v, "email")
            if email:
                emails.append(email)
    return [e for e in emails if e]


def _send_email(settings):
    """Notify recipients after each backup, using the site's outgoing email account."""
    recipients = _resolve_recipients(settings)
    if not recipients:
        return
    status = settings.last_status or "UNKNOWN"
    ctx = {
        "status": status,
        "site": frappe.local.site,
        "time": now_datetime().strftime("%Y-%m-%d %H:%M"),
        "last_backup": str(settings.last_backup or ""),
        "last_upload": str(settings.last_upload or ""),
        "remote": settings.remote or "",
    }
    subject = _fill(settings.email_subject or "[{status}] ERPNext backup - {site} - {time}", ctx)
    message = _fill(settings.email_message or "Site: {site}\nStatus: {status}", ctx)
    try:
        frappe.sendmail(recipients=recipients, subject=subject, message=message)
    except Exception:
        frappe.log_error(title="Cloud Backup email", message=frappe.get_traceback())


def scheduled_backup():
    settings = frappe.get_single("Cloud Backup Settings")
    if not settings.enabled:
        return
    last = settings.last_backup
    if last:
        hours = int(settings.backup_every_hours or 24)
        if (now_datetime() - last).total_seconds() < hours * 3600:
            return
    run_backup_and_push()


# --------------------------------------------------------------------------
# Optional rclone console (only where the rclone binary exists)
# --------------------------------------------------------------------------

def _rclone_binary():
    bundled = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "rclone"
    )
    if os.path.isfile(bundled) and os.access(bundled, os.X_OK):
        return bundled
    path = shutil.which("rclone")
    if not path:
        frappe.throw("rclone is not installed on this host")
    return path


def _config_args(settings):
    if settings.rclone_config_content:
        fd, tmp = tempfile.mkstemp(prefix="rclone-", suffix=".conf")
        with os.fdopen(fd, "w") as f:
            f.write(settings.rclone_config_content)
        return ["--config", tmp], tmp
    if settings.rclone_config:
        return ["--config", settings.rclone_config], None
    return [], None


def _run(settings, args, timeout=21600):
    config_args, tmp = _config_args(settings)
    cmd = [_rclone_binary(), *args, *config_args]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


@frappe.whitelist()
def run_console_command(command):
    settings = frappe.get_single("Cloud Backup Settings")
    command = (command or "").strip()
    if not command:
        frappe.throw("Enter an rclone command, e.g. listremotes, config show, lsd onedrive:, about onedrive:")
    args = shlex.split(command)
    if args and args[0] == "rclone":
        args = args[1:]
    result = _run(settings, args, timeout=300)
    output = (result.stdout or "") + (result.stderr or "")
    frappe.db.set_value("Cloud Backup Settings", "Cloud Backup Settings", "console_output", output)
    frappe.db.commit()
    return output
