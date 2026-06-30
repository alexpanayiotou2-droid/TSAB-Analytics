import os
import sys
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

# A mock helper that is callable and behaves as a context manager
class MockContextManagerAndCallable:
    def __init__(self, *args, **kwargs):
        pass
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    def __call__(self, *args, **kwargs):
        return self
    def __bool__(self):
        return True
    def __nonzero__(self):
        return True
    def __len__(self):
        return 0
    def __getattr__(self, name):
        return self


# Create robust mock for streamlit module to allow importing and running the dashboard app
class MockStreamlit:
    def __init__(self):
        self.sidebar = MockContextManagerAndCallable()
        
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        m = MockContextManagerAndCallable()
        setattr(self, name, m)
        return m
        
    def set_page_config(self, *args, **kwargs):
        pass
        
    def columns(self, spec, *args, **kwargs):
        if isinstance(spec, int):
            return [MockContextManagerAndCallable() for _ in range(spec)]
        elif isinstance(spec, (list, tuple)):
            return [MockContextManagerAndCallable() for _ in range(len(spec))]
        return [MockContextManagerAndCallable(), MockContextManagerAndCallable()]
        
    def empty(self, *args, **kwargs):
        return MockContextManagerAndCallable()
        
    def spinner(self, *args, **kwargs):
        return MockContextManagerAndCallable()
        
    def tabs(self, tabs_list, *args, **kwargs):
        return [MockContextManagerAndCallable() for _ in tabs_list]
        
    def selectbox(self, label, options, *args, **kwargs):
        if options:
            return list(options)[0]
        return ""
        
    def text_input(self, label, value="", *args, **kwargs):
        return value
        
    def file_uploader(self, *args, **kwargs):
        return None
        
    def cache_data(self, *args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            return args[0]
        def decorator(func):
            return func
        return decorator

mock_st = MockStreamlit()
# Bind sidebar methods to same mock behavior
mock_st.sidebar.selectbox = mock_st.selectbox
mock_st.sidebar.file_uploader = mock_st.file_uploader
mock_st.sidebar.empty = mock_st.empty
mock_st.sidebar.columns = mock_st.columns
mock_st.sidebar.__enter__ = MagicMock()
mock_st.sidebar.__exit__ = MagicMock()

# Inject the mock streamlit module
sys.modules['streamlit'] = mock_st

# Add dashboard-frontend to path and import
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'dashboard-frontend'))
import tsab_analytics_app


def test_column_maps():
    # Verify that maps translate database columns correctly
    assert tsab_analytics_app.DK_COLUMN_MAP['earnings_usd'] == 'Earnings (USD)'
    assert tsab_analytics_app.SPOTIFY_COLUMN_MAP['spend'] == 'Spend'
    assert tsab_analytics_app.SPOTIFY_COLUMN_MAP['campaign_name'] == 'Campaign Name'


def test_load_base_data_no_env():
    # If no env variables are set, load_base_data should fall back to local file
    with patch.dict(os.environ, {}, clear=True):
        df = tsab_analytics_app.load_base_data("distrokid_royalties", "non_existent_file.csv", tsab_analytics_app.DK_COLUMN_MAP)
        assert isinstance(df, pd.DataFrame)
        assert df.empty


def test_stitch_data_processing():
    # Test internal stitch_data function within process_data logic
    dk_base = pd.DataFrame([{
        'Date Inserted': '2026-06-01',
        'Reporting Date': '2026-06-01',
        'Artist': 'The Antigravitys',
        'Earnings (USD)': 10.0,
        'Quantity': 100
    }])
    spot_base = pd.DataFrame()
    s4a_base = pd.DataFrame()
    
    dk_df, spot_df, s4a_df, meta_df, submithub_df, pp_camp_df, pp_place_df, ms_camp_df, ms_place_df, ima_camp_df, ima_place_df = tsab_analytics_app.process_data(
        dk_base_df=dk_base,
        dk_files=None,
        spot_base_df=spot_base,
        spot_files=None,
        s4a_base_df=s4a_base,
        s4a_files=None,
        meta_files=None,
        submithub_base_df=pd.DataFrame(),
        submithub_purchases_base_df=pd.DataFrame(),
        submithub_files=None,
        pp_campaigns_base_df=pd.DataFrame(),
        pp_placements_base_df=pd.DataFrame(),
        pp_files=None,
        ms_campaigns_base_df=pd.DataFrame(),
        ms_placements_base_df=pd.DataFrame(),
        ms_files=None,
        ima_campaigns_base_df=pd.DataFrame(),
        ima_placements_base_df=pd.DataFrame(),
        ima_files=None
    )
    
    assert not dk_df.empty
    assert dk_df.iloc[0]['Artist'] == 'The Antigravitys'
    assert spot_df.empty
    assert s4a_df.empty
    assert meta_df.empty
    assert submithub_df.empty

def test_musosoup_processing():
    ms_campaign_base = pd.DataFrame([{
        'song': 'SH2BA',
        'campaign_date': '2026-06-30',
        'budget_gbp': 36.0,
        'budget_usd': 46.8,
        'playlist_adds': 5,
        'other_adds': 2
    }])
    ms_placement_base = pd.DataFrame([{
        'song': 'SH2BA',
        'curator': 'Curator A',
        'publication': 'Pub A',
        'completion_date': '2026-06-30',
        'accept_type': 'Free',
        'contribution_gbp': 0.0,
        'contribution_usd': 0.0,
        'completion_url': 'http://completion.url',
        'placement_type': 'Playlist'
    }])
    
    dk_df, spot_df, s4a_df, meta_df, submithub_df, pp_camp_df, pp_place_df, ms_camp_df, ms_place_df, ima_camp_df, ima_place_df = tsab_analytics_app.process_data(
        dk_base_df=pd.DataFrame(),
        dk_files=None,
        spot_base_df=pd.DataFrame(),
        spot_files=None,
        s4a_base_df=pd.DataFrame(),
        s4a_files=None,
        meta_files=None,
        submithub_base_df=pd.DataFrame(),
        submithub_purchases_base_df=pd.DataFrame(),
        submithub_files=None,
        pp_campaigns_base_df=pd.DataFrame(),
        pp_placements_base_df=pd.DataFrame(),
        pp_files=None,
        ms_campaigns_base_df=ms_campaign_base,
        ms_placements_base_df=ms_placement_base,
        ms_files=None,
        ima_campaigns_base_df=pd.DataFrame(),
        ima_placements_base_df=pd.DataFrame(),
        ima_files=None
    )
    
    assert not ms_camp_df.empty
    assert ms_camp_df.iloc[0]['song'] == 'SH2BA'
    assert not ms_place_df.empty
    assert ms_place_df.iloc[0]['curator'] == 'Curator A'


def test_ima_processing():
    ima_campaign_base = pd.DataFrame([{
        'song': 'Astronaut',
        'campaign_date': '2024-09-20',
        'budget_usd': 297.0,
        'invoice_id': '000013436',
        'package_name': 'Spotify Playlist Promotion',
        'guaranteed_streams': 10000
    }])
    ima_placement_base = pd.DataFrame([{
        'song': 'Astronaut',
        'playlist_name': 'cooking and dancing in the kitchen',
        'platform': 'Spotify',
        'curator': 'Cookfy',
        'followers': 144687,
        'published_date': '2026-06-04'
    }])
    
    dk_df, spot_df, s4a_df, meta_df, submithub_df, pp_camp_df, pp_place_df, ms_camp_df, ms_place_df, ima_camp_df, ima_place_df = tsab_analytics_app.process_data(
        dk_base_df=pd.DataFrame(),
        dk_files=None,
        spot_base_df=pd.DataFrame(),
        spot_files=None,
        s4a_base_df=pd.DataFrame(),
        s4a_files=None,
        meta_files=None,
        submithub_base_df=pd.DataFrame(),
        submithub_purchases_base_df=pd.DataFrame(),
        submithub_files=None,
        pp_campaigns_base_df=pd.DataFrame(),
        pp_placements_base_df=pd.DataFrame(),
        pp_files=None,
        ms_campaigns_base_df=pd.DataFrame(),
        ms_placements_base_df=pd.DataFrame(),
        ms_files=None,
        ima_campaigns_base_df=ima_campaign_base,
        ima_placements_base_df=ima_placement_base,
        ima_files=None
    )
    
    assert not ima_camp_df.empty
    assert ima_camp_df.iloc[0]['song'] == 'Astronaut'
    assert not ima_place_df.empty
    assert ima_place_df.iloc[0]['curator'] == 'Cookfy'


