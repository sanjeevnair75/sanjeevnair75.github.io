"""
CAAR Post-Processor
====================
Runs after the scraper. Takes caar_all.csv/json and produces an enriched
version with:
  - issue_type column (Classification / Exemption / Valuation / etc.)
  - issue_confidence column (explicit / inferred / low)
  - year column (extracted from date_ruling)

Reads:  caar_all.csv
Writes: caar_all_enriched.csv + caar_all_enriched.json
"""

import csv
import json
import re
import sys
from collections import Counter


def classify_issue(subject):
    """Tag a subject line with one of the standard issue types."""
    s = (subject or '').lower().strip()
    if not s:
        return 'Unspecified', 'low'

    # Procedural
    if any(k in s for k in [
        'withdrawal', 'modification petition', 'non-prosecution',
        'non- prosecution', 'kept confidential', 'confidential',
        'remand', 'recall',
    ]):
        return 'Procedural', 'explicit'

    if any(k in s for k in ['country of origin', 'rules of origin', 'origin certificate']):
        return 'Country of Origin', 'explicit'

    if any(k in s for k in ['valuation', 'transaction value', 'related party']):
        return 'Valuation', 'explicit'

    if any(k in s for k in ['anti-dumping', 'antidumping', 'safeguard duty', 'countervailing']):
        return 'Trade Remedy', 'explicit'

    if any(k in s for k in [
        'exemption', 'notification', 'concessional', 'fta benefit', 'preferential',
        'msihc', 'duty drawback', 'epcg', 'sez', 'project import', 'moowr',
        'deferred payment', 'quality control order',
    ]):
        return 'Exemption', 'explicit'

    # Classification - explicit signals
    explicit_signals = [
        'classif', 'clasif', 'classfication',
        'tariff', 'cth', 'chapter heading',
        'hsn', 'hs code', 'harmoniz', 'harmonis',
        'falling under', 'fall under', 'classifiable',
    ]
    if any(sig in s for sig in explicit_signals):
        return 'Classification', 'explicit'

    # Classification - contextual signals
    contextual_signals = [
        'import and trading', 'import of', 'import to', 'export of',
        'whether the', 'whether ', 'manufactur', 'product',
        'in respect of', 'parts for', 'parts of',
        'areca nut', 'betel nut', 'cashew', 'vessel', 'aircraft',
    ]
    if any(sig in s for sig in contextual_signals):
        return 'Classification', 'inferred'

    # Fallback: if the subject has meaningful content, default to Classification
    if len(s) > 5:
        return 'Classification', 'inferred'

    return 'Other / Unclear', 'low'


def extract_year(date_str):
    """Extract a 4-digit year from a date string in DD.MM.YYYY format."""
    if not date_str:
        return ''
    m = re.search(r'(\d{4})', date_str)
    return m.group(1) if m else ''


def main():
    print("=" * 70)
    print("CAAR Post-Processor")
    print("=" * 70)

    in_path = "caar_all.csv"
    out_csv = "caar_all_enriched.csv"
    out_json = "caar_all_enriched.json"

    try:
        with open(in_path, 'r', encoding='utf-8-sig') as f:
            records = list(csv.DictReader(f))
    except FileNotFoundError:
        print(f"ERROR: {in_path} not found. Scraper may have failed.")
        sys.exit(1)

    print(f"Loaded {len(records)} records from {in_path}")

    # Enrich
    for r in records:
        issue, confidence = classify_issue(r.get('subject', ''))
        r['issue_type'] = issue
        r['issue_confidence'] = confidence
        r['year'] = extract_year(r.get('date_ruling', ''))

    # Save
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    if records:
        with open(out_csv, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
            writer.writeheader()
            writer.writerows(records)

    print(f"\nSaved enriched data:")
    print(f"  {out_csv}")
    print(f"  {out_json}")

    # Print stats
    print(f"\nIssue type distribution:")
    issue_counter = Counter(r['issue_type'] for r in records)
    for issue, count in issue_counter.most_common():
        pct = count / len(records) * 100
        print(f"  {issue:25s}: {count:4d} ({pct:.1f}%)")

    print(f"\nYear distribution:")
    year_counter = Counter(r['year'] for r in records if r['year'])
    for year in sorted(year_counter.keys()):
        print(f"  {year}: {year_counter[year]}")


if __name__ == "__main__":
    main()
