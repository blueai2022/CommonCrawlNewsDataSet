#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export SQLite database tables to CSV files.

Usage:
    python dump_db_to_csv.py <db_path> [output_dir] [--limit N]
    
Example:
    python dump_db_to_csv.py /data/CommonCrawl/news/news_database.db ./csv_export
    python dump_db_to_csv.py /data/CommonCrawl/news/news_database.db ./csv_export --limit 1000
"""

import sqlite3
import pandas as pd
import os
import logging
from argparse import ArgumentParser
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def export_table_to_csv(cursor, table_name: str, output_dir: Path, limit: int = None):
    """Export a single table to CSV."""
    try:
        logging.info(f"📊 Exporting table: {table_name}")
        
        # Get row count
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        total_rows = cursor.fetchone()[0]
        logging.info(f"   Total rows: {total_rows:,}")
        
        if total_rows == 0:
            logging.warning(f"   ⚠️  Table {table_name} is empty, skipping")
            return
        
        # Determine how many rows to export
        rows_to_export = min(limit, total_rows) if limit else total_rows
        if limit and limit < total_rows:
            logging.info(f"   Limiting to: {rows_to_export:,} rows")
        
        # Read table into DataFrame with limit
        query = f"SELECT * FROM {table_name}"
        if limit:
            query += f" LIMIT {limit}"
        
        df = pd.read_sql_query(query, cursor.connection)
        
        # Export to CSV
        csv_path = output_dir / f"{table_name}.csv"
        df.to_csv(csv_path, index=False)
        
        file_size_mb = csv_path.stat().st_size / 1024 / 1024
        logging.info(f"   ✅ Exported to: {csv_path}")
        logging.info(f"   Rows: {len(df):,} / {total_rows:,}")
        logging.info(f"   Size: {file_size_mb:.2f} MB")
        
        return csv_path
        
    except Exception as e:
        logging.error(f"   ❌ Error exporting {table_name}: {e}")
        return None

def get_table_names(cursor):
    """Get all table names from the database."""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [row[0] for row in cursor.fetchall()]

def export_custom_queries(cursor, output_dir: Path, limit: int = None):
    """Export useful custom queries/views."""
    logging.info("📊 Exporting custom queries...")
    
    limit_clause = f" LIMIT {limit}" if limit else ""
    
    # Query 1: Articles with location count
    logging.info("   Creating: articles_with_location_count.csv")
    query1 = f"""
        SELECT 
            a.*,
            COUNT(DISTINCT al.location_id) as location_count
        FROM Articles a
        LEFT JOIN Article_Locations al ON a.id = al.article_id
        GROUP BY a.id{limit_clause}
    """
    df1 = pd.read_sql_query(query1, cursor.connection)
    df1.to_csv(output_dir / "articles_with_location_count.csv", index=False)
    logging.info(f"   ✅ {len(df1):,} rows")
    
    # Query 2: Location statistics
    logging.info("   Creating: location_statistics.csv")
    query2 = f"""
        SELECT 
            l.*,
            COUNT(DISTINCT al.article_id) as article_count
        FROM Locations l
        LEFT JOIN Article_Locations al ON l.location_id = al.location_id
        GROUP BY l.location_id
        ORDER BY article_count DESC{limit_clause}
    """
    df2 = pd.read_sql_query(query2, cursor.connection)
    df2.to_csv(output_dir / "location_statistics.csv", index=False)
    logging.info(f"   ✅ {len(df2):,} rows")
    
    # Query 3: Articles with locations (denormalized)
    logging.info("   Creating: articles_with_locations.csv")
    query3 = f"""
        SELECT 
            a.id,
            a.title,
            a.url,
            a.date,
            a.hostname,
            GROUP_CONCAT(l.loc_normal, '; ') as locations,
            GROUP_CONCAT(l.NUTS, '; ') as nuts_codes
        FROM Articles a
        LEFT JOIN Article_Locations al ON a.id = al.article_id
        LEFT JOIN Locations l ON al.location_id = l.location_id
        GROUP BY a.id{limit_clause}
    """
    df3 = pd.read_sql_query(query3, cursor.connection)
    df3.to_csv(output_dir / "articles_with_locations.csv", index=False)
    logging.info(f"   ✅ {len(df3):,} rows")

def main(db_path: str, output_dir: str = None, limit: int = None):
    """Main export function."""
    # Setup output directory
    if output_dir is None:
        output_dir = Path(db_path).parent / "csv_export"
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logging.info("=" * 70)
    logging.info("🗄️  SQLite Database to CSV Export")
    logging.info("=" * 70)
    logging.info(f"Database: {db_path}")
    logging.info(f"Output:   {output_dir}")
    if limit:
        logging.info(f"Limit:    {limit:,} rows per table")
    else:
        logging.info(f"Limit:    None (exporting all rows)")
    logging.info("")
    
    # Connect to database
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get database info
        cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
        db_size_mb = cursor.fetchone()[0] / 1024 / 1024
        logging.info(f"📊 Database size: {db_size_mb:.2f} MB")
        logging.info("")
        
        # Get all tables
        tables = get_table_names(cursor)
        logging.info(f"📋 Found {len(tables)} tables: {', '.join(tables)}")
        logging.info("")
        
        # Export each table
        exported_files = []
        for table in tables:
            csv_path = export_table_to_csv(cursor, table, output_dir, limit)
            if csv_path:
                exported_files.append(csv_path)
            logging.info("")
        
        # Export custom queries
        export_custom_queries(cursor, output_dir, limit)
        logging.info("")
        
        # Summary
        logging.info("=" * 70)
        logging.info("✅ Export Complete!")
        logging.info("=" * 70)
        logging.info(f"Exported {len(exported_files)} tables + 3 custom queries")
        
        total_size = sum(f.stat().st_size for f in exported_files) / 1024 / 1024
        logging.info(f"Total CSV size: {total_size:.2f} MB")
        logging.info(f"Output directory: {output_dir}")
        logging.info("")
        logging.info("Files created:")
        for f in sorted(output_dir.glob("*.csv")):
            size_mb = f.stat().st_size / 1024 / 1024
            logging.info(f"  • {f.name} ({size_mb:.2f} MB)")
        
    except sqlite3.Error as e:
        logging.error(f"❌ Database error: {e}")
        return 1
    except Exception as e:
        logging.error(f"❌ Error: {e}", exc_info=True)
        return 1
    finally:
        if conn:
            conn.close()
    
    return 0

if __name__ == "__main__":
    parser = ArgumentParser(description="Export SQLite database to CSV files.")
    parser.add_argument("db_path", type=str, help="Path to SQLite database file.")
    parser.add_argument("output_dir", type=str, nargs='?', default=None, 
                       help="Output directory for CSV files (default: <db_dir>/csv_export)")
    parser.add_argument("--limit", type=int, default=None,
                       help="Limit number of rows exported per table (default: export all rows)")
    
    args = parser.parse_args()
    exit(main(args.db_path, args.output_dir, args.limit))