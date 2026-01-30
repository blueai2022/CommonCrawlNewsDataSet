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
BASE="/data/CommonCrawl/news/$MONTH_DIR"
DB="/data/CommonCrawl/news/news_database.db"

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
