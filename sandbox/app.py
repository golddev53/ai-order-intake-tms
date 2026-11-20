"""Sandbox services for the AI Order Intake demo.

One FastAPI app that stands in for every external system the n8n workflows call,
so the full pipeline runs locally with no API keys:

  /api/v1/*                     Mock TMS REST API (quotes, shipments, dispatch)
  /maps/api/geocode/json        Google Geocoding API look-alike
  /v1/chat/completions          OpenAI-compatible endpoint with a rule-based extractor
  /mock/slack                   Slack incoming-webhook sink
  /mock/sendgrid/v3/mail/send   SendGrid mail-send sink
  /                             Live dashboard of shipments and outgoing messages

Switch to the real services by changing the base URLs in .env.
"""

import hashlib
import json
import math
import os
import re
import threading
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse

TMS_API_KEY = os.getenv("TMS_API_KEY", "demo-tms-key")

app = FastAPI(title="AI Order Intake - sandbox services")
lock = threading.Lock()
state: dict = {}


def reset_state() -> None:
    state.clear()
    state.update(shipments={}, by_key={}, quotes={}, slack=[], email=[], seq=10000)


reset_state()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def require_auth(authorization: str | None) -> None:
    if authorization != f"Bearer {TMS_API_KEY}":
        raise HTTPException(401, {"error": "invalid_api_key"})


def stable_int(text: str) -> int:
    return int(hashlib.md5(text.lower().encode()).hexdigest(), 16)


# --------------------------------------------------------------------------- TMS

VEHICLES = [  # name, max pallets, max lbs, base fee, per mile
    ("Car", 0, 150, 25.0, 1.6),
    ("9ft Cargo Van", 2, 1500, 45.0, 2.1),
    ("15ft Box Truck", 6, 4000, 95.0, 2.9),
    ("26ft Box Truck", 12, 10000, 160.0, 3.8),
]
REEFER = ("9ft Refrigerator VAN", 2, 1500, 70.0, 2.6)

DRIVERS = [
    {"id": "D-204", "name": "Luis Ortega", "phone": "+14085550111"},
    {"id": "D-219", "name": "Amira Haddad", "phone": "+14085550122"},
    {"id": "D-231", "name": "Kevin Tran", "phone": "+16505550133"},
    {"id": "D-247", "name": "Sofia Petrenko", "phone": "+16505550144"},
]

TRANSITIONS = {
    "draft": {"booked", "cancelled"},
    "booked": {"cancelled"},
    "dispatched": {"cancelled"},
}


def has_coords(stop: dict) -> bool:
    return all(isinstance(stop.get(k), (int, float)) for k in ("lat", "lng"))


def road_miles(a: dict, b: dict) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (a["lat"], a["lng"], b["lat"], b["lng"]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    straight = 3958.8 * 2 * math.asin(math.sqrt(h))
    return max(1.0, round(straight * 1.3, 1))


def pick_vehicle(requested: str | None, pallets: int, weight: float) -> tuple:
    if requested and re.search(r"refrig|reefer", requested, re.I):
        return REEFER
    fitting = [v for v in VEHICLES if pallets <= v[1] and weight <= v[2]]
    named = next((v for v in fitting if requested and v[0].lower() == requested.lower()), None)
    return named or (fitting[0] if fitting else VEHICLES[-1])


@app.post("/api/v1/quotes")
async def create_quote(request: Request, authorization: str | None = Header(None)):
    require_auth(authorization)
    body = await request.json()
    pickup, dropoff = body.get("pickup") or {}, body.get("dropoff") or {}
    if not (has_coords(pickup) and has_coords(dropoff)):
        raise HTTPException(422, {"error": "pickup and dropoff coordinates are required"})

    items = body.get("items") or []
    pallets = sum(int(i.get("quantity") or 0) for i in items if i.get("unit") == "pallet")
    weight = sum(float(i.get("weight_lbs") or 0) for i in items)
    name, _, _, base, per_mile = pick_vehicle(body.get("vehicle_type"), pallets, weight)

    miles = road_miles(pickup, dropoff)
    total = base + per_mile * miles
    surcharge = 0.25 * total if body.get("service_level") == "same_day" else 0.0
    quote = {
        "quote_id": f"Q-{stable_int(json.dumps(body, sort_keys=True)) % 10**6:06d}",
        "currency": "USD",
        "vehicle_type": name,
        "distance_miles": miles,
        "estimated_duration_min": round(miles / 28 * 60 + 30),
        "breakdown": {
            "base": round(base, 2),
            "mileage": round(per_mile * miles, 2),
            "same_day_surcharge": round(surcharge, 2),
        },
        "total": round(total + surcharge, 2),
        "valid_until": iso(utcnow() + timedelta(hours=24)),
    }
    state["quotes"][quote["quote_id"]] = quote
    return quote


@app.get("/api/v1/shipments")
def list_shipments(
    idempotency_key: str | None = None,
    reference_number: str | None = None,
    authorization: str | None = Header(None),
):
    require_auth(authorization)
    rows = list(state["shipments"].values())
    if idempotency_key:
        rows = [s for s in rows if s["idempotency_key"] == idempotency_key]
    if reference_number:
        rows = [s for s in rows if s.get("reference_number") == reference_number]
    return {"data": rows, "count": len(rows)}


@app.post("/api/v1/shipments")
async def create_shipment(
    request: Request,
    response: Response,
    authorization: str | None = Header(None),
    idempotency_key: str | None = Header(None),
):
    require_auth(authorization)
    if not idempotency_key:
        raise HTTPException(400, {"error": "Idempotency-Key header is required"})
    body = await request.json()
    status = body.get("status", "booked")
    if status not in ("draft", "booked"):
        raise HTTPException(422, {"error": "status must be draft or booked"})

    with lock:
        existing_id = state["by_key"].get(idempotency_key)
        if existing_id:
            response.status_code = 200
            return {**state["shipments"][existing_id], "idempotent_replay": True}

        state["seq"] += 1
        shipment_id = f"SHP-{state['seq']}"
        shipment = {
            **body,
            "id": shipment_id,
            "status": status,
            "idempotency_key": idempotency_key,
            "created_at": iso(utcnow()),
            "route": None,
            "events": [{"at": iso(utcnow()), "status": status, "note": body.get("note")}],
        }
        state["shipments"][shipment_id] = shipment
        state["by_key"][idempotency_key] = shipment_id

    response.status_code = 201
    return shipment


def get_or_404(shipment_id: str) -> dict:
    shipment = state["shipments"].get(shipment_id)
    if not shipment:
        raise HTTPException(404, {"error": f"shipment {shipment_id} not found"})
    return shipment


@app.get("/api/v1/shipments/{shipment_id}")
def get_shipment(shipment_id: str, authorization: str | None = Header(None)):
    require_auth(authorization)
    return get_or_404(shipment_id)


@app.patch("/api/v1/shipments/{shipment_id}")
async def update_shipment(shipment_id: str, request: Request, authorization: str | None = Header(None)):
    require_auth(authorization)
    body = await request.json()
    with lock:
        shipment = get_or_404(shipment_id)
        new_status = body.get("status")
        if new_status and new_status != shipment["status"]:
            if new_status not in TRANSITIONS.get(shipment["status"], set()):
                raise HTTPException(409, {"error": f"cannot move {shipment['status']} -> {new_status}"})
            shipment["status"] = new_status
            shipment["events"].append({"at": iso(utcnow()), "status": new_status, "note": body.get("note")})
    return shipment


@app.post("/api/v1/shipments/{shipment_id}/dispatch")
def dispatch_shipment(shipment_id: str, authorization: str | None = Header(None)):
    require_auth(authorization)
    with lock:
        shipment = get_or_404(shipment_id)
        if shipment["status"] == "dispatched":
            return shipment
        if shipment["status"] != "booked":
            raise HTTPException(409, {"error": f"only booked shipments can be dispatched (is {shipment['status']})"})

        pickup, dropoff = shipment.get("pickup") or {}, shipment.get("dropoff") or {}
        pickup_eta = pickup.get("window_start") or iso(utcnow() + timedelta(minutes=45))
        minutes = 60
        if has_coords(pickup) and has_coords(dropoff):
            minutes = round(road_miles(pickup, dropoff) / 28 * 60 + 20)
        try:
            delivery_eta = (datetime.fromisoformat(pickup_eta.replace("Z", "")) + timedelta(minutes=minutes)).isoformat(timespec="minutes")
        except ValueError:
            delivery_eta = None

        shipment["route"] = {
            "id": f"RTE-{stable_int(shipment_id) % 9000 + 1000}",
            "driver": DRIVERS[stable_int(shipment_id) % len(DRIVERS)],
            "pickup_eta": pickup_eta,
            "eta": delivery_eta,
            "tracking_url": f"https://track.example.com/{shipment_id}",
        }
        shipment["status"] = "dispatched"
        shipment["events"].append({"at": iso(utcnow()), "status": "dispatched", "note": shipment["route"]["id"]})
    return shipment


# ---------------------------------------------------------------- Google Geocoding


@app.get("/maps/api/geocode/json")
def geocode(address: str = "", key: str | None = None, components: str | None = None):
    text = address.strip()
    if not text or re.search(r"\b(unknown|tbd|n/a)\b", text, re.I):
        return {"status": "ZERO_RESULTS", "results": []}

    h = stable_int(text)
    precise = bool(re.match(r"^\d+\s", text)) and bool(re.search(r"\b\d{5}\b", text))
    result = {
        "formatted_address": f"{text}, USA",
        "geometry": {
            "location": {
                "lat": round(37.25 + (h % 1000) / 1000 * 0.6, 6),
                "lng": round(-122.45 + (h // 1000 % 1000) / 1000 * 0.6, 6),
            },
            "location_type": "ROOFTOP" if precise else "APPROXIMATE",
        },
        "place_id": f"mock_{h % 10**10}",
        "types": ["street_address"] if precise else ["locality", "political"],
    }
    if not precise:
        result["partial_match"] = True
    return {"status": "OK", "results": [result]}


# ------------------------------------------------- OpenAI-compatible extractor

UNITS = {"pallet": "pallet", "skid": "pallet", "box": "box", "carton": "box", "case": "box", "piece": "piece", "pc": "piece"}


def parse_address(text: str | None) -> dict:
    out = {"name": None, "street": None, "city": None, "state": None, "zip": None}
    if not text:
        return out
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if parts and not re.match(r"^\d", parts[0]):
        out["name"] = parts.pop(0)
    if parts and re.match(r"^\d", parts[0]):
        out["street"] = parts.pop(0)
    match = re.match(r"^([A-Za-z]{2})\s*(\d{5})?$", parts[-1]) if parts else None
    if match:
        out["state"], out["zip"] = match.group(1).upper(), match.group(2)
        parts.pop()
    if parts:
        out["city"] = parts[-1]
    return out


def parse_window(text: str | None) -> tuple[str | None, str | None]:
    if not text:
        return None, None
    m = re.search(r"(\d{4}-\d{2}-\d{2})[ T](\d{1,2}:\d{2})(?:\s*(?:-|to|–)\s*(\d{1,2}:\d{2}))?", text)
    if not m:
        return None, None
    day, start, end = m.groups()
    return f"{day}T{start.zfill(5)}", (f"{day}T{end.zfill(5)}" if end else None)


def field(text: str, pattern: str) -> str | None:
    m = re.search(rf"^\s*(?:{pattern})\s*:\s*(.+)$", text, re.I | re.M)
    return m.group(1).strip() if m else None


def rule_based_extract(prompt: str) -> dict:
    sender = field(prompt, "from")
    body = prompt.split("\n\n", 1)[-1]

    pickup = parse_address(field(body, r"pick[- ]?up(?: from| address| location)?"))
    dropoff = parse_address(field(body, r"deliver(?:y)? to|delivery address|drop[- ]?off|ship to|consignee"))
    pickup["window_start"], pickup["window_end"] = parse_window(field(body, r"pick[- ]?up (?:window|time)"))
    dropoff["window_start"], dropoff["window_end"] = parse_window(field(body, r"deliver(?:y)? (?:by|window|before)"))
    if dropoff["window_start"] and not dropoff["window_end"]:
        dropoff["window_start"], dropoff["window_end"] = None, dropoff["window_start"]
    notes = field(body, r"notes?|special instructions|instructions")
    pickup["instructions"] = dropoff["instructions"] = None

    items = []
    items_text = field(body, r"items?|freight|cargo|load") or body
    qty = re.search(r"(\d+)\s*(pallet|skid|box|carton|case|piece|pc)s?", items_text, re.I)
    weight = re.search(r"(\d[\d,]*)\s*(lbs?|pounds|kg)\b", items_text, re.I)
    if qty or field(body, r"items?|freight|cargo|load"):
        lbs = None
        if weight:
            lbs = float(weight.group(1).replace(",", ""))
            lbs = round(lbs * 2.2046, 1) if weight.group(2).lower() == "kg" else lbs
        items.append({
            "description": field(body, r"items?|freight|cargo|load") or "Freight",
            "quantity": int(qty.group(1)) if qty else None,
            "unit": UNITS.get(qty.group(2).lower(), "other") if qty else "other",
            "weight_lbs": lbs,
        })

    contact = field(body, r"contact") or ""
    phone = re.search(r"\(?\d{3}\)?[\s.-]*\d{3}[\s.-]*\d{4}", contact or body)
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", contact) or (re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", sender) if sender else None)
    ref = re.search(r"\b(PO|P\.O\.|Ref(?:erence)?|Order)\s*(?:#|No\.?)?\s*:?\s*((?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{2,})", prompt, re.I)
    lowered = body.lower()

    vehicle = None
    if re.search(r"refrigerat|reefer|cold chain", lowered):
        vehicle = "9ft Refrigerator VAN"
    elif m := re.search(r"(26|17|15|10)\s?ft box truck", lowered):
        vehicle = f"{m.group(1)}ft Box Truck"
    elif "cargo van" in lowered:
        vehicle = "9ft Cargo Van"

    order = {
        "customer": {
            "company": pickup["name"],
            "contact_name": contact.split(",")[0].strip() or None,
            "email": email.group(0) if email else None,
            "phone": phone.group(0) if phone else None,
        },
        "reference_number": f"{ref.group(1).upper().replace('.', '')}-{ref.group(2)}" if ref else None,
        "service_level": "same_day" if re.search(r"same[- ]day|asap|urgent|today", lowered)
        else "recurring" if re.search(r"\bevery (?:mon|tue|wed|thu|fri|day|week)|weekly|recurring", lowered)
        else "scheduled",
        "pickup": pickup,
        "dropoff": dropoff,
        "items": items,
        "vehicle_type": vehicle,
        "special_instructions": notes,
    }

    checks = {
        "pickup.street": pickup["street"], "pickup.city": pickup["city"], "pickup.state": pickup["state"],
        "pickup.zip": pickup["zip"], "pickup.window_start": pickup["window_start"],
        "dropoff.street": dropoff["street"], "dropoff.city": dropoff["city"], "dropoff.state": dropoff["state"],
        "dropoff.zip": dropoff["zip"], "items.quantity": items and items[0]["quantity"],
    }
    missing = [k for k, v in checks.items() if not v]
    order["confidence"] = round(1 - len(missing) / len(checks), 2)
    order["missing_fields"] = missing
    return order


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    prompt = next((m["content"] for m in reversed(body.get("messages", [])) if m.get("role") == "user"), "")
    content = json.dumps(rule_based_extract(prompt))
    return {
        "id": f"chatcmpl-sandbox-{stable_int(prompt) % 10**8}",
        "object": "chat.completion",
        "created": int(utcnow().timestamp()),
        "model": f"{body.get('model', 'sandbox')} (sandbox rule-based)",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": len(prompt) // 4, "completion_tokens": len(content) // 4, "total_tokens": (len(prompt) + len(content)) // 4},
    }


# ------------------------------------------------------------ Slack / SendGrid


@app.post("/mock/slack")
async def slack_webhook(request: Request):
    state["slack"].append({"at": iso(utcnow()), "payload": await request.json()})
    return PlainTextResponse("ok")


@app.post("/mock/sendgrid/v3/mail/send")
async def sendgrid_send(request: Request):
    state["email"].append({"at": iso(utcnow()), "payload": await request.json()})
    return Response(status_code=202)


@app.get("/mock/state")
def mock_state():
    shipments = sorted(state["shipments"].values(), key=lambda s: s["id"], reverse=True)
    return {"shipments": shipments, "slack": state["slack"][::-1], "email": state["email"][::-1]}


@app.post("/mock/reset")
def mock_reset():
    with lock:
        reset_state()
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def dashboard():
    with open(os.path.join(os.path.dirname(__file__), "dashboard.html"), encoding="utf-8") as f:
        return f.read()
