# CSV Export Guide

This guide explains how to export the SQLite database to CSV format.

## Prerequisites

- Python 3.x installed
- SQLite database file (`news_database.db`)
- The `dump_db_to_csv.py` script

## Installation Steps

### 1. Set up Python Virtual Environment

Create and activate a virtual environment to isolate dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Required Dependencies

Install the necessary Python packages:

```bash
pip install 'pandas>=2.0.0'
pip install 'openpyxl>=3.1.0'
```

### 3. Export Database to CSV

Create the output directory and run the export script:

```bash
mkdir -p ./dump
python3 ./dump_db_to_csv.py ./news_database_01.db ./dump
```

This will export all database tables to CSV files in the `./dump` directory.

### 4. Verify the Export

Navigate to the dump directory and list the generated files:

```bash
cd dump/
ls -l
```

### 5. Inspect the CSV Files

View the first 10 rows and count the total rows in the exported files:

```bash
# Preview the Articles table
head -10 Articles.csv

# Count rows in Articles table
wc -l Articles.csv

# Count rows in articles_with_locations view
wc -l articles_with_locations.csv
```

## Output Files

The export will generate CSV files for each table in the database, including:
- `Articles.csv` - Main articles table
- `articles_with_locations.csv` - Articles with location data
- Additional tables as defined in the database schema
