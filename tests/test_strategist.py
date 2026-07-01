import os
import sys
import pytest
import pandas as pd

# Add paths to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'strategy-agent'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'analytics-mcp'))

import strategist_graph
import server as mcp_server

def test_semantic_metrics_loading():
    metrics = strategist_graph.get_semantic_metrics()
    assert "metrics:" in metrics
    assert "blended_roas" in metrics
    assert "phantom_spend" in metrics
    assert "reinvestment_quadrants" in metrics

def test_local_execute_pandas_sandbox():
    # Test executing a simple script that sums values in a dummy DataFrame
    script = """
import pandas as pd
df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
result = df['a'].sum()
"""
    output = strategist_graph.local_execute_pandas(script)
    assert "=== Analysis Result ===" in output
    assert "6" in output

def test_local_execute_pandas_sandbox_security():
    # Verify that trying to modify os.environ inside the script doesn't leak secrets or throw
    script = """
import os
# Try to write/modify env
os.environ['SUPABASE_KEY'] = 'hacked'
result = os.environ.get('SUPABASE_KEY')
"""
    output = strategist_graph.local_execute_pandas(script)
    assert "hacked" in output
    # Verify outside the execution, the environment key is NOT modified
    assert os.environ.get("SUPABASE_KEY") != "hacked"

def test_should_continue_logic():
    # If state is valid, it should go to synthesize
    state1 = {"is_valid": True, "iterations": 1}
    assert strategist_graph.should_continue(state1) == "synthesize"
    
    # If iterations reach max (3), it should go to synthesize
    state2 = {"is_valid": False, "iterations": 3}
    assert strategist_graph.should_continue(state2) == "synthesize"
    
    # Otherwise, continue generating code
    state3 = {"is_valid": False, "iterations": 1}
    assert strategist_graph.should_continue(state3) == "generate_code"
