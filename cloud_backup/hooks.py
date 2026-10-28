app_name = "cloud_backup"
app_title = "Cloud Backup"
app_publisher = "SF Group"
app_description = "Full ERPNext backup (database + site files) pushed to OneDrive/SharePoint via rclone"
app_license = "MIT"
app_email = "jmsengi@sfgroup.co.tz"

# Runs every hour; scheduled_backup only acts if "Enable Scheduled Backup" is
# ticked AND the configured interval ("Backup Every N Hours") has elapsed.
scheduler_events = {
    "cron": {
        "0 * * * *": ["cloud_backup.api.scheduled_backup"],
    }
}

# Creates the desk buttons (Test Connection / Backup Now / Run Command) as a
# Client Script so they work on every install without needing a bench build.
after_migrate = ["cloud_backup.install.after_migrate"]
