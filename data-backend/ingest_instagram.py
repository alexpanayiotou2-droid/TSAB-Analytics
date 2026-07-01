import os
import re
import ssl
import json
import logging
import urllib.request
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def load_env():
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

def clean_numeric(val, default=0.0):
    num = pd.to_numeric(val, errors='coerce')
    if pd.isna(num):
        return default
    return num

def parse_instagram_file(file_path):
    logger.info(f"Parsing Instagram file: {file_path}")
    try:
        if file_path.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file_path)
        else:
            df = pd.read_csv(file_path)
            
        campaigns = []
        for idx, row in df.iterrows():
            # Check for actual start column first, then reporting starts
            if 'Start' in df.columns:
                rep_starts = pd.to_datetime(row.get('Start'), errors='coerce')
            else:
                rep_starts = pd.to_datetime(row.get('Reporting starts'), errors='coerce')
                
            if 'Reporting ends' in df.columns:
                rep_ends = pd.to_datetime(row.get('Reporting ends'), errors='coerce')
            else:
                rep_ends = pd.to_datetime(row.get('Ends'), errors='coerce')
                
            ends = pd.to_datetime(row.get('Ends'), errors='coerce')
            
            c_name = row.get('Campaign name')
            if pd.isna(c_name) or not str(c_name).strip():
                continue
                
            campaigns.append({
                'reporting_starts': rep_starts.date().isoformat() if pd.notna(rep_starts) else None,
                'reporting_ends': rep_ends.date().isoformat() if pd.notna(rep_ends) else None,
                'campaign_name': str(c_name).strip(),
                'campaign_delivery': str(row.get('Campaign delivery', '')).strip(),
                'results': int(clean_numeric(row.get('Results'), 0)),
                'result_indicator': str(row.get('Result indicator', '')).strip(),
                'reach': int(clean_numeric(row.get('Reach'), 0)),
                'frequency': float(clean_numeric(row.get('Frequency'), 0.0)),
                'amount_spent_usd': float(clean_numeric(row.get('Amount spent (USD)'), 0.0)),
                'ends_date': ends.date().isoformat() if pd.notna(ends) else None,
                'impressions': int(clean_numeric(row.get('Impressions'), 0)),
                'link_clicks': int(clean_numeric(row.get('Link clicks'), 0)),
                'cpc_usd': float(clean_numeric(row.get('CPC (cost per link click) (USD)'), 0.0)),
                'ctr': float(clean_numeric(row.get('CTR (link click-through rate)'), 0.0)),
                'clicks_all': int(clean_numeric(row.get('Clicks (all)'), 0))
            })
            
        return pd.DataFrame(campaigns)
    except Exception as e:
        logger.error(f"Error parsing Instagram file: {e}")
        return pd.DataFrame()

def upload_to_supabase(url, key, campaigns_df):
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    ssl_context = ssl.create_default_context()
    
    # 1. Clear existing instagram_campaigns records
    logger.info("Clearing existing Instagram campaign records from Supabase...")
    endpoint_delete = f"{url.rstrip('/')}/rest/v1/instagram_campaigns?id=not.is.null"
    req = urllib.request.Request(endpoint_delete, headers=headers, method='DELETE')
    try:
        with urllib.request.urlopen(req, context=ssl_context) as resp:
            pass
    except Exception as e:
        logger.warning(f"Failed to clear Instagram campaigns: {e}")
        
    # 2. Upload campaigns
    if not campaigns_df.empty:
        camp_records = campaigns_df.to_dict(orient='records')
        for r in camp_records:
            for k, v in r.items():
                if isinstance(v, pd.Timestamp) or hasattr(v, 'isoformat'):
                    r[k] = v.isoformat()
                elif pd.isna(v):
                    r[k] = None
        endpoint = f"{url.rstrip('/')}/rest/v1/instagram_campaigns"
        payload = json.dumps(camp_records).encode('utf-8')
        req = urllib.request.Request(endpoint, data=payload, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, context=ssl_context) as resp:
                logger.info(f"Uploaded {len(camp_records)} Instagram campaigns to Supabase.")
        except Exception as e:
            logger.error(f"Failed to upload campaigns: {e}")
            raise e

def main():
    logger.info("=== TSAB Instagram Campaigns Ingestion Pipeline ===")
    load_env()
    
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    xlsx_file = "data-backend/Instagram/Insta Campaigns-Jun-1-2023-Jul-1-2026.xlsx"
    csv_file = "data-backend/Instagram/Insta Campaigns-Jun-1-2023-Jul-1-2026.csv"
    
    if os.path.exists(xlsx_file):
        target_file = xlsx_file
    elif os.path.exists(csv_file):
        target_file = csv_file
    else:
        logger.error("No Instagram campaign data file found.")
        return
        
    campaigns_df = parse_instagram_file(target_file)
    logger.info(f"Total Campaigns Parsed: {len(campaigns_df)}")
    
    # Update local cache for offline/fallback mode
    if not campaigns_df.empty:
        local_cache = "data-backend/Instagram/instagram_campaigns.csv"
        try:
            cache_df = campaigns_df.copy()
            if 'id' not in cache_df.columns:
                import uuid
                cache_df['id'] = [str(uuid.uuid4()) for _ in range(len(cache_df))]
            if 'created_at' not in cache_df.columns:
                import datetime
                cache_df['created_at'] = datetime.datetime.now().isoformat()
                
            cols = ['id', 'reporting_starts', 'reporting_ends', 'campaign_name', 'campaign_delivery', 
                    'results', 'result_indicator', 'reach', 'frequency', 'amount_spent_usd', 
                    'ends_date', 'impressions', 'link_clicks', 'cpc_usd', 'ctr', 'clicks_all', 'created_at']
            cols = [c for c in cols if c in cache_df.columns]
            cache_df[cols].to_csv(local_cache, index=False)
            logger.info(f"Updated local fallback cache: {local_cache}")
        except Exception as e:
            logger.error(f"Failed to update local cache: {e}")
            
    if not url or not key:
        logger.warning("Supabase credentials not found in environment. Dry-run complete.")
        return
        
    if not campaigns_df.empty:
        upload_to_supabase(url, key, campaigns_df)
        logger.info("Instagram Ingestion completed successfully!")

if __name__ == '__main__':
    main()
