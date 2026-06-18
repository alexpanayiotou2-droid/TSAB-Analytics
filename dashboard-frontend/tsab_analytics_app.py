import streamlit as st
import pandas as pd
import altair as alt
import os
import json
import urllib.request
import ssl

# --- 1. SETUP & CONFIG ---
st.set_page_config(page_title="TSAB Data Dashboard", layout="wide")
st.title("🎸 TSAB Cloud-Ready ROI Dashboard")
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

# --- BRANDING LAYOUT HOOKS & CUSTOM CSS ---
frontend_dir = os.path.dirname(os.path.abspath(__file__))
logo_path = os.path.join(frontend_dir, "assets", "Bird solo.png")
wordmark_path = os.path.join(frontend_dir, "assets", "SA_Fill_Black.png")

with st.sidebar:
    # Anchor branding block in a container
    brand_container = st.container()
    with brand_container:
        col_logo_left, col_logo_mid, col_logo_right = st.columns([1, 2, 1])
        with col_logo_mid:
            if os.path.exists(logo_path):
                st.image(logo_path, use_container_width=True)
        
        if os.path.exists(wordmark_path):
            st.image(wordmark_path, use_container_width=True, output_format="PNG")
    
    st.markdown("---") # Visual separator

st.markdown(
    """
    <style>
    /* Invert the black typographic logo to white for dark-mode visibility */
    img[alt*="SA_Fill_Black"], img[src*="SA_Fill_Black"] {
        filter: invert(1) brightness(1.2);
        max-height: 55px;
        object-fit: contain;
        display: block;
        margin-left: auto;
        margin-right: auto;
        padding-bottom: 15px;
    }
    
    /* Center the Bird Solo image and add hover micro-animation */
    img[alt*="Bird solo"], img[src*="Bird solo"] {
        max-height: 90px;
        object-fit: contain;
        display: block;
        margin-left: auto;
        margin-right: auto;
        transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    }
    img[alt*="Bird solo"]:hover {
        transform: rotate(5deg) scale(1.05);
    }
    
    /* Make metric cards feel premium with subtle amber indicator bars */
    div[data-testid="stMetric"] {
        background-color: #161920;
        border-radius: 12px;
        padding: 20px 24px;
        border-top: 3px solid #FBAD30;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
        transition: all 0.25s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 25px rgba(251, 173, 48, 0.15);
    }
    
    /* Align metrics header spacing */
    div[data-testid="stMetric"] label {
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: #AEB5C5 !important;
        font-size: 0.75rem !important;
    }
    
    /* Customize sidebar styles */
    section[data-testid="stSidebar"] {
        background-color: #0B0D13 !important;
        border-right: 1px solid #1E222F;
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
    st.header("Update Data")
    st.markdown("Base data loads from Supabase. Drop new files here to **append** to your history.")
    
    dk_uploads = st.file_uploader("1. Add DistroKid Data", type="csv", accept_multiple_files=True)
    dk_freshness = st.empty() 
    
    spot_uploads = st.file_uploader("2. Add Spotify Campaigns", type="csv", accept_multiple_files=True)
    spot_freshness = st.empty() 
    
    s4a_uploads = st.file_uploader("3. Add S4A Daily Tracks", type="csv", accept_multiple_files=True)
    meta_uploads = st.file_uploader("4. Add Meta Ads", type="csv", accept_multiple_files=True)

# Fetch Base Data from Supabase (with Fallbacks)
dk_base_df = load_base_data("distrokid_royalties", "DistroKid Results 6.12.26.csv", DK_COLUMN_MAP)
spot_base_df = load_base_data("spotify_campaign_metrics", "Spotify Campaigns to date 6.12.26.csv", SPOTIFY_COLUMN_MAP)
s4a_base_df = load_base_data("s4a_daily_streams", None, {})

if (dk_base_df.empty and not dk_uploads) or (spot_base_df.empty and not spot_uploads):
    st.info("👋 Welcome! Waiting for data. Please ensure your Supabase database is seeded, or drop your files in the sidebar.")
    st.stop()

# --- 3. DATA PROCESSING & AUTO-STITCHING ---
@st.cache_data
def process_data(dk_base_df, dk_files, spot_base_df, spot_files, s4a_base_df, s4a_files, meta_files):
    
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
    
    return dk_df, spot_df, s4a_df, meta_df

with st.spinner("Stitching and processing datasets..."):
    dk_df, spot_df, s4a_df, meta_df = process_data(dk_base_df, dk_uploads, spot_base_df, spot_uploads, s4a_base_df, s4a_uploads, meta_uploads)

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

if days_lookback:
    dk_current = dk_df[(dk_df['Reporting Date'] > dk_anchor - pd.Timedelta(days=days_lookback)) & (dk_df['Reporting Date'] <= dk_anchor)] if not dk_df.empty else dk_df
    spot_current = spot_df[(spot_df['End Date'] > spot_anchor - pd.Timedelta(days=days_lookback)) & (spot_df['End Date'] <= spot_anchor)] if not spot_df.empty else spot_df
    meta_current = meta_df[(meta_df['Start Date'] > meta_anchor - pd.Timedelta(days=days_lookback)) & (meta_df['Start Date'] <= meta_anchor)] if not meta_df.empty else meta_df
    
    dk_prior = dk_df[(dk_df['Reporting Date'] > dk_anchor - pd.Timedelta(days=days_lookback*2)) & (dk_df['Reporting Date'] <= dk_anchor - pd.Timedelta(days=days_lookback))] if not dk_df.empty else dk_df
    spot_prior = spot_df[(spot_df['End Date'] > spot_anchor - pd.Timedelta(days=days_lookback*2)) & (spot_df['End Date'] <= spot_anchor - pd.Timedelta(days=days_lookback))] if not spot_df.empty else spot_df
    meta_prior = meta_df[(meta_df['Start Date'] > meta_anchor - pd.Timedelta(days=days_lookback*2)) & (meta_df['Start Date'] <= meta_anchor - pd.Timedelta(days=days_lookback))] if not meta_df.empty else meta_df
else:
    dk_current = dk_df
    spot_current = spot_df
    meta_current = meta_df
    dk_prior = pd.DataFrame(columns=dk_df.columns if not dk_df.empty else [])
    spot_prior = pd.DataFrame(columns=spot_df.columns if not spot_df.empty else [])
    meta_prior = pd.DataFrame(columns=meta_df.columns if not meta_df.empty else [])

spend_current = (spot_current['Spend'].sum() if not spot_current.empty else 0) + (meta_current['Amount Spent (USD)'].sum() if not meta_current.empty else 0)
earn_current = dk_current['Earnings (USD)'].sum() if not dk_current.empty else 0
conv_current = spot_current['Converted Listeners'].sum() if not spot_current.empty else 0
streams_current = dk_current['Quantity'].sum() if not dk_current.empty else 0
save_current = spot_current['Save Rate'].mean() if not spot_current.empty else 0

roas_current = (earn_current / spend_current) if spend_current > 0 else 0
cpa_current = (spend_current / conv_current) if conv_current > 0 else 0

spend_prior = (spot_prior['Spend'].sum() if not spot_prior.empty and 'Spend' in spot_prior.columns else 0) + (meta_prior['Amount Spent (USD)'].sum() if not meta_prior.empty and 'Amount Spent (USD)' in meta_prior.columns else 0)
earn_prior = dk_prior['Earnings (USD)'].sum() if not dk_prior.empty and 'Earnings (USD)' in dk_prior.columns else 0
conv_prior = spot_prior['Converted Listeners'].sum() if not spot_prior.empty and 'Converted Listeners' in spot_prior.columns else 0
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

st.divider()

st.subheader("🤖 Strategic Anomaly Engine (Ready for CMO)")
st.markdown("Use the expander below to reveal your automated marketing breakdown.")

with st.expander("🤖 View & Copy Strategic Anomaly Brief", expanded=False):
    st.code(ai_brief, language="markdown")