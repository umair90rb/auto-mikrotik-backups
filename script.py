from routeros_api import RouterOsApiPool
from ftplib import FTP
from datetime import datetime
import time
import os

# ======================
# CONFIG
# ======================
ROUTER_IP = "103.253.18.181"
USERNAME="mascot"
PASSWORD="root@4420"
FTP_PORT = 21
LOCAL_BACKUP_DIR = "./mikrotik_backups"

# ======================
# CONNECT API
# ======================
api_pool = RouterOsApiPool(
    "103.253.18.181",
    username="mascot",
    password="root@4420",
    plaintext_login=True
)
api = api_pool.get_api()

# ======================
# GET IDENTITY
# ======================
identity = api.get_resource('/system/identity').get()[0]['name']

# ======================
# CREATE FILENAME
# ======================
timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
filename = f"{identity}-{timestamp}"

print(f"[+] Creating export: {filename}.rsc")

# ======================
# RUN EXPORT COMMAND
# ======================
api.get_binary_resource('/').call(
    'export',
    {
        'file': filename,
        'show-sensitive': 'yes'
    }
)

# Give router time to write file
time.sleep(3)

# ======================
# DOWNLOAD VIA FTP
# ======================
os.makedirs(LOCAL_BACKUP_DIR, exist_ok=True)
local_file = f"{LOCAL_BACKUP_DIR}/{filename}.rsc"

print("[+] Connecting via FTP...")
ftp = FTP()
ftp.connect(ROUTER_IP, FTP_PORT, timeout=10)
ftp.login(USERNAME, PASSWORD)

with open(local_file, "wb") as f:
    ftp.retrbinary(f"RETR {filename}.rsc", f.write)

ftp.quit()

print(f"[+] Backup downloaded: {local_file}")

# ======================
# OPTIONAL: DELETE FILE FROM ROUTER
# ======================
files = api.get_resource('/file')
for f in files.get():
    if f['name'] == f"{filename}.rsc":
        files.remove(id=f['.id'])
        print("[+] Remote file deleted")

# ======================
# DISCONNECT
# ======================
api_pool.disconnect()
print("[✓] Done")
