"""
MikroTik Backup Utility
Adapted from original script.py
"""
from routeros_api import RouterOsApiPool
from ftplib import FTP
from datetime import datetime
import time
import os
import config


class BackupResult:
    def __init__(self, success, router_id, router_name, message, local_files=None):
        self.success = success
        self.router_id = router_id
        self.router_name = router_name
        self.message = message
        self.local_files = local_files or []  # List of file paths
        self.timestamp = datetime.now().isoformat()

    def to_dict(self):
        return {
            'success': self.success,
            'router_id': self.router_id,
            'router_name': self.router_name,
            'message': self.message,
            'local_files': self.local_files,
            'timestamp': self.timestamp
        }


def create_backup(router):
    """
    Create a backup for a single router.
    Generates both .rsc (export) and .backup (binary) files.

    Args:
        router: dict with keys: id, name, ip, username, password, ftp_port, api_port

    Returns:
        BackupResult object
    """
    router_id = router.get('id')
    router_name = router.get('name', router.get('ip'))
    router_ip = router['ip']
    username = router['username']
    password = router['password']
    ftp_port = router.get('ftp_port', config.DEFAULT_FTP_PORT)
    api_port = router.get('api_port', config.DEFAULT_API_PORT)

    api_pool = None
    ftp = None
    local_files = []

    try:
        # Connect to MikroTik API
        api_pool = RouterOsApiPool(
            router_ip,
            username=username,
            password=password,
            port=api_port,
            plaintext_login=True
        )
        api = api_pool.get_api()

        # Get router identity
        try:
            identity = api.get_resource('/system/identity').get()[0]['name']
        except Exception:
            identity = router_name

        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{identity}-{timestamp}"

        # Ensure backup directory exists
        os.makedirs(config.BACKUP_DIR, exist_ok=True)

        # 1. Create .rsc export file (text-based config)
        # Try with show-sensitive first, fall back without it for older RouterOS
        try:
            api.get_binary_resource('/').call(
                'export',
                {
                    'file': filename.encode() if isinstance(filename, str) else filename,
                    'show-sensitive': b'yes'
                }
            )
        except Exception as e:
            if 'unknown parameter' in str(e).lower():
                # Older RouterOS doesn't support show-sensitive
                api.get_binary_resource('/').call(
                    'export',
                    {
                        'file': filename.encode() if isinstance(filename, str) else filename,
                    }
                )
            else:
                raise

        # 2. Create .backup file (binary backup)
        api.get_binary_resource('/system/backup').call(
            'save',
            {
                'name': filename.encode() if isinstance(filename, str) else filename,
            }
        )

        # Wait for router to write files
        time.sleep(5)

        # Download via FTP
        ftp = FTP()
        ftp.connect(router_ip, ftp_port, timeout=30)
        ftp.login(username, password)

        # Download .rsc file
        local_rsc = os.path.join(config.BACKUP_DIR, f"{filename}.rsc")
        try:
            with open(local_rsc, "wb") as f:
                ftp.retrbinary(f"RETR {filename}.rsc", f.write)
            local_files.append(local_rsc)
        except Exception as e:
            print(f"Warning: Could not download .rsc file: {e}")

        # Download .backup file
        local_backup = os.path.join(config.BACKUP_DIR, f"{filename}.backup")
        try:
            with open(local_backup, "wb") as f:
                ftp.retrbinary(f"RETR {filename}.backup", f.write)
            local_files.append(local_backup)
        except Exception as e:
            print(f"Warning: Could not download .backup file: {e}")

        ftp.quit()
        ftp = None

        # Delete files from router
        try:
            files = api.get_resource('/file')
            for file_entry in files.get():
                file_name = file_entry.get('name', '')
                if file_name in [f"{filename}.rsc", f"{filename}.backup"]:
                    files.remove(id=file_entry['.id'])
        except Exception:
            pass  # Non-critical if deletion fails

        if not local_files:
            return BackupResult(
                success=False,
                router_id=router_id,
                router_name=router_name,
                message="Backup failed: Could not download any backup files"
            )

        file_names = [os.path.basename(f) for f in local_files]
        return BackupResult(
            success=True,
            router_id=router_id,
            router_name=router_name,
            message=f"Backup created: {', '.join(file_names)}",
            local_files=local_files
        )

    except Exception as e:
        return BackupResult(
            success=False,
            router_id=router_id,
            router_name=router_name,
            message=f"Backup failed: {str(e)}"
        )

    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
                pass
        if api_pool:
            try:
                api_pool.disconnect()
            except Exception:
                pass


def test_connection(router):
    """
    Test connection to a router.

    Returns:
        tuple: (success: bool, message: str)
    """
    router_ip = router['ip']
    username = router['username']
    password = router['password']
    api_port = router.get('api_port', config.DEFAULT_API_PORT)

    api_pool = None

    try:
        api_pool = RouterOsApiPool(
            router_ip,
            username=username,
            password=password,
            port=api_port,
            plaintext_login=True
        )
        api = api_pool.get_api()

        # Try to get identity as a test
        identity = api.get_resource('/system/identity').get()[0]['name']

        return True, f"Connected successfully to '{identity}'"

    except Exception as e:
        return False, f"Connection failed: {str(e)}"

    finally:
        if api_pool:
            try:
                api_pool.disconnect()
            except Exception:
                pass
