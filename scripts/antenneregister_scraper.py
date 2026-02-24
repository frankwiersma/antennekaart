#!/usr/bin/env python3
"""
Antenneregister.nl WFS Scraper
Downloads alle antenne-installaties en antenne-groepen, linkt ze aan elkaar.

WFS endpoint: https://antenneregister.nl/mapserver/wfs/

BELANGRIJK: Deze WFS server heeft twee eigenaardigheden:
  1. CQL_FILTER wordt STILLETJES GENEGEERD — gebruik OGC XML FILTER
  2. Ongelimiteerd pagineren (count+startindex) retourneert NIET alle records
     (~391k van ~600k+). Records die via OGC FILTER wél bestaan worden gemist.

Oplossing: We downloaden eerst alle Antennes (installaties), verzamelen alle
unieke AI_IDs uit ANT_IDS, en fetchen de groepen per batch via OGC XML FILTER.
Dit geeft ~96%+ coverage in plaats van ~63%.
"""

import json
import sys
import time
import urllib.request
import urllib.parse
from collections import defaultdict

WFS_URL = "https://antenneregister.nl/mapserver/wfs/"
PAGE_SIZE = 5000
# Max IDs per OGC FILTER OR-query (server has URL length limits)
BATCH_SIZE = 25


def fetch_wfs(typename, count=PAGE_SIZE, start_index=0, ogc_filter=None):
    """Fetch features from WFS. Uses OGC XML FILTER when provided."""
    params = {
        "service": "WFS",
        "request": "GetFeature",
        "version": "2.0.0",
        "typename": typename,
        "outputformat": "application/json",
        "srsname": "EPSG:28992",
        "count": str(count),
    }
    if ogc_filter:
        params["FILTER"] = ogc_filter
    else:
        params["startindex"] = str(start_index)

    url = WFS_URL + "?" + urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return json.loads(resp.read())
        except Exception as e:
            if attempt < 2:
                print(f"    Retry ({attempt+1}/3): {e}")
                time.sleep(2)
            else:
                raise


def fetch_all_paginated(typename):
    """Fetch all features using pagination (for Antennes layer)."""
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


def build_ogc_filter_or(field, values):
    """Build OGC XML FILTER with OR clauses for multiple values."""
    if len(values) == 1:
        return (
            f"<Filter><PropertyIsEqualTo>"
            f"<PropertyName>{field}</PropertyName>"
            f"<Literal>{values[0]}</Literal>"
            f"</PropertyIsEqualTo></Filter>"
        )
    clauses = "".join(
        f"<PropertyIsEqualTo><PropertyName>{field}</PropertyName>"
        f"<Literal>{v}</Literal></PropertyIsEqualTo>"
        for v in values
    )
    return f"<Filter><Or>{clauses}</Or></Filter>"


def fetch_groepen_by_ids(ai_ids):
    """Fetch Antennes_Groepen for specific AI_IDs using OGC FILTER in batches."""
    all_features = []
    ids = list(ai_ids)
    total_batches = (len(ids) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(ids), BATCH_SIZE):
        batch = ids[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1

        if batch_num % 50 == 1 or batch_num == total_batches:
            print(
                f"  Batch {batch_num}/{total_batches} "
                f"({len(all_features)} records zo ver)...",
                flush=True,
            )

        ogc_filter = build_ogc_filter_or("AI_ID", batch)

        # Fetch with high count — one AI_ID can have many panels
        data = fetch_wfs("Antennes_Groepen", count=5000, ogc_filter=ogc_filter)
        features = data.get("features", [])
        all_features.extend(features)

        # Respectful rate limiting
        if batch_num % 10 == 0:
            time.sleep(0.5)

    return all_features


def main():
    print("=" * 60)
    print("Antenneregister.nl WFS Scraper (OGC FILTER methode)")
    print("=" * 60)

    # ── 1. Download alle antenne-installaties ──
    print("\n=== Stap 1: Antennes (installaties) ===")
    antennes = fetch_all_paginated("Antennes")
    print(f"Totaal: {len(antennes)} installaties\n")

    # ── 2. Verzamel alle unieke AI_IDs uit ANT_IDS ──
    print("=== Stap 2: AI_IDs verzamelen ===")
    all_ai_ids = set()
    for ant in antennes:
        ant_ids_str = ant["properties"].get("ANT_IDS", "") or ""
        for aid in ant_ids_str.split(", "):
            aid = aid.strip()
            if aid:
                all_ai_ids.add(aid)

    print(f"Unieke AI_IDs uit Antennes: {len(all_ai_ids)}")

    # ── 3. Fetch groepen per batch via OGC FILTER ──
    print(f"\n=== Stap 3: Antennes_Groepen ophalen ({len(all_ai_ids)} IDs in batches van {BATCH_SIZE}) ===")
    print(f"Geschatte tijd: ~{len(all_ai_ids) // BATCH_SIZE // 2} minuten\n")

    groepen = fetch_groepen_by_ids(all_ai_ids)
    print(f"\nTotaal: {len(groepen)} antenne-groep records\n")

    # ── 4. Bouw lookup: AI_ID → lijst van groep-properties ──
    groep_lookup = defaultdict(list)
    for g in groepen:
        ai_id = str(g["properties"]["AI_ID"])
        groep_lookup[ai_id].append(g["properties"])

    found_unique = len(groep_lookup)
    coverage = found_unique / len(all_ai_ids) * 100 if all_ai_ids else 0
    print(f"Unieke AI_IDs met data: {found_unique}/{len(all_ai_ids)} ({coverage:.1f}%)")

    # ── 5. Link antennes aan groepen ──
    print("\n=== Stap 4: Linken ===")
    linked = []
    total_ids = 0
    found_ids = 0
    missing_ids = 0
    missing_examples = []

    for ant in antennes:
        props = ant["properties"]
        ant_ids_str = props.get("ANT_IDS", "") or ""
        coords = ant.get("geometry", {}).get("coordinates", [None, None])

        ant_id_list = [x.strip() for x in ant_ids_str.split(", ") if x.strip()]

        antenne_details = []
        for aid in ant_id_list:
            total_ids += 1
            if aid in groep_lookup:
                found_ids += 1
                antenne_details.extend(groep_lookup[aid])
            else:
                missing_ids += 1
                if len(missing_examples) < 20:
                    missing_examples.append(aid)

        linked.append(
            {
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
            }
        )

    # ── 6. Stats ──
    coverage = found_ids / total_ids * 100 if total_ids else 0
    print(f"\n{'=' * 60}")
    print(f"RESULTAAT")
    print(f"{'=' * 60}")
    print(f"Installaties:        {len(linked)}")
    print(f"Antenne-groep IDs:   {total_ids}")
    print(f"  Gevonden:          {found_ids} ({coverage:.1f}%)")
    print(f"  Niet gevonden:     {missing_ids}")
    if missing_examples:
        print(f"  Voorbeelden:       {', '.join(missing_examples[:10])}")

    linked_5g = [a for a in linked if a["is_5g"]]
    linked_4g = [a for a in linked if a["is_4g"]]
    print(f"\n5G installaties:     {len(linked_5g)}")
    print(f"  Met details:       {sum(1 for a in linked_5g if a['antennes'])}")
    print(f"4G installaties:     {len(linked_4g)}")
    print(f"  Met details:       {sum(1 for a in linked_4g if a['antennes'])}")

    # ── 7. Opslaan ──
    with open("antennes_linked.json", "w") as f:
        json.dump(linked, f, indent=2, ensure_ascii=False)
    print(f"\nOpgeslagen: antennes_linked.json ({len(linked)} records)")

    with open("antennes_5g_linked.json", "w") as f:
        json.dump(linked_5g, f, indent=2, ensure_ascii=False)
    print(f"Opgeslagen: antennes_5g_linked.json ({len(linked_5g)} records)")

    # Save missing IDs for debugging
    if missing_examples:
        with open("missing_ai_ids.json", "w") as f:
            json.dump(missing_examples, f, indent=2)
        print(f"Opgeslagen: missing_ai_ids.json ({len(missing_examples)} voorbeelden)")


if __name__ == "__main__":
    main()
