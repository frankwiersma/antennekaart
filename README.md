# 📡 Antennekaart NL

Interactive map of all **35,519 antenna installations** and **391,453 antenna groups** in the Netherlands, powered by live data from the official [Antenneregister](https://antenneregister.nl).

**🔴 Live:** [antennekaart.co-evolve.nl](https://antennekaart.co-evolve.nl)

![Antennekaart Screenshot](https://img.shields.io/badge/antennas-35%2C519-22c55e?style=flat-square) ![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square) ![Deploy](https://img.shields.io/badge/deploy-Netlify-00c7b7?style=flat-square)

---

## Features

- 🗺️ **Dark interactive map** — real-time antenna loading via WFS as you pan/zoom
- 📡 **Color-coded by technology** — 5G (green) / 4G (blue) / 3G (orange) / 2G (red) / Microwave (purple)
- 🔍 **Search** — by postcode, city, or address (Nominatim geocoding)
- 📊 **Click for details** — frequency, power (dBW), height, beam direction, safety distance, commissioning date
- ⚡ **Filter chips** — toggle technologies on/off with live counts
- 🇳🇱 **Full Netherlands coverage** — all installations from the Rijksinspectie Digitale Infrastructuur (RDI)
- 📱 **Mobile-friendly** — responsive layout, full-width panel on small screens

## How It Works

The map loads antenna data **live** from the official WFS (Web Feature Service) endpoint at `antenneregister.nl`. No static dataset needed for the map itself — it queries the current viewport's bounding box on every pan/zoom.

```
Browser → Netlify proxy (/wfs/*) → antenneregister.nl/mapserver/wfs/
```

The Netlify proxy handles CORS. Coordinates are converted between RD New (EPSG:28992) and WGS84 client-side using the standard Dutch RD transformation.

## Tech Stack

| What | How |
|------|-----|
| Map | [Leaflet](https://leafletjs.com) + [CARTO](https://carto.com) dark tiles |
| Data | Live WFS queries to Antenneregister.nl |
| Search | [Nominatim](https://nominatim.org) geocoding (OpenStreetMap) |
| Coordinates | RD New ↔ WGS84 conversion (client-side) |
| Hosting | [Netlify](https://netlify.com) with WFS proxy |
| Build | None — single `index.html`, zero dependencies |

## Quick Start

```bash
# Clone
git clone https://github.com/frankwiersma/antennekaart.git
cd antennekaart

# Serve locally (any static server works)
npx serve .
# or
python3 -m http.server 8000
```

> **Note:** The WFS proxy only works on Netlify. For local dev, the map will still work because it falls back to direct WFS requests (which may fail due to CORS in some browsers). Use `netlify dev` for full local testing:
>
> ```bash
> npx netlify-cli dev
> ```

## Project Structure

```
antennekaart/
├── index.html          # The entire app (HTML + CSS + JS, ~330 lines)
├── netlify.toml        # Netlify config + WFS proxy redirect
├── _redirects          # Netlify redirect rules
├── data/               # Offline datasets (CSV, GeoJSON, community data)
│   ├── README.md       # Full schema documentation + API examples
│   ├── antennes.csv    # 35,519 antenna locations
│   ├── antennes_groepen.csv  # 391,453 antenna details
│   ├── *.json.gz       # Compressed GeoJSON versions
│   └── antennekaart.nl/     # Community/crowd-sourced data
│       ├── 5g.json     # 14,411 5G sites with provider info
│       ├── 4g.json     # 16,164 4G sites
│       ├── bts-all.json # 39,715 BTS records with eNB IDs
│       └── ...
└── scripts/
    └── antenneregister_scraper.py  # WFS data downloader
```

## Data

Two complementary datasets in [`data/`](data/):

### Official (Antenneregister.nl / RDI)

The authoritative source. Published by Rijksinspectie Digitale Infrastructuur as open data.

| File | Records | Description |
|------|---------|-------------|
| `antennes.csv` | 35,519 | All locations — postcode, gemeente, technology types, antenna IDs |
| `antennes_groepen.csv` | 391,453 | Per-antenna detail — frequency, power, height, direction, dates |

### Community (Antennekaart.nl)

Crowd-sourced enrichment with **provider identification** (KPN, Vodafone, Odido), BTS metadata, and field scan results.

| File | Records | Description |
|------|---------|-------------|
| `bts-all.json` | 39,715 | All BTS records with eNB IDs, TAC, provider, bands |
| `5g.json` .. `2g.json` | varies | Per-technology GeoJSON with provider + bands |

See [`data/README.md`](data/README.md) for full schema documentation, field descriptions, and API examples.

## WFS API

The Antenneregister exposes a standard OGC WFS endpoint (undocumented, reverse-engineered from the official viewer):

```bash
# Get all antennas in a bounding box (RD New coordinates)
curl "https://antenneregister.nl/mapserver/wfs/?service=WFS&version=2.0.0\
&request=GetFeature&typeName=ms:Antennes&outputFormat=application/json\
&bbox=136000,455000,138000,457000"

# Get antenna details by installation ID (⚠️ use OGC FILTER, not CQL_FILTER!)
curl "https://antenneregister.nl/mapserver/wfs/?service=WFS&version=2.0.0\
&request=GetFeature&typeName=ms:Antennes_Groepen&outputFormat=application/json\
&FILTER=<Filter><PropertyIsEqualTo><PropertyName>AI_ID</PropertyName>\
<Literal>8945423867</Literal></PropertyIsEqualTo></Filter>"
```

> ⚠️ **Critical: `CQL_FILTER` is silently ignored** by this MapServer instance. Always use OGC XML `FILTER` parameter instead. `CQL_FILTER=AI_ID=123` will return unfiltered results without any error.

### Available Layers

| Layer | Content | Records |
|-------|---------|---------|
| `ms:Antennes` | Antenna locations (masts/rooftops) | ~35,500 |
| `ms:Antennes_Groepen` | Individual antenna panels | ~391,500 |
| `ms:Meetgegevens_wfs` | EMV field strength measurements | varies |

### Data Linking

Each location has an `ANT_IDS` field containing comma-separated installation IDs. These link to `AI_ID` in the `Antennes_Groepen` layer:

```
Antennes.ANT_IDS = "8945423867, 8945423868, 8945423869"
                          ↓              ↓              ↓
Antennes_Groepen.AI_ID = 8945423867  8945423868  8945423869
```

> ⚠️ **Coverage note:** Blind pagination (`count` + `startindex`) only returns ~63% of `Antennes_Groepen` records. The remaining ~37% **do exist** but are only accessible via OGC FILTER queries by specific `AI_ID`. The included scraper handles this correctly.

### Pagination & Filtering Gotchas

The WFS server has two important quirks:

1. **`CQL_FILTER` is silently ignored.** The server accepts the parameter without error but returns unfiltered results. Always use OGC XML `FILTER` instead.

2. **Blind pagination misses data.** Paginating through `Antennes_Groepen` without filters (`count=5000&startindex=X`) returns ~391k records covering only ~45k unique `AI_ID`s. The full dataset contains ~72k+ unique IDs. To get complete data, query by specific `AI_ID` using OGC FILTER.

```bash
# ❌ WRONG — CQL_FILTER is silently ignored
curl "...&CQL_FILTER=AI_ID=123"  # Returns random unfiltered data!

# ✅ CORRECT — OGC XML FILTER
curl "...&FILTER=<Filter><PropertyIsEqualTo><PropertyName>AI_ID</PropertyName><Literal>123</Literal></PropertyIsEqualTo></Filter>"

# ✅ Multiple IDs with OR
curl "...&FILTER=<Filter><Or><PropertyIsEqualTo>...</PropertyIsEqualTo><PropertyIsEqualTo>...</PropertyIsEqualTo></Or></Filter>"
```

The included scraper script handles all of this automatically.

## Scripts

### `scripts/antenneregister_scraper.py`

Downloads the complete dataset from the WFS endpoint, links installations to antenna groups, and exports as JSON.

```bash
cd scripts
python3 antenneregister_scraper.py
```

**Output:**
- `antennes_linked.json` — all installations with linked antenna details
- `antennes_5g_linked.json` — 5G-only subset

No external dependencies — uses only Python stdlib (`urllib`, `json`).

## Updating the Data

To refresh the offline datasets in `data/`:

```bash
# 1. Download fresh data via WFS
python3 scripts/antenneregister_scraper.py

# 2. Convert to CSV (optional — use the GeoJSON directly)
# The scraper outputs JSON; for CSV, use ogr2ogr or a simple script

# 3. For community data, fetch from antennekaart.nl API:
curl "https://antennekaart.nl/api/v1/map/layer/5g/?bbox=3.3,50.7,7.3,53.6&zoom=7" > data/antennekaart.nl/5g.json
curl "https://antennekaart.nl/api/v1/map/layer/4g/?bbox=3.3,50.7,7.3,53.6&zoom=7" > data/antennekaart.nl/4g.json
# ... repeat for 3g, 2g, gsm-r, cdma, cgc, fixed-wireless
```

## Contributing

Contributions welcome! Some ideas:

- **Marker clustering** for zoomed-out views
- **Provider identification** in the detail panel (using community data)
- **Heatmap mode** for density visualization
- **URL hash** for shareable map positions (`#@52.09,5.12,15z`)
- **Statistics panel** with nationwide totals
- **Coverage analysis** tools

## License

Code: **MIT**. Data: [Antennebureau](https://antennebureau.nl) / RDI open data.
