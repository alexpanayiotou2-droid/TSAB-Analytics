# TSAB Dashboard UX/UI Guardrails & Mandates

This document sets the strict visual standards for the TSAB frontend. Antigravity agents are prohibited from modifying or refactoring code layout blocks in `dashboard-frontend/` unless they perfectly comply with these rules.

## 1. Prime Executive Hierarchy
The dashboard layout must strictly preserve this top-to-bottom visual hierarchy to ensure an immediate 5-second cognitive grasp of band data:
1.  **Vitals Row (Top):** Key high-level metric cards layout.
2.  **Visual Trends Panel (Middle):** Geographic/Platform interactive charts (`st.columns([1, 1])`).
3.  **AI Strategy Brief (Bottom):** Contained entirely inside an `st.expander`.

## 2. Metric Preservation & Tooltips
* **Contextual Education:** The custom `render_metric` helper function must always keep its `help=` parameters active. Every top-line card (Blended ROAS, Upfront CPA, Save Rate, Phantom Spend) must feature its hover tooltips.
* **Layout Safety:** Moving data fetching backend elements to Supabase must *never* replace this custom card visualization framework with generic, raw dataframes.

## 3. Sidebar Filtering & Dynamic Binding
* **The Global Control:** The primary track dropdown filter must remain titled `"🎯 Select View"` and live in the sidebar.
* **The Cascade Effect:** Selecting a specific track must filter both frontend data scopes cleanly *before* computing the visual components.
* **The Conditional Rule:** If `"All Catalog (Aggregate)"` is selected, the "Phantom Spend" card must be completely omitted from the layout, and the column layout must re-distribute dynamically via `st.columns`. Show the card only when an individual song is focused.