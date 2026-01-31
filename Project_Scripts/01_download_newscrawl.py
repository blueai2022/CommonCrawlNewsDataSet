# -*- coding: utf-8 -*-
"""
Script for downloading CommonCrawl News WARC files for a specified month.

Updated for better maintainability and robustness.
"""
import requests
from concurrent.futures import ThreadPoolExecutor
import gzip
import os
import logging
import time
from warcio.archiveiterator import ArchiveIterator
import argparse
from tqdm import tqdm
from urllib.error import HTTPError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# Argument parser
parser = argparse.ArgumentParser(description='Process YEAR_MONTH for Common Crawl.')
parser.add_argument(
    'year_month',
    type=str,
    help='The Year and Month in YYYY/MM format (e.g., 2023/09).'
)
args = parser.parse_args()
YEAR_MONTH = args.year_month

# Validate YEAR_MONTH format
if not YEAR_MONTH or len(YEAR_MONTH) != 7 or YEAR_MONTH[4] != '/':
    logging.error("Invalid YEAR_MONTH format. Please use YYYY/MM.")
    exit(1)

BASE_URL = "https://data.commoncrawl.org/crawl-data/CC-NEWS/"
folder = YEAR_MONTH.replace("/", "-")
WARC_PATHS_FILE = f"{YEAR_MONTH}/warc.paths.gz"
DOWNLOAD_FOLDER = os.path.join("/data", "CommonCrawl", "news", folder)

DOWNLOAD_URL = "https://data.commoncrawl.org/"

# Ensure folder exists
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Retry logic for requests
def download_with_retries(url, local_path, retries=5, backoff=10):
    """Download a file with retries and exponential backoff."""
    wait_time = backoff
    for attempt in range(retries):
        try:
            logging.info(f"Attempting to download: {url}")
            with requests.get(url, stream=True) as response:
                response.raise_for_status()
                with open(local_path, 'wb') as fd:
                    for chunk in response.iter_content(chunk_size=8192):
                        fd.write(chunk)
            logging.info(f"Downloaded: {local_path}")
            return True
        except requests.exceptions.RequestException as e:
            logging.warning(f"Error downloading {url}: {e}. Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
            wait_time *= 2
    logging.error(f"Failed to download {url} after {retries} attempts.")
    return False

# Download warc.paths.gz
warc_paths_local = os.path.join(DOWNLOAD_FOLDER, os.path.basename(WARC_PATHS_FILE))
if not os.path.exists(warc_paths_local):
    if not download_with_retries(BASE_URL + WARC_PATHS_FILE, warc_paths_local):
        logging.error("Failed to download warc.paths.gz. Exiting.")
        exit(1)

# Extract list of WARC files
logging.info(f"Extracting WARC file paths from: {warc_paths_local}")
with gzip.open(warc_paths_local, 'rt') as f:
    file_paths = [line.strip() for line in f]

# Function to download a single WARC file
def download_warc_file(path):
    """Download a single WARC file."""
    url = DOWNLOAD_URL + path
    local_filename = os.path.join(DOWNLOAD_FOLDER, os.path.basename(path))
    if os.path.exists(local_filename):
        logging.info(f"File already exists, skipping: {local_filename}")
        return
    download_with_retries(url, local_filename)

# Download WARC files concurrently
logging.info(f"Starting download of {len(file_paths)} WARC files.")
with ThreadPoolExecutor(max_workers=10) as executor:
    list(tqdm(executor.map(download_warc_file, file_paths), total=len(file_paths), desc="Downloading WARC files"))

# Cleanup temporary files
logging.info("Download process complete. Cleaning up temporary files.")
if os.path.exists(warc_paths_local):
    os.remove(warc_paths_local)

logging.info("All files downloaded successfully.")
