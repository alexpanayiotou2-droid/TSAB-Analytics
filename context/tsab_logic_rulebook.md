# TSAB Dashboard Business Logic Rulebook

This document defines the strict analytical formulas, metrics, and algorithmic triggers for the TSAB Platform. Any automated backend or database updates must preserve these core data rules exactly.

## 1. Top-Line Vitals & Formulas
* **Blended ROAS:** (Total Net Revenue) / (Total Ad Spend across Spotify Campaigns + Meta/IG Campaigns).
* **Upfront CPA:** (Total Ad Spend) / (Total Converted Listeners).
* **Average Save Rate:** (Total Saves) / (Total Listeners) across active promotional tracks.

## 2. The Conditional "Phantom Spend" Metric
* **The Definition:** Represents campaign ad dollars spent on a track that is experiencing an active drop in algorithmic streaming momentum.
* **The Trigger (The ~30% EPS Drop Rule):** If an individual track's Earnings Per Stream (EPS) drops by 30% or more compared to its historical 28-day trailing delta baseline, flag that variance.
* **UI Mandate:** - If "All Catalog (Aggregate)" view is selected: Hide the Phantom Spend vital metric completely from the summary cards row.
  - If a specific track view is selected: Calculate and display the exact Phantom Spend currency value side-by-side with other metrics.

## 3. Decay Curve Retention Model
* **The Rule:** Stream analytics tracking must compute a trailing 28-day delta to capture decay curves after playlist pushers or platform campaigns end. This ensures the band isolates true organic retention versus artificial campaign peaks.