import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('data/canonical/contacts.db')
cur = conn.cursor()

# Check for records not verified in last 30 days
cur.execute("""
    SELECT firm_name, last_verified_date 
    FROM firms 
    WHERE last_verified_date IS NOT NULL 
    AND last_verified_date < date('now', '-30 days')
""")
stale_firms = cur.fetchall()

# Check for people not verified in last 30 days
cur.execute("""
    SELECT record_id, full_name, last_verified_date 
    FROM people 
    WHERE status = 'qualifying' 
    AND last_verified_date IS NOT NULL 
    AND last_verified_date < date('now', '-30 days')
""")
stale_people = cur.fetchall()

# Check for source changes (content_changed)
cur.execute("""
    SELECT entity_type, entity_id, check_type, action_taken, evidence 
    FROM staleness_log 
    WHERE created_at > date('now', '-1 day')
    AND action_taken IN ('refreshed', 'quarantined', 'flagged')
""")
recent_actions = cur.fetchall()

conn.close()

print(f'STALE_FIRMS: {len(stale_firms)}')
for f in stale_firms:
    print(f'  STALE_FIRM: {f[0]} (last verified: {f[1]})')

print(f'STALE_PEOPLE: {len(stale_people)}')
