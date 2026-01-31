import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from tqdm import tqdm

print("📂 Loading geomap...")
df = pd.read_excel("/data/CommonCrawl/news/geomap.xlsx")

print(f"📊 Current columns: {list(df.columns)}")
print(f"   Total locations: {len(df)}")
print(f"   With coordinates: {df['latitude'].notna().sum()}")

# Load NUTS shapefile
nuts_file = "/home/ubuntu/CommonCrawlNewsDataSet/data/nuts/nuts_2021.geojson"
print(f"\n🗺️  Loading NUTS shapefile from {nuts_file}...")

try:
    nuts_gdf = gpd.read_file(nuts_file)
    print(f"✅ Loaded {len(nuts_gdf)} NUTS regions")
    print(f"   NUTS levels: {sorted(nuts_gdf['LEVL_CODE'].unique())}")
except FileNotFoundError:
    print(f"❌ NUTS file not found: {nuts_file}")
    print("   Download it first with:")
    print("   mkdir -p data/nuts")
    print("   wget https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/NUTS_RG_01M_2021_4326.geojson -O data/nuts/nuts_2021.geojson")
    exit(1)

# Add NUTS columns if they don't exist
for col in ['NUTS0', 'NUTS1', 'NUTS2', 'NUTS3', 'NUTS_NAME']:
    if col not in df.columns:
        df[col] = None

# Function to get NUTS codes for a coordinate
def get_nuts_info(lat, lon):
    """Get NUTS codes for given coordinates."""
    if pd.isna(lat) or pd.isna(lon):
        return {'NUTS0': None, 'NUTS1': None, 'NUTS2': None, 'NUTS3': None, 'NUTS_NAME': None}
    
    try:
        point = Point(lon, lat)
        
        # Find all NUTS regions containing this point
        matches = nuts_gdf[nuts_gdf.geometry.contains(point)]
        
        if len(matches) == 0:
            return {'NUTS0': None, 'NUTS1': None, 'NUTS2': None, 'NUTS3': None, 'NUTS_NAME': None}
        
        # Get the most detailed region (highest NUTS level)
        # Level 3 is most detailed, Level 0 is country
        best_match = matches.sort_values('LEVL_CODE', ascending=False).iloc[0]
        
        nuts_id = best_match['NUTS_ID']
        nuts_name = best_match['NUTS_NAME']
        
        # Extract different NUTS levels from the ID
        # Example: DE212 -> DE (country), DE2 (region), DE21 (district), DE212 (subdistrict)
        return {
            'NUTS0': nuts_id[:2] if len(nuts_id) >= 2 else None,
            'NUTS1': nuts_id[:3] if len(nuts_id) >= 3 else None,
            'NUTS2': nuts_id[:4] if len(nuts_id) >= 4 else None,
            'NUTS3': nuts_id[:5] if len(nuts_id) >= 5 else nuts_id,
            'NUTS_NAME': nuts_name
        }
    
    except Exception as e:
        print(f"⚠️  Error processing ({lat}, {lon}): {e}")
        return {'NUTS0': None, 'NUTS1': None, 'NUTS2': None, 'NUTS3': None, 'NUTS_NAME': None}

# Process each location
print(f"\n🔍 Matching coordinates to NUTS regions...")
successful = 0

for idx, row in tqdm(df.iterrows(), total=len(df), desc="Processing"):
    if pd.notna(row['latitude']) and pd.notna(row['longitude']):
        nuts_info = get_nuts_info(row['latitude'], row['longitude'])
        
        for key, value in nuts_info.items():
            df.at[idx, key] = value
        
        if nuts_info['NUTS3'] is not None:
            successful += 1

# Also add legacy 'NUTS' column for backward compatibility (use NUTS3 or NUTS2)
df['NUTS'] = df['NUTS3'].fillna(df['NUTS2'])

# Keep GEN column for compatibility (use NUTS_NAME)
df['GEN'] = df['NUTS_NAME']

# Summary
print()
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("📊 NUTS Matching Results:")
print(f"   Total locations: {len(df)}")
print(f"   With coordinates: {df['latitude'].notna().sum()}")
print(f"   Matched to NUTS: {successful} ({successful/df['latitude'].notna().sum()*100:.1f}%)")
print(f"   NUTS0 (Country): {df['NUTS0'].notna().sum()}")
print(f"   NUTS1 (Regions): {df['NUTS1'].notna().sum()}")
print(f"   NUTS2 (Districts): {df['NUTS2'].notna().sum()}")
print(f"   NUTS3 (Subdistricts): {df['NUTS3'].notna().sum()}")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

# Save updated files
print("\n💾 Saving updated files...")
df.to_excel("/data/CommonCrawl/news/geomap.xlsx", index=False)
df.to_csv("/data/CommonCrawl/news/geomap.csv", index=False)

print("✅ Updated files:")
print("   Excel: /data/CommonCrawl/news/geomap.xlsx")
print("   CSV: /data/CommonCrawl/news/geomap.csv")
print()

# Show sample
print("🔍 Sample data with NUTS codes:")
sample_cols = ['loc_normal', 'count', 'latitude', 'longitude', 'NUTS0', 'NUTS3', 'NUTS_NAME']
print(df[sample_cols].head(10).to_string())
print()

# Show NUTS distribution
print("📈 Top NUTS3 regions:")
nuts3_counts = df['NUTS3'].value_counts().head(10)
for nuts, count in nuts3_counts.items():
    name = df[df['NUTS3'] == nuts]['NUTS_NAME'].iloc[0] if pd.notna(nuts) else 'Unknown'
    print(f"   {nuts}: {count} locations ({name})")