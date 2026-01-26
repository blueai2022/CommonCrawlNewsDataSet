#!/bin/bash

# Process all downloaded months through the entire pipeline

BASE_PATH="$HOME/Data/CommonCrawl/news"
SCRIPT_DIR="$(pwd)/Project_Scripts"

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

# Ask for confirmation
read -p "Continue with processing? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Process each month
total_months=${#months_to_process[@]}
current=0

for month in "${months_to_process[@]}"; do
    current=$((current + 1))
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📅 Processing Month $current/$total_months: $month"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    cd "$SCRIPT_DIR" || exit 1
    
    # Step 02: Extract from WARC
    echo ""
    echo "🔧 Step 02: Extracting from WARC files..."
    python 02_extract_newscrawl.py "$month" || echo "⚠️  Step 02 had issues"
    
    # Step 03: Extract text
    echo ""
    echo "📝 Step 03: Extracting article text..."
    python 03_extract_text.py "$month" || echo "⚠️  Step 03 had issues"
    
    # Step 04: Compute quality metrics
    echo ""
    echo "📊 Step 04: Computing quality metrics..."
    python 04_compute_quality_metrics.py "$month" || echo "⚠️  Step 04 had issues"
    
    # Step 05: Filter news
    echo ""
    echo "🔍 Step 05: Filtering articles..."
    python 05_filter_news.py "$month" || echo "⚠️  Step 05 had issues"
    
    # Step 06: Named entity recognition (slowest step)
    echo ""
    echo "🗺️  Step 06: Named entity recognition (this may take a while)..."
    python 06_named_entity_recognition.py "$month" || echo "⚠️  Step 06 had issues"
    
    # Step 07: Geocode
    echo ""
    echo "🌍 Step 07: Geocoding locations..."
    python 07_geocode_news.py "$month" || echo "⚠️  Step 07 had issues"
    
    # Step 08: SQLite setup
    echo ""
    echo "💾 Step 08: Loading into SQLite database..."
    python 08_sqlite_setup.py "$month" || echo "⚠️  Step 08 had issues"
    
    echo ""
    echo "✅ Completed processing $month"
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 All months processed!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Database summary:"
sqlite3 "$BASE_PATH/news_database.db" "SELECT COUNT(*) as total_articles FROM articles;" 2>/dev/null || echo "Database query failed"
echo ""
echo "💾 Database location: $BASE_PATH/news_database.db"
echo ""
