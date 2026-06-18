# UI Update Blueprint: Brand Asset & Theme Integration

This blueprint details the layout hooks, assets, and styling modifications required to incorporate the Socially Acceptable branding into the TSAB Cloud-Ready ROI Dashboard.

---

## 1. Visual Hierarchy & Brand Layout Adjustments

To keep the dashboard clean and centered on the **"Executive Flow"** (Vitals on top, Trends in middle), we will place the main branding in the sidebar. This introduces the brand instantly without cluttering the main content cards.

### Sidebar Branding Section (Vertical Lockup)
- **Top Element**: Center the "bird solo" logo ([Bird solo.png](file:///c:/Users/alexp/OneDrive/Documents/Agents/tsab-analytics-platform/dashboard-frontend/assets/Bird%20solo.png)) as a modern icon mark.
- **Middle Element**: Render the typographic name design ([SA_Fill_Black.png](file:///c:/Users/alexp/OneDrive/Documents/Agents/tsab-analytics-platform/dashboard-frontend/assets/SA_Fill_Black.png)) immediately underneath.
- **Bottom Element**: A thin brand divider in "Mechanical Amber" to separate the brand block from the file upload filters.

---

## 2. Streamlit Native Layout Hooks

Instruct the developer to add the following brand loading code block at the start of [tsab_analytics_app.py](file:///c:/Users/alexp/OneDrive/Documents/Agents/tsab-analytics-platform/dashboard-frontend/tsab_analytics_app.py) (immediately after page config and environment setup, around line 31):

```python
import os

# --- BRANDING LAYOUT HOOKS ---
# Resolve absolute paths to assets safely relative to file location
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
```

---

## 3. Brand Color Theme Integration (Mechanical Amber)

To apply the logo color palette consistently without overwhelming the user:
- We establish **#FBAD30** ("Mechanical Amber") as the primary color.
- We run the app in a dark-mode baseline to let the amber accents highlight metric trends, active buttons, and charts.

### A. Streamlit Theme Configuration
Instruct the developer to create a `.streamlit/config.toml` file in the `dashboard-frontend` directory with these contents:

```toml
[theme]
primaryColor = "#FBAD30"
backgroundColor = "#0E1117"
secondaryBackgroundColor = "#1E1E24"
textColor = "#FAFAFA"
font = "sans serif"
```

### B. High-Fidelity CSS Injections
To style metric cards, invert the black wordmark for dark mode, and align UI spacing, inject the following CSS block into the main app file using `st.markdown`:

```python
# Inject custom CSS for premium branding
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
```

### C. Chart Accent Color Updates
Update the Altair store chart in [tsab_analytics_app.py](file:///c:/Users/alexp/OneDrive/Documents/Agents/tsab-analytics-platform/dashboard-frontend/tsab_analytics_app.py) (around line 520) to utilize a clean amber color scheme rather than random nominal colors. Change the color parameter to:

```python
# Replace color=alt.Color('Store:N', legend=None) with:
color=alt.value('#FBAD30')
```

---

## 4. Contextual Tooltips

To protect the "Executive Flow" and make metrics immediately understandable:
- **💰 Blended ROAS**: `help="Blended Return on Ad Spend. Calculated as: Total Royalty Earnings / Total Ad Spend (Spotify + Meta)."`
- **🎯 Upfront CPA**: `help="Upfront Cost per Acquisition. Calculated as: Total Ad Spend / Converted Listeners on Spotify."`
- **👻 Phantom Spend**: `help="Algorithmic royalty discount. Represents the estimated value of royalties sacrificed in Discovery Mode to secure organic algorithmic streams."`
- **❤️ Avg. Save Rate**: `help="The average campaign save rate. Rates above 10% indicate high listener intent and signal potential algorithmic recommendation uplift."`
