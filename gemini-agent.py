# gemini_agent.py

from typing import TypedDict
from langgraph.graph import StateGraph
import requests, os, base64
from dotenv import load_dotenv
import google.generativeai as genai
from IPython.display import Image, display



load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

MODEL = "gemini-2.5-flash"


# 🚨 Ensure env vars are defined
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or ""
REPO = os.getenv("GITHUB_REPO") or ""
WORKFLOW_FILE = os.getenv("WORKFLOW_FILE") or ""
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or ""

for name, val in [("GITHUB_TOKEN", GITHUB_TOKEN), ("GITHUB_REPO", REPO),
                  ("WORKFLOW_FILE", WORKFLOW_FILE), ("GEMINI_API_KEY", GEMINI_API_KEY)]:
    if not val:
        raise ValueError(f"{name} is missing in .env")

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}


# 🧠 Shared Graph State
class CIState(TypedDict):
    workflow_yaml: str
    error_log: str
    gemini_suggestion: str

# 🔍 Node 1: Fetch CI run + logs + workflow
def fetch_ci(state: CIState) -> dict:
    runs = requests.get(f"https://api.github.com/repos/{REPO}/actions/runs?status=failure", headers=HEADERS)
    runs.raise_for_status()
    run = runs.json().get("workflow_runs", [])[0]
    run_id = run["id"]

    wf_meta = requests.get(
        f"https://api.github.com/repos/{REPO}/contents/{WORKFLOW_FILE}", headers=HEADERS
    )
    wf_meta.raise_for_status()
    wf_url = wf_meta.json().get("download_url")
    if not wf_url:
        raise ValueError("download_url missing from workflow metadata")
    yaml_content = requests.get(wf_url).text

    logs_resp = requests.get(run["logs_url"], headers=HEADERS)
    logs_resp.raise_for_status()
    log = logs_resp.text

    return {"workflow_yaml": yaml_content, "error_log": log}

# 🤖 Node 2: Analyze failure with Gemini
def analyze_with_gemini(state):
    response = genai.GenerativeModel(MODEL).generate_content(
        f"CI Failure Log:\n{state['error_log']}\n\n"
        "Summarize root cause and suggest a fix."
    )
    return {"gemini_suggestion": response.text}

# ✅ Build the LangGraph pipeline
builder = StateGraph(CIState)
builder.add_node("fetch_ci", fetch_ci)
builder.add_node("analyze", analyze_with_gemini)
builder.add_edge("fetch_ci", "analyze")
builder.set_entry_point("fetch_ci")
builder.set_finish_point("analyze")

graph = builder.compile()

# 🔁 Run the pipeline
if __name__ == "__main__":
    initial: CIState = {"workflow_yaml": "", "error_log": "", "gemini_suggestion": ""}
    final = graph.invoke(initial)

    print("\n--- Workflow Yaml Snippet ---")
    print(final["workflow_yaml"][:200], "...\n")
    print("--- Error Log Snippet ---")
    print(final["error_log"][:200], "...\n")
    print("💡 Gemini Suggestion:\n", final["gemini_suggestion"])



png = graph.get_graph(xray=True).draw_mermaid_png()
with open("pipeline_graph.png", "wb") as f:
    f.write(png)
print("✅ Graph saved to pipeline_graph.png")


