import pandas as pd
from glob import glob
from collections import Counter, defaultdict
import re

print("🔍 Analyzing Hostname-Location Patterns...\n")

# Load sample NER files
ner_files = glob("/data/CommonCrawl/news/*/06_ner/*.feather")[:5]  # Sample 5 files

all_data = []
for file in ner_files:
    df = pd.read_feather(file)
    all_data.append(df)

combined = pd.concat(all_data, ignore_index=True)

# Extract TLDs
def extract_tld(hostname):
    if pd.isna(hostname):
        return 'unknown'
    parts = str(hostname).split('.')
    if len(parts) >= 2 and parts[-1] in ['uk', 'au', 'nz']:
        return '.'.join(parts[-2:])
    return parts[-1] if parts else 'unknown'

combined['tld'] = combined['hostname'].apply(extract_tld)

print("📊 TLD Distribution:")
tld_counts = combined['tld'].value_counts().head(15)
for tld, count in tld_counts.items():
    print(f"   .{tld}: {count:,}")

print("\n🌍 Sample Hostname → Location mappings:")
location_by_hostname = defaultdict(Counter)

for _, row in combined.iterrows():
    if pd.notna(row['hostname']) and isinstance(row['loc'], list) and len(row['loc']) > 0:
        hostname = row['hostname']
        tld = row['tld']
        for loc in row['loc']:
            loc_clean = re.sub(r"[^a-zA-Zäöüß'\- ]", "", str(loc).lower()).strip()
            if loc_clean:
                location_by_hostname[hostname][loc_clean] += 1

# Show examples
print("\nTop 10 hostnames with their locations:")
for hostname, loc_counter in list(location_by_hostname.items())[:10]:
    tld = extract_tld(hostname)
    top_locs = loc_counter.most_common(3)
    locs_str = ", ".join([f"{loc} ({cnt})" for loc, cnt in top_locs])
    print(f"   {hostname} (.{tld})")
    print(f"      → {locs_str}")

print("\n🔍 Location-TLD associations:")
location_tld_map = defaultdict(Counter)

for _, row in combined.iterrows():
    if pd.notna(row['hostname']) and isinstance(row['loc'], list):
        tld = row['tld']
        for loc in row['loc']:
            loc_clean = re.sub(r"[^a-zA-Zäöüß'\- ]", "", str(loc).lower()).strip()
            if loc_clean:
                location_tld_map[loc_clean][tld] += 1

# Show locations that appear on multiple TLDs (ambiguous cases)
print("\nLocations appearing on multiple TLDs (need smart geocoding):")
ambiguous = {loc: tlds for loc, tlds in location_tld_map.items() if len(tlds) > 2}
for loc, tld_counter in sorted(ambiguous.items(), key=lambda x: sum(x[1].values()), reverse=True)[:15]:
    total = sum(tld_counter.values())
    top_tlds = tld_counter.most_common(3)
    tlds_str = ", ".join([f".{tld} ({cnt})" for tld, cnt in top_tlds])
    print(f"   {loc} ({total} mentions): {tlds_str}")

print("\n✅ Locations strongly associated with one TLD:")
single_tld = {loc: tlds for loc, tlds in location_tld_map.items() if len(tlds) == 1}
for loc, tld_counter in list(single_tld.items())[:10]:
    tld, count = list(tld_counter.items())[0]
    print(f"   {loc} → .{tld} ({count} times)")
    