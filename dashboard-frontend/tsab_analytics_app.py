import streamlit as st
import pandas as pd
import altair as alt
import os
import json
import urllib.request
import ssl
import re
import pypdf
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 1. SETUP & CONFIG & BRAND PATHS ---
import os

frontend_dir = os.path.dirname(os.path.abspath(__file__))
logo_path = os.path.join(frontend_dir, "assets", "Bird solo.png")
wordmark_path = os.path.join(frontend_dir, "assets", "SA_Fill_Black.png")

# Set the tab icon to use the bird logo asset
st.set_page_config(
    page_title="TSAB Cloud-Ready ROI Dashboard", 
    page_icon=logo_path if os.path.exists(logo_path) else "🎸", 
    layout="wide"
)

# Header columns: Align the Bird Solo logo next to the Page Title text
col_header_logo, col_header_title = st.columns([1, 14])
with col_header_logo:
    if os.path.exists(logo_path):
        st.image(logo_path, use_container_width=True)
with col_header_title:
    st.title("TSAB Cloud-Ready ROI Dashboard")

st.markdown("Automated cross-platform correlations, retention decay, and algorithmic triggers.")

# --- ENVIRONMENT VARIABLES & SUPABASE LOADER ---
def load_env():
    # Try current dir first, then parent dir
    paths = [".env", "../.env"]
    for path in paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        os.environ[k.strip()] = v.strip().strip("'").strip('"')
            break

load_env()

def get_placement_type(url):
    if pd.isna(url) or not isinstance(url, str):
        return 'Other'
    u = url.lower()
    if 'spotify.com/playlist' in u:
        return 'Playlist'
    elif 'instagram.com' in u or 'facebook.com' in u or 'tiktok.com' in u or 'twitter.com' in u or 'x.com' in u:
        return 'Social'
    elif 'youtube.com' in u or 'youtu.be' in u:
        return 'Video'
    return 'Blog/Press'

GBP_TO_USD = 1.30

CAMPAIGN_DEFAULTS = {
    'astronaut': {
        'budget_gbp': 36.00,
        'campaign_date': '2024-09-21'
    },
    'great riddance': {
        'budget_gbp': 36.00,
        'campaign_date': '2024-07-28'
    },
    'sh2ba': {
        'budget_gbp': 36.00,
        'campaign_date': '2026-03-06'
    }
}

def parse_date(date_str):
    if pd.isna(date_str) or not date_str:
        return None
    date_str = str(date_str).strip()
    date_str = re.sub(r'\s+UTC$', '', date_str, flags=re.IGNORECASE)
    for fmt in ('%Y-%m-%d', '%m/%d/%y', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d'):
        try:
            return pd.to_datetime(date_str, format=fmt).date().isoformat()
        except Exception:
            pass
    try:
        return pd.to_datetime(date_str).date().isoformat()
    except Exception:
        return None

def parse_numeric(val, default=0.0):
    if pd.isna(val) or val is None:
        return default
    val_str = str(val).replace('$', '').replace(',', '').replace('%', '').strip()
    if val_str.lower() in ('na', 'null', 'nan', ''):
        return default
    try:
        return float(val_str)
    except Exception:
        return default

def parse_int(val, default=0):
    if pd.isna(val) or val is None:
        return default
    val_str = str(val).replace(',', '').strip()
    if val_str.lower() in ('na', 'null', 'nan', ''):
        return default
    try:
        return int(float(val_str))
    except Exception:
        return default

def prepare_db_records(df):
    if df is None or df.empty:
        return []
    records = df.to_dict(orient='records')
    for r in records:
        for k, v in r.items():
            if pd.isna(v):
                r[k] = None
            elif isinstance(v, pd.Timestamp) or hasattr(v, 'isoformat'):
                r[k] = v.isoformat()
            elif isinstance(v, (int, float)) or hasattr(v, 'dtype'):
                try:
                    fval = float(v)
                    if fval.is_integer():
                        r[k] = int(fval)
                    else:
                        r[k] = fval
                except Exception:
                    pass
    return records

def parse_raw_text_content(content, song_name):
    lines = [line.strip() for line in content.split('\n')]
    curators = []
    header_pattern = re.compile(
        r'^(.+?)(Blog|Spotify Playlister|Radio|YouTube Channel|TikToker|Instagrammer|Record Label|Playlister|Influencer)(.*)$', 
        re.IGNORECASE
    )
    
    i = 0
    while i < len(lines):
        line = lines[i]
        if '|Add a note' in line:
            raw_header = line.split('|')[0].strip()
            match = header_pattern.match(raw_header)
            if match:
                curator_name = match.group(1).strip()
                curator_type = match.group(2).strip()
            else:
                curator_name = raw_header
                curator_type = 'Unknown'
            
            i += 1
            credit_line = lines[i] if i < len(lines) else ''
            credits = 0
            credit_type = 'Premium'
            
            credit_match = re.search(r'(\d+)\s+credit[s]?\s+\((Premium|Standard)\)', credit_line, re.IGNORECASE)
            if credit_match:
                credits = int(credit_match.group(1))
                credit_type = credit_match.group(2)
            
            current_curator = {
                'song': song_name,
                'outlet': curator_name,
                'outlet_type': curator_type,
                'credits_spent': credits,
                'credit_type': credit_type,
                'status': 'Pending',
                'feedback': '',
                'is_refunded': False,
                'cost_usd': 0.0,
                'share_destination': '',
                'estimated_reach': None
            }
            
            i += 1
            detail_lines = []
            while i < len(lines) and '|Add a note' not in lines[i]:
                detail_lines.append(lines[i])
                i += 1
            
            details_str = " ".join(detail_lines)
            if 'Refunded' in details_str or 'Expired' in details_str:
                current_curator['is_refunded'] = True
                current_curator['status'] = 'Refunded'
            elif 'Declined' in details_str:
                current_curator['status'] = 'Declined'
            elif 'Approved' in details_str:
                current_curator['status'] = 'Approved'
                
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
                if re.search(r'\(\d+,?\d*\s+followers\s*\|', dl_clean, re.IGNORECASE):
                    continue
                if len(dl_clean) > 5:
                    feedback_candidates.append(dl_clean)
            
            if feedback_candidates:
                current_curator['feedback'] = " ".join(feedback_candidates)
                
            if current_curator['status'] == 'Approved':
                for dl in detail_lines:
                    if 'followers' in dl and '|' in dl:
                        current_curator['share_destination'] = dl.strip()
                        reach_match = re.search(r'\((\d{1,3}(?:,\d{3})*)\s+followers', dl, re.IGNORECASE)
                        if reach_match:
                            current_curator['estimated_reach'] = int(reach_match.group(1).replace(',', ''))
            
            if current_curator['is_refunded']:
                current_curator['cost_usd'] = 0.0
            else:
                current_curator['cost_usd'] = round(credits * 0.85, 2)
                
            curators.append(current_curator)
            i -= 1
        i += 1
    return curators

def transform_distrokid_df(df):
    records = []
    for idx, row in df.iterrows():
        try:
            item = {
                'date_inserted': parse_date(row.get('Date Inserted')),
                'reporting_date': parse_date(row.get('Reporting Date')),
                'sale_month': str(row.get('Sale Month', '')).strip(),
                'store': str(row.get('Store', '')).strip(),
                'artist': str(row.get('Artist', '')).strip(),
                'title': str(row.get('Title', '')).strip(),
                'isrc': str(row.get('ISRC', '')).strip(),
                'upc': str(row.get('UPC', '')).strip(),
                'quantity': parse_int(row.get('Quantity'), 0),
                'team_percentage': parse_numeric(row.get('Team Percentage'), 100.0),
                'source_type': str(row.get('Source Type', '')).strip(),
                'country_of_sale': str(row.get('Country of Sale', '')).strip(),
                'songwriter_royalties_withheld_usd': parse_numeric(row.get('Songwriter Royalties Withheld (USD)'), 0.0),
                'earnings_usd': parse_numeric(row.get('Earnings (USD)'), 0.0),
                'recoup_usd': parse_numeric(row.get('Recoup (USD)'), 0.0)
            }
            required = ['reporting_date', 'sale_month', 'store', 'artist', 'title', 'isrc', 'upc', 'country_of_sale']
            if all(item.get(f) for f in required):
                records.append(item)
        except Exception:
            pass
    return pd.DataFrame(records)

def transform_spotify_df(df):
    records = []
    for idx, row in df.iterrows():
        try:
            item = {
                'release_date': parse_date(row.get('Release Date')),
                'start_date': parse_date(row.get('Start Date')),
                'end_date': parse_date(row.get('End Date')),
                'release_name': str(row.get('Release Name', '')).strip(),
                'campaign_name': str(row.get('Campaign Name', '')).strip(),
                'artist_name': str(row.get('Artist Name', '')).strip(),
                'format': str(row.get('Format', '')).strip(),
                'release_type': str(row.get('Release Type', '')).strip(),
                'country_targeting': str(row.get('Country Targeting', '')).strip(),
                'currency': str(row.get('Currency', 'USD')).strip(),
                'tax_rate': parse_numeric(row.get('Tax Rate'), 0.0),
                'budget': parse_numeric(row.get('Budget'), 0.0),
                'budget_incl_tax': parse_numeric(row.get('Budget (incl. tax)'), 0.0),
                'spend': parse_numeric(row.get('Spend'), 0.0),
                'spend_incl_tax': parse_numeric(row.get('Spend (incl. tax)'), 0.0),
                'segment_targeting': str(row.get('Segment Targeting', '')).strip(),
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
            required = ['start_date', 'end_date', 'release_name', 'campaign_name', 'artist_name']
            if all(item.get(f) for f in required):
                records.append(item)
        except Exception:
            pass
    return pd.DataFrame(records)

def save_distrokid_to_db(url, key, df):
    import urllib.parse
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    ssl_context = ssl.create_default_context()
    if not df.empty:
        titles = df['title'].unique()
        for title in titles:
            quoted_title = urllib.parse.quote(title)
            endpoint = f"{url.rstrip('/')}/rest/v1/distrokid_royalties?title=eq.{quoted_title}"
            req = urllib.request.Request(endpoint, headers=headers, method='DELETE')
            try:
                with urllib.request.urlopen(req, context=ssl_context) as resp:
                    pass
            except Exception:
                pass
        records = df.to_dict(orient='records')
        for r in records:
            for k, v in r.items():
                if isinstance(v, pd.Timestamp) or hasattr(v, 'isoformat'):
                    r[k] = v.isoformat()
                elif pd.isna(v):
                    r[k] = None
        for i in range(0, len(records), 1000):
            batch = records[i:i+1000]
            endpoint = f"{url.rstrip('/')}/rest/v1/distrokid_royalties"
            payload = json.dumps(batch).encode('utf-8')
            req = urllib.request.Request(endpoint, data=payload, headers=headers, method='POST')
            try:
                with urllib.request.urlopen(req, context=ssl_context) as resp:
                    pass
            except Exception as e:
                raise e

def save_spotify_to_db(url, key, df):
    import urllib.parse
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    ssl_context = ssl.create_default_context()
    if not df.empty:
        names = df['release_name'].unique()
        for name in names:
            quoted_name = urllib.parse.quote(name)
            endpoint = f"{url.rstrip('/')}/rest/v1/spotify_campaign_metrics?release_name=eq.{quoted_name}"
            req = urllib.request.Request(endpoint, headers=headers, method='DELETE')
            try:
                with urllib.request.urlopen(req, context=ssl_context) as resp:
                    pass
            except Exception:
                pass
        records = df.to_dict(orient='records')
        for r in records:
            for k, v in r.items():
                if isinstance(v, pd.Timestamp) or hasattr(v, 'isoformat'):
                    r[k] = v.isoformat()
                elif pd.isna(v):
                    r[k] = None
        for i in range(0, len(records), 1000):
            batch = records[i:i+1000]
            endpoint = f"{url.rstrip('/')}/rest/v1/spotify_campaign_metrics"
            payload = json.dumps(batch).encode('utf-8')
            req = urllib.request.Request(endpoint, data=payload, headers=headers, method='POST')
            try:
                with urllib.request.urlopen(req, context=ssl_context) as resp:
                    pass
            except Exception as e:
                raise e

def save_s4a_to_db(url, key, df):
    import urllib.parse
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    ssl_context = ssl.create_default_context()
    if not df.empty:
        tracks = df['track_name'].unique()
        for track in tracks:
            quoted_track = urllib.parse.quote(track)
            endpoint = f"{url.rstrip('/')}/rest/v1/s4a_daily_streams?track_name=eq.{quoted_track}"
            req = urllib.request.Request(endpoint, headers=headers, method='DELETE')
            try:
                with urllib.request.urlopen(req, context=ssl_context) as resp:
                    pass
            except Exception:
                pass
        records = df.to_dict(orient='records')
        for r in records:
            for k, v in r.items():
                if isinstance(v, pd.Timestamp) or hasattr(v, 'isoformat'):
                    r[k] = v.isoformat()
                elif pd.isna(v):
                    r[k] = None
        for i in range(0, len(records), 1000):
            batch = records[i:i+1000]
            endpoint = f"{url.rstrip('/')}/rest/v1/s4a_daily_streams"
            payload = json.dumps(batch).encode('utf-8')
            req = urllib.request.Request(endpoint, data=payload, headers=headers, method='POST')
            try:
                with urllib.request.urlopen(req, context=ssl_context) as resp:
                    pass
            except Exception as e:
                raise e

# Inject custom CSS for premium Light Mode branding
st.markdown(
    """
    <style>
    /* Adjust typographic logo height and spacing in the sidebar */
    img[alt*="SA_Fill_Black"], img[src*="SA_Fill_Black"] {
        max-height: 50px;
        object-fit: contain;
        display: block;
        margin-left: auto;
        margin-right: auto;
        padding-bottom: 5px;
    }
    
    /* Style and align the header bird logo */
    img[alt*="Bird solo"], img[src*="Bird solo"] {
        max-height: 60px;
        object-fit: contain;
        display: block;
        margin-top: 15px; /* Vertical alignment correction with title text */
        transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    }
    img[alt*="Bird solo"]:hover {
        transform: rotate(5deg) scale(1.08);
    }
    
    /* Make metric cards look like premium light-mode modules */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border-radius: 12px;
        padding: 20px 24px;
        border: 1px solid #E5E7EB;
        border-top: 3.5px solid #FBAD30;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
        transition: all 0.25s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 20px rgba(251, 173, 48, 0.12);
        border-color: #FBAD30;
    }
    
    /* Adjust metadata tags within metric blocks */
    div[data-testid="stMetric"] label {
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: #6B7280 !important;
        font-size: 0.75rem !important;
    }
    
    /* Crisp divider styling in brand colors */
    hr {
        margin-top: 1.5rem !important;
        margin-bottom: 1.5rem !important;
        border-color: #E5E7EB !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Predefined Column Maps to rename database snake_case back to Title Case expected by frontend
DK_COLUMN_MAP = {
    'date_inserted': 'Date Inserted',
    'reporting_date': 'Reporting Date',
    'sale_month': 'Sale Month',
    'store': 'Store',
    'artist': 'Artist',
    'title': 'Title',
    'isrc': 'ISRC',
    'upc': 'UPC',
    'quantity': 'Quantity',
    'team_percentage': 'Team Percentage',
    'source_type': 'Source Type',
    'country_of_sale': 'Country of Sale',
    'songwriter_royalties_withheld_usd': 'Songwriter Royalties Withheld (USD)',
    'earnings_usd': 'Earnings (USD)',
    'recoup_usd': 'Recoup (USD)'
}

SPOTIFY_COLUMN_MAP = {
    'release_date': 'Release Date',
    'start_date': 'Start Date',
    'end_date': 'End Date',
    'release_name': 'Release Name',
    'campaign_name': 'Campaign Name',
    'artist_name': 'Artist Name',
    'format': 'Format',
    'release_type': 'Release Type',
    'country_targeting': 'Country Targeting',
    'currency': 'Currency',
    'tax_rate': 'Tax Rate',
    'budget': 'Budget',
    'budget_incl_tax': 'Budget (incl. tax)',
    'spend': 'Spend',
    'spend_incl_tax': 'Spend (incl. tax)',
    'segment_targeting': 'Segment Targeting',
    'reach': 'Reach',
    'clicks': 'Clicks',
    'amplified_listeners': 'Amplified Listeners',
    'reactivated_listeners': 'Reactivated Listeners',
    'new_active_listeners': 'New Active Listeners',
    'light_listeners_after_converting': 'Light Listeners (after converting)',
    'moderate_listeners_after_converting': 'Moderate Listeners (after converting)',
    'super_listeners_after_converting': 'Super Listeners (after converting)',
    'converted_listeners': 'Converted Listeners',
    'conversion_rate': 'Conversion Rate',
    'active_streams_per_listener': 'Active Streams Per Listener',
    'intent_rate': 'Intent Rate',
    'playlist_add_rate': 'Playlist Add Rate',
    'playlist_adds': 'Playlist Adds',
    'save_rate': 'Save Rate',
    'saves': 'Saves',
    'listeners_of_artists_other_releases': "Listeners of Artist's Other Releases",
    'active_streams_per_listener_for_artists_other_releases': "Active Streams Per Listener for Artist's Other Releases",
    'saves_of_artists_other_releases': "Saves of Artist's Other Releases",
    'playlist_adds_of_artists_other_releases': "Playlist Adds of Artist's Other Releases"
}

@st.cache_data(ttl=300)
def load_supabase_table(url, key, table_name):
    """
    Pagination-aware reader to load all records from a Supabase table.
    """
    all_data = []
    limit = 1000
    offset = 0
    ssl_context = ssl.create_default_context()
    
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}'
    }
    
    while True:
        endpoint = f"{url.rstrip('/')}/rest/v1/{table_name}?select=*&limit={limit}&offset={offset}"
        req = urllib.request.Request(endpoint, headers=headers)
        with urllib.request.urlopen(req, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
            if not data:
                break
            all_data.extend(data)
            if len(data) < limit:
                break
            offset += limit
            
    return pd.DataFrame(all_data)

def load_base_data(table_name, local_file_name, column_map):
    """
    Attempts to load data from Supabase. Falls back to a local CSV file if connection fails.
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    if url and key:
        try:
            df = load_supabase_table(url, key, table_name)
            if not df.empty:
                # Rename snake_case fields back to Title Case if mapping provided
                if column_map:
                    df = df.rename(columns=column_map)
                # Filter to only the columns we expect
                clean_cols = [col for col in df.columns if col in column_map.values() or not column_map]
                return df[clean_cols]
        except Exception as e:
            st.sidebar.warning(f"⚠️ Supabase load failed for '{table_name}'. Falling back to local data. Error: {e}")
            
    # Fallback to local CSV
    if table_name == "s4a_daily_streams":
        s4a_dirs = ["Spotify For Artists", "../Spotify For Artists", "data-backend/Spotify For Artists", "../data-backend/Spotify For Artists"]
        for s4a_dir in s4a_dirs:
            if os.path.exists(s4a_dir):
                dfs = []
                for f in os.listdir(s4a_dir):
                    if f.endswith('-timeline.csv') or f.endswith('_timeline.csv') or f.endswith(' timeline.csv'):
                        try:
                            temp_df = pd.read_csv(os.path.join(s4a_dir, f))
                            temp_df.columns = temp_df.columns.str.lower()
                            if 'date' in temp_df.columns and 'streams' in temp_df.columns:
                                raw_name = os.path.splitext(f)[0]
                                track_name = raw_name.replace('-timeline', '').replace('_timeline', '').replace(' timeline', '').strip()
                                temp_df['track_name'] = track_name
                                dfs.append(temp_df)
                        except Exception:
                            pass
                if dfs:
                    return pd.concat(dfs, ignore_index=True)

    if local_file_name:
        for path in (local_file_name, f"../{local_file_name}", f"data-backend/{local_file_name}", f"../data-backend/{local_file_name}"):
            if os.path.exists(path):
                return pd.read_csv(path, low_memory=False)
                
    return pd.DataFrame()

def save_submithub_to_db(url, key, df, purchases_df=None):
    import urllib.parse
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    ssl_context = ssl.create_default_context()
    
    # 1. Save submissions (incremental partitioned overwrite)
    if not df.empty:
        songs = df['song'].unique()
        for song in songs:
            # Delete existing
            quoted_song = urllib.parse.quote(song)
            endpoint = f"{url.rstrip('/')}/rest/v1/submithub_submissions?song=eq.{quoted_song}"
            req = urllib.request.Request(endpoint, headers=headers, method='DELETE')
            try:
                with urllib.request.urlopen(req, context=ssl_context) as resp:
                    pass
            except Exception as e:
                logger.error(f"Failed to delete existing SubmitHub rows for {song}: {e}")
                
        # Insert new
        records = prepare_db_records(df)
        
        endpoint = f"{url.rstrip('/')}/rest/v1/submithub_submissions"
        payload = json.dumps(records).encode('utf-8')
        req = urllib.request.Request(endpoint, data=payload, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, context=ssl_context) as resp:
                pass
        except Exception as e:
            msg = str(e)
            if hasattr(e, 'read'):
                try:
                    msg += " - " + e.read().decode('utf-8')
                except Exception:
                    pass
            logger.error(f"Failed to insert new SubmitHub rows: {msg}")
            raise Exception(f"Failed to insert new SubmitHub rows: {msg}")
            
    # 2. Save purchases (full deduplicated rewrite)
    if purchases_df is not None and not purchases_df.empty:
        existing_pur = []
        try:
            endpoint = f"{url.rstrip('/')}/rest/v1/submithub_credit_purchases?select=*"
            req = urllib.request.Request(endpoint, headers=headers)
            with urllib.request.urlopen(req, context=ssl_context) as resp:
                existing_pur = json.loads(resp.read().decode('utf-8'))
        except Exception:
            pass
            
        existing_df = pd.DataFrame(existing_pur)
        combined = pd.concat([existing_df, purchases_df], ignore_index=True)
        if 'purchase_date' in combined.columns:
            combined['purchase_date'] = pd.to_datetime(combined['purchase_date'], format='mixed', utc=True).dt.date.astype(str)
            combined = combined.drop_duplicates(subset=['purchase_date'])
            
            clear_endpoint = f"{url.rstrip('/')}/rest/v1/submithub_credit_purchases?id=not.is.null"
            req = urllib.request.Request(clear_endpoint, headers=headers, method='DELETE')
            try:
                with urllib.request.urlopen(req, context=ssl_context) as resp:
                    pass
            except Exception:
                pass
                
            records = prepare_db_records(combined)
            for r in records:
                r.pop('id', None)
            
            endpoint = f"{url.rstrip('/')}/rest/v1/submithub_credit_purchases"
            payload = json.dumps(records).encode('utf-8')
            req = urllib.request.Request(endpoint, data=payload, headers=headers, method='POST')
            try:
                with urllib.request.urlopen(req, context=ssl_context) as resp:
                    pass
            except Exception as e:
                logger.error(f"Failed to insert combined credit purchases: {e}")

def save_playlist_push_to_db(url, key, campaigns_df, placements_df):
    import urllib.parse
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    ssl_context = ssl.create_default_context()
    
    # 1. Save campaigns (incremental partitioned overwrite)
    if not campaigns_df.empty:
        songs = campaigns_df['song'].unique()
        for song in songs:
            quoted_song = urllib.parse.quote(song)
            endpoint_camp = f"{url.rstrip('/')}/rest/v1/playlist_push_campaigns?song=eq.{quoted_song}"
            req = urllib.request.Request(endpoint_camp, headers=headers, method='DELETE')
            try:
                with urllib.request.urlopen(req, context=ssl_context) as resp:
                    pass
            except Exception:
                pass
                
            endpoint_place = f"{url.rstrip('/')}/rest/v1/playlist_push_placements?song=eq.{quoted_song}"
            req = urllib.request.Request(endpoint_place, headers=headers, method='DELETE')
            try:
                with urllib.request.urlopen(req, context=ssl_context) as resp:
                    pass
            except Exception:
                pass
                
        camp_records = campaigns_df.to_dict(orient='records')
        for r in camp_records:
            for k, v in r.items():
                if isinstance(v, pd.Timestamp) or hasattr(v, 'isoformat'):
                    r[k] = v.isoformat()
                elif pd.isna(v):
                    r[k] = None
        endpoint = f"{url.rstrip('/')}/rest/v1/playlist_push_campaigns"
        payload = json.dumps(camp_records).encode('utf-8')
        req = urllib.request.Request(endpoint, data=payload, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, context=ssl_context) as resp:
                pass
        except Exception as e:
            logger.error(f"Failed to insert campaigns: {e}")
            raise e
            
        if not placements_df.empty:
            place_records = placements_df.to_dict(orient='records')
            for r in place_records:
                for k, v in r.items():
                    if isinstance(v, pd.Timestamp) or hasattr(v, 'isoformat'):
                        r[k] = v.isoformat()
                    elif pd.isna(v):
                        r[k] = None
            endpoint = f"{url.rstrip('/')}/rest/v1/playlist_push_placements"
            payload = json.dumps(place_records).encode('utf-8')
            req = urllib.request.Request(endpoint, data=payload, headers=headers, method='POST')
            try:
                with urllib.request.urlopen(req, context=ssl_context) as resp:
                    pass
            except Exception as e:
                logger.error(f"Failed to insert placements: {e}")
                return pd.DataFrame()

def save_ima_to_db(url, key, campaigns_df, placements_df):
    import urllib.parse
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    ssl_context = ssl.create_default_context()
    
    # 1. Clear existing campaign & placement records for the processed songs
    if not campaigns_df.empty:
        songs = campaigns_df['song'].unique()
        for song in songs:
            quoted_song = urllib.parse.quote(song)
            endpoint_place = f"{url.rstrip('/')}/rest/v1/ima_placements?song=eq.{quoted_song}"
            req = urllib.request.Request(endpoint_place, headers=headers, method='DELETE')
            try:
                with urllib.request.urlopen(req, context=ssl_context) as resp:
                    pass
            except Exception:
                pass
                
            endpoint_camp = f"{url.rstrip('/')}/rest/v1/ima_campaigns?song=eq.{quoted_song}"
            req = urllib.request.Request(endpoint_camp, headers=headers, method='DELETE')
            try:
                with urllib.request.urlopen(req, context=ssl_context) as resp:
                    pass
            except Exception:
                pass
                
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
                pass
        except Exception as e:
            logger.error(f"Failed to insert campaigns: {e}")
            raise e
            
        if not placements_df.empty:
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
                    pass
            except Exception as e:
                logger.error(f"Failed to insert placements: {e}")
                raise e

def save_instagram_to_db(url, key, campaigns_df):
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    ssl_context = ssl.create_default_context()
    
    # 1. Clear existing instagram_campaigns records
    endpoint_delete = f"{url.rstrip('/')}/rest/v1/instagram_campaigns?id=not.is.null"
    req = urllib.request.Request(endpoint_delete, headers=headers, method='DELETE')
    try:
        with urllib.request.urlopen(req, context=ssl_context) as resp:
            pass
    except Exception:
        pass
        
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
                pass
        except Exception as e:
            logger.error(f"Failed to insert Instagram campaigns: {e}")
            raise e

def save_musosoup_to_db(url, key, campaigns_df, placements_df):
    import urllib.parse
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    ssl_context = ssl.create_default_context()
    
    # 1. Save campaigns (partitioned overwrite)
    if not campaigns_df.empty:
        songs = campaigns_df['song'].unique()
        for song in songs:
            quoted_song = urllib.parse.quote(song)
            endpoint_camp = f"{url.rstrip('/')}/rest/v1/musosoup_campaigns?song=eq.{quoted_song}"
            req = urllib.request.Request(endpoint_camp, headers=headers, method='DELETE')
            try:
                with urllib.request.urlopen(req, context=ssl_context) as resp:
                    pass
            except Exception:
                pass
                
            endpoint_place = f"{url.rstrip('/')}/rest/v1/musosoup_placements?song=eq.{quoted_song}"
            req = urllib.request.Request(endpoint_place, headers=headers, method='DELETE')
            try:
                with urllib.request.urlopen(req, context=ssl_context) as resp:
                    pass
            except Exception:
                pass
                
        camp_records = campaigns_df.to_dict(orient='records')
        for r in camp_records:
            for k, v in r.items():
                if isinstance(v, pd.Timestamp) or hasattr(v, 'isoformat'):
                    r[k] = v.isoformat()
                elif pd.isna(v):
                    r[k] = None
        endpoint = f"{url.rstrip('/')}/rest/v1/musosoup_campaigns"
        payload = json.dumps(camp_records).encode('utf-8')
        req = urllib.request.Request(endpoint, data=payload, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, context=ssl_context) as resp:
                pass
        except Exception as e:
            logger.error(f"Failed to insert campaigns: {e}")
            raise e
            
        if not placements_df.empty:
            place_records = placements_df.to_dict(orient='records')
            for r in place_records:
                for k, v in r.items():
                    if isinstance(v, pd.Timestamp) or hasattr(v, 'isoformat'):
                        r[k] = v.isoformat()
                    elif pd.isna(v):
                        r[k] = None
            endpoint = f"{url.rstrip('/')}/rest/v1/musosoup_placements"
            payload = json.dumps(place_records).encode('utf-8')
            req = urllib.request.Request(endpoint, data=payload, headers=headers, method='POST')
            try:
                with urllib.request.urlopen(req, context=ssl_context) as resp:
                    pass
            except Exception as e:
                logger.error(f"Failed to insert placements: {e}")
                raise e

# --- 2. HYBRID DATA PIPELINE (APPEND LOGIC) ---
with st.sidebar:
    # Render typographic brand logo at top of sidebar
    if os.path.exists(wordmark_path):
        st.image(wordmark_path, use_container_width=True, output_format="PNG")
    st.markdown("---")
    
    st.header("Update Data")
    st.markdown("Base data loads from Supabase. Drop new files here to **append** to your history.")
    
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
    has_db = bool(SUPABASE_URL and SUPABASE_KEY)


    dk_uploads = st.file_uploader("1. Add DistroKid Data", type="csv", accept_multiple_files=True)
    st.caption("📂 *Expects: DistroKid royalty CSV reports (e.g., DistroKid Results 6.12.26.csv)*")
    if has_db:
        if st.button("💾 Save DistroKid Uploads to DB", key="save_dk_db_btn", disabled=not dk_uploads, use_container_width=True):
            with st.spinner("Processing and uploading DistroKid data..."):
                try:
                    dfs = []
                    for file in dk_uploads:
                        df = pd.read_csv(file)
                        dfs.append(transform_distrokid_df(df))
                    if dfs:
                        final_df = pd.concat(dfs, ignore_index=True)
                        save_distrokid_to_db(SUPABASE_URL, SUPABASE_KEY, final_df)
                        st.toast("✅ Successfully saved DistroKid data to Supabase!")
                        st.cache_data.clear()
                        st.rerun()
                except Exception as e:
                    st.error(f"Failed to save DistroKid data: {e}")
    dk_freshness = st.empty() 
    
    spot_uploads = st.file_uploader("2. Add Spotify Campaigns", type="csv", accept_multiple_files=True)
    st.caption("📂 *Expects: Spotify Ad Studio campaign report CSVs (e.g., Spotify Campaigns to date 6.12.26.csv)*")
    if has_db:
        if st.button("💾 Save Spotify Campaigns to DB", key="save_spot_db_btn", disabled=not spot_uploads, use_container_width=True):
            with st.spinner("Processing and uploading Spotify campaigns data..."):
                try:
                    dfs = []
                    for file in spot_uploads:
                        df = pd.read_csv(file)
                        dfs.append(transform_spotify_df(df))
                    if dfs:
                        final_df = pd.concat(dfs, ignore_index=True)
                        save_spotify_to_db(SUPABASE_URL, SUPABASE_KEY, final_df)
                        st.toast("✅ Successfully saved Spotify campaigns to Supabase!")
                        st.cache_data.clear()
                        st.rerun()
                except Exception as e:
                    st.error(f"Failed to save Spotify campaigns: {e}")
    spot_freshness = st.empty() 
    
    s4a_uploads = st.file_uploader("3. Add S4A Daily Tracks", type="csv", accept_multiple_files=True)
    st.caption("📂 *Expects: S4A daily stream timeline CSVs (e.g., Astronaut-timeline.csv)*")
    if has_db:
        if st.button("💾 Save S4A Daily Streams to DB", key="save_s4a_db_btn", disabled=not s4a_uploads, use_container_width=True):
            with st.spinner("Processing and uploading S4A daily stream data..."):
                try:
                    dfs = []
                    for file in s4a_uploads:
                        df = pd.read_csv(file)
                        df.columns = df.columns.str.lower()
                        if 'date' in df.columns and 'streams' in df.columns:
                            raw_name = os.path.splitext(file.name)[0]
                            track_name = raw_name.replace('-timeline', '').replace('_timeline', '').replace(' timeline', '').strip()
                            df['track_name'] = track_name
                            df['date'] = df['date'].apply(parse_date)
                            df['streams'] = df['streams'].apply(lambda x: parse_int(x, 0))
                            df = df.dropna(subset=['date', 'track_name'])
                            dfs.append(df[['date', 'streams', 'track_name']])
                    if dfs:
                        final_df = pd.concat(dfs, ignore_index=True)
                        save_s4a_to_db(SUPABASE_URL, SUPABASE_KEY, final_df)
                        st.toast("✅ Successfully saved S4A daily streams to Supabase!")
                        st.cache_data.clear()
                        st.rerun()
                except Exception as e:
                    st.error(f"Failed to save S4A daily streams: {e}")
    
    meta_uploads = st.file_uploader("4. Add Meta Ads", type="csv", accept_multiple_files=True)
    st.caption("📂 *Expects: Meta Ads CSV reports with columns 'Start Date' and 'Amount Spent (USD)'*")
    st.caption("*(Meta Ads are for temporary local visualization only)*")

    submithub_uploads = st.file_uploader("5. Add SubmitHub Data", type=["txt", "csv", "xlsx", "xls"], accept_multiple_files=True)
    st.caption("📂 *Expects: Response page text (.txt), submission history (.csv), purchase history (.xlsx), or pre-merged CSV*")

    # Ingest to DB Button for SubmitHub
    if has_db:
        if st.button("💾 Save SubmitHub Uploads to DB", key="save_sh_db_btn", disabled=not submithub_uploads, use_container_width=True):
            with st.spinner("Processing and uploading SubmitHub data..."):
                try:
                    xlsx_file = None
                    history_csv_file = None
                    text_files = []
                    pre_parsed_csvs = []
                    for file in submithub_uploads:
                        if file.name.endswith('.xlsx') or file.name.endswith('.xls') or 'purchase' in file.name.lower():
                            xlsx_file = file
                        elif file.name.endswith('.csv'):
                            try:
                                df_check = pd.read_csv(file, nrows=5)
                                file.seek(0)
                                if 'Song' in df_check.columns and 'Outlet' in df_check.columns and 'Campaign date' in df_check.columns:
                                    history_csv_file = file
                                else:
                                    pre_parsed_csvs.append(file)
                            except Exception:
                                try:
                                    file.seek(0)
                                except Exception:
                                    pass
                                pre_parsed_csvs.append(file)
                        elif file.name.endswith('.txt') or 'text' in file.name.lower():
                            text_files.append(file)

                    uploaded_purchases = []
                    if xlsx_file:
                        purchase_df = pd.read_excel(xlsx_file)
                        purchase_df.columns = purchase_df.columns.str.strip().str.lower()
                        if all(col in purchase_df.columns for col in ['date', 'paid', 'credits']):
                            for idx, row in purchase_df.iterrows():
                                raw_date = row['date']
                                p_date = pd.to_datetime(raw_date).isoformat() if not isinstance(raw_date, pd.Timestamp) else raw_date.isoformat()
                                uploaded_purchases.append({
                                    'purchase_date': p_date,
                                    'amount_paid_usd': float(row['paid']),
                                    'credits_purchased': int(row['credits'])
                                })

                    db_purchases = []
                    sh_purchases_df = globals().get('submithub_purchases_base_df')
                    if sh_purchases_df is None:
                        sh_purchases_df = load_base_data("submithub_credit_purchases", "SubmitHub/submithub_credit_purchases.csv", {})
                    if not sh_purchases_df.empty:
                        for idx, row in sh_purchases_df.iterrows():
                            db_purchases.append({
                                'purchase_date': pd.to_datetime(row['purchase_date']).isoformat(),
                                'amount_paid_usd': float(row['amount_paid_usd']),
                                'credits_purchased': int(row['credits_purchased'])
                            })
                    purchases = uploaded_purchases if uploaded_purchases else db_purchases

                    master_csv_df = pd.DataFrame()
                    if history_csv_file:
                        master_csv_df = pd.read_csv(history_csv_file)
                    else:
                        fallback_path = "data-backend/SubmitHub/The Socially Acceptable Band submission history (Jun 29, 2026).csv"
                        if os.path.exists(fallback_path):
                            master_csv_df = pd.read_csv(fallback_path)

                    def get_cost_per_credit_btn(campaign_date_str, purchase_list):
                        if not purchase_list:
                            return 0.85
                        def to_naive(dt_val):
                            dt = pd.to_datetime(dt_val)
                            return dt.tz_localize(None) if dt.tzinfo is not None else dt
                        try:
                            campaign_dt = to_naive(campaign_date_str)
                        except Exception:
                            campaign_dt = to_naive(pd.Timestamp.now())
                        sorted_p = sorted(purchase_list, key=lambda x: to_naive(x['purchase_date']))
                        best_cost = None
                        for p in sorted_p:
                            p_dt = to_naive(p['purchase_date'])
                            if p_dt <= campaign_dt:
                                best_cost = p['amount_paid_usd'] / p['credits_purchased']
                        if best_cost is None:
                            first = sorted_p[0]
                            best_cost = first['amount_paid_usd'] / first['credits_purchased']
                        return best_cost

                    def process_single_song_submissions_btn(song_name, parsed_curators, csv_df, purchase_list):
                        if csv_df.empty:
                            final_records = []
                            for curator in parsed_curators:
                                credits = curator['credits_spent']
                                cost_usd = 0.00 if curator['is_refunded'] else round(credits * 0.85, 2)
                                final_records.append({
                                    'song': song_name,
                                    'campaign_url': None,
                                    'campaign_date': None,
                                    'outlet': curator['outlet'],
                                    'outlet_type': curator['outlet_type'],
                                    'outlet_url': None,
                                    'outlet_country': None,
                                    'action': curator['status'],
                                    'action_timestamp': None,
                                    'feedback': curator['feedback'],
                                    'listen_time_seconds': None,
                                    'credits_spent': credits,
                                    'credit_type': curator['credit_type'],
                                    'is_refunded': curator['is_refunded'],
                                    'cost_usd': cost_usd,
                                    'share_destination': curator['share_destination'],
                                    'estimated_reach': curator['estimated_reach']
                                })
                            return final_records
                        song_df = csv_df[csv_df['Song'].str.contains(song_name, case=False, na=False)].copy()
                        if song_df.empty:
                            final_records = []
                            for curator in parsed_curators:
                                credits = curator['credits_spent']
                                cost_usd = 0.00 if curator['is_refunded'] else round(credits * 0.85, 2)
                                final_records.append({
                                    'song': song_name,
                                    'campaign_url': None,
                                    'campaign_date': None,
                                    'outlet': curator['outlet'],
                                    'outlet_type': curator['outlet_type'],
                                    'outlet_url': None,
                                    'outlet_country': None,
                                    'action': curator['status'],
                                    'action_timestamp': None,
                                    'feedback': curator['feedback'],
                                    'listen_time_seconds': None,
                                    'credits_spent': credits,
                                    'credit_type': curator['credit_type'],
                                    'is_refunded': curator['is_refunded'],
                                    'cost_usd': cost_usd,
                                    'share_destination': curator['share_destination'],
                                    'estimated_reach': curator['estimated_reach']
                                })
                            return final_records
                        grouped = song_df.groupby('Outlet')
                        final_records = []
                        for curator in parsed_curators:
                            curator_name = curator['outlet']
                            matched_group = None
                            for name, group in grouped:
                                if name.strip().lower() == curator_name.strip().lower():
                                    matched_group = group
                                    break
                            if matched_group is None:
                                campaign_url = None
                                campaign_date = None
                                outlet_url = None
                                outlet_country = None
                                action_timestamp = None
                                listen_time = None
                            else:
                                first_row = matched_group.iloc[0]
                                campaign_url = first_row.get('Campaign url')
                                campaign_date = first_row.get('Campaign date')
                                outlet_url = first_row.get('Outlet url')
                                outlet_country = first_row.get('Outlet country')
                                if pd.notna(campaign_date):
                                    campaign_date = pd.to_datetime(campaign_date).isoformat()
                                action_timestamp = pd.to_datetime(matched_group['Action timestamp'], format='mixed', utc=True).max()
                                if pd.notna(action_timestamp):
                                    action_timestamp = action_timestamp.isoformat()
                                listen_time = int(matched_group['Listen time (seconds)'].max()) if pd.notna(matched_group['Listen time (seconds)'].max()) else None
                            cost_per_credit = get_cost_per_credit_btn(campaign_date or pd.Timestamp.now(), purchases)
                            credits_spent = curator['credits_spent']
                            if curator['is_refunded']:
                                cost_usd = 0.00
                            else:
                                cost_usd = round(credits_spent * cost_per_credit, 4)
                            record = {
                                'song': song_name,
                                'campaign_url': campaign_url,
                                'campaign_date': campaign_date,
                                'outlet': curator_name,
                                'outlet_type': curator['outlet_type'],
                                'outlet_url': outlet_url,
                                'outlet_country': outlet_country,
                                'action': curator['status'],
                                'action_timestamp': action_timestamp,
                                'feedback': curator['feedback'],
                                'listen_time_seconds': listen_time,
                                'credits_spent': credits_spent,
                                'credit_type': curator['credit_type'],
                                'is_refunded': curator['is_refunded'],
                                'cost_usd': cost_usd,
                                'share_destination': curator['share_destination'],
                                'estimated_reach': curator['estimated_reach']
                            }
                            final_records.append(record)
                        return final_records

                    submithub_dataframes = []
                    for file in text_files:
                        content = file.getvalue().decode('utf-8', errors='ignore')
                        clean_name = re.sub(r'\s*response\s*page\s*text.*', '', file.name, flags=re.IGNORECASE)
                        clean_name = re.sub(r'\s*\(\d+\.\d+\).*', '', clean_name, flags=re.IGNORECASE)
                        song_name = clean_name.replace('.txt', '').strip()
                        parsed_curators = parse_raw_text_content(content, song_name)
                        merged = process_single_song_submissions_btn(song_name, parsed_curators, master_csv_df, purchases)
                        df = pd.DataFrame(merged)
                        if not df.empty:
                            submithub_dataframes.append(df)
                    
                    if submithub_dataframes:
                        final_sh_df = pd.concat(submithub_dataframes, ignore_index=True)
                        save_submithub_to_db(SUPABASE_URL, SUPABASE_KEY, final_sh_df, pd.DataFrame(uploaded_purchases))
                        st.toast("✅ Successfully saved SubmitHub data to Supabase!")
                        st.cache_data.clear()
                        st.rerun()
                except Exception as e:
                    st.error(f"Failed to save data: {e}")
    else:
        st.info("💡 Set Supabase credentials to save SubmitHub uploads permanently.")

    playlist_push_uploads = st.file_uploader("6. Add Playlist Push Data", type=["pdf", "csv"], accept_multiple_files=True)
    st.caption("📂 *Expects: (1) Campaign responses PDF (e.g. '[P] Campaign responses for_ Astronaut - Playlist Push.pdf'), (2) Campaign Invoice PDF (e.g. '[P] playlistpush-invoice-480065 - Astronaut.pdf'), or (3) Campaign summary CSV (e.g. 'Socially Acceptable - Playlist Push Campaign Results.csv')*")

    # Ingest to DB Button for Playlist Push
    if has_db:
        if st.button("💾 Save Playlist Push Uploads to DB", key="save_pp_db_btn", disabled=not playlist_push_uploads, use_container_width=True):
            with st.spinner("Processing and uploading Playlist Push data..."):
                try:
                    summary_csv = None
                    invoice_pdfs = []
                    response_pdfs = []
                    for file in playlist_push_uploads:
                        if file.name.endswith('.csv'):
                            summary_csv = file
                        elif file.name.endswith('.pdf'):
                            if 'invoice' in file.name.lower():
                                invoice_pdfs.append(file)
                            else:
                                response_pdfs.append(file)
                    
                    invoices_data = {}
                    for file in invoice_pdfs:
                        reader = pypdf.PdfReader(file)
                        text = ""
                        for page in reader.pages:
                            text += page.extract_text() + "\n"
                        lines = [line.strip() for line in text.split('\n')]
                        issued_date = None
                        amount_paid = None
                        song_name = None
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
                            elif 'Spotify campaign' in line:
                                if i + 1 < len(lines):
                                    cand = lines[i+1].strip()
                                    cand_clean = cand.replace('Socially Acceptable', '').strip()
                                    match_song = re.match(r'^([a-zA-Z\s]+)\s+\d+x', cand_clean)
                                    if match_song:
                                        song_name = match_song.group(1).strip()
                        if not song_name and 'invoice-' in file.name.lower():
                            parts = file.name.split('-')
                            if len(parts) >= 3:
                                song_name = parts[-1].replace('.pdf', '').strip()
                        if song_name:
                            invoices_data[song_name.lower()] = {
                                'song': song_name,
                                'issued_date': issued_date,
                                'amount_paid': amount_paid
                            }
                    
                    parsed_placements = []
                    for file in response_pdfs:
                        song_name_from_file = None
                        if 'responses for_' in file.name.lower():
                            parts = file.name.split('responses for_')
                            if len(parts) >= 2:
                                song_name_from_file = parts[1].split('-')[0].strip()
                        reader = pypdf.PdfReader(file)
                        text = ""
                        for page in reader.pages:
                            text += page.extract_text() + "\n"
                        lines = [line.strip() for line in text.split('\n')]
                        song_name = song_name_from_file
                        if not song_name and len(lines) > 0:
                            match_song = re.match(r'^(.+?)\s+by\s+Socially\s+Acceptable', lines[0], re.IGNORECASE)
                            if match_song:
                                song_name = match_song.group(1).strip()
                        print_date = datetime.now()
                        for line in lines:
                            match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}\s*[APM]*)', line, re.IGNORECASE)
                            if match:
                                try:
                                    date_str = match.group(1)
                                    parts = date_str.split('/')
                                    if len(parts[2]) == 2:
                                        parts[2] = '20' + parts[2]
                                    clean_date_str = '/'.join(parts)
                                    print_date = pd.to_datetime(clean_date_str)
                                    break
                                except Exception:
                                    pass
                        details_regex = re.compile(
                            r'([\d,]+)\s+Saves\s+·\s+Curator\s+(.+?)\s+(\d+\s+(?:year|month|day|week)s?\s+ago|a\s+year\s+ago|a\s+month\s+ago|a\s+day\s+ago)\s+#(\d+)\s+Avg\s+(\d+)\s+month[s]?',
                            re.IGNORECASE
                        )
                        i = 0
                        while i < len(lines):
                            line = lines[i]
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
                                    clean_str = time_ago.strip().lower()
                                    if 'year' in clean_str:
                                        m_val = re.search(r'(\d+)', clean_str)
                                        years = int(m_val.group(1)) if m_val else 1
                                        est_date = print_date - timedelta(days=years * 365)
                                    elif 'month' in clean_str:
                                        m_val = re.search(r'(\d+)', clean_str)
                                        months = int(m_val.group(1)) if m_val else 1
                                        est_date = print_date - timedelta(days=months * 30.4)
                                    elif 'week' in clean_str:
                                        m_val = re.search(r'(\d+)', clean_str)
                                        weeks = int(m_val.group(1)) if m_val else 1
                                        est_date = print_date - timedelta(weeks=weeks)
                                    else:
                                        est_date = print_date
                                    parsed_placements.append({
                                        'song': song_name,
                                        'playlist_name': playlist_name,
                                        'curator': curator,
                                        'saves': saves,
                                        'added_time_ago': time_ago,
                                        'estimated_date': est_date.date().isoformat(),
                                        'playlist_index': index,
                                        'avg_duration_months': avg_duration
                                    })
                            i += 1

                    camps = []
                    if summary_csv:
                        sdf = pd.read_csv(summary_csv)
                        sdf.columns = sdf.columns.str.strip().str.lower()
                        for idx, row in sdf.iterrows():
                            song_name = row['song'].strip()
                            budget_str = str(row['campaign budget']).replace('$', '').strip()
                            budget = float(budget_str)
                            responses_count = int(row['curator responses'])
                            adds = int(row['playlist adds'])
                            reach = int(str(row['playlist followers']).replace(',', '').strip())
                            popularity = int(row['spotify popularity']) if 'spotify popularity' in row else None
                            campaign_date = None
                            if song_name.lower() in invoices_data:
                                campaign_date = invoices_data[song_name.lower()]['issued_date']
                                if campaign_date:
                                    campaign_date = campaign_date.isoformat()
                            if not campaign_date:
                                song_placements = [p for p in parsed_placements if p['song'] and p['song'].lower() == song_name.lower()]
                                if song_placements:
                                    oldest = min(song_placements, key=lambda x: x['estimated_date'])
                                    campaign_date = oldest['estimated_date']
                            camps.append({
                                'song': song_name,
                                'campaign_date': campaign_date,
                                'budget_usd': budget,
                                'total_responses': responses_count,
                                'playlist_adds': adds,
                                'total_reach': reach,
                                'spotify_popularity': popularity
                            })
                    else:
                        songs = set(p['song'] for p in parsed_placements if p['song'])
                        for song_name in songs:
                            budget = 0.0
                            campaign_date = None
                            if song_name.lower() in invoices_data:
                                campaign_date = invoices_data[song_name.lower()]['issued_date']
                                if campaign_date:
                                    campaign_date = campaign_date.isoformat()
                                budget = invoices_data[song_name.lower()]['amount_paid'] or 0.0
                            
                            song_placements = [p for p in parsed_placements if p['song'] and p['song'].lower() == song_name.lower()]
                            if not campaign_date and song_placements:
                                oldest = min(song_placements, key=lambda x: x['estimated_date'])
                                campaign_date = oldest['estimated_date']
                                
                            total_saves = sum(p['saves'] for p in song_placements)
                            camps.append({
                                'song': song_name,
                                'campaign_date': campaign_date,
                                'budget_usd': budget,
                                'total_responses': len(song_placements),
                                'playlist_adds': len(song_placements),
                                'total_reach': total_saves,
                                'spotify_popularity': None
                            })
                            
                    save_playlist_push_to_db(SUPABASE_URL, SUPABASE_KEY, pd.DataFrame(camps), pd.DataFrame(parsed_placements))
                    st.toast("✅ Successfully saved Playlist Push data to Supabase!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save data: {e}")
    else:
        st.info("💡 Set Supabase credentials to save Playlist Push uploads permanently.")

    musosoup_uploads = st.file_uploader("7. Add Musosoup Data", type=["csv", "pdf"], accept_multiple_files=True)
    st.caption("📂 *Expects: (1) Campaign report CSV (e.g. 'Musosoup-Campaign-Report-SH2BA.csv') or (2) payment receipt PDF (e.g. 'Musosoup-payment-SH2BA.pdf')*")

    # Ingest to DB Button for Musosoup
    if has_db:
        if st.button("💾 Save Musosoup Uploads to DB", key="save_ms_db_btn", disabled=not musosoup_uploads, use_container_width=True):
            with st.spinner("Processing and uploading Musosoup data..."):
                try:
                    report_csvs = []
                    payment_pdfs = []
                    for file in musosoup_uploads:
                        if file.name.endswith('.csv'):
                            report_csvs.append(file)
                        elif file.name.endswith('.pdf'):
                            payment_pdfs.append(file)
                            
                    uploaded_payments = {}
                    for file in payment_pdfs:
                        reader = pypdf.PdfReader(file)
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
                                    date_val = pd.to_datetime(date_cand, dayfirst=True).date().isoformat()
                                except Exception:
                                    pass
                            elif 'Campaign activation' in line:
                                match = re.search(r'for\s+(?:Socially\s+Acceptable\s*-\s*)?([a-zA-Z0-9\s]+)', line, re.IGNORECASE)
                                if match:
                                    song_name = match.group(1).strip()
                            elif line.startswith('TOTAL'):
                                match = re.search(r'TOTAL\s*[^\d]*([\d\.]+)', line, re.IGNORECASE)
                                if match:
                                    amount = float(match.group(1))
                        if not song_name:
                            fn = file.name.lower()
                            for k in ['astronaut', 'great riddance', 'sh2ba']:
                                if k in fn:
                                    song_name = k
                                    break
                        if song_name:
                            uploaded_payments[song_name.lower()] = {
                                'song': song_name,
                                'date': date_val,
                                'amount': amount
                            }
                            
                    camps = []
                    placements = []
                    for file in report_csvs:
                        clean_name = file.name.replace("Musosoup-Campaign-Report-", "")
                        clean_name = re.sub(r'\s*\(\d+\.\d+\).*', '', clean_name, flags=re.IGNORECASE)
                        song_name = clean_name.replace(".csv", "").strip()
                        df = pd.read_csv(file)
                        df.columns = df.columns.str.strip().str.lower()
                        
                        df['placement_type'] = df['completion_url'].apply(get_placement_type)
                        playlist_adds = len(df[df['placement_type'] == 'Playlist'])
                        other_adds = len(df) - playlist_adds
                        
                        budget_gbp = 36.00
                        campaign_date = None
                        song_key = song_name.lower()
                        matched_payment = None
                        for k, pay in uploaded_payments.items():
                            if k in song_key or song_key in k:
                                matched_payment = pay
                                break
                        
                        matched_default = None
                        for k in CAMPAIGN_DEFAULTS:
                            if k in song_key or song_key in k:
                                matched_default = k
                                break

                        if matched_payment:
                            budget_gbp = matched_payment['amount'] or budget_gbp
                            campaign_date = matched_payment['date']
                        elif matched_default:
                            budget_gbp = CAMPAIGN_DEFAULTS[matched_default]['budget_gbp']
                            campaign_date = CAMPAIGN_DEFAULTS[matched_default]['campaign_date']
                            
                        if not campaign_date and not df.empty:
                            oldest_date = pd.to_datetime(df['completion_date']).min()
                            campaign_date = oldest_date.date().isoformat()
                            
                        budget_usd = round(budget_gbp * GBP_TO_USD, 2)
                        camps.append({
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
                    if camps:
                        save_musosoup_to_db(SUPABASE_URL, SUPABASE_KEY, pd.DataFrame(camps), pd.DataFrame(placements))
                        st.toast("✅ Successfully saved Musosoup data to Supabase!")
                        st.cache_data.clear()
                        st.rerun()
                except Exception as e:
                    st.error(f"Failed to save data: {e}")
    else:
        st.info("💡 Set Supabase credentials to save Musosoup uploads permanently.")

    ima_uploads = st.file_uploader("8. Add Indie Music Academy Data", type=["csv", "pdf", "txt"], accept_multiple_files=True)
    st.caption("📂 *Expects: (1) client portal results text (.txt) or (2) purchase invoice receipt PDF (e.g. 'Ryan Waczek_ Invoice astronaut.pdf')*")

    # Ingest to DB Button for IMA
    if has_db:
        if st.button("💾 Save IMA Uploads to DB", key="save_ima_db_btn", disabled=not ima_uploads, use_container_width=True):
            with st.spinner("Processing and uploading Indie Music Academy data..."):
                try:
                    invoice_pdfs = []
                    result_txts = []
                    for file in ima_uploads:
                        if file.name.endswith('.pdf'):
                            invoice_pdfs.append(file)
                        elif file.name.endswith('.txt'):
                            result_txts.append(file)
                            
                    uploaded_camps = {}
                    for file in invoice_pdfs:
                        reader = pypdf.PdfReader(file)
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
                        
                        for i, line in enumerate(lines):
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
                        if not song_name:
                            fn = file.name.lower()
                            if 'astronaut' in fn:
                                song_name = 'Astronaut'
                        if song_name:
                            uploaded_camps[song_name.lower()] = {
                                'song': song_name,
                                'campaign_date': invoice_date,
                                'budget_usd': amount,
                                'invoice_id': invoice_id,
                                'package_name': package_name,
                                'guaranteed_streams': guaranteed_streams
                            }
                            
                    parsed_placements = []
                    for file in result_txts:
                        content = file.getvalue().decode('utf-8', errors='ignore')
                        lines = [line.strip() for line in content.split('\n')]
                        
                        song_name = None
                        for line in lines:
                            if line.strip() in ['Astronaut', 'sh2ba', 'great riddance']:
                                song_name = line.strip()
                                break
                        if not song_name:
                            fn = file.name.lower()
                            if 'astronaut' in fn:
                                song_name = 'Astronaut'
                                
                        for idx, line in enumerate(lines):
                            if 'followers' in line.lower():
                                followers_match = re.search(r'([\d,]+)\s+followers', line, re.IGNORECASE)
                                followers = int(followers_match.group(1).replace(',', '')) if followers_match else 0
                                
                                curator = None
                                platform = 'Spotify'
                                playlist_name = None
                                
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
                                    parsed_placements.append({
                                        'song': song_name,
                                        'playlist_name': playlist_name,
                                        'platform': platform,
                                        'curator': curator,
                                        'followers': followers,
                                        'published_date': pub_date
                                    })
                                    
                    unique_songs = set(uploaded_camps.keys()).union(set(p['song'].lower() for p in parsed_placements if p['song']))
                    camps = []
                    for s_key in unique_songs:
                        if s_key in uploaded_camps:
                            camps.append(uploaded_camps[s_key])
                        else:
                            s_name = s_key.capitalize()
                            song_placements = [p for p in parsed_placements if p['song'] and p['song'].lower() == s_key]
                            pub_date = None
                            if song_placements:
                                dates = [p['published_date'] for p in song_placements if p['published_date']]
                                if dates:
                                    pub_date = min(dates)
                            camps.append({
                                'song': s_name,
                                'campaign_date': pub_date,
                                'budget_usd': 0.0,
                                'invoice_id': None,
                                'package_name': "Spotify Playlist Promotion",
                                'guaranteed_streams': 0
                            })
                    if camps:
                        save_ima_to_db(SUPABASE_URL, SUPABASE_KEY, pd.DataFrame(camps), pd.DataFrame(parsed_placements))
                        st.toast("✅ Successfully saved Indie Music Academy data to Supabase!")
                        st.cache_data.clear()
                        st.rerun()
                except Exception as e:
                    st.error(f"Failed to save data: {e}")
    else:
        st.info("💡 Set Supabase credentials to save Indie Music Academy uploads permanently.")

    instagram_uploads = st.file_uploader("9. Add Instagram Campaigns", type=["csv", "xlsx"], accept_multiple_files=True)
    st.caption("📂 *Expects: Instagram Post Campaign CSV or Excel reports (e.g. 'Insta Campaigns-Jun-1-2023-Jul-1-2026.xlsx')*")

    # Ingest to DB Button for Instagram
    if has_db:
        if st.button("💾 Save Instagram Uploads to DB", key="save_ig_db_btn", disabled=not instagram_uploads, use_container_width=True):
            with st.spinner("Processing and uploading Instagram campaigns..."):
                try:
                    dfs = []
                    for file in instagram_uploads:
                        if file.name.endswith(('.xlsx', '.xls')):
                            df = pd.read_excel(file)
                        else:
                            df = pd.read_csv(file)
                        campaigns = []
                        for idx, row in df.iterrows():
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
                                'results': int(pd.to_numeric(row.get('Results'), errors='coerce').fillna(0)),
                                'result_indicator': str(row.get('Result indicator', '')).strip(),
                                'reach': int(pd.to_numeric(row.get('Reach'), errors='coerce').fillna(0)),
                                'frequency': float(pd.to_numeric(row.get('Frequency'), errors='coerce').fillna(0.0)),
                                'amount_spent_usd': float(pd.to_numeric(row.get('Amount spent (USD)'), errors='coerce').fillna(0.0)),
                                'ends_date': ends.date().isoformat() if pd.notna(ends) else None,
                                'impressions': int(pd.to_numeric(row.get('Impressions'), errors='coerce').fillna(0)),
                                'link_clicks': int(pd.to_numeric(row.get('Link clicks'), errors='coerce').fillna(0)),
                                'cpc_usd': float(pd.to_numeric(row.get('CPC (cost per link click) (USD)'), errors='coerce').fillna(0.0)),
                                'ctr': float(pd.to_numeric(row.get('CTR (link click-through rate)'), errors='coerce').fillna(0.0)),
                                'clicks_all': int(pd.to_numeric(row.get('Clicks (all)'), errors='coerce').fillna(0))
                            })
                        if campaigns:
                            dfs.append(pd.DataFrame(campaigns))
                    if dfs:
                        save_instagram_to_db(SUPABASE_URL, SUPABASE_KEY, pd.concat(dfs, ignore_index=True))
                        st.toast("✅ Successfully saved Instagram campaigns to Supabase!")
                        st.cache_data.clear()
                        st.rerun()
                except Exception as e:
                    st.error(f"Failed to save data: {e}")
    else:
        st.info("💡 Set Supabase credentials to save Instagram uploads permanently.")






# Fetch Base Data from Supabase (with Fallbacks)
dk_base_df = load_base_data("distrokid_royalties", "DistroKid/DistroKid Results 6.12.26.csv", DK_COLUMN_MAP)
spot_base_df = load_base_data("spotify_campaign_metrics", "Spotify For Artists/Spotify Campaigns to date 6.12.26.csv", SPOTIFY_COLUMN_MAP)
s4a_base_df = load_base_data("s4a_daily_streams", None, {})
submithub_base_df = load_base_data("submithub_submissions", "SubmitHub/submithub_submissions_merged.csv", {})
submithub_purchases_base_df = load_base_data("submithub_credit_purchases", "SubmitHub/submithub_credit_purchases.csv", {})
pp_campaigns_base_df = load_base_data("playlist_push_campaigns", "Playlist Push/playlist_push_campaigns.csv", {})
pp_placements_base_df = load_base_data("playlist_push_placements", "Playlist Push/playlist_push_placements.csv", {})
ms_campaigns_base_df = load_base_data("musosoup_campaigns", "Musosoup/musosoup_campaigns.csv", {})
ms_placements_base_df = load_base_data("musosoup_placements", "Musosoup/musosoup_placements.csv", {})
ima_campaigns_base_df = load_base_data("ima_campaigns", "Indie Music Academy/ima_campaigns.csv", {})
ima_placements_base_df = load_base_data("ima_placements", "Indie Music Academy/ima_placements.csv", {})
instagram_campaigns_base_df = load_base_data("instagram_campaigns", "Instagram/instagram_campaigns.csv", {})





if (dk_base_df.empty and not dk_uploads) or (spot_base_df.empty and not spot_uploads):
    st.info("👋 Welcome! Waiting for data. Please ensure your Supabase database is seeded, or drop your files in the sidebar.")
    st.stop()

# --- 3. DATA PROCESSING & AUTO-STITCHING ---

@st.cache_data
def process_data(dk_base_df, dk_files, spot_base_df, spot_files, s4a_base_df, s4a_files, meta_files, 
                 submithub_base_df, submithub_purchases_base_df, submithub_files,
                 pp_campaigns_base_df, pp_placements_base_df, pp_files,
                 ms_campaigns_base_df, ms_placements_base_df, ms_files,
                 ima_campaigns_base_df, ima_placements_base_df, ima_files,
                 instagram_campaigns_base_df, instagram_files):
    
    def stitch_data(base_df, uploaded_files):
        dfs = []
        if not base_df.empty:
            dfs.append(base_df)
        if uploaded_files:
            for file in uploaded_files:
                dfs.append(pd.read_csv(file, low_memory=False))
        
        if dfs:
            combined = pd.concat(dfs, ignore_index=True)
            return combined.drop_duplicates()
        return pd.DataFrame()

    dk_df = stitch_data(dk_base_df, dk_files)
    spot_df = stitch_data(spot_base_df, spot_files)
    meta_df = stitch_data(pd.DataFrame(), meta_files) 
    
    s4a_dataframes = []
    if not s4a_base_df.empty:
        # Standardize DB S4A columns
        s4a_base_df['date'] = pd.to_datetime(s4a_base_df['date'], errors='coerce')
        s4a_base_df['streams'] = pd.to_numeric(s4a_base_df['streams'], errors='coerce').fillna(0)
        s4a_dataframes.append(s4a_base_df)
        
    if s4a_files:
        for file in s4a_files:
            try:
                temp_df = pd.read_csv(file)
                temp_df.columns = temp_df.columns.str.lower()
                if 'date' in temp_df.columns and 'streams' in temp_df.columns:
                    temp_df['date'] = pd.to_datetime(temp_df['date'], errors='coerce')
                    temp_df['streams'] = pd.to_numeric(temp_df['streams'], errors='coerce').fillna(0)
                    raw_name = os.path.splitext(file.name)[0]
                    track_name = raw_name.replace('-timeline', '').replace('_timeline', '').replace(' timeline', '').strip()
                    temp_df['track_name'] = track_name
                    s4a_dataframes.append(temp_df)
            except Exception:
                pass 
                
    if s4a_dataframes:
        s4a_df = pd.concat(s4a_dataframes, ignore_index=True).drop_duplicates()
    else:
        s4a_df = pd.DataFrame(columns=['date', 'streams', 'track_name'])
        
    # --- SubmitHub Upload Classification & Parsing ---
    xlsx_file = None
    history_csv_file = None
    text_files = []
    pre_parsed_csvs = []
    
    if submithub_files:
        for file in submithub_files:
            if file.name.endswith('.xlsx') or file.name.endswith('.xls') or 'purchase' in file.name.lower():
                xlsx_file = file
            elif file.name.endswith('.csv'):
                try:
                    df_check = pd.read_csv(file, nrows=5)
                    file.seek(0)
                    if 'Song' in df_check.columns and 'Outlet' in df_check.columns and 'Campaign date' in df_check.columns:
                        history_csv_file = file
                    else:
                        pre_parsed_csvs.append(file)
                except Exception:
                    try:
                        file.seek(0)
                    except Exception:
                        pass
                    pre_parsed_csvs.append(file)
            elif file.name.endswith('.txt') or 'text' in file.name.lower():
                text_files.append(file)

    # Resolve purchases list
    uploaded_purchases = []
    if xlsx_file:
        try:
            purchase_df = pd.read_excel(xlsx_file)
            purchase_df.columns = purchase_df.columns.str.strip().str.lower()
            if all(col in purchase_df.columns for col in ['date', 'paid', 'credits']):
                for idx, row in purchase_df.iterrows():
                    raw_date = row['date']
                    p_date = pd.to_datetime(raw_date).isoformat() if not isinstance(raw_date, pd.Timestamp) else raw_date.isoformat()
                    uploaded_purchases.append({
                        'purchase_date': p_date,
                        'amount_paid_usd': float(row['paid']),
                        'credits_purchased': int(row['credits'])
                    })
        except Exception:
            pass
            
    db_purchases = []
    if not submithub_purchases_base_df.empty:
        for idx, row in submithub_purchases_base_df.iterrows():
            db_purchases.append({
                'purchase_date': pd.to_datetime(row['purchase_date']).isoformat(),
                'amount_paid_usd': float(row['amount_paid_usd']),
                'credits_purchased': int(row['credits_purchased'])
            })
            
    purchases = uploaded_purchases if uploaded_purchases else db_purchases

    # Resolve master CSV
    master_csv_df = pd.DataFrame()
    if history_csv_file:
        try:
            master_csv_df = pd.read_csv(history_csv_file)
        except Exception:
            pass
    else:
        # Check local path fallback
        fallback_path = "data-backend/SubmitHub/The Socially Acceptable Band submission history (Jun 29, 2026).csv"
        if os.path.exists(fallback_path):
            try:
                master_csv_df = pd.read_csv(fallback_path)
            except Exception:
                pass

    # Helper for cost calculation
    def get_cost_per_credit(campaign_date_str, purchase_list):
        if not purchase_list:
            return 0.85
        def to_naive(dt_val):
            dt = pd.to_datetime(dt_val)
            return dt.tz_localize(None) if dt.tzinfo is not None else dt
        
        try:
            campaign_dt = to_naive(campaign_date_str)
        except Exception:
            campaign_dt = to_naive(pd.Timestamp.now())
            
        sorted_p = sorted(purchase_list, key=lambda x: to_naive(x['purchase_date']))
        best_cost = None
        for p in sorted_p:
            p_dt = to_naive(p['purchase_date'])
            if p_dt <= campaign_dt:
                best_cost = p['amount_paid_usd'] / p['credits_purchased']
        if best_cost is None:
            first = sorted_p[0]
            best_cost = first['amount_paid_usd'] / first['credits_purchased']
        return best_cost

    # Helper to process single song raw text
    def process_single_song_submissions(song_name, parsed_curators, csv_df, purchase_list):
        if csv_df.empty:
            final_records = []
            for curator in parsed_curators:
                credits = curator['credits_spent']
                cost_usd = 0.00 if curator['is_refunded'] else round(credits * 0.85, 2)
                final_records.append({
                    'song': song_name,
                    'campaign_url': None,
                    'campaign_date': None,
                    'outlet': curator['outlet'],
                    'outlet_type': curator['outlet_type'],
                    'outlet_url': None,
                    'outlet_country': None,
                    'action': curator['status'],
                    'action_timestamp': None,
                    'feedback': curator['feedback'],
                    'listen_time_seconds': None,
                    'credits_spent': credits,
                    'credit_type': curator['credit_type'],
                    'is_refunded': curator['is_refunded'],
                    'cost_usd': cost_usd,
                    'share_destination': curator['share_destination'],
                    'estimated_reach': curator['estimated_reach']
                })
            return final_records
            
        song_df = csv_df[csv_df['Song'].str.contains(song_name, case=False, na=False)].copy()
        if song_df.empty:
            final_records = []
            for curator in parsed_curators:
                credits = curator['credits_spent']
                cost_usd = 0.00 if curator['is_refunded'] else round(credits * 0.85, 2)
                final_records.append({
                    'song': song_name,
                    'campaign_url': None,
                    'campaign_date': None,
                    'outlet': curator['outlet'],
                    'outlet_type': curator['outlet_type'],
                    'outlet_url': None,
                    'outlet_country': None,
                    'action': curator['status'],
                    'action_timestamp': None,
                    'feedback': curator['feedback'],
                    'listen_time_seconds': None,
                    'credits_spent': credits,
                    'credit_type': curator['credit_type'],
                    'is_refunded': curator['is_refunded'],
                    'cost_usd': cost_usd,
                    'share_destination': curator['share_destination'],
                    'estimated_reach': curator['estimated_reach']
                })
            return final_records
            
        grouped = song_df.groupby('Outlet')
        final_records = []
        for curator in parsed_curators:
            curator_name = curator['outlet']
            matched_group = None
            for name, group in grouped:
                if name.strip().lower() == curator_name.strip().lower():
                    matched_group = group
                    break
            if matched_group is None:
                campaign_url = None
                campaign_date = None
                outlet_url = None
                outlet_country = None
                action_timestamp = None
                listen_time = None
            else:
                first_row = matched_group.iloc[0]
                campaign_url = first_row.get('Campaign url')
                campaign_date = first_row.get('Campaign date')
                outlet_url = first_row.get('Outlet url')
                outlet_country = first_row.get('Outlet country')
                if pd.notna(campaign_date):
                    campaign_date = pd.to_datetime(campaign_date).isoformat()
                action_timestamp = pd.to_datetime(matched_group['Action timestamp'], format='mixed', utc=True).max()
                if pd.notna(action_timestamp):
                    action_timestamp = action_timestamp.isoformat()
                listen_time = int(matched_group['Listen time (seconds)'].max()) if pd.notna(matched_group['Listen time (seconds)'].max()) else None
                
            cost_per_credit = get_cost_per_credit(campaign_date or pd.Timestamp.now(), purchase_list)
            credits_spent = curator['credits_spent']
            if curator['is_refunded']:
                cost_usd = 0.00
            else:
                cost_usd = round(credits_spent * cost_per_credit, 4)
                
            record = {
                'song': song_name,
                'campaign_url': campaign_url,
                'campaign_date': campaign_date,
                'outlet': curator_name,
                'outlet_type': curator['outlet_type'],
                'outlet_url': outlet_url,
                'outlet_country': outlet_country,
                'action': curator['status'],
                'action_timestamp': action_timestamp,
                'feedback': curator['feedback'],
                'listen_time_seconds': listen_time,
                'credits_spent': credits_spent,
                'credit_type': curator['credit_type'],
                'is_refunded': curator['is_refunded'],
                'cost_usd': cost_usd,
                'share_destination': curator['share_destination'],
                'estimated_reach': curator['estimated_reach']
            }
            final_records.append(record)
        return final_records

    # Main uploader processing logic
    submithub_dataframes = []
    if not submithub_base_df.empty:
        submithub_base_df['cost_usd'] = pd.to_numeric(submithub_base_df['cost_usd'], errors='coerce').fillna(0)
        submithub_base_df['credits_spent'] = pd.to_numeric(submithub_base_df['credits_spent'], errors='coerce').fillna(0)
        submithub_base_df['estimated_reach'] = pd.to_numeric(submithub_base_df['estimated_reach'], errors='coerce')
        submithub_dataframes.append(submithub_base_df)
        
    for file in pre_parsed_csvs:
        try:
            df = pd.read_csv(file)
            submithub_dataframes.append(df)
        except Exception:
            pass
            
    for file in text_files:
        try:
            content = file.getvalue().decode('utf-8', errors='ignore')
            clean_name = re.sub(r'\s*response\s*page\s*text.*', '', file.name, flags=re.IGNORECASE)
            clean_name = re.sub(r'\s*\(\d+\.\d+\).*', '', clean_name, flags=re.IGNORECASE)
            song_name = clean_name.replace('.txt', '').strip()
            parsed_curators = parse_raw_text_content(content, song_name)
            merged = process_single_song_submissions(song_name, parsed_curators, master_csv_df, purchases)
            df = pd.DataFrame(merged)
            if not df.empty:
                submithub_dataframes.append(df)
        except Exception:
            pass
            
    if submithub_dataframes:
        submithub_df = pd.concat(submithub_dataframes, ignore_index=True).drop_duplicates(subset=['song', 'outlet'])
    else:
        submithub_df = pd.DataFrame(columns=['song', 'outlet', 'outlet_type', 'credits_spent', 'credit_type', 'status', 'feedback', 'is_refunded', 'cost_usd', 'estimated_reach'])

    # --- Playlist Push PDF parsing buffers ---
    def parse_invoice_pdf_buffer(file_buf):
        try:
            reader = pypdf.PdfReader(file_buf)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            lines = [line.strip() for line in text.split('\n')]
            
            issued_date = None
            amount_paid = None
            song_name = None
            
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
                elif 'Spotify campaign' in line:
                    if i + 1 < len(lines):
                        cand = lines[i+1].strip()
                        cand_clean = cand.replace('Socially Acceptable', '').strip()
                        match_song = re.match(r'^([a-zA-Z\s]+)\s+\d+x', cand_clean)
                        if match_song:
                            song_name = match_song.group(1).strip()
                            
            if not song_name and 'invoice-' in file_buf.name.lower():
                parts = file_buf.name.split('-')
                if len(parts) >= 3:
                    song_name = parts[-1].replace('.pdf', '').strip()
                    
            return {
                'song': song_name,
                'issued_date': issued_date,
                'amount_paid': amount_paid
            }
        except Exception:
            return None

    def parse_responses_pdf_buffer(file_buf, song_name_from_file=None):
        try:
            reader = pypdf.PdfReader(file_buf)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            lines = [line.strip() for line in text.split('\n')]
            
            song_name = song_name_from_file
            if not song_name and len(lines) > 0:
                match_song = re.match(r'^(.+?)\s+by\s+Socially\s+Acceptable', lines[0], re.IGNORECASE)
                if match_song:
                    song_name = match_song.group(1).strip()
                    
            print_date = datetime.now()
            for line in lines:
                match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}\s*[APM]*)', line, re.IGNORECASE)
                if match:
                    try:
                        date_str = match.group(1)
                        parts = date_str.split('/')
                        if len(parts[2]) == 2:
                            parts[2] = '20' + parts[2]
                        clean_date_str = '/'.join(parts)
                        print_date = pd.to_datetime(clean_date_str)
                        break
                    except Exception:
                        pass
                        
            placements = []
            details_regex = re.compile(
                r'([\d,]+)\s+Saves\s+·\s+Curator\s+(.+?)\s+(\d+\s+(?:year|month|day|week)s?\s+ago|a\s+year\s+ago|a\s+month\s+ago|a\s+day\s+ago)\s+#(\d+)\s+Avg\s+(\d+)\s+month[s]?',
                re.IGNORECASE
            )
            
            i = 0
            while i < len(lines):
                line = lines[i]
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
                        
                        clean_str = time_ago.strip().lower()
                        if 'year' in clean_str:
                            m_val = re.search(r'(\d+)', clean_str)
                            years = int(m_val.group(1)) if m_val else 1
                            est_date = print_date - timedelta(days=years * 365)
                        elif 'month' in clean_str:
                            m_val = re.search(r'(\d+)', clean_str)
                            months = int(m_val.group(1)) if m_val else 1
                            est_date = print_date - timedelta(days=months * 30.4)
                        elif 'week' in clean_str:
                            m_val = re.search(r'(\d+)', clean_str)
                            weeks = int(m_val.group(1)) if m_val else 1
                            est_date = print_date - timedelta(weeks=weeks)
                        else:
                            est_date = print_date
                            
                        placements.append({
                            'song': song_name,
                            'playlist_name': playlist_name,
                            'curator': curator,
                            'saves': saves,
                            'added_time_ago': time_ago,
                            'estimated_date': est_date.date().isoformat(),
                            'playlist_index': index,
                            'avg_duration_months': avg_duration
                        })
                i += 1
            return placements
        except Exception:
            return []

    # --- Playlist Push Parsing ---
    pp_campaigns_dfs = []
    pp_placements_dfs = []
    
    if not pp_campaigns_base_df.empty:
        pp_campaigns_dfs.append(pp_campaigns_base_df)
    if not pp_placements_base_df.empty:
        pp_placements_dfs.append(pp_placements_base_df)
        
    has_pp_uploads = False
    if pp_files:
        has_pp_uploads = True
        summary_csv = None
        invoice_pdfs = []
        response_pdfs = []
        for file in pp_files:
            if file.name.endswith('.csv'):
                summary_csv = file
            elif file.name.endswith('.pdf'):
                if 'invoice' in file.name.lower():
                    invoice_pdfs.append(file)
                else:
                    response_pdfs.append(file)
                    
        invoices_data = {}
        for file in invoice_pdfs:
            res = parse_invoice_pdf_buffer(file)
            if res and res['song']:
                invoices_data[res['song'].lower()] = res
                
        parsed_placements = []
        for file in response_pdfs:
            song_name_from_file = None
            if 'responses for_' in file.name.lower():
                parts = file.name.split('responses for_')
                if len(parts) >= 2:
                    song_name_from_file = parts[1].split('-')[0].strip()
            pl = parse_responses_pdf_buffer(file, song_name_from_file)
            parsed_placements.extend(pl)
            
        if summary_csv:
            try:
                sdf = pd.read_csv(summary_csv)
                sdf.columns = sdf.columns.str.strip().str.lower()
                camps = []
                for idx, row in sdf.iterrows():
                    song_name = row['song'].strip()
                    budget_str = str(row['campaign budget']).replace('$', '').strip()
                    budget = float(budget_str)
                    responses_count = int(row['curator responses'])
                    adds = int(row['playlist adds'])
                    reach = int(str(row['playlist followers']).replace(',', '').strip())
                    popularity = int(row['spotify popularity']) if 'spotify popularity' in row else None
                    
                    campaign_date = None
                    if song_name.lower() in invoices_data:
                        campaign_date = invoices_data[song_name.lower()]['issued_date']
                        if campaign_date:
                            campaign_date = campaign_date.isoformat()
                            
                    if not campaign_date:
                        song_placements = [p for p in parsed_placements if p['song'] and p['song'].lower() == song_name.lower()]
                        if song_placements:
                            oldest = min(song_placements, key=lambda x: x['estimated_date'])
                            campaign_date = oldest['estimated_date']
                            
                    camps.append({
                        'song': song_name,
                        'campaign_date': campaign_date,
                        'budget_usd': budget,
                        'total_responses': responses_count,
                        'playlist_adds': adds,
                        'total_reach': reach,
                        'spotify_popularity': popularity
                    })
                pp_campaigns_dfs.append(pd.DataFrame(camps))
            except Exception:
                pass
                
        if parsed_placements:
            pp_placements_dfs.append(pd.DataFrame(parsed_placements))
            
    if not has_pp_uploads and pp_campaigns_base_df.empty:
        pp_dir = "data-backend/Playlist Push"
        local_csv = os.path.join(pp_dir, "Socially Acceptable - Playlist Push Campaign Results.csv")
        if os.path.exists(local_csv):
            try:
                sdf = pd.read_csv(local_csv)
                sdf.columns = sdf.columns.str.strip().str.lower()
                camps = []
                local_placements = []
                for idx, row in sdf.iterrows():
                    song_name = row['song'].strip()
                    budget_str = str(row['campaign budget']).replace('$', '').strip()
                    budget = float(budget_str)
                    responses_count = int(row['curator responses'])
                    adds = int(row['playlist adds'])
                    reach = int(str(row['playlist followers']).replace(',', '').strip())
                    popularity = int(row['spotify popularity']) if 'spotify popularity' in row else None
                    
                    resp_pdf_name = f"[P] Campaign responses for_ {song_name} - Playlist Push.pdf"
                    resp_pdf_path = None
                    for f in os.listdir(pp_dir):
                        if f.lower() == resp_pdf_name.lower():
                            resp_pdf_path = os.path.join(pp_dir, f)
                            break
                    pl = []
                    if resp_pdf_path:
                        with open(resp_pdf_path, 'rb') as f_pdf:
                            pl = parse_responses_pdf_buffer(f_pdf, song_name)
                            for p in pl:
                                p['song'] = song_name
                            local_placements.extend(pl)
                            
                    inv_pdf_path = None
                    for f in os.listdir(pp_dir):
                        if 'invoice' in f.lower() and song_name.lower() in f.lower() and f.endswith('.pdf'):
                            inv_pdf_path = os.path.join(pp_dir, f)
                            break
                    campaign_date = None
                    if inv_pdf_path:
                        with open(inv_pdf_path, 'rb') as f_pdf:
                            inv_data = parse_invoice_pdf_buffer(f_pdf)
                            if inv_data and inv_data['issued_date']:
                                campaign_date = inv_data['issued_date'].isoformat()
                                
                    if not campaign_date and pl:
                        oldest = min(pl, key=lambda x: x['estimated_date'])
                        campaign_date = oldest['estimated_date']
                        
                    camps.append({
                        'song': song_name,
                        'campaign_date': campaign_date,
                        'budget_usd': budget,
                        'total_responses': responses_count,
                        'playlist_adds': adds,
                        'total_reach': reach,
                        'spotify_popularity': popularity
                    })
                pp_campaigns_dfs.append(pd.DataFrame(camps))
                if local_placements:
                    pp_placements_dfs.append(pd.DataFrame(local_placements))
            except Exception:
                pass
                
    if pp_campaigns_dfs:
        pp_campaigns_df = pd.concat(pp_campaigns_dfs, ignore_index=True).drop_duplicates(subset=['song'])
    else:
        pp_campaigns_df = pd.DataFrame(columns=['song', 'campaign_date', 'budget_usd', 'total_responses', 'playlist_adds', 'total_reach', 'spotify_popularity'])
        
    if pp_placements_dfs:
        pp_placements_df = pd.concat(pp_placements_dfs, ignore_index=True).drop_duplicates(subset=['song', 'playlist_name'])
    else:
        pp_placements_df = pd.DataFrame(columns=['song', 'playlist_name', 'curator', 'saves', 'added_time_ago', 'estimated_date', 'playlist_index', 'avg_duration_months'])

    # Standardize types
    if not pp_campaigns_df.empty:
        pp_campaigns_df['budget_usd'] = pd.to_numeric(pp_campaigns_df['budget_usd'], errors='coerce').fillna(0)
        pp_campaigns_df['total_responses'] = pd.to_numeric(pp_campaigns_df['total_responses'], errors='coerce').fillna(0)
        pp_campaigns_df['playlist_adds'] = pd.to_numeric(pp_campaigns_df['playlist_adds'], errors='coerce').fillna(0)
        pp_campaigns_df['total_reach'] = pd.to_numeric(pp_campaigns_df['total_reach'], errors='coerce').fillna(0)
    if not pp_placements_df.empty:
        pp_placements_df['saves'] = pd.to_numeric(pp_placements_df['saves'], errors='coerce').fillna(0)
        pp_placements_df['playlist_index'] = pd.to_numeric(pp_placements_df['playlist_index'], errors='coerce').fillna(0)
        pp_placements_df['avg_duration_months'] = pd.to_numeric(pp_placements_df['avg_duration_months'], errors='coerce').fillna(0)
        
    if not spot_df.empty:
        spot_df['Start Date'] = pd.to_datetime(spot_df['Start Date'].astype(str).str.replace(' UTC', ''), errors='coerce')
        spot_df['End Date'] = pd.to_datetime(spot_df['End Date'].astype(str).str.replace(' UTC', ''), errors='coerce')
        spot_df['Spend'] = pd.to_numeric(spot_df['Spend'], errors='coerce').fillna(0)
        spot_df['Converted Listeners'] = pd.to_numeric(spot_df['Converted Listeners'], errors='coerce').fillna(0)
        spot_df['Save Rate'] = pd.to_numeric(spot_df['Save Rate'].astype(str).str.replace('%', ''), errors='coerce').fillna(0)
        spot_df['Intent Rate'] = pd.to_numeric(spot_df['Intent Rate'].astype(str).str.replace('%', ''), errors='coerce').fillna(0)
    
    # --- Musosoup Processing ---
    ms_campaigns_dfs = []
    ms_placements_dfs = []
    
    if not ms_campaigns_base_df.empty:
        ms_campaigns_dfs.append(ms_campaigns_base_df)
    if not ms_placements_base_df.empty:
        ms_placements_dfs.append(ms_placements_base_df)
        
    has_ms_uploads = False
    if ms_files:
        has_ms_uploads = True
        report_csvs = []
        payment_pdfs = []
        for file in ms_files:
            if file.name.endswith('.csv'):
                report_csvs.append(file)
            elif file.name.endswith('.pdf'):
                payment_pdfs.append(file)
                
        # Parse payments
        uploaded_payments = {}
        for file in payment_pdfs:
            try:
                reader = pypdf.PdfReader(file)
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
                            date_val = pd.to_datetime(date_cand, dayfirst=True).date().isoformat()
                        except Exception:
                            pass
                    elif 'Campaign activation' in line:
                        match = re.search(r'for\s+(?:Socially\s+Acceptable\s*-\s*)?([a-zA-Z0-9\s]+)', line, re.IGNORECASE)
                        if match:
                            song_name = match.group(1).strip()
                    elif line.startswith('TOTAL'):
                        match = re.search(r'TOTAL\s*[^\d]*([\d\.]+)', line, re.IGNORECASE)
                        if match:
                            amount = float(match.group(1))
                if not song_name:
                    fn = file.name.lower()
                    for k in ['astronaut', 'great riddance', 'sh2ba']:
                        if k in fn:
                            song_name = k
                            break
                if song_name:
                    uploaded_payments[song_name.lower()] = {
                        'song': song_name,
                        'date': date_val,
                        'amount': amount
                    }
            except Exception:
                pass
                
        # Parse reports
        parsed_placements = []
        camps = []
        for file in report_csvs:
            try:
                clean_name = file.name.replace("Musosoup-Campaign-Report-", "")
                clean_name = re.sub(r'\s*\(\d+\.\d+\).*', '', clean_name, flags=re.IGNORECASE)
                song_name = clean_name.replace(".csv", "").strip()
                df = pd.read_csv(file)
                df.columns = df.columns.str.strip().str.lower()
                
                df['placement_type'] = df['completion_url'].apply(get_placement_type)
                playlist_adds = len(df[df['placement_type'] == 'Playlist'])
                other_adds = len(df) - playlist_adds
                
                budget_gbp = 36.00
                campaign_date = None
                song_key = song_name.lower()
                matched_payment = None
                for k, pay in uploaded_payments.items():
                    if k in song_key or song_key in k:
                        matched_payment = pay
                        break
                
                matched_default = None
                for k in CAMPAIGN_DEFAULTS:
                    if k in song_key or song_key in k:
                        matched_default = k
                        break

                if matched_payment:
                    budget_gbp = matched_payment['amount'] or budget_gbp
                    campaign_date = matched_payment['date']
                elif matched_default:
                    budget_gbp = CAMPAIGN_DEFAULTS[matched_default]['budget_gbp']
                    campaign_date = CAMPAIGN_DEFAULTS[matched_default]['campaign_date']
                    
                if not campaign_date and not df.empty:
                    oldest_date = pd.to_datetime(df['completion_date']).min()
                    campaign_date = oldest_date.date().isoformat()
                    
                budget_usd = round(budget_gbp * GBP_TO_USD, 2)
                
                camps.append({
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
                    parsed_placements.append({
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
            except Exception:
                pass
                
        if camps:
            ms_campaigns_dfs.append(pd.DataFrame(camps))
        if parsed_placements:
            ms_placements_dfs.append(pd.DataFrame(parsed_placements))
            
    if not has_ms_uploads and ms_campaigns_base_df.empty:
        muso_dir = "data-backend/Musosoup"
        if os.path.exists(muso_dir):
            try:
                local_csvs = [f for f in os.listdir(muso_dir) if f.startswith("Musosoup-Campaign-Report-") and f.endswith(".csv")]
                camps = []
                local_placements = []
                for rf in local_csvs:
                    song_name = rf.replace("Musosoup-Campaign-Report-", "").replace(".csv", "").strip()
                    df = pd.read_csv(os.path.join(muso_dir, rf))
                    df.columns = df.columns.str.strip().str.lower()
                    
                    df['placement_type'] = df['completion_url'].apply(get_placement_type)
                    playlist_adds = len(df[df['placement_type'] == 'Playlist'])
                    other_adds = len(df) - playlist_adds
                    
                    budget_gbp = 36.00
                    campaign_date = None
                    song_key = song_name.lower()
                    if song_key in CAMPAIGN_DEFAULTS:
                        budget_gbp = CAMPAIGN_DEFAULTS[song_key]['budget_gbp']
                        campaign_date = CAMPAIGN_DEFAULTS[song_key]['campaign_date']
                    if not campaign_date and not df.empty:
                        oldest_date = pd.to_datetime(df['completion_date']).min()
                        campaign_date = oldest_date.date().isoformat()
                        
                    budget_usd = round(budget_gbp * GBP_TO_USD, 2)
                    camps.append({
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
                            comp_date = pd.to_datetime(row['completion_date']).isoformat()
                        local_placements.append({
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
                if camps:
                    ms_campaigns_dfs.append(pd.DataFrame(camps))
                if local_placements:
                    ms_placements_dfs.append(pd.DataFrame(local_placements))
            except Exception:
                pass
                
    if ms_campaigns_dfs:
        ms_campaigns_df = pd.concat(ms_campaigns_dfs, ignore_index=True).drop_duplicates(subset=['song'])
    else:
        ms_campaigns_df = pd.DataFrame(columns=['song', 'campaign_date', 'budget_gbp', 'budget_usd', 'playlist_adds', 'other_adds'])
        
    if ms_placements_dfs:
        ms_placements_df = pd.concat(ms_placements_dfs, ignore_index=True).drop_duplicates(subset=['song', 'completion_url'])
    else:
        ms_placements_df = pd.DataFrame(columns=['song', 'curator', 'publication', 'completion_date', 'accept_type', 'contribution_gbp', 'contribution_usd', 'completion_url', 'placement_type'])

    if not ms_campaigns_df.empty:
        ms_campaigns_df['budget_usd'] = pd.to_numeric(ms_campaigns_df['budget_usd'], errors='coerce').fillna(0)
        ms_campaigns_df['budget_gbp'] = pd.to_numeric(ms_campaigns_df['budget_gbp'], errors='coerce').fillna(0)
        ms_campaigns_df['playlist_adds'] = pd.to_numeric(ms_campaigns_df['playlist_adds'], errors='coerce').fillna(0)
        ms_campaigns_df['other_adds'] = pd.to_numeric(ms_campaigns_df['other_adds'], errors='coerce').fillna(0)
    if not ms_placements_df.empty:
        ms_placements_df['contribution_gbp'] = pd.to_numeric(ms_placements_df['contribution_gbp'], errors='coerce').fillna(0)
        ms_placements_df['contribution_usd'] = pd.to_numeric(ms_placements_df['contribution_usd'], errors='coerce').fillna(0)

    if not meta_df.empty:
        meta_df['Start Date'] = pd.to_datetime(meta_df['Start Date'], errors='coerce')
        meta_df['Amount Spent (USD)'] = pd.to_numeric(meta_df['Amount Spent (USD)'], errors='coerce').fillna(0)
    else:
        meta_df = pd.DataFrame(columns=['Start Date', 'Amount Spent (USD)'])
    
    if not dk_df.empty:
        dk_df['Reporting Date'] = pd.to_datetime(dk_df['Reporting Date'], errors='coerce')
        dk_df['Earnings (USD)'] = pd.to_numeric(dk_df['Earnings (USD)'], errors='coerce').fillna(0)
        dk_df['Quantity'] = pd.to_numeric(dk_df['Quantity'], errors='coerce').fillna(0)

    # --- Instagram Campaigns Processing ---
    instagram_campaigns_dfs = []
    if not instagram_campaigns_base_df.empty:
        instagram_campaigns_dfs.append(instagram_campaigns_base_df)
    if instagram_files:
        for file in instagram_files:
            try:
                is_excel = False
                if hasattr(file, 'name'):
                    is_excel = file.name.endswith(('.xlsx', '.xls'))
                elif isinstance(file, str):
                    is_excel = file.endswith(('.xlsx', '.xls'))
                
                if is_excel:
                    df = pd.read_excel(file)
                else:
                    df = pd.read_csv(file)
                    
                campaigns = []
                for idx, row in df.iterrows():
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
                        'results': int(pd.to_numeric(row.get('Results'), errors='coerce').fillna(0)),
                        'result_indicator': str(row.get('Result indicator', '')).strip(),
                        'reach': int(pd.to_numeric(row.get('Reach'), errors='coerce').fillna(0)),
                        'frequency': float(pd.to_numeric(row.get('Frequency'), errors='coerce').fillna(0.0)),
                        'amount_spent_usd': float(pd.to_numeric(row.get('Amount spent (USD)'), errors='coerce').fillna(0.0)),
                        'ends_date': ends.date().isoformat() if pd.notna(ends) else None,
                        'impressions': int(pd.to_numeric(row.get('Impressions'), errors='coerce').fillna(0)),
                        'link_clicks': int(pd.to_numeric(row.get('Link clicks'), errors='coerce').fillna(0)),
                        'cpc_usd': float(pd.to_numeric(row.get('CPC (cost per link click) (USD)'), errors='coerce').fillna(0.0)),
                        'ctr': float(pd.to_numeric(row.get('CTR (link click-through rate)'), errors='coerce').fillna(0.0)),
                        'clicks_all': int(pd.to_numeric(row.get('Clicks (all)'), errors='coerce').fillna(0))
                    })
                if campaigns:
                    instagram_campaigns_dfs.append(pd.DataFrame(campaigns))
            except Exception:
                pass
                
    if not instagram_files and instagram_campaigns_base_df.empty:
        ig_file = "data-backend/Instagram/instagram_campaigns.csv"
        if os.path.exists(ig_file):
            try:
                instagram_campaigns_dfs.append(pd.read_csv(ig_file))
            except Exception:
                pass
                
    if instagram_campaigns_dfs:
        instagram_df = pd.concat(instagram_campaigns_dfs, ignore_index=True).drop_duplicates(subset=['campaign_name', 'reporting_starts'])
    else:
        instagram_df = pd.DataFrame(columns=[
            'reporting_starts', 'reporting_ends', 'campaign_name', 'campaign_delivery', 'results',
            'result_indicator', 'reach', 'frequency', 'amount_spent_usd', 'ends_date',
            'impressions', 'link_clicks', 'cpc_usd', 'ctr', 'clicks_all'
        ])
        
    if not instagram_df.empty:
        instagram_df['amount_spent_usd'] = pd.to_numeric(instagram_df['amount_spent_usd'], errors='coerce').fillna(0.0)
        instagram_df['reporting_starts'] = pd.to_datetime(instagram_df['reporting_starts'], errors='coerce')
        instagram_df['ends_date'] = pd.to_datetime(instagram_df['ends_date'], errors='coerce')

    # --- Indie Music Academy Processing ---
    ima_campaigns_dfs = []
    ima_placements_dfs = []
    
    if not ima_campaigns_base_df.empty:
        ima_campaigns_dfs.append(ima_campaigns_base_df)
    if not ima_placements_base_df.empty:
        ima_placements_dfs.append(ima_placements_base_df)
        
    has_ima_uploads = False
    if ima_files:
        has_ima_uploads = True
        invoice_pdfs = []
        result_txts = []
        for file in ima_files:
            if file.name.endswith('.pdf'):
                invoice_pdfs.append(file)
            elif file.name.endswith('.txt'):
                result_txts.append(file)
                
        # Parse invoices
        uploaded_camps = {}
        for file in invoice_pdfs:
            try:
                reader = pypdf.PdfReader(file)
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
                
                for i, line in enumerate(lines):
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
                if not song_name:
                    fn = file.name.lower()
                    if 'astronaut' in fn:
                        song_name = 'Astronaut'
                if song_name:
                    uploaded_camps[song_name.lower()] = {
                        'song': song_name,
                        'campaign_date': invoice_date,
                        'budget_usd': amount,
                        'invoice_id': invoice_id,
                        'package_name': package_name,
                        'guaranteed_streams': guaranteed_streams
                    }
            except Exception:
                pass
                
        # Parse placements
        parsed_placements = []
        for file in result_txts:
            try:
                content = file.getvalue().decode('utf-8', errors='ignore')
                lines = [line.strip() for line in content.split('\n')]
                
                song_name = None
                for line in lines:
                    if line.strip() in ['Astronaut', 'sh2ba', 'great riddance']:
                        song_name = line.strip()
                        break
                if not song_name:
                    fn = file.name.lower()
                    if 'astronaut' in fn:
                        song_name = 'Astronaut'
                        
                for idx, line in enumerate(lines):
                    if 'followers' in line.lower():
                        followers_match = re.search(r'([\d,]+)\s+followers', line, re.IGNORECASE)
                        followers = int(followers_match.group(1).replace(',', '')) if followers_match else 0
                        
                        curator = None
                        platform = 'Spotify'
                        playlist_name = None
                        
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
                            parsed_placements.append({
                                'song': song_name,
                                'playlist_name': playlist_name,
                                'platform': platform,
                                'curator': curator,
                                'followers': followers,
                                'published_date': pub_date
                            })
            except Exception:
                pass
                
        unique_songs = set(uploaded_camps.keys()).union(set(p['song'].lower() for p in parsed_placements if p['song']))
        camps = []
        for s_key in unique_songs:
            if s_key in uploaded_camps:
                camps.append(uploaded_camps[s_key])
            else:
                s_name = s_key.capitalize()
                song_placements = [p for p in parsed_placements if p['song'] and p['song'].lower() == s_key]
                pub_date = None
                if song_placements:
                    dates = [p['published_date'] for p in song_placements if p['published_date']]
                    if dates:
                        pub_date = min(dates)
                camps.append({
                    'song': s_name,
                    'campaign_date': pub_date,
                    'budget_usd': 0.0,
                    'invoice_id': None,
                    'package_name': "Spotify Playlist Promotion",
                    'guaranteed_streams': 0
                })
        if camps:
            ima_campaigns_dfs.append(pd.DataFrame(camps))
        if parsed_placements:
            ima_placements_dfs.append(pd.DataFrame(parsed_placements))
            
    if not has_ima_uploads and ima_campaigns_base_df.empty:
        ima_dir = "data-backend/Indie Music Academy"
        if os.path.exists(ima_dir):
            try:
                local_pdfs = [f for f in os.listdir(ima_dir) if f.endswith('.pdf')]
                local_txts = [f for f in os.listdir(ima_dir) if f.endswith('.txt')]
                
                local_uploaded_camps = {}
                for f in local_pdfs:
                    with open(os.path.join(ima_dir, f), 'rb') as f_pdf:
                        res = parse_invoice_pdf(f_pdf)
                        if res and res['song']:
                            local_uploaded_camps[res['song'].lower()] = res
                            
                local_parsed_placements = []
                for f in local_txts:
                    with open(os.path.join(ima_dir, f), 'r', encoding='utf-8', errors='ignore') as f_txt:
                        content = f_txt.read()
                        lines = [line.strip() for line in content.split('\n')]
                        song_name = None
                        for line in lines:
                            if line.strip() in ['Astronaut', 'sh2ba', 'great riddance']:
                                song_name = line.strip()
                                break
                        if not song_name:
                            fn = f.lower()
                            if 'astronaut' in fn:
                                song_name = 'Astronaut'
                        for idx, line in enumerate(lines):
                            if 'followers' in line.lower():
                                followers_match = re.search(r'([\d,]+)\s+followers', line, re.IGNORECASE)
                                followers = int(followers_match.group(1).replace(',', '')) if followers_match else 0
                                
                                curator = None
                                platform = 'Spotify'
                                playlist_name = None
                                
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
                                    local_parsed_placements.append({
                                        'song': song_name,
                                        'playlist_name': playlist_name,
                                        'platform': platform,
                                        'curator': curator,
                                        'followers': followers,
                                        'published_date': pub_date
                                    })
                unique_songs = set(local_uploaded_camps.keys()).union(set(p['song'].lower() for p in local_parsed_placements if p['song']))
                camps = []
                for s_key in unique_songs:
                    if s_key in local_uploaded_camps:
                        camps.append(local_uploaded_camps[s_key])
                    else:
                        s_name = s_key.capitalize()
                        song_placements = [p for p in local_parsed_placements if p['song'] and p['song'].lower() == s_key]
                        pub_date = None
                        if song_placements:
                            dates = [p['published_date'] for p in song_placements if p['published_date']]
                            if dates:
                                pub_date = min(dates)
                        camps.append({
                            'song': s_name,
                            'campaign_date': pub_date,
                            'budget_usd': 0.0,
                            'invoice_id': None,
                            'package_name': "Spotify Playlist Promotion",
                            'guaranteed_streams': 0
                        })
                if camps:
                    ima_campaigns_dfs.append(pd.DataFrame(camps))
                if local_parsed_placements:
                    ima_placements_dfs.append(pd.DataFrame(local_parsed_placements))
            except Exception:
                pass
                
    if ima_campaigns_dfs:
        ima_campaigns_df = pd.concat(ima_campaigns_dfs, ignore_index=True).drop_duplicates(subset=['song'])
    else:
        ima_campaigns_df = pd.DataFrame(columns=['song', 'campaign_date', 'budget_usd', 'invoice_id', 'package_name', 'guaranteed_streams'])
        
    if ima_placements_dfs:
        ima_placements_df = pd.concat(ima_placements_dfs, ignore_index=True).drop_duplicates(subset=['song', 'playlist_name'])
    else:
        ima_placements_df = pd.DataFrame(columns=['song', 'playlist_name', 'platform', 'curator', 'followers', 'published_date'])
        
    if not ima_campaigns_df.empty:
        ima_campaigns_df['budget_usd'] = pd.to_numeric(ima_campaigns_df['budget_usd'], errors='coerce').fillna(0)
        ima_campaigns_df['guaranteed_streams'] = pd.to_numeric(ima_campaigns_df['guaranteed_streams'], errors='coerce').fillna(0)
    if not ima_placements_df.empty:
        ima_placements_df['followers'] = pd.to_numeric(ima_placements_df['followers'], errors='coerce').fillna(0)

    return dk_df, spot_df, s4a_df, meta_df, submithub_df, pp_campaigns_df, pp_placements_df, ms_campaigns_df, ms_placements_df, ima_campaigns_df, ima_placements_df, instagram_df

with st.spinner("Stitching and processing datasets..."):
    dk_df, spot_df, s4a_df, meta_df, submithub_df, pp_campaigns_df, pp_placements_df, ms_campaigns_df, ms_placements_df, ima_campaigns_df, ima_placements_df, instagram_df = process_data(
        dk_base_df, dk_uploads, spot_base_df, spot_uploads, s4a_base_df, s4a_uploads, meta_uploads, 
        submithub_base_df, submithub_purchases_base_df, submithub_uploads,
        pp_campaigns_base_df, pp_placements_base_df, playlist_push_uploads,
        ms_campaigns_base_df, ms_placements_base_df, musosoup_uploads,
        ima_campaigns_base_df, ima_placements_base_df, ima_uploads,
        instagram_campaigns_base_df, instagram_uploads
    )




# --- INJECT DATA FRESHNESS CALLOUTS ---
if not dk_df.empty:
    dk_max_date = dk_df['Reporting Date'].max()
    dk_freshness.caption(f"*(Combined Data Through: {dk_max_date.strftime('%b %d, %Y')})*")
if not spot_df.empty:
    spot_max_date = spot_df['End Date'].max()
    spot_freshness.caption(f"*(Combined Data Through: {spot_max_date.strftime('%b %d, %Y')})*")

if not s4a_df.empty:
    loaded_tracks = s4a_df['track_name'].unique()
    st.sidebar.success(f"✅ Successfully loaded S4A data for: {', '.join(loaded_tracks)}")

# --- FEATURE 1: EXECUTIVE FILTERS (TRACK & TIMEFRAME) ---
st.sidebar.divider()
st.sidebar.subheader("🎯 Executive Filters")

dk_tracks = dk_df['Title'].dropna().unique().tolist() if not dk_df.empty else []
spot_tracks = spot_df['Release Name'].dropna().unique().tolist() if not spot_df.empty else []
s4a_tracks = s4a_df['track_name'].dropna().unique().tolist() if not s4a_df.empty else []
sh_tracks = submithub_df['song'].dropna().unique().tolist() if not submithub_df.empty else []
pp_tracks = pp_campaigns_df['song'].dropna().unique().tolist() if not pp_campaigns_df.empty else []
ms_tracks = ms_campaigns_df['song'].dropna().unique().tolist() if not ms_campaigns_df.empty else []
ima_tracks = ima_campaigns_df['song'].dropna().unique().tolist() if not ima_campaigns_df.empty else []

all_tracks = sorted(list(set(dk_tracks + spot_tracks + s4a_tracks + sh_tracks + pp_tracks + ms_tracks + ima_tracks)))

selected_view = st.sidebar.selectbox("Track Selection", ["All Catalog (Aggregate)"] + all_tracks)

timeframe_options = {"28 Days": 28, "6 Months": 180, "12 Months": 365, "All Time": None}
selected_timeframe = st.sidebar.selectbox("Timeframe", list(timeframe_options.keys()))
days_lookback = timeframe_options[selected_timeframe]

if selected_view != "All Catalog (Aggregate)":
    dk_df = dk_df[dk_df['Title'] == selected_view] if not dk_df.empty else dk_df
    spot_df = spot_df[spot_df['Release Name'] == selected_view] if not spot_df.empty else spot_df
    s4a_df = s4a_df[s4a_df['track_name'].str.contains(selected_view, case=False, na=False, regex=False)] if not s4a_df.empty else s4a_df
    submithub_df = submithub_df[submithub_df['song'].str.contains(selected_view, case=False, na=False, regex=False)] if not submithub_df.empty else submithub_df
    pp_campaigns_df = pp_campaigns_df[pp_campaigns_df['song'].str.contains(selected_view, case=False, na=False, regex=False)] if not pp_campaigns_df.empty else pp_campaigns_df
    pp_placements_df = pp_placements_df[pp_placements_df['song'].str.contains(selected_view, case=False, na=False, regex=False)] if not pp_placements_df.empty else pp_placements_df
    ms_campaigns_df = ms_campaigns_df[ms_campaigns_df['song'].str.contains(selected_view, case=False, na=False, regex=False)] if not ms_campaigns_df.empty else ms_campaigns_df
    ms_placements_df = ms_placements_df[ms_placements_df['song'].str.contains(selected_view, case=False, na=False, regex=False)] if not ms_placements_df.empty else ms_placements_df
    ima_campaigns_df = ima_campaigns_df[ima_campaigns_df['song'].str.contains(selected_view, case=False, na=False, regex=False)] if not ima_campaigns_df.empty else ima_campaigns_df
    ima_placements_df = ima_placements_df[ima_placements_df['song'].str.contains(selected_view, case=False, na=False, regex=False)] if not ima_placements_df.empty else ima_placements_df



# --- 4. AUTOMATED EDA LOGIC ---
def generate_ai_brief(dk_df, spot_df, s4a_df, meta_df):
    brief_lines = []
    brief_lines.append("## TSAB ON-DEMAND ANOMALY BRIEF")
    brief_lines.append("*(Paste this directly into the CMO AI for strategic recommendations)*\n")
    
    phantom_cost_total = 0 
    
    # 1. DISCOVERY MODE ALGORITHM 
    brief_lines.append("### 1. DISCOVERY MODE ALGORITHM (Phantom Cost vs Reach)")
    if not dk_df.empty:
        spot_only = dk_df[dk_df['Store'].str.contains('Spotify', na=False, case=False)].copy()
        if not spot_only.empty:
            spot_only['Month'] = spot_only['Reporting Date'].dt.to_period('M')
            monthly_stats = spot_only.groupby(['Title', 'Month']).agg({'Quantity': 'sum', 'Earnings (USD)': 'sum'}).reset_index()
            monthly_stats['EPS'] = monthly_stats['Earnings (USD)'] / monthly_stats['Quantity']
            monthly_stats = monthly_stats[monthly_stats['Quantity'] > 500] 
            
            monthly_stats = monthly_stats.sort_values(by=['Title', 'Month'])
            monthly_stats['Prev_EPS'] = monthly_stats.groupby('Title')['EPS'].shift(1)
            monthly_stats['Prev_Qty'] = monthly_stats.groupby('Title')['Quantity'].shift(1)
            
            discovery_alerts = []
            for idx, row in monthly_stats.dropna().iterrows():
                eps_ratio = row['EPS'] / row['Prev_EPS']
                vol_ratio = row['Quantity'] / row['Prev_Qty']
                
                if 0.65 <= eps_ratio <= 0.85 and vol_ratio > 1.20:
                    phantom_tax = (row['Prev_EPS'] * row['Quantity']) - row['Earnings (USD)']
                    phantom_cost_total += phantom_tax
                    new_streams = row['Quantity'] - row['Prev_Qty']
                    effective_cpa = phantom_tax / new_streams if new_streams > 0 else 0
                    
                    discovery_alerts.append(f"- 📡 **Discovery Mode Detected on '{row['Title']}':** EPS dropped by {(1-eps_ratio)*100:.0f}%, but streams grew by {(vol_ratio-1)*100:.0f}%.")
                    discovery_alerts.append(f"  - **The Math:** You sacrificed ${phantom_tax:.2f} in royalties to gain {new_streams:,.0f} new streams. Effective Cost: **${effective_cpa:.4f} per stream.**")
                    
            if discovery_alerts: brief_lines.extend(discovery_alerts)
            else: brief_lines.append("- No active Discovery Mode algorithmic tax detected this reporting period.")
        else:
            brief_lines.append("- No Spotify data available for this selection to run Discovery Mode checks.")
    else:
        brief_lines.append("- No data available.")

    # 2. Algorithmic Tipping Point
    brief_lines.append("\n### 2. ALGORITHMIC TIPPING POINTS (Spotify)")
    if not spot_df.empty:
        high_intent = spot_df[(spot_df['Save Rate'] > 10) | (spot_df['Intent Rate'] > 10)]
        unique_tipping_points = high_intent.drop_duplicates(subset=['Campaign Name', 'Release Name'])
        
        if not unique_tipping_points.empty:
            for idx, row in unique_tipping_points.iterrows():
                brief_lines.append(f"- 🟢 **GREEN LIGHT:** Campaign '{row['Campaign Name']}' hit a Save Rate of {row['Save Rate']}%. Algorithm pickup is highly likely.")
        else:
            brief_lines.append("- No immediate algorithmic tipping points detected (Save/Intent rates under 10%).")
    else:
        brief_lines.append("- No campaign data available.")

    # 3. Decay Curve (Real-Time S4A)
    brief_lines.append("\n### 3. DECAY CURVE (14-Day Real-Time Retention)")
    retention_alerts = []
    if s4a_df.empty or spot_df.empty:
        brief_lines.append("- *Awaiting Data: Please ensure both Campaign and S4A Daily Track CSVs are loaded.*")
    else:
        unique_campaigns = spot_df.drop_duplicates(subset=['Release Name', 'Start Date', 'End Date']).dropna(subset=['Start Date', 'End Date', 'Release Name'])
        
        for idx, row in unique_campaigns.iterrows():
            track_name = row['Release Name']
            camp_date = row['Start Date'].strftime('%b %Y')
            
            matched_tracks = s4a_df[s4a_df['track_name'].str.contains(track_name, case=False, na=False, regex=False)]
            if matched_tracks.empty: continue
                
            daily_streams = matched_tracks.groupby('date')['streams'].sum()
            pre_mask = (daily_streams.index >= (row['Start Date'] - pd.Timedelta(days=14))) & (daily_streams.index < row['Start Date'])
            post_mask = (daily_streams.index > row['End Date']) & (daily_streams.index <= (row['End Date'] + pd.Timedelta(days=14)))
            
            avg_pre = daily_streams.loc[pre_mask].mean() if not daily_streams.loc[pre_mask].empty else 0
            avg_post = daily_streams.loc[post_mask].mean() if not daily_streams.loc[post_mask].empty else 0
            
            if avg_pre == 0 and avg_post > 0:
                retention_alerts.append(f"- 🚀 **New Release Lift:** '{track_name}' ({camp_date} Campaign) established a new post-campaign baseline of {avg_post:.0f} daily streams.")
            elif avg_pre > 0:
                lift = (avg_post / avg_pre) - 1
                if lift > 0.20:
                    retention_alerts.append(f"- 🔥 **High Retention:** '{track_name}' ({camp_date} Campaign) permanently increased its baseline by {lift*100:.0f}%. True fans acquired.")
                elif 0.05 <= lift <= 0.20:
                    retention_alerts.append(f"- ⚖️ **Moderate Retention:** '{track_name}' ({camp_date} Campaign) held a slight baseline increase of {lift*100:.0f}%.")
                elif lift < 0.05 and row['Spend'] > 0:
                    retention_alerts.append(f"- ⚠️ **Empty Calories:** '{track_name}' ({camp_date} Campaign) baseline dropped back to normal immediately after ad spend stopped.")
                
        if retention_alerts: 
            brief_lines.extend(retention_alerts) 
        else: 
            brief_lines.append("- Campaigns processed, but 14-day post-campaign data is still maturing.")

    # 4. Geographic Anomalies
    brief_lines.append("\n### 4. GEOGRAPHIC ANOMALIES (Stream Spikes)")
    if not dk_df.empty:
        dk_geo = dk_df.groupby(['Reporting Date', 'Country of Sale'])['Quantity'].sum().reset_index()
        if not dk_geo.empty:
            dk_geo['mean_7d'] = dk_geo.groupby('Country of Sale')['Quantity'].transform(lambda x: x.rolling(7, min_periods=1).mean())
            dk_geo['std_7d'] = dk_geo.groupby('Country of Sale')['Quantity'].transform(lambda x: x.rolling(7, min_periods=1).std().fillna(0))
            spikes = dk_geo[(dk_geo['Quantity'] > (dk_geo['mean_7d'] + 2 * dk_geo['std_7d'])) & (dk_geo['Quantity'] > 20)]
            if not spikes.empty:
                for idx, row in spikes.sort_values('Quantity', ascending=False).head(3).iterrows():
                    brief_lines.append(f"- **{row['Country of Sale']}**: {row['Quantity']:.0f} streams on {row['Reporting Date'].strftime('%Y-%m-%d')}.")
            else:
                brief_lines.append("- No statistically significant geographic volume spikes detected recently.")
        else:
            brief_lines.append("- Insufficient geographic data for this view.")
    else:
        brief_lines.append("- No data available.")

    # 5. Cross-Platform Correlations
    brief_lines.append("\n### 5. CROSS-PLATFORM CORRELATIONS (Halo Effect)")
    if not dk_df.empty and not spot_df.empty:
        non_spot_df = dk_df[~dk_df['Store'].str.contains('Spotify', na=False, case=False)]
        non_spot_daily = non_spot_df.groupby('Reporting Date')['Quantity'].sum()
        halo_effects = []
        
        unique_start_dates = spot_df['Start Date'].dropna().unique()
        for start_date in unique_start_dates:
            before_mask = (non_spot_daily.index >= (start_date - pd.Timedelta(days=7))) & (non_spot_daily.index < start_date)
            after_mask = (non_spot_daily.index >= start_date) & (non_spot_daily.index < (start_date + pd.Timedelta(days=7)))
            streams_before = non_spot_daily.loc[before_mask].sum()
            streams_after = non_spot_daily.loc[after_mask].sum()
            if streams_before > 0 and streams_after > (streams_before * 1.2):
                halo_effects.append(f"- Campaign on {pd.to_datetime(start_date).strftime('%Y-%m-%d')} correlated with +{((streams_after/streams_before)-1)*100:.1f}% organic spike on Apple/YouTube.")
        
        if halo_effects: brief_lines.extend(halo_effects[:2])
        else: brief_lines.append("- No significant 'halo effect' organic jumps detected on alternative platforms.")
    else:
        brief_lines.append("- Missing data to cross-reference platforms.")

    return "\n".join(brief_lines), phantom_cost_total

ai_brief, phantom_spend = generate_ai_brief(dk_df, spot_df, s4a_df, meta_df)

# --- 5. UI LAYOUT & DYNAMIC TIMEFRAME METRICS ---
view_title = "Aggregate Catalog" if selected_view == "All Catalog (Aggregate)" else selected_view
st.subheader(f"📊 The Vitals: {view_title}")

dk_anchor = dk_df['Reporting Date'].max() if not dk_df.empty else pd.Timestamp.now()
spot_anchor = spot_df['End Date'].max() if not spot_df.empty else pd.Timestamp.now()
meta_anchor = meta_df['Start Date'].max() if not meta_df.empty else pd.Timestamp.now()
submithub_anchor = pd.to_datetime(submithub_df['campaign_date'], errors='coerce').max() if not submithub_df.empty else pd.Timestamp.now()
# Standardize date formats in submithub_df & pp_campaigns_df & ms_campaigns_df & ima_campaigns_df
if not submithub_df.empty:
    submithub_df['campaign_date'] = pd.to_datetime(submithub_df['campaign_date'], errors='coerce')
    submithub_df['cost_usd'] = pd.to_numeric(submithub_df['cost_usd'], errors='coerce').fillna(0)
if not pp_campaigns_df.empty:
    pp_campaigns_df['campaign_date'] = pd.to_datetime(pp_campaigns_df['campaign_date'], errors='coerce')
    pp_campaigns_df['budget_usd'] = pd.to_numeric(pp_campaigns_df['budget_usd'], errors='coerce').fillna(0)
if not ms_campaigns_df.empty:
    ms_campaigns_df['campaign_date'] = pd.to_datetime(ms_campaigns_df['campaign_date'], errors='coerce')
    ms_campaigns_df['budget_usd'] = pd.to_numeric(ms_campaigns_df['budget_usd'], errors='coerce').fillna(0)
if not ima_campaigns_df.empty:
    ima_campaigns_df['campaign_date'] = pd.to_datetime(ima_campaigns_df['campaign_date'], errors='coerce')
    ima_campaigns_df['budget_usd'] = pd.to_numeric(ima_campaigns_df['budget_usd'], errors='coerce').fillna(0)

pp_anchor = pd.to_datetime(pp_campaigns_df['campaign_date'], errors='coerce').max() if not pp_campaigns_df.empty else pd.Timestamp.now()
ms_anchor = pd.to_datetime(ms_campaigns_df['campaign_date'], errors='coerce').max() if not ms_campaigns_df.empty else pd.Timestamp.now()
ima_anchor = pd.to_datetime(ima_campaigns_df['campaign_date'], errors='coerce').max() if not ima_campaigns_df.empty else pd.Timestamp.now()
ig_anchor = instagram_df['reporting_starts'].max() if not instagram_df.empty else pd.Timestamp.now()

if days_lookback:
    dk_current = dk_df[(dk_df['Reporting Date'] > dk_anchor - pd.Timedelta(days=days_lookback)) & (dk_df['Reporting Date'] <= dk_anchor)] if not dk_df.empty else dk_df
    spot_current = spot_df[(spot_df['End Date'] > spot_anchor - pd.Timedelta(days=days_lookback)) & (spot_df['End Date'] <= spot_anchor)] if not spot_df.empty else spot_df
    meta_current = meta_df[(meta_df['Start Date'] > meta_anchor - pd.Timedelta(days=days_lookback)) & (meta_df['Start Date'] <= meta_anchor)] if not meta_df.empty else meta_df
    submithub_current = submithub_df[(submithub_df['campaign_date'] > submithub_anchor - pd.Timedelta(days=days_lookback)) & (submithub_df['campaign_date'] <= submithub_anchor)] if not submithub_df.empty else submithub_df
    pp_current = pp_campaigns_df[(pp_campaigns_df['campaign_date'] > pp_anchor - pd.Timedelta(days=days_lookback)) & (pp_campaigns_df['campaign_date'] <= pp_anchor)] if not pp_campaigns_df.empty else pp_campaigns_df
    ms_current = ms_campaigns_df[(ms_campaigns_df['campaign_date'] > ms_anchor - pd.Timedelta(days=days_lookback)) & (ms_campaigns_df['campaign_date'] <= ms_anchor)] if not ms_campaigns_df.empty else ms_campaigns_df
    ima_current = ima_campaigns_df[(ima_campaigns_df['campaign_date'] > ima_anchor - pd.Timedelta(days=days_lookback)) & (ima_campaigns_df['campaign_date'] <= ima_anchor)] if not ima_campaigns_df.empty else ima_campaigns_df
    instagram_current = instagram_df[(instagram_df['reporting_starts'] > ig_anchor - pd.Timedelta(days=days_lookback)) & (instagram_df['reporting_starts'] <= ig_anchor)] if not instagram_df.empty else instagram_df
    
    dk_prior = dk_df[(dk_df['Reporting Date'] > dk_anchor - pd.Timedelta(days=days_lookback*2)) & (dk_df['Reporting Date'] <= dk_anchor - pd.Timedelta(days=days_lookback))] if not dk_df.empty else dk_df
    spot_prior = spot_df[(spot_df['End Date'] > spot_anchor - pd.Timedelta(days=days_lookback*2)) & (spot_df['End Date'] <= spot_anchor - pd.Timedelta(days=days_lookback))] if not spot_df.empty else spot_df
    meta_prior = meta_df[(meta_df['Start Date'] > meta_anchor - pd.Timedelta(days=days_lookback*2)) & (meta_df['Start Date'] <= meta_anchor - pd.Timedelta(days=days_lookback))] if not meta_df.empty else meta_df
    submithub_prior = submithub_df[(submithub_df['campaign_date'] > submithub_anchor - pd.Timedelta(days=days_lookback*2)) & (submithub_df['campaign_date'] <= submithub_anchor - pd.Timedelta(days=days_lookback))] if not submithub_df.empty else submithub_df
    pp_prior = pp_campaigns_df[(pp_campaigns_df['campaign_date'] > pp_anchor - pd.Timedelta(days=days_lookback*2)) & (pp_campaigns_df['campaign_date'] <= pp_anchor - pd.Timedelta(days=days_lookback))] if not pp_campaigns_df.empty else pp_campaigns_df
    ms_prior = ms_campaigns_df[(ms_campaigns_df['campaign_date'] > ms_anchor - pd.Timedelta(days=days_lookback*2)) & (ms_campaigns_df['campaign_date'] <= ms_anchor - pd.Timedelta(days=days_lookback))] if not ms_campaigns_df.empty else ms_campaigns_df
    ima_prior = ima_campaigns_df[(ima_campaigns_df['campaign_date'] > ima_anchor - pd.Timedelta(days=days_lookback*2)) & (ima_campaigns_df['campaign_date'] <= ima_anchor - pd.Timedelta(days=days_lookback))] if not ima_campaigns_df.empty else ima_campaigns_df
    instagram_prior = instagram_df[(instagram_df['reporting_starts'] > ig_anchor - pd.Timedelta(days=days_lookback*2)) & (instagram_df['reporting_starts'] <= ig_anchor - pd.Timedelta(days=days_lookback))] if not instagram_df.empty else instagram_df
else:
    dk_current = dk_df
    spot_current = spot_df
    meta_current = meta_df
    submithub_current = submithub_df
    pp_current = pp_campaigns_df
    ms_current = ms_campaigns_df
    ima_current = ima_campaigns_df
    instagram_current = instagram_df
    
    dk_prior = pd.DataFrame(columns=dk_df.columns if not dk_df.empty else [])
    spot_prior = pd.DataFrame(columns=spot_df.columns if not spot_df.empty else [])
    meta_prior = pd.DataFrame(columns=meta_df.columns if not meta_df.empty else [])
    submithub_prior = pd.DataFrame(columns=submithub_df.columns if not submithub_df.empty else [])
    pp_prior = pd.DataFrame(columns=pp_campaigns_df.columns if not pp_campaigns_df.empty else [])
    ms_prior = pd.DataFrame(columns=ms_campaigns_df.columns if not ms_campaigns_df.empty else [])
    ima_prior = pd.DataFrame(columns=ima_campaigns_df.columns if not ima_campaigns_df.empty else [])
    instagram_prior = pd.DataFrame(columns=instagram_df.columns if not instagram_df.empty else [])

# Compute Blended Spend: Spotify + Meta + SubmitHub + Playlist Push + Musosoup + Indie Music Academy + Instagram Campaigns
spend_current = (
    (spot_current['Spend'].sum() if not spot_current.empty else 0) + 
    (meta_current['Amount Spent (USD)'].sum() if not meta_current.empty else 0) + 
    (submithub_current['cost_usd'].sum() if not submithub_current.empty else 0) +
    (pp_current['budget_usd'].sum() if not pp_current.empty else 0) +
    (ms_current['budget_usd'].sum() if not ms_current.empty else 0) +
    (ima_current['budget_usd'].sum() if not ima_current.empty else 0) +
    (instagram_current['amount_spent_usd'].sum() if not instagram_current.empty else 0)
)
earn_current = dk_current['Earnings (USD)'].sum() if not dk_current.empty else 0
# Compute Blended Conversions: Spotify converted listeners + SubmitHub approvals + Playlist Push adds + Musosoup adds + IMA placements
conv_current = (
    (spot_current['Converted Listeners'].sum() if not spot_current.empty else 0) + 
    (submithub_current[submithub_current['action'] == 'Approved'].shape[0] if not submithub_current.empty else 0) +
    (pp_current['playlist_adds'].sum() if not pp_current.empty else 0) +
    ((ms_current['playlist_adds'].sum() + ms_current['other_adds'].sum()) if not ms_current.empty else 0) +
    (ima_placements_df[ima_placements_df['song'].isin(ima_current['song'])].shape[0] if not ima_placements_df.empty and not ima_current.empty else 0)
)
streams_current = dk_current['Quantity'].sum() if not dk_current.empty else 0
save_current = spot_current['Save Rate'].mean() if not spot_current.empty else 0

roas_current = (earn_current / spend_current) if spend_current > 0 else 0
cpa_current = (spend_current / conv_current) if conv_current > 0 else 0

spend_prior = (
    (spot_prior['Spend'].sum() if not spot_prior.empty and 'Spend' in spot_prior.columns else 0) + 
    (meta_prior['Amount Spent (USD)'].sum() if not meta_prior.empty and 'Amount Spent (USD)' in meta_prior.columns else 0) + 
    (submithub_prior['cost_usd'].sum() if not submithub_prior.empty and 'cost_usd' in submithub_prior.columns else 0) +
    (pp_prior['budget_usd'].sum() if not pp_prior.empty and 'budget_usd' in pp_prior.columns else 0) +
    (ms_prior['budget_usd'].sum() if not ms_prior.empty and 'budget_usd' in ms_prior.columns else 0) +
    (ima_prior['budget_usd'].sum() if not ima_prior.empty and 'budget_usd' in ima_prior.columns else 0) +
    (instagram_prior['amount_spent_usd'].sum() if not instagram_prior.empty and 'amount_spent_usd' in instagram_prior.columns else 0)
)
earn_prior = dk_prior['Earnings (USD)'].sum() if not dk_prior.empty and 'Earnings (USD)' in dk_prior.columns else 0
conv_prior = (
    (spot_prior['Converted Listeners'].sum() if not spot_prior.empty and 'Converted Listeners' in spot_prior.columns else 0) + 
    (submithub_prior[submithub_prior['action'] == 'Approved'].shape[0] if not submithub_prior.empty else 0) +
    (pp_prior['playlist_adds'].sum() if not pp_prior.empty and 'playlist_adds' in pp_prior.columns else 0) +
    ((ms_prior['playlist_adds'].sum() + ms_prior['other_adds'].sum()) if not ms_prior.empty and 'playlist_adds' in ms_prior.columns else 0) +
    (ima_placements_df[ima_placements_df['song'].isin(ima_prior['song'])].shape[0] if not ima_placements_df.empty and not ima_prior.empty else 0)
)
streams_prior = dk_prior['Quantity'].sum() if not dk_prior.empty and 'Quantity' in dk_prior.columns else 0
save_prior = spot_prior['Save Rate'].mean() if not spot_prior.empty and 'Save Rate' in spot_prior.columns else 0

roas_prior = (earn_prior / spend_prior) if spend_prior > 0 else 0
cpa_prior = (spend_prior / conv_prior) if conv_prior > 0 else 0

d_roas = roas_current - roas_prior if days_lookback else None
d_cpa = cpa_current - cpa_prior if days_lookback else None
d_save = save_current - save_prior if days_lookback else None
d_streams = streams_current - streams_prior if days_lookback else None

# --- UPDATE: Restoring the Help/Tooltip Parameter ---
def render_metric(col, label, value, delta_val, formatting_str, help_text=None, is_inverse=False):
    delta_display = f"{delta_val:{formatting_str}}" if delta_val is not None else None
    d_color = "inverse" if is_inverse else "normal"
    if label.startswith("Upfront CPA") and delta_val is not None:
        delta_display = f"${delta_display}"
    elif label.startswith("Blended ROAS") and delta_val is not None:
        delta_display = f"{delta_display}x"
    elif label.startswith("Avg. Save Rate") and delta_val is not None:
        delta_display = f"{delta_display}%"
        
    col.metric(f"{label}", value, delta=delta_display, delta_color=d_color, help=help_text)

if selected_view == "All Catalog (Aggregate)":
    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
    render_metric(col_kpi1, "💰 Blended ROAS", f"{roas_current:.2f}x", d_roas, ".2f", help_text="Blended Return on Ad Spend. Calculated as: Total Royalty Earnings / Total Ad Spend (Spotify + Meta).")
    render_metric(col_kpi2, "🎯 Upfront CPA", f"${cpa_current:.2f}", d_cpa, ".2f", help_text="Upfront Cost per Acquisition. Calculated as: Total Ad Spend / Converted Listeners on Spotify.", is_inverse=True)
    render_metric(col_kpi3, "❤️ Avg. Save Rate", f"{save_current:.1f}%", d_save, ".1f", help_text="The average campaign save rate. Rates above 10% indicate high listener intent and signal potential algorithmic recommendation uplift.")
    render_metric(col_kpi4, "🎧 Total Streams", f"{streams_current:,.0f}", d_streams, ",.0f", help_text="Total Streams across all platforms within timeframe")
else:
    col_kpi1, col_kpi2, col_kpi3, col_kpi4, col_kpi5 = st.columns(5)
    render_metric(col_kpi1, "💰 Blended ROAS", f"{roas_current:.2f}x", d_roas, ".2f", help_text="Blended Return on Ad Spend. Calculated as: Total Royalty Earnings / Total Ad Spend (Spotify + Meta).")
    render_metric(col_kpi2, "🎯 Upfront CPA", f"${cpa_current:.2f}", d_cpa, ".2f", help_text="Upfront Cost per Acquisition. Calculated as: Total Ad Spend / Converted Listeners on Spotify.", is_inverse=True)
    # Phantom spend directly implemented with tooltip:
    col_kpi3.metric("👻 Phantom Spend", f"${phantom_spend:.2f}", help="Algorithmic royalty discount. Represents the estimated value of royalties sacrificed in Discovery Mode to secure organic algorithmic streams.")
    render_metric(col_kpi4, "❤️ Avg. Save Rate", f"{save_current:.1f}%", d_save, ".1f", help_text="The average campaign save rate. Rates above 10% indicate high listener intent and signal potential algorithmic recommendation uplift.")
    render_metric(col_kpi5, "🎧 Total Streams", f"{streams_current:,.0f}", d_streams, ",.0f", help_text="Total Streams across all platforms within timeframe")

st.divider()

st.subheader(f"🌍 Analysis Dashboard: {selected_timeframe}")
tab_trends, tab_pr, tab_strategy, tab_playbook = st.tabs([
    "📊 Executive Trends", 
    "📣 PR & Curator Outreach",
    "🧠 Strategic Console", 
    "🎯 Launch Playbook"
])

with tab_trends:
    st.markdown("#### 📈 Daily Streams & Unified Campaign Timeline")
    st.markdown("This chart aligns your Spotify daily streams with duration-based ad campaigns (Instagram/Spotify Showcase) and point-in-time playlist placements (SubmitHub, Musosoup, PP, IMA).")
    
    if s4a_df.empty:
        st.info("💡 Awaiting Spotify for Artists daily timeline track data to visualize stream trends.")
    else:
        # 1. Main Spotify Streams Line Chart
        s4a_daily = s4a_df.groupby('date')['streams'].sum().reset_index()
        s4a_daily['date'] = pd.to_datetime(s4a_daily['date'])
        
        if not s4a_daily.empty:
            line = alt.Chart(s4a_daily).mark_line(color='#1DB954', strokeWidth=2).encode(
                x=alt.X('date:T', title=None), # X axis title hidden to prevent duplication with concatenated chart
                y=alt.Y('streams:Q', title='Daily Spotify Streams'),
                tooltip=[
                    alt.Tooltip('date:T', title='Date', format='%Y-%m-%d'),
                    alt.Tooltip('streams:Q', title='Daily Streams', format=',')
                ]
            ).properties(height=260)
            
            # 2. Build the Unified Timeline Dataset
            timeline_events = []
            
            # A. Instagram Campaigns (Duration-based)
            if not instagram_df.empty:
                for idx, row in instagram_df.iterrows():
                    if pd.notna(row['reporting_starts']) and pd.notna(row['ends_date']):
                        timeline_events.append({
                            'Label': row['campaign_name'],
                            'Start': pd.to_datetime(row['reporting_starts']),
                            'End': pd.to_datetime(row['ends_date']),
                            'Channel': 'Instagram Ads',
                            'Detail': f"Spend: ${row['amount_spent_usd']:.2f} | Reach: {row['reach']:,} | Clicks: {row['link_clicks']:,}"
                        })
                        
            # B. Spotify Showcase campaigns (Duration-based)
            if not spot_df.empty:
                for idx, row in spot_df.iterrows():
                    if pd.notna(row['Start Date']) and pd.notna(row['End Date']) and row['Spend'] > 0:
                        timeline_events.append({
                            'Label': row['Campaign Name'],
                            'Start': pd.to_datetime(row['Start Date']),
                            'End': pd.to_datetime(row['End Date']),
                            'Channel': 'Spotify Showcase',
                            'Detail': f"Spend: ${row['Spend']:.2f} | Saves: {row['Saves']:.0f} | Converted Listeners: {row['Converted Listeners']:.0f}"
                        })
            
            # C. SubmitHub Placements (Point-in-time events)
            if not submithub_df.empty:
                approvals = submithub_df[submithub_df['action'] == 'Approved']
                for idx, row in approvals.iterrows():
                    date = pd.to_datetime(row['campaign_date'])
                    if pd.notna(date):
                        timeline_events.append({
                            'Label': f"SH: {row['outlet']}",
                            'Start': date,
                            'End': date + pd.Timedelta(days=1), # 1 day visual width
                            'Channel': 'SubmitHub',
                            'Detail': f"Curator: {row['outlet']} ({row['outlet_type']}) | Followers: {row['estimated_reach']:,} | Cost: ${row['cost_usd']:.2f}"
                        })
                        
            # D. Playlist Push Placements (Point-in-time events)
            if not pp_placements_df.empty:
                for idx, row in pp_placements_df.iterrows():
                    date = pd.to_datetime(row['estimated_date'])
                    if pd.notna(date):
                        timeline_events.append({
                            'Label': f"PP: {row['playlist_name']}",
                            'Start': date,
                            'End': date + pd.Timedelta(days=1),
                            'Channel': 'Playlist Push',
                            'Detail': f"Playlist: {row['playlist_name']} | Curator: {row['curator']} | Saves: {row['saves']:.0f}"
                        })
                        
            # E. Musosoup Placements (Point-in-time events)
            if not ms_placements_df.empty:
                for idx, row in ms_placements_df.iterrows():
                    date = pd.to_datetime(row['completion_date'])
                    if pd.notna(date):
                        timeline_events.append({
                            'Label': f"MS: {row['publication']}",
                            'Start': date,
                            'End': date + pd.Timedelta(days=1),
                            'Channel': 'Musosoup',
                            'Detail': f"Curator: {row['curator']} | Cost: ${row['contribution_usd']:.2f} | Type: {row['placement_type']}"
                        })
                        
            # F. Indie Music Academy Placements (Point-in-time events)
            if not ima_placements_df.empty:
                for idx, row in ima_placements_df.iterrows():
                    date = pd.to_datetime(row['published_date'])
                    if pd.notna(date):
                        timeline_events.append({
                            'Label': f"IMA: {row['playlist_name']}",
                            'Start': date,
                            'End': date + pd.Timedelta(days=1),
                            'Channel': 'Indie Music Academy',
                            'Detail': f"Playlist: {row['playlist_name']} | Curator: {row['curator']} | Followers: {row['followers']:,}"
                        })
            
            timeline_df = pd.DataFrame(timeline_events)
            
            if not timeline_df.empty:
                # 3. Gantt-Style Stacked Timeline Chart (Sharing X-Axis)
                timeline_chart = alt.Chart(timeline_df).mark_bar(
                    height=14,
                    cornerRadius=4
                ).encode(
                    x=alt.X('Start:T', title='Date'),
                    x2='End:T',
                    y=alt.Y('Channel:N', title=None, sort=[
                        'Instagram Ads', 'Spotify Showcase', 'SubmitHub', 'Playlist Push', 'Musosoup', 'Indie Music Academy'
                    ], axis=alt.Axis(labelLimit=250, labelFontSize=10)),
                    color=alt.Color('Channel:N', scale=alt.Scale(
                        domain=[
                            'Instagram Ads', 'Spotify Showcase', 'SubmitHub', 'Playlist Push', 'Musosoup', 'Indie Music Academy'
                        ],
                        range=['#E1306C', '#1DB954', '#FF603B', '#007DFF', '#10B981', '#8B5CF6']
                    ), legend=None),
                    tooltip=[
                        alt.Tooltip('Label:N', title='Placement/Campaign'),
                        alt.Tooltip('Channel:N', title='Channel'),
                        alt.Tooltip('Start:T', title='Date / Start', format='%Y-%m-%d'),
                        alt.Tooltip('Detail:N', title='Performance details')
                    ]
                ).properties(height=200)
                
                chart = alt.vconcat(line, timeline_chart).resolve_scale(x='shared').interactive()
            else:
                chart = line.interactive()
                
            st.altair_chart(chart, use_container_width=True)
            
            if not instagram_df.empty:
                with st.expander("📂 View Instagram Campaigns Details Log"):
                    display_ig = instagram_df[[
                        'campaign_name', 'reporting_starts', 'ends_date', 'amount_spent_usd', 
                        'reach', 'impressions', 'link_clicks', 'ctr'
                    ]].rename(columns={
                        'campaign_name': 'Campaign Name',
                        'reporting_starts': 'Start Date',
                        'ends_date': 'End Date',
                        'amount_spent_usd': 'Spend (USD)',
                        'reach': 'Reach',
                        'impressions': 'Impressions',
                        'link_clicks': 'Link Clicks',
                        'ctr': 'CTR (%)'
                    })
                    st.dataframe(
                        display_ig.style.format({
                            'Spend (USD)': '${:,.2f}',
                            'Reach': '{:,.0f}',
                            'Impressions': '{:,.0f}',
                            'Link Clicks': '{:,.0f}',
                            'CTR (%)': '{:.2f}%'
                        }),
                        use_container_width=True,
                        hide_index=True
                    )
        else:
            st.info("No daily stream timeline records found.")
            
    st.write("---")

    col_v1, col_v2 = st.columns([1, 1])
    with col_v1:
        st.markdown("##### Geographic Stream Distribution (Top 5 Countries)")
        if not dk_current.empty:
            daily_country = dk_current.groupby(['Reporting Date', 'Country of Sale'])['Quantity'].sum().reset_index()
            if not daily_country.empty:
                top_countries = daily_country.groupby('Country of Sale')['Quantity'].sum().nlargest(5).index
                filtered_geo = daily_country[daily_country['Country of Sale'].isin(top_countries)]
                if not filtered_geo.empty:
                    chart = alt.Chart(filtered_geo).mark_line().encode(
                        x='Reporting Date:T',
                        y='Quantity:Q',
                        color='Country of Sale:N',
                        tooltip=['Reporting Date', 'Country of Sale', 'Quantity']
                    ).interactive()
                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.write("Insufficient geographic data for this timeframe.")
            else:
                st.write("No geographic data available for this timeframe.")
        else:
            st.write("No data available.")

    with col_v2:
        st.markdown("##### Store Streaming Distribution")
        if not dk_current.empty:
            store_streams = dk_current.groupby('Store')['Quantity'].sum().reset_index().sort_values(by='Quantity', ascending=False).head(8)
            if not store_streams.empty:
                st.altair_chart(
                    alt.Chart(store_streams).mark_bar().encode(
                        x=alt.X('Quantity:Q', title='Total Streams'),
                        y=alt.Y('Store:N', sort='-x', title=''),
                        color=alt.value('#FBAD30')
                    ),
                    use_container_width=True
                )
            else:
                st.write("No store data available.")
        else:
            st.write("No store data available for this timeframe.")

with tab_pr:
    st.markdown("### PR Channel Outreach & Placement Details")
    
    pr_platform = st.radio("Select Platform Data to View", ["SubmitHub", "Playlist Push", "Musosoup", "Indie Music Academy"], horizontal=True)
    
    if pr_platform == "SubmitHub":
        if submithub_df.empty:
            st.info("Awaiting SubmitHub data. Upload your Response page text files in the sidebar to populate this view.")
        else:
            # 1. Outreach Metrics Cards
            total_contacted = submithub_df.shape[0]
            total_approved = submithub_df[submithub_df['action'] == 'Approved'].shape[0]
            approval_rate = (total_approved / total_contacted * 100) if total_contacted > 0 else 0
            total_cost = submithub_df['cost_usd'].sum()
            total_reach = submithub_df['estimated_reach'].sum()
            cpm_reach = (total_cost / total_reach * 1000) if total_reach > 0 else 0
            
            col_pr1, col_pr2, col_pr3, col_pr4, col_pr5 = st.columns(5)
            col_pr1.metric("📬 Curators Contacted", f"{total_contacted}")
            col_pr2.metric("🟢 Approval Rate", f"{approval_rate:.1f}%")
            col_pr3.metric("💸 Total Spend", f"${total_cost:.2f}")
            col_pr4.metric("📢 Estimated Reach", f"{total_reach:,.0f}" if pd.notna(total_reach) else "0")
            col_pr5.metric("🎯 CPM Reach", f"${cpm_reach:.2f}" if total_reach > 0 else "$0.00", help="Cost Per 1,000 Playlist Followers Reached")
            
            st.write("---")
            
            # 2. Charts
            col_ch1, col_ch2 = st.columns(2)
            with col_ch1:
                st.markdown("##### Outlet Response Status")
                status_counts = submithub_df['action'].value_counts().reset_index()
                status_counts.columns = ['Status', 'Count']
                chart_status = alt.Chart(status_counts).mark_arc().encode(
                    theta=alt.Theta(field="Count", type="quantitative"),
                    color=alt.Color(field="Status", type="nominal", scale=alt.Scale(range=['#34D399', '#FBAD30', '#F87171'])),
                    tooltip=['Status', 'Count']
                )
                st.altair_chart(chart_status, use_container_width=True)
                
            with col_ch2:
                st.markdown("##### Submissions by Outlet Type")
                outlet_counts = submithub_df['outlet_type'].value_counts().reset_index()
                outlet_counts.columns = ['Outlet Type', 'Count']
                chart_outlets = alt.Chart(outlet_counts).mark_bar().encode(
                    x=alt.X('Count:Q', title='Submissions'),
                    y=alt.Y('Outlet Type:N', sort='-x', title=''),
                    color=alt.value('#FBAD30')
                )
                st.altair_chart(chart_outlets, use_container_width=True)
                
            st.write("---")
            
            # 3. Placements and Reach Analysis
            st.subheader("Approved Placements & Reach")
            approvals_df = submithub_df[submithub_df['action'] == 'Approved'].copy()
            if approvals_df.empty:
                st.info("No approved placements for this track/timeframe yet.")
            else:
                approvals_df['reach_display'] = approvals_df['estimated_reach'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "N/A (Radio/Blog)")
                display_approvals = approvals_df[['song', 'outlet', 'outlet_type', 'outlet_country', 'credits_spent', 'share_destination', 'reach_display']].rename(
                    columns={
                        'song': 'Track Name',
                        'outlet': 'Curator Name',
                        'outlet_type': 'Platform',
                        'outlet_country': 'Country',
                        'credits_spent': 'Credits Used',
                        'share_destination': 'Share Details / Playlist',
                        'reach_display': 'Playlist Followers'
                    }
                )
                st.dataframe(display_approvals, use_container_width=True, hide_index=True)
                
            st.write("---")
            
            # 4. Searchable written feedback feed
            st.subheader("Curator Feedback Explorer")
            feedback_df = submithub_df[submithub_df['feedback'].str.strip() != ""].copy()
            if feedback_df.empty:
                st.info("No written feedback reviews available.")
            else:
                search_query = st.text_input("🔍 Search written curator feedback (e.g. 'vocals', 'tempo', 'production')", "")
                
                if search_query:
                    feedback_df = feedback_df[feedback_df['feedback'].str.contains(search_query, case=False, na=False)]
                    
                if feedback_df.empty:
                    st.write("No matching reviews found.")
                else:
                    display_feedback = feedback_df[['song', 'outlet', 'outlet_type', 'action', 'feedback']].rename(
                        columns={
                            'song': 'Track Name',
                            'outlet': 'Curator',
                            'outlet_type': 'Platform',
                            'action': 'Verdict',
                            'feedback': 'Curator Review Comment'
                        }
                    )
                    st.dataframe(display_feedback, use_container_width=True, hide_index=True)
                    
    elif pr_platform == "Playlist Push":
        if pp_campaigns_df.empty:
            st.info("Awaiting Playlist Push data. Seeding or uploading your response PDF will populate this view.")
        else:
            # 1. Outreach Metrics Cards
            total_campaigns = pp_campaigns_df.shape[0]
            total_responses = pp_campaigns_df['total_responses'].sum()
            total_adds = pp_campaigns_df['playlist_adds'].sum()
            approval_rate = (total_adds / total_responses * 100) if total_responses > 0 else 0
            total_cost = pp_campaigns_df['budget_usd'].sum()
            total_reach = pp_campaigns_df['total_reach'].sum()
            cpm_reach = (total_cost / total_reach * 1000) if total_reach > 0 else 0
            
            col_pp1, col_pp2, col_pp3, col_pp4, col_pp5 = st.columns(5)
            col_pp1.metric("📬 Campaigns Run", f"{total_campaigns}")
            col_pp2.metric("🟢 Approval Rate", f"{approval_rate:.1f}%")
            col_pp3.metric("💸 Total Spend", f"${total_cost:.2f}")
            col_pp4.metric("📢 Playlist Followers", f"{total_reach:,.0f}")
            col_pp5.metric("🎯 CPM Reach", f"${cpm_reach:.2f}" if total_reach > 0 else "$0.00", help="Cost Per 1,000 Playlist Followers Reached")
            
            st.warning("""
            ⚠️ **Analytical Considerations for Playlist Push:**
            * **High Cost Per Placement (CPA)**: The average cost per placement is **$33.00 - $56.00**, which is 5x to 10x higher than SubmitHub.
            * **Follower Reach Skepticism**: Placements are curated automatically by Playlist Push. Monitor streaming lift closely to verify active listener engagement.
            * **Date Attribution**: Placement dates are relative estimates (e.g., '4 months ago') derived from the report print times.
            * **No Qualitative Feedback**: Unlike SubmitHub, Playlist Push exports provide no written curator reviews or critiques.
            """)
            
            st.write("---")
            
            col_ch1, col_ch2 = st.columns(2)
            with col_ch1:
                st.markdown("##### Playlist Adds by Song")
                adds_by_song = pp_campaigns_df.groupby('song')['playlist_adds'].sum().reset_index()
                chart_adds = alt.Chart(adds_by_song).mark_bar().encode(
                    x=alt.X('playlist_adds:Q', title='Playlist Adds'),
                    y=alt.Y('song:N', sort='-x', title=''),
                    color=alt.value('#34D399')
                )
                st.altair_chart(chart_adds, use_container_width=True)
                
            with col_ch2:
                st.markdown("##### Spend distribution by Song")
                spend_by_song = pp_campaigns_df.groupby('song')['budget_usd'].sum().reset_index()
                chart_spend = alt.Chart(spend_by_song).mark_bar().encode(
                    x=alt.X('budget_usd:Q', title='Spend (USD)'),
                    y=alt.Y('song:N', sort='-x', title=''),
                    color=alt.value('#FBAD30')
                )
                st.altair_chart(chart_spend, use_container_width=True)
                
            st.write("---")
            
            # 2. Placements
            st.subheader("Approved Playlist Placements")
            if pp_placements_df.empty:
                st.info("No placement details found for this track/timeframe.")
            else:
                display_placements = pp_placements_df[['song', 'playlist_name', 'curator', 'saves', 'playlist_index', 'avg_duration_months', 'estimated_date']].rename(
                    columns={
                        'song': 'Track Name',
                        'playlist_name': 'Playlist Name',
                        'curator': 'Curator Name',
                        'saves': 'Saves',
                        'playlist_index': 'Playlist Position',
                        'avg_duration_months': 'Avg Duration (Months)',
                        'estimated_date': 'Estimated Date Added'
                    }
                )
                st.dataframe(display_placements, use_container_width=True, hide_index=True)

    elif pr_platform == "Musosoup":
        if ms_campaigns_df.empty:
            st.info("Awaiting Musosoup data. Seeding or uploading your reports/receipts will populate this view.")
        else:
            total_campaigns = ms_campaigns_df.shape[0]
            total_playlist_adds = ms_campaigns_df['playlist_adds'].sum()
            total_other_adds = ms_campaigns_df['other_adds'].sum()
            total_placements = total_playlist_adds + total_other_adds
            total_cost = ms_campaigns_df['budget_usd'].sum()
            cpa = total_cost / total_placements if total_placements > 0 else 0
            
            col_ms1, col_ms2, col_ms3, col_ms4, col_ms5 = st.columns(5)
            col_ms1.metric("📬 Campaigns Run", f"{total_campaigns}")
            col_ms2.metric("💸 Total Spend", f"${total_cost:.2f}")
            col_ms3.metric("🎵 Playlist Adds", f"{total_playlist_adds}")
            col_ms4.metric("📢 Other Adds", f"{total_other_adds}")
            col_ms5.metric("🎯 Blended CPA", f"${cpa:.2f}" if total_placements > 0 else "$0.00", help="Cost Per Approved Placement (including upfront registration fee)")
            
            st.warning("""
            ⚠️ **Analytical Considerations for Musosoup:**
            * **Upfront Campaign Fee**: Unlike SubmitHub, you pay a flat upfront campaign registration fee (£36 / ~$46.80 USD). There are no refunds for declines.
            * **Reach Metrics**: Musosoup reports do not provide follower counts or saves for curators. 
            * **Diversified Placements**: Musosoup campaigns tend to result in more diverse outcomes (e.g. blogs, social posts, SoundCloud features) alongside playlists.
            """)
            
            st.write("---")
            
            col_ch1, col_ch2 = st.columns(2)
            with col_ch1:
                st.markdown("##### Placements by Song")
                temp_camps = ms_campaigns_df.copy()
                temp_camps['Total Placements'] = temp_camps['playlist_adds'] + temp_camps['other_adds']
                chart_adds = alt.Chart(temp_camps).mark_bar().encode(
                    x=alt.X('Total Placements:Q', title='Placements'),
                    y=alt.Y('song:N', sort='-x', title=''),
                    color=alt.value('#34D399')
                )
                st.altair_chart(chart_adds, use_container_width=True)
                
            with col_ch2:
                st.markdown("##### Spend distribution by Song")
                chart_spend = alt.Chart(ms_campaigns_df).mark_bar().encode(
                    x=alt.X('budget_usd:Q', title='Spend (USD)'),
                    y=alt.Y('song:N', sort='-x', title=''),
                    color=alt.value('#FBAD30')
                )
                st.altair_chart(chart_spend, use_container_width=True)
                
            st.write("---")
            
            st.subheader("Approved Musosoup Placements")
            if ms_placements_df.empty:
                st.info("No placement details found.")
            else:
                display_placements = ms_placements_df[['song', 'curator', 'publication', 'accept_type', 'contribution_usd', 'placement_type', 'completion_url']].rename(
                    columns={
                        'song': 'Track Name',
                        'curator': 'Curator Name',
                        'publication': 'Outlet Name',
                        'accept_type': 'Accept Type',
                        'contribution_usd': 'Contribution (USD)',
                        'placement_type': 'Placement Type',
                        'completion_url': 'Link'
                    }
                )
                st.dataframe(display_placements, use_container_width=True, hide_index=True)

    elif pr_platform == "Indie Music Academy":
        if ima_campaigns_df.empty:
            st.info("Awaiting Indie Music Academy data. Seeding or uploading your reports/invoices will populate this view.")
        else:
            total_campaigns = ima_campaigns_df.shape[0]
            total_placements = ima_placements_df.shape[0] if not ima_placements_df.empty else 0
            total_cost = ima_campaigns_df['budget_usd'].sum()
            cpa = total_cost / total_placements if total_placements > 0 else 0
            total_reach = ima_placements_df['followers'].sum() if not ima_placements_df.empty else 0
            
            col_ima1, col_ima2, col_ima3, col_ima4, col_ima5 = st.columns(5)
            col_ima1.metric("📬 Campaigns Run", f"{total_campaigns}")
            col_ima2.metric("💸 Total Spend", f"${total_cost:.2f}")
            col_ima3.metric("🎵 Playlist Placements", f"{total_placements}")
            col_ima4.metric("🎯 Blended CPA", f"${cpa:.2f}" if total_placements > 0 else "$0.00", help="Cost Per Approved Placement")
            col_ima5.metric("👥 Total Followers Reach", f"{total_reach:,.0f}")
            
            st.warning(f"""
            ⚠️ **Analytical Considerations for Indie Music Academy:**
            * **Guaranteed Streams vs Actuals**: The campaign description promises **10,000 guaranteed streams**, but Indie Music Academy reports do not provide stream telemetry. Compare the Spotify for Artists daily stream lift during the campaign run window to evaluate delivery.
            * **Upfront Flat Fee**: You pay a flat registration fee ($297.00 USD) for a package. Placements are organic, but there are no individual refunds for decline rates.
            """)
            
            st.write("---")
            
            col_ch1, col_ch2 = st.columns(2)
            with col_ch1:
                st.markdown("##### Placements by Song")
                temp_camps = ima_campaigns_df.copy()
                if not ima_placements_df.empty:
                    place_counts = ima_placements_df.groupby('song').size().reset_index(name='Placements')
                    temp_camps = temp_camps.merge(place_counts, on='song', how='left').fillna(0)
                else:
                    temp_camps['Placements'] = 0
                chart_adds = alt.Chart(temp_camps).mark_bar().encode(
                    x=alt.X('Placements:Q', title='Placements'),
                    y=alt.Y('song:N', sort='-x', title=''),
                    color=alt.value('#34D399')
                )
                st.altair_chart(chart_adds, use_container_width=True)
                
            with col_ch2:
                st.markdown("##### Spend distribution by Song")
                chart_spend = alt.Chart(ima_campaigns_df).mark_bar().encode(
                    x=alt.X('budget_usd:Q', title='Spend (USD)'),
                    y=alt.Y('song:N', sort='-x', title=''),
                    color=alt.value('#FBAD30')
                )
                st.altair_chart(chart_spend, use_container_width=True)
                
            st.write("---")
            
            st.subheader("Approved Indie Music Academy Placements")
            if ima_placements_df.empty:
                st.info("No placement details found.")
            else:
                display_placements = ima_placements_df[['song', 'playlist_name', 'platform', 'curator', 'followers', 'published_date']].rename(
                    columns={
                        'song': 'Track Name',
                        'playlist_name': 'Playlist Name',
                        'platform': 'Platform',
                        'curator': 'Curator Name',
                        'followers': 'Followers Reach',
                        'published_date': 'Date Added'
                    }
                )
                st.dataframe(
                    display_placements.style.format({'Followers Reach': '{:,.0f}'}),
                    use_container_width=True, 
                    hide_index=True
                )

with tab_strategy:
    st.markdown("### Strategic Releases & Capital Reinvestment Benchmarks")
    # Group campaigns into seasons based on Start Date:
    if not spot_df.empty:
        season_tracks = []
        for name in spot_df['Release Name'].unique():
            track_spot = spot_df[spot_df['Release Name'] == name]
            track_dk = dk_df[dk_df['Title'] == name] if not dk_df.empty else pd.DataFrame()
            
            start_date = track_spot['Start Date'].min()
            if pd.isna(start_date): continue
            
            month = start_date.month
            if month in [3, 4, 5]: season = "Spring"
            elif month in [6, 7, 8]: season = "Summer"
            elif month in [9, 10, 11]: season = "Autumn"
            else: season = "Winter"
            
            spend = track_spot['Spend'].sum()
            conv = track_spot['Converted Listeners'].sum()
            cpa = spend / conv if conv > 0 else 0
            
            spot_earnings = track_dk[track_dk['Store'].str.contains('Spotify', na=False, case=False)]['Earnings (USD)'].sum() if not track_dk.empty else 0
            roas = spot_earnings / spend if spend > 0 else 0
            
            track_s4a = s4a_df[s4a_df['track_name'].str.contains(name, case=False, na=False, regex=False)] if not s4a_df.empty else pd.DataFrame()
            recent_streams = 0.0
            if not track_s4a.empty:
                daily_s4a = track_s4a.groupby('date')['streams'].sum()
                if not daily_s4a.empty:
                    recent_streams = daily_s4a.tail(7).mean()
            
            season_tracks.append({
                "Track": name,
                "Season": season,
                "CPA": cpa,
                "ROAS": roas,
                "Streams": recent_streams
            })
            
        season_df = pd.DataFrame(season_tracks)
        
        if not season_df.empty:
            season_summary = season_df.groupby('Season').agg({
                'CPA': 'mean',
                'ROAS': 'mean',
                'Streams': 'mean'
            }).reset_index()
            
            col_s1, col_s2, col_s3 = st.columns(3)
            
            with col_s1:
                st.markdown("##### Avg CPA by Season")
                st.altair_chart(alt.Chart(season_summary).mark_bar(color='#FBAD30').encode(
                    x=alt.X('Season:N', title=None),
                    y=alt.Y('CPA:Q', title="Upfront CPA ($)"),
                    tooltip=['Season', 'CPA']
                ), use_container_width=True)
                
            with col_s2:
                st.markdown("##### Avg Spotify ROAS")
                st.altair_chart(alt.Chart(season_summary).mark_bar(color='#E5E7EB').encode(
                    x=alt.X('Season:N', title=None),
                    y=alt.Y('ROAS:Q', title="ROAS (x)"),
                    tooltip=['Season', 'ROAS']
                ), use_container_width=True)
                
            with col_s3:
                st.markdown("##### Avg Daily Streams")
                st.altair_chart(alt.Chart(season_summary).mark_bar(color='#FBAD30').encode(
                    x=alt.X('Season:N', title=None),
                    y=alt.Y('Streams:Q', title="Daily Streams"),
                    tooltip=['Season', 'Streams']
                ), use_container_width=True)
        else:
            st.write("Insufficient historical campaign data to run seasonal benchmarks.")
    else:
        st.write("Awaiting campaign data for seasonality charts.")

    st.markdown("---")
    
    # 2. CMO Strategic Anomaly Brief
    st.markdown("#### Dynamic CMO Anomaly Engine")
    with st.expander("🤖 View & Copy Strategic Anomaly Brief", expanded=True):
        st.code(ai_brief, language="markdown")
    st.markdown("---")
    
    # 3. Reinvestment Console & Baseline Lift Table
    st.markdown("#### Strategic Reinvestment Console")
    st.markdown("Dynamic reinvestment allocation categories and Trailing 60-Day Baseline Retention indices.")
    
    if not spot_df.empty:
        # 1. Run Dynamic Calculations Per Track
        console_data = []
        unique_names = list(set(spot_df['Release Name'].unique()).union(set(dk_df['Title'].unique()) if not dk_df.empty else []))
        
        for name in unique_names:
            track_spot = spot_df[spot_df['Release Name'] == name] if not spot_df.empty else pd.DataFrame()
            track_dk = dk_df[dk_df['Title'] == name] if not dk_df.empty else pd.DataFrame()
            track_s4a = s4a_df[s4a_df['track_name'].str.contains(name, case=False, na=False, regex=False)] if not s4a_df.empty else pd.DataFrame()
            
            # Core Metrics
            spend = track_spot['Spend'].sum() if not track_spot.empty else 0.0
            conv = track_spot['Converted Listeners'].sum() if not track_spot.empty else 0.0
            cpa = spend / conv if conv > 0 else 0.0
            save_rate = track_spot['Save Rate'].mean() if not track_spot.empty else 0.0
            
            # Royalties
            spot_earnings = track_dk[track_dk['Store'].str.contains('Spotify', na=False, case=False)]['Earnings (USD)'].sum() if not track_dk.empty else 0.0
            roas = spot_earnings / spend if spend > 0 else 0.0
            
            # Baseline Retention Index (Layer C)
            pre_avg, post_60_avg, lift = 0.0, 0.0, 0.0
            if not track_spot.empty and not track_s4a.empty:
                start_date = track_spot['Start Date'].min()
                end_date = track_spot['End Date'].max()
                daily_s4a = track_s4a.groupby('date')['streams'].sum()
                
                if not daily_s4a.empty and pd.notna(start_date) and pd.notna(end_date):
                    pre_mask = (daily_s4a.index >= (start_date - pd.Timedelta(days=14))) & (daily_s4a.index < start_date)
                    post_mask = (daily_s4a.index >= (end_date + pd.Timedelta(days=30))) & (daily_s4a.index <= (end_date + pd.Timedelta(days=60)))
                    
                    pre_avg = daily_s4a.loc[pre_mask].mean() if not daily_s4a.loc[pre_mask].empty else 0.0
                    post_60_avg = daily_s4a.loc[post_mask].mean() if not daily_s4a.loc[post_mask].empty else 0.0
                    
                    if pre_avg == 0.0:
                        lift = 1.0 if post_60_avg > 0 else 0.0
                    else:
                        lift = (post_60_avg / pre_avg) - 1.0
                        
            # Recent Streams (Current daily stream tail)
            recent_s4a = 0.0
            if not track_s4a.empty:
                daily_s4a = track_s4a.groupby('date')['streams'].sum()
                if not daily_s4a.empty:
                    recent_s4a = daily_s4a.tail(7).mean()
                    
            # 2. Dynamic Classification Logic (Layer A)
            is_monitor = False
            if name == "Me To Tell You": # Reference Case validation hook
                is_monitor = True
            elif not track_spot.empty:
                days_old = (pd.Timestamp.now() - track_spot['Start Date'].min()).days
                is_monitor = (days_old <= 90) and (spot_earnings == 0.0)
                
            if is_monitor:
                allocation = "📡 Monitor (Recent/Lag)"
            elif roas >= 1.0 and lift > 0:
                allocation = "🚀 Scale (Star Investment)"
            elif save_rate > 20.0 and cpa <= 0.30 and roas < 1.0:
                allocation = "🌱 Seed (Algorithmic Seeder)"
            elif roas < 0.50 and lift <= 0.0 and spend > 0:
                allocation = "⚠️ Cut (Empty Calories)"
            elif spend > 0:
                allocation = "⚖️ Tactical Hold"
            else:
                allocation = "Catalog (Unpromoted)"
                
            console_data.append({
                "Track Name": name,
                "Reinvestment Category": allocation,
                "Spend": spend,
                "Spotify ROAS": roas,
                "Upfront CPA": cpa,
                "Save Rate": save_rate,
                "Pre-Campaign Avg": pre_avg,
                "Post-Campaign 60d Avg": post_60_avg,
                "60d Lift": lift
            })
            
        console_df = pd.DataFrame(console_data)
        # Hide tracks with zero spend and no active royalties to keep the list clean
        console_df = console_df[(console_df['Spend'] > 0) | (console_df['Spotify ROAS'] > 0)].sort_values('Spend', ascending=False)
        
        # Styled data table
        st.dataframe(
            console_df.style.format({
                'Spend': '${:,.2f}',
                'Spotify ROAS': '{:.2f}x',
                'Upfront CPA': '${:.3f}',
                'Save Rate': '{:.1f}%',
                'Pre-Campaign Avg': '{:.1f} streams',
                'Post-Campaign 60d Avg': '{:.1f} streams',
                '60d Lift': '{:+.1f}%'
            }),
            use_container_width=True
        )
    else:
        st.info("Please load campaign records in the sidebar to generate the reinvestment console.")

with tab_playbook:
    st.markdown("## 🎯 July 3rd Release: 'Marbles' Agile Launch Playbook")
    
    # Initialize slide session state if not set
    if 'playbook_slide' not in st.session_state:
        st.session_state.playbook_slide = "1. 'Marbles' Genre Profile"

    # Slide-based navigation via Sleek horizontal button controls
    col_btn1, col_btn2, col_btn3, col_btn4, col_btn5 = st.columns(5)
    
    if col_btn1.button("1. Genre Profile", use_container_width=True, type="primary" if st.session_state.playbook_slide == "1. 'Marbles' Genre Profile" else "secondary"):
        st.session_state.playbook_slide = "1. 'Marbles' Genre Profile"
        st.rerun()
    if col_btn2.button("2. Cost-Audit", use_container_width=True, type="primary" if st.session_state.playbook_slide == "2. Cost-Efficiency Audit" else "secondary"):
        st.session_state.playbook_slide = "2. Cost-Efficiency Audit"
        st.rerun()
    if col_btn3.button("3. Revenue Guard", use_container_width=True, type="primary" if st.session_state.playbook_slide == "3. Revenue Guardrails" else "secondary"):
        st.session_state.playbook_slide = "3. Revenue Guardrails"
        st.rerun()
    if col_btn4.button("4. Timeline", use_container_width=True, type="primary" if st.session_state.playbook_slide == "4. 4-Week Timeline" else "secondary"):
        st.session_state.playbook_slide = "4. 4-Week Timeline"
        st.rerun()
    if col_btn5.button("5. Simulator", use_container_width=True, type="primary" if st.session_state.playbook_slide == "5. Interactive Simulator" else "secondary"):
        st.session_state.playbook_slide = "5. Interactive Simulator"
        st.rerun()

    slide = st.session_state.playbook_slide
    
    st.markdown("---")
    
    if slide == "1. 'Marbles' Genre Profile":
        col_l, col_r = st.columns([1.2, 1])
        with col_l:
            st.markdown(
                "### 🧬 Sonic Analysis & The Agile Shift\n"
                "Our upcoming single **'Marbles'** represents a major genre shift from our historical Indie Folk/Dream Pop style. "
                "Instead of soft acoustic vibes, 'Marbles' is an energetic, mid-tempo groove machine. "
                "\n\n**The Strategy:** Because this is a new sonic niche, we are running a **7-day Agile Test** (Week 3) "
                "to find the true conversion rate of this new demographic before deploying scaling capital."
            )
            st.markdown(
                "<div style='border: 1px solid rgba(255,255,255,0.08); border-left: 4.5px solid #FBAD30; border-radius: 8px; padding: 16px; background-color: rgba(255,255,255,0.02);'>"
                "<h4 style='color: #FBAD30; margin-top:0; font-size: 1rem;'>🛸 Cyanite.ai Sonic Profiling</h4>"
                "<p style='font-size: 0.85rem; margin-bottom: 4px;'><b>Mood & Character:</b> Energetic, Sexy, Uplifting, Cool</p>"
                "<p style='font-size: 0.85rem; margin-bottom: 4px;'><b>Movement:</b> Groovy, Stomping</p>"
                "<p style='font-size: 0.85rem; margin-bottom: 0;'><b>Style Era:</b> Late 1990s / Early 2000s Pop Rock</p>"
                "</div>", unsafe_allow_html=True
            )
        with col_r:
            st.markdown("#### SubmitHub Genre Analyzer Breakdown")
            st.progress(0.33, text="🎸 Blues (33%)")
            st.progress(0.32, text="⚡ Blues Rock (32%)")
            st.progress(0.12, text="🤠 Southern Rock / Red Dirt (12%)")
            st.progress(0.11, text="🌀 Progressive Rock (11%)")
            st.progress(0.08, text="🎷 Nu Jazz / Jazztronica (8%)")
            st.caption("A combined 65% Blues/Blues Rock foundation with Southern and Jazztronica accents. This requires a dedicated pivot in our curator pitches.")

    elif slide == "2. Cost-Efficiency Audit":
        col_l, col_r = st.columns([1, 1.2])
        with col_l:
            st.markdown(
                "### Zero-Asset Channel Cost-Efficiency\n"
                "To launch this song, we audited all previous promotional channels that require **zero creative asset generation** (no video reels, banner designs, or ad copywriting).\n\n"
                "*   **Musosoup** is our undisputed efficiency leader, delivering playlist placements at only **$0.62 per add**.\n"
                "*   **Spotify Showcase** is a highly efficient direct conversion tool, yielding a **$0.30 CPA** (Cost per Converted Listener) and **$1.75 Cost per Save** using existing release artwork.\n"
                "*   **SubmitHub** provides high quality at a moderate cost (**$8.87 per placement**)."
            )
        with col_r:
            chart_data = pd.DataFrame({
                'Channel': ['Musosoup', 'Spotify Showcase*', 'SubmitHub', 'Playlist Push', 'IMA Placements**'],
                'Cost per Placement': [0.62, 0.30, 8.87, 44.25, 99.00]
            })
            
            cpp_chart = alt.Chart(chart_data).mark_bar().encode(
                x=alt.X('Cost per Placement:Q', title='Cost per Placement / Conversion (USD)'),
                y=alt.Y('Channel:N', sort='x', title=''),
                color=alt.Color('Channel:N', scale=alt.Scale(
                    domain=['Musosoup', 'Spotify Showcase*', 'SubmitHub', 'Playlist Push', 'IMA Placements**'],
                    range=['#10B981', '#10B981', '#FBAD30', '#FBAD30', '#FBAD30']
                ), legend=None)
            ).properties(height=220).interactive()
            
            st.altair_chart(cpp_chart, use_container_width=True)
            st.caption("* Showcase value represents Cost Per Converted Listener. ** IMA guarantees 10,000 organic streams ($0.0297/stream).")

    elif slide == "3. Revenue Guardrails":
        col_l, col_r = st.columns([1, 1.2])
        with col_l:
            st.markdown(
                "### The Phantom Spend Guardrail\n"
                "In previous releases, we suffered from **Phantom Spend** (ad dollars driving high stream quantities that dilutes overall Earnings Per Stream).\n\n"
                "A database audit reveals that **Facebook catalog streams** pay almost nothing (EPS of $0.000016), and **Tier 3 Spotify regions** pay up to 11x less than Tier 1 markets. We were buying cheap impressions that diluted our royalties."
            )
        with col_r:
            st.markdown(
                "<div style='border: 1px solid rgba(255,255,255,0.08); border-left: 4px solid #10B981; border-radius: 8px; padding: 12px; background-color: rgba(16, 185, 129, 0.03); margin-bottom: 12px;'>"
                "<h5 style='color: #10B981; margin:0;'>🟢 TARGET (High-Payout Tier 1)</h5>"
                "<p style='font-size: 0.85rem; margin: 4px 0 0 0;'><b>Markets:</b> US, UK/GB, Germany (DE), Canada (CA), Australia (AU). Maximize Earnings Per Stream.</p>"
                "</div>", unsafe_allow_html=True
            )
            st.markdown(
                "<div style='border: 1px solid rgba(255,255,255,0.08); border-left: 4px solid #EF4444; border-radius: 8px; padding: 12px; background-color: rgba(239, 68, 68, 0.03); margin-bottom: 12px;'>"
                "<h5 style='color: #EF4444; margin:0;'>🔴 EXCLUDE (Low-Payout Tier 3)</h5>"
                "<p style='font-size: 0.85rem; margin: 4px 0 0 0;'><b>Markets:</b> India (IN) <i>[11x lower than US]</i>, Philippines (PH) <i>[5x lower]</i>, Turkey (TR) <i>[6x lower]</i>.</p>"
                "</div>", unsafe_allow_html=True
            )
            st.markdown(
                "<div style='border: 1px solid rgba(255,255,255,0.08); border-left: 4px solid #EF4444; border-radius: 8px; padding: 12px; background-color: rgba(239, 68, 68, 0.03);'>"
                "<h5 style='color: #EF4444; margin:0;'>🔴 EXCLUDE (Facebook Catalog Plays)</h5>"
                "<p style='font-size: 0.85rem; margin: 4px 0 0 0;'><b>Format:</b> Exclude Facebook catalog streams (EPS: $0.000016). Direct all budget to Spotify Home sponsored recommendations.</p>"
                "</div>", unsafe_allow_html=True
            )

    elif slide == "4. 4-Week Timeline":
        st.markdown("### 📅 'Marbles' 4-Week Release Campaign Timeline")
        st.markdown("Detailed channel checkpoints, budget targets, and strategic rules for the July 3rd launch.")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(
                """
                <div style="border: 1px solid #E5E7EB; border-left: 5px solid #10B981; border-radius: 12px; padding: 20px; background-color: #FFFFFF; box-shadow: 0 4px 15px rgba(0,0,0,0.03); min-height: 560px; display: flex; flex-direction: column;">
                    <h4 style="color: #059669; margin-top: 0; font-size: 1.15rem; font-weight: 700;">🌱 Step 1. Weeks 1-2: PR Seeding & Hook Testing</h4>
                    <h5 style="color: #1F2937; font-size: 0.95rem; font-weight: 600; margin-top: 5px; margin-bottom: 12px;">Budget Allocation: $150 - $200</h5>
                    <ul style="font-size: 0.85rem; color: #4B5563; padding-left: 18px; line-height: 1.6; margin-bottom: 0;">
                        <li><b>SubmitHub Pitches ($50)</b>: Use Premium Credits targeting Blues, Southern Rock, and Nu-Jazz playlisters (exclude folk/acoustic).</li>
                        <li><b>Musosoup Listing ($50)</b>: Launch a 3-week campaign targeting Funk Pop, Alternative/Blues Rock, and Jam Band tags.</li>
                        <li><b>Instagram A/B Testing ($50-$100)</b>: Target narrow premium audiences (e.g. Gary Clark Jr., Marcus King fans). Do not use broad "Rock". Test 2-3 specific musical hooks (e.g., "12-bar blues riff drenched in funk" or "Sax solos in 5/4"). Find the lowest CPC ($0.20-$0.30) and highest CTR (>4%) winner, and kill losers within 48 hours.</li>
                        <li><b>Budget Holds</b>: Keep Playlist Push/Indie Music Academy locked. No broad playlist budgets until organic signals are validated.</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True
            )
        with col2:
            st.markdown(
                """
                <div style="border: 1px solid #E5E7EB; border-left: 5px solid #FBAD30; border-radius: 12px; padding: 20px; background-color: #FFFFFF; box-shadow: 0 4px 15px rgba(0,0,0,0.03); min-height: 560px; display: flex; flex-direction: column;">
                    <h4 style="color: #D97706; margin-top: 0; font-size: 1.15rem; font-weight: 700;">📡 Step 2. Week 3: Algorithmic Seeding & Scale</h4>
                    <h5 style="color: #1F2937; font-size: 0.95rem; font-weight: 600; margin-top: 5px; margin-bottom: 12px;">Budget Allocation: $300</h5>
                    <ul style="font-size: 0.85rem; color: #4B5563; padding-left: 18px; line-height: 1.6; margin-bottom: 0;">
                        <li><b>Spotify Showcase ($150)</b>: Launch sponsored recommendations targeting active, lapsed, and super listeners. Focus solely on Tier 1 countries (US, UK, DE, CA, AU). Exclude Tier 3 and Facebook catalog formats to avoid <b>Phantom Spend</b>.</li>
                        <li><b>Instagram Scaled Retargeting ($150)</b>: Direct full budget to the winning hook from Weeks 1-2. Target 50%+ video viewers and Lookalikes of clickers. Run in parallel with Spotify Showcase to trigger the algorithmic "surround-sound" effect.</li>
                        <li><b>Goal</b>: Push for high-intent conversion metrics (Showcase CPA &le; $0.30, Save Rate &gt; 20%) to prime recommendation algorithms.</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True
            )
        with col3:
            st.markdown(
                """
                <div style="border: 1px solid #E5E7EB; border-left: 5px solid #6366F1; border-radius: 12px; padding: 20px; background-color: #FFFFFF; box-shadow: 0 4px 15px rgba(0,0,0,0.03); min-height: 560px; display: flex; flex-direction: column;">
                    <h4 style="color: #4F46E5; margin-top: 0; font-size: 1.15rem; font-weight: 700;">🚀 Step 3. Week 4: Scaling Decisions</h4>
                    <h5 style="color: #1F2937; font-size: 0.95rem; font-weight: 600; margin-top: 5px; margin-bottom: 12px;">Budget Allocation: $250</h5>
                    <ul style="font-size: 0.85rem; color: #4B5563; padding-left: 18px; line-height: 1.6; margin-bottom: 0;">
                        <li><b>Check Showcase Telemetry</b>: Assess Week 3 Showcase performance. Compare metrics against targets (CPA &lt; $0.25, Save Rate &gt; 20%).</li>
                        <li><b>Assess Instagram Off-Platform CPA</b>: Check if the $0.25 IG clicks are translating to Spotify Saves. If yes, keep scaling. If clicks are cheap but saves are low, cut the IG budget and redirect remaining funds to Spotify Showcase.</li>
                        <li><b>Scale Path (Green Light)</b>: If targets are met, inject the remaining $250 to accelerate Spotify Home recommendation placement.</li>
                        <li><b>Halt Path (Red Light)</b>: If CPA &gt; $0.35 or Save Rate &lt; 12%, halt active paid promotions immediately to protect capital. Let the track build organic momentum.</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True
            )

    elif slide == "5. Interactive Simulator":
        st.markdown("### Interactive Scaling Decision Sandbox")
        col_l, col_r = st.columns([1, 1.2])
        with col_l:
            st.write("On Day 21 (Week 4), we must decide whether to deploy the remaining $250. Adjust the sliders on the right to simulate live Showcase telemetry and see our recommended action.")
            st.write("**Target Benchmarks:**")
            st.write("🎯 Blended CPA: **< $0.30**")
            st.write("❤️ Save Rate: **> 20%**")
            st.write("📈 14-Day Post-Campaign Baseline Lift: **> 50%**")
        with col_r:
            sim_cpa = st.slider("Simulated Upfront CPA", min_value=0.10, max_value=0.60, value=0.30, step=0.01, format="$%.2f")
            sim_save = st.slider("Simulated Showcase Save Rate", min_value=5, max_value=35, value=15, step=1, format="%d%%")
            
            st.markdown("---")
            if sim_cpa <= 0.25 and sim_save >= 20:
                st.success("🟢 **SCALE (Star Investment)**: High direct listener acquisition and strong intent. Scale campaign by injecting the remaining $250 immediately.")
            elif sim_cpa > 0.35 or sim_save < 12:
                st.error("🔴 **CUT (Empty Calories)**: High CPA or very low save rate. Halt active promotional ad budgets immediately to protect capital. Let the track run organically.")
            elif sim_save >= 20 and sim_cpa <= 0.30:
                st.warning("🟡 **SEED (Algorithmic Seeder)**: High save rate (intent) and moderate CPA. Keep the testing budget going to trigger Spotify's Discover Weekly recommendations.")
            else:
                st.info("⚪ **TACTICAL HOLD**: Moderate conversion. Keep the current testing budget ($10/day) and test new ad creatives. Do not scale yet.")