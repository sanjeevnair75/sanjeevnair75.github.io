#!/usr/bin/env python3
"""
BHC Daily Orders Scraper - GitHub Actions Runner
Scrapes all 5 Bombay High Court benches, classifies Indirect Tax matters,
and writes the results to data/latest.json for the web tool to consume.

Run by: .github/workflows/bhc-daily.yml
Produces: data/latest.json  +  data/archive/YYYY-MM-DD.json
"""

import urllib.request
import urllib.parse
import re
import html as html_lib
import json
import os
from datetime import datetime, timezone, timedelta
from http.cookiejar import CookieJar
from pathlib import Path


# ======================================================================
# CONFIGURATION
# ======================================================================

BENCHES = [
    ('B', 'Bombay HC'),
    ('A', 'Bombay HC Aurangabad'),
    ('N', 'Bombay HC Nagpur'),
    ('G', 'Bombay HC Goa'),
    ('K', 'Bombay HC Kolhapur'),
]

BASE_URL = 'https://bombayhighcourt.gov.in/bhc'
RECENT_URL = f'{BASE_URL}/front/recentjudgment'
CHANGE_URL = f'{BASE_URL}/bench/change?bench='
MAX_PAGES = 10
USER_AGENT = 'Mozilla/5.0 (compatible; JurisNair-Tracker/1.0; +https://www.jurisnair.com)'

IST = timezone(timedelta(hours=5, minutes=30))


# ======================================================================
# CLASSIFIER
# ======================================================================

KEYWORDS_HIGH = [
    r'\bCustoms?\b', r'\bCGST\b', r'\bSGST\b', r'\bIGST\b', r'\bGST\b',
    r'\bExcise\b', r'\bService Tax\b', r'\bCENVAT\b', r'\bCESTAT\b',
    r'\bDGGI\b', r'\bDRI\b', r'\bCBIC\b', r'\bCBEC\b', r'\bDGFT\b',
    r'\bBill of Entry\b', r'\bShow Cause Notice\b', r'\bAnti.?Dumping\b',
    r'\bSafeguard Duty\b', r'\bCAAR\b', r'\bICEGATE\b',
    r'\bCustoms Act\b', r'\bCGST Act\b', r'\bIGST Act\b',
]

KEYWORDS_MEDIUM = [
    r'\bRevenue\b', r'\bDuty\b', r'\bDepartment of Revenue\b',
    r'\bMinistry of Finance\b', r'\bFTP\b', r'\bFEMA\b', r'\bSEZ\b', r'\bEPCG\b',
    r'\bPMLA\b', r'\bEnforcement Directorate\b',
    r'\bAdvance Ruling\b', r'\bAdvance Authorisation\b',
]

PARTY_HIGH = [
    r'Commissioner of Customs',
    r'Commissioner of CGST',
    r'Commissioner of Central Excise',
    r'Commissioner of Service Tax',
    r'Principal Commissioner of (?:Customs|CGST|Central Excise|Service Tax|GST)',
    r'Chief Commissioner of (?:Customs|CGST|GST|Central Excise)',
    r'Additional Commissioner of (?:Customs|CGST|Central Excise)',
    r'Joint Commissioner of (?:Customs|CGST|Central Excise)',
    r'Directorate General of GST Intelligence',
    r'Directorate of Revenue Intelligence',
    r'Central Board of Indirect Taxes',
]


def classify(text):
    signals = []
    category = 'N/A'
    high_hits = 0
    med_hits = 0

    for pattern in KEYWORDS_HIGH:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            kw = matches[0]
            signals.append(f'keyword:{kw}')
            high_hits += 1
            if category == 'N/A':
                kw_lower = kw.lower()
                if re.search(r'\b(?:c|s|i)?gst\b', kw_lower):
                    category = 'GST'
                elif any(x in kw_lower for x in ['custom', 'dri', 'bill of entry', 'caar', 'icegate', 'dggi']):
                    category = 'Customs'
                elif any(x in kw_lower for x in ['excise', 'cestat', 'cenvat']):
                    category = 'Excise'
                elif 'service tax' in kw_lower:
                    category = 'Service Tax'
                elif 'dump' in kw_lower or 'safeguard' in kw_lower:
                    category = 'Trade Remedy'
                elif 'dgft' in kw_lower:
                    category = 'FTP'

    for pattern in PARTY_HIGH:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            match_text = matches[0] if isinstance(matches[0], str) else str(matches[0])
            signals.append(f'party:{match_text}')
            high_hits += 2

    for pattern in KEYWORDS_MEDIUM:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            signals.append(f'keyword:{matches[0]}')
            med_hits += 1

    if high_hits >= 2:
        return True, 'high', (category if category != 'N/A' else 'Indirect Tax'), '; '.join(signals[:6])
    elif high_hits == 1:
        return True, 'medium', (category if category != 'N/A' else 'Indirect Tax'), '; '.join(signals[:6])
    elif med_hits >= 2:
        return True, 'low', 'Possibly Indirect Tax (review)', '; '.join(signals[:6])
    else:
        return False, 'none', 'N/A', ''


# ======================================================================
# SCRAPER
# ======================================================================

def make_opener():
    cj = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [('User-Agent', USER_AGENT)]
    return opener


def fetch(opener, url):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with opener.open(req, timeout=30) as response:
        return response.read().decode('utf-8', errors='replace')


def clean_text(t):
    t = re.sub(r'<br\s*/?>', ' ', t)
    t = re.sub(r'<[^>]+>', '', t)
    return ' '.join(html_lib.unescape(t).split())


def parse_rows(html_content):
    tbody_match = re.search(r'<tbody[^>]*>(.*?)</tbody>', html_content, re.DOTALL)
    if not tbody_match:
        return []
    rows_html = re.findall(r'<tr[^>]*>(.*?)</tr>', tbody_match.group(1), re.DOTALL)
    results = []
    for row in rows_html:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(cells) < 5:
            continue
        matter_no = clean_text(cells[1])
        parties = clean_text(cells[2])
        coram = clean_text(cells[3])
        date_cell_html = cells[4]
        date_text = clean_text(date_cell_html)
        date_match = re.search(r'(\d{2}/\d{2}/\d{4})', date_text)
        order_date = date_match.group(1) if date_match else ''
        type_match = re.search(r'\((Civil|Criminal|Original)\)', date_text)
        order_type = type_match.group(1) if type_match else ''
        is_judgment = '(J)' in date_text
        link_match = re.search(r'href="([^"]*download[^"]*)"', date_cell_html)
        pdf_link = html_lib.unescape(link_match.group(1)) if link_match else ''
        results.append({
            'matterNo': matter_no,
            'parties': parties,
            'coram': coram,
            'orderDate': order_date,
            'orderType': order_type,
            'isJudgment': is_judgment,
            'pdfLink': pdf_link,
        })
    return results


def scrape_bench(bench_code, bench_name):
    print(f'Scraping {bench_name}...', flush=True)
    opener = make_opener()
    try:
        fetch(opener, f'{CHANGE_URL}{bench_code}')
    except Exception:
        pass
    all_results = []
    for page_num in range(1, MAX_PAGES + 1):
        url = RECENT_URL if page_num == 1 else f'{RECENT_URL}?page={page_num}'
        try:
            page_html = fetch(opener, url)
        except Exception as e:
            print(f'  page {page_num} failed: {e}')
            break
        rows = parse_rows(page_html)
        if not rows:
            break
        for r in rows:
            r['bench'] = bench_name
            all_results.append(r)
        if f'page={page_num + 1}' not in page_html:
            break
    print(f'  {len(all_results)} orders')
    return all_results


# ======================================================================
# MAIN
# ======================================================================

def main():
    now_ist = datetime.now(IST)
    date_str = now_ist.strftime('%Y-%m-%d')
    timestamp_str = now_ist.strftime('%d %B %Y, %I:%M %p IST')

    print(f'Juris Nair BHC Tracker - Daily Run')
    print(f'Time: {timestamp_str}')
    print('-' * 50)

    all_records = []
    for bench_code, bench_name in BENCHES:
        try:
            records = scrape_bench(bench_code, bench_name)
            all_records.extend(records)
        except Exception as e:
            print(f'  ERROR: {e}')

    if not all_records:
        print('No records fetched. Exiting without overwriting.')
        return

    print(f'\nTotal: {len(all_records)}. Classifying...')

    for rec in all_records:
        combined_text = f"{rec['parties']} {rec['matterNo']} {rec['coram']}"
        is_it, conf, cat, sig = classify(combined_text)
        rec['isIT'] = is_it
        rec['confidence'] = conf
        rec['category'] = cat
        rec['signals'] = sig

    it_count = sum(1 for r in all_records if r['isIT'])
    high = sum(1 for r in all_records if r['confidence'] == 'high')
    med = sum(1 for r in all_records if r['confidence'] == 'medium')
    low = sum(1 for r in all_records if r['confidence'] == 'low')

    bench_stats = {}
    for r in all_records:
        b = r['bench']
        bench_stats.setdefault(b, {'total': 0, 'it': 0})
        bench_stats[b]['total'] += 1
        if r['isIT']:
            bench_stats[b]['it'] += 1

    output = {
        'generated': timestamp_str,
        'generatedISO': now_ist.isoformat(),
        'dateStr': date_str,
        'totalOrders': len(all_records),
        'indirectTaxCount': it_count,
        'highCount': high,
        'mediumCount': med,
        'lowCount': low,
        'benchStats': bench_stats,
        'orders': all_records,
    }

    # Write to /data folder
    data_dir = Path('data')
    data_dir.mkdir(exist_ok=True)
    archive_dir = data_dir / 'archive'
    archive_dir.mkdir(exist_ok=True)

    latest_path = data_dir / 'latest.json'
    archive_path = archive_dir / f'{date_str}.json'

    with open(latest_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    with open(archive_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'\nWrote: {latest_path}')
    print(f'Wrote: {archive_path}')
    print(f'\nTotal: {len(all_records)} | IT: {it_count} (high:{high} med:{med} low:{low})')
    print('Done.')


if __name__ == '__main__':
    main()
