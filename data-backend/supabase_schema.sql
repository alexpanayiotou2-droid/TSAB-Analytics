-- Supabase PostgreSQL Schema Definition
-- Target: data-backend/supabase_schema.sql
-- Generated for TSAB Analytics Platform Migration

-- Enable pgcrypto for gen_random_uuid() support (standard in Supabase)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

--------------------------------------------------------------------------------
-- 1. TABLES
--------------------------------------------------------------------------------

-- Table: distrokid_royalties
-- Houses actual CSV data from "DistroKid Results 6.12.26.csv"
CREATE TABLE IF NOT EXISTS distrokid_royalties (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date_inserted DATE,
    reporting_date DATE NOT NULL,
    sale_month VARCHAR(7) NOT NULL, -- Format 'YYYY-MM'
    store VARCHAR(255) NOT NULL,
    artist VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    isrc VARCHAR(20) NOT NULL,
    upc VARCHAR(20) NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    team_percentage NUMERIC(5, 2) NOT NULL DEFAULT 100.00, -- Replaces expected 'Client pro-rata'
    source_type VARCHAR(50) NOT NULL, -- Replaces expected 'Track/Album'
    country_of_sale VARCHAR(10) NOT NULL,
    songwriter_royalties_withheld_usd NUMERIC(15, 6) DEFAULT 0.000000,
    earnings_usd NUMERIC(20, 12) NOT NULL DEFAULT 0.000000000000,
    recoup_usd NUMERIC(15, 6) DEFAULT 0.000000,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Table: spotify_campaign_metrics
-- Houses actual CSV data from "Spotify Campaigns to date 6.12.26.csv"
CREATE TABLE IF NOT EXISTS spotify_campaign_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    release_date DATE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    release_name VARCHAR(255) NOT NULL, -- Replaces expected 'Track Target'
    campaign_name VARCHAR(255) NOT NULL,
    artist_name VARCHAR(255) NOT NULL,
    format VARCHAR(100),
    release_type VARCHAR(50),
    country_targeting VARCHAR(100),
    currency VARCHAR(10) NOT NULL DEFAULT 'USD',
    tax_rate NUMERIC(6, 4) DEFAULT 0.0000, -- E.g. '0.000%' parsed to 0.0000
    budget NUMERIC(12, 2) DEFAULT 0.00,
    budget_incl_tax NUMERIC(12, 2) DEFAULT 0.00,
    spend NUMERIC(12, 2) NOT NULL DEFAULT 0.00, -- Replaces expected 'Ad Spend'
    spend_incl_tax NUMERIC(12, 2) DEFAULT 0.00,
    segment_targeting VARCHAR(100),
    reach INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    amplified_listeners INTEGER NOT NULL DEFAULT 0,
    reactivated_listeners INTEGER NOT NULL DEFAULT 0,
    new_active_listeners INTEGER NOT NULL DEFAULT 0, -- Replaces expected 'New Listeners'
    light_listeners_after_converting INTEGER NOT NULL DEFAULT 0,
    moderate_listeners_after_converting INTEGER NOT NULL DEFAULT 0,
    super_listeners_after_converting INTEGER NOT NULL DEFAULT 0,
    converted_listeners INTEGER NOT NULL DEFAULT 0,
    conversion_rate NUMERIC(6, 4) NOT NULL DEFAULT 0.0000, -- E.g. '1.07%' parsed to 1.07 or 0.0107
    active_streams_per_listener NUMERIC(8, 4) NOT NULL DEFAULT 0.0000,
    intent_rate NUMERIC(6, 4) NOT NULL DEFAULT 0.0000, -- E.g. '13.95%' parsed to 13.95
    playlist_add_rate NUMERIC(6, 4) NOT NULL DEFAULT 0.0000, -- E.g. '4.65%' parsed to 4.65
    playlist_adds INTEGER NOT NULL DEFAULT 0,
    save_rate NUMERIC(6, 4) NOT NULL DEFAULT 0.0000, -- E.g. '13.95%' parsed to 13.95
    saves INTEGER NOT NULL DEFAULT 0,
    listeners_of_artists_other_releases INTEGER DEFAULT 0,
    active_streams_per_listener_for_artists_other_releases NUMERIC(8, 4) DEFAULT 0.0000,
    saves_of_artists_other_releases INTEGER DEFAULT 0,
    playlist_adds_of_artists_other_releases INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Table: s4a_daily_streams
-- Houses daily Spotify for Artists stream statistics for decay tracking
CREATE TABLE IF NOT EXISTS s4a_daily_streams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL,
    streams INTEGER NOT NULL DEFAULT 0,
    track_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

--------------------------------------------------------------------------------
-- 2. INDEXES
--------------------------------------------------------------------------------

-- DistroKid indexes
CREATE INDEX IF NOT EXISTS idx_distrokid_title ON distrokid_royalties(title);
CREATE INDEX IF NOT EXISTS idx_distrokid_reporting_date ON distrokid_royalties(reporting_date);
CREATE INDEX IF NOT EXISTS idx_distrokid_store ON distrokid_royalties(store);

-- Spotify Campaigns indexes
CREATE INDEX IF NOT EXISTS idx_spotify_release_name ON spotify_campaign_metrics(release_name);
CREATE INDEX IF NOT EXISTS idx_spotify_start_date ON spotify_campaign_metrics(start_date);
CREATE INDEX IF NOT EXISTS idx_spotify_end_date ON spotify_campaign_metrics(end_date);

-- S4A daily streams indexes
CREATE INDEX IF NOT EXISTS idx_s4a_track_name ON s4a_daily_streams(track_name);
CREATE INDEX IF NOT EXISTS idx_s4a_date ON s4a_daily_streams(date);

--------------------------------------------------------------------------------
-- 3. DERIVED METRICS VIEWS
--------------------------------------------------------------------------------

-- View: v_phantom_spend_monthly
-- Computes the monthly Phantom Spend per track based on the ~30% EPS drop trigger rule.
CREATE OR REPLACE VIEW v_phantom_spend_monthly AS
WITH spotify_monthly_royalties AS (
    SELECT
        title AS track_name,
        -- Group reporting dates into calendar months
        DATE_TRUNC('month', reporting_date)::DATE AS sale_month_date,
        SUM(quantity) AS total_quantity,
        SUM(earnings_usd) AS total_earnings_usd
    FROM distrokid_royalties
    WHERE store ILIKE '%Spotify%'
    GROUP BY title, DATE_TRUNC('month', reporting_date)::DATE
),
monthly_eps_with_lag AS (
    SELECT
        track_name,
        sale_month_date,
        total_quantity,
        total_earnings_usd,
        total_earnings_usd / NULLIF(total_quantity, 0) AS eps,
        LAG(total_earnings_usd / NULLIF(total_quantity, 0)) OVER (
            PARTITION BY track_name 
            ORDER BY sale_month_date
        ) AS prev_eps,
        LAG(total_quantity) OVER (
            PARTITION BY track_name 
            ORDER BY sale_month_date
        ) AS prev_quantity
    FROM spotify_monthly_royalties
    WHERE total_quantity > 500 -- Minimum stream threshold from dashboard
)
SELECT
    track_name,
    sale_month_date,
    total_quantity,
    total_earnings_usd,
    eps,
    prev_eps,
    prev_quantity,
    -- Algorithmic trigger: EPS drops by 15% to 35% (approx 30% drop rule) while stream volume grows by > 20%
    CASE 
        WHEN prev_eps IS NOT NULL AND prev_quantity IS NOT NULL AND prev_quantity > 0 AND prev_eps > 0
             AND (eps / prev_eps) >= 0.65 AND (eps / prev_eps) <= 0.85 
             AND (total_quantity::NUMERIC / prev_quantity) > 1.20
        THEN (prev_eps * total_quantity) - total_earnings_usd
        ELSE 0.0
    END AS phantom_spend,
    CASE 
        WHEN prev_eps IS NOT NULL AND prev_quantity IS NOT NULL AND prev_quantity > 0 AND prev_eps > 0
             AND (eps / prev_eps) >= 0.65 AND (eps / prev_eps) <= 0.85 
             AND (total_quantity::NUMERIC / prev_quantity) > 1.20
        THEN TRUE
        ELSE FALSE
    END AS phantom_spend_flag
FROM monthly_eps_with_lag;

-- View: v_track_analytics
-- Main rollup analytics view representing derived columns at the track level.
CREATE OR REPLACE VIEW v_track_analytics AS
WITH track_royalties AS (
    SELECT 
        title AS track_name,
        SUM(earnings_usd) AS total_earnings_usd,
        SUM(quantity) AS total_streams
    FROM distrokid_royalties
    GROUP BY title
),
track_campaigns AS (
    SELECT 
        release_name AS track_name,
        SUM(spend) AS total_spend_usd,
        SUM(converted_listeners) AS total_converted_listeners,
        SUM(saves) AS total_saves,
        AVG(save_rate) AS avg_save_rate,
        AVG(intent_rate) AS avg_intent_rate
    FROM spotify_campaign_metrics
    GROUP BY release_name
),
track_submithub AS (
    SELECT 
        song AS track_name,
        SUM(cost_usd) AS submithub_spend_usd,
        COUNT(CASE WHEN action = 'Approved' THEN 1 END) AS submithub_approvals,
        SUM(estimated_reach) AS submithub_reach
    FROM submithub_submissions
    GROUP BY song
),
track_phantom AS (
    SELECT 
        track_name,
        SUM(phantom_spend) AS total_phantom_spend,
        BOOL_OR(phantom_spend_flag) AS has_phantom_spend_flag
    FROM v_phantom_spend_monthly
    GROUP BY track_name
)
SELECT
    COALESCE(r.track_name, c.track_name, s.track_name) AS track_name,
    COALESCE(r.total_earnings_usd, 0.0) AS total_earnings_usd,
    COALESCE(r.total_streams, 0) AS total_streams,
    (COALESCE(c.total_spend_usd, 0.0) + COALESCE(s.submithub_spend_usd, 0.0)) AS total_spend_usd,
    (COALESCE(c.total_converted_listeners, 0) + COALESCE(s.submithub_approvals, 0)) AS total_converted_listeners,
    COALESCE(c.total_saves, 0) AS total_saves,
    COALESCE(c.avg_save_rate, 0.0) AS avg_save_rate,
    COALESCE(c.avg_intent_rate, 0.0) AS avg_intent_rate,
    -- Derived: Blended ROAS (Royalties / Blended Spend)
    CASE 
        WHEN (COALESCE(c.total_spend_usd, 0.0) + COALESCE(s.submithub_spend_usd, 0.0)) > 0 
        THEN COALESCE(r.total_earnings_usd, 0.0) / (COALESCE(c.total_spend_usd, 0.0) + COALESCE(s.submithub_spend_usd, 0.0))
        ELSE 0.0
    END AS blended_roas,
    -- Derived: Upfront CPA (Blended Spend / Blended Conversions)
    CASE 
        WHEN (COALESCE(c.total_converted_listeners, 0) + COALESCE(s.submithub_approvals, 0)) > 0 
        THEN (COALESCE(c.total_spend_usd, 0.0) + COALESCE(s.submithub_spend_usd, 0.0)) / (COALESCE(c.total_converted_listeners, 0) + COALESCE(s.submithub_approvals, 0))
        ELSE 0.0
    END AS upfront_cpa,
    -- Derived: Phantom Spend Details
    COALESCE(p.total_phantom_spend, 0.0) AS phantom_spend,
    COALESCE(p.has_phantom_spend_flag, FALSE) AS phantom_spend_flag,
    COALESCE(s.submithub_reach, 0) AS submithub_reach
FROM track_royalties r
FULL OUTER JOIN track_campaigns c ON r.track_name = c.track_name
FULL OUTER JOIN track_submithub s ON COALESCE(r.track_name, c.track_name) = s.track_name
LEFT JOIN track_phantom p ON COALESCE(r.track_name, c.track_name, s.track_name) = p.track_name;

-- View: v_campaign_retention_decay
-- Tracks 14-day pre/post campaign stream changes to measure baseline organic lift and retention health.
CREATE OR REPLACE VIEW v_campaign_retention_decay AS
WITH campaign_dates AS (
    SELECT 
        campaign_name,
        release_name AS track_name,
        start_date,
        end_date,
        spend
    FROM spotify_campaign_metrics
),
campaign_pre_streams AS (
    SELECT 
        c.campaign_name,
        c.track_name,
        AVG(s.streams) AS avg_streams_pre
    FROM campaign_dates c
    JOIN s4a_daily_streams s 
      ON s.track_name ILIKE '%' || c.track_name || '%'
     AND s.date >= (c.start_date - INTERVAL '14 days')
     AND s.date < c.start_date
    GROUP BY c.campaign_name, c.track_name
),
campaign_post_streams AS (
    SELECT 
        c.campaign_name,
        c.track_name,
        AVG(s.streams) AS avg_streams_post
    FROM campaign_dates c
    JOIN s4a_daily_streams s 
      ON s.track_name ILIKE '%' || c.track_name || '%'
     AND s.date > c.end_date
     AND s.date <= (c.end_date + INTERVAL '14 days')
    GROUP BY c.campaign_name, c.track_name
)
SELECT 
    c.campaign_name,
    c.track_name,
    c.start_date,
    c.end_date,
    c.spend,
    COALESCE(pre.avg_streams_pre, 0.0) AS avg_streams_pre,
    COALESCE(post.avg_streams_post, 0.0) AS avg_streams_post,
    CASE 
        -- Classifications matching streamlit dashboard logic
        WHEN COALESCE(pre.avg_streams_pre, 0.0) = 0.0 AND COALESCE(post.avg_streams_post, 0.0) > 0.0 THEN 'New Release Lift'
        WHEN COALESCE(pre.avg_streams_pre, 0.0) > 0.0 AND (COALESCE(post.avg_streams_post, 0.0) / pre.avg_streams_pre - 1.0) > 0.20 THEN 'High Retention'
        WHEN COALESCE(pre.avg_streams_pre, 0.0) > 0.0 AND (COALESCE(post.avg_streams_post, 0.0) / pre.avg_streams_pre - 1.0) BETWEEN 0.05 AND 0.20 THEN 'Moderate Retention'
        WHEN COALESCE(pre.avg_streams_pre, 0.0) > 0.0 AND (COALESCE(post.avg_streams_post, 0.0) / pre.avg_streams_pre - 1.0) < 0.05 AND c.spend > 0 THEN 'Empty Calories'
        ELSE 'Maturity / Inactive'
    END AS retention_classification,
    CASE 
        WHEN COALESCE(pre.avg_streams_pre, 0.0) > 0.0 
        THEN (COALESCE(post.avg_streams_post, 0.0) / pre.avg_streams_pre) - 1.0
        ELSE NULL
    END AS baseline_lift
FROM campaign_dates c
LEFT JOIN campaign_pre_streams pre ON c.campaign_name = pre.campaign_name AND c.track_name = pre.track_name
LEFT JOIN campaign_post_streams post ON c.campaign_name = post.campaign_name AND c.track_name = post.track_name;

--------------------------------------------------------------------------------
-- 4. SECURITY & ROW LEVEL SECURITY (RLS) POLICIES
--------------------------------------------------------------------------------

-- 1. Enforce Row Level Security for ALL tables (including S4A)
ALTER TABLE distrokid_royalties ENABLE ROW LEVEL SECURITY;
ALTER TABLE spotify_campaign_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE s4a_daily_streams ENABLE ROW LEVEL SECURITY;

-- 2. CLEAR OUT OLD POLICIES IF THEY EXIST (Idempotent Rerun Safety)
DROP POLICY IF EXISTS "Allow read access to anon users" ON distrokid_royalties;
DROP POLICY IF EXISTS "Allow read access to anon users" ON spotify_campaign_metrics;
DROP POLICY IF EXISTS "Allow read access to anon users" ON s4a_daily_streams;

-- 3. Create fresh read-only policies for your Streamlit frontend
CREATE POLICY "Allow read access to anon users" 
ON distrokid_royalties FOR SELECT 
TO anon, authenticated USING (true);

CREATE POLICY "Allow read access to anon users" 
ON spotify_campaign_metrics FOR SELECT 
TO anon, authenticated USING (true);

CREATE POLICY "Allow read access to anon users" 
ON s4a_daily_streams FOR SELECT 
TO anon, authenticated USING (true);


--------------------------------------------------------------------------------
-- 5. SUBMITHUB TABLES & POLICIES
--------------------------------------------------------------------------------

-- Table: submithub_credit_purchases
CREATE TABLE IF NOT EXISTS submithub_credit_purchases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_date TIMESTAMP WITH TIME ZONE NOT NULL,
    amount_paid_usd NUMERIC(10, 2) NOT NULL,
    credits_purchased INTEGER NOT NULL,
    cost_per_credit NUMERIC(10, 4) GENERATED ALWAYS AS (amount_paid_usd / NULLIF(credits_purchased, 0)) STORED,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Table: submithub_submissions
CREATE TABLE IF NOT EXISTS submithub_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    song VARCHAR(255) NOT NULL,
    campaign_url VARCHAR(255),
    campaign_date TIMESTAMP WITH TIME ZONE,
    outlet VARCHAR(255) NOT NULL,
    outlet_type VARCHAR(100),
    outlet_url VARCHAR(255),
    outlet_country VARCHAR(100),
    action VARCHAR(50) NOT NULL,
    action_timestamp TIMESTAMP WITH TIME ZONE,
    feedback TEXT,
    listen_time_seconds INTEGER,
    credits_spent INTEGER NOT NULL DEFAULT 0,
    credit_type VARCHAR(50),
    is_refunded BOOLEAN NOT NULL DEFAULT FALSE,
    cost_usd NUMERIC(10, 4) DEFAULT 0.0000,
    share_destination VARCHAR(255),
    estimated_reach INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable RLS
ALTER TABLE submithub_credit_purchases ENABLE ROW LEVEL SECURITY;
ALTER TABLE submithub_submissions ENABLE ROW LEVEL SECURITY;

-- Policies
DROP POLICY IF EXISTS "Allow read access to anon users" ON submithub_credit_purchases;
DROP POLICY IF EXISTS "Allow read access to anon users" ON submithub_submissions;

CREATE POLICY "Allow read access to anon users" 
ON submithub_credit_purchases FOR SELECT 
TO anon, authenticated USING (true);

CREATE POLICY "Allow read access to anon users" 
ON submithub_submissions FOR SELECT 
TO anon, authenticated USING (true);


-- Table: playlist_push_campaigns
CREATE TABLE IF NOT EXISTS playlist_push_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    song VARCHAR(255) NOT NULL,
    campaign_date TIMESTAMP WITH TIME ZONE,
    budget_usd NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    total_responses INTEGER NOT NULL DEFAULT 0,
    playlist_adds INTEGER NOT NULL DEFAULT 0,
    total_reach INTEGER NOT NULL DEFAULT 0,
    spotify_popularity INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Table: playlist_push_placements
CREATE TABLE IF NOT EXISTS playlist_push_placements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    song VARCHAR(255) NOT NULL,
    playlist_name VARCHAR(255) NOT NULL,
    curator VARCHAR(255) NOT NULL,
    saves INTEGER NOT NULL DEFAULT 0,
    added_time_ago VARCHAR(100),
    estimated_date TIMESTAMP WITH TIME ZONE,
    playlist_index INTEGER,
    avg_duration_months INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Table: musosoup_campaigns
CREATE TABLE IF NOT EXISTS musosoup_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    song VARCHAR(255) NOT NULL,
    campaign_date DATE,
    budget_gbp NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    budget_usd NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    playlist_adds INTEGER NOT NULL DEFAULT 0,
    other_adds INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Table: musosoup_placements
CREATE TABLE IF NOT EXISTS musosoup_placements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    song VARCHAR(255) NOT NULL,
    curator VARCHAR(255),
    publication VARCHAR(255),
    completion_date TIMESTAMP WITH TIME ZONE,
    accept_type VARCHAR(50),
    contribution_gbp NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    contribution_usd NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    completion_url TEXT,
    placement_type VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable RLS
ALTER TABLE playlist_push_campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE playlist_push_placements ENABLE ROW LEVEL SECURITY;
ALTER TABLE musosoup_campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE musosoup_placements ENABLE ROW LEVEL SECURITY;

-- Policies
DROP POLICY IF EXISTS "Allow read access to anon users" ON playlist_push_campaigns;
DROP POLICY IF EXISTS "Allow read access to anon users" ON playlist_push_placements;
DROP POLICY IF EXISTS "Allow read access to anon users" ON musosoup_campaigns;
DROP POLICY IF EXISTS "Allow read access to anon users" ON musosoup_placements;

CREATE POLICY "Allow read access to anon users" 
ON playlist_push_campaigns FOR SELECT 
TO anon, authenticated USING (true);

CREATE POLICY "Allow read access to anon users" 
ON playlist_push_placements FOR SELECT 
TO anon, authenticated USING (true);

CREATE POLICY "Allow read access to anon users" 
ON musosoup_campaigns FOR SELECT 
TO anon, authenticated USING (true);

CREATE POLICY "Allow read access to anon users" 
ON musosoup_placements FOR SELECT 
TO anon, authenticated USING (true);
