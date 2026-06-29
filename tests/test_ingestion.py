import os
import sys
import pytest

# Add data-backend to sys.path to allow importing ingest_historical_data
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'data-backend'))

import ingest_historical_data

def test_parse_date():
    # ISO-8601 YYYY-MM-DD
    assert ingest_historical_data.parse_date("2026-05-27") == "2026-05-27"
    
    # M/D/YY with UTC suffix
    assert ingest_historical_data.parse_date("3/6/26 UTC") == "2026-03-06"
    
    # M/D/YYYY
    assert ingest_historical_data.parse_date("12/25/2025") == "2025-12-25"
    
    # Empty/NA inputs
    assert ingest_historical_data.parse_date("") is None
    assert ingest_historical_data.parse_date("NA") is None
    assert ingest_historical_data.parse_date(None) is None
    
    # Invalid formats
    with pytest.raises(ValueError):
        ingest_historical_data.parse_date("2026/05/27")
    with pytest.raises(ValueError):
        ingest_historical_data.parse_date("invalid-date")


def test_parse_numeric():
    # Standard float strings
    assert ingest_historical_data.parse_numeric("123.45") == 123.45
    
    # Currency symbol and commas
    assert ingest_historical_data.parse_numeric("$1,234.56") == 1234.56
    
    # Percentage symbol
    assert ingest_historical_data.parse_numeric("13.95%") == 13.95
    
    # Empty/NA inputs with defaults
    assert ingest_historical_data.parse_numeric("", 10.0) == 10.0
    assert ingest_historical_data.parse_numeric("NA", 0.0) == 0.0
    assert ingest_historical_data.parse_numeric(None, 5.5) == 5.5
    
    # Invalid floats fallback to default
    assert ingest_historical_data.parse_numeric("not-a-number", 99.9) == 99.9


def test_parse_int():
    # Standard integer strings
    assert ingest_historical_data.parse_int("123") == 123
    
    # Integers with commas
    assert ingest_historical_data.parse_int("8,065") == 8065
    
    # Empty/NA inputs with defaults
    assert ingest_historical_data.parse_int("", 10) == 10
    assert ingest_historical_data.parse_int("NA", 0) == 0
    assert ingest_historical_data.parse_int(None, 5) == 5
    
    # Invalid ints fallback to default
    assert ingest_historical_data.parse_int("not-an-int", 99) == 99


def test_transform_distrokid_rows():
    raw_rows = [
        {
            'Date Inserted': '6/12/26 UTC',
            'Reporting Date': '6/1/26 UTC',
            'Sale Month': '2026-06',
            'Store': 'Spotify',
            'Artist': 'The Antigravitys',
            'Title': 'Agentic Flow',
            'ISRC': 'US1234567890',
            'UPC': '190000000000',
            'Quantity': '1,500',
            'Team Percentage': '100.00%',
            'Source Type': 'Premium',
            'Country of Sale': 'US',
            'Songwriter Royalties Withheld (USD)': '$0.00',
            'Earnings (USD)': '$15.50',
            'Recoup (USD)': '$0.00'
        },
        {
            # Invalid row missing required field Artist
            'Date Inserted': '6/12/26 UTC',
            'Reporting Date': '6/1/26 UTC',
            'Sale Month': '2026-06',
            'Store': 'Apple Music',
            'Artist': '',
            'Title': 'Agentic Flow',
            'ISRC': 'US1234567890',
            'UPC': '190000000000',
            'Quantity': '100',
            'Team Percentage': '100.00%',
            'Source Type': 'Purchased',
            'Country of Sale': 'UK',
            'Songwriter Royalties Withheld (USD)': '$0.00',
            'Earnings (USD)': '$1.20',
            'Recoup (USD)': '$0.00'
        }
    ]
    
    transformed = ingest_historical_data.transform_distrokid_rows(raw_rows)
    
    # Valid row should be transformed, invalid row skipped
    assert len(transformed) == 1
    
    item = transformed[0]
    assert item['date_inserted'] == "2026-06-12"
    assert item['reporting_date'] == "2026-06-01"
    assert item['sale_month'] == "2026-06"
    assert item['store'] == "Spotify"
    assert item['artist'] == "The Antigravitys"
    assert item['title'] == "Agentic Flow"
    assert item['isrc'] == "US1234567890"
    assert item['upc'] == "190000000000"
    assert item['quantity'] == 1500
    assert item['team_percentage'] == 100.0
    assert item['source_type'] == "Premium"
    assert item['country_of_sale'] == "US"
    assert item['earnings_usd'] == 15.50


def test_transform_spotify_rows():
    raw_rows = [
        {
            'Release Date': '2026-05-01',
            'Start Date': '2026-05-15',
            'End Date': '2026-05-22',
            'Release Name': 'Agentic Flow',
            'Campaign Name': 'Spring Wave',
            'Artist Name': 'The Antigravitys',
            'Format': 'Marquee',
            'Release Type': 'Single',
            'Country Targeting': 'US',
            'Currency': 'USD',
            'Tax Rate': '0.0%',
            'Budget': '$500.00',
            'Budget (incl. tax)': '$500.00',
            'Spend': '$450.00',
            'Spend (incl. tax)': '$450.00',
            'Segment Targeting': 'Reactivated',
            'Reach': '10,000',
            'Clicks': '500',
            'Converted Listeners': '300'
        },
        {
            # Invalid row missing required field Start Date
            'Release Date': '2026-05-01',
            'Start Date': '',
            'End Date': '2026-05-22',
            'Release Name': 'Agentic Flow',
            'Campaign Name': 'Spring Wave',
            'Artist Name': 'The Antigravitys',
            'Format': 'Marquee',
            'Budget': '$500.00'
        }
    ]
    
    transformed = ingest_historical_data.transform_spotify_rows(raw_rows)
    
    # Valid row should be transformed, invalid row skipped
    assert len(transformed) == 1
    
    item = transformed[0]
    assert item['release_date'] == "2026-05-01"
    assert item['start_date'] == "2026-05-15"
    assert item['end_date'] == "2026-05-22"
    assert item['release_name'] == "Agentic Flow"
    assert item['campaign_name'] == "Spring Wave"
    assert item['artist_name'] == "The Antigravitys"
    assert item['budget'] == 500.0
    assert item['spend'] == 450.0
    assert item['reach'] == 10000
    assert item['clicks'] == 500
    assert item['converted_listeners'] == 300
