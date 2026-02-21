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

## License

This data is published by the [Antennebureau](https://antennebureau.nl) / Rijksinspectie Digitale Infrastructuur (RDI) as open data.
