"""
Backup Scheduler using APScheduler
"""
from flask_apscheduler import APScheduler
import json
import os
from datetime import datetime
import config

scheduler = APScheduler()

JOB_ID = 'backup_all_routers'


def load_settings():
    """Load settings from JSON file."""
    if os.path.exists(config.SETTINGS_FILE):
        with open(config.SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return config.DEFAULT_SETTINGS.copy()


def save_settings(settings):
    """Save settings to JSON file."""
    os.makedirs(os.path.dirname(config.SETTINGS_FILE), exist_ok=True)
    with open(config.SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)


def load_routers():
    """Load routers from JSON file."""
    if os.path.exists(config.ROUTERS_FILE):
        with open(config.ROUTERS_FILE, 'r') as f:
            return json.load(f)
    return []


def load_backup_log():
    """Load backup log from JSON file."""
    if os.path.exists(config.BACKUP_LOG_FILE):
        with open(config.BACKUP_LOG_FILE, 'r') as f:
            return json.load(f)
    return []


def save_backup_log(log):
    """Save backup log to JSON file."""
    os.makedirs(os.path.dirname(config.BACKUP_LOG_FILE), exist_ok=True)
    # Keep only last 100 entries
    log = log[-100:]
    with open(config.BACKUP_LOG_FILE, 'w') as f:
        json.dump(log, f, indent=2)


def add_log_entry(entry):
    """Add an entry to the backup log."""
    log = load_backup_log()
    log.append(entry)
    save_backup_log(log)


def scheduled_backup_job():
    """
    Job function to backup all routers.
    This runs within the Flask app context.
    """
    from utils.backup import create_backup
    from utils.gdrive import gdrive_client

    print(f"[Scheduler] Starting scheduled backup at {datetime.now().isoformat()}")

    settings = load_settings()
    routers = load_routers()

    if not routers:
        print("[Scheduler] No routers configured")
        return

    folder_id = settings.get('google_drive_folder_id', '') or None  # Convert empty string to None
    delete_local = settings.get('delete_local_after_upload', False)
    gdrive_authorized = gdrive_client.is_authorized()

    for router in routers:
        print(f"[Scheduler] Backing up {router.get('name', router.get('ip'))}")

        result = create_backup(router)
        log_entry = result.to_dict()
        log_entry['triggered_by'] = 'scheduler'

        # Upload to Google Drive if authorized
        if result.success and result.local_files and gdrive_authorized:
            drive_files = []
            drive_errors = []
            for local_file in result.local_files:
                success, drive_result = gdrive_client.upload_file(local_file, folder_id)
                if success:
                    drive_files.append({
                        'id': drive_result.get('id'),
                        'name': drive_result.get('name'),
                        'link': drive_result.get('link')
                    })
                    print(f"[Scheduler] Uploaded to Drive: {drive_result.get('name')}")

                    # Delete local file if configured
                    if delete_local and os.path.exists(local_file):
                        os.remove(local_file)
                else:
                    drive_errors.append(drive_result)
                    print(f"[Scheduler] Drive upload failed: {drive_result}")

            if drive_files:
                log_entry['drive_files'] = drive_files

                # Delete old backups from Drive after successful upload
                if result.local_files:
                    filename = os.path.basename(result.local_files[0])
                    router_identity = '-'.join(filename.split('-')[:-1])
                    if router_identity:
                        gdrive_client.delete_old_backups(router_identity, folder_id, keep_latest=12)
                        print(f"[Scheduler] Cleaned up old backups for {router_identity}")

            if drive_errors:
                log_entry['drive_errors'] = drive_errors
            if drive_files and delete_local:
                log_entry['local_deleted'] = True

        add_log_entry(log_entry)

    print(f"[Scheduler] Backup job completed at {datetime.now().isoformat()}")


def update_scheduler(app):
    """
    Update the scheduler based on current settings.
    """
    settings = load_settings()

    # Remove existing job if it exists
    if scheduler.get_job(JOB_ID):
        scheduler.remove_job(JOB_ID)

    if not settings.get('schedule_enabled', False):
        print("[Scheduler] Scheduling disabled")
        return

    schedule_type = settings.get('schedule_type', 'interval')

    if schedule_type == 'interval':
        hours = settings.get('schedule_interval_hours', 24)
        scheduler.add_job(
            id=JOB_ID,
            func=scheduled_backup_job,
            trigger='interval',
            hours=hours
        )
        print(f"[Scheduler] Scheduled backup every {hours} hours")

    elif schedule_type == 'cron':
        hour = settings.get('schedule_cron_hour', 2)
        minute = settings.get('schedule_cron_minute', 0)
        scheduler.add_job(
            id=JOB_ID,
            func=scheduled_backup_job,
            trigger='cron',
            hour=hour,
            minute=minute
        )
        print(f"[Scheduler] Scheduled backup daily at {hour:02d}:{minute:02d}")


def init_scheduler(app):
    """Initialize the scheduler with the Flask app."""
    scheduler.init_app(app)
    scheduler.start()
    update_scheduler(app)
    print("[Scheduler] Initialized")
