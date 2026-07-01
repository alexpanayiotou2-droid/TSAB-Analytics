# UI Update Blueprint: Main Page Tab & Timeline Refactoring (Revision 4)

This blueprint details the layout changes required to implement the 4-tab dashboard system and the enhanced, high-contrast visual timeline for the Launch Playbook. The sidebar and uploader widgets will remain exactly in their original states.

---

## 1. Visual Hierarchy & Brand Layout Overhaul

- **Sidebar (No Changes)**: All 8 uploaders, text instructions, database buttons, and filters in the sidebar remain exactly as-is.
- **Main Page Tab Redesign**: To resolve vertical scroll fatigue, the main dashboard body is reorganized into a 4-tab system:
  1. **`📊 Executive Trends`**: Geographic trends and store stream distributions.
  2. **`📣 PR & Curator Outreach`**: SubmitHub, Playlist Push, Musosoup, and IMA platform dashboards (including placements tables and Curator Feedback Explorer).
  3. **`🧠 Strategic Console`**: Seasonality comparisons, the **Strategic Reinvestment Console** (Layer A/C Table), and the **Strategic Anomaly Engine** (CMO Brief).
  4. **`🎯 Launch Playbook`**: Slide-based campaign timelines and the budget sandbox simulator.

---

## 2. Streamlit Native Layout Hooks & Code Additions

Instruct the developer to apply the following code refactoring in [tsab_analytics_app.py](file:///c:/Users/alexp/OneDrive/Documents/Agents/tsab-analytics-platform/dashboard-frontend/tsab_analytics_app.py):

### Step A: Page Header Setup (Lines 9-33)
Ensure the page title and tab icon utilize the bird logo asset:

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

### Step B: Main Page 4-Tab Restructuring (Lines 2802 onwards)
Replace the old tab layout and bottom-appended sections with the following nested 4-tab layout:

```python
st.subheader(f"🌍 Analysis Dashboard: {selected_timeframe}")
tab_trends, tab_pr, tab_strategy, tab_playbook = st.tabs([
    "📊 Executive Trends", 
    "📣 PR & Curator Outreach",
    "🧠 Strategic Console", 
    "🎯 Launch Playbook"
])

# --- TAB 1: EXECUTIVE TRENDS ---
with tab_trends:
    col_v1, col_v2 = st.columns([1, 1])
    with col_v1:
        st.markdown("##### Geographic Stream Distribution (Top 5 Countries)")
        # ... (Geographic line chart code remains unchanged) ...
    with col_v2:
        st.markdown("##### Store Streaming Distribution")
        # ... (Store bar chart code remains unchanged) ...

# --- TAB 2: PR & CURATOR OUTREACH ---
with tab_pr:
    st.markdown("### PR Channel Outreach & Placement Details")
    pr_platform = st.radio("Select Platform Data to View", ["SubmitHub", "Playlist Push", "Musosoup", "Indie Music Academy"], horizontal=True)
    # ... (SubmitHub, Playlist Push, Musosoup, and IMA visualizer panels and feedback explorer remain unchanged) ...

# --- TAB 3: STRATEGIC CONSOLE ---
with tab_strategy:
    st.markdown("### Strategic Releases & Capital Reinvestment Benchmarks")
    # 1. Seasonality Comparison charts
    # ... (Seasonality calculation and Altair chart code remains unchanged) ...
    st.markdown("---")
    
    # 2. CMO Strategic Anomaly Brief
    st.markdown("#### Dynamic CMO Anomaly Engine")
    with st.expander("🤖 View & Copy Strategic Anomaly Brief", expanded=True):
        st.code(ai_brief, language="markdown")
    st.markdown("---")
    
    # 3. Reinvestment Console & Baseline Lift Table
    st.markdown("#### Strategic Reinvestment Console")
    # ... (Reinvestment Console calculation and dataframe display remains unchanged) ...

# --- TAB 4: LAUNCH PLAYBOOK ---
with tab_playbook:
    # ... (Timeline, budgets, slide buttons, and Interactive Simulator remain unchanged) ...
```

*Note: The subheaders `st.subheader("🤖 Strategic Anomaly Engine...")` and `st.subheader("🤖 Strategic Reinvestment Console")` at the absolute bottom of the file (lines 3399 & 3406) must be removed so they only render inside Tab 3.*

---

## 3. Launch Playbook Slide 4 Enhancements: Timeline Cards

In [tsab_analytics_app.py](file:///c:/Users/alexp/OneDrive/Documents/Agents/tsab-analytics-platform/dashboard-frontend/tsab_analytics_app.py) (around lines 3458-3485), replace the simple dark div blocks with these high-contrast visual timeline cards. This fixes the contrast bugs for light mode and integrates SubmitHub Premium Credits:

```python
    elif slide == "4. 4-Week Timeline":
        st.markdown("### 📅 4-Week Release Campaign Timeline")
        st.markdown("Detailed channel checkpoints, budget targets, and strategic rules for the July 3rd launch.")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(
                """
                <div style="border: 1px solid #E5E7EB; border-left: 5px solid #10B981; border-radius: 12px; padding: 20px; background-color: #FFFFFF; box-shadow: 0 4px 15px rgba(0,0,0,0.03); min-height: 400px; display: flex; flex-direction: column;">
                    <h4 style="color: #059669; margin-top: 0; font-size: 1.15rem; font-weight: 700;">🌱 Step 1. Weeks 1-2: PR Seeding</h4>
                    <h5 style="color: #1F2937; font-size: 0.95rem; font-weight: 600; margin-top: 5px; margin-bottom: 12px;">Budget Allocation: $100</h5>
                    <ul style="font-size: 0.85rem; color: #4B5563; padding-left: 18px; line-height: 1.6; margin-bottom: 0;">
                        <li><b>SubmitHub pitches ($50)</b>: You <b>MUST use Premium Credits</b> (not standard). This guarantees response times within 48 hours, yielding quick playlist additions and immediate curator reviews.</li>
                        <li><b>Musosoup listing ($50)</b>: Launch a 3-week campaign. Accept only verified premium placement offers with high follower reach to maximize efficiency (historical average: $0.62 per add).</li>
                        <li><b>Budget Holds</b>: Keep Playlist Push and Indie Music Academy budgets fully locked. Do not launch raw playlist campaigns before establishing organic listener signals.</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True
            )
        with col2:
            st.markdown(
                """
                <div style="border: 1px solid #E5E7EB; border-left: 5px solid #FBAD30; border-radius: 12px; padding: 20px; background-color: #FFFFFF; box-shadow: 0 4px 15px rgba(0,0,0,0.03); min-height: 400px; display: flex; flex-direction: column;">
                    <h4 style="color: #D97706; margin-top: 0; font-size: 1.15rem; font-weight: 700;">📡 Step 2. Week 3: Algorithmic Seeding</h4>
                    <h5 style="color: #1F2937; font-size: 0.95rem; font-weight: 600; margin-top: 5px; margin-bottom: 12px;">Budget Allocation: $150</h5>
                    <ul style="font-size: 0.85rem; color: #4B5563; padding-left: 18px; line-height: 1.6; margin-bottom: 0;">
                        <li><b>Spotify Showcase ($150)</b>: Launch sponsored recommendations to target active, lapsed, and super listeners. Focus budget solely on high-payout Tier 1 countries (US, UK, DE, CA, AU).</li>
                        <li><b>Exclude Low-Payouts</b>: Do not direct ad budget to Tier 3 countries (India, Philippines, Turkey) or Facebook Catalog formats, which dilute royalties and cause <b>Phantom Spend</b>.</li>
                        <li><b>Goal</b>: Push for high-intent conversion metrics (CPA &le; $0.30 and Save Rate &gt; 20%) to prime the algorithmic recommendation feeds.</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True
            )
        with col3:
            st.markdown(
                """
                <div style="border: 1px solid #E5E7EB; border-left: 5px solid #6366F1; border-radius: 12px; padding: 20px; background-color: #FFFFFF; box-shadow: 0 4px 15px rgba(0,0,0,0.03); min-height: 400px; display: flex; flex-direction: column;">
                    <h4 style="color: #4F46E5; margin-top: 0; font-size: 1.15rem; font-weight: 700;">🚀 Step 3. Week 4: Scaling Decisions</h4>
                    <h5 style="color: #1F2937; font-size: 0.95rem; font-weight: 600; margin-top: 5px; margin-bottom: 12px;">Budget Allocation: $250</h5>
                    <ul style="font-size: 0.85rem; color: #4B5563; padding-left: 18px; line-height: 1.6; margin-bottom: 0;">
                        <li><b>Check Showcase Telemetry</b>: Assess Week 3 Showcase performance. Compare metrics against targets (CPA &lt; $0.25, Save Rate &gt; 20%).</li>
                        <li><b>Scale Path (Green Light)</b>: If targets are met, inject the remaining $250 to accelerate Spotify Home recommendation placement.</li>
                        <li><b>Halt Path (Red Light)</b>: If CPA &gt; $0.35 or Save Rate &lt; 12%, halt active paid promotions immediately to protect capital. Let the track build organic momentum.</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True
            )
```

---

## 4. Brand Color Theme Integration (Mechanical Amber Light Theme)

No changes to the light theme configuration or custom metric card CSS styles. The theme parameters and metric border styles remain active as described in Revisions 1 and 2.
