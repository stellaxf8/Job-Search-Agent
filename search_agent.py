"""
search_agent.py
---------------
Searches LinkedIn, Indeed, and Glassdoor for AI BA / Analyst roles
using SerpAPI, then scores each result against your resume using Claude.

Requirements:
    pip install requests anthropic python-dotenv

Environment variables (set in GitHub Secrets):
    SERP_API_KEY   — your SerpAPI key
    ANTHROPIC_API_KEY — your Anthropic API key
"""

import os
import json
import requests
import anthropic
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)

SERP_API_KEY = os.getenv("SERP_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# ── Config ────────────────────────────────────────────────────────────────────

SEARCH_QUERIES = [
    "AI Business Analyst entry level",
    "AI Business Analyst junior",
    "AI ML Business Analyst entry level",
    "AI Analyst entry level",
    "AI Analyst junior",
    "AI Product Analyst entry level",
    "AI Engineer Business Analyst entry level",
]

LOCATION_QUERY = "Vancouver"           # appended to each search query
LOCATION_PARAM = "Vancouver, British Columbia, Canada"  # SerpAPI location param
RESULTS_PER_QUERY = 10  # SerpAPI returns up to 10 per call

SOURCES = {
    "google_jobs": "",  # No site filter — let Google Jobs return results from all boards
}

# Paste your resume text here (plain text, no formatting needed)
RESUME_TEXT = """
Stella Fuentes — AI Analyst / Business Analyst
Vancouver, BC | stella_fuentes@outlook.com

Summary:
Business Analyst and AI specialist with expertise in scoping and delivering
AI-powered automation solutions. Experienced in requirements gathering, user
story development, and process mapping. Azure AI Engineer certified with
hands-on experience across LLM APIs and Python.

Skills:
- Business Analysis: requirements gathering, user stories, process mapping, stakeholder coordination
- Programming: Python, SQL, Node.js
- AI/ML: LLM fine-tuning, prompt engineering, OpenAI API, Anthropic API, RAG
- Tools: Azure AI, Power BI, Replit, Power Automate, Pandas, Plotly

Experience:
AI Analyst / Business Analyst — Red Pill Labs, Vancouver, BC (Jun 2025 – Present)
- Owned end-to-end delivery of RFP analysis tool (Replit/Claude), reducing vendor evaluation from 3 hours to 30 minutes.
- Led discovery and requirements gathering for AI knowledge management tool; developed user stories and functional specifications.
- Built Python automation solutions (Pandas, Scikit-learn) reducing manual processing by 35%.
- Created Power BI dashboards analyzing 50K+ records.

Manager / Bartender — Earls Kitchen + Bar, Surrey, BC (Sep 2017 – Jan 2022)
- Managed 15-person team; drove data-driven operational decision-making.

Projects:
- RFP Analysis & Vendor Intelligence Platform (Jan 2026): AI-powered tool using Claude + Python in Replit.
- Predictive Finance for Credit Union (Apr 2025): AI forecasting model for cash position management.

Education & Certifications:
- Diploma, Business Information Technology Management (AI Management) — BCIT, May 2025
- Microsoft Certified: Azure AI Engineer Associate — May 2026
- Developing LLM Applications with LangChain — DataCamp, Jun 2026
- Talking to AI: Prompt Engineering for PM — PMI, Aug 2025
"""

# ── Job Search ─────────────────────────────────────────────────────────────────

def search_jobs(query: str, source_name: str, site_filter: str) -> list[dict]:
    """Calls SerpAPI Google Jobs search and returns a list of job dicts."""
    params = {
        "engine": "google_jobs",
        "q": f"{query} {LOCATION_QUERY}".strip(),
        "location": LOCATION_PARAM,
        "api_key": SERP_API_KEY,
        "num": RESULTS_PER_QUERY,
    }
    response = requests.get("https://serpapi.com/search", params=params, timeout=15)
    response.raise_for_status()
    data = response.json()

    # Debug — print keys from first job to confirm field names (remove after confirming)
    if data.get("jobs_results"):
        first = data["jobs_results"][0]
        print("  DEBUG job keys:", list(first.keys()))
        print("  DEBUG apply_options:", first.get("apply_options", []))
        print("  DEBUG related_links:", first.get("related_links", []))

    jobs = []
    for job in data.get("jobs_results", []):
        # SerpAPI returns links in multiple places — try each in order
        link = (
            job.get("job_link") or
            job.get("link") or
            (job.get("related_links") or [{}])[0].get("link", "") or
            (job.get("apply_options") or [{}])[0].get("link", "") or
            ""
        )
        jobs.append({
            "title":       job.get("title", ""),
            "company":     job.get("company_name", ""),
            "location":    job.get("location", ""),
            "description": job.get("description", "")[:2000],
            "link":        link,
            "source":      source_name,
            "posted_at":   job.get("detected_extensions", {}).get("posted_at", ""),
            "query":       query,
        })
    return jobs


def fetch_all_jobs() -> list[dict]:
    """Runs all query + source combinations and deduplicates by title + company."""
    all_jobs = []
    seen = set()

    for query in SEARCH_QUERIES:
        for source_name, site_filter in SOURCES.items():
            print(f"  Searching [{source_name}] for: {query}")
            try:
                results = search_jobs(query, source_name, site_filter)
                for job in results:
                    key = (job["title"].lower(), job["company"].lower())
                    if key not in seen:
                        seen.add(key)
                        all_jobs.append(job)
            except Exception as e:
                print(f"  Warning: {source_name} search failed for '{query}': {e}")

    print(f"\nTotal unique jobs found: {len(all_jobs)}")
    return all_jobs


# ── Claude Scoring ─────────────────────────────────────────────────────────────

def score_job(job: dict, client: anthropic.Anthropic) -> dict:
    """
    Sends the job description + resume to Claude and returns a structured
    match score with reasoning.
    """
    prompt = f"""You are a job match evaluator. Score how well this candidate's resume matches the job posting.

RESUME:
{RESUME_TEXT}

JOB POSTING:
Title: {job['title']}
Company: {job['company']}
Location: {job['location']}
Description: {job['description']}

Rules:
- If the job title or description indicates a Senior, Lead, Principal, or Director level role, set match_score below 40.

Return ONLY a JSON object with these exact keys:
{{
  "match_score": <integer 0-100>,
  "match_reason": "<one sentence why it is or isn't a strong match>",
  "missing_skills": ["<skill1>", "<skill2>"],
  "highlight_bullets": ["<most relevant resume bullet 1>", "<most relevant resume bullet 2>"]
}}

No preamble, no markdown, just the JSON object."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    try:
        scored = json.loads(raw)
    except json.JSONDecodeError:
        scored = {"match_score": 0, "match_reason": "Parsing error", "missing_skills": [], "highlight_bullets": []}

    return {**job, **scored}


def score_all_jobs(jobs: list[dict]) -> list[dict]:
    """Scores all jobs and returns sorted by match_score descending."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    scored_jobs = []

    for i, job in enumerate(jobs, 1):
        print(f"  Scoring {i}/{len(jobs)}: {job['title']} @ {job['company']}")
        scored = score_job(job, client)
        scored_jobs.append(scored)

    scored_jobs.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return scored_jobs


# ── Save Results ───────────────────────────────────────────────────────────────

def save_results(scored_jobs: list[dict]) -> str:
    """Saves results to a timestamped JSON file and returns the filepath."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"job_results_{timestamp}.json"
    with open(filename, "w") as f:
        json.dump(scored_jobs, f, indent=2)
    print(f"\nResults saved to: {filename}")
    return filename


# ── Main ───────────────────────────────────────────────────────────────────────

def run():
    print("=== Job Search Agent: Starting ===\n")

    print("Step 1: Fetching jobs...")
    jobs = fetch_all_jobs()

    print("\nStep 2: Scoring jobs with Claude...")
    scored_jobs = score_all_jobs(jobs)

    print("\nStep 3: Saving results...")
    output_file = save_results(scored_jobs)

    # Print top 5 matches to console
    print("\n=== Top 5 Matches ===")
    for job in scored_jobs[:5]:
        score = job.get("match_score", 0)
        print(f"  {score}% — {job['title']} @ {job['company']} ({job['source']})")
        print(f"         {job.get('match_reason', '')}")

    return scored_jobs, output_file


if __name__ == "__main__":
    run()
