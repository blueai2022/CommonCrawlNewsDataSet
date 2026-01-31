import os
import sqlite3
import pandas as pd
from typing import List, Tuple, Dict
from tqdm import tqdm
import hashlib
import logging
from argparse import ArgumentParser
import re

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Functions
def strip_uuid(uuid_str: str) -> str:
    """Convert UUID to a stripped format."""
    if uuid_str.startswith("<urn:uuid:") and uuid_str.endswith(">"):
        return uuid_str[10:-1]
    return uuid_str

def extract_tld(hostname: str) -> str:
    """Extract the top-level domain (TLD) from a hostname."""
    try:
        return hostname.split('.')[-1]
    except Exception:
        return ""

def hash_uuid(uuid_str: str) -> int:
    """Generate a hashed integer (63-bit) from UUID using SHA-256."""
    return int(hashlib.sha256(uuid_str.encode()).hexdigest(), 16) % (2**63 - 1)

def create_tables(cursor):
    """Create database tables if they don't exist."""
    logging.info("Creating database tables...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Articles (
            id TEXT PRIMARY KEY,
            url TEXT,
            excerpt TEXT,
            title TEXT,
            text TEXT,
            tags TEXT,
            categories TEXT,
            hostname TEXT,
            date TEXT,
            date_crawled TEXT
        );
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Locations (
            location_id INTEGER PRIMARY KEY,
            loc_normal TEXT UNIQUE,
            latitude REAL,
            longitude REAL,
            NUTS TEXT,
            GEN TEXT
        );
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Article_Locations (
            article_id TEXT,
            location_id INTEGER,
            FOREIGN KEY (article_id) REFERENCES Articles(id),
            FOREIGN KEY (location_id) REFERENCES Locations(location_id)
        );
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Article_Vectors (
            id TEXT PRIMARY KEY,
            hashed_id INTEGER UNIQUE
        );
    ''')
    cursor.connection.commit()

def load_location_mapping(geomap_path: str) -> Tuple[Dict[str, int], pd.DataFrame]:
    """Load location mapping from geomap."""
    logging.info(f"Loading geomap from {geomap_path}...")
    df = pd.read_excel(geomap_path)
    required_columns = {'loc_normal', 'latitude', 'longitude', 'NUTS', 'GEN'}
    if not required_columns.issubset(df.columns):
        raise ValueError(f"The geomap file is missing required columns: {required_columns}")
    df['location_id'] = df['loc_normal'].apply(lambda x: int(hashlib.sha1(x.encode()).hexdigest(), 16) % (10**8))
    location_map = dict(zip(df['loc_normal'], df['location_id']))
    return location_map, df[['location_id', 'loc_normal', 'latitude', 'longitude', 'NUTS', 'GEN']]

def insert_locations(df: pd.DataFrame, cursor):
    """Insert location data into the database."""
    logging.info("Inserting location data...")
    locations = df.to_records(index=False).tolist()
    cursor.executemany('''
        INSERT OR IGNORE INTO Locations (location_id, loc_normal, latitude, longitude, NUTS, GEN)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', locations)
    cursor.connection.commit()

def load_and_insert_metadata(directory: str, location_map: Dict[str, int], cursor):
    """Load metadata from files and insert it into the database."""
    logging.info(f"Processing metadata files in {directory}...")
    for filename in tqdm(os.listdir(directory)):
        if filename.endswith('.feather'):
            try:
                file_path = os.path.join(directory, filename)
                data = pd.read_feather(file_path)

                # Ensure required columns exist
                required_columns = {'id', 'url', 'excerpt', 'title', 'text', 'tags', 
                                    'categories', 'hostname', 'date', 'date_crawled', 'loc_normal'}
                missing_columns = required_columns - set(data.columns)
                if missing_columns:
                    logging.error(f"Skipping {filename}: Missing columns {missing_columns}")
                    continue

                data["id"] = data["id"].apply(strip_uuid)
                data["tld"] = data["hostname"].apply(extract_tld)

                # Ensure 'loc_normal' exists and is cleaned properly
                data["loc_normal"] = data["loc_normal"].fillna("").astype(str).str.lower()
                data["loc_normal"] = data["loc_normal"].apply(lambda x: re.sub(r"[^a-zäöüß ']", "", x).strip())

                # Convert datetime columns to strings for SQLite compatibility
                if 'date' in data.columns:
                    data['date'] = pd.to_datetime(data['date'], errors='coerce').dt.strftime('%Y-%m-%d')
                if 'date_crawled' in data.columns:
                    data['date_crawled'] = pd.to_datetime(data['date_crawled'], errors='coerce').dt.strftime('%Y-%m-%d')

                articles = []
                article_locations = []
                article_vectors = []
                
                for _, row in data.iterrows():
                    articles.append((
                        row['id'], row['url'], row['excerpt'], row['title'], 
                        row['text'], row['tags'], row['categories'], row['hostname'], 
                        row.get('date', None), row.get('date_crawled', None)
                    ))
                    
                    location_id = location_map.get(row['loc_normal'])
                    if location_id:
                        article_locations.append((row['id'], location_id))

                    # Generate hashed ID for each article
                    hashed_id = hash_uuid(row['id'])
                    article_vectors.append((row['id'], hashed_id))

                # Perform batch inserts
                cursor.executemany('''
                    INSERT OR REPLACE INTO Articles (id, url, excerpt, title, text, tags, categories, hostname, date, date_crawled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', articles)

                cursor.executemany('''
                    INSERT OR IGNORE INTO Article_Locations (article_id, location_id)
                    VALUES (?, ?)
                ''', article_locations)

                cursor.executemany('''
                    INSERT OR IGNORE INTO Article_Vectors (id, hashed_id)
                    VALUES (?, ?)
                ''', article_vectors)
                
                cursor.connection.commit()  # Commit once per file for better performance

            except Exception as e:
                logging.error(f"Error processing file {filename}: {e}", exc_info=True)

# Main function
def main(text_metadata_dir, geomap_path, db_path):
    logging.info("Starting the database pipeline...")
    connection = sqlite3.connect(db_path, timeout=30)
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL;")
        create_tables(cursor)
        location_map, locations_df = load_location_mapping(geomap_path)
        insert_locations(locations_df, cursor)
        load_and_insert_metadata(text_metadata_dir, location_map, cursor)
    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True)
    finally:
        connection.close()
        logging.info("Pipeline completed.")

if __name__ == "__main__":
    parser = ArgumentParser(description="Store article metadata and geolocation data into SQLite database.")
    parser.add_argument("text_metadata_dir", type=str, help="Directory containing text metadata files.")
    parser.add_argument("geomap_path", type=str, help="Path to the geomap file.")
    parser.add_argument("db_path", type=str, help="Path to the SQLite database.")
    args = parser.parse_args()

    main(args.text_metadata_dir, args.geomap_path, args.db_path)
