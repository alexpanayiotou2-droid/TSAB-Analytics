import os
import sys
import json
import ssl
import urllib.request
import io
import contextlib
import traceback
import pandas as pd
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP, Context

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Initialize FastMCP
mcp = FastMCP("TSAB Analytics Code Interpreter")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def fetch_table_data(table_name: str) -> pd.DataFrame:
    """Helper to fetch data from Supabase REST API."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment.")
    
    all_data = []
    limit = 1000
    offset = 0
    ssl_context = ssl.create_default_context()
    
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}'
    }
    
    while True:
        endpoint = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table_name}?select=*&limit={limit}&offset={offset}"
        req = urllib.request.Request(endpoint, headers=headers)
        try:
            with urllib.request.urlopen(req, context=ssl_context) as response:
                data = json.loads(response.read().decode('utf-8'))
                if not data:
                    break
                all_data.extend(data)
                if len(data) < limit:
                    break
                offset += limit
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            raise RuntimeError(f"Failed to fetch table '{table_name}' from Supabase: {e.code} - {error_body}")
            
    return pd.DataFrame(all_data)

@mcp.tool()
def list_analytical_tables() -> str:
    """List the names of all the analytical tables available in the Supabase schema."""
    # From supabase_schema.sql, we know the tables include:
    # distrokid_royalties, spotify_campaign_metrics, submithub_submissions, 
    # submithub_credit_purchases, playlist_push_campaigns, playlist_push_placements,
    # musosoup_campaigns, musosoup_placements, instagram_campaign_metrics,
    # instagram_insights_metrics, ima_campaigns, ima_placements
    tables = [
        "distrokid_royalties",
        "spotify_campaign_metrics",
        "submithub_submissions",
        "submithub_credit_purchases",
        "playlist_push_campaigns",
        "playlist_push_placements",
        "musosoup_campaigns",
        "musosoup_placements",
        "instagram_campaign_metrics",
        "instagram_insights_metrics",
        "ima_campaigns",
        "ima_placements"
    ]
    return json.dumps(tables, indent=2)

@mcp.tool()
def get_table_schema(table_name: str) -> str:
    """Get the schema and column details for a specific table.
    
    Args:
        table_name: The name of the table (e.g. 'distrokid_royalties')
    """
    try:
        df = fetch_table_data(table_name)
        if df.empty:
            return f"Table '{table_name}' is empty or not found."
        
        schema_info = {
            "columns": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "row_count": len(df),
            "preview": df.head(3).to_dict(orient="records")
        }
        return json.dumps(schema_info, indent=2)
    except Exception as e:
        return f"Error reading schema: {str(e)}"

@mcp.tool()
def execute_pandas_analysis(script: str) -> str:
    """Executes a Python script for data analysis with pandas.
    
    The script has access to:
    - `pd` (pandas library)
    - `load_table(table_name)` which returns a table from Supabase as a pandas DataFrame.
    
    Only read operations are allowed. Write actions to Supabase are blocked.
    Your script should assign any final output or summary to a variable named `result`.
    If you want to return text or tables, assign them to `result`.
    
    Example script:
        df = load_table('distrokid_royalties')
        result = df.groupby('song_title')['amount'].sum().reset_index().to_string()
    
    Args:
        script: The python code to execute.
    """
    # Create execution namespace
    stdout_capture = io.StringIO()
    
    # Simple, read-only wrapper function for the script to load tables
    cached_tables = {}
    def load_table(table_name: str) -> pd.DataFrame:
        if table_name in cached_tables:
            return cached_tables[table_name]
        df = fetch_table_data(table_name)
        cached_tables[table_name] = df
        return df

    local_namespace = {
        "pd": pd,
        "load_table": load_table,
        "result": None
    }
    
    # Strip env vars to prevent the script from accessing keys directly via os.environ
    original_env = dict(os.environ)
    os.environ.pop("SUPABASE_KEY", None)
    
    try:
        with contextlib.redirect_stdout(stdout_capture):
            # Execute script
            exec(script, {}, local_namespace)
            
        output = stdout_capture.getvalue()
        result_val = local_namespace.get("result")
        
        response = []
        if output:
            response.append("=== Script Standard Output ===")
            response.append(output)
        if result_val is not None:
            response.append("=== Script Analysis Result ===")
            response.append(str(result_val))
            
        if not response:
            return "Script executed successfully with no output. Please assign the final result to the `result` variable."
            
        return "\n".join(response)
        
    except Exception as e:
        tb = traceback.format_exc()
        return f"Script Execution Failed:\nError: {str(e)}\n\nTraceback:\n{tb}"
    finally:
        # Restore environment variables
        os.environ.clear()
        os.environ.update(original_env)

@mcp.tool()
async def run_strategist_agent(query: str, ctx: Context) -> str:
    """Run the advanced strategist agent using LangGraph and pandas to answer analytical queries.
    
    This agent plans, generates code, runs code in a pandas sandbox, critiques the code output to check for errors/generics, and synthesizes a numbers-driven strategic report citing exact metrics.
    
    Args:
        query: The user's query or analysis request (e.g. 'What is our blended ROAS?')
    """
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from strategy_agent.strategist_graph import run_strategist
    return await run_strategist(query, mcp_context=ctx)

if __name__ == "__main__":
    mcp.run()
