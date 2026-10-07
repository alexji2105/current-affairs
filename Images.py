"""Auto-fetch a diagram/map from Wikimedia Commons (free, no API key, openly licensed).
Google image search is NOT used: its Custom Search API is closed to new users (shuts 1 Jan 2027)
and scraping Google Images breaks its terms."""
import json, os, re, urllib.parse, urllib.request

API = "https://commons.wikimedia.org/w/api.php"
UA = "UPTETCurrentAffairsBot/1.0 (personal study notes project)"   # Wikimedia asks for a descriptive User-Agent
OK_MIME = ("image/png", "image/jpeg", "image/svg+xml")


def _get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
    return body if binary else json.loads(body.decode("utf-8"))


def search_commons(query, width=1000):
    params = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": "6",
              "gsrsearch": query, "gsrlimit": "8", "prop": "imageinfo",
              "iiprop": "url|mime|size|extmetadata", "iiurlwidth": str(width)}
    data = _get(API + "?" + urllib.parse.urlencode(params))
    pages = sorted((data.get("query", {}).get("pages", {})).values(), key=lambda p: p.get("index", 99))
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        if ii.get("mime") not in OK_MIME or ii.get("width", 0) < 400:
            continue
        meta = ii.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()[:60]
        return {"url": ii.get("thumburl") or ii["url"], "license": lic, "artist": artist,
                "page": ii.get("descriptionurl", "")}
    return None


def fetch_image(query, out_stem):
    """Returns (file_path, credit_text) or None."""
    if not query or not query.strip():
        return None
    hit = search_commons(query)
    if not hit:
        return None
    ext = os.path.splitext(urllib.parse.urlparse(hit["url"]).path)[1].lower()
    ext = ext if ext in (".png", ".jpg", ".jpeg") else ".png"
    path = out_stem + ext
    with open(path, "wb") as f:
        f.write(_get(hit["url"], binary=True))
    credit = "Image: Wikimedia Commons"
    if hit["artist"]:
        credit += f", {hit['artist']}"
    if hit["license"]:
        credit += f" ({hit['license']})"
    return path, credit
