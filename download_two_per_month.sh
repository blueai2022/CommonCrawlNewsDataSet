#!/bin/bash

# Download 2 random files from each month (Aug 2016 - Dec 2019)
# This gives a good sample across time without overwhelming storage

START_YEAR=2016
START_MONTH=8
END_YEAR=2016
END_MONTH=9

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
