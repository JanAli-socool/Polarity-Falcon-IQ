import json
import re
from typing import Any
from pathlib import Path

# Add these imports to rag/agent.py
# from rag.retriever_v2 import RetrievalQuery, retrieve
# from stage2.retrieval import RetrievalQuery, retrieve

# Replace the tool_decompose function in rag/agent.py with this enhanced version:

ENHANCED_DECOMPOSE = '''
    def tool_decompose(self, complex_query: str) -> Dict[str, Any]:
        """Tool: Decompose a complex multi-part query into structured sub-queries with filters."""
        q = complex_query.lower()
        sub_queries = []
        filters = {}
        
        # Extract firm names (quoted or capitalized phrases)
        firm_matches = re.findall(r'"([^"]+)"', complex_query)  # "TFO Family Office"
        if firm_matches:
            filters["firm_name"] = firm_matches[0]
        
        # Geography detection
        geo_terms = {
            "united states": "united states", "usa": "united states", "u.s.": "united states", "us": "united states",
            "canada": "canada", "uk": "united kingdom", "united kingdom": "united kingdom",
            "switzerland": "switzerland", "singapore": "singapore", "hong kong": "hong kong",
            "germany": "germany", "france": "france", "australia": "australia",
            "south africa": "south africa", "brazil": "brazil", "uae": "united arab emirates",
            "japan": "japan", "china": "china", "india": "india"
        }
        for geo, normalized in geo_terms.items():
            if geo in complex_query.lower():
                filters["country"] = normalized
                break
        
        # Sector detection
        sector_terms = {
            "healthcare": ["healthcare", "health care", "life sciences", "biotech", "pharma"],
            "technology": ["technology", "tech", "software", "digital", "ai", "artificial intelligence"],
            "financial services": ["financial services", "fintech", "banking", "wealth management", "asset management"],
            "private equity": ["private equity", "pe", "buyout", "venture capital", "vc"],
            "real estate": ["real estate", "property", "reit"],
            "energy": ["energy", "oil", "gas", "renewable", "solar", "wind"],
            "industrials": ["industrials", "manufacturing", "industrial"],
            "consumer": ["consumer", "retail", "ecommerce", "brand"],
        }
        for sector, terms in sector_terms.items():
            if any(term in q for term in terms):
                terms.append(sector)
        
        # Role/title detection
        role_terms = {
            "investment_decision_maker": ["chief investment officer", "cio", "investment director", "portfolio manager", "investment manager"],
            "executive_decision_maker": ["chief executive officer", "ceo", "president", "chairman", "founder", "co-founder"],
            "partner_or_principal": ["managing partner", "general partner", "senior partner", "partner", "principal"],
            "capital_or_relationship_lead": ["head of capital", "head of relationships", "investor relations", "capital formation"],
        }
        for role_class, terms in role_terms.items():
            if any(term in q for term in terms):
                filters["role_class"] = role_class
                break
        
        # Email/LinkedIn filters
        if "email" in q:
            filters["has_email"] = True
        if "linkedin" in q:
            filters["route_type"] = "linkedin"
        
        # Trust state
        if "current" in q or "recent" in q:
            filters["trust_state"] = "supported_current"
        
        # Compound query patterns
        sub_queries = []
        if " vs " in q or " versus " in q or " compare " in q:
            parts = re.split(r"\s+(?:vs|versus|compare)\s+", q, flags=re.IGNORECASE)
            for part in parts:
                part = part.strip().replace(" and ", " ").strip()
                if part:
                    sub_queries.append(part.strip())
        
        elif " and " in q and ("how many" in q or "count" in q or "list" in q):
            parts = re.split(r"\s+and\s+", q)
            for part in parts:
                part = part.strip()
                if part:
                    sub_queries.append(part)
        
        elif " for " in q and ("show" in q or "list" in q or "find" in q):
            parts = re.split(r"\s+for\s+", q, flags=re.IGNORECASE)
            if len(parts) >= 2:
                sub_queries.append(parts[0].strip())
                sub_queries.append(f"for {parts[1].strip()}")
        
        # Default: single query with extracted filters
        if not sub_queries:
            sub_queries = [complex_query]
        
        return {
            "original_query": complex_query,
            "sub_queries": sub_queries,
            "filters": filters,
            "count": len(sub_queries),
        }
'''

print("Enhanced tool_decompose function ready to be added to rag/agent.py")
print("Key improvements:")
print("1. Extracts firm names (quoted)")
print("2. Extracts geography/country filters")
print("3. Extracts sector/industry filters")
print("4. Extracts role/class filters")
print("5. Extracts email/LinkedIn filters")
print("5. Extracts trust state filters")
print("6. Returns structured filters for each sub-query")