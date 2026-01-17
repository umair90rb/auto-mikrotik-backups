"""
MikroTik Backup Manager - Flask Web Application
"""
import os

# Allow OAuth2 over HTTP for local development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import json
import uuid

import config
from utils.backup import create_backup, test_connection
from utils.gdrive import gdrive_client
from utils.scheduler import (
    init_scheduler, update_scheduler, load_settings, save_settings,
    load_routers, load_backup_log, add_log_entry, scheduler
)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# Simple User class for Flask-Login
class User(UserMixin):
    def __init__(self, user_id):
        self.id = user_id


@login_manager.user_loader
def load_user(user_id):
    if user_id == config.ADMIN_USERNAME:
        return User(user_id)
    return None


# Helper functions for router storage
def save_routers(routers):
    os.makedirs(os.path.dirname(config.ROUTERS_FILE), exist_ok=True)
    with open(config.ROUTERS_FILE, 'w') as f:
        json.dump(routers, f, indent=2)


def get_router_by_id(router_id):
    routers = load_routers()
    for router in routers:
        if router['id'] == router_id:
            return router
    return None


# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == config.ADMIN_USERNAME and password == config.ADMIN_PASSWORD:
            user = User(username)
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'success')
    return redirect(url_for('login'))


@app.route('/')
@login_required
def dashboard():
    routers = load_routers()
    backup_log = load_backup_log()
    settings = load_settings()

    # Get last backup for each router
    last_backups = {}
    for log in backup_log:
        router_id = log.get('router_id')
        if router_id:
            last_backups[router_id] = log  # Later entries overwrite earlier ones

    # Get next scheduled run time
    next_run = None
    schedule_enabled = settings.get('schedule_enabled', False)
    if schedule_enabled:
        job = scheduler.get_job('backup_all_routers')
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

    return render_template('dashboard.html', routers=routers, last_backups=last_backups,
                          next_run=next_run, schedule_enabled=schedule_enabled)


@app.route('/router/add', methods=['GET', 'POST'])
@login_required
def add_router():
    if request.method == 'POST':
        router = {
            'id': str(uuid.uuid4()),
            'name': request.form.get('name'),
            'ip': request.form.get('ip'),
            'username': request.form.get('username'),
            'password': request.form.get('password'),
            'api_port': int(request.form.get('api_port', 8728)),
            'ftp_port': int(request.form.get('ftp_port', 21))
        }

        routers = load_routers()
        routers.append(router)
        save_routers(routers)

        flash(f'Router "{router["name"]}" added successfully', 'success')
        return redirect(url_for('dashboard'))

    return render_template('add_router.html', router=None)


@app.route('/router/bulk-upload', methods=['GET', 'POST'])
@login_required
def bulk_upload():
    if request.method == 'POST':
        # Check if file was uploaded
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(url_for('bulk_upload'))

        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('bulk_upload'))

        if not file.filename.endswith('.json'):
            flash('Please upload a JSON file', 'error')
            return redirect(url_for('bulk_upload'))

        try:
            # Parse JSON content
            content = file.read().decode('utf-8')
            new_routers = json.loads(content)

            if not isinstance(new_routers, list):
                flash('JSON must be an array of routers', 'error')
                return redirect(url_for('bulk_upload'))

            # Validate and add routers
            routers = load_routers()
            existing_ips = {r['ip'] for r in routers}
            added = 0
            skipped = 0

            for router_data in new_routers:
                # Validate required fields
                if not all(key in router_data for key in ['name', 'ip', 'username', 'password']):
                    skipped += 1
                    continue

                # Skip if IP already exists
                if router_data['ip'] in existing_ips:
                    skipped += 1
                    continue

                router = {
                    'id': str(uuid.uuid4()),
                    'name': router_data['name'],
                    'ip': router_data['ip'],
                    'username': router_data['username'],
                    'password': router_data['password'],
                    'api_port': int(router_data.get('api_port', 8728)),
                    'ftp_port': int(router_data.get('ftp_port', 21))
                }
                routers.append(router)
                existing_ips.add(router['ip'])
                added += 1

            save_routers(routers)

            if added > 0:
                flash(f'Successfully added {added} router(s)', 'success')
            if skipped > 0:
                flash(f'Skipped {skipped} router(s) (duplicate IP or missing fields)', 'warning')

            return redirect(url_for('dashboard'))

        except json.JSONDecodeError:
            flash('Invalid JSON file', 'error')
            return redirect(url_for('bulk_upload'))
        except Exception as e:
            flash(f'Error processing file: {str(e)}', 'error')
            return redirect(url_for('bulk_upload'))

    return render_template('bulk_upload.html')


@app.route('/router/<router_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_router(router_id):
    routers = load_routers()
    router = None
    router_index = None

    for i, r in enumerate(routers):
        if r['id'] == router_id:
            router = r
            router_index = i
            break

    if router is None:
        flash('Router not found', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        router['name'] = request.form.get('name')
        router['ip'] = request.form.get('ip')
        router['username'] = request.form.get('username')
        router['password'] = request.form.get('password')
        router['api_port'] = int(request.form.get('api_port', 8728))
        router['ftp_port'] = int(request.form.get('ftp_port', 21))

        routers[router_index] = router
        save_routers(routers)

        flash(f'Router "{router["name"]}" updated successfully', 'success')
        return redirect(url_for('dashboard'))

    return render_template('add_router.html', router=router)


@app.route('/router/<router_id>/delete', methods=['POST'])
@login_required
def delete_router(router_id):
    routers = load_routers()
    router_name = None

    for i, r in enumerate(routers):
        if r['id'] == router_id:
            router_name = r['name']
            routers.pop(i)
            break

    if router_name:
        save_routers(routers)
        flash(f'Router "{router_name}" deleted', 'success')
    else:
        flash('Router not found', 'error')

    return redirect(url_for('dashboard'))


@app.route('/router/<router_id>/test', methods=['POST'])
@login_required
def test_router(router_id):
    router = get_router_by_id(router_id)

    if router is None:
        flash('Router not found', 'error')
        return redirect(url_for('dashboard'))

    success, message = test_connection(router)

    if success:
        flash(f'{router["name"]}: {message}', 'success')
    else:
        flash(f'{router["name"]}: {message}', 'error')

    return redirect(url_for('dashboard'))


@app.route('/backup/<router_id>', methods=['POST'])
@login_required
def backup_single(router_id):
    router = get_router_by_id(router_id)

    if router is None:
        flash('Router not found', 'error')
        return redirect(url_for('dashboard'))

    result = create_backup(router)
    log_entry = result.to_dict()
    log_entry['triggered_by'] = 'manual'

    # Upload to Google Drive if authorized
    settings = load_settings()
    folder_id = settings.get('google_drive_folder_id', '') or None  # Convert empty string to None

    if result.success and result.local_files and gdrive_client.is_authorized():
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
                # Delete local if configured
                if settings.get('delete_local_after_upload', False):
                    if os.path.exists(local_file):
                        os.remove(local_file)
            else:
                drive_errors.append(drive_result)

        if drive_files:
            log_entry['drive_files'] = drive_files
            flash(f'{len(drive_files)} file(s) uploaded to Google Drive', 'success')

            # Delete old backups from Drive after successful upload
            # Extract router identity from filename (format: identity-timestamp.ext)
            if result.local_files:
                filename = os.path.basename(result.local_files[0])
                # Remove timestamp and extension to get identity
                router_identity = '-'.join(filename.split('-')[:-1])
                if router_identity:
                    gdrive_client.delete_old_backups(router_identity, folder_id, keep_latest=2)

        if drive_errors:
            log_entry['drive_errors'] = drive_errors
            flash(f'Some uploads failed: {drive_errors}', 'error')
        if drive_files and settings.get('delete_local_after_upload', False):
            log_entry['local_deleted'] = True

    add_log_entry(log_entry)

    if result.success:
        flash(f'{router["name"]}: {result.message}', 'success')
    else:
        flash(f'{router["name"]}: {result.message}', 'error')

    return redirect(url_for('dashboard'))


@app.route('/backup/all', methods=['POST'])
@login_required
def backup_all():
    routers = load_routers()

    if not routers:
        flash('No routers configured', 'error')
        return redirect(url_for('dashboard'))

    settings = load_settings()
    folder_id = settings.get('google_drive_folder_id', '') or None  # Convert empty string to None
    delete_local = settings.get('delete_local_after_upload', False)
    gdrive_authorized = gdrive_client.is_authorized()

    success_count = 0
    fail_count = 0

    for router in routers:
        result = create_backup(router)
        log_entry = result.to_dict()
        log_entry['triggered_by'] = 'manual_all'

        if result.success:
            success_count += 1

            # Upload to Google Drive if authorized
            if result.local_files and gdrive_authorized:
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
                        if delete_local and os.path.exists(local_file):
                            os.remove(local_file)
                    else:
                        drive_errors.append(drive_result)

                if drive_files:
                    log_entry['drive_files'] = drive_files

                    # Delete old backups from Drive after successful upload
                    if result.local_files:
                        filename = os.path.basename(result.local_files[0])
                        router_identity = '-'.join(filename.split('-')[:-1])
                        if router_identity:
                            gdrive_client.delete_old_backups(router_identity, folder_id, keep_latest=2)

                if drive_errors:
                    log_entry['drive_errors'] = drive_errors
                if drive_files and delete_local:
                    log_entry['local_deleted'] = True
        else:
            fail_count += 1

        add_log_entry(log_entry)

    flash(f'Backup completed: {success_count} successful, {fail_count} failed',
          'success' if fail_count == 0 else 'warning')

    return redirect(url_for('dashboard'))


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    current_settings = load_settings()
    gdrive_status = None
    gdrive_authorized = gdrive_client.is_authorized()

    if request.method == 'POST':
        if request.form.get('test_gdrive'):
            # Test Google Drive connection
            folder_id = request.form.get('google_drive_folder_id', '')
            success, message = gdrive_client.test_connection(folder_id if folder_id else None)
            gdrive_status = {'success': success, 'message': message}
        else:
            # Save settings
            current_settings['schedule_enabled'] = 'schedule_enabled' in request.form
            current_settings['schedule_type'] = request.form.get('schedule_type', 'interval')
            current_settings['schedule_interval_hours'] = int(request.form.get('schedule_interval_hours', 24))
            current_settings['schedule_cron_hour'] = int(request.form.get('schedule_cron_hour', 2))
            current_settings['schedule_cron_minute'] = int(request.form.get('schedule_cron_minute', 0))
            current_settings['google_drive_folder_id'] = request.form.get('google_drive_folder_id', '')
            current_settings['delete_local_after_upload'] = 'delete_local_after_upload' in request.form

            save_settings(current_settings)
            update_scheduler(app)

            flash('Settings saved successfully', 'success')
            return redirect(url_for('settings'))

    return render_template('settings.html', settings=current_settings, gdrive_status=gdrive_status, gdrive_authorized=gdrive_authorized)


@app.route('/gdrive/authorize')
@login_required
def gdrive_authorize():
    redirect_uri = url_for('gdrive_callback', _external=True)
    success, result = gdrive_client.get_auth_url(redirect_uri)

    if success:
        return redirect(result)
    else:
        flash(f'Failed to start authorization: {result}', 'error')
        return redirect(url_for('settings'))


@app.route('/gdrive/callback')
@login_required
def gdrive_callback():
    redirect_uri = url_for('gdrive_callback', _external=True)
    authorization_response = request.url

    success, message = gdrive_client.handle_callback(authorization_response, redirect_uri)

    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')

    return redirect(url_for('settings'))


@app.route('/gdrive/revoke', methods=['POST'])
@login_required
def gdrive_revoke():
    gdrive_client.revoke()
    flash('Google Drive access has been revoked', 'success')
    return redirect(url_for('settings'))


@app.route('/backups')
@login_required
def backups():
    logs = load_backup_log()
    return render_template('backups.html', logs=logs)


# Initialize scheduler on startup
with app.app_context():
    init_scheduler(app)


if __name__ == '__main__':
    # Ensure directories exist
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(config.BACKUP_DIR, exist_ok=True)

    app.run(host='0.0.0.0', port=config.PORT, debug=config.DEBUG)
