#!/bin/bash

# Process all downloaded months through the entire pipeline

BASE_PATH="/data/CommonCrawl/news"
SCRIPT_DIR="$(pwd)/Project_Scripts"
DB_PATH="$BASE_PATH/news_database.db"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚙️  Processing All Downloaded CommonCrawl News Data"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "❌ Virtual environment not activated!"
    echo "   Please run: source venv/bin/activate"
    exit 1
fi

# Check for required files
TLDS_FILE="$SCRIPT_DIR/tlds_exclusion.xlsx"
SPACY_MODEL="en_geonames"
GEOMAP_FILE="$BASE_PATH/geomap.xlsx"

if [ ! -f "$TLDS_FILE" ]; then
    echo "⚠️  Warning: TLD exclusion file not found at $TLDS_FILE"
    echo "   Creating a minimal version..."
    
    # Check if openpyxl is installed
    python3 -c "import openpyxl" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "   Installing openpyxl..."
        pip install -q openpyxl
    fi
    
    # Create a minimal TLD exclusion file if it doesn't exist
    python3 << EOF
import pandas as pd
import os

# Common TLDs to exclude
tlds = []  # Empty list = keep ALL countries
df = pd.DataFrame({'Country Code': tlds})

try:
    df.to_excel('$TLDS_FILE', index=False)
    print(f"✅ Created TLD exclusion file with {len(tlds)} entries")
except Exception as e:
    print(f"❌ Failed to create TLD file: {e}")
    exit(1)
EOF
    
    if [ $? -ne 0 ]; then
        echo "❌ Failed to create TLD exclusion file"
        exit 1
    fi
fi

# Find all month directories with WARC files
months_to_process=()
for month_dir in "$BASE_PATH"/*/; do
    if [ -d "$month_dir/warc" ] && [ "$(ls -A "$month_dir/warc"/*.warc.gz 2>/dev/null)" ]; then
        month_name=$(basename "$month_dir")
        # Convert 2016-08 to 2016/08
        month_param="${month_name:0:4}/${month_name:5:2}"
        months_to_process+=("$month_param")
    fi
done

if [ ${#months_to_process[@]} -eq 0 ]; then
    echo "❌ No months with WARC files found in $BASE_PATH"
    echo "   Run download_two_per_month.sh first"
    exit 1
fi

echo "📅 Found ${#months_to_process[@]} months to process:"
for month in "${months_to_process[@]}"; do
    echo "   - $month"
done
echo ""

# Ask for confirmation (skip if running non-interactively)
if [ -t 0 ]; then
    # stdin is a terminal, we can ask for confirmation
    read -p "Continue with processing? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cancelled."
        exit 0
    fi
else
    # Non-interactive (nohup, cron, etc.), auto-continue
    echo "Running non-interactively, auto-continuing..."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Process each month
total_months=${#months_to_process[@]}
current=0

for month in "${months_to_process[@]}"; do
    current=$((current + 1))
    
    # Convert month format: 2016/08 -> 2016-08
    month_dir=$(echo "$month" | tr '/' '-')
    MONTH_PATH="$BASE_PATH/$month_dir"
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📅 Processing Month $current/$total_months: $month"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    cd "$SCRIPT_DIR" || exit 1
    
    # Create necessary directories
    mkdir -p "$MONTH_PATH/03_text"
    mkdir -p "$MONTH_PATH/04_quality"
    mkdir -p "$MONTH_PATH/05_filtered"
    mkdir -p "$MONTH_PATH/06_ner"
    
    # Step 02: Extract from WARC
    # Note: 02_extract_newscrawl.py saves .feather files to the SAME folder as WARC files
    # and deletes WARC files after processing
    echo ""
    echo "🔧 Step 02: Extracting from WARC files..."
    if [ -d "$MONTH_PATH/warc" ] && [ "$(ls -A "$MONTH_PATH/warc"/*.warc.gz 2>/dev/null)" ]; then
        python 02_extract_newscrawl.py "$MONTH_PATH/warc" || echo "⚠️  Step 02 had issues"
    else
        echo "⚠️  No WARC files found in $MONTH_PATH/warc"
    fi
    
    # Step 03: Extract text
    # Input: .feather files from warc folder
    # Output: *_processed.feather files in the SAME folder
    echo ""
    echo "📝 Step 03: Extracting article text..."
    if [ "$(ls -A "$MONTH_PATH/warc"/*.feather 2>/dev/null)" ]; then
        python 03_extract_text.py "$MONTH_PATH/warc" "$TLDS_FILE" || echo "⚠️  Step 03 had issues"
        # Move processed files to 03_text folder and remove unprocessed ones
        mv "$MONTH_PATH/warc"/*_processed.feather "$MONTH_PATH/03_text/" 2>/dev/null || true
        # Remove non-processed feather files from warc folder
        rm -f "$MONTH_PATH/warc"/*.feather 2>/dev/null || true
    else
        echo "⚠️  No feather files found in $MONTH_PATH/warc after extraction"
    fi
    
    # Step 04: Compute quality metrics
    echo ""
    echo "📊 Step 04: Computing quality metrics..."
    if [ "$(ls -A "$MONTH_PATH/03_text"/*.feather 2>/dev/null)" ]; then
        python 04_compute_quality_metrics.py "$MONTH_PATH/03_text" "$MONTH_PATH/04_quality" || echo "⚠️  Step 04 had issues"
    else
        echo "⚠️  No feather files found in $MONTH_PATH/03_text"
    fi
    
    # Step 05: Filter news
    echo ""
    echo "🔍 Step 05: Filtering articles..."
    if [ "$(ls -A "$MONTH_PATH/04_quality"/*.feather 2>/dev/null)" ]; then
        python 05_filter_news.py "$MONTH_PATH/04_quality" "$MONTH_PATH/05_filtered" || echo "⚠️  Step 05 had issues"
    else
        echo "⚠️  No feather files found in $MONTH_PATH/04_quality"
    fi
    
    # Step 06: Named entity recognition (slowest step)
    echo ""
    echo "🗺️  Step 06: Named entity recognition (this may take a while)..."
    if [ "$(ls -A "$MONTH_PATH/05_filtered"/*.feather 2>/dev/null)" ]; then
        python 06_named_entity_recognition.py "$MONTH_PATH/05_filtered" "$MONTH_PATH/06_ner" "$SPACY_MODEL" || echo "⚠️  Step 06 had issues"
    else
        echo "⚠️  No feather files found in $MONTH_PATH/05_filtered"
    fi
    
    # Step 07: Geocode (only run once to create geomap)
    echo ""
    echo "🌍 Step 07: Geocoding locations..."
    if [ ! -f "$GEOMAP_FILE" ]; then
        if [ "$(find "$BASE_PATH" -path "*/06_ner/*.feather" 2>/dev/null | head -1)" ]; then
            echo "   Creating geomap from all NER files (this only needs to run once)..."
            python 07_geocode_news.py || echo "⚠️  Step 07 had issues"
        else
            echo "⚠️  No NER files found in any month directory"
        fi
    else
        echo "   ✅ Geomap already exists at $GEOMAP_FILE, skipping"
    fi
    
    # Step 08: SQLite setup
    echo ""
    echo "💾 Step 08: Loading into SQLite database..."
    if [ -f "$GEOMAP_FILE" ] && [ "$(ls -A "$MONTH_PATH/06_ner"/*.feather 2>/dev/null)" ]; then
        python 08_sqlite_setup.py "$MONTH_PATH/06_ner" "$GEOMAP_FILE" "$DB_PATH" || echo "⚠️  Step 08 had issues"
    else
        if [ ! -f "$GEOMAP_FILE" ]; then
            echo "⚠️  Geomap file not found: $GEOMAP_FILE"
        fi
        if [ ! "$(ls -A "$MONTH_PATH/06_ner"/*.feather 2>/dev/null)" ]; then
            echo "⚠️  No NER files found in $MONTH_PATH/06_ner"
        fi
    fi
    
    echo ""
    echo "✅ Completed processing $month"
    echo ""
    echo "📁 Storage cleanup (optional):"
    echo "   To save disk space, you can delete intermediate files:"
    echo "   rm -rf $MONTH_PATH/03_text $MONTH_PATH/04_quality $MONTH_PATH/05_filtered"
    echo "   (This keeps only warc/ and 06_ner/ for reprocessing if needed)"
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 All months processed!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Database summary:"
if [ -f "$DB_PATH" ]; then
    article_count=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM Articles;" 2>/dev/null)
    if [ $? -eq 0 ]; then
        echo "   Total articles in database: $article_count"
    else
        echo "   Database exists but query failed"
    fi
else
    echo "   ❌ Database not created"
fi
echo ""
echo "💾 Database location: $DB_PATH"
echo ""
echo "📦 Total storage used:"
du -sh "$BASE_PATH" 2>/dev/null || echo "   Could not calculate storage"
echo ""
