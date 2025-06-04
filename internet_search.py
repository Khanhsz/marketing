import requests


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
