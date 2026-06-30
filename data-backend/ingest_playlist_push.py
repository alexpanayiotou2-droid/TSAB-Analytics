#!/usr/bin/env python3
"""
TSAB Playlist Push Ingestion Pipeline.
Parses campaign summaries, invoice details, and placement listings from PDFs,
resolving precise dates and seeding Supabase.
"""
import os
import re
import sys
import json
import ssl
import urllib.request
import argparse
import logging
from datetime import datetime, timedelta
import pandas as pd
import pypdf

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ==============================================================================
# UTILS & HELPERS
# ==============================================================================

def load_env():
    """Loads environment variables from .env if present."""
    env_path = ".env"
    if os.path.exists(env_path):
        logger.info("Loading environment variables from .env")
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

def parse_time_ago(time_ago_str, print_date):
    """
    Translates relative time-ago strings like '4 months ago' or 'a year ago'
    into an absolute datetime based on the print date of the PDF.
    """
    clean_str = time_ago_str.strip().lower()
    
    if 'year' in clean_str:
        match = re.search(r'(\d+)', clean_str)
        years = int(match.group(1)) if match else 1
        return print_date - timedelta(days=years * 365)
    elif 'month' in clean_str:
        match = re.search(r'(\d+)', clean_str)
        months = int(match.group(1)) if match else 1
        return print_date - timedelta(days=months * 30.4)
    elif 'week' in clean_str:
        match = re.search(r'(\d+)', clean_str)
        weeks = int(match.group(1)) if match else 1
        return print_date - timedelta(weeks=weeks)
    elif 'day' in clean_str:
        match = re.search(r'(\d+)', clean_str)
        days = int(match.group(1)) if match else 1
        return print_date - timedelta(days=days)
        
    return print_date

# ==============================================================================
# PARSING MODULES
# ==============================================================================

def parse_invoice_pdf(invoice_path):
    """
    Extracts Issued Date and Amount Paid from a Playlist Push invoice PDF.
    """
    logger.info(f"Parsing invoice PDF: {invoice_path}")
    if not os.path.exists(invoice_path):
        return None
        
    reader = pypdf.PdfReader(invoice_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
        
    lines = [line.strip() for line in text.split('\n')]
    
    issued_date = None
    amount_paid = None
    
    for i, line in enumerate(lines):
        if 'Issued:' in line:
            if i + 1 < len(lines):
                date_candidate = lines[i+1].strip()
                try:
                    issued_date = pd.to_datetime(date_candidate).date()
                except Exception:
                    pass
        elif 'Amount paid' in line:
            match = re.search(r'\$?([\d,]+\.?\d*)', line)
            if match:
                amount_paid = float(match.group(1).replace(',', ''))
                
    return {
        'issued_date': issued_date,
        'amount_paid': amount_paid
    }

def parse_responses_pdf(pdf_path):
    """
    Parses approved playlist placements from a Campaign responses PDF.
    """
    logger.info(f"Parsing campaign responses PDF: {pdf_path}")
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"Responses PDF not found: {pdf_path}")
        
    reader = pypdf.PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
        
    lines = [line.strip() for line in text.split('\n')]
    
    # 1. Parse Print/Download Date from footer (e.g. 6/26/26, 2:18 PM)
    print_date = datetime.now() # fallback default
    for line in lines:
        match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}\s*[APM]*)', line, re.IGNORECASE)
        if match:
            try:
                date_str = match.group(1)
                # handle 2-digit years
                parts = date_str.split('/')
                if len(parts[2]) == 2:
                    parts[2] = '20' + parts[2]
                clean_date_str = '/'.join(parts)
                print_date = pd.to_datetime(clean_date_str)
                break
            except Exception:
                pass
                
    placements = []
    
    # Matching pattern:
    # 5:  cooking vibes 🍳
    # 6: 41,858 Saves · Curator KoranoRecords a year ago #37 Avg 2 months
    header_regex = re.compile(r'^(?:[^\w]*)\s*(.+)$')
    details_regex = re.compile(
        r'([\d,]+)\s+Saves\s+·\s+Curator\s+(.+?)\s+(\d+\s+(?:year|month|day|week)s?\s+ago|a\s+year\s+ago|a\s+month\s+ago|a\s+day\s+ago)\s+#(\d+)\s+Avg\s+(\d+)\s+month[s]?',
        re.IGNORECASE
    )
    
    i = 0
    while i < len(lines):
        line = lines[i]
        # Look for playlist marker or prefix (Playlist Push outputs a Spotify icon )
        if line.startswith('') or ('saves' in lines[i+1].lower() and 'curator' in lines[i+1].lower() if i+1 < len(lines) else False):
            playlist_name = line.replace('', '').strip()
            
            i += 1
            if i >= len(lines):
                break
                
            details_line = lines[i]
            match = details_regex.match(details_line)
            if match:
                saves = int(match.group(1).replace(',', ''))
                curator = match.group(2).strip()
                time_ago = match.group(3).strip()
                index = int(match.group(4))
                avg_duration = int(match.group(5))
                
                est_date = parse_time_ago(time_ago, print_date)
                
                placements.append({
                    'playlist_name': playlist_name,
                    'curator': curator,
                    'saves': saves,
                    'added_time_ago': time_ago,
                    'estimated_date': est_date.date().isoformat(),
                    'playlist_index': index,
                    'avg_duration_months': avg_duration
                })
        i += 1
        
    logger.info(f"Extracted {len(placements)} placements from response PDF.")
    return placements, print_date

# ==============================================================================
# PIPELINE MERGER
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Ingest Playlist Push data into Supabase.")
    parser.add_argument('--dry-run', action='store_true', help="Validate files locally without sending to Supabase.")
    args = parser.parse_args()
    
    logger.info("=== TSAB Playlist Push Ingestion Pipeline ===")
    if args.dry_run:
        logger.info("DRY-RUN MODE ENABLED.")
        
    load_env()
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    
    if not args.dry_run:
        if not supabase_url or not supabase_key:
            logger.error("SUPABASE_URL and SUPABASE_KEY must be set in environment.")
            sys.exit(1)
            
    # Paths
    pp_dir = "data-backend/Playlist Push"
    summary_csv_path = os.path.join(pp_dir, "Socially Acceptable - Playlist Push Campaign Results.csv")
    
    if not os.path.exists(summary_csv_path):
        logger.error(f"Missing summary CSV file: {summary_csv_path}")
        sys.exit(1)
        
    # Read summary CSV
    summary_df = pd.read_csv(summary_csv_path)
    summary_df.columns = summary_df.columns.str.strip().str.lower()
    
    campaigns = []
    all_placements = []
    
    # Map song filenames
    # Walk directory to find PDF response files
    for idx, row in summary_df.iterrows():
        song_name = row['song'].strip()
        budget_str = str(row['campaign budget']).replace('$', '').strip()
        budget = float(budget_str)
        responses_count = int(row['curator responses'])
        adds = int(row['playlist adds'])
        reach = int(str(row['playlist followers']).replace(',', '').strip())
        popularity = int(row['spotify popularity']) if 'spotify popularity' in row else None
        
        logger.info(f"Processing Song: '{song_name}' (Budget: ${budget})")
        
        # 1. Search for campaign responses PDF
        resp_pdf_name = f"[P] Campaign responses for_ {song_name} - Playlist Push.pdf"
        # Match case-insensitive just in case
        resp_pdf_path = None
        for f in os.listdir(pp_dir):
            if f.lower() == resp_pdf_name.lower():
                resp_pdf_path = os.path.join(pp_dir, f)
                break
                
        if not resp_pdf_path:
            logger.warning(f"Could not find campaign responses PDF for song '{song_name}'. Skipping placements.")
            continue
            
        placements, print_date = parse_responses_pdf(resp_pdf_path)
        
        # 2. Check for Invoice PDF to get exact date
        # Example format: [P] playlistpush-invoice-480065 - Astronaut.pdf
        inv_pdf_path = None
        for f in os.listdir(pp_dir):
            if 'invoice' in f.lower() and song_name.lower() in f.lower() and f.endswith('.pdf'):
                inv_pdf_path = os.path.join(pp_dir, f)
                break
                
        campaign_date = None
        if inv_pdf_path:
            inv_data = parse_invoice_pdf(inv_pdf_path)
            if inv_data:
                campaign_date = inv_data['issued_date'].isoformat()
                logger.info(f"Found invoice date for '{song_name}': {campaign_date}")
        
        # If no invoice, estimate campaign date based on the oldest placement
        if not campaign_date and placements:
            oldest_placement = min(placements, key=lambda x: x['estimated_date'])
            campaign_date = oldest_placement['estimated_date']
            logger.info(f"Estimated campaign date for '{song_name}' from oldest placement: {campaign_date}")
            
        campaigns.append({
            'song': song_name,
            'campaign_date': campaign_date,
            'budget_usd': budget,
            'total_responses': responses_count,
            'playlist_adds': adds,
            'total_reach': reach,
            'spotify_popularity': popularity
        })
        
        for p in placements:
            p['song'] = song_name
            all_placements.append(p)
            
    # Validation summary
    logger.info("--- Data Parsing Validation Summary ---")
    logger.info(f"Total Campaigns Parsed: {len(campaigns)}")
    logger.info(f"Total Placements Parsed: {len(all_placements)}")
    
    # 4. Seeding Supabase
    if args.dry_run:
        logger.info("Dry run complete: Validations passed successfully!")
    else:
        logger.info("Uploading records to Supabase...")
        
        # Clear existing tables first
        clear_table(supabase_url, supabase_key, "playlist_push_placements")
        clear_table(supabase_url, supabase_key, "playlist_push_campaigns")
        
        # Seed
        write_to_supabase(supabase_url, supabase_key, "playlist_push_campaigns", campaigns)
        write_to_supabase(supabase_url, supabase_key, "playlist_push_placements", all_placements)
        logger.info("Playlist Push Ingestion Complete!")

def clear_table(url, key, table):
    endpoint = f"{url.rstrip('/')}/rest/v1/{table}"
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
    }
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
    
    ssl_context = ssl.create_default_context()
    
    for i in range(0, total_rows, batch_size):
        batch = data[i:i + batch_size]
        payload = json.dumps(batch).encode('utf-8')
        req = urllib.request.Request(endpoint, data=payload, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, context=ssl_context) as response:
                status = response.getcode()
                if status not in (200, 201, 204):
                    raise Exception(f"Unexpected status: {status}")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8')
            logger.error(f"Failed to insert batch starting at row {i} (status {e.code}): {err_body}")
            sys.exit(1)
            
    logger.info(f"Successfully seeded table '{table}'.")

if __name__ == '__main__':
    main()
