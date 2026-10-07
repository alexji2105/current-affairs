"""Map drawing: physical/political India (full boundary incl. Kashmir, from DataMeet) and world maps (Natural Earth).
All geopandas imports are lazy so the PDF still builds if map data is missing."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SEA, LAND, HILITE = "#dff0fb", "#f6f1e3", "#f4a261"
REGION_COLORS = {"Range/mtn": "#b08968", "Plateau": "#d9c08a", "Plain": "#c7e0b0", "Desert": "#f2e2a8"}
NAME_COLS = ["ST_NM", "STATE", "State", "NAME_1", "st_nm", "NAME", "name"]


def _gpd():
    import geopandas as gpd
    return gpd


def _find(*names):
    for n in names:
        p = os.path.join(DATA, n)
        if os.path.exists(p):
            return p
    return None


def _india_states():
    p = _find("india_states.geojson", "india_states.shp", "india_states.json")
    if not p:
        raise FileNotFoundError("data/india_states.geojson missing (see README step 2)")
    g = _gpd().read_file(p).to_crs(4326)
    return g


def _ne(name):
    p = _find(name)
    if not p:
        return None
    return _gpd().read_file(p).to_crs(4326)


def _name_col(gdf):
    for c in NAME_COLS:
        if c in gdf.columns:
            return c
    return None


def _norm(s):
    return str(s).lower().replace("&", "and").replace("-", " ").strip()


def _points(ax, spec):
    for p in spec.get("points", []) or []:
        try:
            x, y = float(p["lon"]), float(p["lat"])
        except Exception:
            continue
        ax.scatter([x], [y], s=28, c="#d62828", edgecolor="white", zorder=10)
        ax.annotate(p.get("name", ""), (x, y), xytext=(4, 4), textcoords="offset points",
                    fontsize=7, color="#7a0c0c", zorder=11, weight="bold")


def _physical_layers(ax, clip_geom, label=True):
    rivers = _ne("ne_50m_rivers_lake_centerlines.shp")
    lakes = _ne("ne_50m_lakes.shp")
    regions = _ne("ne_50m_geography_regions_polys.shp")
    gpd = _gpd()
    if regions is not None and "featurecla" in regions.columns:
        r = gpd.clip(regions, clip_geom)
        for cls, col in REGION_COLORS.items():
            sub = r[r["featurecla"] == cls]
            if len(sub):
                sub.plot(ax=ax, color=col, alpha=0.75, edgecolor="none", zorder=2)
                if label:
                    for _, row in sub.iterrows():
                        c = row.geometry.representative_point()
                        ax.text(c.x, c.y, str(row.get("name", "")), fontsize=5.5, ha="center",
                                color="#5a4632", style="italic", zorder=6)
    if lakes is not None:
        gpd.clip(lakes, clip_geom).plot(ax=ax, color="#7fc4ec", zorder=3)
    if rivers is not None:
        rv = gpd.clip(rivers, clip_geom)
        rv.plot(ax=ax, color="#2a7fc1", linewidth=0.9, zorder=4)
        if label and "name" in rv.columns:
            done = set()
            for _, row in rv.iterrows():
                nm = row.get("name")
                if nm and nm not in done and row.geometry is not None and not row.geometry.is_empty:
                    done.add(nm)
                    c = row.geometry.interpolate(0.5, normalized=True) if row.geometry.geom_type == "LineString" else row.geometry.representative_point()
                    ax.text(c.x, c.y, nm, fontsize=5, color="#0b4f8a", zorder=7)


def _india(spec, out, physical):
    st = _india_states()
    col = _name_col(st)
    hl = {_norm(x) for x in spec.get("highlight_states", []) or []}
    union = st.geometry.union_all() if hasattr(st.geometry, "union_all") else st.geometry.unary_union
    fig, ax = plt.subplots(figsize=(6.4, 6.9), dpi=200)
    fig.patch.set_facecolor("white")
    ax.set_facecolor(SEA)
    if physical:
        st.plot(ax=ax, color=LAND, edgecolor="none", zorder=1)
        _physical_layers(ax, union.buffer(0.2))
        st.boundary.plot(ax=ax, color="#8a8a8a", linewidth=0.3, zorder=5)
    else:
        st.plot(ax=ax, color="#f1f5fb", edgecolor="#6b7c99", linewidth=0.5, zorder=1)
    if hl and col:
        mask = st[col].map(_norm).isin(hl)
        st[mask].plot(ax=ax, color=HILITE, edgecolor="#b5651d", linewidth=0.8, alpha=0.9, zorder=3 if not physical else 5)
    gpd = _gpd()
    gpd.GeoSeries([union], crs=4326).boundary.plot(ax=ax, color="black", linewidth=1.3, zorder=8)
    if not physical and col:
        for _, row in st.iterrows():
            c = row.geometry.representative_point()
            ax.text(c.x, c.y, str(row[col]), fontsize=4.5, ha="center", color="#33415c", zorder=6)
    _points(ax, spec)
    minx, miny, maxx, maxy = st.total_bounds
    ax.set_xlim(minx - 1, maxx + 1)
    ax.set_ylim(miny - 1, maxy + 1)
    ax.set_aspect("equal")
    ax.set_axis_off()
    fig.savefig(out, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def _world(spec, out, physical):
    ctry = _ne("ne_110m_admin_0_countries.shp")
    if ctry is None:
        raise FileNotFoundError("Natural Earth countries file missing (run fetch_data.py)")
    gpd = _gpd()
    hl = {_norm(x) for x in spec.get("highlight_countries", []) or []}
    cols = [c for c in ("NAME", "ADMIN", "NAME_LONG") if c in ctry.columns]
    mask = ctry[cols[0]].map(_norm).isin(hl) if cols else None
    if cols and hl:
        for c in cols[1:]:
            mask = mask | ctry[c].map(_norm).isin(hl)
    fig, ax = plt.subplots(figsize=(9, 4.9), dpi=200)
    ax.set_facecolor(SEA)
    ctry.plot(ax=ax, color=LAND if physical else "#eef2f9", edgecolor="#8a8a8a", linewidth=0.3, zorder=1)
    if physical:
        from shapely.geometry import box
        _physical_layers(ax, box(-180, -90, 180, 90), label=False)
    if mask is not None and mask.any():
        ctry[mask].plot(ax=ax, color=HILITE, edgecolor="#b5651d", linewidth=0.7, zorder=5)
    try:   # draw India as per Indian official map (Kashmir included)
        st = _india_states()
        india = st.dissolve()
        india.plot(ax=ax, color=HILITE if "india" in hl else (LAND if physical else "#eef2f9"),
                   edgecolor="black", linewidth=0.8, zorder=6)
    except Exception as ex:
        print(f"[india overlay skipped] {ex}")
    _points(ax, spec)
    if mask is not None and mask.any():
        minx, miny, maxx, maxy = ctry[mask].total_bounds
        pad_x, pad_y = max((maxx - minx) * 0.6, 12), max((maxy - miny) * 0.6, 8)
        ax.set_xlim(max(minx - pad_x, -180), min(maxx + pad_x, 180))
        ax.set_ylim(max(miny - pad_y, -90), min(maxy + pad_y, 90))
    else:
        ax.set_xlim(-180, 180)
        ax.set_ylim(-60, 85)
    ax.set_aspect("equal")
    ax.set_axis_off()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def draw_map(spec, out_path):
    t = (spec or {}).get("type", "none")
    if t == "none":
        return None
    if t.startswith("india"):
        return _india(spec, out_path, physical=t.endswith("physical"))
    if t.startswith("world"):
        return _world(spec, out_path, physical=t.endswith("physical"))
    return None
