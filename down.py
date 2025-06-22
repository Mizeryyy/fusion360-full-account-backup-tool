import os
import sys
import time
import requests
import webbrowser
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from tqdm import tqdm


# --- Configuration ---
# It's highly recommended to set these as environment variables for security
CLIENT_ID = "6ocbezNVfJqS6z8D1GB1Y1l7pL2kr6fKSGKdB0S6aZyDTb66"
CLIENT_SECRET = "9KHqcX3jknjXdzaSg6GGFvmH2VlDJPFvDlqdcVmzG5xkCG4vCvbZOuGdRRsiaxCi"
REDIRECT_URI = "http://localhost:8080/callback"
SCOPES = "data:read"  # Correct scope per official documentation.
DOWNLOAD_DIR = "Fusion360_Backup_Final"
DOWNLOAD_TIMEOUT = 300

# --- Globals & API Endpoints ---
auth_code_from_user = None
BASE_API_URL = "https://developer.api.autodesk.com"

# --- Authentication ---
class OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code_from_user
        query = parse_qs(urlparse(self.path).query)
        if 'code' in query:
            auth_code_from_user = query['code'][0]
            self.send_response(200); self.send_header('Content-type', 'text/html'); self.end_headers()
            self.wfile.write(b"<h1>Authentication successful!</h1><p>You can close this window now.</p>")

def get_user_token():
    auth_link = f"{BASE_API_URL}/authentication/v2/authorize?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&scope={SCOPES}"
    print("\n--- User Authentication ---")
    webbrowser.open(auth_link)
    httpd = HTTPServer(('localhost', 8080), OAuthHandler)
    print("\nWaiting for authentication callback...")
    while auth_code_from_user is None: httpd.handle_request()
    print("Authorization code received. Requesting access token...")
    payload = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code', 'code': auth_code_from_user, 'redirect_uri': REDIRECT_URI}
    try:
        response = requests.post(f"{BASE_API_URL}/authentication/v2/token", data=payload, timeout=30)
        response.raise_for_status()
        print("Access Token granted successfully!")
        return response.json()['access_token']
    except requests.exceptions.RequestException as e:
        print(f"\n[FATAL ERROR] Failed to get token: {e}\nResponse: {e.response.text if e.response else 'N/A'}"); sys.exit(1)

# --- API & Helper Functions ---
def make_api_request(url, token, **kwargs):
    headers = {'Authorization': f'Bearer {token}'}
    try:
        response = requests.request('get', url, headers=headers, timeout=45, **kwargs)
        response.raise_for_status()
        return response.json() if response.text else None
    except requests.exceptions.RequestException as e:
        print(f"\n[API ERROR] Request failed for {url}: {e}")
        if e.response is not None: print(f"       Response Body: {e.response.text}")
        return None

def sanitize_filename(name): return re.sub(r'[\\/*?:"<>|]', "_", name)

def find_all_items(token):
    all_items = []
    print("\n--- Discovering All Files ---")
    hubs = make_api_request(f"{BASE_API_URL}/project/v1/hubs", token)
    if not hubs: sys.exit("Could not find any hubs (accounts).")
    
    for hub in hubs.get('data', []):
        projects_url = hub['links']['self']['href'] + '/projects'
        projects = make_api_request(projects_url, token)
        if not projects: continue
        
        project_list = projects.get('data', [])
        with tqdm(total=len(project_list), desc=f"Scanning Hub '{hub['attributes']['name']}'", unit="project") as pbar:
            for project in project_list:
                pbar.set_description(f"Project: {project['attributes']['name'][:25]:<25}")
                q = [project['relationships']['rootFolder']['data']['id']]
                while q:
                    folder_id = q.pop(0)
                    contents_url = f"{BASE_API_URL}/data/v1/projects/{project['id']}/folders/{folder_id}/contents"
                    while contents_url:
                        contents = make_api_request(contents_url, token)
                        if not contents: break
                        for item in contents.get('data', []):
                            if item.get('type') == 'folders': q.append(item['id'])
                            elif item.get('type') == 'items' and item.get('attributes'):
                                all_items.append({
                                    'name': item['attributes']['displayName'],
                                    'project_id': project['id'],
                                    'project_name': project['attributes']['name'],
                                    'item_id': item['id']
                                })
                        next_url = contents.get('links', {}).get('next', {}).get('href')
                        contents_url = next_url if next_url else None
                pbar.update(1)
    return all_items

def download_file(file_info, token, failed_list):
    project_name = sanitize_filename(file_info['project_name'])
    base_name = sanitize_filename(file_info['name'])
    
    item_versions_url = f"{BASE_API_URL}/data/v1/projects/{file_info['project_id']}/items/{file_info['item_id']}/versions"
    versions_data = make_api_request(item_versions_url, token)
    
    if not versions_data or not versions_data.get('data'):
        failed_list.append(file_info); return False

    try:
        version_attributes = versions_data['data'][0]['attributes']
        storage_urn = versions_data['data'][0]['relationships']['storage']['data']['id']
    except (KeyError, IndexError):
        failed_list.append(file_info); return False
        
    urn_match = re.search(r'urn:adsk\.objects:os\.object:([^/]+)/(.+)', storage_urn)
    if not urn_match:
        failed_list.append(file_info); return False
    
    bucket_key = urn_match.group(1)
    object_key = urn_match.group(2)
    
    # --- ROBUST FILENAME LOGIC ---
    final_filename = base_name
    _, storage_ext = os.path.splitext(object_key)
    if storage_ext:
        if not final_filename.lower().endswith(storage_ext.lower()):
            final_filename = f"{final_filename}{storage_ext}"
    else:
        file_type_ext = version_attributes.get('fileType')
        if file_type_ext and not final_filename.lower().endswith(f'.{file_type_ext.lower()}'):
            final_filename = f"{final_filename}.{file_type_ext}"
            
    # --- DUPLICATE HANDLING LOGIC ---
    local_path = os.path.join(DOWNLOAD_DIR, project_name)
    os.makedirs(local_path, exist_ok=True)
    
    base_filepath_name, extension = os.path.splitext(final_filename)
    counter = 1
    file_path = os.path.join(local_path, final_filename)
    
    while os.path.exists(file_path):
        # If the file already exists, create a new name with a counter
        new_filename = f"{base_filepath_name} ({counter}){extension}"
        file_path = os.path.join(local_path, new_filename)
        counter += 1
    
    # If the path has changed, it means the original file exists.
    # We can choose to skip downloading it to "update" the folder.
    # For now, per your request, we download it with a new name.
    
    signed_url_endpoint = f"{BASE_API_URL}/oss/v2/buckets/{bucket_key}/objects/{object_key}/signeds3download"
    signed_url_data = make_api_request(signed_url_endpoint, token)
    
    if not signed_url_data or 'url' not in signed_url_data:
        failed_list.append(file_info); return False
        
    download_url = signed_url_data['url']
    
    try:
        with requests.get(download_url, stream=True, timeout=DOWNLOAD_TIMEOUT) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            # Use the final, unique filename for the progress bar
            unique_filename = os.path.basename(file_path)
            with open(file_path, 'wb') as f, tqdm(total=total_size, unit='B', unit_scale=True, unit_divisor=1024, desc=unique_filename[:40], leave=False) as pbar:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk); pbar.update(len(chunk))
        return True
    except requests.exceptions.RequestException as e:
        failed_list.append(file_info); return False

def main():
    print("--- Autodesk Fusion 360 Safe Batch Downloader ---")
    print("This version will NOT overwrite existing files.")
    print("If a file already exists, a number will be added (e.g., 'file (1).f3d').")
    
    if not CLIENT_ID or not CLIENT_SECRET:
        print("[FATAL ERROR] APS_CLIENT_ID and APS_CLIENT_SECRET environment variables not set."); sys.exit(1)

    token = get_user_token()
    all_files = find_all_items(token)

    if not all_files: print("\nNo downloadable files found. Exiting."); sys.exit(0)
    
    print(f"\n--- Ready to Download: {len(all_files)} files ---")
    try: input("Press Enter to begin...")
    except (EOFError, KeyboardInterrupt): sys.exit("\nDownload cancelled.")
    
    failed_downloads = []
    with tqdm(total=len(all_files), desc="Overall Progress", unit="file") as main_pbar:
        for file_info in all_files:
            download_file(file_info, token, failed_downloads)
            main_pbar.update(1)
            
    print("\n\n" + "="*50); print("--- DOWNLOAD COMPLETE ---".center(50)); print("="*50)
    if not failed_downloads:
        print("\n✅ All files processed successfully!")
    else:
        print(f"\n⚠️ {len(failed_downloads)} file(s) could not be downloaded due to API errors:")
        for file_info in failed_downloads:
            print(f"  - Project: {file_info.get('project_name', '?')}, File: {file_info.get('name', '?')}")
    print("\n" + "="*50)

if __name__ == "__main__":
    main()