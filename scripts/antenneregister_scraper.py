#!/usr/bin/env python3
"""
Antenneregister.nl WFS Scraper
Downloads alle antenne-installaties en antenne-groepen, linkt ze aan elkaar.

WFS endpoint: https://antenneregister.nl/mapserver/wfs/
- Antennes: installaties (masten/locaties) met ANT_IDS (comma-separated groep IDs)
- Antennes_Groepen: individuele antennes met AI_ID (linkt naar ANT_IDS)

Let op: ~37% van de ANT_IDS heeft geen match in Antennes_Groepen (data-issue server-side).
"""

import json
import urllib.request
import urllib.parse
from collections import defaultdict

WFS_URL = "https://antenneregister.nl/mapserver/wfs/"
PAGE_SIZE = 5000


def fetch_wfs(typename, count=PAGE_SIZE, start_index=0):
    params = {
        "service": "WFS",
        "request": "GetFeature",
        "version": "2.0.0",
        "typename": typename,
        "outputformat": "application/json",
        "srsname": "EPSG:28992",
        "count": str(count),
        "startindex": str(start_index),
    }
    url = WFS_URL + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read())


def fetch_all(typename):
    all_features = []
    start = 0
    while True:
        print(f"  {typename} offset={start}...", end=" ", flush=True)
        data = fetch_wfs(typename, count=PAGE_SIZE, start_index=start)
        features = data.get("features", [])
        print(f"{len(features)} features")
        all_features.extend(features)
        if len(features) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return all_features


def main():
    # 1. Download alle antenne-installaties
    print("=== Downloading Antennes (installaties) ===")
    antennes = fetch_all("Antennes")
    print(f"Totaal: {len(antennes)} installaties\n")

    # 2. Download alle antenne-groepen
    print("=== Downloading Antennes_Groepen (individuele antennes) ===")
    groepen = fetch_all("Antennes_Groepen")
    print(f"Totaal: {len(groepen)} antenne records\n")

    # 3. Bouw lookup: AI_ID -> lijst van antenne-groepen
    groep_lookup = defaultdict(list)
    for g in groepen:
        ai_id = str(g["properties"]["AI_ID"])
        groep_lookup[ai_id].append(g["properties"])

    print(f"Unieke AI_IDs in Antennes_Groepen: {len(groep_lookup)}")

    # 4. Link antennes aan groepen
    linked = []
    total_ids = 0
    found_ids = 0
    missing_ids = 0

    for ant in antennes:
        props = ant["properties"]
        ant_ids_str = props.get("ANT_IDS", "")
        coords = ant.get("geometry", {}).get("coordinates", [None, None])

        # Split ANT_IDS op ", "
        ant_id_list = [x.strip() for x in ant_ids_str.split(", ") if x.strip()] if ant_ids_str else []

        antenne_details = []
        for aid in ant_id_list:
            total_ids += 1
            if aid in groep_lookup:
                found_ids += 1
                antenne_details.extend(groep_lookup[aid])
            else:
                missing_ids += 1

        linked.append({
            "id": props.get("ID"),
            "x": coords[0],
            "y": coords[1],
            "gemeente": props.get("GEMEENTE"),
            "woonplaats": props.get("WOONPLAATSNAAM"),
            "postcode": props.get("POSTCODE"),
            "hoofdsoort": props.get("HOOFDSOORT"),
            "is_2g": bool(props.get("TWEEG")),
            "is_3g": bool(props.get("DRIEG")),
            "is_4g": bool(props.get("VIERG")),
            "is_5g": bool(props.get("VIJFG")),
            "is_mobiel": bool(props.get("MOBIELE_COMMUNICATIE")),
            "is_omroep": bool(props.get("OMROEP")),
            "is_vaste_verb": bool(props.get("VASTE_VERB")),
            "small_cell": props.get("SMALL_CELL_INDICATOR", ""),
            "ant_ids": ant_id_list,
            "antennes": antenne_details,
        })

    # 5. Stats
    coverage = found_ids / total_ids * 100 if total_ids else 0
    print(f"\n=== Resultaat ===")
    print(f"Installaties: {len(linked)}")
    print(f"Antenne-groep IDs totaal: {total_ids}")
    print(f"  Gevonden: {found_ids} ({coverage:.1f}%)")
    print(f"  Missend:  {missing_ids} (data ontbreekt in WFS)")

    # Filter alleen 5G als je wilt
    linked_5g = [a for a in linked if a["is_5g"]]
    print(f"\nWaarvan 5G installaties: {len(linked_5g)}")
    print(f"  Met antenne-details: {sum(1 for a in linked_5g if a['antennes'])}")
    print(f"  Zonder details:      {sum(1 for a in linked_5g if not a['antennes'])}")

    # 6. Opslaan
    with open("antennes_linked.json", "w") as f:
        json.dump(linked, f, indent=2, ensure_ascii=False)
    print(f"\nOpgeslagen: antennes_linked.json ({len(linked)} records)")

    with open("antennes_5g_linked.json", "w") as f:
        json.dump(linked_5g, f, indent=2, ensure_ascii=False)
    print(f"Opgeslagen: antennes_5g_linked.json ({len(linked_5g)} records)")


if __name__ == "__main__":
    main()
