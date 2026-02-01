import re
import pandas as pd
from tqdm import tqdm
from multiprocessing import Pool
from glob import glob
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import sys
import os

# ═══════════════════════════════════════════════════════════════════════════
# FILTER CONFIGURATION - Toggle filters on/off
# ═══════════════════════════════════════════════════════════════════════════
ENABLE_NON_FRANCE_FILTER = True      # Layer 1: Filter non-French country indicators
ENABLE_GEOCODE_CONFIDENCE = True     # Layer 2: Validate geocoded coordinates in France
ENABLE_STOPWORD_FILTER = True        # Layer 3: Filter common words (not places)

# ═══════════════════════════════════════════════════════════════════════════
# FILTER LAYER 1: Non-French Country Indicators
# ═══════════════════════════════════════════════════════════════════════════
NON_FRANCE_INDICATORS = {
    'syrie', 'syria', 'irak', 'iraq', 'iran', 'israël', 'israel',
    'palestine', 'liban', 'lebanon', 'jordanie', 'jordan',
    'arabie saoudite', 'saudi arabia', 'yémen', 'yemen',
    'allemagne', 'germany', 'italie', 'italy', 'espagne', 'spain',
    'royaume-uni', 'united kingdom', 'angleterre', 'england',
    'belgique', 'belgium', 'pays-bas', 'netherlands', 'hollande',
    'suisse', 'switzerland', 'portugal', 'grèce', 'greece',
    'turquie', 'turkey', 'russie', 'russia', 'pologne', 'poland',
    'ukraine', 'autriche', 'austria',
    'états-unis', 'etats-unis', 'united states', 'usa', 'amérique', 'america',
    'canada', 'mexique', 'mexico', 'brésil', 'brazil', 'argentine', 'argentina',
    'chine', 'china', 'japon', 'japan', 'inde', 'india',
    'corée', 'korea', 'thaïlande', 'thailand', 'vietnam',
    'égypte', 'egypt', 'maroc', 'morocco', 'algérie', 'algeria',
    'tunisie', 'tunisia', 'libye', 'libya', 'afrique du sud', 'south africa',
    'australie', 'australia',
}

def filter_non_france_endings(loc_normal):
    """
    Check if location ends with or is a non-French country.
    Returns True if should be KEPT, False if should be FILTERED OUT.
    """
    if not ENABLE_NON_FRANCE_FILTER:
        return True
    
    loc_clean = str(loc_normal).lower().strip()
    
    # Exact match - location IS a country name
    if loc_clean in NON_FRANCE_INDICATORS:
        return False
    
    # Check for ", country" or " country" at end
    for country in NON_FRANCE_INDICATORS:
        if loc_clean.endswith(f', {country}') or loc_clean.endswith(f' {country}'):
            return False
    
    return True

# ═══════════════════════════════════════════════════════════════════════════
# FILTER LAYER 2: Geocoding Confidence (France Bounding Box)
# ═══════════════════════════════════════════════════════════════════════════
FRANCE_BOUNDS = {
    'lat_min': 41.0, 'lat_max': 51.5,   # Corsica to northern border
    'lon_min': -5.5, 'lon_max': 10.0,   # Western to eastern France
}

def filter_geocode_confidence(location):
    """
    Check if geocoded location is within France bounds.
    Returns True if should be KEPT, False if should be FILTERED OUT.
    """
    if not ENABLE_GEOCODE_CONFIDENCE:
        return True
    
    if location is None:
        return False
    
    lat, lon = location.latitude, location.longitude
    
    # Check if within France bounding box
    in_france = (FRANCE_BOUNDS['lat_min'] <= lat <= FRANCE_BOUNDS['lat_max'] and
                 FRANCE_BOUNDS['lon_min'] <= lon <= FRANCE_BOUNDS['lon_max'])
    
    return in_france

# ═══════════════════════════════════════════════════════════════════════════
# FILTER LAYER 3: Stopwords (Exact Match Only)
# ═══════════════════════════════════════════════════════════════════════════
LOCATION_STOPWORDS = {
    'américains', 'américain', 'americains', 'americain',
    'français', 'francais', 'française', 'francaise',
    'européens', 'européen', 'europeens', 'europeen',
    'de france', 'la france', 'en france',
    'du', 'de', 'la', 'le', 'les', 'des', 'un', 'une',
    'etat', 'état', 'etats', 'états',
    'pays', 'ville', 'région', 'region',
    'nord', 'sud', 'est', 'ouest',
    'monde', 'international', 'national',
}

def filter_stopwords(loc_normal):
    """
    Check if location is a stopword (EXACT match only, not substring).
    Returns True if should be KEPT, False if should be FILTERED OUT.
    """
    if not ENABLE_STOPWORD_FILTER:
        return True
    
    loc_clean = str(loc_normal).lower().strip()
    
    # EXACT match only (won't filter "nord-pas-de-calais")
    return loc_clean not in LOCATION_STOPWORDS

# ═══════════════════════════════════════════════════════════════════════════
# ORIGINAL FUNCTIONS (unchanged)
# ═══════════════════════════════════════════════════════════════════════════

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
    
    # Match coordinates to NUTS regions using itertuples (faster than iterrows)
    print(f"📍 Matching coordinates to NUTS regions...")
    matched = 0
    
    for row in tqdm(geomap.itertuples(), total=len(geomap), desc="NUTS matching"):
        if pd.notna(row.latitude) and pd.notna(row.longitude):
            try:
                point = Point(row.longitude, row.latitude)
                matches = nuts_gdf[nuts_gdf.geometry.contains(point)]
                
                if len(matches) > 0:
                    # Get most detailed region (highest NUTS level)
                    best_match = matches.sort_values('LEVL_CODE', ascending=False).iloc[0]
                    geomap.at[row.Index, 'NUTS'] = best_match['NUTS_ID']
                    geomap.at[row.Index, 'GEN'] = best_match['NUTS_NAME']
                    matched += 1
            except Exception as e:
                continue
    
    print(f"   ✅ Matched {matched} / {geomap['latitude'].notna().sum()} locations to NUTS")
    
    return geomap

# ═══════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION (minimal changes marked with # NEW or # MODIFIED)
# ═══════════════════════════════════════════════════════════════════════════

def main():
    # NEW: Print active filters
    print("🔧 Active Filter Layers:")
    print(f"   Layer 1 - Non-France filter:  {'✅ ENABLED' if ENABLE_NON_FRANCE_FILTER else '❌ DISABLED'}")
    print(f"   Layer 2 - Geocode confidence: {'✅ ENABLED' if ENABLE_GEOCODE_CONFIDENCE else '❌ DISABLED'}")
    print(f"   Layer 3 - Stopword filter:    {'✅ ENABLED' if ENABLE_STOPWORD_FILTER else '❌ DISABLED'}")
    print()
    
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

    # Limit processes for I/O-bound file reading
    num_processes = min(8, len(files))
    print(f"📖 Reading {len(files)} files using {num_processes} processes...")

    # Create a pool of workers for parallel processing
    with Pool(processes=num_processes) as pool:
        # Use tqdm to display a progress bar
        dataframes = list(tqdm(pool.imap(read_feather, files), total=len(files)))

    # Concatenate all DataFrames into one large DataFrame
    combined_df = pd.concat(dataframes, ignore_index=True)

    # MODIFIED: Process and clean location data with filters
    print(f"🔄 Expanding location arrays (with filtering)...")
    rows = []
    stats = {'total': 0, 'filtered_non_france': 0, 'filtered_stopwords': 0, 'kept': 0}  # NEW: Track stats
    
    for row in tqdm(combined_df.itertuples(), total=len(combined_df), desc="Expanding locations"):
        locs = row.loc if hasattr(row.loc, '__len__') else []
        locs_norm = row.loc_normal if hasattr(row.loc_normal, '__len__') else []
        
        # Match each normalized location with its original
        for i, norm_loc in enumerate(locs_norm):
            stats['total'] += 1  # NEW
            
            if norm_loc and len(str(norm_loc)) > 1:
                # NEW: Apply Layer 3 - Stopword filter
                if not filter_stopwords(norm_loc):
                    stats['filtered_stopwords'] += 1
                    continue
                
                # NEW: Apply Layer 1 - Non-France filter
                if not filter_non_france_endings(norm_loc):
                    stats['filtered_non_france'] += 1
                    continue
                
                # MODIFIED: Only add if passed filters
                stats['kept'] += 1
                rows.append({
                    'loc': locs[i] if i < len(locs) else norm_loc,
                    'loc_normal': norm_loc
                })
    
    # NEW: Print filtering statistics
    print(f"\n📊 Pre-geocoding Filter Statistics:")
    print(f"   Total location mentions:     {stats['total']:,}")
    print(f"   Filtered (non-France):       {stats['filtered_non_france']:,}")
    print(f"   Filtered (stopwords):        {stats['filtered_stopwords']:,}")
    print(f"   Kept for geocoding:          {stats['kept']:,}")
    if stats['total'] > 0:
        print(f"   Filter rate:                 {(stats['total']-stats['kept'])/stats['total']*100:.1f}%")
    
    # Create new DataFrame from expanded rows
    combined_df = pd.DataFrame(rows)
    combined_df = combined_df.dropna(subset=["loc_normal"])
    
    # Filter out empty normalized locations
    combined_df = combined_df[combined_df["loc_normal"].str.len() > 1]
    print(f"✅ Expanded to {len(combined_df)} location mentions")

    # Group by normalized location and filter by occurrence count
    geomap = combined_df.groupby("loc_normal").size().reset_index(name="count")
    
    # Show distribution before filtering
    print(f"\n📊 Location count distribution:")
    print(f"   Total unique locations: {len(geomap)}")
    print(geomap.nlargest(20, 'count')[['loc_normal', 'count']].to_string(index=False))
    
    # Adaptive threshold based on dataset size
    total_articles = len(combined_df)
    if total_articles < 1000:
        threshold = 2  # Small dataset - geocode locations appearing 2+ times
        print(f"\n📉 Small dataset detected ({total_articles} location mentions)")
    elif total_articles < 10000:
        threshold = 10
        print(f"\n📊 Medium dataset detected ({total_articles} location mentions)")
    else:
        threshold = 100
        print(f"\n📈 Large dataset detected ({total_articles} location mentions)")
    
    print(f"   Using threshold: count > {threshold}")
    geomap = geomap[geomap["count"] > threshold]
    
    if len(geomap) == 0:
        print(f"\n❌ No locations remaining after filtering!")
        print(f"   All locations appear ≤{threshold} times")
        print(f"   Processing with threshold=1 instead...")
        geomap = combined_df.groupby("loc_normal").size().reset_index(name="count")
    
    print(f"   Locations to geocode: {len(geomap)}")

    # Initialize Geolocator
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

    # NEW: Track geocoding statistics
    geocode_stats = {'attempted': 0, 'success': 0, 'failed': 0, 'filtered_confidence': 0}

    # MODIFIED: Iterate over each place name and geocode with confidence filtering
    print(f"\n🔍 Geocoding {len(geomap)} locations...")
    for idx, row in tqdm(geomap.iterrows(), total=len(geomap), desc="Geocoding"):
        try:
            geocode_stats['attempted'] += 1  # NEW
            # FIXED: Don't append ", France" - let geocoder find actual location
            location = geocode(row["loc_normal"])

            # MODIFIED: Apply Layer 2 - Geocode confidence filter
            if filter_geocode_confidence(location):
                geomap.at[idx, "latitude"] = location.latitude
                geomap.at[idx, "longitude"] = location.longitude
                geocode_stats['success'] += 1  # NEW
            else:
                # Location is outside France bounds - filtered out
                geocode_stats['filtered_confidence'] += 1  # NEW
                geomap.at[idx, "latitude"] = None
                geomap.at[idx, "longitude"] = None
        except Exception as e:
            geocode_stats['failed'] += 1  # NEW
            geomap.at[idx, "latitude"] = None
            geomap.at[idx, "longitude"] = None

    # NEW: Print geocoding statistics
    print(f"\n📊 Geocoding Statistics:")
    print(f"   Attempted:                   {geocode_stats['attempted']:,}")
    print(f"   Successful:                  {geocode_stats['success']:,}")
    print(f"   Filtered (low confidence):   {geocode_stats['filtered_confidence']:,}")
    print(f"   Failed (errors):             {geocode_stats['failed']:,}")
    if geocode_stats['attempted'] > 0:
        print(f"   Success rate:                {geocode_stats['success']/geocode_stats['attempted']*100:.1f}%")

    # NEW: Save filtered locations for transparency before cleanup
    filtered_locs = geomap[geomap['latitude'].isna()].copy()
    if len(filtered_locs) > 0:
        filtered_locs['filter_reason'] = 'Outside France bounds or geocoding failed'
        filtered_locs = filtered_locs[['loc_normal', 'count', 'filter_reason']]
        filtered_locs = filtered_locs.sort_values('count', ascending=False)
        
        print(f"\n💾 Saving filtered locations log...")
        filtered_locs.to_csv('/data/CommonCrawl/news/filtered_locations.csv', index=False)
        print(f"   ✅ Saved {len(filtered_locs)} filtered locations to filtered_locations.csv")
        print(f"\n   Top filtered locations:")
        print(filtered_locs.head(10).to_string(index=False))

    # NEW: Remove locations without coordinates (cleanup)
    print(f"\n🧹 Cleaning geomap...")
    print(f"   Before cleanup: {len(geomap)} locations")
    geomap_clean = geomap[geomap['latitude'].notna()].copy()
    print(f"   After cleanup:  {len(geomap_clean)} locations")
    print(f"   Removed:        {len(geomap) - len(geomap_clean)} locations without valid coordinates")

    # Add NUTS codes to clean geomap only
    print()
    geomap_clean = add_nuts_codes(geomap_clean)

    # Save clean geomap (production-ready)
    print()
    geomap_clean.to_excel('/data/CommonCrawl/news/geomap.xlsx', index=False)
    geomap_clean.to_csv('/data/CommonCrawl/news/geomap.csv', index=False)
    print("✅ Saved clean geomap to:")
    print("   Excel: /data/CommonCrawl/news/geomap.xlsx")
    print("   CSV: /data/CommonCrawl/news/geomap.csv")
    
    # Show summary
    print()
    print("📊 Final Geomap Summary:")
    print(f"   Total locations:         {len(geomap_clean)}")
    print(f"   All have coordinates:    {geomap_clean['latitude'].notna().sum()} ✅")
    print(f"   With NUTS codes:         {geomap_clean['NUTS'].notna().sum()}")
    print()
    print(f"   Filtered locations saved separately in filtered_locations.csv")
    print(f"   (for transparency and debugging)")

if __name__ == "__main__":
    main()
