#!/usr/bin/env python3
"""Daily UP TET / Super TET current-affairs PDF.

Flow: RSS (PIB, The Hindu, Indian Express) -> keep PREVIOUS day's items (IST)
      -> Gemini picks 10 -> Gemini writes each in A-F format -> maps -> PDF -> Gmail.
"""
import os, re, sys, json, time, html, smtplib, datetime as dt
from email.message import EmailMessage
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")   # change if Google renames models
CALL_GAP = float(os.getenv("CALL_GAP", "7"))             # seconds between Gemini calls (free-tier rate limit)
OUT_DIR = "output"
MAP_DIR = os.path.join(OUT_DIR, "maps")
EXAM = "UP TET / Super TET"

# Verify these URLs once in a browser; sites sometimes change their feeds.
FEEDS = [
    ("PIB", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3"),
    ("The Hindu", "https://www.thehindu.com/news/national/feeder/default.rss"),
    ("The Hindu", "https://www.thehindu.com/education/feeder/default.rss"),
    ("The Hindu", "https://www.thehindu.com/sci-tech/feeder/default.rss"),
    ("The Hindu", "https://www.thehindu.com/sport/feeder/default.rss"),
    ("The Hindu", "https://www.thehindu.com/sci-tech/energy-and-environment/feeder/default.rss"),
    ("Indian Express", "https://indianexpress.com/section/india/feed/"),
    ("Indian Express", "https://indianexpress.com/section/education/feed/"),
    ("Indian Express", "https://indianexpress.com/section/explained/feed/"),
    ("Indian Express", "https://indianexpress.com/section/sports/feed/"),
    ("Indian Express", "https://indianexpress.com/section/cities/lucknow/feed/"),
]

QUOTES = [
    ("Education is the most powerful weapon which you can use to change the world.", "Nelson Mandela"),
    ("Dream, dream, dream. Dreams transform into thoughts and thoughts result in action.", "A. P. J. Abdul Kalam"),
    ("Education is the manifestation of the perfection already in man.", "Swami Vivekananda"),
    ("The future belongs to those who believe in the beauty of their dreams.", "Eleanor Roosevelt"),
    ("Arise, awake, and stop not till the goal is reached.", "Swami Vivekananda"),
    ("It always seems impossible until it is done.", "Nelson Mandela"),
    ("Learning never exhausts the mind.", "Leonardo da Vinci"),
]


def esc(x):
    return html.escape(str(x if x is not None else ""))


# ----------------------------------------------------------------- dates
def target_date():
    """Previous day in IST (override with TARGET_DATE=YYYY-MM-DD)."""
    env = os.getenv("TARGET_DATE", "").strip()
    if env:
        return dt.date.fromisoformat(env)
    return dt.datetime.now(IST).date() - dt.timedelta(days=1)


# ----------------------------------------------------------------- news
def strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def fetch_candidates(day):
    import feedparser
    seen, out = set(), []
    for source, url in FEEDS:
        try:
            feed = feedparser.parse(url)
        except Exception as ex:
            print(f"[feed fail] {url}: {ex}")
            continue
        n = 0
        for e in feed.entries:
            tm = e.get("published_parsed") or e.get("updated_parsed")
            if not tm:
                continue
            d = dt.datetime(*tm[:6], tzinfo=dt.timezone.utc).astimezone(IST).date()
            if d != day:
                continue
            title = strip_tags(e.get("title", ""))
            key = title.lower()
            if not title or key in seen:
                continue
            seen.add(key)
            out.append({"source": source, "title": title, "link": e.get("link", ""),
                        "summary": strip_tags(e.get("summary", ""))[:300]})
            n += 1
        print(f"[feed] {source} {url.split('/')[-3:-1]} -> {n} items for {day}")
    return out[:90]


def article_text(url, fallback):
    try:
        import trafilatura
        raw = trafilatura.fetch_url(url)
        txt = trafilatura.extract(raw) if raw else None
        if txt and len(txt) > 300:
            return txt[:4500]
    except Exception as ex:
        print(f"[article fail] {url}: {ex}")
    return fallback


# ----------------------------------------------------------------- gemini
def make_client():
    from google import genai
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def ask_json(client, prompt, retries=4):
    from google.genai import types
    last = None
    for i in range(retries):
        try:
            r = client.models.generate_content(
                model=MODEL, contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.3))
            time.sleep(CALL_GAP)
            return json.loads(r.text)
        except Exception as ex:
            last = ex
            wait = 20 * (i + 1)
            print(f"[gemini retry {i+1}] {ex} -> waiting {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Gemini failed: {last}")


def pick_top10(client, cands, day):
    if len(cands) <= 10:
        return [(c, "") for c in cands]
    lines = "\n".join(f"{i} | {c['source']} | {c['title']} | {c['summary'][:160]}" for i, c in enumerate(cands))
    prompt = f"""You are the editor of a daily current-affairs PDF for {EXAM} (teacher eligibility exams, Uttar Pradesh).
Date of news: {day}. From the numbered list below choose exactly 10 DIFFERENT stories (no duplicates of one event).
Balanced mix: ~3 national/government schemes/policy, ~2 Uttar Pradesh or state news, ~1-2 education/NEP/child development,
~1-2 science-tech/environment, ~1 sports/awards/important days. Prefer stories with strong static-GK linkage.
Skip crime, gossip, opinion and pure politics.
Return JSON: {{"picks":[{{"index":<int>,"category":"<short label>"}}]}}

{lines}"""
    data = ask_json(client, prompt)
    picks, used = [], set()
    for p in data.get("picks", []):
        try:
            i = int(p["index"])
        except Exception:
            continue
        if 0 <= i < len(cands) and i not in used:
            used.add(i)
            picks.append((cands[i], p.get("category", "")))
    return picks[:10]


ITEM_PROMPT = """You write exam notes for {exam}. News date: {day}. Source: {source}.
Headline: {title}
Article text (the ONLY source for 'why_in_news'):
\"\"\"{text}\"\"\"

Return ONE JSON object with exactly these keys:
{{
 "headline_en": "clear English headline",
 "headline_hi": "Hindi headline in Devanagari",
 "category": "National | Uttar Pradesh | Education | Science & Tech | Environment | Sports | Awards & Days | International | Economy",
 "why_in_news": "3-5 sentences, only facts from the article text, in your own words",
 "historical_linkage": "3-5 sentences: background, earlier events, related Acts/schemes/years",
 "static_facts": ["AT LEAST 10 short exam-relevant facts related to this news (polity, geography, history, science, EVS, education/CDP, GK)"],
 "mnemonic": "a short memory trick for some of the facts, or empty string",
 "map": {{"type": "none | india_physical | india_political | world_physical | world_political | image",
          "image_query": "only for type image: 3-6 word English search phrase for Wikimedia Commons",
          "highlight_states": ["official Indian state/UT names"], "highlight_countries": ["English country names"],
          "points": [{{"name": "place", "lat": 0.0, "lon": 0.0}}], "caption": "one line"}},
 "table": null,
 "fun_fact": "one catchy line useful for a one-day exam"
}}
Rules:
- Use only facts you are confident are correct. Never invent figures, dates or names; leave a fact out if unsure.
- Do not copy sentences from the article.
- "map": use a type other than "none" only when a place/geography is central. India-wide physical features -> india_physical. Use type "image" (with image_query) when a DIAGRAM or a picture is needed that cannot be drawn as an India/world map (e.g. parts of a plant, a rocket, a monument, a river-basin or ocean-current diagram).
- "table": null unless a comparison or data table is genuinely useful; otherwise {{"title": "", "columns": [], "rows": [[]]}} with at most 8 rows.
"""


def write_item(client, cand, category_hint, day):
    text = article_text(cand["link"], cand["summary"] or cand["title"])
    prompt = ITEM_PROMPT.format(exam=EXAM, day=day, source=cand["source"], title=cand["title"], text=text)
    data = ask_json(client, prompt)
    facts = [str(f) for f in data.get("static_facts", []) if str(f).strip()]
    if len(facts) < 10:
        data2 = ask_json(client, prompt + f"\nYour last answer had only {len(facts)} static_facts. Return the full JSON again with at least 10.")
        facts2 = [str(f) for f in data2.get("static_facts", []) if str(f).strip()]
        if len(facts2) > len(facts):
            data, facts = data2, facts2
    data["static_facts"] = facts
    data.setdefault("category", category_hint or "")
    data["source"] = cand["source"]
    data["link"] = cand["link"]
    return data


# ----------------------------------------------------------------- html / pdf
CSS = """
@page { size: A4; margin: 16mm 14mm 18mm 14mm;
  @bottom-center { content: "__EXAM__ | Current Affairs __DATE__ | Page " counter(page); font-size: 8pt; color: #5b6b8c; } }
@page :first { margin: 0; @bottom-center { content: none; } }
* { box-sizing: border-box; }
body { font-family: "Noto Sans", "Noto Sans Devanagari", "DejaVu Sans", sans-serif; font-size: 10pt; color: #1b2433; line-height: 1.45; }
.cover { height: 296mm; padding: 0 0 14mm 0; page-break-after: always; position: relative; }
.band { background: #0b3d91; color: #fff; padding: 26mm 18mm 14mm 18mm; }
.band .exam { letter-spacing: 2px; font-size: 11pt; opacity: .9; }
.band h1 { font-size: 30pt; margin: 6mm 0 2mm 0; line-height: 1.1; }
.band .date { font-size: 15pt; margin-top: 4mm; color: #cfe0ff; }
.cover .inner { padding: 10mm 18mm 0 18mm; }
.cover h2 { color: #0b3d91; font-size: 13pt; border-bottom: 2px solid #0b3d91; padding-bottom: 2mm; margin: 0 0 3mm 0; }
.toc { list-style: none; padding: 0; margin: 0; }
.toc li { padding: 1.6mm 0; border-bottom: 1px dotted #b8c7e6; }
.toc .hi { color: #5b6b8c; font-size: 9pt; display: block; }
.quote { margin-top: 9mm; background: #e8f0fe; border-left: 4px solid #0b3d91; padding: 4mm 5mm; font-style: italic; }
.quote span { display: block; margin-top: 1.5mm; font-style: normal; font-size: 9pt; color: #0b3d91; }
.note { position: absolute; bottom: 10mm; left: 18mm; right: 18mm; font-size: 7.5pt; color: #5b6b8c; }
.item { margin-top: 7mm; }
.item h2 { background: #0b3d91; color: #fff; font-size: 12.5pt; padding: 2.5mm 3.5mm; margin: 0; break-after: avoid; }
.item .hi { background: #e8f0fe; color: #0b3d91; padding: 1.5mm 3.5mm; font-weight: bold; break-after: avoid; }
.tag { display: inline-block; font-size: 7.5pt; background: #cfe0ff; color: #0b3d91; padding: .4mm 2mm; border-radius: 2mm; margin: 2mm 0; }
h3 { color: #0b3d91; font-size: 10.5pt; margin: 3.5mm 0 1mm 0; break-after: avoid; }
p { margin: 0 0 1.5mm 0; text-align: justify; }
ol.facts { margin: 0; padding-left: 6mm; }
ol.facts li { margin-bottom: .8mm; }
.mnemo { background: #fff8e1; border: 1px solid #f0d78c; padding: 2mm 3mm; margin-top: 2mm; }
figure { margin: 2mm 0; text-align: center; break-inside: avoid; }
figure img { max-width: 100%; max-height: 105mm; border: 1px solid #b8c7e6; }
figcaption { font-size: 8pt; color: #5b6b8c; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; break-inside: avoid; }
th { background: #0b3d91; color: #fff; padding: 1.2mm 2mm; text-align: left; }
td { border: 1px solid #b8c7e6; padding: 1.2mm 2mm; }
tr:nth-child(even) td { background: #f3f7ff; }
.fun { background: #e6f4ea; border-left: 4px solid #2e7d32; padding: 2mm 3mm; margin-top: 2mm; break-inside: avoid; }
.src { font-size: 7.5pt; color: #5b6b8c; margin-top: 1.5mm; }
"""


def build_html(items, day):
    date_long = f"{day.day} {day.strftime('%B %Y')}"
    weekday = day.strftime("%A")
    q, who = QUOTES[day.toordinal() % len(QUOTES)]
    toc = "".join(
        f"<li>{i}. {esc(it.get('headline_en'))}<span class='hi'>{esc(it.get('headline_hi'))}</span></li>"
        for i, it in enumerate(items, 1))
    parts = [f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS.replace('__EXAM__', EXAM).replace('__DATE__', date_long)}</style></head><body>
<div class="cover">
  <div class="band"><div class="exam">{esc(EXAM)}</div><h1>Daily Current Affairs</h1>
  <div class="date">{esc(date_long)} ({weekday})</div></div>
  <div class="inner"><h2>Today's {len(items)} news</h2><ol class="toc" style="list-style:none">{toc}</ol>
  <div class="quote">&ldquo;{esc(q)}&rdquo;<span>- {esc(who)}</span></div></div>
  <div class="note">Notes are AI-assisted from PIB, The Hindu and Indian Express reports. Verify dates and figures from official sources before the exam. Maps are for study purposes only.</div>
</div>"""]
    for i, it in enumerate(items, 1):
        facts = "".join(f"<li>{esc(f)}</li>" for f in it.get("static_facts", []))
        mn = f"<div class='mnemo'><b>Mnemonic:</b> {esc(it['mnemonic'])}</div>" if it.get("mnemonic") else ""
        mp = ""
        if it.get("map_file"):
            cap = esc((it.get("map") or {}).get("caption", ""))
            if it.get("map_credit"):
                cap += f" <br><small>{esc(it['map_credit'])}. Boundaries may differ from India's official map.</small>"
            mp = f"<h3>D. Map</h3><figure><img src='{esc(it['map_file'])}'><figcaption>{cap}</figcaption></figure>"
        tb = ""
        t = it.get("table")
        if isinstance(t, dict) and t.get("columns") and any(t.get("rows") or []):
            head = "".join(f"<th>{esc(c)}</th>" for c in t["columns"])
            body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in t["rows"] if r)
            tb = f"<h3>E. Data table: {esc(t.get('title', ''))}</h3><table><tr>{head}</tr>{body}</table>"
        parts.append(f"""<div class="item">
<h2>{i}. {esc(it.get('headline_en'))}</h2><div class="hi">{esc(it.get('headline_hi'))}</div>
<span class="tag">{esc(it.get('category'))}</span>
<h3>A. Why in news</h3><p>{esc(it.get('why_in_news'))}</p>
<h3>B. Historical data / linkage</h3><p>{esc(it.get('historical_linkage'))}</p>
<h3>C. Static facts</h3><ol class="facts">{facts}</ol>{mn}
{mp}{tb}
<h3>F. Fun fact for one-day exam</h3><div class="fun">{esc(it.get('fun_fact'))}</div>
<div class="src">Source: {esc(it.get('source'))}</div></div>""")
    parts.append("</body></html>")
    return "\n".join(parts)


def make_maps(items):
    try:
        from maps import draw_map
    except Exception as ex:
        print(f"[maps disabled] {ex}")
        draw_map = None
    for i, it in enumerate(items, 1):
        spec = it.get("map") or {}
        kind = spec.get("type", "none")
        if kind == "none":
            continue
        try:
            if kind == "image":
                from images import fetch_image
                res = fetch_image(spec.get("image_query", ""), os.path.join(MAP_DIR, f"img_{i}"))
                if res:
                    it["map_file"] = os.path.relpath(res[0], ".")
                    it["map_credit"] = res[1]
            elif draw_map:
                path = os.path.join(MAP_DIR, f"map_{i}.png")
                if draw_map(spec, path):
                    it["map_file"] = os.path.relpath(path, ".")
        except Exception as ex:   # a bad map/image must never kill the whole PDF
            print(f"[map {i} failed] {ex}")


def send_email(pdf_path, day):
    user, pwd, to = os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"], os.environ["MAIL_TO"]
    msg = EmailMessage()
    msg["Subject"] = f"Current Affairs {day.strftime('%d-%m-%Y')} | {EXAM}"
    msg["From"], msg["To"] = user, to
    msg.set_content(f"Your {EXAM} current affairs PDF for {day.strftime('%d %B %Y')} is attached.")
    with open(pdf_path, "rb") as f:
        msg.add_attachment(f.read(), maintype="application", subtype="pdf", filename=os.path.basename(pdf_path))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pwd)
        s.send_message(msg)
    print("[email sent]")


def send_telegram(pdf_path=None, caption="", text=""):
    import requests
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    base = f"https://api.telegram.org/bot{token}"
    if pdf_path:
        with open(pdf_path, "rb") as f:
            r = requests.post(f"{base}/sendDocument", data={"chat_id": chat, "caption": caption[:1000]},
                              files={"document": (os.path.basename(pdf_path), f, "application/pdf")}, timeout=180)
    else:
        r = requests.post(f"{base}/sendMessage", data={"chat_id": chat, "text": text[:4000]}, timeout=60)
    r.raise_for_status()
    print("[telegram sent]")


def notify_failure(msg):
    if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        try:
            send_telegram(text=f"Current affairs build failed: {msg}")
        except Exception as ex:
            print(f"[telegram notify failed] {ex}")


def main():
    try:
        run()
    except (Exception, SystemExit) as ex:
        notify_failure(str(ex))
        raise


def run():
    day = target_date()
    print(f"Building current affairs for {day}")
    os.makedirs(MAP_DIR, exist_ok=True)
    cands = fetch_candidates(day)
    if not cands:
        sys.exit(f"No feed items found for {day}. Check the FEEDS list.")
    client = make_client()
    picks = pick_top10(client, cands, day)
    items = []
    for cand, cat in picks:
        try:
            items.append(write_item(client, cand, cat, day))
            print(f"[done] {cand['title'][:70]}")
        except Exception as ex:
            print(f"[skip] {cand['title'][:70]}: {ex}")
    if not items:
        sys.exit("Gemini returned nothing.")
    make_maps(items)
    html_doc = build_html(items, day)
    pdf_path = os.path.join(OUT_DIR, f"Current_Affairs_{day.strftime('%d-%m-%Y')}.pdf")
    from weasyprint import HTML
    HTML(string=html_doc, base_url=os.getcwd()).write_pdf(pdf_path)
    print(f"[pdf] {pdf_path}")
    if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        heads = "\n".join(f"{i}. {it.get('headline_en','')}" for i, it in enumerate(items, 1))
        send_telegram(pdf_path, caption=f"Current Affairs {day.strftime('%d %B %Y')} | {EXAM}\n\n{heads}")
    if os.getenv("GMAIL_USER") and os.getenv("MAIL_TO"):   # optional extra copy by email
        send_email(pdf_path, day)


if __name__ == "__main__":
    main()
