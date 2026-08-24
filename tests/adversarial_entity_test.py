import json
import re
from pathlib import Path

with open("data/final/family_office_contacts.jsonl", "r", encoding="utf-8") as f:
    records = [json.loads(line) for line in f]

ADVERSARIAL_PATTERNS = [
    r"^(top|best|top\s+\d+)\s+(family\s+office|multi[- ]family\s+office)",
    r"^(what\s+is\s+a|what\s+are\s+)",
    r"^(our|the)\s+(team|firm|office|company)",
    r"^(why|how|when|where)\s+",
    r"(law\s+firm|law\s+firm|accounting\s+firm|accountancy|legal\s+services|attorney|solicitor)",
    r"(bank|wealth\s+management|asset\s+management|investment\s+advisor|financial\s+advisor)",
    r"(recruiter|recruitment|headhunter|executive\s+search)",
    r"(conference|summit|forum|webinar|event|workshop)",
    r"(news|article|blog|post|press\s+release|announcement)",
    r"^https?://",
    r"\.(com|io|co|net|org)\s*$",
    r"^(family\s+office|multi[- ]family\s+office|single[- ]family\s+office)\s*$",
]

def is_adversarial(firm_name: str) -> bool:
    name = firm_name.strip().lower()
    for pattern in ADVERSARIAL_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return True
    return False

adversarial = []
clean = []
for rec in records:
    firm = rec.get("Family Office Name", "")
    if is_adversarial(firm):
        adversarial.append(rec)
    else:
        clean.append(rec)

print(f"Total: {len(records)}")
print(f"Adversarial (noise): {len(adversarial)} ({len(adversarial)/len(records)*100:.1f}%)")
print(f"Clean (plausible FO): {len(clean)} ({len(clean)/len(records)*100:.1f}%)")

print("\nAdversarial examples:")
for rec in adversarial[:30]:
    print(f"  NOISE: {rec.get('Family Office Name', '')[:100]}")

# Save clean set
with open("data/final/family_office_contacts_clean.jsonl", "w", encoding="utf-8") as f:
    for rec in clean:
        f.write(json.dumps(rec) + "\n")

print(f"\nSaved clean records to data/final/family_office_contacts_clean.jsonl")