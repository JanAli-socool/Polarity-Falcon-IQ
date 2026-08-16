# pipeline/query_layer.py
# Deterministic Query Layer: SQL interface for counts, filters, aggregates
# Provides precise, auditable queries over the canonical dataset

import sqlite3
import pathlib
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

DB_PATH = pathlib.Path("data/canonical/contacts.db")

class QueryType(Enum):
    COUNT = "count"
    FILTER = "filter"
    AGGREGATE = "aggregate"
    SEARCH = "search"

@dataclass
class QueryResult:
    query_type: QueryType
    sql: str
    params: tuple
    rows: List[Dict[str, Any]]
    row_count: int
    explanation: str

class QueryLayer:
    """Deterministic SQL query interface for the canonical dataset."""
    
    def __init__(self, db_path: pathlib.Path = DB_PATH):
        self.db_path = db_path
    
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def execute(self, sql: str, params: tuple = ()) -> QueryResult:
        """Execute a read-only SQL query and return structured result."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = [dict(row) for row in cur.fetchall()]
            return QueryResult(
                query_type=QueryType.SEARCH,
                sql=sql,
                params=params,
                rows=rows,
                row_count=len(rows),
                explanation=f"Executed query returning {len(rows)} rows"
            )
        finally:
            conn.close()
    
    # ---- Firm-level queries ----
    
    def count_firms(self, verification_tier: Optional[str] = None, 
                    country: Optional[str] = None) -> QueryResult:
        """Count firms with optional filters."""
        conditions = []
        params = []
        if verification_tier:
            conditions.append("verification_tier = ?")
            params.append(verification_tier)
        if country:
            conditions.append("firm_country = ?")
            params.append(country)
        
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT COUNT(*) as count FROM firms {where}"
        return self.execute(sql, tuple(params))
    
    def list_firms(self, verification_tier: Optional[str] = None,
                   country: Optional[str] = None,
                   limit: int = 100) -> QueryResult:
        """List firms with optional filters."""
        conditions = []
        params = []
        if verification_tier:
            conditions.append("verification_tier = ?")
            params.append(verification_tier)
        if country:
            conditions.append("firm_country = ?")
            params.append(country)
        
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT * FROM firms {where} ORDER BY firm_name LIMIT ?"
        params.append(limit)
        return self.execute(sql, tuple(params))
    
    def firm_contacts(self, firm_name: str) -> QueryResult:
        """Get all qualifying contacts for a specific firm."""
        sql = """
            SELECT p.*, f.firm_name, f.verification_tier, f.firm_country
            FROM people p
            JOIN firms f ON p.firm_id = f.firm_id
            WHERE f.firm_name = ? AND p.status = 'qualifying'
            ORDER BY p.record_id
        """
        return self.execute(sql, (firm_name,))
    
    # ---- People-level queries ----
    
    def count_people(self, status: str = "qualifying",
                     firm_name: Optional[str] = None,
                     has_email: bool = False,
                     has_linkedin: bool = False,
                     title_contains: Optional[str] = None) -> QueryResult:
        """Count people with filters."""
        conditions = ["p.status = ?"]
        params = [status]
        
        if firm_name:
            conditions.append("f.firm_name = ?")
            params.append(firm_name)
        if has_email:
            conditions.append("p.email != '' AND p.email_validation_code IN ('V1','V2')")
        if has_linkedin:
            conditions.append("p.linkedin_url != ''")
        if title_contains:
            conditions.append("p.title_normalized LIKE ?")
            params.append(f"%{title_contains}%")
        
        where = "WHERE " + " AND ".join(conditions)
        sql = f"""
            SELECT COUNT(*) as count
            FROM people p
            JOIN firms f ON p.firm_id = f.firm_id
            {where}
        """
        return self.execute(sql, tuple(params))
    
    def search_people(self, 
                      firm_name: Optional[str] = None,
                      title_contains: Optional[str] = None,
                      name_contains: Optional[str] = None,
                      has_email: bool = False,
                      has_linkedin: bool = False,
                      verification_tier: Optional[str] = None,
                      country: Optional[str] = None,
                      limit: int = 50) -> QueryResult:
        """Search people with multiple filters."""
        conditions = ["p.status = 'qualifying'"]
        params = []
        
        if firm_name:
            conditions.append("f.firm_name = ?")
            params.append(firm_name)
        if title_contains:
            conditions.append("p.title_normalized LIKE ?")
            params.append(f"%{title_contains}%")
        if name_contains:
            conditions.append("(p.full_name LIKE ? OR p.first_name LIKE ? OR p.last_name LIKE ?)")
            params.extend([f"%{name_contains}%"] * 3)
        if has_email:
            conditions.append("p.email != '' AND p.email_validation_code IN ('V1','V2')")
        if has_linkedin:
            conditions.append("p.linkedin_url != ''")
        if verification_tier:
            conditions.append("f.verification_tier = ?")
            params.append(verification_tier)
        if country:
            conditions.append("f.firm_country = ?")
            params.append(country)
        
        where = "WHERE " + " AND ".join(conditions)
        sql = f"""
            SELECT p.record_id, p.full_name, p.first_name, p.last_name,
                   p.title_normalized, p.job_title, p.email, p.email_validation_code,
                   p.email_quality, p.linkedin_url, p.phone,
                   f.firm_name, f.verification_tier, f.firm_country,
                   p.source_url, p.confidence, p.last_verified_date
            FROM people p
            JOIN firms f ON p.firm_id = f.firm_id
            {where}
            ORDER BY f.firm_name, p.record_id
            LIMIT ?
        """
        params.append(limit)
        return self.execute(sql, tuple(params))
    
    # ---- Aggregate queries ----
    
    def people_by_firm(self, status: str = "qualifying") -> QueryResult:
        """Count of people per firm."""
        sql = """
            SELECT f.firm_name, f.verification_tier, f.firm_country,
                   COUNT(p.person_id) as contact_count
            FROM firms f
            LEFT JOIN people p ON p.firm_id = f.firm_id AND p.status = ?
            GROUP BY f.firm_id, f.firm_name, f.verification_tier, f.firm_country
            HAVING contact_count > 0
            ORDER BY contact_count DESC
        """
        return self.execute(sql, (status,))
    
    def people_by_title(self, status: str = "qualifying",
                        min_count: int = 1) -> QueryResult:
        """Count of people by normalized title."""
        sql = """
            SELECT p.title_normalized, COUNT(*) as count
            FROM people p
            WHERE p.status = ? AND p.title_normalized != ''
            GROUP BY p.title_normalized
            HAVING count >= ?
            ORDER BY count DESC
        """
        return self.execute(sql, (status, min_count))
    
    def people_by_country(self, status: str = "qualifying") -> QueryResult:
        """Count of people by firm country."""
        sql = """
            SELECT f.firm_country, COUNT(p.person_id) as contact_count,
                   COUNT(DISTINCT f.firm_id) as firm_count
            FROM firms f
            LEFT JOIN people p ON p.firm_id = f.firm_id AND p.status = ?
            GROUP BY f.firm_country
            ORDER BY contact_count DESC
        """
        return self.execute(sql, (status,))
    
    def email_coverage(self) -> QueryResult:
        """Email validation code distribution."""
        sql = """
            SELECT email_validation_code, COUNT(*) as count
            FROM people
            WHERE status = 'qualifying'
            GROUP BY email_validation_code
            ORDER BY count DESC
        """
        return self.execute(sql, ())
    
    def verification_tier_distribution(self) -> QueryResult:
        """Distribution of firms by verification tier."""
        sql = """
            SELECT verification_tier, COUNT(*) as firm_count
            FROM firms
            GROUP BY verification_tier
            ORDER BY firm_count DESC
        """
        return self.execute(sql, ())
    
    def source_class_distribution(self) -> QueryResult:
        """Distribution of discovery source classes."""
        sql = """
            SELECT source_class, COUNT(*) as count
            FROM discovery_log
            WHERE entity_type = 'firm'
            GROUP BY source_class
            ORDER BY count DESC
        """
        return self.execute(sql, ())
    
    def staleness_summary(self, run_id: Optional[int] = None) -> QueryResult:
        """Summary of staleness checks."""
        conditions = []
        params = []
        if run_id:
            conditions.append("run_id = ?")
            params.append(run_id)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"""
            SELECT check_type, action_taken, COUNT(*) as count
            FROM staleness_log
            {where}
            GROUP BY check_type, action_taken
            ORDER BY count DESC
        """
        return self.execute(sql, tuple(params))
    
    # ---- Run log queries ----
    
    def recent_runs(self, limit: int = 20) -> QueryResult:
        """Get recent run log entries."""
        sql = """
            SELECT * FROM run_log
            ORDER BY run_started DESC
            LIMIT ?
        """
        return self.execute(sql, (limit,))
    
    def run_summary(self, run_id: int) -> QueryResult:
        """Get detailed summary for a specific run."""
        sql = "SELECT * FROM run_log WHERE run_id = ?"
        return self.execute(sql, (run_id,))
    
    # ---- Natural language to SQL (simple intent mapping) ----
    
    def parse_and_execute(self, question: str) -> QueryResult:
        """Simple intent detection for common questions."""
        q = question.lower()
        
        # Count firms
        if "how many firms" in q or "count firms" in q:
            return self.count_firms()
        
        # Count people
        if "how many people" in q or "count people" in q or "count contacts" in q:
            return self.count_people()
        
        # People with email
        if "email" in q and ("how many" in q or "count" in q):
            return self.count_people(has_email=True)
        
        # People with LinkedIn
        if "linkedin" in q and ("how many" in q or "count" in q):
            return self.count_people(has_linkedin=True)
        
        # People by title
        if "chief investment officer" in q or "cio" in q:
            return self.search_people(title_contains="chief investment officer")
        if "managing partner" in q:
            return self.search_people(title_contains="managing partner")
        if "managing director" in q:
            return self.search_people(title_contains="managing director")
        if "partner" in q and "how many" in q:
            return self.count_people(title_contains="partner")
        
        # Firms by country
        if "united states" in q or "us " in q or "usa" in q:
            return self.count_firms(country="United States")
        
        # Default: search people by name/title keywords
        keywords = ["chief", "managing", "director", "partner", "president", "founder", "cio", "cfo"]
        for kw in keywords:
            if kw in q:
                return self.search_people(title_contains=kw)
        
        # Fallback: return all qualifying people (limited)
        return self.search_people(limit=20)


# Convenience functions
def get_query_layer() -> QueryLayer:
    return QueryLayer()


if __name__ == "__main__":
    ql = QueryLayer()
    
    print("=== Firm Counts ===")
    print(ql.count_firms().rows)
    print(ql.verification_tier_distribution().rows)
    
    print("\n=== People Counts ===")
    print(ql.count_people().rows)
    print(ql.count_people(has_email=True).rows)
    print(ql.count_people(has_linkedin=True).rows)
    
    print("\n=== People by Firm ===")
    for r in ql.people_by_firm().rows:
        print(f"  {r['firm_name']}: {r['contact_count']} contacts")
    
    print("\n=== People by Title ===")
    for r in ql.people_by_title().rows[:10]:
        print(f"  {r['title_normalized']}: {r['count']}")
    
    print("\n=== Email Coverage ===")
    print(ql.email_coverage().rows)
    
    print("\n=== Search: Chief Investment Officer ===")
    results = ql.search_people(title_contains="chief investment officer")
    for r in results.rows:
        print(f"  {r['full_name']} - {r['firm_name']} - {r['title_normalized']}")
    
    print("\n=== Natural Language: 'How many firms?' ===")
    print(ql.parse_and_execute("How many firms?").rows)
    
    print("\n=== Natural Language: 'Show me chief investment officers' ===")
    results = ql.parse_and_execute("Show me chief investment officers")
    for r in results.rows[:5]:
        print(f"  {r['full_name']} @ {r['firm_name']} ({r['title_normalized']})")