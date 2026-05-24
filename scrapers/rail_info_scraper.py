from datetime import datetime
import json
import random
import re
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
from bs4 import BeautifulSoup

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]


def extract_days_from_page(page) -> dict[str, list[str]]:
    """
    Extract running days for each train entirely in the browser,
    using computed color to distinguish active vs inactive days.
    Returns {train_number: [active day names]}
    """
    return page.evaluate("""
        () => {
            const dayLabels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
            const result = {};

            const ttLinks = document.querySelectorAll('a[href^="/time-table/"]');
            const seen = new Set();

            for (const link of ttLinks) {
                const match = link.getAttribute('href')?.match(/\\/time-table\\/(\\d+)/);
                if (!match || seen.has(match[1])) continue;
                seen.add(match[1]);
                const trainNum = match[1];

                let card = link.closest('.MuiPaper-root');
                if (!card) continue;

                const allText = card.querySelectorAll('p');
                let runsOnP = null;
                for (const p of allText) {
                    if (p.textContent.includes('Runs on:')) {
                        runsOnP = p;
                        break;
                    }
                }
                if (!runsOnP) continue;

                const container = runsOnP.parentElement;
                if (!container) continue;

                const dayBoxes = [...container.children].filter(
                    el => el.tagName === 'DIV' && 'MTWTFS'.includes(el.textContent.trim())
                );

                if (dayBoxes.length < 7) continue;

                const colors = dayBoxes.slice(0, 7).map(d => ({
                    color: window.getComputedStyle(d).color
                }));

                function brightness(rgbStr) {
                    const nums = rgbStr.match(/\\d+/g);
                    if (!nums || nums.length < 3) return 999;
                    return parseInt(nums[0]) + parseInt(nums[1]) + parseInt(nums[2]);
                }

                const uniqueColors = [...new Set(colors.map(c => c.color))];

                let activeDays = [];
                if (uniqueColors.length === 1) {
                    activeDays = dayLabels.slice();
                } else {
                    const darkest = uniqueColors.reduce((a, b) =>
                        brightness(a) < brightness(b) ? a : b
                    );
                    for (let i = 0; i < 7; i++) {
                        if (colors[i].color === darkest) {
                            activeDays.push(dayLabels[i]);
                        }
                    }
                }

                result[trainNum] = activeDays;
            }
            return result;
        }
    """)


def parse_next_run_date(date_str: str, journey_date: str) -> str:
    """
    Convert:
        'Wed, Jan 01'
    into:
        '2027-01-01'

    based on journey_date format:
        'YYYY-MM-DD'
    """

    journey_dt = datetime.strptime(journey_date, "%Y-%m-%d")

    # First try current journey year
    dt = datetime.strptime(
        f"{date_str} {journey_dt.year}",
        "%a, %b %d %Y"
    )

    # If parsed date already passed, move to next year
    if dt.date() < journey_dt.date():
        dt = datetime.strptime(
            f"{date_str} {journey_dt.year + 1}",
            "%a, %b %d %Y"
        )

    return dt.strftime("%Y-%m-%d")


def parse_trains(html: str, journey_date: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []

    cards = soup.find_all(
        lambda tag: tag.name == "div"
        and any("MuiPaper-root" in c for c in tag.get("class", []))
        and tag.find("a", href=re.compile(r"^/time-table/\d+"))
        and tag.find(string=re.compile(r"Runs on:"))
    )

    for card in cards:
        try:
            # ── Train number & name ───────────────────────────────────────
            tt_link = card.find("a", href=re.compile(r"^/time-table/\d+"))
            if not tt_link:
                continue

            train_number = None
            train_name = None
            num_span = tt_link.find("span")
            if num_span:
                train_number = num_span.get_text(strip=True)
                full_text = tt_link.get_text(strip=True)
                train_name = full_text.replace(train_number, "", 1).strip()

            # ── Departure & Arrival ───────────────────────────────────────
            time_spans = card.find_all(
                "span", style=re.compile(r"font-size:\s*1\.8rem")
            )

            departure_date = None
            next_run_div = card.find(
                lambda tag: tag.name == "div"
                and not tag.find()  # leaf node
                and "Next run on" in tag.get_text()
            )

            if next_run_div:
                # "Next run on Wed, Jul 01"
                raw = next_run_div.get_text(strip=True)
                departure_date = raw.replace(
                    "Next run on", "").strip()  # "Wed, Jul 01"
                departure_date = parse_next_run_date(
                    departure_date, journey_date)

            dep_station = dep_time = arr_time = arr_station = None
            dep_city = arr_city = None

            if len(time_spans) >= 2:
                dep_text = time_spans[0].get_text(strip=True).rstrip(",")
                dep_text2 = time_spans[1].get_text(strip=True).rstrip(",")

                if ":" in dep_text2:
                    dep_station = dep_text
                    dep_time = dep_text2
                else:
                    dep_station = dep_text2
                    dep_time = dep_text

            if len(time_spans) >= 4:
                arr_text = time_spans[2].get_text(strip=True).rstrip(",")
                arr_text2 = time_spans[3].get_text(strip=True).rstrip(",")

                if ":" in arr_text:
                    arr_time = arr_text
                    arr_station = arr_text2
                else:
                    arr_time = arr_text2
                    arr_station = arr_text

            city_spans = card.find_all(
                "span", style=re.compile(r"font-size:\s*1\.5rem")
            )
            if len(city_spans) >= 1:
                dep_city = city_spans[0].get_text(strip=True)
            if len(city_spans) >= 2:
                arr_city = city_spans[1].get_text(strip=True)

            # ── Duration, halts, distance ─────────────────────────────────
            duration = None
            halts = None
            distance = None

            dur_spans = card.find_all(
                "span", style=re.compile(r"font-weight:\s*700")
            )
            dur_parts = [
                s.get_text(strip=True) for s in dur_spans
                if re.search(r"\d+\s*[hm]", s.get_text(strip=True))
            ]
            if dur_parts:
                duration = " ".join(dur_parts)

            halts_match = re.search(r"(\d+)\s*halts", card.get_text())
            if halts_match:
                halts = int(halts_match.group(1))

            dist_match = re.search(r"(\d+)\s*kms", card.get_text())
            if dist_match:
                distance = f"{dist_match.group(1)} km"

            # ── Ticket classes ────────────────────────────────────────────
            tickets = []
            seat_boxes = card.find_all(
                lambda tag: tag.name == "div"
                and any("Mui-seat__layout_box" in c for c in tag.get("class", []))
            )

            for box in seat_boxes:
                cls_tag = box.find(
                    lambda t: any(
                        "Mui-booking_class__title" in c for c in t.get("class", []))
                )
                price_tag = box.find(
                    lambda t: any(
                        "Mui-booking_class__price" in c for c in t.get("class", []))
                )
                avail_tag = box.find(
                    lambda t: any(
                        "Mui-availibility_and__seat_count_title" in c for c in t.get("class", []))
                )

                cls_name = cls_tag.get_text(strip=True) if cls_tag else None

                price = None
                if price_tag:
                    price_num = re.search(
                        r"(\d+)", price_tag.get_text(strip=True))
                    price = int(price_num.group(1)) if price_num else None

                availability = None
                probability = None
                if avail_tag:
                    for s in avail_tag.find_all("span", recursive=True):
                        text = s.get_text(strip=True)
                        if "Waitlist" in text or "Available" in text or "RAC" in text:
                            availability = text
                    prob_tag = avail_tag.find(
                        lambda t: any(
                            "Mui-probability__title" in c for c in t.get("class", []))
                    )
                    if prob_tag:
                        probability = prob_tag.get_text(strip=True)

                tickets.append({
                    "class": cls_name,
                    "price": f"INR {price}",
                    "availability": availability,
                    "probability": probability if probability else "UNKNOWN",
                })

            results.append({
                "train_name": train_name,
                "train_number": train_number,
                "train_link": f"https://www.railyatri.in/time-table/{train_number}",
                "depart_days": [],  # filled in by extract_days_from_page()
                "departure_date": departure_date if departure_date else journey_date,
                "departure": {
                    "station_code": dep_station,
                    "station_name": dep_city,
                    "time": dep_time,
                },
                "arrival": {
                    "station_code": arr_station,
                    "station_name": arr_city,
                    "time": arr_time,
                },
                "duration": duration,
                "halts": halts,
                "distance": distance,
                "tickets": tickets,
                "source": "RailYatri"
            })

        except Exception as e:
            print(f"[warn] skipped a card — {e}")
            continue

    return results


def is_page_valid(page) -> bool:
    title = page.title().lower()
    bad = ["error", "something went wrong",
           "403", "access denied", "just a moment"]
    if any(b in title for b in bad):
        print(f"[!] Bad page title: '{page.title()}'")
        return False
    if not page.query_selector("a[href^='/time-table/']"):
        print("[!] No train cards found")
        return False
    return True


def _attempt_scrape(p, from_code: str, to_code: str, journey_date: str) -> list[dict] | None:
    url = (
        f"https://www.railyatri.in/booking/trains-between-stations"
        f"?from_code={from_code}&to_code={to_code}&journey_date={journey_date}"
    )

    browser = p.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": 1366, "height": 768},
        locale="en-IN",
        timezone_id="Asia/Kolkata",
    )
    page = context.new_page()

    try:
        page.goto("https://www.railyatri.in",
                  wait_until="domcontentloaded", timeout=10_000)
        time.sleep(random.uniform(1, 2))

        page.goto(url, wait_until="domcontentloaded", timeout=10_000)
        page.wait_for_selector("a[href^='/time-table/']", timeout=10_000)
        time.sleep(random.uniform(1.5, 2.5))

        if not is_page_valid(page):
            return None

        html = page.content()
        results = parse_trains(html, journey_date)

        # Resolve running days from live DOM computed styles
        days_map = extract_days_from_page(page)
        for train in results:
            num = train.get("train_number")
            if num and num in days_map:
                train["depart_days"] = days_map[num]

        return results

    except PlaywrightTimeoutError as e:
        print(f"[!] Timeout: {e}")
        return None
    except Exception as e:
        print(f"[!] Error: {e}")
        return None
    finally:
        context.close()
        browser.close()


def scrape_trains(from_code: str, to_code: str, journey_date: str) -> list[dict]:
    with Stealth().use_sync(sync_playwright()) as p:
        result = _attempt_scrape(p, from_code, to_code, journey_date)

        if result is not None:
            print(f"[✓] Got {len(result)} trains.")
            return result
        else:
            return []


if __name__ == "__main__":
    print("Scraping RailYatri...")
    trains = scrape_trains(
        from_code="HWH",
        to_code="MTJ",
        journey_date="2026-06-30",
    )
    json.dump(
        trains,
        open("railyatri_trains.json", "w", encoding="utf-8"),
        indent=2,
        ensure_ascii=False,
    )
    print(f"Saved {len(trains)} trains → railyatri_trains.json")
