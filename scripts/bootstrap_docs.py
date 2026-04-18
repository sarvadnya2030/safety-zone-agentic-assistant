#!/usr/bin/env python3
"""
Seed data/docs/ with NDMA/hazard content AND download real India Flood Inventory data.
Run once before build_index.py.
"""
import csv
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

DOCS_DIR = Path("data/docs")
GEO_DIR = Path("data/geo")
DOCS_DIR.mkdir(parents=True, exist_ok=True)
GEO_DIR.mkdir(parents=True, exist_ok=True)

# ── Static seed documents ──────────────────────────────────────────────────────

SEED_DOCS = [
    (
        "ndma_flood_guidelines",
        "NDMA Flood Management Guidelines",
        "NDMA India",
        "https://ndma.gov.in",
        """Flood Management Guidelines — National Disaster Management Authority (NDMA), India.

Floods are one of the most common and widespread natural disasters in India. Nearly 40 million hectares (12% of land) is prone to floods and river erosion.

Key preparedness actions:
- Move to higher ground immediately when flood warnings are issued.
- Do not walk through moving water — 6 inches of moving water can knock you down.
- If driving, avoid flooded roads; turn around, don't drown.
- Disconnect electrical appliances. Do not touch electrical equipment if wet.
- Contact local authorities for evacuation routes and shelter locations.

Warning levels:
- Yellow Alert: Be aware — heavy rainfall expected
- Orange Alert: Be prepared — flooding possible
- Red Alert: Take action — flooding imminent or occurring

Relief camps are set up by district administration. Contact District Collector's office for nearest relief camp address.

Emergency contacts: NDMA helpline 1078. State emergency operations centres are operational 24x7 during floods.
""",
    ),
    (
        "ndma_earthquake_guidelines",
        "NDMA Earthquake Safety Guidelines",
        "NDMA India",
        "https://ndma.gov.in",
        """Earthquake Safety Guidelines — National Disaster Management Authority (NDMA), India.

India is highly vulnerable to earthquakes. More than 59% of India's land area is under threat from earthquakes of varying intensity.

Seismic zones:
- Zone II: Low damage risk
- Zone III: Moderate damage risk
- Zone IV: High damage risk (includes Delhi, J&K, Himachal Pradesh, Uttarakhand, North-East)
- Zone V: Very high damage risk (includes Andaman & Nicobar, parts of North-East)

What to do during an earthquake:
- DROP, COVER, and HOLD ON. Get under a desk or table.
- Stay away from windows, heavy furniture, and outer walls.
- Do not run outside during shaking.
- If outdoors, move away from buildings, streetlights, and utility wires.

After the earthquake:
- Expect aftershocks. Each time you feel one, DROP, COVER, and HOLD ON.
- Check for injuries. Do not move seriously injured persons.
- Check for hazards: gas leaks, damaged electrical wiring, structural damage.
- Use battery-powered radio for emergency information.

NCS (National Centre for Seismology) monitors all earthquakes in India. Magnitude 5.0+ events trigger public alerts.
""",
    ),
    (
        "ndma_cyclone_guidelines",
        "NDMA Cyclone Preparedness Guidelines",
        "NDMA India",
        "https://sachet.ndma.gov.in",
        """Cyclone Preparedness Guidelines — National Disaster Management Authority (NDMA).

India's east coast (Bay of Bengal) is highly cyclone-prone. Andhra Pradesh, Odisha, West Bengal, and Tamil Nadu are most affected.

Cyclone alert levels (IMD):
- Pre-Cyclone Watch: 72 hours before landfall
- Cyclone Alert: 48 hours before landfall
- Cyclone Warning: 24 hours before landfall
- Post-Landfall Outlook

Actions before landfall:
- Move to a cyclone shelter or pucca building on higher ground.
- Stock emergency supplies: water, food, medicines, torch, radio.
- Board up windows and doors. Secure loose objects.

Coastal evacuation:
- Follow directions of local authorities for evacuation routes.
- Identify nearest cyclone shelters. India has 8,900+ multi-purpose cyclone shelters on the east coast.
- Do not stay in coastal areas during high surge warnings.

SACHET (System for Advisories, Cyclone and Heavy rainfall Early warning Tools) issues real-time CAP alerts via NDMA. RSS feed: https://sachet.ndma.gov.in/CapFeed
""",
    ),
    (
        "ndma_landslide_guidelines",
        "NDMA Landslide Risk Reduction Guidelines",
        "NDMA India",
        "https://ndma.gov.in",
        """Landslide Risk Reduction Guidelines — National Disaster Management Authority (NDMA).

India ranks among the top five countries in the world affected by landslides. About 15% of India's land area is prone to landslides.

High-risk states: Uttarakhand, Himachal Pradesh, Sikkim, Darjeeling (West Bengal), Nilgiris (Tamil Nadu), Western Ghats (Kerala, Karnataka, Maharashtra), North-East states.

Warning signs of an impending landslide:
- Sudden increase in stream flow, often with debris
- Changes in water level in streams (muddy, brown discolouration)
- Cracks or unusual bulges appearing on slopes
- Trees or utility poles beginning to tilt
- Sounds of cracking trees or boulders

Preventive actions:
- Do not build on steep slopes without proper retaining structures.
- Plant deep-rooted plants on slopes to stabilise soil.
- Construct proper drainage systems.

Emergency response:
- Evacuate immediately if local authorities issue landslide warnings.
- Avoid valleys and low-lying areas in heavy rainfall.
- Do not return to slide areas until authorities declare safety.

India Landslide Atlas (NRSC/ISRO): provides district-wise landslide frequency maps across 17 states. Source: https://www.isro.gov.in/Landslide_Atlas_India.html
""",
    ),
    (
        "relief_camp_protocols",
        "Relief Camp Setup and Management Protocols",
        "NDMA/State DMAs",
        "https://ndma.gov.in",
        """Relief Camp Setup and Management — Standard Operating Procedures.

Relief camps (also called temporary accommodation centres or evacuation shelters) are established by district administrations during disasters.

Selection of sites:
- Located on high, safe ground (away from flood zones, landslide paths)
- Accessible by road from multiple directions
- Close to water supply and sanitation facilities
- Preferably in government schools, community halls, or purpose-built cyclone shelters

Minimum standards (Sphere standards):
- 3.5 square metres per person for covered living space
- 1 toilet per 20 persons; separate toilets for men and women
- Safe water: 15 litres per person per day minimum
- 2,100 kcal food per person per day

Registration and tracking:
- All evacuees must be registered on entry with name, address, family details
- Camp population data submitted to district EOC daily
- Separate registers for vulnerable groups: elderly, disabled, pregnant women, children

Medical support:
- Each camp should have a primary health team
- Emergency medication for 3 days minimum
- Medical mobile units for camps with 500+ persons

Contact: NDMA helpline 1078. State Emergency Operations Centre (SEOC): contact varies by state.
""",
    ),
    (
        "forest_fire_monitoring",
        "Forest Fire Monitoring and Response — India",
        "FSI / ISRO / NRSC",
        "https://fsiforestfire.gov.in",
        """Forest Fire Monitoring in India — FSI and ISRO/NRSC Systems.

Forest fires are monitored in near-real-time using MODIS and VIIRS satellite sensors. Data updates every 15 minutes as satellites pass over India (6 passes/day).

Primary portal: https://fsiforestfire.gov.in
- FirePointSearch: Current NRT fire hotspot query by state, date, and sensor
- LargeForestFire/CurrentLFF: Active large forest fires requiring emergency response
- ArchivalData: Historical fire records for analysis

High-risk states and seasons:
- Uttarakhand, Himachal Pradesh: April–June (pre-monsoon)
- Odisha, Jharkhand, Chhattisgarh: February–May
- Assam, Mizoram, Manipur: March–April (jhum cultivation)
- Maharashtra, Karnataka (Sahayadri): March–May

Fire Danger Rating System (FDRS):
- Normal: Low fire risk
- Moderate: Exercise caution
- High: Avoid forest entry
- Very High: Forest entry banned
- Extreme: Emergency response activated

Evacuation: Local forest officials and district administration coordinate. NDMA helpline 1078. Forest fire alerts also published on SACHET (https://sachet.ndma.gov.in).
""",
    ),
]

# ── India Flood Inventory download ────────────────────────────────────────────

# Source: https://zenodo.org/doi/10.5281/zenodo.4742142
# DFSI = District Flood Severity Index (district-level flood risk score)
FLOOD_CSV_URL = "https://zenodo.org/records/16994648/files/DFSI.csv?download=1"
FLOOD_CSV_PATH = GEO_DIR / "DFSI.csv"
FLOOD_PRIORS_PATH = GEO_DIR / "flood_inventory.geojson"

# Landslide risk priors from atlas (manually curated from ISRO Landslide Atlas 2023)
# Source: https://www.isro.gov.in/Landslide_Atlas_India.html
# Scale: 0.0 (low) to 1.0 (very high susceptibility)
LANDSLIDE_PRIORS = {
    "chamoli": 0.95, "rudraprayag": 0.92, "pithoragarh": 0.90, "uttarkashi": 0.88,
    "tehri garhwal": 0.85, "bageshwar": 0.82, "champawat": 0.78,
    "kinnaur": 0.93, "kullu": 0.88, "mandi": 0.82, "lahaul and spiti": 0.80,
    "shimla": 0.75, "sirmaur": 0.72,
    "ramban": 0.91, "doda": 0.88, "kishtwar": 0.86, "reasi": 0.80,
    "idukki": 0.85, "wayanad": 0.90, "palakkad": 0.70, "malappuram": 0.68,
    "darjeeling": 0.88, "kalimpong": 0.86,
    "north sikkim": 0.92, "east sikkim": 0.85, "west sikkim": 0.82,
    "tawang": 0.88, "west kameng": 0.83, "upper subansiri": 0.80,
    "raigad": 0.55, "ratnagiri": 0.52, "sindhudurg": 0.48,
    "kodagu": 0.72, "chikkamagaluru": 0.65, "hassan": 0.60,
    "nilgiris": 0.75, "coimbatore": 0.55,
}


def download_flood_csv() -> bool:
    if FLOOD_CSV_PATH.exists():
        print(f"  {FLOOD_CSV_PATH.name} already exists, skipping download")
        return True
    print(f"  Downloading India Flood Inventory DFSI.csv from Zenodo...")
    try:
        req = urllib.request.Request(str(FLOOD_CSV_URL), headers={"User-Agent": "CivilianSafetyMonitor/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        FLOOD_CSV_PATH.write_bytes(data)
        print(f"  Downloaded {len(data):,} bytes → {FLOOD_CSV_PATH}")
        return True
    except Exception as exc:
        print(f"  WARNING: Download failed ({exc}) — using fallback flood priors")
        return False


def build_flood_priors_geojson() -> None:
    """Convert DFSI.csv to GeoJSON-like dict with district risk scores."""
    features = []

    if FLOOD_CSV_PATH.exists():
        try:
            with open(FLOOD_CSV_PATH, encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames or []
                print(f"  DFSI.csv columns: {headers[:10]}")

                # DFSI.csv layout: unnamed col 0 = district, State_Name, DFSI
                district_col = headers[0] if headers else None  # first col (may be '')
                score_col = next(
                    (h for h in headers if "dfsi" in h.lower() or "severity" in h.lower() or "score" in h.lower()), None
                ) or next((h for h in headers if "index" in h.lower()), None)
                state_col = next((h for h in headers if "state" in h.lower()), None)

                print(f"  Using: district={district_col}, score={score_col}, state={state_col}")

                # Collect all scores to normalise to [0, 1]
                rows_raw = []
                for row in reader:
                    if district_col is None:
                        break
                    district = row.get(district_col, "").strip()
                    score_raw = row.get(score_col, "0") if score_col else "0"
                    state = row.get(state_col, "") if state_col else ""
                    try:
                        score = float(score_raw.replace(",", "") or 0)
                    except ValueError:
                        score = 0.0
                    if district:
                        rows_raw.append((district.lower(), state, score))

                if rows_raw:
                    max_score = max(s for _, _, s in rows_raw) or 1.0
                    for district, state, score in rows_raw:
                        normalised = min(score / max_score, 1.0)
                        features.append({
                            "type": "Feature",
                            "properties": {
                                "district": district,
                                "state": state,
                                "risk_score": round(normalised, 4),
                                "source": "India Flood Inventory DFSI (Zenodo)",
                            },
                            "geometry": None,
                        })
                    print(f"  Built {len(features)} district flood priors from DFSI.csv")
        except Exception as exc:
            print(f"  WARNING: DFSI.csv parse failed ({exc}) — using fallback")

    # Fallback: known high-risk districts
    if not features:
        fallback = {
            "dhubri": 0.95, "barpeta": 0.90, "kamrup": 0.85, "dibrugarh": 0.88,
            "darbhanga": 0.92, "muzaffarpur": 0.88, "sitamarhi": 0.87, "supaul": 0.89,
            "murshidabad": 0.85, "nadia": 0.82, "malda": 0.80,
            "kendrapara": 0.87, "cuttack": 0.82, "jagatsinghpur": 0.85,
            "east godavari": 0.78, "west godavari": 0.75, "krishna": 0.72,
            "ernakulam": 0.70, "thrissur": 0.68, "pathanamthitta": 0.72,
            "kolhapur": 0.65, "sangli": 0.60, "raigad": 0.58,
            "bahraich": 0.82, "lakhimpur kheri": 0.80,
        }
        for district, score in fallback.items():
            features.append({
                "type": "Feature",
                "properties": {"district": district, "risk_score": score,
                               "source": "India Flood Inventory (curated fallback)"},
                "geometry": None,
            })
        print(f"  Used curated fallback: {len(features)} districts")

    geojson = {"type": "FeatureCollection", "features": features}
    FLOOD_PRIORS_PATH.write_text(json.dumps(geojson, indent=2))
    print(f"  Written {FLOOD_PRIORS_PATH}")


def build_landslide_geojson() -> None:
    landslide_path = GEO_DIR / "landslide_atlas.geojson"
    features = [
        {
            "type": "Feature",
            "properties": {"district": district, "risk_score": score,
                           "source": "ISRO Landslide Atlas 2023"},
            "geometry": None,
        }
        for district, score in LANDSLIDE_PRIORS.items()
    ]
    geojson = {"type": "FeatureCollection", "features": features}
    landslide_path.write_text(json.dumps(geojson, indent=2))
    print(f"  Written {landslide_path} ({len(features)} districts)")


def write_doc(stem: str, title: str, source: str, url: str, text: str) -> None:
    txt_path = DOCS_DIR / f"{stem}.txt"
    meta_path = DOCS_DIR / f"{stem}.meta.json"
    txt_path.write_text(text, encoding="utf-8")
    meta_path.write_text(json.dumps({
        "title": title, "source": source, "url": url,
        "published_at": "2024-01-01T00:00:00Z",
    }, indent=2), encoding="utf-8")
    print(f"  wrote {txt_path.name}")


if __name__ == "__main__":
    print(f"\n1. Seeding {len(SEED_DOCS)} documents into {DOCS_DIR}/")
    for stem, title, source, url, text in SEED_DOCS:
        write_doc(stem, title, source, url, text)

    print(f"\n2. Downloading India Flood Inventory (Zenodo) →")
    download_flood_csv()
    build_flood_priors_geojson()

    print(f"\n3. Building landslide priors (ISRO Atlas 2023) →")
    build_landslide_geojson()

    print(f"\nDone. Now run: python scripts/build_index.py")
