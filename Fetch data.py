"""Downloads free Natural Earth map data into ./data (public domain). Skips files already present."""
import io, os, urllib.request, zipfile

BASE = "https://naciscdn.org/naturalearth"
FILES = [
    "110m/cultural/ne_110m_admin_0_countries.zip",
    "50m/physical/ne_50m_rivers_lake_centerlines.zip",
    "50m/physical/ne_50m_lakes.zip",
    "50m/physical/ne_50m_geography_regions_polys.zip",
]
os.makedirs("data", exist_ok=True)
for f in FILES:
    shp = os.path.basename(f).replace(".zip", ".shp")
    if os.path.exists(os.path.join("data", shp)):
        continue
    try:
        with urllib.request.urlopen(f"{BASE}/{f}", timeout=120) as r:
            zipfile.ZipFile(io.BytesIO(r.read())).extractall("data")
        print("downloaded", f)
    except Exception as ex:
        print("FAILED", f, ex, "- download it manually from naturalearthdata.com into the data folder")
