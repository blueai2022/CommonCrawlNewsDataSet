#!/bin/bash

# Download files from specified period with 100 file limit per month
# Modified from download_two_per_month.sh

START_YEAR=2016
START_MONTH=8
END_YEAR=2016
END_MONTH=9

# File limit per month
FILES_PER_MONTH=100

BASE_PATH="/data/CommonCrawl/news"
mkdir -p "$BASE_PATH"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📥 CommonCrawl News - Download with Limit"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📅 Period: $(printf "%04d/%02d" $START_YEAR $START_MONTH) to $(printf "%04d/%02d" $END_YEAR $END_MONTH)"
echo "📊 Mode: Maximum $FILES_PER_MONTH files per month"
echo "💾 Download location: $BASE_PATH"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Skip confirmation if running non-interactively (e.g., with nohup)
if [ -t 0 ]; then
    echo "⚠️  File limit: $FILES_PER_MONTH files per month"
    echo "   Estimated: ~700 MB per file"
    echo ""
    read -p "Continue? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cancelled."
        exit 0
    fi
    echo ""
else
    echo "ℹ️  Running non-interactively (nohup/background mode)"
    echo "   Auto-starting download..."
    echo ""
fi

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
        echo "📥 Will download maximum: $FILES_PER_MONTH files"
        echo ""
        
        # Download files with limit
        file_counter=0
        while IFS= read -r file_path; do
            file_counter=$((file_counter + 1))
            
            # Break if limit reached
            if [ "$file_counter" -gt "$FILES_PER_MONTH" ]; then
                break
            fi
            
            filename=$(basename "$file_path")
            
            # Check if already downloaded
            if [ -f "$BASE_PATH/$month_dir/warc/$filename" ]; then
                file_size=$(du -h "$BASE_PATH/$month_dir/warc/$filename" | cut -f1)
                echo "  ✅ [$file_counter/$FILES_PER_MONTH] Already exists: $filename ($file_size)"
                total_skipped=$((total_skipped + 1))
            else
                echo "  📥 [$file_counter/$FILES_PER_MONTH] Downloading: $filename"
                
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
        done <<< "$file_list"
        
        echo ""
        echo "✅ Completed $month_folder: $file_counter/$total_files files (limit: $FILES_PER_MONTH)"
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
echo "   File limit per month: $FILES_PER_MONTH"
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
echo "      python 02_extract_newscrawl.py /data/CommonCrawl/news/$month_dir/warc"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"