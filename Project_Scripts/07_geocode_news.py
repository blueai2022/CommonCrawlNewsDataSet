import re
import pandas as pd
from tqdm import tqdm
from multiprocessing import Pool
from glob import glob
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import sys
import os

# Function to read and process feather files
def read_feather(file_path):
    """
    Reads a feather file and returns it as a DataFrame with additional preprocessing.
    """
    try:
        df = pd.read_feather(file_path)
        df["len"] = df["text"].str.split().str.len()
        return df
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return pd.DataFrame()  # Return an empty DataFrame in case of error

def add_nuts_codes(geomap):
    """
    Add NUTS codes to geomap based on coordinates.
    
    Args:
        geomap: DataFrame with 'latitude' and 'longitude' columns
        
    Returns:
        DataFrame with added NUTS and GEN columns
    """
    try:
        import geopandas as gpd
        from shapely.geometry import Point
    except ImportError:
        print("⚠️  geopandas not installed. Installing...")
        os.system("pip install -q geopandas")
        import geopandas as gpd
        from shapely.geometry import Point
    
    # Define NUTS file path
    nuts_file = "/home/ubuntu/CommonCrawlNewsDataSet/data/nuts/nuts_2021.geojson"
    
    # Download NUTS data if missing
    if not os.path.exists(nuts_file):
        print(f"📥 Downloading NUTS data...")
        os.makedirs(os.path.dirname(nuts_file), exist_ok=True)
        
        import urllib.request
        url = "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/NUTS_RG_01M_2021_4326.geojson"
        try:
            urllib.request.urlretrieve(url, nuts_file)
            print(f"   ✅ Downloaded NUTS data")
        except Exception as e:
            print(f"   ❌ Download failed: {e}")
            print(f"   Continuing without NUTS codes...")
            geomap['NUTS'] = None
            geomap['GEN'] = None
            return geomap
    
    # Load NUTS data
    try:
        print(f"🗺️  Loading NUTS regions...")
        nuts_gdf = gpd.read_file(nuts_file)
        print(f"   Loaded {len(nuts_gdf)} NUTS regions")
    except Exception as e:
        print(f"❌ Error loading NUTS data: {e}")
        geomap['NUTS'] = None
        geomap['GEN'] = None
        return geomap
    
    # Initialize NUTS columns
    geomap['NUTS'] = None
    geomap['GEN'] = None
    
    # Match coordinates to NUTS regions
    print(f"📍 Matching coordinates to NUTS regions...")
    matched = 0
    
    for idx, row in tqdm(geomap.iterrows(), total=len(geomap), desc="NUTS matching"):
        if pd.notna(row['latitude']) and pd.notna(row['longitude']):
            try:
                point = Point(row['longitude'], row['latitude'])
                matches = nuts_gdf[nuts_gdf.geometry.contains(point)]
                
                if len(matches) > 0:
                    # Get most detailed region (highest NUTS level)
                    best_match = matches.sort_values('LEVL_CODE', ascending=False).iloc[0]
                    geomap.at[idx, 'NUTS'] = best_match['NUTS_ID']
                    geomap.at[idx, 'GEN'] = best_match['NUTS_NAME']
                    matched += 1
            except Exception as e:
                continue
    
    print(f"   ✅ Matched {matched} / {geomap['latitude'].notna().sum()} locations to NUTS")
    
    return geomap

# Main function for processing feather files and creating geomap
def main():
    # If no arguments, search for all 06_ner folders automatically
    if len(sys.argv) < 2:
        base_path = "/data/CommonCrawl/news"
        ner_folders = glob(os.path.join(base_path, "*/06_ner"))
        if not ner_folders:
            print(f"❌ No 06_ner folders found in {base_path}")
            sys.exit(1)
        print(f"📂 Auto-detected {len(ner_folders)} NER folders")
    else:
        # Use provided arguments
        ner_folders = sys.argv[1:]
    
    # Collect all feather files
    files = []
    for folder in ner_folders:
        pattern = os.path.join(folder, "*.feather")
        found = glob(pattern)
        files.extend(found)
        print(f"   Found {len(found)} files in {folder}")

    # Number of processes to use (adjust according to your system's capabilities)
    num_processes = min(60, len(files))  # Ensure it does not exceed available CPUs

    # Create a pool of workers for parallel processing
    with Pool(processes=num_processes) as pool:
        # Use tqdm to display a progress bar
        dataframes = list(tqdm(pool.imap(read_feather, files), total=len(files)))

    # Concatenate all DataFrames into one large DataFrame
    combined_df = pd.concat(dataframes, ignore_index=True)

    # Process and clean location data
    combined_df = combined_df.explode("loc").dropna(subset=["loc"])
    combined_df["loc_normal"] = combined_df["loc"].apply(
        lambda x: re.sub(r"[^a-zA-Zäöüß'\- ]", "", str(x).lower()).strip()
    )
    combined_df = combined_df[combined_df["loc_normal"] != ""]

    # Group by normalized location and filter by occurrence count
    geomap = combined_df.groupby("loc_normal").size().reset_index(name="count")
    geomap = geomap[geomap["count"] > 100]

    #Initialize Geolocator
    geolocator = Nominatim(user_agent="ADD_USERNAME_HERE", timeout=10)

    # RateLimiter: 1 call/sec, with up to 3 retries on failure and exponential back-off
    geocode = RateLimiter(
    geolocator.geocode,
    min_delay_seconds=1,
    max_retries=3,
    error_wait_seconds=2.0,
    swallow_exceptions=False
    )

    # Prepare result columns
    geomap["latitude"] = None
    geomap["longitude"] = None

    # Iterate over each place name and geocode
    print(f"🔍 Geocoding {len(geomap)} locations...")
    for idx, row in tqdm(geomap.iterrows(), total=len(geomap), desc="Geocoding"):
        try:
            location = geocode(row["loc_normal"] + ", France")

            if location:
                geomap.at[idx, "latitude"] = location.latitude
                geomap.at[idx, "longitude"] = location.longitude
            else:
                geomap.at[idx, "latitude"] = None
                geomap.at[idx, "longitude"] = None
        except Exception as e:
            print(f"Geocoding failed for {row['loc_normal']}: {e}")
            geomap.at[idx, "latitude"] = None
            geomap.at[idx, "longitude"] = None

    # Add NUTS codes (NEW - single function call)
    print()
    geomap = add_nuts_codes(geomap)

    # Now you can save or continue with your spatial join…
    print()
    geomap.to_excel('/data/CommonCrawl/news/geomap.xlsx', index=False)
    geomap.to_csv('/data/CommonCrawl/news/geomap.csv', index=False)
    print("✅ Saved geomap to:")
    print("   Excel: /data/CommonCrawl/news/geomap.xlsx")
    print("   CSV: /data/CommonCrawl/news/geomap.csv")
    
    # Show summary
    print()
    print("📊 Geomap Summary:")
    print(f"   Total locations: {len(geomap)}")
    print(f"   With coordinates: {geomap['latitude'].notna().sum()}")
    print(f"   With NUTS codes: {geomap['NUTS'].notna().sum()}")

if __name__ == "__main__":
    main()
