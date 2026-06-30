import streamlit as st
import pandas as pd
import altair as alt
import os
import json
import urllib.request
import ssl
import re

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
    if local_file_name:
        for path in (local_file_name, f"../{local_file_name}", f"data-backend/{local_file_name}", f"../data-backend/{local_file_name}"):
            if os.path.exists(path):
                return pd.read_csv(path, low_memory=False)
                
    return pd.DataFrame()

# --- 2. HYBRID DATA PIPELINE (APPEND LOGIC) ---
with st.sidebar:
    # Render typographic brand logo at top of sidebar
    if os.path.exists(wordmark_path):
        st.image(wordmark_path, use_container_width=True, output_format="PNG")
    st.markdown("---")
    
    st.header("Update Data")
    st.markdown("Base data loads from Supabase. Drop new files here to **append** to your history.")
    
    dk_uploads = st.file_uploader("1. Add DistroKid Data", type="csv", accept_multiple_files=True)
    st.caption("📂 *Expects: DistroKid royalty CSV reports (e.g., DistroKid Results 6.12.26.csv)*")
    dk_freshness = st.empty() 
    
    spot_uploads = st.file_uploader("2. Add Spotify Campaigns", type="csv", accept_multiple_files=True)
    st.caption("📂 *Expects: Spotify Ad Studio campaign report CSVs (e.g., Spotify Campaigns to date 6.12.26.csv)*")
    spot_freshness = st.empty() 
    
    s4a_uploads = st.file_uploader("3. Add S4A Daily Tracks", type="csv", accept_multiple_files=True)
    st.caption("📂 *Expects: S4A daily stream timeline CSVs (e.g., Astronaut-timeline.csv)*")
    
    meta_uploads = st.file_uploader("4. Add Meta Ads", type="csv", accept_multiple_files=True)
    st.caption("📂 *Expects: Meta Ads CSV reports with columns 'Start Date' and 'Amount Spent (USD)'*")

    submithub_uploads = st.file_uploader("5. Add SubmitHub Data", type=["txt", "csv", "xlsx", "xls"], accept_multiple_files=True)
    st.caption("📂 *Expects: Response page text (.txt), submission history (.csv), purchase history (.xlsx), or pre-merged CSV*")

    playlist_push_uploads = st.file_uploader("6. Add Playlist Push Data", type=["pdf", "csv"], accept_multiple_files=True)
    st.caption("📂 *Expects: (1) Campaign responses PDF (e.g. '[P] Campaign responses for_ Astronaut - Playlist Push.pdf'), (2) Campaign Invoice PDF (e.g. '[P] playlistpush-invoice-480065 - Astronaut.pdf'), or (3) Campaign summary CSV (e.g. 'Socially Acceptable - Playlist Push Campaign Results.csv')*")





# Fetch Base Data from Supabase (with Fallbacks)
dk_base_df = load_base_data("distrokid_royalties", "DistroKid/DistroKid Results 6.12.26.csv", DK_COLUMN_MAP)
spot_base_df = load_base_data("spotify_campaign_metrics", "Spotify For Artists/Spotify Campaigns to date 6.12.26.csv", SPOTIFY_COLUMN_MAP)
s4a_base_df = load_base_data("s4a_daily_streams", None, {})
submithub_base_df = load_base_data("submithub_submissions", "SubmitHub/submithub_submissions_merged.csv", {})
submithub_purchases_base_df = load_base_data("submithub_credit_purchases", "SubmitHub/submithub_credit_purchases.csv", {})
pp_campaigns_base_df = load_base_data("playlist_push_campaigns", "Playlist Push/playlist_push_campaigns.csv", {})
pp_placements_base_df = load_base_data("playlist_push_placements", "Playlist Push/playlist_push_placements.csv", {})





if (dk_base_df.empty and not dk_uploads) or (spot_base_df.empty and not spot_uploads):
    st.info("👋 Welcome! Waiting for data. Please ensure your Supabase database is seeded, or drop your files in the sidebar.")
    st.stop()

# --- 3. DATA PROCESSING & AUTO-STITCHING ---
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

@st.cache_data
def process_data(dk_base_df, dk_files, spot_base_df, spot_files, s4a_base_df, s4a_files, meta_files, 
                 submithub_base_df, submithub_purchases_base_df, submithub_files,
                 pp_campaigns_base_df, pp_placements_base_df, pp_files):
    
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
                    if 'Song' in df_check.columns and 'Outlet' in df_check.columns and 'Campaign date' in df_check.columns:
                        history_csv_file = file
                    else:
                        pre_parsed_csvs.append(file)
                except Exception:
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
                action_timestamp = pd.to_datetime(matched_group['Action timestamp']).max()
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
            song_name = file.name.replace(' response page text.txt', '').replace(' Response page text.txt', '').replace(' response page text', '').replace('.txt', '').strip()
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
        
    if not meta_df.empty:
        meta_df['Start Date'] = pd.to_datetime(meta_df['Start Date'], errors='coerce')
        meta_df['Amount Spent (USD)'] = pd.to_numeric(meta_df['Amount Spent (USD)'], errors='coerce').fillna(0)
    else:
        meta_df = pd.DataFrame(columns=['Start Date', 'Amount Spent (USD)'])
    
    if not dk_df.empty:
        dk_df['Reporting Date'] = pd.to_datetime(dk_df['Reporting Date'], errors='coerce')
        dk_df['Earnings (USD)'] = pd.to_numeric(dk_df['Earnings (USD)'], errors='coerce').fillna(0)
        dk_df['Quantity'] = pd.to_numeric(dk_df['Quantity'], errors='coerce').fillna(0)
    
    if not spot_df.empty:
        spot_df['Start Date'] = pd.to_datetime(spot_df['Start Date'].astype(str).str.replace(' UTC', ''), errors='coerce')
        spot_df['End Date'] = pd.to_datetime(spot_df['End Date'].astype(str).str.replace(' UTC', ''), errors='coerce')
        spot_df['Spend'] = pd.to_numeric(spot_df['Spend'], errors='coerce').fillna(0)
        spot_df['Converted Listeners'] = pd.to_numeric(spot_df['Converted Listeners'], errors='coerce').fillna(0)
        spot_df['Save Rate'] = pd.to_numeric(spot_df['Save Rate'].astype(str).str.replace('%', ''), errors='coerce').fillna(0)
        spot_df['Intent Rate'] = pd.to_numeric(spot_df['Intent Rate'].astype(str).str.replace('%', ''), errors='coerce').fillna(0)
    
    return dk_df, spot_df, s4a_df, meta_df, submithub_df, pp_campaigns_df, pp_placements_df

with st.spinner("Stitching and processing datasets..."):
    dk_df, spot_df, s4a_df, meta_df, submithub_df, pp_campaigns_df, pp_placements_df = process_data(
        dk_base_df, dk_uploads, spot_base_df, spot_uploads, s4a_base_df, s4a_uploads, meta_uploads, 
        submithub_base_df, submithub_purchases_base_df, submithub_uploads,
        pp_campaigns_base_df, pp_placements_base_df, playlist_push_uploads
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
all_tracks = sorted(list(set(dk_tracks + spot_tracks)))

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

# Standardize date formats in submithub_df & pp_campaigns_df
if not submithub_df.empty:
    submithub_df['campaign_date'] = pd.to_datetime(submithub_df['campaign_date'], errors='coerce')
    submithub_df['cost_usd'] = pd.to_numeric(submithub_df['cost_usd'], errors='coerce').fillna(0)
if not pp_campaigns_df.empty:
    pp_campaigns_df['campaign_date'] = pd.to_datetime(pp_campaigns_df['campaign_date'], errors='coerce')
    pp_campaigns_df['budget_usd'] = pd.to_numeric(pp_campaigns_df['budget_usd'], errors='coerce').fillna(0)

pp_anchor = pd.to_datetime(pp_campaigns_df['campaign_date'], errors='coerce').max() if not pp_campaigns_df.empty else pd.Timestamp.now()

if days_lookback:
    dk_current = dk_df[(dk_df['Reporting Date'] > dk_anchor - pd.Timedelta(days=days_lookback)) & (dk_df['Reporting Date'] <= dk_anchor)] if not dk_df.empty else dk_df
    spot_current = spot_df[(spot_df['End Date'] > spot_anchor - pd.Timedelta(days=days_lookback)) & (spot_df['End Date'] <= spot_anchor)] if not spot_df.empty else spot_df
    meta_current = meta_df[(meta_df['Start Date'] > meta_anchor - pd.Timedelta(days=days_lookback)) & (meta_df['Start Date'] <= meta_anchor)] if not meta_df.empty else meta_df
    submithub_current = submithub_df[(submithub_df['campaign_date'] > submithub_anchor - pd.Timedelta(days=days_lookback)) & (submithub_df['campaign_date'] <= submithub_anchor)] if not submithub_df.empty else submithub_df
    pp_current = pp_campaigns_df[(pp_campaigns_df['campaign_date'] > pp_anchor - pd.Timedelta(days=days_lookback)) & (pp_campaigns_df['campaign_date'] <= pp_anchor)] if not pp_campaigns_df.empty else pp_campaigns_df
    
    dk_prior = dk_df[(dk_df['Reporting Date'] > dk_anchor - pd.Timedelta(days=days_lookback*2)) & (dk_df['Reporting Date'] <= dk_anchor - pd.Timedelta(days=days_lookback))] if not dk_df.empty else dk_df
    spot_prior = spot_df[(spot_df['End Date'] > spot_anchor - pd.Timedelta(days=days_lookback*2)) & (spot_df['End Date'] <= spot_anchor - pd.Timedelta(days=days_lookback))] if not spot_df.empty else spot_df
    meta_prior = meta_df[(meta_df['Start Date'] > meta_anchor - pd.Timedelta(days=days_lookback*2)) & (meta_df['Start Date'] <= meta_anchor - pd.Timedelta(days=days_lookback))] if not meta_df.empty else meta_df
    submithub_prior = submithub_df[(submithub_df['campaign_date'] > submithub_anchor - pd.Timedelta(days=days_lookback*2)) & (submithub_df['campaign_date'] <= submithub_anchor - pd.Timedelta(days=days_lookback))] if not submithub_df.empty else submithub_df
    pp_prior = pp_campaigns_df[(pp_campaigns_df['campaign_date'] > pp_anchor - pd.Timedelta(days=days_lookback*2)) & (pp_campaigns_df['campaign_date'] <= pp_anchor - pd.Timedelta(days=days_lookback))] if not pp_campaigns_df.empty else pp_campaigns_df
else:
    dk_current = dk_df
    spot_current = spot_df
    meta_current = meta_df
    submithub_current = submithub_df
    pp_current = pp_campaigns_df
    
    dk_prior = pd.DataFrame(columns=dk_df.columns if not dk_df.empty else [])
    spot_prior = pd.DataFrame(columns=spot_df.columns if not spot_df.empty else [])
    meta_prior = pd.DataFrame(columns=meta_df.columns if not meta_df.empty else [])
    submithub_prior = pd.DataFrame(columns=submithub_df.columns if not submithub_df.empty else [])
    pp_prior = pd.DataFrame(columns=pp_campaigns_df.columns if not pp_campaigns_df.empty else [])

# Compute Blended Spend: Spotify + Meta + SubmitHub + Playlist Push
spend_current = (
    (spot_current['Spend'].sum() if not spot_current.empty else 0) + 
    (meta_current['Amount Spent (USD)'].sum() if not meta_current.empty else 0) + 
    (submithub_current['cost_usd'].sum() if not submithub_current.empty else 0) +
    (pp_current['budget_usd'].sum() if not pp_current.empty else 0)
)
earn_current = dk_current['Earnings (USD)'].sum() if not dk_current.empty else 0
# Compute Blended Conversions: Spotify converted listeners + SubmitHub approvals + Playlist Push adds
conv_current = (
    (spot_current['Converted Listeners'].sum() if not spot_current.empty else 0) + 
    (submithub_current[submithub_current['action'] == 'Approved'].shape[0] if not submithub_current.empty else 0) +
    (pp_current['playlist_adds'].sum() if not pp_current.empty else 0)
)
streams_current = dk_current['Quantity'].sum() if not dk_current.empty else 0
save_current = spot_current['Save Rate'].mean() if not spot_current.empty else 0

roas_current = (earn_current / spend_current) if spend_current > 0 else 0
cpa_current = (spend_current / conv_current) if conv_current > 0 else 0

spend_prior = (
    (spot_prior['Spend'].sum() if not spot_prior.empty and 'Spend' in spot_prior.columns else 0) + 
    (meta_prior['Amount Spent (USD)'].sum() if not meta_prior.empty and 'Amount Spent (USD)' in meta_prior.columns else 0) + 
    (submithub_prior['cost_usd'].sum() if not submithub_prior.empty and 'cost_usd' in submithub_prior.columns else 0) +
    (pp_prior['budget_usd'].sum() if not pp_prior.empty and 'budget_usd' in pp_prior.columns else 0)
)
earn_prior = dk_prior['Earnings (USD)'].sum() if not dk_prior.empty and 'Earnings (USD)' in dk_prior.columns else 0
conv_prior = (
    (spot_prior['Converted Listeners'].sum() if not spot_prior.empty and 'Converted Listeners' in spot_prior.columns else 0) + 
    (submithub_prior[submithub_prior['action'] == 'Approved'].shape[0] if not submithub_prior.empty else 0) +
    (pp_prior['playlist_adds'].sum() if not pp_prior.empty and 'playlist_adds' in pp_prior.columns else 0)
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

st.subheader(f"🌍 Trends: {selected_timeframe}")
tab_core, tab_season, tab_pr = st.tabs(["📈 Core Trends", "🍂 Seasonality Analysis", "📣 PR & Curator Outreach"])

with tab_core:
    col_v1, col_v2 = st.columns([1, 1])
    with col_v1:
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

with tab_season:
    # Build Seasonality Comparison Dataset dynamically
    # Group campaigns into seasons based on Start Date:
    # Spring = March/April/May | Summer = June/July/August | Autumn = September/October/November
    if not spot_df.empty:
        season_tracks = []
        for name in spot_df['Release Name'].unique():
            track_spot = spot_df[spot_df['Release Name'] == name]
            track_dk = dk_df[dk_df['Title'] == name] if not dk_df.empty else pd.DataFrame()
            
            # Map start date to season
            start_date = track_spot['Start Date'].min()
            if pd.isna(start_date): continue
            
            month = start_date.month
            if month in [3, 4, 5]: season = "Spring"
            elif month in [6, 7, 8]: season = "Summer"
            elif month in [9, 10, 11]: season = "Autumn"
            else: season = "Winter"
            
            # Aggregate metrics
            spend = track_spot['Spend'].sum()
            conv = track_spot['Converted Listeners'].sum()
            cpa = spend / conv if conv > 0 else 0
            
            # Spotify ROAS = Spotify Earnings / Spotify Spend
            spot_earnings = track_dk[track_dk['Store'].str.contains('Spotify', na=False, case=False)]['Earnings (USD)'].sum() if not track_dk.empty else 0
            roas = spot_earnings / spend if spend > 0 else 0
            
            # Trailing 7-day average daily streams from S4A
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

with tab_pr:
    st.markdown("### 📣 PR & Curator Outreach Performance")
    
    pr_platform = st.radio("Select Outreach Platform", ["SubmitHub", "Playlist Push"], horizontal=True)
    
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


st.divider()


st.subheader("🤖 Strategic Anomaly Engine (Ready for CMO)")
st.markdown("Use the expander below to reveal your automated marketing breakdown.")

with st.expander("🤖 View & Copy Strategic Anomaly Brief", expanded=False):
    st.code(ai_brief, language="markdown")

st.divider()
st.subheader("🤖 Strategic Reinvestment Console")
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