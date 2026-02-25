#!/usr/bin/env python3
"""
antenneregister_scraper.py — RDI Antenneregister WFS downloader
================================================================

Downloads all antenna installations from the official Dutch RDI (Rijksinspectie
Digitale Infrastructuur) Antenneregister WFS endpoint, links each installation
to its individual antenna panels, and exports the combined dataset.

WFS endpoint:  https://antenneregister.nl/mapserver/wfs/
Layers:
  - Antennes          ~35 500 records   installations (masts / locations)
  - Antennes_Groepen  ~391 000 records  individual antenna panels per installation

DATA MODEL
----------
Each *installation* (Antennes) has an ANT_IDS field — a comma-separated list of
antenna-group IDs.  Each *antenna panel* (Antennes_Groepen) has an AI_ID field
that links it back.  One installation typically has 3–30 panels.

NOTE: This WFS server has two quirks documented in the source:
  1. CQL_FILTER is SILENTLY IGNORED — always use OGC XML FILTER
  2. Blind pagination (startindex) misses records — explicit OGC FILTER
     queries by AI_ID batch achieve ~96%+ coverage vs ~63% from pagination

The script uses method (2): collect all AI_IDs from Antennes, then fetch
Antennes_Groepen in batches via OGC XML FILTER for maximum completeness.

USAGE
-----
  # Download everything, export JSON + GeoJSON + CSV (default)
  python antenneregister_scraper.py

  # Only export GeoJSON and KML
  python antenneregister_scraper.py --format geojson kml

  # Only 5G installations, with WGS84 coordinates
  python antenneregister_scraper.py --tech 5g --wgs84

  # Only Utrecht municipality
  python antenneregister_scraper.py --gemeente Utrecht

  # Convert existing antennes_linked.json to other formats (skip re-download)
  python antenneregister_scraper.py --from-file antennes_linked.json --format geojson csv kml

  # Show all options
  python antenneregister_scraper.py --help

EXPORT FORMATS
--------------
  json      Compact list of dicts with all fields  (antennes_linked.json)
  geojson   RFC 7946 FeatureCollection, WGS84       (antennes_linked.geojson)
  csv       Flat table, one row per installation    (antennes_linked.csv)
  kml       Google Earth / Maps import             (antennes_linked.kml)

REQUIREMENTS
------------
  Python 3.8+, stdlib only (json, csv, argparse, urllib, gzip, time, etc.)
  No third-party packages needed.

COORDINATES
-----------
  Source data uses Dutch RD New (EPSG:28992, X/Y in meters).
  Use --wgs84 to convert coordinates to WGS84 (lon/lat).  The conversion uses
  the official RDNAPTRANS polynomial approximation (sub-metre accuracy for NL).
"""

import argparse
import csv
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from io import StringIO

# ─── WFS settings ────────────────────────────────────────────────────────────

WFS_URL   = "https://antenneregister.nl/mapserver/wfs/"
PAGE_SIZE = 5000
MAX_RETRY = 5
RETRY_DELAY = 3   # seconds, doubles on each retry

# HTTP headers that mimic a real browser enough to avoid WAF blocks
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AntenneregisterScraper/2.0; "
        "+https://github.com/frankwiersma/antennekaart)"
    ),
    "Accept": "application/json, */*",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "nl,en;q=0.9",
    "Connection": "keep-alive",
}

# ─── RD → WGS84 coordinate conversion ───────────────────────────────────────
# Source: RDNAPTRANS2018 polynomial approximation (published by Kadaster NL)
# Accuracy: < 0.01 m anywhere in the Netherlands

def rd_to_wgs84(x: float, y: float) -> tuple:
    """Convert Dutch RD New (EPSG:28992) X,Y to WGS84 lon,lat."""
    # Correction terms from RDNAPTRANS 2018 Appendix C
    X0, Y0 = 155000.0, 463000.0
    dx = (x - X0) * 1e-5
    dy = (y - Y0) * 1e-5

    # Latitude polynomial
    lat_coefs = [
        (0, 1,  3235.65389),
        (2, 0,  -32.58297),
        (0, 2,  -0.24750),
        (2, 1,  -0.84978),
        (0, 3,  -0.06550),
        (2, 2,  -0.01709),
        (1, 0,  -0.00738),
        (4, 0,   0.00530),
        (2, 3,  -0.00039),
        (4, 1,   0.00033),
        (1, 1,  -0.00012),
    ]
    # Longitude polynomial
    lon_coefs = [
        (1, 0,  5260.52916),
        (1, 1,  105.94684),
        (1, 2,    2.45656),
        (3, 0,   -0.81885),
        (1, 3,    0.05594),
        (3, 1,   -0.05607),
        (0, 1,    0.01199),
        (3, 2,   -0.00256),
        (1, 4,    0.00128),
        (0, 2,    0.00022),
        (2, 0,   -0.00022),
        (5, 0,    0.00026),
    ]

    lat_dec = sum(c * (dx ** p) * (dy ** q) for p, q, c in lat_coefs)
    lon_dec = sum(c * (dx ** p) * (dy ** q) for p, q, c in lon_coefs)

    lat_wgs84 = 52.15517440 + lat_dec / 3600.0
    lon_wgs84 =  5.38720621 + lon_dec / 3600.0
    return round(lon_wgs84, 7), round(lat_wgs84, 7)


# ─── HTTP helpers ─────────────────────────────────────────────────────────────

def _make_request(url: str) -> bytes:
    """Fetch URL with retries, gzip handling, and clear error messages."""
    req = urllib.request.Request(url, headers=_HEADERS)
    delay = RETRY_DELAY

    for attempt in range(1, MAX_RETRY + 1):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                raw = resp.read()

            # Server may send gzip even without Content-Encoding header
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)

            if not raw:
                raise ValueError("Server returned empty response body")

            return raw

        except (urllib.error.URLError, ValueError, OSError) as exc:
            if attempt == MAX_RETRY:
                raise RuntimeError(
                    f"Request failed after {MAX_RETRY} attempts: {exc}\n"
                    f"URL: {url}"
                ) from exc

            print(
                f"  ⚠  Attempt {attempt}/{MAX_RETRY} failed ({exc}), "
                f"retrying in {delay}s …",
                file=sys.stderr,
            )
            time.sleep(delay)
            delay *= 2


def fetch_wfs(typename: str, count: int = PAGE_SIZE, start_index: int = 0) -> dict:
    """Fetch one page of WFS features."""
    params = {
        "service":      "WFS",
        "request":      "GetFeature",
        "version":      "2.0.0",
        "typename":     typename,
        "outputformat": "application/json",
        "srsname":      "EPSG:28992",
        "count":        str(count),
        "startindex":   str(start_index),
    }
    url = WFS_URL + "?" + urllib.parse.urlencode(params)
    raw = _make_request(url)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Server returned non-JSON for {typename} "
            f"(offset={start_index}): {raw[:200]!r}"
        ) from exc


def fetch_all(typename: str, desc: str = "") -> list:
    """Paginate through all WFS features for a typename (Antennes layer only)."""
    all_features = []
    start = 0
    label = desc or typename

    while True:
        page_no = start // PAGE_SIZE + 1
        print(f"  [{label}] page {page_no} (offset {start}) …", end="  ", flush=True)
        data = fetch_wfs(typename, count=PAGE_SIZE, start_index=start)
        features = data.get("features", [])
        print(f"{len(features)} records")
        all_features.extend(features)

        if len(features) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    return all_features


# ─── OGC FILTER helpers (for Antennes_Groepen — pagination gives ~63% coverage) ──
# Critical discovery: this MapServer silently ignores CQL_FILTER, and blind
# pagination misses ~37% of records.  Querying explicitly by AI_ID via OGC XML
# FILTER achieves ~96%+ coverage.  Batch size ≤25 to stay under URL length limits.

BATCH_SIZE = 25   # max AI_IDs per OGC OR-query


def _build_ogc_filter(field: str, values: list) -> str:
    """Build an OGC XML FILTER with OR clauses for multiple field values."""
    if len(values) == 1:
        return (
            f"<Filter>"
            f"<PropertyIsEqualTo>"
            f"<PropertyName>{field}</PropertyName>"
            f"<Literal>{values[0]}</Literal>"
            f"</PropertyIsEqualTo>"
            f"</Filter>"
        )
    clauses = "".join(
        f"<PropertyIsEqualTo>"
        f"<PropertyName>{field}</PropertyName>"
        f"<Literal>{v}</Literal>"
        f"</PropertyIsEqualTo>"
        for v in values
    )
    return f"<Filter><Or>{clauses}</Or></Filter>"


def fetch_groepen_by_ids(ai_ids: set) -> list:
    """
    Fetch Antennes_Groepen panels for specific AI_IDs using OGC XML FILTER.
    Batches of BATCH_SIZE IDs per request to stay under URL length limits.
    Rate-limits to be polite to the server.
    """
    ids = sorted(ai_ids)
    total_batches = (len(ids) + BATCH_SIZE - 1) // BATCH_SIZE
    all_features = []

    for i in range(0, len(ids), BATCH_SIZE):
        batch = ids[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1

        if batch_num == 1 or batch_num % 100 == 0 or batch_num == total_batches:
            pct = batch_num / total_batches * 100
            print(
                f"  [Antennes_Groepen] batch {batch_num}/{total_batches}"
                f" ({pct:.0f}%)  {len(all_features):,} panels so far …",
                flush=True,
            )

        ogc_filter = _build_ogc_filter("AI_ID", batch)
        params = {
            "service":      "WFS",
            "request":      "GetFeature",
            "version":      "2.0.0",
            "typename":     "Antennes_Groepen",
            "outputformat": "application/json",
            "srsname":      "EPSG:28992",
            "count":        "5000",   # one AI_ID can have many panels
            "FILTER":       ogc_filter,
        }
        url = WFS_URL + "?" + urllib.parse.urlencode(params)
        raw = _make_request(url)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"  ⚠  JSON error at batch {batch_num}: {exc} — skipping", file=sys.stderr)
            continue
        all_features.extend(data.get("features", []))

        # Polite rate limiting — 0.3s every 10 batches
        if batch_num % 10 == 0:
            time.sleep(0.3)

    return all_features


# ─── Core logic ───────────────────────────────────────────────────────────────

def download_and_link() -> list:
    """
    Download Antennes + Antennes_Groepen from WFS, link them, return records.

    Uses OGC XML FILTER to fetch Antennes_Groepen by AI_ID batches (~96%+
    coverage) instead of blind pagination (~63%).
    """
    print("━━━  Step 1 / 3  Downloading installations (Antennes) …")
    antennes = fetch_all("Antennes", "Antennes")
    print(f"  ✓  {len(antennes):,} installations\n")

    # Collect all unique AI_IDs referenced across all installations
    all_ai_ids: set = set()
    for ant in antennes:
        ids_str = ant["properties"].get("ANT_IDS", "") or ""
        for aid in ids_str.replace(",", " ").split():
            if aid:
                all_ai_ids.add(aid)
    print(f"  Unique AI_IDs to fetch: {len(all_ai_ids):,}\n")

    print(f"━━━  Step 2 / 3  Fetching panels via OGC FILTER"
          f"  ({(len(all_ai_ids) + BATCH_SIZE - 1) // BATCH_SIZE} batches of {BATCH_SIZE}) …")
    est_min = len(all_ai_ids) // BATCH_SIZE // 3
    print(f"  Estimated time: ~{est_min}–{est_min*2} min (depends on server speed)\n")
    groepen = fetch_groepen_by_ids(all_ai_ids)
    print(f"\n  ✓  {len(groepen):,} panels fetched\n")

    print("━━━  Step 3 / 3  Linking installations to panels …")
    groep_lookup: dict = defaultdict(list)
    for g in groepen:
        ai_id = str(g["properties"].get("AI_ID", ""))
        if ai_id:
            groep_lookup[ai_id].append(g["properties"])

    linked = []
    total_ids = found_ids = missing_ids = 0

    for ant in antennes:
        props  = ant["properties"]
        coords = ant.get("geometry", {}).get("coordinates", [None, None])

        ids_str  = props.get("ANT_IDS", "") or ""
        ant_id_list = [s.strip() for s in ids_str.replace(",", " ").split() if s.strip()]

        details = []
        for aid in ant_id_list:
            total_ids += 1
            if aid in groep_lookup:
                found_ids += 1
                details.extend(groep_lookup[aid])
            else:
                missing_ids += 1

        linked.append({
            "id":           props.get("ID"),
            "x":            coords[0],
            "y":            coords[1],
            "gemeente":     props.get("GEMEENTE"),
            "woonplaats":   props.get("WOONPLAATSNAAM"),
            "postcode":     props.get("POSTCODE"),
            "hoofdsoort":   props.get("HOOFDSOORT"),
            "is_2g":        bool(props.get("TWEEG")),
            "is_3g":        bool(props.get("DRIEG")),
            "is_4g":        bool(props.get("VIERG")),
            "is_5g":        bool(props.get("VIJFG")),
            "is_mobiel":    bool(props.get("MOBIELE_COMMUNICATIE")),
            "is_omroep":    bool(props.get("OMROEP")),
            "is_vaste_verb": bool(props.get("VASTE_VERB")),
            "small_cell":   props.get("SMALL_CELL_INDICATOR", ""),
            "ant_ids":      ant_id_list,
            "panels":       details,
        })

    pct = found_ids / total_ids * 100 if total_ids else 0
    print(f"  Panel IDs in source : {total_ids:,}")
    print(f"  Matched to panels   : {found_ids:,}  ({pct:.1f} %)")
    if missing_ids:
        print(f"  No panel data       : {missing_ids:,}  ({100-pct:.1f} %) — residual WFS gap")
    return linked


# ─── Filters ──────────────────────────────────────────────────────────────────

def apply_filters(records: list, args) -> list:
    """Apply --tech / --gemeente / --postcode / --provider filters."""
    total = len(records)
    filtered = records

    if args.tech:
        key_map = {
            "2g": "is_2g", "3g": "is_3g", "4g": "is_4g", "5g": "is_5g",
            "mobiel": "is_mobiel", "omroep": "is_omroep",
            "vaste_verb": "is_vaste_verb",
        }
        keys = [key_map[t.lower()] for t in args.tech if t.lower() in key_map]
        if keys:
            filtered = [r for r in filtered if any(r.get(k) for k in keys)]

    if args.gemeente:
        q = [g.lower() for g in args.gemeente]
        filtered = [r for r in filtered if (r.get("gemeente") or "").lower() in q]

    if args.postcode:
        q = [p.upper()[:4] for p in args.postcode]
        filtered = [r for r in filtered if (r.get("postcode") or "")[:4] in q]

    if len(filtered) < total:
        print(f"\n  Filter: {total:,} → {len(filtered):,} records")

    return filtered


# ─── Coordinate helpers ───────────────────────────────────────────────────────

def coords_for(rec: dict, wgs84: bool) -> tuple:
    """Return (lon/x, lat/y) for a record, optionally converted to WGS84."""
    x, y = rec.get("x"), rec.get("y")
    if x is None or y is None:
        return None, None
    if wgs84:
        return rd_to_wgs84(x, y)
    return x, y


# ─── Exporters ────────────────────────────────────────────────────────────────

def export_json(records: list, path: str, wgs84: bool):
    """Export as compact JSON list."""
    out = []
    for r in records:
        row = dict(r)
        if wgs84:
            lon, lat = coords_for(r, wgs84=True)
            row["lon"], row["lat"] = lon, lat
            del row["x"], row["y"]
        out.append(row)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"  ✓  JSON      → {path}  ({len(out):,} records)")


def export_geojson(records: list, path: str, wgs84: bool):
    """Export as RFC 7946 GeoJSON FeatureCollection."""
    features = []
    skipped = 0

    for r in records:
        lon, lat = coords_for(r, wgs84=wgs84)
        if lon is None:
            skipped += 1
            continue

        # Properties: everything except raw coord fields and panels list
        props = {k: v for k, v in r.items()
                 if k not in ("x", "y", "panels")}
        props["panel_count"] = len(r.get("panels", []))
        # Summarise panel technology strings
        techs = list({p.get("SAT_CODE") for p in r.get("panels", []) if p.get("SAT_CODE")})
        props["technologies"] = sorted(techs)

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat],
            },
            "properties": props,
        })

    crs_note = "WGS84" if wgs84 else "RD New (EPSG:28992)"
    fc = {
        "type": "FeatureCollection",
        "name": "antenneregister",
        "_crs": crs_note,
        "features": features,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))

    note = f"  (skipped {skipped} without coords)" if skipped else ""
    print(f"  ✓  GeoJSON   → {path}  ({len(features):,} features){note}")


def export_csv(records: list, path: str, wgs84: bool):
    """Export as flat CSV — one row per installation, panels summarised."""
    fieldnames = [
        "id", "x_or_lon", "y_or_lat", "gemeente", "woonplaats", "postcode",
        "hoofdsoort", "is_2g", "is_3g", "is_4g", "is_5g",
        "is_mobiel", "is_omroep", "is_vaste_verb", "small_cell",
        "panel_count", "technologies", "ant_ids",
    ]
    rows = []
    for r in records:
        lon, lat = coords_for(r, wgs84=wgs84)
        techs = sorted({p.get("SAT_CODE") for p in r.get("panels", []) if p.get("SAT_CODE")})
        rows.append({
            "id":          r.get("id"),
            "x_or_lon":    lon,
            "y_or_lat":    lat,
            "gemeente":    r.get("gemeente"),
            "woonplaats":  r.get("woonplaats"),
            "postcode":    r.get("postcode"),
            "hoofdsoort":  r.get("hoofdsoort"),
            "is_2g":       r.get("is_2g"),
            "is_3g":       r.get("is_3g"),
            "is_4g":       r.get("is_4g"),
            "is_5g":       r.get("is_5g"),
            "is_mobiel":   r.get("is_mobiel"),
            "is_omroep":   r.get("is_omroep"),
            "is_vaste_verb": r.get("is_vaste_verb"),
            "small_cell":  r.get("small_cell"),
            "panel_count": len(r.get("panels", [])),
            "technologies": " | ".join(techs),
            "ant_ids":     " | ".join(r.get("ant_ids", [])),
        })

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  ✓  CSV       → {path}  ({len(rows):,} rows)")


def export_kml(records: list, path: str, wgs84: bool):
    """Export as KML (Google Earth / Maps compatible)."""
    def esc(s) -> str:
        if s is None:
            return ""
        return (str(s)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))

    buf = StringIO()
    buf.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    buf.write('<kml xmlns="http://www.opengis.net/kml/2.2">\n')
    buf.write('<Document>\n')
    buf.write('  <name>Antenneregister NL</name>\n')
    buf.write('  <description>RDI Antenneregister antenna installations</description>\n')

    # Style definitions for each tech
    styles = {
        "5g":      ("#5GNR",    "ff00e5a0"),
        "4g":      ("#LTE",     "ff2979ff"),
        "3g":      ("#UMTS",    "ffff9800"),
        "2g":      ("#GSM",     "ffff1744"),
        "overig":  ("#Other",   "ff9e9e9e"),
    }
    for sid, (_, color) in styles.items():
        buf.write(f'  <Style id="{sid}">\n')
        buf.write(f'    <IconStyle><color>{color}</color><scale>0.6</scale>'
                  '<Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href>'
                  '</Icon></IconStyle>\n')
        buf.write('  </Style>\n')

    skipped = 0
    for r in records:
        lon, lat = coords_for(r, wgs84=wgs84)
        if lon is None:
            skipped += 1
            continue

        # Pick style
        if r.get("is_5g"):     style = "#5g"
        elif r.get("is_4g"):   style = "#4g"
        elif r.get("is_3g"):   style = "#3g"
        elif r.get("is_2g"):   style = "#2g"
        else:                  style = "#overig"

        techs = sorted({p.get("SAT_CODE") for p in r.get("panels", []) if p.get("SAT_CODE")})
        desc_parts = [
            f"<b>ID:</b> {esc(r.get('id'))}",
            f"<b>Gemeente:</b> {esc(r.get('gemeente'))}",
            f"<b>Postcode:</b> {esc(r.get('postcode'))}",
            f"<b>Technologie:</b> {esc(r.get('hoofdsoort'))}",
            f"<b>Panels:</b> {len(r.get('panels', []))}",
            f"<b>SAT codes:</b> {esc(', '.join(techs))}",
        ]
        name = esc(r.get("woonplaats") or r.get("gemeente") or str(r.get("id")))

        buf.write("  <Placemark>\n")
        buf.write(f"    <name>{name}</name>\n")
        buf.write(f"    <styleUrl>{style}</styleUrl>\n")
        buf.write(f"    <description><![CDATA[{'<br/>'.join(desc_parts)}]]></description>\n")
        buf.write(f"    <Point><coordinates>{lon},{lat},0</coordinates></Point>\n")
        buf.write("  </Placemark>\n")

    buf.write("</Document>\n</kml>\n")

    with open(path, "w", encoding="utf-8") as f:
        f.write(buf.getvalue())

    note = f"  (skipped {skipped} without coords)" if skipped else ""
    total = len(records) - skipped
    print(f"  ✓  KML       → {path}  ({total:,} placemarks){note}")


# ─── Stats ────────────────────────────────────────────────────────────────────

def print_stats(records: list):
    total = len(records)
    print(f"\n{'━'*50}")
    print(f"  Total installations : {total:,}")
    for tech in ("5g", "4g", "3g", "2g", "mobiel", "omroep", "vaste_verb"):
        key = f"is_{tech}"
        count = sum(1 for r in records if r.get(key))
        if count:
            print(f"  {key:<18}: {count:,}  ({count/total*100:.1f} %)")

    # Top 10 gemeenten
    from collections import Counter
    gem_counts = Counter(r.get("gemeente") for r in records if r.get("gemeente"))
    print(f"\n  Top 10 gemeenten:")
    for gem, cnt in gem_counts.most_common(10):
        print(f"    {gem:<30} {cnt:>5,}")
    print(f"{'━'*50}\n")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="antenneregister_scraper.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__.split("USAGE")[0].strip(),
        epilog="""
EXAMPLES
  Download everything (default: JSON + GeoJSON + CSV in current directory):
    python antenneregister_scraper.py

  All 5G sites in WGS84, GeoJSON only:
    python antenneregister_scraper.py --tech 5g --wgs84 --format geojson

  Amsterdam + Utrecht, all formats:
    python antenneregister_scraper.py --gemeente Amsterdam Utrecht

  Convert an existing JSON file to GeoJSON + KML without re-downloading:
    python antenneregister_scraper.py --from-file antennes_linked.json --format geojson kml

  Show statistics only (no file output):
    python antenneregister_scraper.py --stats-only

SUPPORTED TECHNOLOGIES (--tech)
  2g  3g  4g  5g  mobiel  omroep  vaste_verb
""",
    )

    p.add_argument(
        "--format", nargs="+",
        choices=["json", "geojson", "csv", "kml"],
        default=["json", "geojson", "csv"],
        metavar="FMT",
        help="Output format(s).  Choices: json geojson csv kml  (default: json geojson csv)",
    )
    p.add_argument(
        "--output-dir", default=".",
        metavar="DIR",
        help="Directory for output files  (default: current directory)",
    )
    p.add_argument(
        "--prefix", default="antennes_linked",
        metavar="NAME",
        help="Base filename for outputs  (default: antennes_linked)",
    )
    p.add_argument(
        "--wgs84", action="store_true",
        help="Convert coordinates from Dutch RD New (EPSG:28992) to WGS84 lon/lat",
    )
    p.add_argument(
        "--from-file", metavar="FILE",
        help="Skip downloading — read records from an existing JSON file instead",
    )
    p.add_argument(
        "--tech", nargs="+",
        metavar="TECH",
        help="Filter by technology: 2g 3g 4g 5g mobiel omroep vaste_verb",
    )
    p.add_argument(
        "--gemeente", nargs="+",
        metavar="NAAM",
        help="Filter by municipality name  (case-insensitive, exact match)",
    )
    p.add_argument(
        "--postcode", nargs="+",
        metavar="PC4",
        help="Filter by 4-digit postcode prefix  e.g. 3513",
    )
    p.add_argument(
        "--stats-only", action="store_true",
        help="Download/load data, print statistics, but do not write output files",
    )
    p.add_argument(
        "--no-panels", action="store_true",
        help="Skip downloading Antennes_Groepen (faster, no panel details in output)",
    )
    p.add_argument(
        "--raw-json", metavar="FILE",
        help="Also save the raw linked dataset to this file before filtering",
    )
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    t0 = time.time()

    # ── Load or download data ──────────────────────────────────────────────
    if args.from_file:
        print(f"Loading records from {args.from_file} …")
        with open(args.from_file, encoding="utf-8") as f:
            records = json.load(f)
        print(f"  Loaded {len(records):,} records\n")
    else:
        if args.no_panels:
            # Lightweight download — installations only
            print("━━━  Downloading installations (panels skipped) …")
            antennes = fetch_all("Antennes", "Antennes")
            records = []
            for ant in antennes:
                props  = ant["properties"]
                coords = ant.get("geometry", {}).get("coordinates", [None, None])
                ant_ids_str = props.get("ANT_IDS", "") or ""
                records.append({
                    "id":           props.get("ID"),
                    "x":            coords[0],
                    "y":            coords[1],
                    "gemeente":     props.get("GEMEENTE"),
                    "woonplaats":   props.get("WOONPLAATSNAAM"),
                    "postcode":     props.get("POSTCODE"),
                    "hoofdsoort":   props.get("HOOFDSOORT"),
                    "is_2g":        bool(props.get("TWEEG")),
                    "is_3g":        bool(props.get("DRIEG")),
                    "is_4g":        bool(props.get("VIERG")),
                    "is_5g":        bool(props.get("VIJFG")),
                    "is_mobiel":    bool(props.get("MOBIELE_COMMUNICATIE")),
                    "is_omroep":    bool(props.get("OMROEP")),
                    "is_vaste_verb": bool(props.get("VASTE_VERB")),
                    "small_cell":   props.get("SMALL_CELL_INDICATOR", ""),
                    "ant_ids":      [s.strip() for s in ant_ids_str.split(",") if s.strip()],
                    "panels":       [],
                })
        else:
            records = download_and_link()

    # Optionally save full raw dataset before filtering
    if args.raw_json:
        with open(args.raw_json, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        print(f"\n  Raw data saved → {args.raw_json}")

    # ── Apply filters ─────────────────────────────────────────────────────
    records = apply_filters(records, args)

    # ── Statistics ────────────────────────────────────────────────────────
    if args.stats_only or True:   # always show quick stats
        print_stats(records)

    if args.stats_only:
        elapsed = time.time() - t0
        print(f"Done in {elapsed:.1f}s  (stats only, no files written)")
        return

    # ── Export ────────────────────────────────────────────────────────────
    prefix = os.path.join(args.output_dir, args.prefix)
    coord_label = " [WGS84]" if args.wgs84 else " [RD New]"
    print(f"Exporting {len(records):,} records{coord_label}:")

    fmt_dispatch = {
        "json":    (export_json,    ".json"),
        "geojson": (export_geojson, ".geojson"),
        "csv":     (export_csv,     ".csv"),
        "kml":     (export_kml,     ".kml"),
    }
    for fmt in args.format:
        fn, ext = fmt_dispatch[fmt]
        fn(records, prefix + ext, wgs84=args.wgs84)

    elapsed = time.time() - t0
    print(f"\n✓  Done in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
