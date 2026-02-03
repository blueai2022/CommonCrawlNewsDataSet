# -*- coding: utf-8 -*-
"""
Script for extracting and processing text content from WARC files.
OPTIMIZED: Streaming processing with incremental saves to prevent OOM.
"""
import pandas as pd
import os
import logging
import trafilatura
import json
from urllib.parse import urlparse
from argparse import ArgumentParser
import pyarrow.feather as feather

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
    """Process a single feather file with streaming and incremental saves."""
    try:
        output_file = filename.replace(".feather", "_processed.feather")
        temp_output_file = output_file.replace(".feather", "_temp.feather")
        
        # Skip if already processed
        if os.path.exists(output_file):
            logging.info(f"✓ Skipping (already processed): {os.path.basename(filename)}")
            return True
        
        logging.info(f"Processing {os.path.basename(filename)}")
        
        # Use PyArrow to read metadata WITHOUT loading data
        table = feather.read_table(filename)
        total_rows = len(table)
        logging.info(f"  Total records: {total_rows:,}")
        
        # Process in streaming chunks
        CHUNK_SIZE = 5000
        SAVE_EVERY = 10000  # Save to disk every 10k extracted records
        
        all_rows = []
        processed_count = 0
        saved_chunks = []  # Track temporary chunk files
        
        for chunk_start in range(0, total_rows, CHUNK_SIZE):
            chunk_end = min(chunk_start + CHUNK_SIZE, total_rows)
            
            # Read ONLY this chunk from disk
            chunk_table = table.slice(chunk_start, chunk_end - chunk_start)
            chunk_data = chunk_table.to_pandas()
            
            # Apply TLD filtering
            chunk_data["TLD"] = chunk_data["URL"].apply(extract_top_level_domain)
            if len(exclude_tlds) > 0 and "Country Code" in exclude_tlds.columns:
                before_filter = len(chunk_data)
                chunk_data = chunk_data[~chunk_data["TLD"].isin(exclude_tlds["Country Code"])]
                filtered_count = before_filter - len(chunk_data)
                if filtered_count > 0 and chunk_start == 0:
                    logging.info(f"  TLD filtering enabled ({len(exclude_tlds)} exclusions)")
            
            chunk_data = chunk_data.reset_index(drop=True)
            
            # Extract text from this chunk
            for idx, row in chunk_data.iterrows():
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
                        processed_count += 1
                except Exception:
                    # Silently skip problematic records
                    pass
            
            # Free chunk memory
            del chunk_table, chunk_data
            
            # REAL FIX: Save intermediate results to disk when we accumulate too many
            if len(all_rows) >= SAVE_EVERY or chunk_end == total_rows:
                if all_rows:
                    chunk_df = pd.DataFrame(all_rows).dropna(subset=["text"])
                    chunk_file = f"{temp_output_file}.part{len(saved_chunks)}.feather"
                    chunk_df.to_feather(chunk_file)
                    saved_chunks.append(chunk_file)
                    logging.info(f"  💾 Saved intermediate chunk: {len(all_rows)} rows to part{len(saved_chunks)-1}")
                    del all_rows, chunk_df
                    all_rows = []  # Reset for next batch
            
            # Log progress
            if chunk_end % 5000 == 0 or chunk_end == total_rows:
                logging.info(f"  Progress: {chunk_end:,}/{total_rows:,} ({chunk_end*100//total_rows}%) - Extracted: {processed_count:,}")
        
        # Free the table
        del table
        
        # REAL FIX: Merge all saved chunks into final file
        if saved_chunks:
            logging.info(f"  🔗 Merging {len(saved_chunks)} chunks into final file...")
            all_dfs = []
            for chunk_file in saved_chunks:
                df = pd.read_feather(chunk_file)
                all_dfs.append(df)
            
            final_df = pd.concat(all_dfs, ignore_index=True)
            final_df = final_df.drop_duplicates(subset=["text", "hostname"])
            final_df.to_feather(output_file)
            
            # Clean up temporary files
            for chunk_file in saved_chunks:
                try:
                    os.remove(chunk_file)
                except Exception as e:
                    logging.warning(f"  Could not remove temp file {chunk_file}: {e}")
            
            logging.info(f"  ✅ Saved: {os.path.basename(output_file)} ({len(final_df):,} articles)")
            del all_dfs, final_df
            return True
        else:
            logging.warning(f"  ⚠️  No valid articles extracted from {os.path.basename(filename)}")
            return False
            
    except Exception as e:
        logging.error(f"  ❌ Error processing {os.path.basename(filename)}: {e}")
        import traceback
        logging.error(traceback.format_exc())
        
        # Clean up any temp files on error
        if 'saved_chunks' in locals():
            for chunk_file in saved_chunks:
                try:
                    if os.path.exists(chunk_file):
                        os.remove(chunk_file)
                except:
                    pass
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

