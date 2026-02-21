# Antenneregister Data

Complete dataset of all antenna installations in the Netherlands, sourced from the official [Antenneregister](https://antenneregister.nl) (Rijksinspectie Digitale Infrastructuur).

**Last downloaded:** 2026-02-21

## Files

| File | Records | Description |
|------|---------|-------------|
| `antennes.csv` | 35,519 | All antenna locations (postcode, gemeente, technology types, antenna IDs) |
| `antennes.json.gz` | 35,519 | Same data as GeoJSON (coordinates in EPSG:28992 / RD New) |
| `antennes_groepen.csv` | 391,453 | Per-antenna detail: frequency, power (dBW), height, beam direction, safety distance, dates |
| `antennes_groepen.json.gz` | 391,453 | Same data as GeoJSON |

## Schema

### Antennes (locations)
| Field | Description |
|-------|-------------|
| `ID` | Location ID |
| `X`, `Y` | Coordinates (RD New / EPSG:28992) |
| `AANTAL` | Number of antenna installations |
| `HOOFDSOORT` | Primary technology type (e.g., "5G NR, LTE, UMTS") |
| `ANT_IDS` | Comma-separated antenna installation IDs (links to `AI_ID` in Antennes_Groepen) |
| `TWEEG`..`VIJFG` | Count per generation (2G, 3G, 4G, 5G) |
| `GEMEENTE` | Municipality |
| `POSTCODE` | Postal code |
| `WOONPLAATSNAAM` | City/town name |
| `SMALL_CELL_INDICATOR` | Whether it's a small cell |

### Antennes_Groepen (per-antenna detail)
| Field | Description |
|-------|-------------|
| `ID` | Record ID |
| `AI_ID` | Antenna Installation ID (links to `ANT_IDS` in Antennes) |
| `SAT_CODE` | Technology: `5G NR`, `LTE`, `UMTS`, `GSM`, `VV` (microwave), `OMROEP AMFM`, `ZENDAMATEUR`, etc. |
| `DIR_NONDIR` | `D` = directional, `N` = omnidirectional |
| `HOOGTE` | Antenna height in meters |
| `HOOFDSTRAALRICHTING` | Main beam direction in degrees (0-360) |
| `VEILIGE_AFSTAND` | Safety distance in meters |
| `FREQUENTIE` | Operating frequency (e.g., "773 MHz", "3700 MHz", "38.36 GHz") |
| `ZENDVERMOGEN` | Transmit power in dBW |
| `DATUM_PLAATSING` | Installation date |
| `DATUM_INGEBRUIKNAME` | Commissioning date |
| `DATUM_WIJZIGING` | Last modification date |

## Data Source

**WFS Endpoint:** `https://antenneregister.nl/mapserver/wfs/`

```bash
# Example: Get all antennas in a bounding box (RD New coordinates)
curl "https://antenneregister.nl/mapserver/wfs/?service=WFS&version=2.0.0&request=GetFeature&typeName=ms:Antennes&outputFormat=application/json&bbox=136000,455000,138000,457000"

# Example: Get antenna detail by installation ID
curl "https://antenneregister.nl/mapserver/wfs/?service=WFS&version=2.0.0&request=GetFeature&typeName=ms:Antennes_Groepen&outputFormat=application/json&CQL_FILTER=AI_ID=8945423867"
```

---

## Antennekaart.nl Data (Community / Crowd-Sourced)

Additional data scraped from [antennekaart.nl](https://antennekaart.nl) which enriches the official register with provider identification, BTS metadata, and field scan results.

Located in `antennekaart.nl/` subdirectory.

### Files

| File | Records | Description |
|------|---------|-------------|
| `5g.json` | 14,411 | 5G sites (GeoJSON with provider, bands, angles) |
| `4g.json` | 16,164 | 4G sites |
| `3g.json` | 5,280 | 3G sites |
| `2g.json` | 10,263 | 2G sites |
| `gsm-r.json` | 369 | GSM-R (ProRail train communications) |
| `cdma.json` | 184 | CDMA (smart meter readout network) |
| `cgc.json` | 7 | CGC (in-flight 4G internet) |
| `fixed-wireless.json` | 13,900 | Microwave / fixed wireless links |
| `bts-all.json` | 39,715 | All BTS records with eNB identifiers, TAC, provider, bands, last scanned |
| `site-types.json` | 29 | Site type definitions (indoor, rooftop, mast, etc.) |

### Properties per tower (GeoJSON)

- `location_id` — Antennekaart.nl site ID
- `coordinates` — [lon, lat] (WGS84)
- `provider_id` — Network operator ID
- `bands` — Frequency band numbers
- `angles` — Antenna azimuth angles (degrees)
- `is_kpn_huawei` — Huawei equipment flag (KPN sites)
- `deleted` — Whether site is decommissioned

### BTS Properties (bts-all.json)

- `identifier` — eNB ID (4G) or equivalent
- `tracking_area` — TAC (Tracking Area Code)
- `last_scanned` — When this BTS was last detected in the field
- `provider` — `{id, name, slug, mcc, mnc, color}`
- `lat`, `lon` — Coordinates (WGS84)
- `band_ids` — Active frequency band IDs

### Providers

| ID | Name | MCC-MNC | Color |
|----|------|---------|-------|
| 1 | KPN | 204-08 | #00FF00 |
| 3 | Odido (T-Mobile) | 204-16 | #0084FF |
| 4 | Vodafone | 204-04 | #FF0000 |
| 5 | ProRail | — | #B20A2F |
| 6 | Utility Connect | — | #00FFFF |
| 7 | EAN (aviation) | — | #0000FF |

### API Endpoints (antennekaart.nl)

```bash
# Map layer per technology (GeoJSON)
curl "https://antennekaart.nl/api/v1/map/layer/4g/?bbox=5.0,52.0,5.5,52.5&zoom=12"

# Location details
curl "https://antennekaart.nl/api/v1/locations/{location_id}/"

# BTS lookup by eNB identifier
curl "https://antennekaart.nl/api/v1/bts/?radio_technology=lte&identifier=409040"
```

---

## License

This data is published by the [Antennebureau](https://antennebureau.nl) / Rijksinspectie Digitale Infrastructuur (RDI) as open data. Antennekaart.nl data is community-sourced.
