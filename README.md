# 📡 Antennekaart NL

Interactive map of all **35,519 antenna installations** and **391,453 antenna groups** in the Netherlands.

**Live:** [antennekaart.co-evolve.nl](https://antennekaart.co-evolve.nl)

## Features

- 🗺️ Dark interactive map with real-time antenna loading
- 📡 Color-coded by technology: 5G / 4G / 3G / 2G / Microwave
- 🔍 Search by postcode, city, or address
- 📊 Click any antenna for detailed specs: frequency, power (dBW), height, beam direction, safety distance
- ⚡ Filter by technology type
- 📥 Full dataset available in `data/` directory (CSV + GeoJSON)

## Data

Two complementary datasets in `data/`:

**Official (Antenneregister.nl / RDI):**
- `antennes.csv` — 35,519 locations with postcode, gemeente, tech types
- `antennes_groepen.csv` — 391,453 antenna groups with frequency, power, height, direction, dates
- Compressed GeoJSON versions (.json.gz)

**Community (Antennekaart.nl):**
- Per-technology GeoJSON: 5G, 4G, 3G, 2G, GSM-R, CDMA, CGC, fixed-wireless
- `bts-all.json` — 39,715 BTS records with eNB IDs, TAC, provider, bands, last scanned
- Provider identification (KPN, Odido, Vodafone, ProRail)

See [`data/README.md`](data/README.md) for full schema documentation and API examples.

## Tech

Pure HTML/CSS/JS with Leaflet. No build step. Netlify proxy handles WFS CORS.

## License

Code: MIT. Data: Antennebureau / RDI open data.
