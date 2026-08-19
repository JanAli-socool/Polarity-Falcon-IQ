import sqlite3
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import dns.resolver

conn = sqlite3.connect('data/canonical/contacts.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Get all qualifying firms with their official URLs
cur.execute('SELECT firm_id, firm_name, official_url, last_verified_date FROM firms WHERE official_url IS NOT NULL AND official_url != ""')
firms = cur.fetchall()

staleness_found = []

for firm in firms:
    firm_id = firm['firm_id']
    firm_name = firm['firm_name']
    url = firm['official_url']
    last_verified = firm['last_verified_date']
    
    try:
        # Fetch the firm's website
        headers = {'User-Agent': 'Mozilla/5.0 (research; contact@example.com)'}
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove script/style
            for tag in soup(['script', 'style', 'nav', 'footer']):
                tag.decompose()
            
            text = re.sub(r'\s+', ' ', soup.get_text(' '))
            low = text.lower()
            
            # Check if still self-describes as family office
            fo_phrases = ['family office', 'single-family office', 'multi-family office', 'family wealth', 'multi family office']
            still_fo = any(phrase in low for phrase in fo_phrases)
            
            if not still_fo:
                staleness_found.append({
                    'firm_id': firm_id,
                    'firm_name': firm_name,
                    'check_type': 'content_changed',
                    'previous_value': 'self-described as family office',
                    'current_value': 'no longer self-describes as family office',
                    'action_taken': 'flagged',
                    'evidence': f'Page content no longer contains family office language. Status: {response.status_code}'
                })
            else:
                # Content still valid, update last_verified_date
                cur.execute('UPDATE firms SET last_verified_date = ?, updated_at = ? WHERE firm_id = ?',
                           (datetime.now().isoformat(), datetime.now().isoformat(), firm_id))
        else:
            staleness_found.append({
                'firm_id': firm_id,
                'firm_name': firm_name,
                'check_type': 'source_gone',
                'previous_value': 'accessible',
                'current_value': f'HTTP {response.status_code}',
                'action_taken': 'flagged',
                'evidence': f'Firm website returned {response.status_code}'
            })
            
    except Exception as e:
        staleness_found.append({
            'firm_id': firm_id,
            'firm_name': firm_name,
            'check_type': 'fetch_error',
            'previous_value': 'accessible',
            'current_value': f'error: {type(e).__name__}',
            'action_taken': 'flagged',
            'evidence': str(e)
        })

# Log staleness findings
run_id = None
cur.execute('INSERT INTO run_log (run_type, run_started, status, notes) VALUES (?, ?, ?, ?)',
           ('staleness_check', datetime.now().isoformat(), 'success', f'Checked {len(firms)} firms, found {len(staleness_found)} issues'))
run_id = cur.lastrowid

for s in staleness_found:
    cur.execute('''
        INSERT INTO staleness_log (run_id, entity_type, entity_id, check_type, previous_value, current_value, action_taken, evidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (run_id, 'firm', s['firm_id'], s['check_type'], s['previous_value'], s['current_value'], s['action_taken'], s['evidence']))

# Also check people emails
cur.execute('SELECT person_id, record_id, email FROM people WHERE status = "qualifying" AND email != "" AND email_validation_code IN ("V1", "V2")')
people = cur.fetchall()

for person in people:
    person_id = person['person_id']
    record_id = person['record_id']
    email = person['email']
    domain = email.split('@')[-1]
    
    try:
        answers = dns.resolver.resolve(domain, 'MX', lifetime=5)
    except Exception:
        cur.execute('''
            INSERT INTO staleness_log (run_id, entity_type, entity_id, check_type, previous_value, current_value, action_taken, evidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (run_id, 'person', person_id, 'email_bounced', 'MX verified', 'MX verification failed', 'flagged', f'Email domain {domain} no longer has MX records'))

conn.commit()
conn.close()

print(f'Staleness check complete. Firms checked: {len(firms)}, Issues found: {len(staleness_found)}')
for s in staleness_found:
    print(f'  FLAGGED: {s["firm_name"]} - {s["check_type"]} - {s["evidence"][:100]}')
