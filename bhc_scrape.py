#!/usr/bin/env python3
"""
BHC Daily Orders Scraper v2 - With PDF Content Scanning
Scrapes all 5 Bombay High Court benches, classifies Indirect Tax matters
using THREE-PASS classification:
  Pass 1 - Party name classifier (fast, current logic)
  Pass 2 - PDF content scanner (for borderline cases)
  Pass 3 - Known tax-litigant watchlist

Produces: data/latest.json  +  data/archive/YYYY-MM-DD.json
"""

import urllib.request
import urllib.parse
import urllib.error
import re
import html as html_lib
import json
import io
import time
from datetime import datetime, timezone, timedelta
from http.cookiejar import CookieJar
from pathlib import Path

# Optional PDF support - fail gracefully if missing
try:
    from pypdf import PdfReader
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print('WARNING: pypdf not installed. PDF content scanning disabled.')


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
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
PDF_MAX_PAGES = 3
PDF_MAX_BYTES = 5_000_000
PDF_TIMEOUT = 20
PDF_MAX_SCANS = 80

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
    r'\bMGST Act\b', r'\bFinance Act\b',
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

# Known frequent indirect-tax litigants — if one of these appears as a party
# AND the other party is Union of India / Commissioner / etc., we scan the PDF.
KNOWN_TAX_LITIGANTS = [
    r'\bK\s*[-.]?\s*Line\b',
    r'\bReliance Industries\b',
    r'\bTata Steel\b', r'\bTata Motors\b', r'\bTata Electronics\b', r'\bTata Consultancy\b',
    r'\bSamsung\b',
    r'\bVolkswagen\b', r'\bSkoda\b', r'\bAudi\b',
    r'\bLupin\b', r'\bSun Pharma\b', r'\bGlenmark\b',
    r'\bCipla\b', r'\bDr\.?\s*Reddy', r'\bBiocon\b',
    r'\bLarsen\s*&?\s*Toubro\b',
    r'\bBharti Airtel\b', r'\bVodafone\b',
    r'\bAdani\b', r'\bHindalco\b', r'\bVedanta\b',
    r'\bMaruti\b', r'\bMahindra\b', r'\bBajaj Auto\b',
    r'\bMahanagar Gas\b',
    r'\bShell India\b', r'\bBPCL\b', r'\bHPCL\b', r'\bONGC\b',
    r'\bHindustan Unilever\b', r'\bColgate\b', r'\bNestle\b',
    r'\bMondelez\b', r'\bPepsiCo\b',
]

ADVERSARY_PATTERNS = [
    r'\bUnion of India\b', r'\bState of Maharashtra\b',
    r'\bCommissioner\b', r'\bDeputy Commissioner\b',
    r'\bDirectorate\b', r'\bAssistant Commissioner\b',
    r'\bJt\.?\s*Commissioner\b', r'\bAddl\.?\s*Commissioner\b',
]


def category_from_keyword(kw):
    kw_lower = kw.lower()
    if re.search(r'\b(?:c|s|i)?gst\b', kw_lower):
        return 'GST'
    if any(x in kw_lower for x in ['custom', 'dri', 'bill of entry', 'caar', 'icegate', 'dggi']):
        return 'Customs'
    if any(x in kw_lower for x in ['excise', 'cestat', 'cenvat']):
        return 'Excise'
    if 'service tax' in kw_lower:
        return 'Service Tax'
    if 'dump' in kw_lower or 'safeguard' in kw_lower:
        return 'Trade Remedy'
    if 'dgft' in kw_lower:
        return 'FTP'
    return 'N/A'


def classify_text(text):
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
                cat = category_from_keyword(kw)
                if cat != 'N/A':
                    category = cat

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

    return high_hits, med_hits, category, signals


def classify_from_parties(text):
    high, med, category, signals = classify_text(text)
    if high >= 2:
        return True, 'high', (category if category != 'N/A' else 'Indirect Tax'), '; '.join(signals[:6]), False
    elif high == 1:
        return True, 'medium', (category if category != 'N/A' else 'Indirect Tax'), '; '.join(signals[:6]), False
    elif med >= 2:
        return True, 'low', 'Possibly Indirect Tax (review)', '; '.join(signals[:6]), True
    else:
        return False, 'none', 'N/A', '', False


def is_watchlist_suspect(text):
    has_known = any(re.search(p, text, re.IGNORECASE) for p in KNOWN_TAX_LITIGANTS)
    has_adversary = any(re.search(p, text, re.IGNORECASE) for p in ADVERSARY_PATTERNS)
    return has_known and has_adversary


# ======================================================================
# SCRAPER
# ======================================================================

def make_opener():
    cj = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [
        ('User-Agent', USER_AGENT),
        ('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9'),
        ('Accept-Language', 'en-US,en;q=0.9'),
    ]
    return opener


def fetch(opener, url, max_retries=3):
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            with opener.open(req, timeout=30) as response:
                return response.read().decode('utf-8', errors='replace')
        except urllib.error.HTTPError as e:
            if e.code == 503 and attempt < max_retries - 1:
                time.sleep(3 + attempt * 2)
                continue
            raise
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            raise


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
# PDF SCANNING (PASS 2)
# ======================================================================

def extract_pdf_text(pdf_url):
    if not PDF_AVAILABLE or not pdf_url:
        return ''
    try:
        req = urllib.request.Request(pdf_url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req, timeout=PDF_TIMEOUT) as response:
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) > PDF_MAX_BYTES:
                return ''
            data = response.read(PDF_MAX_BYTES)
        reader = PdfReader(io.BytesIO(data))
        text = ''
        for i, page in enumerate(reader.pages[:PDF_MAX_PAGES]):
            try:
                text += page.extract_text() + '\n'
            except Exception:
                continue
        return text
    except Exception:
        return ''


def rescan_with_pdf(record, scan_counter):
    if scan_counter[0] >= PDF_MAX_SCANS:
        return False
    text = extract_pdf_text(record['pdfLink'])
    scan_counter[0] += 1
    if not text:
        return False

    high, med, category, signals = classify_text(text)
    if high >= 2:
        record['isIT'] = True
        record['confidence'] = 'high'
        record['category'] = category if category != 'N/A' else 'Indirect Tax'
        record['signals'] = 'PDF: ' + '; '.join(signals[:6])
        record['pdfScanned'] = True
        return True
    elif high == 1:
        record['isIT'] = True
        record['confidence'] = 'medium'
        record['category'] = category if category != 'N/A' else 'Indirect Tax'
        record['signals'] = 'PDF: ' + '; '.join(signals[:6])
        record['pdfScanned'] = True
        return True
    elif med >= 2:
        record['isIT'] = True
        record['confidence'] = 'low'
        record['category'] = 'Possibly Indirect Tax (PDF keywords)'
        record['signals'] = 'PDF: ' + '; '.join(signals[:6])
        record['pdfScanned'] = True
        return True
    record['pdfScanned'] = True
    return False


# ======================================================================
# MAIN
# ======================================================================

def main():
    now_ist = datetime.now(IST)
    date_str = now_ist.strftime('%Y-%m-%d')
    timestamp_str = now_ist.strftime('%d %B %Y, %I:%M %p IST')

    print(f'Juris Nair BHC Tracker - Daily Run (v2 with PDF scanning)')
    print(f'Time: {timestamp_str}')
    print('-' * 50)

    all_records = []
    for bench_code, bench_name in BENCHES:
        try:
            records = scrape_bench(bench_code, bench_name)
            all_records.extend(records)
        except Exception as e:
            print(f'  ERROR scraping {bench_name}: {e}')

    if not all_records:
        print('No records fetched. Exiting without overwriting.')
        return

    print(f'\nTotal: {len(all_records)}. Running Pass 1 (party-name classifier)...')

    pdf_scan_queue = []
    for rec in all_records:
        combined_text = f"{rec['parties']} {rec['matterNo']} {rec['coram']}"
        is_it, conf, cat, sig, needs_rescan = classify_from_parties(combined_text)
        rec['isIT'] = is_it
        rec['confidence'] = conf
        rec['category'] = cat
        rec['signals'] = sig
        rec['pdfScanned'] = False

        if needs_rescan or is_watchlist_suspect(combined_text):
            if rec.get('pdfLink'):
                pdf_scan_queue.append(rec)

    pass1_count = sum(1 for r in all_records if r['isIT'])
    print(f'Pass 1: {pass1_count} Indirect Tax matches from party names')

    if pdf_scan_queue and PDF_AVAILABLE:
        print(f'\nPass 2: Scanning {min(len(pdf_scan_queue), PDF_MAX_SCANS)} PDFs for deeper classification...')
        scan_counter = [0]
        upgraded = 0
        newly_flagged = 0
        for rec in pdf_scan_queue:
            was_flagged_before = rec['isIT']
            prev_conf = rec['confidence']
            if rescan_with_pdf(rec, scan_counter):
                if not was_flagged_before:
                    newly_flagged += 1
                elif rec['confidence'] != prev_conf:
                    upgraded += 1
            time.sleep(0.5)
        print(f'Pass 2 complete: {newly_flagged} newly flagged, {upgraded} upgraded, {scan_counter[0]} PDFs scanned')
    elif pdf_scan_queue:
        print('Pass 2 SKIPPED: pypdf not available')

    it_count = sum(1 for r in all_records if r['isIT'])
    high = sum(1 for r in all_records if r['confidence'] == 'high')
    med = sum(1 for r in all_records if r['confidence'] == 'medium')
    low = sum(1 for r in all_records if r['confidence'] == 'low')
    pdf_scanned = sum(1 for r in all_records if r.get('pdfScanned'))

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
        'pdfScannedCount': pdf_scanned,
        'benchStats': bench_stats,
        'orders': all_records,
    }

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
    print(f'\nFinal: {len(all_records)} orders | IT: {it_count} (high:{high} med:{med} low:{low}) | {pdf_scanned} PDFs scanned')
    print('Done.')


if __name__ == '__main__':
    main()
