import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Flask settings
SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-secret-key-in-production')
DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
PORT = int(os.environ.get('PORT', 5000))

# Admin credentials
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# Data files
DATA_DIR = os.path.join(BASE_DIR, 'data')
ROUTERS_FILE = os.path.join(DATA_DIR, 'routers.json')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')
BACKUP_LOG_FILE = os.path.join(DATA_DIR, 'backup_log.json')

# Backup directory
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')

# Google Drive OAuth2 credentials (can be set via environment variables)
# GOOGLE_CLIENT_SECRET - JSON string of client_secret.json
# GOOGLE_TOKEN - JSON string of token.json (after authorization)

# Default settings
DEFAULT_SETTINGS = {
    'schedule_enabled': False,
    'schedule_type': 'interval',  # 'interval' or 'cron'
    'schedule_interval_hours': 24,
    'schedule_cron_hour': 2,
    'schedule_cron_minute': 0,
    'google_drive_folder_id': '',
    'delete_local_after_upload': False
}

# MikroTik defaults
DEFAULT_API_PORT = 8728
DEFAULT_FTP_PORT = 21
