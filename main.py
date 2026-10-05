"""Daily UP TET / Super TET current affairs PDF.
Free stack: feedparser + trafilatura + Gemini free tier + geopandas/matplotlib + weasyprint + Telegram.
"""
import os, io, re, json, time, base64, html, tempfile
import datetime as dt
import feedparser, requests, trafilatura
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import geopandas as gpd
from google import genai
from weasyprint import HTML

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
TODAY = dt.datetime.now(IST)
DATE_STR = TODAY.strftime("%d %B %Y")
OUT = f"Current_Affairs_{TODAY.strftime('%d-%m-%Y')}.pdf"

# Check these URLs once in a browser; sites change feed links sometimes.
FEEDS = {
    "PIB": "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
    "The Hindu": "https://www.thehindu.com/news/national/feeder/default.rss",
    "The Hindu (Education)": "https://www.thehindu.com/education/feeder/default.rss",
    "Indian Express": "https://indianexpress.com/section/india/feed/",
    "Indian Express (Education)": "https://indianexpress.com/section/education/feed/",
}

SYLLABUS = (
    "UP TET / Super TET: child development & pedagogy, NEP 2020, RTE Act, education schemes "
    "and policies, central and Uttar Pradesh government schemes, awards and honours, sports, "
    "environment and biodiversity, science and technology, important days, Indian geography, "
    "polity, economy, EVS, general knowledge."
)

NE = "https://naturalearth.s3.amazonaws.com"
STATES_URL = f"{NE}/10m_cultural/ne_10m_admin_1_states_provinces.zip"
RIVERS_URL = f"{NE}/10m_physical/ne_10m_rivers_lake_centerlines.zip"


def ask(prompt, retries=3):
    for i in range(retries):
        try:
            r = client.models.generate_content(
                model=MODEL, contents=prompt,
                config={"response_mime_type": "application/json", "temperature": 0.3},
            )
            txt = re.sub(r"^```(?:json)?|```$", "", r.text.strip(), flags=re.M).strip()
            return json.loads(txt)
        except Exception as e:
            print("Gemini retry:", e)
            time.sleep(20 * (i + 1))
    return None


def collect():
    items = []
    for src, url in FEEDS.items():
        try:
            for e in feedparser.parse(url).entries[:20]:
                items.append({"source": src, "title": e.get("title", ""),
                              "link": e.get("link", ""), "summary": e.get("summary", "")[:300]})
        except Exception as ex:
            print("Feed failed:", src, ex)
    return items


def select(items):
    listing = "\n".join(f"{i}. [{x['source']}] {x['title']}" for i, x in enumerate(items))
    prompt = (
        f"Syllabus: {SYLLABUS}\nFrom the headlines below pick the 10 most useful for this exam. "
        "Prefer variety (education, schemes, environment, science, sports, geography, polity). "
        "Avoid duplicates and pure politics/crime. Return JSON: {\"indices\": [10 integers]}.\n\n"
        + listing)
    res = ask(prompt)
    idx = res["indices"][:10] if res else list(range(10))
    return [items[i] for i in idx if 0 <= i < len(items)]


STORY_PROMPT = """You are writing exam notes for UP TET / Super TET aspirants.
News headline: {title}
Source: {source}
Article text (may be partial): {text}

Write ORIGINAL notes in your own words (do not copy sentences). Return ONLY JSON:
{{
 "headline": "clear headline",
 "why_in_news": "3-5 sentences",
 "historical_linkage": "background, history, earlier related events/laws/dates",
 "static_facts": ["at least 10 exam-relevant static facts closely related to this topic"],
 "map": null or {{"title": "...", "features": [
     {{"name": "Nanda Devi", "type": "mountain|river|lake|park|dam|port|city|state|other",
       "query": "Nanda Devi, Uttarakhand, India"}} ]}},
 "table": null or {{"title": "...", "columns": ["..."], "rows": [["..."]]}},
 "fun_fact": "one memorable fact useful for a one-day exam"
}}
Rules: include "map" ONLY if the news is tied to physical geography (mountain, river, lake,
national park, dam, port, state/region). Max 6 features. For a river use type "river" and its
exact name. For a state use type "state" and the exact state name. "table" only if real
comparable data exists. Do not invent figures; if unsure, leave the fact out."""


def build_story(item):
    text = ""
    try:
        d = trafilatura.fetch_url(item["link"])
        text = (trafilatura.extract(d) or "")[:4000] if d else ""
    except Exception:
        pass
    text = text or item["summary"]
    s = ask(STORY_PROMPT.format(title=item["title"], source=item["source"], text=text))
    if s:
        s["source"] = item["source"]
    return s


# ---------- maps ----------
_cache = {}


def _load(url, name):
    if name not in _cache:
        p = os.path.join(tempfile.gettempdir(), name + ".zip")
        if not os.path.exists(p):
            with open(p, "wb") as f:
                f.write(requests.get(url, timeout=120).content)
        _cache[name] = gpd.read_file(f"zip://{p}")
    return _cache[name]


def geocode(q):
    time.sleep(1.1)  # Nominatim: max 1 request/sec
    r = requests.get("https://nominatim.openstreetmap.org/search",
                     params={"q": q, "format": "json", "limit": 1},
                     headers={"User-Agent": "tet-current-affairs-bot"}, timeout=30).json()
    return (float(r[0]["lon"]), float(r[0]["lat"])) if r else None


MARK = {"mountain": ("^", "saddlebrown"), "lake": ("o", "dodgerblue"), "park": ("*", "green"),
        "dam": ("s", "dimgray"), "port": ("P", "navy"), "city": ("o", "black"), "other": ("o", "red")}


def draw_map(spec):
    try:
        feats = spec.get("features") or []
        states = _load(STATES_URL, "states")
        india = states[states["admin"] == "India"]
        fig, ax = plt.subplots(figsize=(6, 6.4))
        india.plot(ax=ax, color="#f4efe2", edgecolor="#888", linewidth=0.5)
        hi = [f["name"].lower() for f in feats if f.get("type") == "state"]
        if hi:
            india[india["name"].str.lower().isin(hi)].plot(ax=ax, color="#f7c873", edgecolor="#555")
        rivers = [f["name"].lower() for f in feats if f.get("type") == "river"]
        if rivers:
            rv = _load(RIVERS_URL, "rivers")
            rv = rv[rv["name"].fillna("").str.lower().apply(lambda n: any(r in n for r in rivers))]
            rv = rv.cx[68:98, 6:38]
            if len(rv):
                rv.plot(ax=ax, color="#1f77b4", linewidth=1.8)
                for _, row in rv.iterrows():
                    c = row.geometry.representative_point()
                    ax.annotate(row["name"], (c.x, c.y), fontsize=8, color="#1f4e79")
        for f in feats:
            t = f.get("type")
            if t in ("river", "state"):
                if t == "state":
                    for _, row in india[india["name"].str.lower() == f["name"].lower()].iterrows():
                        c = row.geometry.representative_point()
                        ax.annotate(f["name"], (c.x, c.y), fontsize=8, ha="center")
                continue
            pt = geocode(f.get("query") or f["name"])
            if pt and 67 < pt[0] < 98 and 6 < pt[1] < 38:
                m, col = MARK.get(t, MARK["other"])
                ax.scatter(*pt, marker=m, s=90, color=col, edgecolor="k", zorder=5)
                ax.annotate(f["name"], pt, xytext=(4, 4), textcoords="offset points",
                            fontsize=8, weight="bold")
        ax.set_xlim(67, 98.5); ax.set_ylim(6, 37.5); ax.axis("off")
        ax.set_title(spec.get("title", ""), fontsize=11)
        fig.text(0.5, 0.02, "Illustrative map - not to scale, not an authority on boundaries",
                 ha="center", fontsize=6.5, color="gray")
        buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=130, bbox_inches="tight"); plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print("Map failed:", e)
        return None


# ---------- PDF ----------
CSS = """
@page { size: A4; margin: 16mm; @bottom-center { content: counter(page); font-size: 9pt; color: #777; } }
body { font-family: 'Noto Sans', sans-serif; font-size: 10.5pt; line-height: 1.45; color: #222; }
h1 { text-align: center; color: #1a3d7c; border-bottom: 3px solid #1a3d7c; padding-bottom: 6px; }
.story { page-break-before: always; }
h2 { color: #1a3d7c; font-size: 14pt; margin-bottom: 2px; }
.src { font-size: 8.5pt; color: #888; margin-bottom: 8px; }
h3 { font-size: 11pt; background: #e8eefb; padding: 3px 8px; margin: 12px 0 4px; }
table { border-collapse: collapse; width: 100%; font-size: 9.5pt; }
th, td { border: 1px solid #999; padding: 4px 6px; text-align: left; }
th { background: #dde6f7; }
.fun { border: 2px dashed #e08a00; background: #fff6e5; padding: 8px; }
img { max-width: 100%; max-height: 330px; display: block; margin: auto; }
"""
e = html.escape


def story_html(n, s):
    out = [f"<div class='story'><h2>{n}. {e(s['headline'])}</h2><div class='src'>Source: {e(s['source'])}</div>"]
    out.append(f"<h3>A. Why in News</h3><p>{e(s['why_in_news'])}</p>")
    out.append(f"<h3>B. Historical Data / Linkage</h3><p>{e(s['historical_linkage'])}</p>")
    facts = "".join(f"<li>{e(str(x))}</li>" for x in s.get("static_facts", []))
    out.append(f"<h3>C. Static Facts</h3><ol>{facts}</ol>")
    if s.get("map"):
        img = draw_map(s["map"])
        if img:
            out.append(f"<h3>D. Map</h3><img src='data:image/png;base64,{img}'>")
    t = s.get("table")
    if t and t.get("rows"):
        head = "".join(f"<th>{e(str(c))}</th>" for c in t["columns"])
        body = "".join("<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in r) + "</tr>" for r in t["rows"])
        out.append(f"<h3>E. Data Table: {e(t.get('title', ''))}</h3><table><tr>{head}</tr>{body}</table>")
    out.append(f"<h3>F. Fun Fact</h3><div class='fun'>{e(s['fun_fact'])}</div></div>")
    return "".join(out)


def send_telegram(path):
    tok, chat = os.getenv("TG_TOKEN"), os.getenv("TG_CHAT_ID")
    if not (tok and chat):
        print("Telegram secrets missing, skipping send"); return
    with open(path, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendDocument",
                          data={"chat_id": chat, "caption": f"Current Affairs - {DATE_STR}"},
                          files={"document": f}, timeout=120)
    print("Telegram:", r.status_code)


def main():
    picks = select(collect())
    stories = []
    for it in picks:
        s = build_story(it)
        if s and s.get("headline"):
            stories.append(s)
        time.sleep(8)  # stay under free-tier per-minute limits
    body = "".join(story_html(i + 1, s) for i, s in enumerate(stories))
    page = f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body><h1>{DATE_STR} - Current Affairs</h1><p style='text-align:center'>UP TET / Super TET</p>{body}</body></html>"
    HTML(string=page).write_pdf(OUT)
    print("Created", OUT)
    send_telegram(OUT)


if __name__ == "__main__":
    main()
