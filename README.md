# Fusion 360 Batch Downloader

This script authenticates with Autodesk’s Platform Services (APS) API and downloads all Fusion 360 design files associated with your account. It processes every project across all hubs and downloads the latest version of each file into a local folder structure.

Files are organized by project name. However, any subfolders inside each project are **not** preserved in the backup; all files within a project (including from subfolders) are downloaded into a single flat directory named after the project.

---
## MADE WITH MOSTLY AI. WHILE IT ONLY REQUIRES READ ACCESS TO YOUR AUTODESK ACCOUNT USE AT YOUR OWN RISK
## Features

- Recursively scans all hubs and projects in your account.
- Downloads all available Fusion 360 design files.
- Automatically adds proper file extensions (most of the time).
- Prevents overwriting by adding `(1)`, `(2)`, etc., to duplicate filenames.
- Provides progress bars for the download process.
- Logs and retries any failed downloads at the end of execution.
- Does not require Fusion360 to open the file drastically increasing download speed.
---

## Requirements

- Python 3.7 or higher
- Required Python packages, which can be installed via pip:
- The down.py file
```bash
pip install tqdm requests
```

---

## Setup

#### 1. Create a Forge (APS) App
- Go to the [Autodesk Forge Portal](https://forge.autodesk.com/) and create an application.
- When creating the app, enable the **Data Management API**.
- Set the redirect URI in the app settings to exactly: `http://localhost:8080/callback`

#### 2. Set Environment Variables
- Find the **Client ID** and **Client Secret** for your app on the Forge portal.
- While you are in the same directory as the script, set them as environment variables in your terminal or shell. 

**On macOS/Linux:**
```bash
export APS_CLIENT_ID="your-client-id"
export APS_CLIENT_SECRET="your-client-secret"
```

**On Windows (Command Prompt):**
```bash
setx APS_CLIENT_ID="your-client-id"
setx APS_CLIENT_SECRET="your-client-secret"
```
*(Note: You must restart the Command Prompt after using `setx`)*

> Alternatively, you can store them in a `.env` file and use a package like `python-dotenv` to load them securely into the script.
> 
> OR You can change lines 14-15 to your respecitve tokens
```
Line 14: CLIENT_ID = os.getenv("APS_CLIENT_ID") --> CLIENT_ID = "CLIENT_ID_TOKEN"

Line 15: CLIENT_SECRET = os.getenv("APS_CLIENT_SECRET") --> CLIENT_SECRET = "CLIENT_SECRET_TOKEN"
```
---

## Usage

1. **Run the script from your terminal:**
```bash
python down.py
```

2. **Authenticate in Browser:**
A browser window will open, prompting you to log in to your Autodesk account. After you log in and click **Allow**, the script will begin.

3. **Download Process:**
- The script scans all hubs, projects, and folders in your account.
- It then downloads the most recent version of each file.
- Files are saved to `Fusion360_Backup_Final/<Project Name>/` as a .f3d
- Drawings and other files seem to fail.

---

## Download Structure

- All files are downloaded into a root `Fusion360_Backup_Final` folder.
- Each project gets its own sub-folder.
- **Subfolders are flattened** — files from subfolders within a project are placed directly into the main project folder.
- If a file with the same name already exists, a numeric suffix like `(1)` is added to the new file to prevent overwriting.

---

## Failed Downloads

Any files that fail to download will be listed at the end of the script’s execution. These are usually caused by not being 3D models in Fusion360.

#### Notes

- This script does not overwrite existing files.
- Files are downloaded using temporary, secure, signed S3 URLs provided by Autodesk's API.
- Ensure your Forge App has proper access to the hubs and projects you wish to back up.
