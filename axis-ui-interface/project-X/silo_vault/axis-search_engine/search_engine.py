# search_engine.py
# AXIS Search Engine Module - Dual-Channel Live Web Scraper & Context Feeder
# Fetches live results from DuckDuckGo endpoints concurrently, parses text snippets,
# and formats them for both user browsing and NEXXUS context integration.

import requests
import re
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor
from html import unescape

def clean_html_tags(raw_text: str) -> str:
    """Strips HTML markup and decodes entities for clean text consumption."""
    if not raw_text:
        return ""
    clean = re.sub(r'<[^>]+>', '', raw_text)
    return unescape(clean).strip()

def parse_duckduckgo_html(html_content: str) -> list:
    """Parses titles, links, and snippets from DuckDuckGo HTML output."""
    results = []
    if not html_content:
        return results
   
    # Match standard result blocks in duckduckgo html/lite layout
    # Looking for result links and snippet bodies
    try:
        # Simple pattern matching for results
        links = re.findall(r'<a[^>]*class="[^"]*result__url[^"]*"[^>]*>(.*?)</a>', html_content, re.DOTALL)
        snippets = re.findall(r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', html_content, re.DOTALL)
       
        # Fallback for lite/html alternative layout structures
        if not snippets:
            snippets = re.findall(r'class="result-snippet"[^>]*>(.*?)</td>', html_content, re.DOTALL)

        for i in range(min(len(snippets), 5)):
            clean_snippet = clean_html_tags(snippets[i])
            if clean_snippet:
                results.append({
                    "index": i + 1,
                    "snippet": clean_snippet
                })
    except Exception:
        pass
       
    # If regex parsing yields zero structured snippets, fallback to text blocks
    if not results:
        # Extract raw text chunks that look meaningful
        lines = [clean_html_tags(line) for line in html_content.split('\n') if len(line.strip()) > 40]
        for idx, line in enumerate(lines[:5]):
            results.append({"index": idx + 1, "snippet": line})

    return results

def fetch_source(name, url, headers):
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            parsed_results = parse_duckduckgo_html(response.text)
            return {
                "source": name,
                "status": "success",
                "parsed_results": parsed_results,
                "raw_content_preview": response.text[:300] # Truncated for telemetry preview
            }
    except Exception as e:
        pass
        
    return {"source": name, "status": "failed", "parsed_results": [], "raw_content_preview": None}

def search_web(query: str) -> dict:
    """
    Executes concurrent queries across DuckDuckGo search endpoints,
    aggregating clean web data for both user review and NEXXUS grounding.
    """
    sources = {
        "duckduckgo": f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
        "secondary_lookup": f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}"
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
   
    raw_source_outputs = []

    # Fan out requests concurrently across multiple sources
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(fetch_source, name, url, headers): name for name, url in sources.items()}
        for future in futures:
            raw_source_outputs.append(future.result())

    # Consolidate and flatten snippets for easy reading
    consolidated_snippets = []
    for source_res in raw_source_outputs:
        if source_res.get("status") == "success":
            for item in source_res.get("parsed_results", []):
                if item not in consolidated_snippets:
                    consolidated_snippets.append(item)

    return {
        "query": query,
        "total_sources_queried": len(sources),
        "aggregated_snippets": consolidated_snippets,
        "raw_sources": raw_source_outputs
    }

if __name__ == "__main__":
    test_query = "Python programming"
    print(f"Running test search for: '{test_query}'...\n")
    results = search_web(test_query)
   
    print(f"Query: {results['query']}")
    print(f"Total Sources Queried: {results['total_sources_queried']}\n")
    print("--- Extracted Web Snippets (For You & NEXXUS) ---")
    for snippet_obj in results.get("aggregated_snippets", []):
        print(f"[{snippet_obj.get('index')}] {snippet_obj.get('snippet')}")