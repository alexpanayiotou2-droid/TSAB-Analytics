import streamlit as st
import pandas as pd
import altair as alt
import os

# --- 1. SETUP & CONFIG ---
st.set_page_config(page_title="TSAB Data Dashboard", layout="wide")
st.title("🎸 TSAB Cloud-Ready ROI Dashboard")
st.markdown("Automated cross-platform correlations, retention decay, and algorithmic triggers.")

# --- 2. HYBRID DATA PIPELINE ---
with st.sidebar:
    st.header("Update Data (Optional)")
    st.markdown("Dashboard loads automatically from GitHub. Upload new files here to test overrides before committing them.")
    
    dk_upload = st.file_uploader("Override DistroKid Data", type="csv")
    spot_upload = st.file_uploader("Override Spotify Data", type="csv")
    meta_upload = st.file_uploader("Override Meta Ads", type="csv")

dk_file = dk_upload if dk_upload else ("DistroKid Results 6.12.26.csv" if os.path.exists("DistroKid Results 6.12.26.csv") else None)
spot_file = spot_upload if spot_upload else ("Spotify Campaigns to date 6.12.26.csv" if os.path.exists("Spotify Campaigns to date 6.12.26.csv") else None)
meta_file = meta_upload if meta_upload else None 

if not (dk_file and spot_file):
    st.info("👋 Welcome! Waiting for data. Please ensure your CSVs are uploaded to GitHub, or drop them in the sidebar.")
    st.stop()

# --- 3. DATA PROCESSING & CLEANING ---
@st.cache_data
def process_data(dk, spot, meta):
    dk_df = pd.read_csv(dk, low_memory=False)
    spot_df = pd.read_csv(spot, low_memory=False)
    
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
    
    return dk_df, spot_df, meta_df

with st.spinner("Processing massive datasets..."):
    dk_df, spot_df, meta_df = process_data(dk_file, spot_file, meta_file)

# --- 4. AUTOMATED EDA LOGIC ---
def generate_ai_brief(dk_df, spot_df, meta_df):
    brief_lines = []
    brief_lines.append("## TSAB ON-DEMAND ANOMALY BRIEF")
    brief_lines.append("*(Paste this directly into the CMO AI for strategic recommendations)*\n")
    
    # Algorithmic Tipping Point
    brief_lines.append("### 1. ALGORITHMIC TIPPING POINTS (Spotify)")
    high_intent = spot_df[(spot_df['Save Rate'] > 10) | (spot_df['Intent Rate'] > 10)]
    if not high_intent.empty:
        for idx, row in high_intent.iterrows():
            brief_lines.append(f"- 🟢 **GREEN LIGHT:** Campaign '{row['Campaign Name']}' hit a Save Rate of {row['Save Rate']}%. Algorithm pickup is highly likely.")
    else:
        brief_lines.append("- No immediate algorithmic tipping points detected (Save/Intent rates under 10%).")

    # Decay Curve
    brief_lines.append("\n### 2. DECAY CURVE (14-Day Post-Campaign Retention)")
    retention_alerts = []
    for idx, row in spot_df.dropna(subset=['Start Date', 'End Date', 'Release Name']).iterrows():
        track_name = row['Release Name']
        track_data = dk_df[dk_df['Title'] == track_name]
        if track_data.empty: continue
        daily_streams = track_data.groupby('Reporting Date')['Quantity'].sum()
        pre_mask = (daily_streams.index >= (row['Start Date'] - pd.Timedelta(days=14))) & (daily_streams.index < row['Start Date'])
        post_mask = (daily_streams.index > row['End Date']) & (daily_streams.index <= (row['End Date'] + pd.Timedelta(days=14)))
        avg_pre = daily_streams.loc[pre_mask].mean() if not daily_streams.loc[pre_mask].empty else 0
        avg_post = daily_streams.loc[post_mask].mean() if not daily_streams.loc[post_mask].empty else 0
        if avg_post > (avg_pre * 1.2): 
            retention_alerts.append(f"- 🔥 **High Retention:** '{track_name}' permanently increased its baseline by {((avg_post/avg_pre)-1)*100:.0f}%. True fans acquired.")
        elif avg_post < (avg_pre * 1.05) and row['Spend'] > 0:
            retention_alerts.append(f"- ⚠️ **Empty Calories:** '{track_name}' baseline dropped immediately after ad spend stopped.")
            
    if retention_alerts: brief_lines.extend(retention_alerts[:4])
    else: brief_lines.append("- Not enough post-campaign baseline data to calculate decay curves yet.")

    # Geographic Anomalies
    brief_lines.append("\n### 3. GEOGRAPHIC ANOMALIES (Stream Spikes)")
    dk_geo = dk_df.groupby(['Reporting Date', 'Country of Sale'])['Quantity'].sum().reset_index()
    dk_geo['mean_7d'] = dk_geo.groupby('Country of Sale')['Quantity'].transform(lambda x: x.rolling(7, min_periods=1).mean())
    dk_geo['std_7d'] = dk_geo.groupby('Country of Sale')['Quantity'].transform(lambda x: x.rolling(7, min_periods=1).std().fillna(0))
    spikes = dk_geo[(dk_geo['Quantity'] > (dk_geo['mean_7d'] + 2 * dk_geo['std_7d'])) & (dk_geo['Quantity'] > 20)]
    if not spikes.empty:
        for idx, row in spikes.sort_values('Quantity', ascending=False).head(3).iterrows():
            brief_lines.append(f"- **{row['Country of Sale']}**: {row['Quantity']:.0f} streams on {row['Reporting Date'].strftime('%Y-%m-%d')}.")
    else:
        brief_lines.append("- No statistically significant geographic volume spikes detected recently.")

    # Cross-Platform Correlations
    brief_lines.append("\n### 4. CROSS-PLATFORM CORRELATIONS (Halo Effect)")
    non_spot_df = dk_df[~dk_df['Store'].str.contains('Spotify', na=False, case=False)]
    non_spot_daily = non_spot_df.groupby('Reporting Date')['Quantity'].sum()
    halo_effects = []
    for start_date in spot_df['Start Date'].dropna().unique():
        before_mask = (non_spot_daily.index >= (start_date - pd.Timedelta(days=7))) & (non_spot_daily.index < start_date)
        after_mask = (non_spot_daily.index >= start_date) & (non_spot_daily.index < (start_date + pd.Timedelta(days=7)))
        streams_before = non_spot_daily.loc[before_mask].sum()
        streams_after = non_spot_daily.loc[after_mask].sum()
        if streams_before > 0 and streams_after > (streams_before * 1.2):
            halo_effects.append(f"- Campaign on {pd.to_datetime(start_date).strftime('%Y-%m-%d')} correlated with +{((streams_after/streams_before)-1)*100:.1f}% organic spike on Apple/YouTube.")
    
    if halo_effects: brief_lines.extend(halo_effects[:2])
    else: brief_lines.append("- No significant 'halo effect' organic jumps detected on alternative platforms.")

    return "\n".join(brief_lines)

ai_brief = generate_ai_brief(dk_df, spot_df, meta_df)

# --- 5. UI LAYOUT ---

# --- ROW 1: THE VITALS (KPIs) ---
st.subheader("📊 The Vitals")
total_spend = spot_df['Spend'].sum() + meta_df['Amount Spent (USD)'].sum()
total_earnings = dk_df['Earnings (USD)'].sum()
total_converted = spot_df['Converted Listeners'].sum()
total_streams = dk_df['Quantity'].sum()

roas = (total_earnings / total_spend) if total_spend > 0 else 0
cpa = (total_spend / total_converted) if total_converted > 0 else 0
avg_save_rate = spot_df['Save Rate'].mean() if not spot_df.empty else 0

col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
col_kpi1.metric("💰 Blended ROAS", f"{roas:.2f}x", help="Total Royalty Earnings / Total Ad Spend")
col_kpi2.metric("🎯 True CPA", f"${cpa:.2f}", help="Total Spend / Converted Listeners")
col_kpi3.metric("❤️ Avg. Save Rate", f"{avg_save_rate:.1f}%", help="Average Save Rate across all Spotify Campaigns")
col_kpi4.metric("🎧 Total Streams", f"{total_streams:,.0f}", help="Total Streams across all platforms")

st.divider()

# --- ROW 2: THE TRENDS (Visuals) ---
st.subheader("🌍 Platform & Geographic Trends")
col_v1, col_v2 = st.columns([1, 1])

with col_v1:
    daily_country = dk_df.groupby(['Reporting Date', 'Country of Sale'])['Quantity'].sum().reset_index()
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
        st.write("Insufficient geographic data.")

with col_v2:
    store_streams = dk_df.groupby('Store')['Quantity'].sum().reset_index().sort_values(by='Quantity', ascending=False).head(8)
    st.altair_chart(
        alt.Chart(store_streams).mark_bar().encode(
            x=alt.X('Quantity:Q', title='Total Streams'),
            y=alt.Y('Store:N', sort='-x', title=''),
            color=alt.Color('Store:N', legend=None)
        ),
        use_container_width=True
    )

st.divider()

# --- ROW 3: THE STRATEGY (Anomaly Engine) ---
st.subheader("🤖 Strategic Anomaly Engine (Ready for CMO)")
st.markdown("Copy this text and paste it into your AI assistant for strategic advice.")
st.code(ai_brief, language="markdown")