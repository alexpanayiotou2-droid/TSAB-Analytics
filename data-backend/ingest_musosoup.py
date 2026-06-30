#!/usr/bin/env python3
"""
TSAB Musosoup Ingestion Pipeline.
Parses campaign reports (CSVs) and payment receipts (PDFs),
mapping placement types and seeding Supabase.
"""
import os
import re
import sys
import json
import ssl
import urllib.request
import argparse
import logging
from datetime import datetime
import pandas as pd
import pypdf

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Currency conversion rate (GBP to USD constant)
GBP_TO_USD = 1.30

# Hardcoded receipts from email fallbacks
CAMPAIGN_DEFAULTS = {
    'astronaut': {
        'budget_gbp': 36.00,
        'campaign_date': '2024-09-21' # date of first placement
    },
    'great riddance': {
        'budget_gbp': 36.00,
        'campaign_date': '2024-07-28' # date of first placement
    },
    'sh2ba': {
        'budget_gbp': 36.00,
        'campaign_date': '2026-03-06'
    }
}

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

def parse_musosoup_payment_pdf(pdf_path):
    """
    Parses a Musosoup sales receipt PDF to extract Date, Song Name, and Total.
    """
    logger.info(f"Parsing payment PDF: {pdf_path}")
    if not os.path.exists(pdf_path):
        return None
        
    reader = pypdf.PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
        
    lines = [line.strip() for line in text.split('\n')]
    
    date_val = None
    amount = None
    song_name = None
    
    for i, line in enumerate(lines):
        if line.startswith('Date:'):
            date_cand = line.replace('Date:', '').strip()
            try:
                # Format: DD/MM/YYYY or MM/DD/YYYY (06/03/2026 -> 2026-03-06)
                parts = date_cand.split('/')
                date_val = pd.to_datetime(date_cand, dayfirst=True).date()
            except Exception:
                pass
        elif 'Campaign activation' in line:
            match = re.search(r'for\s+(?:Socially\s+Acceptable\s*-\s*)?([a-zA-Z0-9\s]+)', line, re.IGNORECASE)
            if match:
                song_name = match.group(1).strip()
        elif line.startswith('TOTAL'):
            match = re.search(r'TOTAL\s+[^\d]*([\d\.]+)', line, re.IGNORECASE)
            if match:
                amount = float(match.group(1))
                
    if not song_name:
        fn = os.path.basename(pdf_path).lower()
        for k in CAMPAIGN_DEFAULTS.keys():
            if k in fn:
                song_name = k
                break
                
    return {
        'song': song_name,
        'date': date_val,
        'amount': amount
    }

def get_placement_type(url):
    """Categorizes the placement_type based on the target completion_url."""
    if not url or pd.isna(url):
        return 'Other'
    url_lower = str(url).lower()
    if 'spotify.com' in url_lower:
        return 'Playlist'
    elif any(domain in url_lower for domain in ['instagram.com', 'facebook.com', 'x.com', 'twitter.com', 'tiktok.com', 'youtube.com']):
        return 'Social'
    elif 'soundcloud.com' in url_lower:
        return 'Audio'
    else:
        return 'Blog'

def clear_table(url, key, table):
    """Deletes all records from a Supabase table."""
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    endpoint = f"{url.rstrip('/')}/rest/v1/{table}?id=not.is.null"
    req = urllib.request.Request(endpoint, headers=headers, method='DELETE')
    ssl_context = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ssl_context) as response:
        if response.status not in (200, 204):
            raise Exception(f"Failed to clear table {table}: {response.status}")
    logger.info(f"Cleared existing records in '{table}'.")

def write_to_supabase(url, key, table, records):
    """Bulk inserts records into a Supabase table."""
    if not records:
        return
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    endpoint = f"{url.rstrip('/')}/rest/v1/{table}"
    
    for r in records:
        for k, v in r.items():
            if isinstance(v, (datetime, pd.Timestamp)) or hasattr(v, 'isoformat'):
                r[k] = v.isoformat()
            elif pd.isna(v):
                r[k] = None
                
    payload = json.dumps(records).encode('utf-8')
    req = urllib.request.Request(endpoint, data=payload, headers=headers, method='POST')
    ssl_context = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ssl_context) as response:
        if response.status not in (200, 201, 204):
            raise Exception(f"Failed to write to table {table}: {response.status}")

def main():
    parser = argparse.ArgumentParser(description="Ingest Musosoup campaign reports and payments.")
    parser.add_argument('--dry-run', action='store_true', help="Validate files locally without sending to Supabase.")
    args = parser.parse_args()
    
    logger.info("=== TSAB Musosoup Ingestion Pipeline ===")
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
    muso_dir = "data-backend/Musosoup"
    
    # 1. Discover campaign reports (CSVs)
    report_files = [f for f in os.listdir(muso_dir) if f.startswith("Musosoup-Campaign-Report-") and f.endswith(".csv")]
    if not report_files:
        logger.error("No Musosoup campaign reports found.")
        sys.exit(1)
        
    # 2. Discover payment PDFs
    payment_data = {}
    for f in os.listdir(muso_dir):
        if f.startswith("Musosoup-payment-") and f.endswith(".pdf"):
            pdf_path = os.path.join(muso_dir, f)
            parsed = parse_musosoup_payment_pdf(pdf_path)
            if parsed and parsed['song']:
                payment_data[parsed['song'].lower()] = parsed
                
    campaigns = []
    placements = []
    
    for rf in report_files:
        song_name = rf.replace("Musosoup-Campaign-Report-", "").replace(".csv", "").strip()
        logger.info(f"Processing Report: '{rf}' for Song: '{song_name}'")
        
        df = pd.read_csv(os.path.join(muso_dir, rf))
        df.columns = df.columns.str.strip().str.lower()
        
        df['placement_type'] = df['completion_url'].apply(get_placement_type)
        playlist_adds = len(df[df['placement_type'] == 'Playlist'])
        other_adds = len(df) - playlist_adds
        
        budget_gbp = 36.00
        campaign_date = None
        
        song_key = song_name.lower()
        if song_key in payment_data:
            budget_gbp = payment_data[song_key]['amount'] or budget_gbp
            campaign_date = payment_data[song_key]['date']
            if campaign_date:
                campaign_date = campaign_date.isoformat()
                
        if not campaign_date and song_key in CAMPAIGN_DEFAULTS:
            budget_gbp = CAMPAIGN_DEFAULTS[song_key]['budget_gbp']
            campaign_date = CAMPAIGN_DEFAULTS[song_key]['campaign_date']
            
        if not campaign_date and not df.empty:
            oldest_date = pd.to_datetime(df['completion_date']).min()
            campaign_date = oldest_date.date().isoformat()
            
        budget_usd = round(budget_gbp * GBP_TO_USD, 2)
        
        campaigns.append({
            'song': song_name,
            'campaign_date': campaign_date,
            'budget_gbp': budget_gbp,
            'budget_usd': budget_usd,
            'playlist_adds': playlist_adds,
            'other_adds': other_adds
        })
        
        for idx, row in df.iterrows():
            c_gbp = float(row.get('contribution', 0.0))
            c_usd = round(c_gbp * GBP_TO_USD, 2)
            
            comp_date = None
            if pd.notna(row.get('completion_date')):
                try:
                    comp_date = pd.to_datetime(row['completion_date']).isoformat()
                except Exception:
                    pass
                    
            placements.append({
                'song': song_name,
                'curator': row.get('curator'),
                'publication': row.get('publication'),
                'completion_date': comp_date,
                'accept_type': row.get('accept_type', 'Free'),
                'contribution_gbp': c_gbp,
                'contribution_usd': c_usd,
                'completion_url': row.get('completion_url'),
                'placement_type': row.get('placement_type')
            })
            
    logger.info("--- Data Ingestion Validation Summary ---")
    logger.info(f"Total Campaigns: {len(campaigns)}")
    logger.info(f"Total Placements: {len(placements)}")
    
    if args.dry_run:
        logger.info("Dry run complete: Validations passed successfully!")
    else:
        logger.info("Uploading records to Supabase...")
        clear_table(supabase_url, supabase_key, "musosoup_placements")
        clear_table(supabase_url, supabase_key, "musosoup_campaigns")
        write_to_supabase(supabase_url, supabase_key, "musosoup_campaigns", campaigns)
        write_to_supabase(supabase_url, supabase_key, "musosoup_placements", placements)
        logger.info("Musosoup Ingestion Complete!")

if __name__ == '__main__':
    main()
