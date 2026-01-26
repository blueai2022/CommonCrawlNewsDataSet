# Fresh Machine Setup Guide - CommonCrawl News Dataset

Complete setup guide for downloading and processing CommonCrawl News data on GitHub Codespaces or Linux.

## Prerequisites

- **GitHub Codespaces** or **Ubuntu/Debian Linux**
- **100+ GB free disk space** (for our plan: 2 files/month, Aug 2016 - Dec 2019)
  - ⚠️ **Codespaces default**: 32 GB (insufficient!)
  - **Recommended**: Request larger Codespace or use external storage
- **Internet connection** (stable, preferably fast)
- **Time**: Setup ~15 min, Download 3-7 hours, Processing 40-50 hours

## ⚠️ Important: Codespaces Storage Limitation

**Default Codespaces (32 GB) is NOT enough for this project.**

**Options:**
1. **Request larger Codespace** (contact your org admin for 64+ GB)
2. **Use selective download** (1 file per month instead of 2)
3. **Clean intermediate files** frequently
4. **Use persistent external storage** (mount cloud storage)

For this guide, we'll use **Option 2**: Download 1 file per month (41 files total = ~20-30 GB)

## Part 1: Initial Setup (15 minutes)

### Step 1: Verify Python Installation

```bash
# Codespaces comes with Python pre-installed
python3 --version
# Should show: Python 3.10+ or 3.11+

# If not installed (unlikely in Codespaces):
sudo apt update
sudo apt install -y python3 python3-pip python3-venv
```

### Step 2: Fork and Open in Codespaces

#### A. Fork the Repository

1. Visit: https://github.com/LennartKriesch/CommonCrawl_NewsDataset
2. Click **"Fork"** (top right)
3. This creates: `https://github.com/YOUR_USERNAME/CommonCrawl_NewsDataset`

#### B. Open in Codespaces

1. On **your fork's page**, click the green **"Code"** button
2. Select **"Codespaces"** tab
3. Click **"Create codespace on main"**

**OR** use this direct link (replace YOUR_USERNAME):
```
https://github.com/codespaces/new?hide_repo_select=true&ref=main&repo=YOUR_USERNAME/CommonCrawl_NewsDataset
```

#### C. Verify Setup

Once Codespaces opens:

```bash
# Check you're in the right directory
pwd
# Should show: /workspaces/CommonCrawl_NewsDataset

# Check git status
git remote -v
# Should show your fork as 'origin'

# List files to verify repo contents
ls -la
# Should see: Project_Scripts/, requirements.txt, README.md, etc.
```

#### D. Add Upstream (Optional - for staying updated)

```bash
# Add original repo as upstream
git remote add upstream https://github.com/LennartKriesch/CommonCrawl_NewsDataset.git

# Verify
git remote -v
# Should now show:
# origin    https://github.com/YOUR_USERNAME/CommonCrawl_NewsDataset.git
# upstream  https://github.com/LennartKriesch/CommonCrawl_NewsDataset.git

# To pull future updates from original:
git fetch upstream
git merge upstream/main
```

### Step 3: Check Available Disk Space

```bash
# Check available space
df -h /workspaces

# Should show:
# Filesystem      Size  Used Avail Use% Mounted on
# overlay          32G  5.0G   27G  16% /workspaces  ← Need 20-30 GB free minimum
```

### Step 4: Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Your prompt should now show (venv) at the beginning
# Example: (venv) @user ➜ /workspaces/CommonCrawl_NewsDataset $
```

### Step 5: Install System Dependencies

```bash
# Install required system packages
sudo apt update
sudo apt install -y \
    build-essential \
    curl \
    sqlite3 \
    git

# Verify installations
curl --version
sqlite3 --version
```

### Step 6: Install Python Dependencies

```bash
# Make sure venv is activated
source venv/bin/activate

# Upgrade pip first
pip install --upgrade pip

# Install all requirements
pip install -r requirements.txt

# This will install:
# - requests (for downloading)
# - pandas, pyarrow (for data processing)
# - trafilatura (for text extraction)
# - spacy (for NER)
# - geopy (for geocoding)
# - tqdm (for progress bars)
# - warcio (for reading WARC files)
# - sentence-transformers (for embeddings, optional)
# - usearch (for vector database, optional)
```

### Step 7: Install spaCy Language Model

```bash
# Download the base English model
python -m spacy download en_core_web_sm

# Download the custom geolocation NER model
# Note: This is a large download (~500 MB)
pip install https://huggingface.co/LKriesch/LLAMA_fast_geotag/resolve/main/en_geonames-0.0.0.tar.gz
```

### Step 8: Create Data Directory

```bash
# For Codespaces, use /workspaces for persistence
# For regular Linux, use ~/Data

# Codespaces:
mkdir -p /workspaces/CommonCrawl/news

# Regular Linux:
# mkdir -p ~/Data/CommonCrawl/news

# Update the download path in scripts (see Step 9)
```

### Step 9: Update Download Path for Codespaces

````python
// filepath: [01_download_newscrawl.py](http://_vscodecontentref_/0)
// ...existing code...

# Change line 49 from:
DOWNLOAD_FOLDER = os.path.join(os.path.expanduser("~"), "Data", "CommonCrawl", "news", folder)

# To:
DOWNLOAD_FOLDER = os.path.join("/workspaces", "CommonCrawl", "news", folder)

// ...existing code...
`````

## Part 2: Download Helper Scripts

### Create Download Script

```bash
# Make sure you're in the project directory
cd ~/Projects/CommonCrawl_NewsDataset

# Create the download script
cat > download_two_per_month.sh << 'EOF'
#!/bin/bash

# Download 2 random files from each month (Aug 2016 - Dec 2019)
# This gives a good sample across time without overwhelming storage

START_YEAR=2016
START_MONTH=8
END_YEAR=2019
END_MONTH=12

BASE_PATH="$HOME/Data/CommonCrawl/news"
mkdir -p "$BASE_PATH"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📥 CommonCrawl News - Download 2 Random Files Per Month"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📅 Period: $(printf "%04d/%02d" $START_YEAR $START_MONTH) to $(printf "%04d/%02d" $END_YEAR $END_MONTH)"
echo "📊 Files per month: 2"
echo "💾 Download location: $BASE_PATH"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

total_months=0
total_downloaded=0
total_skipped=0
failed_months=0

current_year=$START_YEAR
current_month=$START_MONTH

while [ "$current_year" -le "$END_YEAR" ]; do
    while [ "$current_month" -le 12 ]; do
        # Check if we've passed the end date
        if [ "$current_year" -eq "$END_YEAR" ] && [ "$current_month" -gt "$END_MONTH" ]; then
            break 2
        fi
        
        # Format as YYYY/MM
        month_folder=$(printf "%04d/%02d" $current_year $current_month)
        month_dir=$(printf "%04d-%02d" $current_year $current_month)
        
        total_months=$((total_months + 1))
        
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "📅 Month $total_months: $month_folder"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        # Create directory
        mkdir -p "$BASE_PATH/$month_dir/warc"
        
        # Get file list
        file_list_url="https://data.commoncrawl.org/crawl-data/CC-NEWS/$month_folder/warc.paths.gz"
        
        # Download and parse file list
        echo "📋 Fetching file list..."
        file_list=$(curl -sf "$file_list_url" | gunzip 2>/dev/null)
        
        if [ -z "$file_list" ]; then
            echo "⚠️  No data available for $month_folder"
            failed_months=$((failed_months + 1))
            current_month=$((current_month + 1))
            echo ""
            continue
        fi
        
        # Count total files
        total_files=$(echo "$file_list" | wc -l | tr -d ' ')
        echo "📊 Total files available: $total_files"
        
        # Download 2 random files
        for i in 1 2; do
            # Pick a random file
            random_line=$((1 + RANDOM % total_files))
            file_path=$(echo "$file_list" | sed -n "${random_line}p")
            filename=$(basename "$file_path")
            
            # Check if already downloaded
            if [ -f "$BASE_PATH/$month_dir/warc/$filename" ]; then
                file_size=$(du -h "$BASE_PATH/$month_dir/warc/$filename" | cut -f1)
                echo "  ✅ File $i already exists: $filename ($file_size)"
                total_skipped=$((total_skipped + 1))
            else
                echo "  📥 Downloading file $i (#$random_line of $total_files): $filename"
                
                # Download the file
                download_url="https://data.commoncrawl.org/$file_path"
                if curl -# -o "$BASE_PATH/$month_dir/warc/$filename" "$download_url" 2>/dev/null; then
                    file_size=$(du -h "$BASE_PATH/$month_dir/warc/$filename" | cut -f1)
                    echo "     ✅ Downloaded: $file_size"
                    total_downloaded=$((total_downloaded + 1))
                else
                    echo "     ❌ Download failed"
                    rm -f "$BASE_PATH/$month_dir/warc/$filename"
                fi
            fi
        done
        
        echo ""
        current_month=$((current_month + 1))
    done
    
    current_month=1
    current_year=$((current_year + 1))
done

# Calculate summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Download Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Summary:"
echo "   Months processed: $total_months"
echo "   Files downloaded (new): $total_downloaded"
echo "   Files skipped (existing): $total_skipped"
echo "   Failed months: $failed_months"
echo ""

total_files_on_disk=$(find "$BASE_PATH" -name "*.warc.gz" | wc -l | tr -d ' ')
total_size=$(du -sh "$BASE_PATH" 2>/dev/null | cut -f1)

echo "📁 Current state:"
echo "   Total files on disk: $total_files_on_disk"
echo "   Total storage used: $total_size"
echo "   Data location: $BASE_PATH"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🚀 Next Steps:"
echo "   1. Process the downloaded files:"
echo "      source venv/bin/activate"
echo "      ./process_all_months.sh"
echo ""
echo "   2. Or process manually for each month:"
echo "      cd Project_Scripts"
echo "      python 02_extract_newscrawl.py 2016/08"
echo "      python 03_extract_text.py 2016/08"
echo "      # ... etc"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
EOF

chmod +x download_two_per_month.sh
```

### Create Processing Script

```bash
cat > process_all_months.sh << 'EOF'
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
EOF

chmod +x process_all_months.sh
```

### Create Progress Checker

```bash
cat > check_progress.sh << 'EOF'
#!/bin/bash

# Check processing progress for a specific month
# Usage: ./check_progress.sh YYYY/MM

if [ -z "$1" ]; then
    echo "Usage: ./check_progress.sh YYYY/MM"
    echo "Example: ./check_progress.sh 2016/08"
    exit 1
fi

MONTH_INPUT="$1"
MONTH_DIR=$(echo $MONTH_INPUT | tr '/' '-')
BASE="$HOME/Data/CommonCrawl/news/$MONTH_DIR"
DB="$HOME/Data/CommonCrawl/news/news_database.db"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Progress for $MONTH_INPUT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ ! -d "$BASE" ]; then
    echo "❌ Month directory not found: $BASE"
    exit 1
fi

# Count files at each stage
warc_count=$(ls $BASE/warc/*.warc.gz 2>/dev/null | wc -l | tr -d ' ')
extract_count=$(ls $BASE/02_warc/*.feather 2>/dev/null | wc -l | tr -d ' ')
text_count=$(ls $BASE/03_text/*.feather 2>/dev/null | wc -l | tr -d ' ')
quality_count=$(ls $BASE/04_quality/*.feather 2>/dev/null | wc -l | tr -d ' ')
filtered_count=$(ls $BASE/05_filtered/*.feather 2>/dev/null | wc -l | tr -d ' ')
ner_count=$(ls $BASE/06_ner/*.feather 2>/dev/null | wc -l | tr -d ' ')
geocoded_count=$(ls $BASE/07_geocoded/*.feather 2>/dev/null | wc -l | tr -d ' ')

echo "📥 Files:"
echo "   WARC downloaded:     $warc_count"
echo "   Extracted:           $extract_count"
echo "   Text parsed:         $text_count"
echo "   Quality filtered:    $quality_count"
echo "   Final filtered:      $filtered_count"
echo "   NER processed:       $ner_count"
echo "   Geocoded:            $geocoded_count"
echo ""

# Get database stats
if [ -f "$DB" ]; then
    db_articles=$(sqlite3 "$DB" "SELECT COUNT(*) FROM articles WHERE date LIKE '${MONTH_DIR}%'" 2>/dev/null || echo "0")
    echo "💾 Database:"
    echo "   Articles in DB:      $db_articles"
else
    echo "💾 Database: Not created yet"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Show next step
if [ $warc_count -eq 0 ]; then
    echo "🎯 Next: Download files"
elif [ $extract_count -lt $warc_count ]; then
    echo "🎯 Next: python 02_extract_newscrawl.py $MONTH_INPUT"
elif [ $text_count -lt $extract_count ]; then
    echo "🎯 Next: python 03_extract_text.py $MONTH_INPUT"
elif [ $ner_count -lt $filtered_count ]; then
    echo "🎯 Next: python 06_named_entity_recognition.py $MONTH_INPUT"
elif [ $geocoded_count -lt $ner_count ]; then
    echo "🎯 Next: python 07_geocode_news.py $MONTH_INPUT"
elif [ "$db_articles" = "0" ]; then
    echo "🎯 Next: python 08_sqlite_setup.py $MONTH_INPUT"
else
    echo "✅ Processing complete!"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
EOF

chmod +x check_progress.sh
```

## Part 3: Execute the Plan

### Quick Test First (Recommended)

```bash
# Activate virtual environment
source venv/bin/activate

# Download just 1 file from first month to test
cd Project_Scripts
python 01_download_newscrawl.py 2016/08

# This will download ALL files for August 2016 (only 2-3 files exist)
# Wait for it to complete (~5-10 minutes)

# Process it
python 02_extract_newscrawl.py 2016/08
python 03_extract_text.py 2016/08
python 04_compute_quality_metrics.py 2016/08
python 05_filter_news.py 2016/08
python 06_named_entity_recognition.py 2016/08
python 07_geocode_news.py 2016/08
python 08_sqlite_setup.py 2016/08

# Check results
cd ..
./check_progress.sh 2016/08
```

### Full Download and Processing

```bash
# Make sure you're in the project directory
cd ~/Projects/CommonCrawl_NewsDataset

# Activate virtual environment
source venv/bin/activate

# Start the download (runs in foreground)
# This will take 3-7 hours
./download_two_per_month.sh

# After download completes, process everything
# This will take 40-50 hours
./process_all_months.sh
```

### Run in Background (Recommended for Long Tasks)

```bash
# Activate virtual environment
source venv/bin/activate

# Run download in background with logging
nohup ./download_two_per_month.sh > download.log 2>&1 &

# Monitor progress
tail -f download.log

# After download, process in background
nohup ./process_all_months.sh > process.log 2>&1 &

# Monitor processing
tail -f process.log
```

## Part 4: Monitor and Verify

### Check Overall Progress

```bash
# Count total downloaded files
find ~/Data/CommonCrawl/news -name "*.warc.gz" | wc -l
# Target: 82 files (2 files × 41 months)

# Check database
sqlite3 ~/Data/CommonCrawl/news/news_database.db "SELECT COUNT(*) FROM articles"
# Expected: ~820,000 - 2,460,000 articles

# Check storage
du -sh ~/Data/CommonCrawl/news
# Expected: ~40-80 GB
```

### Query Your Data

```bash
# Activate virtual environment
source venv/bin/activate

# Start Python
python3
```

```python
import sqlite3
import os

# Connect to database
db_path = os.path.expanduser("~/Data/CommonCrawl/news/news_database.db")
conn = sqlite3.connect(db_path)

# Get total articles
count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
print(f"Total articles: {count:,}")

# Get articles by country
country_counts = conn.execute("""
    SELECT l.country, COUNT(DISTINCT a.article_id) as article_count
    FROM articles a
    JOIN article_locations al ON a.article_id = al.article_id
    JOIN locations l ON al.location_id = l.location_id
    GROUP BY l.country
    ORDER BY article_count DESC
    LIMIT 10
""").fetchall()

print("\nTop 10 countries by article count:")
for country, count in country_counts:
    print(f"  {country}: {count:,} articles")

# Get articles over time
monthly_counts = conn.execute("""
    SELECT strftime('%Y-%m', date) as month, COUNT(*) as count
    FROM articles
    GROUP BY month
    ORDER BY month
""").fetchall()

print("\nArticles per month:")
for month, count in monthly_counts[:10]:
    print(f"  {month}: {count:,} articles")

conn.close()
```

## Troubleshooting

### Virtual Environment Not Activating

```bash
# Make sure you're in the project directory
cd ~/Projects/CommonCrawl_NewsDataset

# Try activating again
source venv/bin/activate

# If still fails, recreate it
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### SSL Certificate Errors

```bash
# Install Python certificates
/Applications/Python\ 3.*/Install\ Certificates.command

# Or upgrade certifi
pip install --upgrade certifi
```

### Out of Disk Space

```bash
# Check what's using space
du -sh ~/Data/CommonCrawl/news/*

# Remove intermediate files (keep only WARC and database)
rm -rf ~/Data/CommonCrawl/news/*/02_warc
rm -rf ~/Data/CommonCrawl/news/*/03_text
rm -rf ~/Data/CommonCrawl/news/*/04_quality
rm -rf ~/Data/CommonCrawl/news/*/05_filtered
rm -rf ~/Data/CommonCrawl/news/*/06_ner
rm -rf ~/Data/CommonCrawl/news/*/07_geocoded

# You can reprocess from WARC files anytime
```

### Script Fails During Processing

```bash
# Check which month failed
./check_progress.sh 2016/08

# Resume from that month
source venv/bin/activate
cd Project_Scripts
python 02_extract_newscrawl.py 2016/08
# ... continue with remaining steps
```

## Timeline Summary

| Task | Duration | Can Pause? |
|------|----------|------------|
| Setup | 30 min | ✅ Yes |
| Download (82 files) | 3-7 hours | ✅ Yes |
| Processing (82 files) | 40-50 hours | ✅ Yes |
| **Total** | **44-58 hours** | ✅ Yes |

**Recommendation:**
- Day 1: Setup (30 min) + Start download overnight
- Day 2: Download finishes, start processing over weekend
- Day 3-4: Processing completes

## Final Result

After everything completes:
- ✅ 82 WARC files (2 per month × 41 months)
- ✅ ~820K - 2.4M articles
- ✅ Geographic data for all articles
- ✅ SQLite database at `~/Data/CommonCrawl/news/news_database.db`
- ✅ Time series from August 2016 - December 2019
- ✅ ~40-80 GB total storage

Ready to start? Begin with Part 1, Step 1!

### Codespaces-Specific Setup

1. **Storage**: Codespaces has limited disk space (32 GB default). Monitor usage:
   ```bash
   df -h ~
   ```

2. **Persistence**: Data in `/workspaces` persists, but `~/Data` may not. Use:
   ```bash
   mkdir -p /workspaces/CommonCrawl/news
   # Update scripts to use: /workspaces/CommonCrawl/news
   ```

3. **Performance**: Codespaces CPUs are limited. Reduce parallel processing:
   - In [`01_download_newscrawl.py`](Project_Scripts/01_download_newscrawl.py): Change `max_workers=10` → `max_workers=2`
   - In other scripts: Adjust `Pool(processes=...)` to use fewer cores

## Resource Management in Codespaces

Monitor your usage to avoid running out of space:

```bash
# Check disk space
df -h ~

# Check memory usage
free -h

# Find largest directories
du -h ~/Data/CommonCrawl/news | sort -rh | head -10

# Clean up intermediate files
rm -rf ~/Data/CommonCrawl/news/2024-01/02_warc/
```
