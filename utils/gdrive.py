"""
Google Drive Upload Utility
Uses OAuth2 authentication (user login flow)

Supports both file-based and environment variable credentials:
- GOOGLE_CLIENT_SECRET: JSON string of client_secret.json contents
- GOOGLE_TOKEN: JSON string of token.json contents (for persistent auth)
"""
import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import config

# OAuth2 scopes
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Paths
CREDENTIALS_DIR = os.path.join(config.BASE_DIR, 'credentials')
CLIENT_SECRET_FILE = os.path.join(CREDENTIALS_DIR, 'client_secret.json')
TOKEN_FILE = os.path.join(CREDENTIALS_DIR, 'token.json')


def get_client_secret():
    """Get client secret from file or environment variable."""
    # Try environment variable first
    env_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    if env_secret:
        try:
            return json.loads(env_secret)
        except json.JSONDecodeError:
            pass

    # Fall back to file
    if os.path.exists(CLIENT_SECRET_FILE):
        with open(CLIENT_SECRET_FILE, 'r') as f:
            return json.load(f)

    return None


def get_token():
    """Get token from file or environment variable."""
    # Try environment variable first
    env_token = os.environ.get('GOOGLE_TOKEN')
    if env_token:
        try:
            return json.loads(env_token)
        except json.JSONDecodeError:
            pass

    # Fall back to file
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as f:
            return json.load(f)

    return None


def save_token(token_data):
    """Save token to file and print for env var setup."""
    os.makedirs(CREDENTIALS_DIR, exist_ok=True)

    # Save to file
    with open(TOKEN_FILE, 'w') as f:
        json.dump(token_data, f)

    # Print for environment variable setup (useful for deployment)
    print("\n[Google Drive] Token saved. For deployment, set this environment variable:")
    print(f"GOOGLE_TOKEN={json.dumps(token_data)}\n")


class GoogleDriveClient:
    def __init__(self):
        self.service = None
        self._initialized = False
        self._error = None

    def get_auth_url(self, redirect_uri):
        """
        Get the OAuth2 authorization URL.

        Returns:
            tuple: (success, auth_url or error_message)
        """
        client_config = get_client_secret()
        if not client_config:
            return False, "Client secret not found. Set GOOGLE_CLIENT_SECRET env var or add client_secret.json file."

        try:
            flow = Flow.from_client_config(
                client_config,
                scopes=SCOPES,
                redirect_uri=redirect_uri
            )
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            return True, auth_url
        except Exception as e:
            return False, f"Failed to create auth URL: {str(e)}"

    def handle_callback(self, authorization_response, redirect_uri):
        """
        Handle the OAuth2 callback and save the token.

        Args:
            authorization_response: The full callback URL with code
            redirect_uri: The redirect URI used in the auth request

        Returns:
            tuple: (success, message)
        """
        client_config = get_client_secret()
        if not client_config:
            return False, "Client secret not found"

        try:
            flow = Flow.from_client_config(
                client_config,
                scopes=SCOPES,
                redirect_uri=redirect_uri
            )
            flow.fetch_token(authorization_response=authorization_response)

            credentials = flow.credentials
            token_data = json.loads(credentials.to_json())

            # Save the token
            save_token(token_data)

            self._initialized = False  # Reset to force re-init with new token
            return True, "Google Drive authorized successfully!"
        except Exception as e:
            return False, f"Authorization failed: {str(e)}"

    def is_authorized(self):
        """Check if we have valid credentials."""
        token_data = get_token()
        if token_data:
            try:
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                return creds and creds.valid or (creds and creds.expired and creds.refresh_token)
            except Exception:
                return False
        return False

    def initialize(self):
        """Initialize the Google Drive service."""
        if self._initialized and self.service:
            return True, None

        token_data = get_token()
        if not token_data:
            self._error = "Not authorized. Please authorize Google Drive access first."
            return False, self._error

        try:
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)

            # Refresh token if expired
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # Save refreshed token
                refreshed_data = json.loads(creds.to_json())
                save_token(refreshed_data)

            if not creds or not creds.valid:
                self._error = "Invalid credentials. Please re-authorize Google Drive access."
                return False, self._error

            self.service = build('drive', 'v3', credentials=creds)
            self._initialized = True
            return True, None
        except Exception as e:
            self._error = f"Failed to initialize Google Drive: {str(e)}"
            return False, self._error

    def upload_file(self, local_path, folder_id=None):
        """
        Upload a file to Google Drive.

        Args:
            local_path: Path to the local file
            folder_id: Google Drive folder ID (optional)

        Returns:
            tuple: (success: bool, file_id or error_message: str)
        """
        success, error = self.initialize()
        if not success:
            return False, error

        if not os.path.exists(local_path):
            return False, f"File not found: {local_path}"

        try:
            filename = os.path.basename(local_path)

            file_metadata = {'name': filename}
            if folder_id:
                file_metadata['parents'] = [folder_id]

            media = MediaFileUpload(
                local_path,
                mimetype='text/plain',
                resumable=True
            )

            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink'
            ).execute()

            return True, {
                'id': file.get('id'),
                'name': file.get('name'),
                'link': file.get('webViewLink')
            }

        except Exception as e:
            return False, f"Upload failed: {str(e)}"

    def list_files(self, folder_id=None, max_results=50):
        """
        List files in Google Drive.

        Args:
            folder_id: Google Drive folder ID (optional)
            max_results: Maximum number of results to return

        Returns:
            tuple: (success: bool, list of files or error_message)
        """
        success, error = self.initialize()
        if not success:
            return False, error

        try:
            query = "mimeType != 'application/vnd.google-apps.folder'"
            if folder_id:
                query += f" and '{folder_id}' in parents"

            results = self.service.files().list(
                q=query,
                pageSize=max_results,
                fields="files(id, name, createdTime, size, webViewLink)",
                orderBy="createdTime desc"
            ).execute()

            files = results.get('files', [])
            return True, files

        except Exception as e:
            return False, f"Failed to list files: {str(e)}"

    def delete_file(self, file_id):
        """
        Delete a file from Google Drive.

        Args:
            file_id: Google Drive file ID

        Returns:
            tuple: (success: bool, message: str)
        """
        success, error = self.initialize()
        if not success:
            return False, error

        try:
            self.service.files().delete(fileId=file_id).execute()
            return True, "File deleted successfully"
        except Exception as e:
            return False, f"Failed to delete file: {str(e)}"

    def test_connection(self, folder_id=None):
        """
        Test Google Drive connection.

        Returns:
            tuple: (success: bool, message: str)
        """
        if not self.is_authorized():
            return False, "Not authorized. Please click 'Authorize Google Drive' to connect your account."

        success, error = self.initialize()
        if not success:
            return False, error

        try:
            # Try to get user info as a connection test
            about = self.service.about().get(fields="user").execute()
            user_email = about.get('user', {}).get('emailAddress', 'Unknown')

            if folder_id:
                # Verify folder access
                try:
                    folder = self.service.files().get(
                        fileId=folder_id,
                        fields="name"
                    ).execute()
                    folder_name = folder.get('name', 'Unknown')
                    return True, f"Connected as {user_email}. Folder: {folder_name}"
                except Exception:
                    return False, f"Connected as {user_email}, but cannot access folder ID: {folder_id}. Make sure the folder exists and you have access."

            return True, f"Connected as {user_email}"

        except Exception as e:
            return False, f"Connection test failed: {str(e)}"

    def revoke(self):
        """Revoke access and delete stored token."""
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
        self._initialized = False
        self.service = None


# Singleton instance
gdrive_client = GoogleDriveClient()
