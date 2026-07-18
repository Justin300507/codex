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

BUS_STANDS = [
    {"name": "Vyttila Mobility Hub", "lat": 9.9668, "lng": 76.3204, "routes": ["Kakkanad", "Fort Kochi", "Aluva"]},
    {"name": "Aluva KSRTC Bus Stand", "lat": 10.1085, "lng": 76.3510, "routes": ["Airport", "Angamaly", "Ernakulam"]},
    {"name": "Edappally Junction Bus Stop", "lat": 10.0253, "lng": 76.3074, "routes": ["Vyttila", "Kakkanad", "Aluva"]},
    {"name": "Kaloor Bus Stand", "lat": 9.9910, "lng": 76.3002, "routes": ["Fort Kochi", "MG Road", "Vyttila"]},
    {"name": "MG Road Bus Stop", "lat": 9.9771, "lng": 76.2842, "routes": ["Vyttila", "High Court", "Mattancherry"]},
    {"name": "Thrippunithura Bus Stand", "lat": 9.9452, "lng": 76.3631, "routes": ["Hill Palace", "Vyttila", "Kakkanad"]},
]

# Station-specific transfer points, used instead of inferring from a small citywide list.
STATION_HUBS = {
    "Aluva": ("Aluva KSRTC Bus Stand", 280, "Aluva Metro Auto Stand", 45, ["Airport", "Angamaly", "Ernakulam"]),
    "Pulinchodu": ("Pulinchodu Bus Stop", 90, "Pulinchodu Auto Point", 30, ["Aluva", "Kalamassery", "Edappally"]),
    "Companypady": ("Companypady Junction Bus Stop", 110, "Companypady Auto Stand", 35, ["Aluva", "Kalamassery", "Edappally"]),
    "Ambattukavu": ("Ambattukavu Bus Stop", 85, "Ambattukavu Auto Point", 25, ["Aluva", "Kalamassery", "Edappally"]),
    "Muttom": ("Muttom Metro Bus Stop", 100, "Muttom Auto Stand", 30, ["Aluva", "Kalamassery", "Edappally"]),
    "Kalamassery": ("Kalamassery Municipal Bus Stop", 170, "Kalamassery Auto Stand", 40, ["Aluva", "Edappally", "Kakkanad"]),
    "Cochin University": ("CUSAT Bus Stop", 75, "CUSAT Auto Stand", 25, ["Kakkanad", "Edappally", "Aluva"]),
    "Pathadipalam": ("Pathadipalam Bus Stop", 65, "Pathadipalam Auto Point", 20, ["Kakkanad", "Edappally", "Aluva"]),
    "Edapally": ("Edappally Junction Bus Stop", 140, "Edappally Metro Auto Stand", 45, ["Vyttila", "Kakkanad", "Aluva"]),
    "Changampuzha Park": ("Changampuzha Park Bus Stop", 70, "Changampuzha Auto Point", 25, ["Aluva", "Kaloor", "Vyttila"]),
    "Palarivattom": ("Palarivattom Junction Bus Stop", 105, "Palarivattom Auto Stand", 35, ["Kakkanad", "Kaloor", "Vyttila"]),
    "JLN Stadium": ("JLN Stadium Bus Stop", 80, "Stadium Metro Auto Point", 25, ["Kakkanad", "Kaloor", "Vyttila"]),
    "Kaloor": ("Kaloor Bus Stand", 160, "Kaloor Metro Auto Stand", 45, ["Fort Kochi", "MG Road", "Vyttila"]),
    "Lissie": ("Lissie Junction Bus Stop", 90, "Lissie Auto Point", 25, ["MG Road", "Kaloor", "Vyttila"]),
    "MG Road": ("MG Road Bus Stop", 110, "MG Road Metro Auto Stand", 35, ["Vyttila", "High Court", "Mattancherry"]),
    "Maharaja's College": ("Maharaja's College Bus Stop", 75, "Maharaja's Auto Point", 20, ["MG Road", "Fort Kochi", "Vyttila"]),
    "Ernakulam South": ("Ernakulam Junction Bus Stop", 150, "Ernakulam South Auto Stand", 45, ["Vyttila", "MG Road", "Fort Kochi"]),
    "Kadavanthra": ("Kadavanthra Junction Bus Stop", 95, "Kadavanthra Auto Stand", 30, ["Vyttila", "MG Road", "Kakkanad"]),
    "Elamkulam": ("Elamkulam Bus Stop", 80, "Elamkulam Metro Auto Point", 25, ["Vyttila", "Kadavanthra", "MG Road"]),
    "Vyttila": ("Vyttila Mobility Hub", 160, "Vyttila Metro Auto Stand", 35, ["Kakkanad", "Fort Kochi", "Aluva"]),
    "Thykoodam": ("Thykoodam Bus Stop", 85, "Thykoodam Auto Point", 25, ["Vyttila", "Tripunithura", "MG Road"]),
    "Petta": ("Petta Junction Bus Stop", 100, "Petta Metro Auto Stand", 30, ["Vyttila", "Tripunithura", "Fort Kochi"]),
    "SN Junction": ("SN Junction Bus Stop", 65, "SN Junction Auto Point", 20, ["Vyttila", "Tripunithura", "Kakkanad"]),
    "Vadakkekotta": ("Vadakkekotta Bus Stop", 80, "Vadakkekotta Auto Stand", 25, ["Tripunithura", "Vyttila", "Hill Palace"]),
    "Thrippunithura Terminal": ("Thrippunithura Bus Stand", 130, "Thrippunithura Terminal Auto Stand", 40, ["Hill Palace", "Vyttila", "Kakkanad"]),
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

def travel_options(distance):
    fares = fare_options(distance)
    return [
        {"mode": "bus", "label": "Bus", "fare": fares["bus"], "time": round(distance * 4 + 10)},
        {"mode": "auto", "label": "Auto", "fare": fares["auto"], "time": round(distance * 2.5)},
        {"mode": "cab", "label": "Cab", "fare": fares["cab"], "time": round(distance * 2.2)},
    ]

def recommendation(distance, budget):
    fares = fare_options(distance)
    if distance < 1:
        return {"mode": "walk", "fare": 0, "reasoning": "This is under 1 km - a short, zero-cost walk is the best fit.", "fares": fares, "options": travel_options(distance), "time": 12}
    bus_time, auto_time, cab_time = distance * 4 + 10, distance * 2.5, distance * 2.2
    if distance >= 10:
        mode, reason = "bus", "For trips over 10 km, bus is recommended first: it is substantially cheaper than an auto or cab and avoids a long road trip."
    elif distance <= 8:
        mode, reason = "auto", "An auto avoids indirect bus waiting and is the best balance of direct travel time and cost."
    elif budget in ("250_500", "no_limit"):
        mode, reason = "cab", "A cab is preferred here for a faster, tracked, driver-verified trip with more room for comfort."
    else:
        mode, reason = "auto", "An auto gives a direct route while staying closer to your selected budget."
    fastest = min((bus_time, "bus"), (auto_time, "auto"), (cab_time, "cab"))[1]
    return {"mode": mode, "fare": fares[mode], "reasoning": reason, "fares": fares, "options": travel_options(distance), "time": round({"bus":bus_time,"auto":auto_time,"cab":cab_time}.get(mode,12)), "fastest": fastest, "cheapest": "bus"}

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

WEATHER_CACHE = {"at": 0, "data": {"available": False, "message": "Weather unavailable - standard travel advice shown."}}

async def seed_weather():
    if time.time() - WEATHER_CACHE["at"] < 600:
        return WEATHER_CACHE["data"]
    key = os.getenv("OPENWEATHER_API_KEY")
    if not key:
        return WEATHER_CACHE["data"]
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get("https://api.openweathermap.org/data/2.5/weather", params={"lat": 9.9675, "lon": 76.32, "appid": key, "units": "metric"})
            body = response.json()
            condition = body["weather"][0]["main"].lower()
            data = {"available": True, "temperature": round(body["main"]["temp"]), "condition": body["weather"][0]["description"], "rain": condition in ("rain", "drizzle", "thunderstorm")}
            WEATHER_CACHE.update(at=time.time(), data=data)
            return data
    except Exception:
        return WEATHER_CACHE["data"]

def next_departures():
    now = datetime.now()
    minute = now.hour * 60 + now.minute
    intervals = (8, 14, 21)
    return [(now.replace(second=0, microsecond=0).timestamp() + offset * 60) for offset in intervals]

def seeded_passengers():
    rows = [("Anjali", "Hill Palace", "women-only"), ("Riya", "Hill Palace", "women-only"), ("Arun", "Infopark", "any"), ("Vivek", "Infopark", "any"), ("Meera", "Kakkanad", "women-only"), ("Neha", "Kakkanad", "any"), ("Nikhil", "Marine Drive", "quiet"), ("Rahul", "Fort Kochi", "any"), ("Fathima", "Panampilly Nagar", "any"), ("Kevin", "Lulu Mall", "any"), ("Jishnu", "Broadway", "any"), ("Asha", "Ernakulam Junction", "any"), ("Sanjay", "Cochin University", "quiet"), ("Tina", "Mattancherry", "any"), ("Adarsh", "Bolgatty", "any")]
    return [{"id": f"seed-{i}", "name": n, "destination": d, "lat": LANDMARKS[d][0], "lng": LANDMARKS[d][1], "origin_station": "Vyttila", "budget_range": "no_limit", "max_walk_m": 400, "preference": p, "meetup_tag": "Metro gate", "created": time.time()-i*60} for i,(n,d,p) in enumerate(rows)]

PASSENGERS = seeded_passengers()

def build_groups():
    eligible = [p for p in PASSENGERS if p.get("pool_opted_in", True) and road_distance(STATIONS.get(p["origin_station"], STATIONS["Vyttila"]), (p["lat"],p["lng"]), p["destination"]) < 18]
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

def find_pool_offer(passenger, solo_fare):
    if passenger["distance_km"] >= 18 or passenger["preference"] == "quiet":
        return None
    matches = [p for p in PASSENGERS if p["id"] != passenger["id"] and p.get("pool_opted_in", True) and p["origin_station"] == passenger["origin_station"] and p["preference"] == passenger["preference"] and min(p["max_walk_m"], passenger["max_walk_m"]) >= 150 and haversine((p["lat"],p["lng"]), (passenger["lat"],passenger["lng"])) <= .9]
    if not matches:
        return None
    partner = matches[0]
    mode = "cab" if passenger["distance_km"] > 8 else "auto"
    riders = min(4, len(matches) + 1)
    shared = round(fare_options(passenger["distance_km"])[mode] / riders)
    return {"partner_name": partner["name"], "partner_tag": partner.get("meetup_tag") or "Metro gate", "mode": mode, "riders": riders, "shared_fare": shared, "solo_fare": solo_fare, "saving": max(0, solo_fare-shared), "meetup": "Vyttila Metro main exit"}

@app.get("/")
def home(): return FileResponse(ROOT / "static" / "index.html")

@app.get("/health")
def health(): return {"status": "healthy", "service": "LastMile"}

@app.get("/stations")
def stations(): return [{"name": n, "lat": c[0], "lng": c[1]} for n,c in STATIONS.items()]

@app.get("/weather")
async def weather(): return await seed_weather()

@app.get("/bus-stands")
def bus_stands(station: str = "Vyttila"):
    if station not in STATIONS:
        raise HTTPException(400, "Unknown metro station")
    now = datetime.now()
    bus_name, bus_walk, auto_name, auto_walk, routes = STATION_HUBS[station]
    bus = {"name": bus_name, "walk_m": bus_walk, "routes": routes, "frequency": "Check the stop board or conductor for the next bus. Live bus timing is not available here."}
    auto = {"name": auto_name, "walk_m": auto_walk}
    cab = {"name": f"{station} Metro cab pickup", "walk_m": auto_walk + 20}
    return {"station": station, "stands": [bus], "auto_stand": auto, "cab_stand": cab, "updated_at": now.isoformat(), "source": "Transfer points only; this app does not provide live bus timing."}

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
    weather = asyncio.run(seed_weather())
    rec = recommendation(dist, req.budget_range)
    if weather.get("rain") and rec["mode"] == "walk":
        rec.update(mode="auto", fare=fare_options(dist)["auto"], reasoning="Rain: Rain detected - an auto is prioritized over walking for a more comfortable last mile.")
    p = {"id": uuid.uuid4().hex[:8], **req.model_dump(), "distance_km":dist, "created":time.time(), "pool_opted_in":False}
    PASSENGERS.append(p)
    return {"passenger":p, "recommendation":rec, "pooling_available": dist < 18, "pool_offer":find_pool_offer(p, rec["fare"]), "weather": weather}

@app.post("/passengers/{passenger_id}/join-pool")
def join_pool(passenger_id: str):
    passenger = next((p for p in PASSENGERS if p["id"] == passenger_id), None)
    if not passenger: raise HTTPException(404, "Passenger not found")
    passenger["pool_opted_in"] = True
    return {"joined": True, "groups": build_groups(), "message": "Pool request accepted - meet at the Vyttila Metro main exit."}

@app.get("/groups")
def groups(): return {"groups": build_groups(), "updated_at": datetime.now().isoformat()}

@app.get("/stats")
def stats():
    groups = build_groups(); counts = {}
    for p in PASSENGERS: counts[p["destination"]] = counts.get(p["destination"],0)+1
    saved = sum(g["cost_per_member"] * len(g["members"]) * .28 for g in groups)
    return {"total_passengers":len(PASSENGERS), "groups_formed":len(groups), "money_saved":round(saved), "co2_saved":round(sum(len(g["members"])*.18 for g in groups),1), "most_requested":max(counts,key=counts.get)}
