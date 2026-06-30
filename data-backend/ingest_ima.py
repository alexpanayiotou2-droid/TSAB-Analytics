import os
import re
import ssl
import json
import logging
import urllib.request
import pypdf
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

def parse_invoice_pdf(file_path):
    logger.info(f"Parsing invoice PDF: {file_path}")
    try:
        reader = pypdf.PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        
        lines = [line.strip() for line in text.split('\n')]
        
        invoice_date = None
        amount = None
        song_name = None
        invoice_id = None
        guaranteed_streams = 0
        package_name = "Spotify Playlist Promotion"
        
        # September 20th 2024
        # Invoice 000013436
        # Total (USD) \n $297.00
        for i, line in enumerate(lines):
            # Parse Date
            if re.match(r'^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+(st|nd|rd|th)?\s+\d{4}', line, re.IGNORECASE):
                try:
                    clean_date = re.sub(r'(st|nd|rd|th)', '', line, flags=re.IGNORECASE)
                    invoice_date = pd.to_datetime(clean_date).date().isoformat()
                except Exception:
                    pass
            elif line.startswith('Invoice '):
                invoice_id = line.replace('Invoice ', '').strip()
            elif 'Total' in line and i + 1 < len(lines):
                next_line = lines[i+1].strip()
                match = re.search(r'\$?([\d,]+\.?\d*)', next_line)
                if match:
                    amount = float(match.group(1).replace(',', ''))
            elif 'Socially Acceptable - ' in line:
                song_name = line.replace('Socially Acceptable - ', '').strip()
            elif 'Guaranteed Real Streams' in line:
                match_streams = re.search(r'([\d,]+)\s+Guaranteed', line, re.IGNORECASE)
                if match_streams:
                    guaranteed_streams = int(match_streams.group(1).replace(',', ''))
                    
        # Clean song name if unparsed
        if not song_name:
            fn = os.path.basename(file_path).lower()
            if 'astronaut' in fn:
                song_name = 'Astronaut'
                
        return {
            'song': song_name,
            'campaign_date': invoice_date,
            'budget_usd': amount,
            'invoice_id': invoice_id,
            'package_name': package_name,
            'guaranteed_streams': guaranteed_streams
        }
    except Exception as e:
        logger.error(f"Error parsing invoice PDF: {e}")
        return None

def parse_results_txt(file_path):
    logger.info(f"Parsing results text: {file_path}")
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        lines = [line.strip() for line in content.split('\n')]
        
        # Find song name
        song_name = None
        for line in lines:
            if line.strip() in ['Astronaut', 'sh2ba', 'great riddance']:
                song_name = line.strip()
                break
        if not song_name:
            fn = os.path.basename(file_path).lower()
            if 'astronaut' in fn:
                song_name = 'Astronaut'
                
        placements = []
        for idx, line in enumerate(lines):
            if 'followers' in line.lower():
                try:
                    followers_match = re.search(r'([\d,]+)\s+followers', line, re.IGNORECASE)
                    followers = int(followers_match.group(1).replace(',', '')) if followers_match else 0
                    
                    curator = None
                    platform = 'Spotify'
                    playlist_name = None
                    
                    # Backtrack for curator details
                    for backtrack in range(1, 10):
                        if idx - backtrack >= 0:
                            bt_line = lines[idx - backtrack].strip()
                            if bt_line.startswith('by '):
                                curator = bt_line.replace('by ', '').strip()
                                if idx - backtrack - 1 >= 0:
                                    plat_cand = lines[idx - backtrack - 1].strip()
                                    if plat_cand:
                                        platform = plat_cand
                                        
                                for pl_backtrack in range(backtrack + 2, backtrack + 10):
                                    if idx - pl_backtrack >= 0:
                                        pl_line = lines[idx - pl_backtrack].strip()
                                        if pl_line and pl_line not in [
                                            'Dashboard', 'Campaigns', 'Artists', 'Contact support', 
                                            'Manage billing', 'Settings', 'Theme', 'Results Available', 
                                            'Campaign progress', 'Artist on Spotify', 'Track on Spotify', 
                                            'Campaign Delivery', 'Results & deliverables', 
                                            'Published placements, reports, and campaign results.'
                                        ]:
                                            playlist_name = pl_line
                                            break
                                break
                                
                    # Forwardtrack for published date
                    pub_date = None
                    for forwardtrack in range(1, 10):
                        if idx + forwardtrack < len(lines):
                            f_line = lines[idx + forwardtrack].strip()
                            if f_line.startswith('Published '):
                                date_str = f_line.replace('Published ', '').strip()
                                try:
                                    pub_date = pd.to_datetime(date_str).date().isoformat()
                                except Exception:
                                    pass
                                break
                                
                    if playlist_name:
                        placements.append({
                            'song': song_name,
                            'playlist_name': playlist_name,
                            'platform': platform,
                            'curator': curator,
                            'followers': followers,
                            'published_date': pub_date
                        })
                except Exception as e:
                    logger.error(f"Error parsing placement around line {idx}: {e}")
                    
        return placements
    except Exception as e:
        logger.error(f"Error parsing results text: {e}")
        return []

def upload_to_supabase(url, key, campaigns_df, placements_df):
    import urllib.parse
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    ssl_context = ssl.create_default_context()
    
    # 1. Clear existing campaign & placement records for the processed songs
    processed_songs = set(campaigns_df['song'].unique())
    if placements_df is not None and not placements_df.empty:
        processed_songs.update(placements_df['song'].unique())
        
    for song in processed_songs:
        quoted_song = urllib.parse.quote(song)
        logger.info(f"Clearing existing database records for song: '{song}'")
        
        # Delete placements
        endpoint_place = f"{url.rstrip('/')}/rest/v1/ima_placements?song=eq.{quoted_song}"
        req = urllib.request.Request(endpoint_place, headers=headers, method='DELETE')
        try:
            with urllib.request.urlopen(req, context=ssl_context) as resp:
                pass
        except Exception as e:
            logger.warning(f"Failed to clear placements for '{song}': {e}")
            
        # Delete campaigns
        endpoint_camp = f"{url.rstrip('/')}/rest/v1/ima_campaigns?song=eq.{quoted_song}"
        req = urllib.request.Request(endpoint_camp, headers=headers, method='DELETE')
        try:
            with urllib.request.urlopen(req, context=ssl_context) as resp:
                pass
        except Exception as e:
            logger.warning(f"Failed to clear campaigns for '{song}': {e}")
            
    # 2. Upload campaigns
    if not campaigns_df.empty:
        camp_records = campaigns_df.to_dict(orient='records')
        for r in camp_records:
            for k, v in r.items():
                if isinstance(v, pd.Timestamp) or hasattr(v, 'isoformat'):
                    r[k] = v.isoformat()
                elif pd.isna(v):
                    r[k] = None
        endpoint = f"{url.rstrip('/')}/rest/v1/ima_campaigns"
        payload = json.dumps(camp_records).encode('utf-8')
        req = urllib.request.Request(endpoint, data=payload, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, context=ssl_context) as resp:
                logger.info(f"Uploaded {len(camp_records)} campaigns to Supabase.")
        except Exception as e:
            logger.error(f"Failed to upload campaigns: {e}")
            raise e
            
    # 3. Upload placements
    if placements_df is not None and not placements_df.empty:
        place_records = placements_df.to_dict(orient='records')
        for r in place_records:
            for k, v in r.items():
                if isinstance(v, pd.Timestamp) or hasattr(v, 'isoformat'):
                    r[k] = v.isoformat()
                elif pd.isna(v):
                    r[k] = None
        endpoint = f"{url.rstrip('/')}/rest/v1/ima_placements"
        payload = json.dumps(place_records).encode('utf-8')
        req = urllib.request.Request(endpoint, data=payload, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, context=ssl_context) as resp:
                logger.info(f"Uploaded {len(place_records)} placements to Supabase.")
        except Exception as e:
            logger.error(f"Failed to upload placements: {e}")
            raise e

def main():
    logger.info("=== TSAB Indie Music Academy Ingestion Pipeline ===")
    load_env()
    
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    target_dir = "data-backend/Indie Music Academy"
    if not os.path.exists(target_dir):
        logger.error(f"Directory not found: {target_dir}")
        return
        
    campaigns = []
    placements = []
    
    for file in os.listdir(target_dir):
        file_path = os.path.join(target_dir, file)
        if file.endswith('.pdf'):
            res = parse_invoice_pdf(file_path)
            if res:
                campaigns.append(res)
        elif file.endswith('.txt'):
            res = parse_results_txt(file_path)
            if res:
                placements.extend(res)
                
    if not campaigns:
        logger.warning("No campaign details found in invoice PDFs.")
    if not placements:
        logger.warning("No placement details found in results text files.")
        
    campaigns_df = pd.DataFrame(campaigns)
    placements_df = pd.DataFrame(placements)
    
    logger.info(f"Total Campaigns Parsed: {len(campaigns_df)}")
    logger.info(f"Total Placements Parsed: {len(placements_df)}")
    
    if not url or not key:
        logger.warning("Supabase credentials not found in environment. Dry-run complete.")
        return
        
    if not campaigns_df.empty:
        upload_to_supabase(url, key, campaigns_df, placements_df)
        logger.info("Ingestion completed successfully!")

if __name__ == '__main__':
    main()
