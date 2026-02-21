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

All data is sourced from the official [Antenneregister](https://antenneregister.nl) (RDI) via their WFS endpoint.

See [`data/README.md`](data/README.md) for full schema documentation and API examples.

## Tech

Pure HTML/CSS/JS with Leaflet. No build step. Netlify proxy handles WFS CORS.

## License

Code: MIT. Data: Antennebureau / RDI open data.
