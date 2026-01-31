import pandas as pd

# Read existing geomap
df = pd.read_excel("/data/CommonCrawl/news/geomap.xlsx")

print(f"📊 Current columns: {list(df.columns)}")

# Add missing columns if needed
if 'NUTS' not in df.columns:
    df['NUTS'] = None
    print("✅ Added 'NUTS' column (placeholder)")

if 'GEN' not in df.columns:
    df['GEN'] = None
    print("✅ Added 'GEN' column (placeholder)")

# Save back
df.to_excel("/data/CommonCrawl/news/geomap.xlsx", index=False)
df.to_csv("/data/CommonCrawl/news/geomap.csv", index=False)

print()
print(f"✅ Updated geomap with all required columns")
print(f"   Columns now: {list(df.columns)}")
print()
print("📊 Summary:")
print(f"   Total locations: {len(df)}")
print(f"   Geocoded: {df['latitude'].notna().sum()}")
print(f"   Ready for Step 08: ✅")