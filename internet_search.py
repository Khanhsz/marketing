import requests
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


def fetch_wikipedia_summary(title: str):
    """Return a short summary from Wikipedia for the given title."""
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
    resp = requests.get(url, timeout=5)
    if resp.status_code == 200:
        data = resp.json()
        return data.get("extract")
    return None
