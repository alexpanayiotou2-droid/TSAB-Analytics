#!/usr/bin/env python3
"""
Production-grade historical data ingestion script for Supabase.
Author: Data Engineer
Target: data-backend/ingest_historical_data.py
"""

import os
import sys
import csv
import json
import logging
import ssl
import urllib.request
from datetime import datetime
import argparse

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ingest_historical_data")

# Custom .env loader to support zero-dependency environment variable parsing
def load_env(env_path=".env"):
    if os.path.exists(env_path):
        logger.info(f"Loading environment variables from {env_path}")
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    # Clean up quotes and whitespace
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    os.environ[key] = val
    else:
        logger.warning(f"No .env file found at {env_path}")

# ==============================================================================
# MODULE A: LOADER
# ==============================================================================

def load_csv_data(file_path):
    """
    Loads raw rows from a local CSV file.
    """
    logger.info(f"Loading data from local CSV: {file_path}")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV file not found: {file_path}")
    
    rows = []
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    logger.info(f"Successfully loaded {len(rows)} raw rows from {file_path}")
    return rows

"""
================================================================================
FUTURE CLOUD API INGESTION PLACEHOLDER (Module A Expansion)
================================================================================
To swap from local CSV ingestion to a Cloud API:

1. Import the necessary library (e.g. `requests` or client SDK).
2. Define access tokens and endpoint URLs in your .env file.
3. Replace the calls in main() with these functions:

def fetch_distrokid_api_data(start_date=None, end_date=None):
    # Retrieve report metadata, request generation, and pull down CSV stream directly
    api_url = "https://api.distrokid.com/v1/reports/royalties"
    headers = {"Authorization": f"Bearer {os.environ.get('DISTROKID_API_KEY')}"}
    params = {"start_date": start_date, "end_date": end_date}
    
    # response = requests.get(api_url, headers=headers, params=params)
    # response.raise_for_status()
    # return parse_api_csv_stream(response.text)
    pass

def fetch_spotify_campaign_api_data(start_date=None, end_date=None):
    # Fetch campaign reports from Spotify Ad Studio / Promoted API
    api_url = "https://api.spotify.com/v1/ads/campaigns"
    headers = {"Authorization": f"Bearer {os.environ.get('SPOTIFY_ADS_TOKEN')}"}
    
    # response = requests.get(api_url, headers=headers)
    # response.raise_for_status()
    # return response.json()['campaigns']
    pass
================================================================================
"""

# ==============================================================================
# MODULE B: TRANSFORMER
# ==============================================================================

def parse_date(date_str):
    """
    Standardizes date strings (e.g. '3/6/26 UTC', '2026-05-27') to ISO-8601 'YYYY-MM-DD'.
    """
    if not date_str or date_str.strip().upper() in ('NA', ''):
        return None
    
    # Clean up suffix/timezone
    date_str = date_str.replace(' UTC', '').strip()
    
    # Try ISO-8601 (YYYY-MM-DD)
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return date_str
    except ValueError:
        pass
        
    # Try M/D/YY or M/D/YYYY
    parts = date_str.split('/')
    if len(parts) == 3:
        month, day, year = parts
        if len(year) == 2:
            year = "20" + year
        try:
            return datetime(int(year), int(month), int(day)).date().isoformat()
        except ValueError:
            pass
            
    raise ValueError(f"Unrecognized date format: '{date_str}'")

def parse_numeric(val, default=0.0):
    """
    Sanitizes and converts currency or rate strings (e.g. '$300.00', '13.95%') to floats.
    """
    if not val or val.strip().upper() in ('NA', ''):
        return default
    
    cleaned = val.replace('$', '').replace(',', '').replace('%', '').strip()
    try:
        return float(cleaned)
    except ValueError:
        return default

def parse_int(val, default=0):
    """
    Sanitizes and converts integer strings (e.g. '8,065') to ints.
    """
    if not val or val.strip().upper() in ('NA', ''):
        return default
    
    cleaned = val.replace(',', '').strip()
    try:
        return int(cleaned)
    except ValueError:
        return default

def transform_distrokid_rows(raw_rows):
    """
    Transforms and validates DistroKid rows.
    """
    transformed = []
    skipped = 0
    for idx, row in enumerate(raw_rows, start=1):
        try:
            # Map headers to Postgres columns
            item = {
                'date_inserted': parse_date(row.get('Date Inserted')),
                'reporting_date': parse_date(row.get('Reporting Date')),
                'sale_month': row.get('Sale Month', '').strip(),
                'store': row.get('Store', '').strip(),
                'artist': row.get('Artist', '').strip(),
                'title': row.get('Title', '').strip(),
                'isrc': row.get('ISRC', '').strip(),
                'upc': row.get('UPC', '').strip(),
                'quantity': parse_int(row.get('Quantity'), 0),
                'team_percentage': parse_numeric(row.get('Team Percentage'), 100.0),
                'source_type': row.get('Source Type', '').strip(),
                'country_of_sale': row.get('Country of Sale', '').strip(),
                'songwriter_royalties_withheld_usd': parse_numeric(row.get('Songwriter Royalties Withheld (USD)'), 0.0),
                'earnings_usd': parse_numeric(row.get('Earnings (USD)'), 0.0),
                'recoup_usd': parse_numeric(row.get('Recoup (USD)'), 0.0)
            }
            
            # Validation checks
            required = ['reporting_date', 'sale_month', 'store', 'artist', 'title', 'isrc', 'upc', 'country_of_sale']
            for field in required:
                if not item.get(field):
                    raise ValueError(f"Missing required field '{field}'")
            
            transformed.append(item)
        except Exception as e:
            logger.error(f"[DistroKid Validation Error] Row {idx} failed: {e}. Raw Row: {row}")
            skipped += 1
            
    logger.info(f"DistroKid Transformation Complete: {len(transformed)} validated, {skipped} skipped.")
    if skipped > 0:
        logger.warning(f"Skipped {skipped} invalid DistroKid rows.")
    return transformed

def transform_spotify_rows(raw_rows):
    """
    Transforms and validates Spotify Campaign rows.
    """
    transformed = []
    skipped = 0
    for idx, row in enumerate(raw_rows, start=1):
        try:
            # Map headers to Postgres columns
            item = {
                'release_date': parse_date(row.get('Release Date')),
                'start_date': parse_date(row.get('Start Date')),
                'end_date': parse_date(row.get('End Date')),
                'release_name': row.get('Release Name', '').strip(),
                'campaign_name': row.get('Campaign Name', '').strip(),
                'artist_name': row.get('Artist Name', '').strip(),
                'format': row.get('Format', '').strip(),
                'release_type': row.get('Release Type', '').strip(),
                'country_targeting': row.get('Country Targeting', '').strip(),
                'currency': row.get('Currency', 'USD').strip(),
                'tax_rate': parse_numeric(row.get('Tax Rate'), 0.0),
                'budget': parse_numeric(row.get('Budget'), 0.0),
                'budget_incl_tax': parse_numeric(row.get('Budget (incl. tax)'), 0.0),
                'spend': parse_numeric(row.get('Spend'), 0.0),
                'spend_incl_tax': parse_numeric(row.get('Spend (incl. tax)'), 0.0),
                'segment_targeting': row.get('Segment Targeting', '').strip(),
                'reach': parse_int(row.get('Reach'), 0),
                'clicks': parse_int(row.get('Clicks'), 0),
                'amplified_listeners': parse_int(row.get('Amplified Listeners'), 0),
                'reactivated_listeners': parse_int(row.get('Reactivated Listeners'), 0),
                'new_active_listeners': parse_int(row.get('New Active Listeners'), 0),
                'light_listeners_after_converting': parse_int(row.get('Light Listeners (after converting)'), 0),
                'moderate_listeners_after_converting': parse_int(row.get('Moderate Listeners (after converting)'), 0),
                'super_listeners_after_converting': parse_int(row.get('Super Listeners (after converting)'), 0),
                'converted_listeners': parse_int(row.get('Converted Listeners'), 0),
                'conversion_rate': parse_numeric(row.get('Conversion Rate'), 0.0),
                'active_streams_per_listener': parse_numeric(row.get('Active Streams Per Listener'), 0.0),
                'intent_rate': parse_numeric(row.get('Intent Rate'), 0.0),
                'playlist_add_rate': parse_numeric(row.get('Playlist Add Rate'), 0.0),
                'playlist_adds': parse_int(row.get('Playlist Adds'), 0),
                'save_rate': parse_numeric(row.get('Save Rate'), 0.0),
                'saves': parse_int(row.get('Saves'), 0),
                'listeners_of_artists_other_releases': parse_int(row.get("Listeners of Artist's Other Releases"), 0),
                'active_streams_per_listener_for_artists_other_releases': parse_numeric(row.get("Active Streams Per Listener for Artist's Other Releases"), 0.0),
                'saves_of_artists_other_releases': parse_int(row.get("Saves of Artist's Other Releases"), 0),
                'playlist_adds_of_artists_other_releases': parse_int(row.get("Playlist Adds of Artist's Other Releases"), 0)
            }
            
            # Validation checks
            required = ['start_date', 'end_date', 'release_name', 'campaign_name', 'artist_name']
            for field in required:
                if not item.get(field):
                    raise ValueError(f"Missing required field '{field}'")
            
            transformed.append(item)
        except Exception as e:
            logger.error(f"[Spotify Validation Error] Row {idx} failed: {e}. Raw Row: {row}")
            skipped += 1
            
    logger.info(f"Spotify Transformation Complete: {len(transformed)} validated, {skipped} skipped.")
    if skipped > 0:
        logger.warning(f"Skipped {skipped} invalid Spotify rows.")
    return transformed

# ==============================================================================
# MODULE C: DATABASE WRITER
# ==============================================================================

def write_to_supabase(url, key, table, data, batch_size=1000):
    """
    Uploads data in chunks to Supabase using standard HTTP POST requests.
    """
    total_rows = len(data)
    if total_rows == 0:
        logger.info(f"No records to insert into {table}.")
        return
    
    endpoint = f"{url.rstrip('/')}/rest/v1/{table}"
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    
    logger.info(f"Starting seeding for table '{table}': {total_rows} records via REST API.")
    
    # Establish SSL context
    ssl_context = ssl.create_default_context()
    
    for i in range(0, total_rows, batch_size):
        batch = data[i:i + batch_size]
        logger.info(f"Sending batch {i//batch_size + 1} ({len(batch)} rows)...")
        
        payload = json.dumps(batch).encode('utf-8')
        req = urllib.request.Request(endpoint, data=payload, headers=headers, method='POST')
        
        try:
            with urllib.request.urlopen(req, context=ssl_context) as response:
                status = response.getcode()
                if status in (200, 201, 204):
                    logger.info(f"Successfully inserted batch {i//batch_size + 1} (rows {i} to {min(i+batch_size, total_rows)}).")
                else:
                    raise Exception(f"Unexpected status code: {status}")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8')
            logger.error(f"Failed to insert batch starting at row {i} (status {e.code}): {err_body}")
            logger.error(f"Failed Batch sample: {batch[0] if batch else None}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Error during network request for batch starting at row {i}: {e}")
            sys.exit(1)
            
    logger.info(f"Finished seeding table '{table}'.")

# ==============================================================================
# MAIN FUNCTION
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Ingest historical DistroKid and Spotify campaigns data into Supabase.")
    parser.add_argument('--dry-run', action='store_true', help="Parse and validate CSV files locally without sending to Supabase.")
    parser.add_argument('--batch-size', type=int, default=1000, help="Number of records to upload per API call (default: 1000).")
    args = parser.parse_args()
    
    logger.info("=== TSAB Historical Data Ingestion Pipeline ===")
    if args.dry_run:
        logger.info("DRY-RUN MODE ENABLED. No data will be written to Supabase.")
        
    # Load env vars
    load_env()
    
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    
    if not args.dry_run:
        if not supabase_url or not supabase_key:
            logger.error("SUPABASE_URL and SUPABASE_KEY must be set in your environment or .env file.")
            sys.exit(1)
            
    # File Paths
    distrokid_csv = "data-backend/DistroKid Results 6.12.26.csv"
    spotify_csv = "data-backend/Spotify Campaigns to date 6.12.26.csv"
    
    # 1. Processing DistroKid
    try:
        dk_raw = load_csv_data(distrokid_csv)
        dk_transformed = transform_distrokid_rows(dk_raw)
    except Exception as e:
        logger.critical(f"Failed to load/transform DistroKid data: {e}")
        sys.exit(1)
        
    # 2. Processing Spotify
    try:
        spot_raw = load_csv_data(spotify_csv)
        spot_transformed = transform_spotify_rows(spot_raw)
    except Exception as e:
        logger.critical(f"Failed to load/transform Spotify campaigns data: {e}")
        sys.exit(1)
        
    # 3. Write to Supabase (if not dry-run)
    if args.dry_run:
        logger.info("Dry run complete: Validation passed successfully on all inputs!")
        logger.info(f"DistroKid: {len(dk_transformed)} rows parsed.")
        logger.info(f"Spotify Campaigns: {len(spot_transformed)} rows parsed.")
    else:
        logger.info("Executing database uploads...")
        write_to_supabase(supabase_url, supabase_key, "distrokid_royalties", dk_transformed, batch_size=args.batch_size)
        write_to_supabase(supabase_url, supabase_key, "spotify_campaign_metrics", spot_transformed, batch_size=args.batch_size)
        logger.info("Database seeding complete!")

if __name__ == '__main__':
    main()
