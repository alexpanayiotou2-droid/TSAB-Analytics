# UI Update Blueprint: Brand Asset & Light Theme Integration (Revision 1)

This blueprint details the layout hooks, assets, and styling modifications required to incorporate the Socially Acceptable branding into a premium, high-contrast light theme for the TSAB Cloud-Ready ROI Dashboard.

---

## 1. Visual Hierarchy & Brand Layout Adjustments

- **Sidebar Branding**: Display *only* the typographic wordmark ([SA_Fill_Black.png](file:///c:/Users/alexp/OneDrive/Documents/Agents/tsab-analytics-platform/dashboard-frontend/assets/SA_Fill_Black.png)) at the top of the sidebar. The "bird solo" logo is removed from the sidebar to prevent visual repetition.
- **Main Header Branding**: The guitar emoji (`🎸`) in the page title is replaced with the "bird solo" logo ([Bird solo.png](file:///c:/Users/alexp/OneDrive/Documents/Agents/tsab-analytics-platform/dashboard-frontend/assets/Bird%20solo.png)) inline with the text.
- **Tab Favicon**: The browser tab icon is updated to use the bird logo.

---

## 2. Streamlit Native Layout Hooks

Apply the following code modifications in [tsab_analytics_app.py](file:///c:/Users/alexp/OneDrive/Documents/Agents/tsab-analytics-platform/dashboard-frontend/tsab_analytics_app.py):

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
Update the sidebar header initialization block to display only the wordmark design:

```python
with st.sidebar:
    # Render typographic brand logo at top of sidebar
    if os.path.exists(wordmark_path):
        st.image(wordmark_path, use_container_width=True, output_format="PNG")
    st.markdown("---")
    
    st.header("Update Data")
    st.markdown("Base data loads from Supabase. Drop new files here to **append** to your history.")
```

---

## 3. Brand Color Theme Integration (Mechanical Amber Light Theme)

### A. Streamlit Theme Configuration
Create (or overwrite) `.streamlit/config.toml` in the `dashboard-frontend` directory with these light-theme specifications:

```toml
[theme]
primaryColor = "#FBAD30"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F8F9FA"
textColor = "#1F2937"
font = "sans serif"
```

### B. Custom CSS Styling (Light Mode)
Inject the following styling block into the app (e.g. immediately after loading environment variables or before the sidebar layout):

```python
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
```

### C. Chart Accent Color Updates
Ensure that the bar chart's color scheme uses the brand's amber color to match the design language (around line 520):

```python
# Update the Altair bar chart color encoding:
color=alt.value('#FBAD30')
```

---

## 4. Contextual Tooltips

- **Blended ROAS**: `help="Blended Return on Ad Spend. Calculated as: Total Royalty Earnings / Total Ad Spend (Spotify + Meta)."`
- **Upfront CPA**: `help="Upfront Cost per Acquisition. Calculated as: Total Ad Spend / Converted Listeners on Spotify."`
- **Phantom Spend**: `help="Algorithmic royalty discount. Represents the estimated value of royalties sacrificed in Discovery Mode to secure organic algorithmic streams."`
- **Avg. Save Rate**: `help="The average campaign save rate. Rates above 10% indicate high listener intent and signal potential algorithmic recommendation uplift."`
