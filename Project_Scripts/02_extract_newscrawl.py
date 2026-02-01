import gzip
import os
import logging
from warcio.archiveiterator import ArchiveIterator
import pandas as pd
from os import listdir
from multiprocessing import Pool
from tqdm import tqdm
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

def extract_records(warc_file_path):
    """Extract records from a WARC file."""
    records = []
    try:
        with gzip.open(warc_file_path, 'rb') as stream:
            iterator = ArchiveIterator(stream)
            for record in iterator:
                if record.rec_type == 'response':
                    try:
                        warc_record_id = record.rec_headers.get_header('WARC-Record-ID')
                        url = record.rec_headers.get_header('WARC-Target-URI')
                        date = record.rec_headers.get_header('WARC-Date')
                        content_length = record.rec_headers.get_header('Content-Length')
                        mime_type = record.http_headers.get_header('Content-Type') if record.http_headers else None
                        content = record.content_stream().read()
                        records.append((warc_record_id, url, date, content_length, mime_type, content))
                    except Exception as e:
                        logging.warning(f"Error processing record in {warc_file_path}: {e}")
    except Exception as e:
        logging.error(f"Error extracting records from {warc_file_path}: {e}")
    
    return records

def process_warc_file(warc_file_path):
    """Process a single WARC file."""
    try:
        logging.info(f"Processing file: {warc_file_path}")
        
        # Extract records
        data = extract_records(warc_file_path)
        
        if data:
            # Convert to DataFrame
            df = pd.DataFrame(data, columns=["ID", "URL", "Date", "Content-Length", "MIME-Type", "Content"])
            
            # Save DataFrame as Feather file
            output_path = warc_file_path.replace(".warc.gz", ".feather")
            df.to_feather(output_path)
            logging.info(f"Saved Feather file: {output_path}")
            
            # Delete WARC file after successful processing
            os.remove(warc_file_path)
            logging.info(f"Deleted WARC file: {warc_file_path}")
        else:
            logging.warning(f"No records extracted from {warc_file_path}")
        
    except Exception as e:
        logging.error(f"Error processing {warc_file_path}: {e}")

if __name__ == '__main__':
    # Argument parser
    parser = argparse.ArgumentParser(description="Extract data from WARC files.")
    parser.add_argument(
        'folder',
        type=str,
        help="Folder containing WARC files (e.g., 'D:\\CommonCrawl\\News\\2024-01')."
    )
    args = parser.parse_args()
    folder = args.folder

    # Get list of WARC files
    files = [os.path.join(folder, f) for f in listdir(folder) if f.endswith(".warc.gz")]

    if not files:
        logging.error(f"No WARC files found in folder: {folder}")
        exit(1)

    # Use a multiprocessing Pool to process files concurrently
    # OPTIMIZED: Use only 2 processes to prevent multiple instance conflicts
    # With 8 vCPUs and large WARC files (500-800MB), 2 processes is optimal
    num_processes = min(2, os.cpu_count())
    logging.info(f"Found {len(files)} WARC files. Using {num_processes} processes...")
    
    with Pool(processes=num_processes) as pool:
        list(tqdm(pool.imap(process_warc_file, files), total=len(files), desc="Processing WARC files"))

    logging.info("All WARC files processed successfully.")
