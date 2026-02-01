# -*- coding: utf-8 -*-
"""
Script for filtering processed news articles based on quality metrics.

Updated for better maintainability and robustness.
@author: Lukas-admin
"""
import os
import logging
import pandas as pd
from glob import glob
from functools import partial
from multiprocessing import Pool, cpu_count
from tqdm import tqdm
from argparse import ArgumentParser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

def process_and_save_file(file_path, save_dir):
    """Filter and save a single file based on quality metrics."""
    try:
        df = pd.read_feather(file_path)
    except Exception as e:
        logging.error(f"Error reading file {file_path}: {e}")
        return

    try:
        # Apply filtering criteria
        df = df[
            (df['javascript_count'] == 0) &
            (df["sentences_count"] >= 3) &
            (df["fraction_non_alpha_words"] < 0.1) &
            (df['words_per_line'] > 5) &
            (df["mean_word_length"].between(3, 12)) &
            (df["word_count"].between(50, 10000))
        ]
    except KeyError as e:
        logging.error(f"Missing expected column in file {file_path}: {e}")
        return

    if not df.empty:
        df = df.reset_index(drop=True)
        save_path = os.path.join(save_dir, os.path.basename(file_path))
        df.to_feather(save_path)
        logging.info(f"File saved: {save_path}")
    else:
        logging.warning(f"No valid rows in file {file_path}. Skipping.")

def main(input_folder, output_folder):
    """Main function to process and filter files."""
    os.makedirs(output_folder, exist_ok=True)

    # Get list of files to process, skipping already processed ones
    input_files = glob(os.path.join(input_folder, "*.feather"))
    processed_files = {os.path.basename(f) for f in glob(os.path.join(output_folder, "*.feather"))}
    files_to_process = [f for f in input_files if os.path.basename(f) not in processed_files]

    if not files_to_process:
        logging.info("No new files to process.")
        return

    logging.info(f"Found {len(files_to_process)} files to process.")
    process_func = partial(process_and_save_file, save_dir=output_folder)

    # OPTIMIZED: Use 2 workers to prevent I/O contention
    # Filtering is lightweight (pandas operations), but reading/writing large feather files
    # on network storage creates I/O bottleneck. 2 workers = optimal throughput on vCPUs
    num_processes = min(len(files_to_process), 2)
    logging.info(f"Using {num_processes} processes for filtering")
    
    with Pool(processes=num_processes) as pool:
        for _ in tqdm(pool.imap_unordered(process_func, files_to_process), total=len(files_to_process), desc="Processing files"):
            pass

if __name__ == "__main__":
    parser = ArgumentParser(description="Filter processed news articles based on quality metrics.")
    parser.add_argument("input_folder", type=str, help="Folder containing processed feather files.")
    parser.add_argument("output_folder", type=str, help="Folder to save filtered feather files.")
    args = parser.parse_args()

    main(args.input_folder, args.output_folder)
