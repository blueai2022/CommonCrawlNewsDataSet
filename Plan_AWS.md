# Fresh Machine Setup Guide - CommonCrawl News Dataset

Complete setup guide for downloading and processing CommonCrawl News data on **AWS Ubuntu** or any Linux machine.

## Prerequisites

- **AWS Ubuntu Instance** (recommended: t3.xlarge or larger) or **Ubuntu/Debian Linux**
- **100-200 GB free disk space** (for our plan: 2 files/month, Aug 2016 - Dec 2019)
  - 💰 **AWS Single Volume**: 240 GB root volume works great!
  - 🌍 **Region**: us-east-2 (Ohio) - $19.20/month for 240 GB gp3
  - ⚠️ **Storage will use**: ~40-120 GB depending on cleanup strategy
- **Internet connection** (stable, preferably fast)
- **Time**: Setup ~15 min, Download 3-7 hours, Processing 40-50 hours

## ⚠️ Important: Storage Setup

**Your configuration: 240 GB root volume at /**
- ✅ Plenty of space for everything
- ✅ No need for separate data volume
- ✅ Simpler setup and management
- 💾 Data location: `/data/CommonCrawl/news`

**Storage breakdown:**
```
System + applications:     ~10-15 GB
Python environment:        ~5-8 GB
Downloaded WARC files:     ~40-50 GB
Processing intermediate:   ~30-40 GB (can be cleaned)
Final database + NER:      ~15-25 GB
Buffer space:              ~100-140 GB free
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total available:           240 GB ✅
```

## Part 0: AWS Setup (If Using AWS)

### Your Current Configuration

✅ **Already done:**
- EC2 instance launched (t3.xlarge or similar)
- 240 GB gp3 volume attached as root (/)
- Ubuntu 24.04 LTS installed
- SSH access working

### Verify Your Setup

```bash
# Check total disk space
df -h /
# Should show ~240GB total

# Check available space
df -h / | awk 'NR==2 {print "Total:", $2, "Available:", $4, "Used:", $5}'

# Create data directory
sudo mkdir -p /data/CommonCrawl/news

# Set ownership (replace 'ubuntu' if using different user)
sudo chown -R $USER:$USER /data

# Verify write permissions
touch /data/test.txt && rm /data/test.txt && echo "✅ Write permissions OK"
```

## Part 1: Initial Setup (15 minutes)

### Step 1: Update System and Install Dependencies

```bash
# Update package lists
sudo apt update && sudo apt upgrade -y

# Install required system packages
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    build-essential \
    curl \
    wget \
    sqlite3 \
    git \
    htop \
    iotop \
    screen \
    tmux \
    tree

# Verify installations
python3 --version  # Should show Python 3.12+
curl --version
sqlite3 --version
git --version
```

### Step 2: Clone Repository

```bash
# Clone to home directory
cd ~
git clone https://github.com/LukasKriesch/CommonCrawlNewsDataSet.git
cd CommonCrawlNewsDataSet

# Verify
pwd
# Should show: /home/ubuntu/CommonCrawlNewsDataSet (or your username)

ls -la
# Should see: Project_Scripts/, requirements.txt, README.md, etc.
```

### Step 3: Check Available Disk Space

```bash
# Check root filesystem space
df -h /

# Example output:
# Filesystem      Size  Used Avail Use% Mounted on
# /dev/xvda1      236G   12G  224G   5% /

# Check /data directory
du -sh /data 2>/dev/null || echo "/data is empty (good!)"
```

### Step 4: Create Virtual Environment

```bash
# Create virtual environment in project directory
python3 -m venv venv

# Activate it
source venv/bin/activate

# Your prompt should now show (venv) at the beginning
# Example: (venv) ubuntu@ip-172-31-xx-xx:~/CommonCrawlNewsDataSet$
```

### Step 5: Install Python Dependencies

```bash
# Make sure venv is activated (you should see (venv) in prompt)
source venv/bin/activate

# Upgrade pip first
pip install --upgrade pip

# Install all requirements
pip install -r requirements.txt

# Verify key packages
python -c "import pandas; print(f'✅ pandas: {pandas.__version__}')"
python -c "import pyarrow; print(f'✅ pyarrow: {pyarrow.__version__}')"
python -c "import spacy; print(f'✅ spacy: {spacy.__version__}')"
```

### Step 6: Install spaCy Language Models

```bash
# Still in activated venv
# Download the base English model
python -m spacy download en_core_web_sm

# Download the custom geolocation NER model
# Note: This is a large download (~500 MB)
pip install https://huggingface.co/LKriesch/LLAMA_fast_geotag/resolve/main/en_geonames-0.0.0.tar.gz

# Verify installation
python -c "import spacy; nlp = spacy.load('en_geonames'); print('✅ en_geonames model loaded')"
```

### Step 7: Update Scripts to Use /data Path

```bash
# Update all helper scripts to use /data instead of ~/Data
cd ~/CommonCrawlNewsDataSet

# Update download script
sed -i 's|$HOME/Data/CommonCrawl|/data/CommonCrawl|g' download_two_per_month.sh

# Update process script  
sed -i 's|$HOME/Data/CommonCrawl|/data/CommonCrawl|g' process_all_months.sh

# Update check progress script
sed -i 's|$HOME/Data/CommonCrawl|/data/CommonCrawl|g' check_progress.sh

# Verify changes
echo "Checking download_two_per_month.sh:"
grep "BASE_PATH" download_two_per_month.sh
echo ""
echo "Checking process_all_months.sh:"
grep "BASE_PATH" process_all_months.sh
echo ""
echo "Checking check_progress.sh:"
grep "BASE=" check_progress.sh

# All should show /data/CommonCrawl/news
```

### Step 8: Create Data Directory Structure

```bash
# Create main data directory (already created in Part 0, but verify)
sudo mkdir -p /data/CommonCrawl/news
sudo chown -R $USER:$USER /data

# Verify
ls -ld /data/CommonCrawl/news
# Should show: drwxrwxr-x ubuntu ubuntu (or your username)
```

## Part 2: Download and Process

### Option A: Run in Screen Session (Recommended)

Screen sessions survive SSH disconnections:

```bash
# Create a screen session for downloading
screen -S download

# Inside screen:
cd ~/CommonCrawlNewsDataSet
source venv/bin/activate
./download_two_per_month.sh

# To detach from screen: Press Ctrl+A, then D
# Screen continues running in background

# To reattach later:
screen -r download

# To list all screen sessions:
screen -ls
```

### Option B: Run with nohup (Alternative)

```bash
cd ~/CommonCrawlNewsDataSet
source venv/bin/activate

# Run download in background
nohup ./download_two_per_month.sh > download.log 2>&1 &

# Monitor progress
tail -f download.log

# Check if still running
ps aux | grep download_two_per_month
```

### Full Workflow

```bash
# 1. Start download (in screen)
screen -S download
cd ~/CommonCrawlNewsDataSet
source venv/bin/activate
./download_two_per_month.sh
# Detach: Ctrl+A, then D

# 2. Monitor download progress (from another terminal)
watch -n 60 'echo "Files downloaded: $(find /data/CommonCrawl/news -name "*.warc.gz" | wc -l) / 82"; df -h / | grep -E "Filesystem|/"'

# 3. After download completes, start processing
screen -S process
cd ~/CommonCrawlNewsDataSet
source venv/bin/activate
./process_all_months.sh
# Detach: Ctrl+A, then D

# 4. Monitor processing
tail -f process.log  # if using nohup
# Or check specific month:
./check_progress.sh 2016/08
```

## Part 3: Monitor System Resources

### Create Comprehensive Monitoring Script

```bash
cat > ~/monitor.sh << 'EOF'
#!/bin/bash
clear
echo "╔════════════════════════════════════════════════════════════╗"
echo "║     CommonCrawl Processing Monitor - AWS (240GB Root)      ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "📊 System Resources:"
echo "────────────────────────────────────────────────────────────"
echo "CPU Usage:"
top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{printf "  %.1f%% used\n", 100-$1}'
echo ""
echo "Memory:"
free -h | awk '/Mem:/ {printf "  %s / %s used (%.1f%%)\n", $3, $2, ($3/$2)*100}'
echo ""
echo "Disk Space (/):"
df -h / | awk 'NR==2 {printf "  %s / %s used (%s)\n", $3, $2, $5}'
echo ""
echo "  /data usage:"
du -sh /data/CommonCrawl/news 2>/dev/null | awk '{printf "  %s\n", $1}' || echo "  0B"
echo ""

echo "📥 Download Progress:"
echo "────────────────────────────────────────────────────────────"
warc_count=$(find /data/CommonCrawl/news -name "*.warc.gz" 2>/dev/null | wc -l)
echo "  WARC files: $warc_count / 82"
percent=$((warc_count * 100 / 82))
echo "  Progress: $percent%"
echo ""

echo "🔄 Processing Progress:"
echo "────────────────────────────────────────────────────────────"
feather_count=$(find /data/CommonCrawl/news -name "*.feather" 2>/dev/null | wc -l)
echo "  Feather files: $feather_count"
echo ""

if [ -f /data/CommonCrawl/news/news_database.db ]; then
    article_count=$(sqlite3 /data/CommonCrawl/news/news_database.db "SELECT COUNT(*) FROM Articles;" 2>/dev/null || echo "0")
    echo "  Articles in DB: $article_count"
    
    if [ "$article_count" != "0" ]; then
        db_size=$(du -h /data/CommonCrawl/news/news_database.db | cut -f1)
        echo "  Database size: $db_size"
    fi
else
    echo "  Database: Not created yet"
fi
echo ""

echo "⚡ Active Processes:"
echo "────────────────────────────────────────────────────────────"
active_procs=$(ps aux | grep -E "download|process|python.*(extract|filter|ner)" | grep -v grep)
if [ -z "$active_procs" ]; then
    echo "  No active processing"
else
    echo "$active_procs" | head -5
fi
echo ""

echo "🖥️  Screen Sessions:"
echo "────────────────────────────────────────────────────────────"
screen -ls 2>/dev/null | grep -E "download|process" || echo "  No screen sessions"
echo ""
echo "Press Ctrl+C to exit"
EOF

chmod +x ~/monitor.sh

# Run the monitor
~/monitor.sh

# Or watch it update every 30 seconds
watch -n 30 ~/monitor.sh
```

### Quick Status Checks

```bash
# Quick disk usage check
df -h / | grep -E "Filesystem|/"
du -sh /data/CommonCrawl/news

# Quick download progress
echo "Downloaded: $(find /data/CommonCrawl/news -name '*.warc.gz' | wc -l) / 82 files"

# Quick processing check
echo "Feather files: $(find /data/CommonCrawl/news -name '*.feather' | wc -l)"
echo "Database: $([ -f /data/CommonCrawl/news/news_database.db ] && echo 'EXISTS' || echo 'Not created')"

# Check available space
df -h / | awk 'NR==2 {print "Available space:", $4}'

# Top space consumers
du -sh /data/CommonCrawl/news/*/ 2>/dev/null | sort -rh | head -10
```

## Part 4: Storage Management

### Space-Saving Strategy

```bash
# After processing completes, clean intermediate files
# This frees up ~40-50 GB

# Clean all intermediate processing files (keep WARC, NER, database)
find /data/CommonCrawl/news -type d -name "03_text" -exec rm -rf {} + 2>/dev/null
find /data/CommonCrawl/news -type d -name "04_quality" -exec rm -rf {} + 2>/dev/null
find /data/CommonCrawl/news -type d -name "05_filtered" -exec rm -rf {} + 2>/dev/null

# Check space saved
df -h /
```

### Storage Breakdown

```bash
# See what's taking up space
cat > ~/check_storage.sh << 'EOF'
#!/bin/bash
echo "📊 Storage Breakdown for /data/CommonCrawl/news"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

for dir in /data/CommonCrawl/news/*/; do
    month=$(basename "$dir")
    size=$(du -sh "$dir" 2>/dev/null | cut -f1)
    
    warc=$(find "$dir/warc" -name "*.warc.gz" 2>/dev/null | wc -l)
    feather=$(find "$dir" -name "*.feather" 2>/dev/null | wc -l)
    
    echo "$month: $size (WARC: $warc, Feather: $feather)"
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Database:"
if [ -f /data/CommonCrawl/news/news_database.db ]; then
    db_size=$(du -h /data/CommonCrawl/news/news_database.db | cut -f1)
    echo "  news_database.db: $db_size"
fi

if [ -f /data/CommonCrawl/news/geomap.xlsx ]; then
    geo_size=$(du -h /data/CommonCrawl/news/geomap.xlsx | cut -f1)
    echo "  geomap.xlsx: $geo_size"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
total=$(du -sh /data/CommonCrawl/news | cut -f1)
echo "Total: $total"
EOF

chmod +x ~/check_storage.sh
~/check_storage.sh
```

## Part 5: Query Your Data

### Connect to Database

```bash
# Activate venv
cd ~/CommonCrawlNewsDataSet
source venv/bin/activate

# Start Python
python3
```

```python
import sqlite3
import pandas as pd

# Connect to database
conn = sqlite3.connect('/data/CommonCrawl/news/news_database.db')

# Get total articles
total = conn.execute("SELECT COUNT(*) FROM Articles").fetchone()[0]
print(f"Total articles: {total:,}")

# Get articles by country
df_countries = pd.read_sql_query("""
    SELECT l.country, COUNT(DISTINCT a.article_id) as article_count
    FROM Articles a
    JOIN Article_Locations al ON a.article_id = al.article_id
    JOIN Locations l ON al.location_id = l.location_id
    GROUP BY l.country
    ORDER BY article_count DESC
    LIMIT 10
""", conn)
print("\nTop 10 countries:")
print(df_countries)

# Articles over time
df_timeline = pd.read_sql_query("""
    SELECT strftime('%Y-%m', date) as month, COUNT(*) as count
    FROM Articles
    GROUP BY month
    ORDER BY month
""", conn)
print("\nArticles per month:")
print(df_timeline.head(10))

conn.close()
```

## Troubleshooting

### Check Disk Space Issues

```bash
# If running low on space (< 20 GB free)
df -h / | awk 'NR==2 {if ($5+0 > 80) print "⚠️  Disk usage over 80%!"}'

# Find largest files/dirs
du -h /data/CommonCrawl/news | sort -rh | head -20

# Clean intermediate files
find /data/CommonCrawl/news -type d -name "03_text" -exec rm -rf {} + 2>/dev/null
find /data/CommonCrawl/news -type d -name "04_quality" -exec rm -rf {} + 2>/dev/null
```

### Screen Session Issues

```bash
# List all screen sessions
screen -ls

# Reattach to detached session
screen -r download

# If "Attached" elsewhere, force detach and reattach
screen -d -r download

# Kill a screen session
screen -S download -X quit
```

### Process Stuck or Failed

```bash
# Check what's running
ps aux | grep python

# Check specific month progress
./check_progress.sh 2016/08

# Resume from failed step
cd ~/CommonCrawlNewsDataSet
source venv/bin/activate
cd Project_Scripts

# Example: Resume from Step 06 for specific month
python 06_named_entity_recognition.py /data/CommonCrawl/news/2016-08/05_filtered /data/CommonCrawl/news/2016-08/06_ner en_geonames
```

## Cost Summary (AWS us-east-2)

```
Monthly Cost Breakdown:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EC2 t3.xlarge (24/7):      $120.19/month
EBS gp3 240 GB:             $19.20/month
Data transfer (50 GB):       $4.50/month
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total (running):           ~$143.89/month

Cost while stopped:         ~$19.20/month (EBS only)

One-time processing cost:
Setup + Download (8h):       $1.34
Processing (48h):            $8.05
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total one-time:              ~$9.39

💡 Tip: Stop instance after processing to pay only $19.20/month
```

## Timeline Summary

| Task | Duration | Space Used |
|------|----------|------------|
| Setup | 30 min | ~10 GB |
| Download (82 files) | 3-7 hours | +45 GB |
| Processing | 40-50 hours | +40 GB (intermediate) |
| Final state | - | ~70-80 GB total |
| **With cleanup** | - | **~50-60 GB total** |

## Final Result

After everything completes:
- ✅ 82 WARC files downloaded (2 per month × 41 months)
- ✅ ~820K - 2.4M articles extracted
- ✅ Geographic NER data for all articles
- ✅ SQLite database at `/data/CommonCrawl/news/news_database.db`
- ✅ Time series: August 2016 - December 2019
- ✅ Storage used: ~50-80 GB (240 GB available)
- ✅ ~160 GB free space remaining for future expansion

**Your 240 GB root volume is perfect for this project!** 🎉

Ready to start? Begin with Part 1!