import requests
import os
from urllib.parse import quote


def search_duckduckgo(query: str, max_results: int = 5):
    """Search DuckDuckGo for a query and return a list of title/url dicts."""
    url = "https://api.duckduckgo.com/"
    params = {
        "q": query,
        "format": "json",
        "no_html": 1,
        "skip_disambig": 1,
    }
    resp = requests.get(url, params=params, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("RelatedTopics", [])[:max_results]:
        if isinstance(item, dict) and "Text" in item and "FirstURL" in item:
            results.append({"title": item["Text"], "url": item["FirstURL"]})
    return results


def search_google(query: str, max_results: int = 5):
    """Search Google Custom Search and return a list of title/url dicts."""
    api_key = os.getenv("GOOGLE_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID")
    if not api_key or not cse_id:
        return []

    url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": api_key, "cx": cse_id, "q": query}
    resp = requests.get(url, params=params, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("items", [])[:max_results]:
        results.append({"title": item.get("title"), "url": item.get("link")})
    return results


def fetch_wikipedia_summary(title: str):
    """Return a short summary from Wikipedia for the given title."""
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
    resp = requests.get(url, timeout=5)
    if resp.status_code == 200:
        data = resp.json()
        return data.get("extract")
    return None
