"""
CAAR Unified Scraper - Headless / Cloud Edition
================================================
Scrapes all 4 sections of the CBIC CAAR portal.

This is the headless version intended to run on GitHub Actions:
  - headless=True (no visible browser)
  - no slow_mo
  - works inside a Linux container with Playwright pre-installed

Output (written to the script's working directory):
  - mumbai_rulings.csv + mumbai_rulings.json
  - mumbai_orders.csv  + mumbai_orders.json
  - delhi_rulings.csv  + delhi_rulings.json
  - delhi_orders.csv   + delhi_orders.json
  - caar_all.csv       + caar_all.json    (consolidated)
"""

import csv
import json
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


BASE_URL = "https://www.cbic.gov.in"

SECTIONS = [
    ("Mumbai Rulings",
     "https://www.cbic.gov.in/entities/cbic-content-mst/OTMwMQ==",
     50,
     "mumbai_rulings"),
    ("Mumbai Orders",
     "https://www.cbic.gov.in/entities/cbic-content-mst/OTQ0MA==",
     20,
     "mumbai_orders"),
    ("Delhi Rulings",
     "https://www.cbic.gov.in/entities/cbic-content-mst/OTQ1OQ==",
     40,
     "delhi_rulings"),
    ("Delhi Orders",
     "https://www.cbic.gov.in/entities/cbic-content-mst/OTUyMg==",
     20,
     "delhi_orders"),
]

PAGE_RENDER_WAIT = 3.0
TIMEOUT_MS = 45000
SAFETY_PAGE_CAP = 80


def extract_rows_from_page(page, page_num, section_label):
    """Extract all rows from the current page of the table."""
    rulings = []
    page.wait_for_selector("table tbody tr", timeout=TIMEOUT_MS)
    rows = page.query_selector_all("table tbody tr")

    for row in rows:
        cells = row.query_selector_all("td")
        if len(cells) < 6:
            continue

        sl_no = cells[0].inner_text().strip()
        applicant = cells[1].inner_text().strip()
        date_application = cells[2].inner_text().strip()
        date_ruling = cells[3].inner_text().strip()

        subject = cells[4].inner_text().strip()
        for trailing in ["Read More...", "Read More..", "Read More."]:
            if subject.endswith(trailing):
                subject = subject[:-len(trailing)].strip()
                break

        link_cell = cells[5]
        link_elem = link_cell.query_selector("a")
        if link_elem:
            ruling_no = link_elem.inner_text().strip()
            pdf_href = (link_elem.get_attribute("href") or "").strip()
            if pdf_href and not pdf_href.startswith("http"):
                if pdf_href.startswith("/"):
                    pdf_link = BASE_URL + pdf_href
                else:
                    pdf_link = BASE_URL + "/" + pdf_href
            else:
                pdf_link = pdf_href
        else:
            ruling_no = link_cell.inner_text().strip()
            pdf_link = ""

        rulings.append({
            "section": section_label,
            "page_no": page_num,
            "sl_no_on_page": sl_no,
            "applicant": applicant,
            "date_application": date_application,
            "date_ruling": date_ruling,
            "subject": subject,
            "ruling_no": ruling_no,
            "pdf_link": pdf_link,
            "pdf_available": "YES" if pdf_link else "NO",
        })

    return rulings


def click_next_page(page):
    for btn in page.query_selector_all("a, button"):
        try:
            text = btn.inner_text().strip().lower()
        except Exception:
            continue
        if "next" in text:
            classes = (btn.get_attribute("class") or "").lower()
            aria_disabled = (btn.get_attribute("aria-disabled") or "").lower()
            if "disabled" in classes or aria_disabled == "true":
                return False
            try:
                btn.click()
                return True
            except Exception:
                continue
    return False


def save_section_output(records, file_stem, section_label):
    if not records:
        print(f"  No records to save for {section_label}")
        return

    with open(f"{file_stem}.json", "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    with open(f"{file_stem}.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)

    print(f"  Saved {file_stem}.csv and {file_stem}.json")


def save_consolidated(all_records):
    if not all_records:
        return
    with open("caar_all.json", "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)
    with open("caar_all.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_records[0].keys()))
        writer.writeheader()
        writer.writerows(all_records)
    print(f"  Saved caar_all.csv and caar_all.json ({len(all_records)} records)")


def scrape_section(page, label, url, expected_pages, file_stem):
    print(f"\n--- SECTION: {label} ---")
    print(f"  URL: {url}")

    records = []
    page.goto(url, wait_until="networkidle", timeout=60000)
    time.sleep(PAGE_RENDER_WAIT)

    try:
        page.wait_for_selector("table tbody tr", timeout=TIMEOUT_MS)
    except PlaywrightTimeout:
        print(f"  TIMEOUT: table did not load for {label}. Skipping section.")
        return []

    page_num = 1
    while page_num <= SAFETY_PAGE_CAP:
        try:
            page_records = extract_rows_from_page(page, page_num, label)
            records.extend(page_records)
            print(f"  Page {page_num}: {len(page_records)} rows | Section total: {len(records)}")
        except PlaywrightTimeout:
            print(f"  TIMEOUT on page {page_num}. Stopping section.")
            break
        except Exception as e:
            print(f"  ERROR on page {page_num}: {e}")
            break

        if not click_next_page(page):
            print(f"  Reached last page of {label} (after page {page_num}).")
            break

        time.sleep(PAGE_RENDER_WAIT)
        page_num += 1

    print(f"  {label} complete: {len(records)} records across {page_num} pages.")
    save_section_output(records, file_stem, label)
    return records


def main():
    print("=" * 70)
    print("CAAR Unified Scraper (Headless / Cloud)")
    print("=" * 70)

    all_records = []
    section_summary = []
    overall_start = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            for label, url, expected_pages, file_stem in SECTIONS:
                section_records = scrape_section(
                    page, label, url, expected_pages, file_stem
                )
                all_records.extend(section_records)
                section_summary.append((label, len(section_records)))

            print("\n" + "=" * 70)
            print("ALL SECTIONS COMPLETE")
            for label, count in section_summary:
                print(f"  {label:20s}: {count} records")
            print(f"  {'TOTAL':20s}: {len(all_records)} records")
            print(f"  Total runtime:        {(time.time() - overall_start):.1f}s")

            save_consolidated(all_records)

        except Exception as e:
            print(f"\nFATAL ERROR: {e}")
            if all_records:
                print("Saving partial data...")
                save_consolidated(all_records)
            sys.exit(1)

        finally:
            browser.close()

    print("\nScraper finished successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
