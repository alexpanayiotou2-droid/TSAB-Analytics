#!/usr/bin/env python3
"""
SubmitHub Data Ingestion Pipeline for TSAB Analytics Platform.
Author: Data Engineer
Target: data-backend/ingest_submithub.py
"""

import os
import sys
import re
import json
import logging
import ssl
import urllib.request
import pandas as pd
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
logger = logging.getLogger("ingest_submithub")

# Custom .env loader (matching existing ingest_historical_data.py)
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
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    os.environ[key] = val
    else:
        # Check parent folder as fallback
        parent_env = os.path.join("..", env_path)
        if os.path.exists(parent_env):
            load_env(parent_env)
        else:
            logger.warning(f"No .env file found at {env_path}")

# ==============================================================================
# PARSING MODULES
# ==============================================================================

def parse_credit_purchases(excel_path):
    """
    Parses the Credit Purchase History spreadsheet.
    """
    logger.info(f"Parsing credit purchases from: {excel_path}")
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel file not found: {excel_path}")
        
    df = pd.read_excel(excel_path)
    
    # Standardize headers
    df.columns = df.columns.str.strip().str.lower()
    
    required = ['date', 'paid', 'credits']
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required Excel column: '{col}'")
            
    purchases = []
    for idx, row in df.iterrows():
        raw_date = row['date']
        # Convert date to string format compatible with pg TIMESTAMP
        if isinstance(raw_date, pd.Timestamp):
            purchase_date = raw_date.isoformat()
        else:
            purchase_date = pd.to_datetime(raw_date).isoformat()
            
        purchases.append({
            'purchase_date': purchase_date,
            'amount_paid_usd': float(row['paid']),
            'credits_purchased': int(row['credits'])
        })
        
    logger.info(f"Successfully parsed {len(purchases)} credit purchase records.")
    return purchases

def parse_submithub_page_text(file_path):
    """
    Parses raw copy-pasted song response text files.
    """
    logger.info(f"Parsing raw page text from: {file_path}")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Page text file not found: {file_path}")
        
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f.readlines()]
        
    curators = []
    
    # Smarter regex to match: [Name] [Outlet Type] [Badges/Notes]
    header_pattern = re.compile(
        r'^(.+?)(Blog|Spotify Playlister|Radio|YouTube Channel|TikToker|Instagrammer|Record Label|Playlister|Influencer)(.*)$', 
        re.IGNORECASE
    )
    
    i = 0
    while i < len(lines):
        line = lines[i]
        if '|Add a note' in line:
            raw_header = line.split('|')[0].strip()
            
            # Match curator name and type
            match = header_pattern.match(raw_header)
            if match:
                curator_name = match.group(1).strip()
                curator_type = match.group(2).strip()
            else:
                curator_name = raw_header
                curator_type = 'Unknown'
            
            # Read next line for credits
            i += 1
            credit_line = lines[i] if i < len(lines) else ''
            credits = 0
            credit_type = 'Premium'
            
            credit_match = re.search(r'(\d+)\s+credit[s]?\s+\((Premium|Standard)\)', credit_line, re.IGNORECASE)
            if credit_match:
                credits = int(credit_match.group(1))
                credit_type = credit_match.group(2)
            
            current_curator = {
                'curator': curator_name,
                'type': curator_type,
                'credits_spent': credits,
                'credit_type': credit_type,
                'status': 'Pending',
                'feedback': '',
                'share_url': '',
                'share_destination': '',
                'is_refunded': False,
                'estimated_reach': None
            }
            
            # Scan details until next curator block
            i += 1
            detail_lines = []
            while i < len(lines) and '|Add a note' not in lines[i]:
                detail_lines.append(lines[i])
                i += 1
            
            details_str = " ".join(detail_lines)
            
            # Check for refund or final status
            if 'Refunded' in details_str or 'Expired' in details_str:
                current_curator['is_refunded'] = True
                current_curator['status'] = 'Refunded'
            elif 'Declined' in details_str:
                current_curator['status'] = 'Declined'
            elif 'Approved' in details_str:
                current_curator['status'] = 'Approved'
                
            # Extract feedback and clean up UI noise
            feedback_candidates = []
            for dl in detail_lines:
                dl_clean = dl.strip()
                if any(x in dl_clean for x in ['Listened', 'Declined', 'Approved', 'Refunded', 'Expired', 'Translate', 'Specific enough', 'Could be better', 'To be shared:', 'in a Spotify', 'Shared', 'Manage', 'Review your experience']):
                    continue
                if re.match(r'^\d+\s+(year|month|day|week|hour|minute)s?\s+ago', dl_clean, re.IGNORECASE):
                    continue
                if '(Your rating will be kept anonymous)' in dl_clean:
                    continue
                if not dl_clean:
                    continue
                # Skip playlist metrics from feedback
                if re.search(r'\(\d+,?\d*\s+followers\s*\|', dl_clean, re.IGNORECASE):
                    continue
                if len(dl_clean) > 5:
                    feedback_candidates.append(dl_clean)
            
            if feedback_candidates:
                current_curator['feedback'] = " ".join(feedback_candidates)
                
            # Extract share details & estimated reach if approved
            if current_curator['status'] == 'Approved':
                for dl in detail_lines:
                    if 'followers' in dl and '|' in dl:
                        current_curator['share_destination'] = dl.strip()
                        # Extract reach (followers)
                        reach_match = re.search(r'\((\d{1,3}(?:,\d{3})*)\s+followers', dl, re.IGNORECASE)
                        if reach_match:
                            current_curator['estimated_reach'] = int(reach_match.group(1).replace(',', ''))
            
            curators.append(current_curator)
            i -= 1
        i += 1
        
    logger.info(f"Successfully parsed {len(curators)} submissions from raw page text.")
    return curators

# ==============================================================================
# PIPELINE MERGER
# ==============================================================================

def get_cost_per_credit(campaign_date_str, purchases):
    """
    Finds the Cost Per Credit from the closest preceding purchase date.
    """
    if not purchases:
        return 1.00 # default fallback
        
    # Helper to strip timezone if present
    def to_naive_dt(dt_val):
        dt = pd.to_datetime(dt_val)
        return dt.tz_localize(None) if dt.tzinfo is not None else dt
        
    campaign_dt = to_naive_dt(campaign_date_str)
    
    # Sort purchases by date ascending
    sorted_purchases = sorted(purchases, key=lambda x: to_naive_dt(x['purchase_date']))
    
    best_cost = None
    for p in sorted_purchases:
        p_dt = to_naive_dt(p['purchase_date'])
        if p_dt <= campaign_dt:
            best_cost = p['amount_paid_usd'] / p['credits_purchased']
            
    if best_cost is None:
        # Fallback to the first purchase if campaign is older than all purchase history
        first = sorted_purchases[0]
        best_cost = first['amount_paid_usd'] / first['credits_purchased']
        
    return best_cost


def process_submissions(song_name, parsed_curators, master_csv_path, purchases):
    """
    Merges parsed curators from text with their metadata (dates, URLs) from the master CSV.
    """
    logger.info(f"Merging raw page text with master CSV: {master_csv_path}")
    if not os.path.exists(master_csv_path):
        raise FileNotFoundError(f"Master CSV file not found: {master_csv_path}")
        
    csv_df = pd.read_csv(master_csv_path)
    
    # Filter to the specific song
    song_df = csv_df[csv_df['Song'].str.contains(song_name, case=False, na=False)].copy()
    if song_df.empty:
        raise ValueError(f"No records found in master CSV for song: '{song_name}'")
        
    # Group by Outlet to aggregate history events (listen, declined, approved, etc.)
    grouped = song_df.groupby('Outlet')
    
    final_records = []
    
    for curator_entry in parsed_curators:
        curator_name = curator_entry['curator']
        
        # Match case-insensitive in the grouped outlets
        matched_group = None
        for name, group in grouped:
            if name.strip().lower() == curator_name.strip().lower():
                matched_group = group
                break
                
        if matched_group is None:
            logger.warning(f"Curator '{curator_name}' in page text was not found in the master CSV for '{song_name}'!")
            # Use defaults/empty strings if not matched
            campaign_url = None
            campaign_date = None
            outlet_url = None
            outlet_country = None
            action_timestamp = None
            listen_time = None
        else:
            # Grab metadata from first row
            first_row = matched_group.iloc[0]
            campaign_url = first_row.get('Campaign url')
            campaign_date = first_row.get('Campaign date')
            outlet_url = first_row.get('Outlet url')
            outlet_country = first_row.get('Outlet country')
            
            # Format dates
            if pd.notna(campaign_date):
                campaign_date = pd.to_datetime(campaign_date).isoformat()
            
            # Timestamps and listen times
            action_timestamp = pd.to_datetime(matched_group['Action timestamp'], format='mixed', utc=True).max()
            if pd.notna(action_timestamp):
                action_timestamp = action_timestamp.isoformat()
                
            listen_time = int(matched_group['Listen time (seconds)'].max()) if pd.notna(matched_group['Listen time (seconds)'].max()) else None

        # Compute spend
        cost_per_credit = get_cost_per_credit(campaign_date or datetime.now(), purchases)
        credits_spent = curator_entry['credits_spent']
        
        if curator_entry['is_refunded']:
            cost_usd = 0.00
        else:
            cost_usd = credits_spent * cost_per_credit
            
        record = {
            'song': song_name,
            'campaign_url': campaign_url,
            'campaign_date': campaign_date,
            'outlet': curator_name,
            'outlet_type': curator_entry['type'],
            'outlet_url': outlet_url,
            'outlet_country': outlet_country,
            'action': curator_entry['status'],
            'action_timestamp': action_timestamp,
            'feedback': curator_entry['feedback'],
            'listen_time_seconds': listen_time,
            'credits_spent': credits_spent,
            'credit_type': curator_entry['credit_type'],
            'is_refunded': curator_entry['is_refunded'],
            'cost_usd': round(cost_usd, 4),
            'share_destination': curator_entry['share_destination'],
            'estimated_reach': curator_entry['estimated_reach']
        }
        final_records.append(record)
        
    return final_records

# ==============================================================================
# DATABASE WRITER
# ==============================================================================

def clear_supabase_table(url, key, table):
    endpoint = f"{url.rstrip('/')}/rest/v1/{table}"
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
    }
    # To delete all rows, Postgrest requires a filter. id=not.is.null works for UUID ids
    req = urllib.request.Request(endpoint + "?id=not.is.null", headers=headers, method='DELETE')
    try:
        ssl_context = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ssl_context) as response:
            status = response.getcode()
            logger.info(f"Cleared existing records in '{table}' (status: {status}).")
    except Exception as e:
        logger.warning(f"Could not clear table '{table}': {e}")


def write_to_supabase(url, key, table, data, batch_size=1000):
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
    
    logger.info(f"Uploading {total_rows} records to table '{table}'...")
    ssl_context = ssl.create_default_context()
    
    for i in range(0, total_rows, batch_size):
        batch = data[i:i + batch_size]
        payload = json.dumps(batch).encode('utf-8')
        req = urllib.request.Request(endpoint, data=payload, headers=headers, method='POST')
        
        try:
            with urllib.request.urlopen(req, context=ssl_context) as response:
                status = response.getcode()
                if status not in (200, 201, 204):
                    raise Exception(f"Unexpected status code: {status}")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8')
            logger.error(f"Failed to insert batch starting at row {i} (status {e.code}): {err_body}")
            sys.exit(1)
            
    logger.info(f"Successfully seeded table '{table}'.")

# ==============================================================================
# MAIN PIPELINE
# ==============================================================================

def main():
    import glob
    
    parser = argparse.ArgumentParser(description="Ingest SubmitHub credits and submissions data into Supabase.")
    parser.add_argument('--dry-run', action='store_true', help="Parse and validate files locally without sending to Supabase.")
    args = parser.parse_args()
    
    logger.info("=== TSAB SubmitHub Ingestion Pipeline ===")
    if args.dry_run:
        logger.info("DRY-RUN MODE ENABLED.")
        
    # Load environment variables
    load_env()
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    
    if not args.dry_run:
        if not supabase_url or not supabase_key:
            logger.error("SUPABASE_URL and SUPABASE_KEY must be set in your environment or .env file.")
            sys.exit(1)
            
    # Paths
    submithub_dir = "data-backend/SubmitHub"
    excel_path = os.path.join(submithub_dir, "Credit Purchase History.xlsx")
    master_csv_path = os.path.join(submithub_dir, "The Socially Acceptable Band submission history (Jun 29, 2026).csv")
    
    # 1. Parse credit purchases
    try:
        purchases = parse_credit_purchases(excel_path)
    except Exception as e:
        logger.critical(f"Failed to parse credit purchases: {e}")
        sys.exit(1)
        
    # Find all response page text files
    search_pattern = os.path.join(submithub_dir, "*response page text.txt")
    text_files = glob.glob(search_pattern)
    # Check case variations
    text_files.extend(glob.glob(os.path.join(submithub_dir, "*Response page text.txt")))
    text_files = list(set(text_files))
    
    if not text_files:
        logger.error("No SubmitHub Response page text files found to process!")
        sys.exit(1)
        
    logger.info(f"Found {len(text_files)} tracks' response text files to parse.")
    
    all_submissions = []
    
    for text_file in text_files:
        basename = os.path.basename(text_file)
        # Extract song name from filename
        song_name_match = re.match(r'^(.+?)\s+response\s+page\s+text\.txt$', basename, re.IGNORECASE)
        if not song_name_match:
            continue
        song_name = song_name_match.group(1).strip()
        
        logger.info(f"Processing track: '{song_name}' (File: {basename})")
        
        # 2. Parse song raw page text
        try:
            parsed_curators = parse_submithub_page_text(text_file)
        except Exception as e:
            logger.error(f"Failed to parse page text for '{song_name}': {e}")
            continue
            
        # 3. Merge with master CSV metadata and credit cost
        try:
            submissions = process_submissions(song_name, parsed_curators, master_csv_path, purchases)
            all_submissions.extend(submissions)
        except Exception as e:
            logger.error(f"Failed to merge and process submissions for '{song_name}': {e}")
            continue
            
    # Validation summary
    total_records = len(all_submissions)
    total_credits = sum(s['credits_spent'] for s in all_submissions)
    refunded_credits = sum(s['credits_spent'] for s in all_submissions if s['is_refunded'])
    net_usd = sum(s['cost_usd'] for s in all_submissions)
    
    logger.info("--- Data Parsing Validation Summary (All Tracks) ---")
    logger.info(f"Total Submissions Processed: {total_records}")
    logger.info(f"Total Credits Spent: {total_credits}")
    logger.info(f"Refunded Credits: {refunded_credits}")
    logger.info(f"Net Campaign Cost Calculated: ${net_usd:.2f} USD")
    
    # 4. Upload to database
    if args.dry_run:
        logger.info("Dry run complete: All validations passed successfully!")
    else:
        logger.info("Executing database seeding...")
        # Clear existing tables first
        clear_supabase_table(supabase_url, supabase_key, "submithub_submissions")
        clear_supabase_table(supabase_url, supabase_key, "submithub_credit_purchases")
        
        # Seeding
        write_to_supabase(supabase_url, supabase_key, "submithub_credit_purchases", purchases)
        write_to_supabase(supabase_url, supabase_key, "submithub_submissions", all_submissions)
        logger.info("SubmitHub Ingestion Complete!")

if __name__ == '__main__':
    main()

