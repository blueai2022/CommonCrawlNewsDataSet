# -*- coding: utf-8 -*-
"""
Script for extracting and processing text content from WARC files.
OPTIMIZED: Sequential processing to avoid memory issues and hangs.
"""
import pandas as pd
import os
import logging
import trafilatura
import json
from urllib.parse import urlparse
from argparse import ArgumentParser

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

def process_file_sequential(filename, exclude_tlds):
    """Process a single feather file sequentially with chunking to avoid memory issues."""
    try:
        output_file = filename.replace(".feather", "_processed.feather")
        
        # Skip if already processed
        if os.path.exists(output_file):
            logging.info(f"✓ Skipping (already processed): {os.path.basename(filename)}")
            return True
        
        logging.info(f"Processing {os.path.basename(filename)}")
        
        # Read the data
        data = pd.read_feather(filename)
        total_rows = len(data)
        logging.info(f"  Loaded {total_rows:,} records")
        
        # Apply TLD filtering
        data["TLD"] = data["URL"].apply(extract_top_level_domain)
        if len(exclude_tlds) > 0 and "Country Code" in exclude_tlds.columns:
            before_filter = len(data)
            data = data[~data["TLD"].isin(exclude_tlds["Country Code"])]
            filtered_count = before_filter - len(data)
            if filtered_count > 0:
                logging.info(f"  Filtered {filtered_count:,} by TLD")
        
        data = data.reset_index(drop=True)
        
        # Process in chunks to avoid memory buildup
        CHUNK_SIZE = 1000
        all_rows = []
        processed_count = 0  # FIX: Track extraction count
        
        for chunk_start in range(0, len(data), CHUNK_SIZE):
            chunk_end = min(chunk_start + CHUNK_SIZE, len(data))
            chunk = data.iloc[chunk_start:chunk_end]
            
            for idx, row in chunk.iterrows():
                try:
                    extracted = trafilatura.extract(
                        row["Content"],
                        include_comments=False,
                        deduplicate=True,
                        output_format="json",
                        with_metadata=True,
                        target_language='fr'
                    )
                    
                    if extracted:
                        root = json.loads(extracted)
                        all_rows.append({
                            "id": row["ID"],
                            "text": root.get("raw_text"),
                            "url": row["URL"],
                            "excerpt": root.get("excerpt"),
                            "date": row.get("date"),
                            "tags": root.get("tags"),
                            "categories": root.get("categories"),
                            "title": root.get("title"),
                            "date_crawled": root.get("filedate"),
                            "hostname": root.get("hostname")
                        })
                        processed_count += 1  # FIX: Increment counter
                except Exception:
                    # Silently skip problematic records (avoid log spam)
                    pass
            
            # FIX: Log progress with extraction count every 5000 records
            if chunk_end % 5000 == 0 or chunk_end == total_rows:
                logging.info(f"  Progress: {chunk_end:,}/{total_rows:,} ({chunk_end*100//total_rows}%) - Extracted: {processed_count:,}")
        
        # Save results
        if all_rows:
            output_df = pd.DataFrame(all_rows).dropna(subset=["text"]).drop_duplicates(subset=["text", "hostname"])
            output_df.to_feather(output_file)
            logging.info(f"  ✅ Saved: {os.path.basename(output_file)} ({len(output_df):,} articles)")
            
            # FIX: Explicit memory cleanup
            del data, all_rows, output_df
            return True
        else:
            logging.warning(f"  ⚠️  No valid articles extracted from {os.path.basename(filename)}")
            # FIX: Clean up even on failure
            del data, all_rows
            return False
            
    except Exception as e:
        logging.error(f"  ❌ Error processing {os.path.basename(filename)}: {e}")
        return False

def main(folder, tlds_file):
    """Main function to process all feather files sequentially."""
    if not os.path.exists(folder):
        logging.error(f"Folder does not exist: {folder}")
        return
    
    # Load TLD exclusions once
    logging.info(f"Loading TLD exclusions from {tlds_file}")
    exclude_tlds = pd.read_excel(tlds_file)
    logging.info(f"Loaded {len(exclude_tlds)} TLD exclusions")
    
    # Get list of files to process
    files = [
        os.path.join(folder, f) 
        for f in os.listdir(folder) 
        if f.endswith(".feather") and not f.endswith("_processed.feather")
    ]
    
    if not files:
        logging.warning(f"No unprocessed feather files found in: {folder}")
        return
    
    logging.info(f"Found {len(files)} files to process")
    logging.info("=" * 70)
    
    # Process files sequentially
    successful = 0
    failed = 0
    
    for i, filename in enumerate(files, 1):
        logging.info(f"[{i}/{len(files)}] Processing: {os.path.basename(filename)}")
        
        if process_file_sequential(filename, exclude_tlds):
            successful += 1
        else:
            failed += 1
        
        logging.info("-" * 70)
    
    # Summary
    logging.info("=" * 70)
    logging.info(f"Processing complete:")
    logging.info(f"  ✅ Successful: {successful}")
    logging.info(f"  ❌ Failed: {failed}")
    logging.info(f"  📊 Total: {len(files)}")
    logging.info("=" * 70)

if __name__ == "__main__":
    parser = ArgumentParser(description="Extract and process text from feather files.")
    parser.add_argument("folder", type=str, help="Folder containing feather files.")
    parser.add_argument("tlds_file", type=str, help="Path to Excel file with TLD exclusions.")
    args = parser.parse_args()
    
    main(args.folder, args.tlds_file)
