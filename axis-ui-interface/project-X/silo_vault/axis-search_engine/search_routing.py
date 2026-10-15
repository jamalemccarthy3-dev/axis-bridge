import requests
from config.search_routing_config import SearchRoutingConfig

class SearchRouting:
    """Engine responsible for directing search queries to the appropriate remote endpoint."""
    def __init__(self):
        self.config = SearchRoutingConfig()
        # You will need to define the axis-triage endpoint in your config
        self.triage_url = "http://axis-triage.local/process"

    def route_query(self, query, query_type="general_search", use_triage=False):
        """Directs the query to the designated remote search node with optional triage."""
        
        # Check if we need to pass through axis-triage first
        if use_triage:
            query = self._run_axis_triage(query)
            if "error" in query:
                return query # Stop if triage fails

        # Fetch the target_url exactly as defined in your config
        target_url = self.config.endpoints.get(query_type, self.config.default_route)
        
        try:
            # FIX: Use requests.get with params for Internet Archive API compatibility
            # This correctly encodes the query and avoids "Invalid URL" errors
            payload = {'url': query}
            response = requests.get(target_url, params=payload)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"routing_failed_status_{response.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def _run_axis_triage(self, query):
        """Internal helper to pass data through axis-triage."""
        try:
            response = requests.post(self.triage_url, json={"query": query})
            return response.json().get("sanitized_query", query)
        except Exception:
            return {"error": "axis-triage_failed"}