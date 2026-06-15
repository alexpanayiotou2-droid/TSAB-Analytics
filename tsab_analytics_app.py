import streamlit as st
import pandas as pd
import altair as alt
import os

# --- 1. SETUP & CONFIG ---
st.set_page_config(page_title="TSAB Data Dashboard", layout="wide")
st.title("🎸 TSAB Cloud-Ready ROI Dashboard")
st.markdown("Automated cross-platform correlations, retention decay, and algorithmic triggers.")

# --- 2. HYBRID DATA PIPELINE WITH PROXIMITY PLACEHOLDERS ---
with st.sidebar:
    st.header("Update Data (Optional)")
    st.markdown("Dashboard loads automatically from GitHub. Upload new files here to test overrides before committing.")
    
    dk_upload = st.file_uploader("1. DistroKid Data", type="csv")
    dk_freshness = st.empty() # Placeholder for inline freshness
    
    spot_upload = st.file_uploader("2. Spotify Campaigns", type="csv")
    spot_freshness = st.empty() # Placeholder for inline freshness
    
    s4a_uploads = st.file_uploader("3. S4A Daily Tracks (Upload '-timeline' files here)", type="csv", accept_multiple_files=True)
    meta_upload = st.file_uploader("4. Meta Ads", type="csv")

dk_file = dk_upload if dk_upload else ("DistroKid Results 6.12.26.csv" if os.path.exists("DistroKid Results 6.12.26.csv") else None)
spot_file = spot_upload if spot_upload else ("Spotify Campaigns to date 6.12.26.csv" if os.path.exists("Spotify Campaigns to date 6.12.26.csv") else None)

if not (dk_file and spot_file):
    st.info("👋 Welcome! Waiting for data. Please ensure your core CSVs are uploaded to GitHub, or drop them in the sidebar.")
    st.stop()

# --- 3. DATA PROCESSING & CLEANING ---
@st.cache_data
def process_data(dk, spot, s4a_files, meta):
    dk_df = pd.read_csv(dk, low_memory=False)
    spot_df = pd.read_csv(spot, low_memory=False)
    
    s4a_dataframes = []
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
        s4a_df = pd.concat(s4a_dataframes, ignore_index=True)
    else:
        s4a_df = pd.DataFrame(columns=['date', 'streams', 'track_name'])
    
    if meta is not None:
        meta_df = pd.read_csv(meta, low_memory=False)
        meta_df['Start Date'] = pd.to_datetime(meta_df['Start Date'], errors='coerce')
        meta_df['Amount Spent (USD)'] = pd.to_numeric(meta_df['Amount Spent (USD)'], errors='coerce').fillna(0)
    else:
        meta_df = pd.DataFrame(columns=['Start Date', 'Amount Spent (USD)'])
    
    dk_df['Reporting Date'] = pd.to_datetime(dk_df['Reporting Date'], errors='coerce')
    dk_df['Earnings (USD)'] = pd.to_numeric(dk_df['Earnings (USD)'], errors='coerce').fillna(0)
    dk_df['Quantity'] = pd.to_numeric(dk_df['Quantity'], errors='coerce').fillna(0)
    
    spot_df['Start Date'] = pd.to_datetime(spot_df['Start Date'].astype(str).str.replace(' UTC', ''), errors='coerce')
    spot_df['End Date'] = pd.to_datetime(spot_df['End Date'].astype(str).str.replace(' UTC', ''), errors='coerce')
    spot_df['Spend'] = pd.to_numeric(spot_df['Spend'], errors='coerce').fillna(0)
    spot_df['Converted Listeners'] = pd.to_numeric(spot_df['Converted Listeners'], errors='coerce').fillna(0)
    spot_df['Save Rate'] = pd.to_numeric(spot_df['Save Rate'].astype(str).str.replace('%', ''), errors='coerce').fillna(0)
    spot_df['Intent Rate'] = pd.to_numeric(spot_df['Intent Rate'].astype(str).str.replace('%', ''), errors='coerce').fillna(0)
    
    return dk_df, spot_df, s4a_df, meta_df

with st.spinner("Processing datasets..."):
    dk_df, spot_df, s4a_df, meta_df = process_data(dk_file, spot_file, s4a_uploads, meta_upload)

# --- INJECT DATA FRESHNESS CALLOUTS ---
if not dk_df.empty:
    dk_max_date = dk_df['Reporting Date'].max()
    dk_freshness.caption(f"*(Current Through: {dk_max_date.strftime('%b %d, %Y')})*")
if not spot_df.empty:
    spot_max_date = spot_df['End Date'].max()
    spot_freshness.caption(f"*(Current Through: {spot_max_date.strftime('%b %d, %Y')})*")

if not s4a_df.empty:
    loaded_tracks = s4a_df['track_name'].unique()
    st.sidebar.success(f"✅ Successfully loaded S4A data for: {', '.join(loaded_tracks)}")

# --- FEATURE 1: EXECUTIVE FILTERS (TRACK & TIMEFRAME) ---
st.sidebar.divider()
st.sidebar.subheader("🎯 Executive Filters")

dk_tracks = dk_df['Title'].dropna().unique().tolist()
spot_tracks = spot_df['Release Name'].dropna().unique().tolist()
all_tracks = sorted(list(set(dk_tracks + spot_tracks)))

selected_view = st.sidebar.selectbox("Track Selection", ["All Catalog (Aggregate)"] + all_tracks)

# Timeframe Selection Mapping
timeframe_options = {"28 Days": 28, "6 Months": 180, "12 Months": 365, "All Time": None}
selected_timeframe = st.sidebar.selectbox("Timeframe", list(timeframe_options.keys()))
days_lookback = timeframe_options[selected_timeframe]

# Apply Track Filter Globally BEFORE metrics and charts execute
if selected_view != "All Catalog (Aggregate)":
    dk_df = dk_df[dk_df['Title'] == selected_view]
    spot_df = spot_df[spot_df['Release Name'] == selected_view]
    s4a_df = s4a_df[s4a_df['track_name'].str.contains(selected_view, case=False, na=False, regex=False)]

# --- 4. AUTOMATED EDA LOGIC ---
def generate_ai_brief(dk_df, spot_df, s4a_df, meta_df):
    brief_lines = []
    brief_lines.append("## TSAB ON-DEMAND ANOMALY BRIEF")
    brief_lines.append("*(Paste this directly into the CMO AI for strategic recommendations)*\n")
    
    phantom_cost_total = 0 
    
    # 1. DISCOVERY MODE ALGORITHM 
    brief_lines.append("### 1. DISCOVERY MODE ALGORITHM (Phantom Cost vs Reach)")
    spot_only = dk_df[dk_df['Store'].str.contains('Spotify', na=False, case=False)].copy()
    spot_only['Month'] = spot_only['Reporting Date'].dt.to_period('M')
    
    if not spot_only.empty:
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

    # 2. Algorithmic Tipping Point
    brief_lines.append("\n### 2. ALGORITHMIC TIPPING POINTS (Spotify)")
    high_intent = spot_df[(spot_df['Save Rate'] > 10) | (spot_df['Intent Rate'] > 10)]
    unique_tipping_points = high_intent.drop_duplicates(subset=['Campaign Name', 'Release Name'])
    
    if not unique_tipping_points.empty:
        for idx, row in unique_tipping_points.iterrows():
            brief_lines.append(f"- 🟢 **GREEN LIGHT:** Campaign '{row['Campaign Name']}' hit a Save Rate of {row['Save Rate']}%. Algorithm pickup is highly likely.")
    else:
        brief_lines.append("- No immediate algorithmic tipping points detected (Save/Intent rates under 10%).")

    # 3. Decay Curve (Real-Time S4A)
    brief_lines.append("\n### 3. DECAY CURVE (14-Day Real-Time Retention)")
    retention_alerts = []
    if s4a_df.empty:
        brief_lines.append("- *Awaiting Data: Please upload S4A Daily Track CSVs to calculate real-time decay curves.*")
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

    # 5. Cross-Platform Correlations
    brief_lines.append("\n### 5. CROSS-PLATFORM CORRELATIONS (Halo Effect)")
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

    return "\n".join(brief_lines), phantom_cost_total

ai_brief, phantom_spend = generate_ai_brief(dk_df, spot_df, s4a_df, meta_df)

# --- 5. UI LAYOUT & DYNAMIC TIMEFRAME METRICS ---
view_title = "Aggregate Catalog" if selected_view == "All Catalog (Aggregate)" else selected_view
st.subheader(f"📊 The Vitals: {view_title}")

dk_anchor = dk_df['Reporting Date'].max() if not dk_df.empty else pd.Timestamp.now()
spot_anchor = spot_df['End Date'].max() if not spot_df.empty else pd.Timestamp.now()
meta_anchor = meta_df['Start Date'].max() if not meta_df.empty else pd.Timestamp.now()

# DYNAMIC DATA FILTERS
if days_lookback:
    # Current Period
    dk_current = dk_df[(dk_df['Reporting Date'] > dk_anchor - pd.Timedelta(days=days_lookback)) & (dk_df['Reporting Date'] <= dk_anchor)]
    spot_current = spot_df[(spot_df['End Date'] > spot_anchor - pd.Timedelta(days=days_lookback)) & (spot_df['End Date'] <= spot_anchor)]
    meta_current = meta_df[(meta_df['Start Date'] > meta_anchor - pd.Timedelta(days=days_lookback)) & (meta_df['Start Date'] <= meta_anchor)]
    
    # Prior Period for Deltas
    dk_prior = dk_df[(dk_df['Reporting Date'] > dk_anchor - pd.Timedelta(days=days_lookback*2)) & (dk_df['Reporting Date'] <= dk_anchor - pd.Timedelta(days=days_lookback))]
    spot_prior = spot_df[(spot_df['End Date'] > spot_anchor - pd.Timedelta(days=days_lookback*2)) & (spot_df['End Date'] <= spot_anchor - pd.Timedelta(days=days_lookback))]
    meta_prior = meta_df[(meta_df['Start Date'] > meta_anchor - pd.Timedelta(days=days_lookback*2)) & (meta_df['Start Date'] <= meta_anchor - pd.Timedelta(days=days_lookback))]
else:
    # All Time - No prior period comparison
    dk_current = dk_df
    spot_current = spot_df
    meta_current = meta_df
    
    # THE BUG FIX: Initialize empty DataFrames with matching columns
    dk_prior = pd.DataFrame(columns=dk_df.columns)
    spot_prior = pd.DataFrame(columns=spot_df.columns)
    meta_prior = pd.DataFrame(columns=meta_df.columns)

# Current Metrics
spend_current = spot_current['Spend'].sum() + meta_current['Amount Spent (USD)'].sum()
earn_current = dk_current['Earnings (USD)'].sum()
conv_current = spot_current['Converted Listeners'].sum()
streams_current = dk_current['Quantity'].sum()
save_current = spot_current['Save Rate'].mean() if not spot_current.empty else 0

roas_current = (earn_current / spend_current) if spend_current > 0 else 0
cpa_current = (spend_current / conv_current) if conv_current > 0 else 0

# Prior Metrics (Calculated safely, stays 0 if empty)
spend_prior = spot_prior['Spend'].sum() + meta_prior['Amount Spent (USD)'].sum()
earn_prior = dk_prior['Earnings (USD)'].sum()
conv_prior = spot_prior['Converted Listeners'].sum()
streams_prior = dk_prior['Quantity'].sum()
save_prior = spot_prior['Save Rate'].mean() if not spot_prior.empty else 0

roas_prior = (earn_prior / spend_prior) if spend_prior > 0 else 0
cpa_prior = (spend_prior / conv_prior) if conv_prior > 0 else 0

# Deltas (Hidden if "All Time")
d_roas = roas_current - roas_prior if days_lookback else None
d_cpa = cpa_current - cpa_prior if days_lookback else None
d_save = save_current - save_prior if days_lookback else None
d_streams = streams_current - streams_prior if days_lookback else None

# Helper functions to conditionally display deltas
def render_metric(col, label, value, delta_val, formatting_str, is_inverse=False):
    delta_display = f"{delta_val:{formatting_str}}" if delta_val is not None else None
    d_color = "inverse" if is_inverse else "normal"
    if label == "Upfront CPA" and delta_val is not None:
        delta_display = f"${delta_display}"
    elif label == "Blended ROAS" and delta_val is not None:
        delta_display = f"{delta_display}x"
    elif label == "Avg. Save Rate" and delta_val is not None:
        delta_display = f"{delta_display}%"
        
    col.metric(f"{label}", value, delta=delta_display, delta_color=d_color)

# Render Vitals
if selected_view == "All Catalog (Aggregate)":
    # 4 columns, no Phantom Spend
    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
    render_metric(col_kpi1, "💰 Blended ROAS", f"{roas_current:.2f}x", d_roas, ".2f")
    render_metric(col_kpi2, "🎯 Upfront CPA", f"${cpa_current:.2f}", d_cpa, ".2f", is_inverse=True)
    render_metric(col_kpi3, "❤️ Avg. Save Rate", f"{save_current:.1f}%", d_save, ".1f")
    render_metric(col_kpi4, "🎧 Total Streams", f"{streams_current:,.0f}", d_streams, ",.0f")
else:
    # 5 columns, reveals track-specific Phantom Spend
    col_kpi1, col_kpi2, col_kpi3, col_kpi4, col_kpi5 = st.columns(5)
    render_metric(col_kpi1, "💰 Blended ROAS", f"{roas_current:.2f}x", d_roas, ".2f")
    render_metric(col_kpi2, "🎯 Upfront CPA", f"${cpa_current:.2f}", d_cpa, ".2f", is_inverse=True)
    col_kpi3.metric("👻 Phantom Spend", f"${phantom_spend:.2f}", help="Cumulative royalties sacrificed to Discovery Mode for this track")
    render_metric(col_kpi4, "❤️ Avg. Save Rate", f"{save_current:.1f}%", d_save, ".1f")
    render_metric(col_kpi5, "🎧 Total Streams", f"{streams_current:,.0f}", d_streams, ",.0f")

st.divider()

st.subheader(f"🌍 Trends: {selected_timeframe}")
col_v1, col_v2 = st.columns([1, 1])

with col_v1:
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

with col_v2:
    if not dk_current.empty:
        store_streams = dk_current.groupby('Store')['Quantity'].sum().reset_index().sort_values(by='Quantity', ascending=False).head(8)
        st.altair_chart(
            alt.Chart(store_streams).mark_bar().encode(
                x=alt.X('Quantity:Q', title='Total Streams'),
                y=alt.Y('Store:N', sort='-x', title=''),
                color=alt.Color('Store:N', legend=None)
            ),
            use_container_width=True
        )
    else:
        st.write("No store data available for this timeframe.")

st.divider()

st.subheader("🤖 Strategic Anomaly Engine (Ready for CMO)")
st.markdown("Use the expander below to reveal your automated marketing breakdown.")

with st.expander("🤖 View & Copy Strategic Anomaly Brief", expanded=False):
    st.code(ai_brief, language="markdown")