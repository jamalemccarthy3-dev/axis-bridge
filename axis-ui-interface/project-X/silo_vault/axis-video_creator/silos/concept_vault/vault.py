from lib.vault_tool import add_concept, get_concept, list_concepts, search_concepts
from config.vault_config import CONFIG


def run_vault(action, **kw):
    """action: add (concept=...), get (concept_id=...), search (query=..., limit=5) or list. -> what the tool returns."""
    f = CONFIG["vault_file"]
    if action == "add":
        return add_concept(kw["concept"], f, CONFIG["max_concepts"], CONFIG["max_text_chars"])
    if action == "get":
        return get_concept(kw["concept_id"], f)
    if action == "search":
        return search_concepts(kw["query"], f, kw.get("limit", 5))
    if action == "list":
        return list_concepts(f)
    raise ValueError("unknown vault action %r" % action)
