# -*- coding: utf-8 -*-
"""
Script for extracting and processing text content from WARC files.

Updated for improved maintainability and robustness.
"""
from tqdm import tqdm
import pandas as pd
import multiprocessing
import os
import logging
import trafilatura
import json
from urllib.parse import urlparse
from argparse import ArgumentParser
from functools import partial

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

def extract_top_level_domain(url):
    """Extract the top-level domain (TLD) from a URL."""
    try:
        parsed_url = urlparse(url)
        domain_parts = parsed_url.netloc.split('.')
        if len(domain_parts) > 1:
            return '.' + domain_parts[-1]
        return domain_parts[0]
    except Exception as e:
        logging.warning(f"Error extracting TLD from {url}: {e}")
        return None

def parse_file(filename, exclude_tlds):
    """Parse a single feather file and extract text using Trafilatura."""
    rows = []
    try:
        data = pd.read_feather(filename)
        data["TLD"] = data["URL"].apply(extract_top_level_domain)
        
        # Only filter if exclusion list is not empty
        if len(exclude_tlds) > 0 and "Country Code" in exclude_tlds.columns:
            data = data[~data["TLD"].isin(exclude_tlds["Country Code"])]
        else:
            logging.info(f"No TLD filtering applied (empty exclusion list)")
        
        data = data.reset_index(drop=True)

        for _, row in tqdm(data.iterrows(), total=len(data), desc=f"Processing {os.path.basename(filename)}", leave=False):
            try:
                extracted = trafilatura.extract(
                    row["Content"],
                    include_comments=False,
                    deduplicate=True,
                    output_format="json",
                    with_metadata=True,
                    # target_language removed - accepting all languages
                )
                if extracted:
                    root = json.loads(extracted)
                    rows.append({
                        "id": row["ID"],
                        "text": root.get("raw_text"),
                        "url": row["URL"],
                        "excerpt": root.get("excerpt"),
                        "date": root.get("date"),
                        "tags": root.get("tags"),
                        "categories": root.get("categories"),
                        "title": root.get("title"),
                        "date_crawled": root.get("filedate"),
                        "hostname": root.get("hostname")
                    })
            except Exception as e:
                logging.warning(f"Error processing record {row['URL']}: {e}")

        if rows:
            output_df = pd.DataFrame(rows).dropna(subset=["text"]).drop_duplicates(subset=["text", "hostname"])
            output_file = filename.replace(".feather", "_processed.feather")
            output_df.to_feather(output_file)
            logging.info(f"Saved processed file: {output_file} ({len(output_df)} articles)")
            return True
        else:
            logging.warning(f"No valid articles extracted from {filename}")
            return False

    except Exception as e:
        logging.error(f"Error processing file {filename}: {e}")
        return False

def main(folder, tlds_file):
    """Main function to process all feather files in the given folder."""
    if not os.path.exists(folder):
        logging.error(f"Folder does not exist: {folder}")
        return

    exclude_tlds = pd.read_excel(tlds_file)
    files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".feather") and not f.endswith("_processed.feather")]

    if not files:
        logging.warning(f"No feather files found in folder: {folder}")
        return

    logging.info(f"Processing {len(files)} files from folder: {folder}")
    logging.info(f"TLD exclusions: {len(exclude_tlds)} entries")
    
    # Use partial to create a picklable function
    parse_with_tlds = partial(parse_file, exclude_tlds=exclude_tlds)
    
    with multiprocessing.Pool(processes=os.cpu_count()) as pool:
        with tqdm(total=len(files), desc="Overall Progress") as pbar:
            for result in pool.imap_unordered(parse_with_tlds, files):
                pbar.update()

if __name__ == "__main__":
    parser = ArgumentParser(description="Extract and process text from feather files.")
    parser.add_argument("folder", type=str, help="Folder containing feather files.")
    parser.add_argument("tlds_file", type=str, help="Path to the Excel file containing TLD exclusions.")
    args = parser.parse_args()

    main(args.folder, args.tlds_file)
