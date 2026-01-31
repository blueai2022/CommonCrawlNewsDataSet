import pandas as pd
from glob import glob

# Find a sample NER file
ner_files = glob("/data/CommonCrawl/news/*/06_ner/*.feather")

if ner_files:
    df = pd.read_feather(ner_files[0])
    
    print("📊 Columns in NER output:")
    print(list(df.columns))
    print()
    
    print("🔍 Sample data:")
    sample = df[['hostname', 'loc']].head(10)
    for idx, row in sample.iterrows():
        print(f"\nHostname: {row['hostname']}")
        print(f"Locations: {row['loc']}")
    
    print("\n📈 Location extraction statistics:")
    print(f"   Total articles: {len(df)}")
    print(f"   Articles with locations: {df['loc'].apply(lambda x: len(x) > 0 if isinstance(x, list) else False).sum()}")
    print(f"   Avg locations per article: {df['loc'].apply(lambda x: len(x) if isinstance(x, list) else 0).mean():.2f}")
else:
    print("❌ No NER files found")