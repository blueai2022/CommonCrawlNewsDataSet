# -*- coding: utf-8 -*-
"""
Script for computing quality metrics for news articles.

Updated for maintainability, efficiency, and robustness.
"""
import os
import re
import logging
import pandas as pd
from functools import partial
from multiprocessing import Pool, cpu_count
from tqdm import tqdm
from glob import glob
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# Pre-compile regular expressions
sentence_pattern = re.compile(r'\b[^.!?]+[.!?]*')

def compute_metrics(article):
    """Compute quality metrics for a single article."""
    bullet_points = {"\u2022", "\u2023", "\u25B6", "\u25C0", "\u25E6", "\u25A0", "\u25A1", "\u25AA", "\u25AB", "\u2013"}
    metrics = {
        "fraction_ellipsis": 0,
        "fraction_non_alpha_words": 0,
        "mean_word_length": 0,
        "javascript_count": article.lower().count("javascript"),
        "words_per_line": 0,
        "bullet_point_starts": 0,
        "sentences_count": len(sentence_pattern.findall(article)),
        "word_count": 0
    }

    total_word_length, non_alpha_word_count, total_words, ellipsis_count = 0, 0, 0, 0
    lines = article.split('\n')
    for line in lines:
        line_ended_with_ellipsis = line.endswith("...") or line.endswith("…")
        ellipsis_count += line_ended_with_ellipsis

        words = line.split()
        for word in words:
            non_alpha_word_count += not any(c.isalpha() for c in word)
            total_word_length += len(word)

        total_words += len(words)
        metrics["bullet_point_starts"] += int(line != "" and line[0] in bullet_points)

    metrics["fraction_ellipsis"] = ellipsis_count / len(lines) if lines else 0
    metrics["fraction_non_alpha_words"] = non_alpha_word_count / total_words if total_words else 0
    metrics["mean_word_length"] = total_word_length / total_words if total_words else 0
    metrics["words_per_line"] = total_words / len(lines) if lines else 0
    metrics["word_count"] = total_words

    return metrics

def process_and_save_file(file_path, save_dir):
    """Process a single file and save the result with computed metrics."""
    try:
        df = pd.read_feather(file_path)
        metrics_list = df['text'].apply(compute_metrics).tolist()
        metrics_df = pd.DataFrame(metrics_list)
        df_with_metrics = pd.concat([df, metrics_df], axis=1)

        filename = os.path.basename(file_path)
        save_path = os.path.join(save_dir, filename)

        if len(df_with_metrics) > 0:
            df_with_metrics.to_feather(save_path)
            logging.info(f"File saved: {save_path}")
        else:
            logging.warning(f"No data to save for file: {file_path}")
    except Exception as e:
        logging.error(f"Error processing file {file_path}: {e}")

def main(input_folder, output_folder, max_processes):
    """Main function to process all files in the input folder."""
    os.makedirs(output_folder, exist_ok=True)
    files = glob(os.path.join(input_folder, "*.feather"))

    if not files:
        logging.warning(f"No feather files found in folder: {input_folder}")
        return

    # Limit processes for quality metric computation
    # 6-8 is optimal for CPU-bound string operations
    num_processes = min(len(files), max_processes, 8)
    logging.info(f"Found {len(files)} files. Using {num_processes} processes...")
    
    process_func = partial(process_and_save_file, save_dir=output_folder)

    with Pool(processes=num_processes) as pool:
        for _ in tqdm(pool.imap_unordered(process_func, files), total=len(files), desc="Processing files"):
            pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute quality metrics for news articles.")
    parser.add_argument("input_folder", type=str, help="Folder containing input feather files.")
    parser.add_argument("output_folder", type=str, help="Folder to save processed files.")
    parser.add_argument("--max_processes", type=int, default=8, help="Maximum number of processes to use (default: 8).")
    args = parser.parse_args()

    main(args.input_folder, args.output_folder, args.max_processes)
