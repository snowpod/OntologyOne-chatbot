# utils/github_store_client.py

import fitz 
import os
import requests

from pathlib import Path

from utils.config import Config
from utils.logging import get_logger

github_token = os.environ.get("GITHUB_TOKEN")  # Set this as a secret env var in Render
if not github_token:
    raise ValueError("GitHub token is not set.")

DOC_SHA_URL = "credential_url"
DOC_STORE = "documentstore"

IMG_SHA_URL = "credential_url"
IMG_STORE = "imagestore"
IMG_FILE_URL = "url"
IMAGES_FOLDER = "images_folder"

config = Config()
doc_store_owner = config.get(DOC_STORE, "owner")
doc_store_repo = config.get(DOC_STORE, "repo")
doc_store_project = config.get(DOC_STORE, "project")

file_url_base_folder = config.get(DOC_STORE, "file_url_base_folder")
file_url_child_folder = config.get(DOC_STORE, "file_url_child_folder")

img_store_owner = config.get(IMG_STORE, "owner")
img_store_repo = config.get(IMG_STORE, "repo")
img_store_project = config.get(IMG_STORE, "project")
images_folder = config.get(IMG_STORE, IMAGES_FOLDER)

CACHE_DIR = Path("/tmp/github_docs_cache")  # Convert string to Path object
CACHE_DIR.mkdir(parents=True, exist_ok=True)  # Now this works correctly

def _get_app_logger():
    config = Config()
    return get_logger(config.get("log", "app"))

def _fetch_doc_latest_commit_sha(filename:str) -> str:
    doc_store = DOC_STORE
    sha_url = DOC_SHA_URL

    sha_url = _fetch_latest_commit_sha(doc_store, sha_url, 
                                       doc_store_owner, doc_store_repo, doc_store_project, filename)
    
    return sha_url

def _fetch_image_latest_commit_sha(filename:str) -> str:
    doc_store = IMG_STORE
    sha_url = IMG_SHA_URL

    sha_url = _fetch_latest_commit_sha(doc_store, sha_url, 
                                       img_store_owner, img_store_repo, img_store_project, filename)

def _fetch_latest_commit_sha(doc_store:str, sha_url_template_key:str, 
                             owner:str, repo:str, project:str, filename:str) -> str:
    app_logger = _get_app_logger()

    sha_url = (config.get(doc_store, sha_url_template_key).format(owner=owner, 
                                                                  repo=repo,
                                                                  project=project,
                                                                  filename=filename))
    headers = {"Authorization": f"token {github_token}"}
    
    response = requests.get(sha_url, headers=headers)
    if response.status_code == 200:
        latest_commit = response.json()[0]
        return latest_commit['sha']
    else:
        app_logger.error(f"github_store_client Status Code: {response.status_code}")
        app_logger.error(f"github_store_client Response: {response.json()}")
        raise Exception("Failed to fetch commits from GitHub")

def _fetch_file_url(file_name:str, folder:str) -> str:
    if folder:
        return file_url_child_folder.format(owner=doc_store_owner, 
                                            repo=doc_store_repo, 
                                            project=doc_store_project,
                                            folder=folder,
                                            filename=file_name)
    
    return file_url_base_folder.format(owner=doc_store_owner, 
                                       repo=doc_store_repo, 
                                       project=doc_store_project,
                                       filename=file_name)

def _get_formatted_cached_file_path(project:str, filename:str, folder:str=None) -> str:
    # Return constructed cached file path
    if folder:
        return CACHE_DIR / f"{project}__{folder}__{filename}"
    return CACHE_DIR / f"{project}__{filename}"

def _fetch_cached_file_path(project: str, file_name: str, folder:str) -> str:
    cached_file_path = _get_formatted_cached_file_path(project, file_name, folder)
    if cached_file_path.exists():   # return early if file is already cached
        return cached_file_path
    
    # if cached file does not exist, fetch from GitHub and cache it
    file_url = _fetch_file_url(file_name, folder)

    # Include your GitHub token for private access
    headers = {"Authorization": f"token {github_token}"}
    response = requests.get(file_url, headers=headers)

    # Check if the request was successful
    if response.status_code != 200:
        raise FileNotFoundError(f"Failed to fetch {file_name} from GitHub (status {response.status_code})")

    # Save the file locally in cache
    with open(cached_file_path, "wb") as f:
        f.write(response.content)

    return cached_file_path

def fetch_image_url(file_name:str) -> str:
    return _fetch_file_url(file_name, images_folder)

def fetch_cached_image_path(project:str, file_name:str) -> str:
    return _fetch_cached_file_path(project, file_name, images_folder)

def fetch_cached_doc_path(project: str, file_name: str) -> str:
    folder = None
    return _fetch_cached_file_path(project, file_name, folder)

def fetch_cached_story_file_path(project: str, file_name: str) -> str:
    folder = config.get(DOC_STORE, "stories_folder")
    return _fetch_cached_file_path(project, file_name, folder)

def extract_pages_from_doc(filepath: str, pages: list[int] = None) -> str:
    """Extracts text from a PDF by page (0-based), or entire file for non-PDFs or when pages is None."""
    path = Path(filepath)
    if path.suffix.lower() == ".pdf":
        text = ""
        with fitz.open(filepath) as doc:
            if pages is None:
                for page in doc:
                    text += page.get_text() + "\n"
            else:
                for page_num in pages:
                    page = doc.load_page(page_num)
                    text += page.get_text() + "\n"
        return text
    else:
        # Plain text or RDF (.ttl, .txt, etc.)
        return path.read_text(encoding="utf-8")

def delete_cached_file(project: str, file_name: str, folder:str) -> bool:
    """Delete the cached PDF file for the given project and filename."""
    app_logger = _get_app_logger()

    # Construct the cached file path
    cached_file_path = _fetch_cached_file_path(project, file_name, folder)                                        
                                        
    if cached_file_path.exists():
        cached_file_path.unlink()
        app_logger.error(f"github_store_client Deleted cached file: {cached_file_path}")
        return True
    else:
        app_logger.error(f"github_store_client No cached file to delete: {cached_file_path}")
        return False
    
def list_cached_files(project: str, folder: str = None) -> list[str]:
    """List all cached files for a given project and optional folder."""
    if folder:
        pattern = f"{project}__{folder}__*"
    else:
        pattern = f"{project}__*"

    cached_files = list(CACHE_DIR.glob(pattern))
    return [str(file) for file in cached_files if file.is_file()]