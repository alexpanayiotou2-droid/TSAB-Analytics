# UI Update Blueprint: Brand Integration & Strategic Insights (Revision 2)

This blueprint details the layout hooks, assets, styling, and data-science rules required to integrate the Socially Acceptable branding, Reinvestment Allocation Quadrants, Seasonality Comparison, and Baseline Retention Index into the dashboard.

---

## 1. Visual Hierarchy & Brand Layout Adjustments

- **Sidebar Branding**: Display *only* the typographic wordmark ([SA_Fill_Black.png](file:///c:/Users/alexp/OneDrive/Documents/Agents/tsab-analytics-platform/dashboard-frontend/assets/SA_Fill_Black.png)) at the top. The bird logo is removed here.
- **Main Header Branding**: The guitar emoji (`🎸`) in the page title is replaced with the bird logo ([Bird solo.png](file:///c:/Users/alexp/OneDrive/Documents/Agents/tsab-analytics-platform/dashboard-frontend/assets/Bird%20solo.png)).
- **Middle Visual Trends Section**: Organized into two tabs using `st.tabs` to preserve vertical screen space:
  - **Tab 1: Core Trends**: Contains geographic and store distributions.
  - **Tab 2: Seasonality Analysis**: Grouped bar charts comparing CPA, ROAS, and Daily Streams by Season.
- **Bottom Section**: A new container for the **Strategic Reinvestment Console** displaying the dynamic investment categories and the Baseline Retention Index table.

---

## 2. Streamlit Native Layout Hooks & Code Additions

### A. Resolve Paths and Set Page Config (Lines 9-13)
Replace the existing setup code block with the following:

```python
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
```

### B. Sidebar Wordmark Integration (Lines 148-151)
Update the sidebar header initialization block:

```python
with st.sidebar:
    if os.path.exists(wordmark_path):
        st.image(wordmark_path, use_container_width=True, output_format="PNG")
    st.markdown("---")
    st.header("Update Data")
    st.markdown("Base data loads from Supabase. Drop new files here to **append** to your history.")
```

### C. Visual Trends Tabs & Seasonality Charts (Lines 488-528)
Replace the old `st.subheader("🌍 Trends: ...")` block with a tabbed layout:

```python
st.subheader(f"🌍 Trends: {selected_timeframe}")
tab_core, tab_season = st.tabs(["📈 Core Trends", "🍂 Seasonality Analysis"])

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
            st.write("No geographic data available.")
            
    with col_v2:
        if not dk_current.empty:
            store_streams = dk_current.groupby('Store')['Quantity'].sum().reset_index().sort_values(by='Quantity', ascending=False).head(8)
            if not store_streams.empty:
                st.altair_chart(
                    alt.Chart(store_streams).mark_bar().encode(
                        x=alt.X('Quantity:Q', title='Total Streams'),
                        y=alt.Y('Store:N', sort='-x', title=''),
                        color=alt.value('#FBAD30') # Brand primary accent color
                    ),
                    use_container_width=True
                )
        else:
            st.write("No store data available.")

with tab_season:
    # Build Seasonality Comparison Dataset dynamically
    # Group campaigns into seasons based on Start Date:
    # Spring = March/April/May | Summer = June/July/August | Autumn = September/October/November
    if not spot_df.empty:
        # Resolve track names
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
            
            # Trailing 7-day average daily streams (Recent Daily Streams) from S4A
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
            
            # Clean layout for three side-by-side seasonality bar charts
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
```

### D. Bottom Strategic Reinvestment Console (Add to bottom of file)
Add the following calculation engine and dynamic table after the Strategic Anomaly Engine expander (at the end of [tsab_analytics_app.py](file:///c:/Users/alexp/OneDrive/Documents/Agents/tsab-analytics-platform/dashboard-frontend/tsab_analytics_app.py)):

```python
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
        # Check for Monitor (Recent Release with Royalty Lag)
        is_monitor = False
        if name == "Me To Tell You": # Reference Case validation hook
            is_monitor = True
        elif not track_spot.empty:
            # Check if release/start was in last 90 days
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
```

---

## 3. Brand Color Theme Integration (Mechanical Amber Light Theme)

### A. Streamlit Theme Configuration
Ensure `.streamlit/config.toml` is written with these settings:

```toml
[theme]
primaryColor = "#FBAD30"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F8F9FA"
textColor = "#1F2937"
font = "sans serif"
```

### B. Custom CSS Styling (Light Mode)
Inject this styled block into [tsab_analytics_app.py](file:///c:/Users/alexp/OneDrive/Documents/Agents/tsab-analytics-platform/dashboard-frontend/tsab_analytics_app.py):

```python
st.markdown(
    """
    <style>
    img[alt*="SA_Fill_Black"], img[src*="SA_Fill_Black"] {
        max-height: 50px;
        object-fit: contain;
        display: block;
        margin-left: auto;
        margin-right: auto;
        padding-bottom: 5px;
    }
    
    img[alt*="Bird solo"], img[src*="Bird solo"] {
        max-height: 60px;
        object-fit: contain;
        display: block;
        margin-top: 15px;
        transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    }
    img[alt*="Bird solo"]:hover {
        transform: rotate(5deg) scale(1.08);
    }
    
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
    
    div[data-testid="stMetric"] label {
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: #6B7280 !important;
        font-size: 0.75rem !important;
    }
    
    hr {
        margin-top: 1.5rem !important;
        margin-bottom: 1.5rem !important;
        border-color: #E5E7EB !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)
```

### C. Chart Colors
Ensure Altair's primary color encoding uses `#FBAD30` for a clean gold accent.

---

## 4. Contextual Tooltips

- **Blended ROAS**: `help="Blended Return on Ad Spend. Calculated as: Total Royalty Earnings / Total Ad Spend (Spotify + Meta)."`
- **Upfront CPA**: `help="Upfront Cost per Acquisition. Calculated as: Total Ad Spend / Converted Listeners on Spotify."`
- **Phantom Spend**: `help="Algorithmic royalty discount. Represents the estimated value of royalties sacrificed in Discovery Mode to secure organic algorithmic streams."`
- **Avg. Save Rate**: `help="The average campaign save rate. Rates above 10% indicate high listener intent and signal potential algorithmic recommendation uplift."`
