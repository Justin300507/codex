import asyncio
import difflib
import math
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
app = FastAPI(title="LastMile", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

# Kochi Metro stations, west-to-east ordering, approximate public coordinates.
STATIONS = {
    "Aluva": (10.1076, 76.3516), "Pulinchodu": (10.0949, 76.3496), "Companypady": (10.0895, 76.3482),
    "Ambattukavu": (10.0785, 76.3472), "Muttom": (10.0685, 76.3450), "Kalamassery": (10.0521, 76.3412),
    "Cochin University": (10.0470, 76.3286), "Pathadipalam": (10.0388, 76.3256), "Edapally": (10.0257, 76.3085),
    "Changampuzha Park": (10.0193, 76.3071), "Palarivattom": (10.0051, 76.3065), "JLN Stadium": (9.9982, 76.3025),
    "Kaloor": (9.9915, 76.2992), "Lissie": (9.9854, 76.2914), "MG Road": (9.9773, 76.2850),
    "Maharaja's College": (9.9686, 76.2878), "Ernakulam South": (9.9604, 76.2905), "Kadavanthra": (9.9675, 76.2981),
    "Elamkulam": (9.9653, 76.3048), "Vyttila": (9.9675, 76.3200), "Thykoodam": (9.9676, 76.3307),
    "Petta": (9.9560, 76.3420), "SN Junction": (9.9520, 76.3518), "Vadakkekotta": (9.9480, 76.3581),
    "Thrippunithura Terminal": (9.9460, 76.3618),
}

# Local fallbacks keep destination confirmation usable during API failures.
LANDMARKS = {
    "Fort Kochi": (9.9656, 76.2423), "Mattancherry": (9.9574, 76.2590), "Marine Drive": (9.9816, 76.2797),
    "Lulu Mall": (10.0272, 76.3087), "Kochi Airport": (10.1518, 76.3930), "Hill Palace": (9.9497, 76.3630),
    "Infopark": (10.0159, 76.3645), "Kakkanad": (10.0159, 76.3419), "Cochin University": (10.0430, 76.3270),
    "Amrita Hospital": (10.0454, 76.3265), "Broadway": (9.9813, 76.2814), "MG Road": (9.9773, 76.2850),
    "Vyttila Hub": (9.9667, 76.3202), "Ernakulam Junction": (9.9602, 76.2905), "Bolgatty": (10.0124, 76.2793),
    "Cherai Beach": (10.1426, 76.1786), "Willingdon Island": (9.9514, 76.2748), "Panampilly Nagar": (9.9668, 76.2960),
    "Kaloor": (9.9908, 76.2993), "Edappally": (10.0257, 76.3085),
}

class LocateRequest(BaseModel):
    destination: str = Field(min_length=2, max_length=160)

class PassengerRequest(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    destination: str
    lat: float
    lng: float
    origin_station: str = "Vyttila"
    budget_range: Literal["under_100", "100_250", "250_500", "no_limit"] = "no_limit"
    max_walk_m: int = Field(default=300, ge=0, le=1500)
    preference: Literal["any", "women-only", "quiet"] = "any"
    meetup_tag: str = Field(default="", max_length=60)

def haversine(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    return 6371 * 2 * math.asin(math.sqrt(math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2))

def road_distance(origin, dest, destination_name=""):
    if "fort kochi" in destination_name.lower(): return 14.8
    return round(haversine(origin, dest) * 1.4, 1)

def fare_options(distance):
    night = datetime.now().hour >= 22 or datetime.now().hour < 5
    auto = max(26, 26 + 17.14 * max(0, distance - 1)) * (1.5 if night else 1)
    cab = 68 + 20 * distance
    bus = 10 if distance < 5 else 12 if distance < 12 else 15
    return {"walk": 0, "bus": round(bus), "auto": round(auto), "cab": round(cab)}

def recommendation(distance, budget):
    fares = fare_options(distance)
    if distance < 1:
        return {"mode": "walk", "fare": 0, "reasoning": "This is under 1 km — a short, zero-cost walk is the best fit.", "fares": fares, "time": 12}
    bus_time, auto_time, cab_time = distance * 4 + 10, distance * 2.5, distance * 2.2
    if distance >= 18:
        mode, reason = "bus", "At this distance, bus is recommended: auto and cab costs rise sharply, while pooling is unavailable."
    elif distance <= 8:
        mode, reason = "auto", "An auto avoids indirect bus waiting and is the best balance of direct travel time and cost."
    elif budget in ("250_500", "no_limit"):
        mode, reason = "cab", "A cab is preferred here for a faster, tracked, driver-verified trip with more room for comfort."
    else:
        mode, reason = "auto", "An auto gives a direct route while staying closer to your selected budget."
    fastest = min((bus_time, "bus"), (auto_time, "auto"), (cab_time, "cab"))[1]
    return {"mode": mode, "fare": fares[mode], "reasoning": reason, "fares": fares, "time": round({"bus":bus_time,"auto":auto_time,"cab":cab_time}.get(mode,12)), "fastest": fastest, "cheapest": "bus"}

async def google_geocode(query):
    key = os.getenv("GOOGLE_GEOCODING_API_KEY")
    if not key: return None
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get("https://maps.googleapis.com/maps/api/geocode/json", params={"address": f"{query}, Kochi, Kerala", "region": "in", "key": key})
            item = res.json().get("results", [None])[0]
            if item:
                loc = item["geometry"]["location"]
                return {"address": item["formatted_address"], "lat": loc["lat"], "lng": loc["lng"], "source": "google"}
    except Exception: pass
    return None

async def seed_weather():
    # Keep optional weather non-blocking and transparent when no configured key exists.
    return {"available": False, "message": "Weather check is optional for this demo."}

def seeded_passengers():
    rows = [("Anjali", "Hill Palace", "women-only"), ("Riya", "Hill Palace", "women-only"), ("Arun", "Infopark", "any"), ("Vivek", "Infopark", "any"), ("Meera", "Kakkanad", "women-only"), ("Neha", "Kakkanad", "any"), ("Nikhil", "Marine Drive", "quiet"), ("Rahul", "Fort Kochi", "any"), ("Fathima", "Panampilly Nagar", "any"), ("Kevin", "Lulu Mall", "any"), ("Jishnu", "Broadway", "any"), ("Asha", "Ernakulam Junction", "any"), ("Sanjay", "Cochin University", "quiet"), ("Tina", "Mattancherry", "any"), ("Adarsh", "Bolgatty", "any")]
    return [{"id": f"seed-{i}", "name": n, "destination": d, "lat": LANDMARKS[d][0], "lng": LANDMARKS[d][1], "origin_station": "Vyttila", "budget_range": "no_limit", "max_walk_m": 400, "preference": p, "meetup_tag": "Metro gate", "created": time.time()-i*60} for i,(n,d,p) in enumerate(rows)]

PASSENGERS = seeded_passengers()

def build_groups():
    eligible = [p for p in PASSENGERS if road_distance(STATIONS.get(p["origin_station"], STATIONS["Vyttila"]), (p["lat"],p["lng"]), p["destination"]) < 18]
    groups, used = [], set()
    for p in eligible:
        if p["id"] in used: continue
        matches = [q for q in eligible if q["id"] not in used and q["id"] != p["id"] and p["preference"] == q["preference"] and haversine((p["lat"],p["lng"]),(q["lat"],q["lng"])) <= .9 and min(p["max_walk_m"],q["max_walk_m"]) >= 150]
        members = [p] + matches[:3]
        if len(members) < 2: continue
        used.update(m["id"] for m in members)
        dist = road_distance(STATIONS.get(p["origin_station"], STATIONS["Vyttila"]), (p["lat"],p["lng"]), p["destination"])
        rec = recommendation(dist, p["budget_range"])
        mode = "cab" if rec["mode"] == "cab" else "auto"
        cost = round(fare_options(dist)[mode] / len(members))
        groups.append({"group_id": "G-"+p["id"][-4:].upper(), "members": [{"name":m["name"],"tag":m["meetup_tag"]} for m in members], "suggested_mode": mode, "cost_per_member": cost, "ai_reasoning": f"Shared {mode} accepts a brief coordination stop in exchange for a lower individual fare.", "meetup_point_at_station": "Vyttila Metro main exit", "women_only": p["preference"] == "women-only", "destination": p["destination"]})
    return groups

@app.get("/")
def home(): return FileResponse(ROOT / "static" / "index.html")

@app.get("/health")
def health(): return {"status": "healthy", "service": "LastMile"}

@app.get("/stations")
def stations(): return [{"name": n, "lat": c[0], "lng": c[1]} for n,c in STATIONS.items()]

@app.post("/locate")
async def locate(req: LocateRequest):
    real = await google_geocode(req.destination)
    if real: return real
    names = list(LANDMARKS)
    match = difflib.get_close_matches(req.destination.lower(), [n.lower() for n in names], n=1, cutoff=.25)
    name = next((n for n in names if match and n.lower() == match[0]), "Vyttila Hub")
    lat,lng = LANDMARKS[name]
    return {"address": name, "lat": lat, "lng": lng, "source": "fallback"}

@app.post("/passengers")
def add_passenger(req: PassengerRequest):
    if req.origin_station not in STATIONS: raise HTTPException(400, "Unknown metro station")
    dist = road_distance(STATIONS[req.origin_station], (req.lat,req.lng), req.destination)
    rec = recommendation(dist, req.budget_range)
    p = {"id": uuid.uuid4().hex[:8], **req.model_dump(), "distance_km":dist, "created":time.time()}
    PASSENGERS.append(p)
    return {"passenger":p, "recommendation":rec, "pooling_available": dist < 18, "weather": asyncio.run(seed_weather())}

@app.get("/groups")
def groups(): return {"groups": build_groups(), "updated_at": datetime.now().isoformat()}

@app.get("/stats")
def stats():
    groups = build_groups(); counts = {}
    for p in PASSENGERS: counts[p["destination"]] = counts.get(p["destination"],0)+1
    saved = sum(g["cost_per_member"] * len(g["members"]) * .28 for g in groups)
    return {"total_passengers":len(PASSENGERS), "groups_formed":len(groups), "money_saved":round(saved), "co2_saved":round(sum(len(g["members"])*.18 for g in groups),1), "most_requested":max(counts,key=counts.get)}
