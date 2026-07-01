import os
import sys
import json
import ssl
import urllib.request
import traceback
import io
import contextlib
import pandas as pd
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

# Load env vars
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Preflight check for credentials
def fetch_table_data(table_name: str) -> pd.DataFrame:
    """Fetch table data from Supabase."""
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
            raise RuntimeError(f"Failed to fetch table '{table_name}': {e.code} - {error_body}")
            
    return pd.DataFrame(all_data)

def local_execute_pandas(script: str) -> str:
    """Executes pandas script locally in a read-only environment."""
    stdout_capture = io.StringIO()
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
    
    # Strip env vars for execution safety
    original_env = dict(os.environ)
    os.environ.pop("SUPABASE_KEY", None)
    
    try:
        with contextlib.redirect_stdout(stdout_capture):
            exec(script, {}, local_namespace)
            
        output = stdout_capture.getvalue()
        result_val = local_namespace.get("result")
        
        response = []
        if output:
            response.append("=== Standard Output ===")
            response.append(output)
        if result_val is not None:
            response.append("=== Analysis Result ===")
            response.append(str(result_val))
            
        if not response:
            return "Script executed successfully but returned no output/result."
        return "\n".join(response)
    except Exception as e:
        return f"Execution Error: {str(e)}\n{traceback.format_exc()}"
    finally:
        os.environ.clear()
        os.environ.update(original_env)

# Define LangGraph State
class AgentState(TypedDict):
    query: str
    mcp_context: Optional[Any] # FastMCP Context if called via MCP
    plan: str
    code: str
    code_output: str
    critique: str
    history: List[Dict[str, str]]
    final_report: str
    iterations: int

# Read the rulebook
def get_rulebook() -> str:
    rulebook_path = os.path.join(os.path.dirname(__file__), "..", "context", "tsab_logic_rulebook.md")
    try:
        with open(rulebook_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "No rulebook found. Standard music analytics rules apply."

# Read semantic metrics
def get_semantic_metrics() -> str:
    metrics_path = os.path.join(os.path.dirname(__file__), "..", "context", "semantic_metrics.yml")
    try:
        with open(metrics_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "No semantic metrics definition found."

# LLM Helper with fallbacks and sampling support
async def call_llm(prompt: str, system_prompt: str, state: AgentState) -> str:
    ctx = state.get("mcp_context")
    
    # 1. Try MCP Sampling if Context is available
    if ctx and hasattr(ctx, "session") and hasattr(ctx.session, "create_message"):
        try:
            from mcp.types import SamplingMessage, TextContent
            response = await ctx.session.create_message(
                messages=[SamplingMessage(role="user", content=TextContent(type="text", text=prompt))],
                system_prompt=system_prompt,
                max_tokens=2000
            )
            if response and response.content and hasattr(response.content, "text"):
                return response.content.text
            elif hasattr(response, "content") and isinstance(response.content, list) and len(response.content) > 0:
                return response.content[0].text
        except Exception as e:
            print(f"MCP Sampling failed, falling back to direct API: {e}", file=sys.stderr)

    # 2. Fallback to Gemini Direct API
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                system_instruction=system_prompt
            )
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"Gemini API call failed: {e}", file=sys.stderr)

    # 3. Fallback to OpenAI Direct API
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"OpenAI API call failed: {e}", file=sys.stderr)

    raise RuntimeError(
        "No LLM client keys found (GEMINI_API_KEY or OPENAI_API_KEY) and MCP client sampling was unavailable or failed. "
        "Please set an API key in your .env file."
    )

# Node 1: Plan Analysis
async def plan_node(state: AgentState) -> dict:
    rulebook = get_rulebook()
    semantic_metrics = get_semantic_metrics()
    prompt = f"""We need to analyze the Supabase database to answer this user query: "{state['query']}".
    
    Here is our Business Logic Rulebook:
    {rulebook}
    
    Here are our Semantic Metrics & Classification Rules:
    {semantic_metrics}
    
    Please formulate an analytical plan. Identify which tables and fields we need to query.
    Keep the plan focused on retrieving the exact metrics requested.
    """
    
    system_prompt = "You are a senior data engineer and strategist. Create a data analysis plan."
    plan = await call_llm(prompt, system_prompt, state)
    return {"plan": plan, "iterations": state.get("iterations", 0) + 1}

# Node 2: Generate Pandas Code
async def code_node(state: AgentState) -> dict:
    rulebook = get_rulebook()
    semantic_metrics = get_semantic_metrics()
    history_str = json.dumps(state.get("history", []), indent=2)
    prompt = f"""Based on the plan, write a Python script using pandas to analyze our Supabase tables.
    
    Plan:
    {state['plan']}
    
    Business Logic Rulebook:
    {rulebook}
    
    Semantic Metrics & Classification Rules:
    {semantic_metrics}
    
    History of attempts:
    {history_str}
    
    Available tables:
    - distrokid_royalties
    - spotify_campaign_metrics
    - submithub_submissions
    - submithub_credit_purchases
    - playlist_push_campaigns
    - playlist_push_placements
    - musosoup_campaigns
    - musosoup_placements
    - instagram_campaign_metrics
    - instagram_insights_metrics
    - ima_campaigns
    - ima_placements
    
    CRITICAL RULES:
    1. You MUST use the helper function `load_table('table_name')` to get a pandas DataFrame for any table. E.g., `df = load_table('distrokid_royalties')`. Do not use any other way to fetch data.
    2. Write standard python/pandas code.
    3. You MUST assign the final output or descriptive table/string to the variable `result`. E.g., `result = output_df.to_string()`.
    4. Print any diagnostic metrics if needed.
    5. Output ONLY the raw Python code. Do not include markdown code block backticks (like ```python) or any other conversational text. Just output pure Python code.
    """
    
    system_prompt = "You are an expert Python data analyst. Output only pure, executable python code."
    code_raw = await call_llm(prompt, system_prompt, state)
    
    # Clean up the output in case the LLM ignored instructions and wrapped in backticks
    code = code_raw.strip()
    if code.startswith("```python"):
        code = code[9:]
    if code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]
    code = code.strip()
    
    return {"code": code}

# Node 3: Execute Code
async def execute_node(state: AgentState) -> dict:
    code = state["code"]
    print(f"--- Executing Pandas Script (Iteration {state.get('iterations', 1)}) ---")
    print(code)
    output = local_execute_pandas(code)
    print(f"--- Execution Output ---")
    print(output)
    return {"code_output": output}

# Node 4: Critique
async def critique_node(state: AgentState) -> dict:
    rulebook = get_rulebook()
    semantic_metrics = get_semantic_metrics()
    prompt = f"""Review the output of our pandas execution to see if it successfully answers the user's question or if there are bugs/errors/generic results.
    
    User Query: {state['query']}
    Code Executed:
    {state['code']}
    
    Code Output:
    {state['code_output']}
    
    Business Logic Rulebook:
    {rulebook}
    
    Semantic Metrics & Classification Rules:
    {semantic_metrics}
    
    Is the analysis mathematically sound, free of errors, and does it directly answer the user's question without being generic?
    If there are errors, explain the error.
    If the result is too generic or missing key rulebook/semantic metrics calculations (like Phantom Spend or ROAS), describe what is missing.
    
    Output a JSON object in this format:
    {{
      "is_valid": true/false,
      "feedback": "Your detailed feedback here"
    }}
    Do not output any other text than the JSON object.
    """
    
    system_prompt = "You are a rigorous code reviewer and data auditor. Output only a valid JSON response."
    response = await call_llm(prompt, system_prompt, state)
    
    # Parse JSON
    try:
        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        data = json.loads(cleaned)
        is_valid = data.get("is_valid", False)
        feedback = data.get("feedback", "")
    except Exception:
        is_valid = False
        feedback = f"Failed to parse critique JSON. Raw output: {response}"
        
    history = state.get("history", [])
    history.append({
        "code": state["code"],
        "output": state["code_output"],
        "feedback": feedback
    })
    
    return {"critique": feedback, "history": history, "is_valid": is_valid}

# Node 5: Synthesize Report
async def synthesize_node(state: AgentState) -> dict:
    rulebook = get_rulebook()
    semantic_metrics = get_semantic_metrics()
    prompt = f"""Write the final strategic recommendation report for the user.
    
    User Query: {state['query']}
    
    Business Logic Rulebook:
    {rulebook}
    
    Semantic Metrics & Classification Rules:
    {semantic_metrics}
    
    Data Analysis Execution Results:
    {state['code_output']}
    
    CRITICAL INSTRUCTIONS:
    1. Do NOT give generic advice. Cite exact numbers, averages, sums, and correlations from the data analysis results.
    2. Explicitly reference the TSAB rulebook metrics (e.g. Blended ROAS, Upfront CPA, Phantom Spend, Decay Curve) and classification categories (e.g. Scale, Seed, Monitor, Cut).
    3. Structure the report with clear headings, key findings, and actionable next steps.
    """
    
    system_prompt = "You are a chief data strategist. Write a highly analytical, numbers-driven strategic report."
    report = await call_llm(prompt, system_prompt, state)
    return {"final_report": report}

# Define conditional routing
def should_continue(state: AgentState):
    # Check if we should iterate or stop
    if state.get("is_valid") == True:
        return "synthesize"
    if state.get("iterations", 0) >= 3:
        # Stop iterating after 3 attempts and synthesize with what we have
        return "synthesize"
    return "generate_code"

# Build Graph
builder = StateGraph(AgentState)
builder.add_node("plan", plan_node)
builder.add_node("generate_code", code_node)
builder.add_node("execute_code", execute_node)
builder.add_node("critique", critique_node)
builder.add_node("synthesize", synthesize_node)

builder.set_entry_point("plan")
builder.add_edge("plan", "generate_code")
builder.add_edge("generate_code", "execute_code")
builder.add_edge("execute_code", "critique")
builder.add_conditional_edges(
    "critique",
    should_continue,
    {
        "generate_code": "generate_code",
        "synthesize": "synthesize"
    }
)
builder.add_edge("synthesize", END)

workflow = builder.compile()

async def run_strategist(query: str, mcp_context: Optional[Any] = None) -> str:
    """Run the strategist workflow."""
    initial_state = {
        "query": query,
        "mcp_context": mcp_context,
        "plan": "",
        "code": "",
        "code_output": "",
        "critique": "",
        "history": [],
        "final_report": "",
        "iterations": 0
    }
    final_state = await workflow.ainvoke(initial_state)
    return final_state["final_report"]

if __name__ == "__main__":
    # Test harness for local CLI execution
    if len(sys.argv) > 1:
        import asyncio
        query_input = sys.argv[1]
        print(f"Running strategist for: {query_input}")
        res = asyncio.run(run_strategist(query_input))
        print(res)
    else:
        print("Usage: python strategist_graph.py '<query>'")
