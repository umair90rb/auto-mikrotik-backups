# Deployment Guide

## Environment Variables

Set these environment variables in your deployment platform:

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Flask secret key (generate a random string) |
| `ADMIN_USERNAME` | Yes | Login username |
| `ADMIN_PASSWORD` | Yes | Login password |
| `GOOGLE_CLIENT_SECRET` | Yes | JSON string of your Google OAuth client_secret.json |
| `GOOGLE_TOKEN` | No* | JSON string of OAuth token (see below) |
| `PORT` | No | Port to run on (default: 5000, auto-set by platform) |
| `FLASK_DEBUG` | No | Set to "False" for production |

## Google Drive Setup

### 1. Create OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable the **Google Drive API**
4. Go to **Credentials** > **Create Credentials** > **OAuth client ID**
5. Select **Web application**
6. Add authorized redirect URI: `https://your-app-url.com/gdrive/callback`
7. Download the JSON file

### 2. Set GOOGLE_CLIENT_SECRET

Copy the entire contents of the downloaded JSON file and set it as the `GOOGLE_CLIENT_SECRET` environment variable.

Example:
```
GOOGLE_CLIENT_SECRET={"web":{"client_id":"xxx.apps.googleusercontent.com","project_id":"xxx","auth_uri":"https://accounts.google.com/o/oauth2/auth",...}}
```

### 3. Authorize Google Drive

1. Deploy the app
2. Log in to your app
3. Go to **Settings** > Click **Authorize Google Drive**
4. Complete the Google authorization flow
5. After authorization, the app will print the `GOOGLE_TOKEN` value to the logs
6. Copy that token and set it as an environment variable for persistence

## Deploy to Railway

1. Push your code to GitHub
2. Go to [Railway](https://railway.app/)
3. Click **New Project** > **Deploy from GitHub repo**
4. Select your repository
5. Add environment variables in the **Variables** tab
6. Railway will auto-deploy

## Deploy to Render

1. Push your code to GitHub
2. Go to [Render](https://render.com/)
3. Click **New** > **Web Service**
4. Connect your GitHub repository
5. Render will detect the `render.yaml` configuration
6. Add environment variables in the **Environment** tab
7. Click **Create Web Service**

## Important Notes

### Data Persistence

The app stores data in JSON files. On Railway/Render:
- Router configs, settings, and logs are stored in the `data/` folder
- These persist as long as the instance isn't redeployed
- For long-term persistence, consider backing up the data files or migrating to a database

### Scheduled Backups

The scheduler runs inside the web process. With `workers=1`, it will work correctly. If you scale to multiple workers, you'll get duplicate backup jobs.

### Google OAuth Token

After first authorization, copy the `GOOGLE_TOKEN` from logs and set it as an env var. This ensures the token persists across deployments.
