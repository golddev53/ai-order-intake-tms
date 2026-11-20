"""Builds the importable n8n workflow files in ../workflows from the code in ./code.

Code node JavaScript lives in ./code/*.js so it can be read, diffed and linted like
normal source. Run `python n8n/build.py` after editing, then re-import the JSON.
"""

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE_DIR = ROOT / "n8n" / "code"
OUT_DIR = ROOT / "workflows"

INTAKE_ID = "aiIntakeMain0001"
REVIEW_ID = "aiIntakeReview01"
ALERTS_ID = "aiIntakeAlerts01"

TMS_AUTH = [("Authorization", "=Bearer {{ $env.TMS_API_KEY }}")]
RETRY = {"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 2000}


def order_schema() -> dict:
    schema = json.loads((ROOT / "schema" / "order.schema.json").read_text(encoding="utf-8"))
    for key in ("$schema", "title", "description"):
        schema.pop(key, None)
    return schema


def read_code(name: str, **replacements: str) -> str:
    code = (CODE_DIR / f"{name}.js").read_text(encoding="utf-8")
    for placeholder, value in replacements.items():
        code = code.replace(placeholder, value)
    return code


class Workflow:
    def __init__(self, wf_id: str, name: str, **settings):
        self.id, self.name = wf_id, name
        self.nodes: list[dict] = []
        self.connections: dict = {}
        self.settings = {"executionOrder": "v1", "saveManualExecutions": True, **settings}

    def node(self, name, node_type, version, params, pos, **extra) -> str:
        self.nodes.append({
            "parameters": params,
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.id}/{name}")),
            "name": name,
            "type": node_type,
            "typeVersion": version,
            "position": list(pos),
            **extra,
        })
        return name

    def connect(self, src: str, dst: str, output: int = 0) -> None:
        outputs = self.connections.setdefault(src, {"main": []})["main"]
        while len(outputs) <= output:
            outputs.append([])
        outputs[output].append({"node": dst, "type": "main", "index": 0})

    def chain(self, *names: str) -> None:
        for src, dst in zip(names, names[1:]):
            self.connect(src, dst)

    # ---- node helpers -------------------------------------------------------

    def code(self, name, file, pos, each=False, **replacements):
        params = {"jsCode": read_code(file, **replacements)}
        if each:
            params["mode"] = "runOnceForEachItem"
        return self.node(name, "n8n-nodes-base.code", 2, params, pos)

    def http(self, name, method, url, pos, query=None, headers=None, body=None, timeout=20000, retry=True, **extra):
        params = {"method": method, "url": url}
        if query:
            params["sendQuery"] = True
            params["queryParameters"] = {"parameters": [{"name": k, "value": v} for k, v in query]}
        if headers:
            params["sendHeaders"] = True
            params["headerParameters"] = {"parameters": [{"name": k, "value": v} for k, v in headers]}
        if body:
            params.update(sendBody=True, specifyBody="json", jsonBody=body)
        params["options"] = {"timeout": timeout}
        return self.node(name, "n8n-nodes-base.httpRequest", 4.2, params, pos, **(RETRY if retry else {}), **extra)

    def if_true(self, name, expression, pos):
        params = {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                "conditions": [{
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.id}/{name}/cond")),
                    "leftValue": expression,
                    "rightValue": "",
                    "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                }],
                "combinator": "and",
            },
            "options": {},
        }
        return self.node(name, "n8n-nodes-base.if", 2, params, pos)

    def hmac(self, name, value, prop, pos):
        params = {
            "action": "hmac",
            "type": "SHA256",
            "value": value,
            "dataPropertyName": prop,
            "secret": "={{ $env.REVIEW_SIGNING_SECRET }}",
            "encoding": "hex",
        }
        return self.node(name, "n8n-nodes-base.crypto", 1, params, pos)

    def webhook(self, name, path, method, pos, response_mode):
        params = {"httpMethod": method, "path": path, "responseMode": response_mode, "options": {}}
        if response_mode == "lastNode":
            params["responseData"] = "firstEntryJson"
        return self.node(name, "n8n-nodes-base.webhook", 2, params, pos,
                         webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.id}/{path}")))

    def note(self, title, text, pos, width, height, color=7):
        self.node(title, "n8n-nodes-base.stickyNote", 1,
                  {"content": f"## {title}\n{text}", "width": width, "height": height, "color": color}, pos)

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "nodes": self.nodes,
            "connections": self.connections,
            "settings": self.settings,
            "active": False,
            "pinData": {},
            "tags": [],
        }


def slack_post(wf, name, body, pos):
    return wf.http(name, "POST", "={{ $env.SLACK_WEBHOOK_URL }}", pos, body=body)


def send_confirmation(wf, name, pos):
    body = ("={{ JSON.stringify({ ...$json.email, from: { email: $env.FROM_EMAIL || 'dispatch@example.com', "
            "name: $env.FROM_NAME || 'Dispatch' } }) }}")
    return wf.http(name, "POST", "={{ $env.SENDGRID_BASE_URL || 'https://api.sendgrid.com' }}/v3/mail/send", pos,
                   headers=[("Authorization", "=Bearer {{ $env.SENDGRID_API_KEY }}")], body=body)


# --------------------------------------------------------------------------- intake


def build_intake() -> Workflow:
    wf = Workflow(INTAKE_ID, "AI Order Intake -> TMS", errorWorkflow=ALERTS_ID)

    wf.note("1. Intake", "Every channel is normalized into one envelope. Enable the email, Shopify and Drive triggers after adding their credentials.", (-60, -160), 900, 940, 7)
    wf.note("2. AI extraction", "Unstructured text goes to the LLM, which must answer with the strict LogisticsOrder JSON schema and a confidence score.", (1060, -160), 920, 400, 6)
    wf.note("3. Validate & enrich", "Clean fields, build the idempotency key, verify both addresses with Google Maps.", (1920, 140), 1100, 340, 4)
    wf.note("4. Dedupe & quote", "Skip orders already in the TMS, then get a price and vehicle from the TMS.", (3040, 40), 640, 520, 3)
    wf.note("5. Book or review", "Clean orders are booked, dispatched and confirmed. Anything uncertain becomes a draft and goes to Slack for approval.", (3700, 100), 1520, 640, 5)

    webhook = wf.webhook("Webhook: Order Intake", "order-intake", "POST", (0, 0), "lastNode")
    email = wf.node("Email: Orders Inbox", "n8n-nodes-base.emailReadImap", 2, {"format": "resolved", "options": {}}, (0, 200), disabled=True)
    shopify = wf.node("Shopify: Order Created", "n8n-nodes-base.shopifyTrigger", 1, {"topic": "orders/create"}, (0, 400), disabled=True)
    drive = wf.node("Drive: New CSV in Folder", "n8n-nodes-base.googleDriveTrigger", 1, {
        "pollTimes": {"item": [{"mode": "everyMinute"}]},
        "triggerOn": "specificFolder",
        "folderToWatch": {"__rl": True, "value": "", "mode": "list"},
        "event": "fileCreated",
        "options": {},
    }, (0, 600), disabled=True)

    pdf = wf.node("Extract PDF Attachment", "n8n-nodes-base.extractFromFile", 1,
                  {"operation": "pdf", "binaryPropertyName": "attachment_0", "options": {}}, (220, 200),
                  onError="continueRegularOutput")
    download = wf.node("Drive: Download CSV", "n8n-nodes-base.googleDrive", 3, {
        "operation": "download",
        "fileId": {"__rl": True, "value": "={{ $json.id }}", "mode": "id"},
        "options": {},
    }, (220, 600))
    parse_csv = wf.node("Parse CSV Rows", "n8n-nodes-base.extractFromFile", 1, {"operation": "csv", "options": {}}, (440, 600))

    n_webhook = wf.code("Normalize: Webhook", "normalize-webhook", (660, 0))
    n_email = wf.code("Normalize: Email", "normalize-email", (660, 200))
    n_shopify = wf.code("Normalize: Shopify", "normalize-shopify", (660, 400))
    n_csv = wf.code("Normalize: CSV", "normalize-csv", (660, 600))

    config_expr = """={{ {
  openai_model: $env.OPENAI_MODEL || 'gpt-4o-mini',
  timezone: $env.GENERIC_TIMEZONE || 'America/Los_Angeles',
  min_confidence: Number($env.AUTO_APPROVE_MIN_CONFIDENCE || 0.85),
  max_auto_price: Number($env.AUTO_APPROVE_MAX_PRICE || 1500),
  public_url: ($env.N8N_WEBHOOK_URL || $env.WEBHOOK_URL || 'http://localhost:5678/').replace(/\\/+$/, ''),
  tms_ui_url: ($env.TMS_UI_URL || $env.TMS_BASE_URL || '').replace(/\\/+$/, ''),
  default_pickup: {
    name: $env.DEFAULT_PICKUP_NAME || 'Main Warehouse',
    street: $env.DEFAULT_PICKUP_STREET || null,
    city: $env.DEFAULT_PICKUP_CITY || null,
    state: $env.DEFAULT_PICKUP_STATE || null,
    zip: $env.DEFAULT_PICKUP_ZIP || null
  }
} }}"""
    config = wf.node("Load Config", "n8n-nodes-base.set", 3.4, {
        "mode": "manual",
        "includeOtherFields": True,
        "assignments": {"assignments": [{
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{INTAKE_ID}/config")),
            "name": "config",
            "value": config_expr,
            "type": "object",
        }]},
        "options": {},
    }, (880, 300))

    needs_ai = wf.if_true("Needs AI Extraction?", "={{ !$json.order }}", (1100, 300))
    build_ai = wf.code("Build AI Request", "build-ai-request", (1320, 0), each=True,
                       __ORDER_SCHEMA__=json.dumps(order_schema(), indent=2))
    call_ai = wf.http("AI: Extract Order", "POST", "={{ $env.OPENAI_BASE_URL || 'https://api.openai.com/v1' }}/chat/completions",
                      (1540, 0), headers=[("Authorization", "=Bearer {{ $env.OPENAI_API_KEY }}")],
                      body="={{ JSON.stringify($json.ai_request) }}", timeout=60000)
    parse_ai = wf.code("Parse AI Output", "parse-ai-output", (1760, 0), each=True)

    validate = wf.code("Validate & Normalize Order", "validate-order", (1980, 300))
    idem = wf.node("Idempotency Key", "n8n-nodes-base.crypto", 1, {
        "type": "SHA256", "value": "={{ $json.key_source }}", "dataPropertyName": "idempotency_key", "encoding": "hex",
    }, (2200, 300))

    maps_url = "={{ $env.GOOGLE_MAPS_BASE_URL || 'https://maps.googleapis.com' }}/maps/api/geocode/json"
    addr = "[{0}.street, {0}.city, {0}.state, {0}.zip].filter(Boolean).join(', ')"
    geo_pickup = wf.http("Maps: Geocode Pickup", "GET", maps_url, (2420, 300), query=[
        ("address", "={{ " + addr.format("$json.order.pickup") + " }}"),
        ("components", "country:US"),
        ("key", "={{ $env.GOOGLE_MAPS_API_KEY }}"),
    ])
    geo_dropoff = wf.http("Maps: Geocode Dropoff", "GET", maps_url, (2640, 300), query=[
        ("address", "={{ " + addr.format("$('Idempotency Key').item.json.order.dropoff") + " }}"),
        ("components", "country:US"),
        ("key", "={{ $env.GOOGLE_MAPS_API_KEY }}"),
    ])
    apply_geo = wf.code("Apply Address Validation", "apply-address-validation", (2860, 300), each=True)

    tms = "={{ $env.TMS_BASE_URL }}/api/v1"
    find = wf.http("TMS: Find Existing Shipment", "GET", f"{tms}/shipments", (3080, 300), headers=TMS_AUTH,
                   query=[("idempotency_key", "={{ $json.idempotency_key }}")])
    is_dup = wf.if_true("Already in TMS?", "={{ ($json.data ?? []).length > 0 }}", (3300, 300))
    dup = wf.code("Result: Duplicate", "result-duplicate", (3520, 140), each=True)
    quote = wf.http("TMS: Get Quote", "POST", f"{tms}/quotes", (3520, 420), headers=TMS_AUTH,
                    body="={{ JSON.stringify($('Apply Address Validation').item.json.quote_request) }}",
                    retry=False, onError="continueRegularOutput")
    decide = wf.code("Decide: Auto-book or Review", "decide-routing", (3740, 420), each=True)
    needs_review = wf.if_true("Needs Human Review?", "={{ $json.needs_review }}", (3960, 420))

    idem_header = [*TMS_AUTH, ("Idempotency-Key", "={{ $json.idempotency_key }}")]
    create = wf.http("TMS: Create Shipment", "POST", f"{tms}/shipments", (4180, 280), headers=idem_header,
                     body="={{ JSON.stringify({ ...$json.tms_payload, status: 'booked', note: 'Auto-booked by AI order intake' }) }}")
    dispatch = wf.http("TMS: Dispatch to Route", "POST", f"{tms}/shipments/{{{{ $json.id }}}}/dispatch", (4400, 280), headers=TMS_AUTH)
    compose = wf.code("Compose Confirmation", "compose-confirmation", (4620, 280), each=True)
    send = send_confirmation(wf, "Email: Customer Confirmation", (4840, 280))
    booked = wf.code("Result: Booked", "result-booked", (5060, 280), each=True)

    draft = wf.http("TMS: Create Draft Shipment", "POST", f"{tms}/shipments", (4180, 560), headers=idem_header,
                    body="={{ JSON.stringify({ ...$json.tms_payload, status: 'draft', note: 'Held for review: ' + $json.review_reasons.join('; ') }) }}")
    sign = wf.hmac("Sign Review Link", "={{ $json.id + '.' + $('Decide: Auto-book or Review').item.json.review_expires_at }}",
                   "review_sig", (4400, 560))
    compose_review = wf.code("Compose Review Request", "compose-review-request", (4620, 560), each=True)
    slack = slack_post(wf, "Slack: Request Review", "={{ JSON.stringify($json.slack) }}", (4840, 560))
    review = wf.code("Result: Needs Review", "result-needs-review", (5060, 560), each=True)

    wf.connect(webhook, n_webhook)
    wf.chain(email, pdf, n_email)
    wf.connect(shopify, n_shopify)
    wf.chain(drive, download, parse_csv, n_csv)
    for normalizer in (n_webhook, n_email, n_shopify, n_csv):
        wf.connect(normalizer, config)
    wf.connect(config, needs_ai)
    wf.connect(needs_ai, build_ai, 0)
    wf.connect(needs_ai, validate, 1)
    wf.chain(build_ai, call_ai, parse_ai, validate)
    wf.chain(validate, idem, geo_pickup, geo_dropoff, apply_geo, find, is_dup)
    wf.connect(is_dup, dup, 0)
    wf.connect(is_dup, quote, 1)
    wf.chain(quote, decide, needs_review)
    wf.connect(needs_review, draft, 0)
    wf.connect(needs_review, create, 1)
    wf.chain(create, dispatch, compose, send, booked)
    wf.chain(draft, sign, compose_review, slack, review)
    return wf


# --------------------------------------------------------------------------- review


RESULT_PAGE = """=<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ $json.title }}</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b1020;font:16px/1.6 system-ui,sans-serif;color:#e6ebf5}
.card{max-width:520px;margin:24px;padding:32px;border-radius:16px;background:#131c33;border:1px solid rgba(148,163,184,.2);border-top:4px solid #22d3ee}
.good{border-top-color:#34d399}.bad{border-top-color:#f87171}
h1{margin:0 0 8px;font-size:22px}p{margin:0;color:#94a3b8}
</style></head>
<body><div class="card {{ $json.tone }}"><h1>{{ $json.title }}</h1><p>{{ $json.message }}</p></div></body></html>"""


def build_review() -> Workflow:
    wf = Workflow(REVIEW_ID, "AI Order Intake - Slack Review Actions", errorWorkflow=ALERTS_ID)
    wf.note("Review links", "Approve / Reject buttons in Slack open this webhook. Links are HMAC-signed and expire after 24 hours.", (-60, -140), 760, 320, 6)

    hook = wf.webhook("Webhook: Review Action", "order-review", "GET", (0, 0), "responseNode")
    verify = wf.hmac("Verify Signature", "={{ ($json.query.shipment_id ?? '') + '.' + ($json.query.exp ?? '') }}", "expected_sig", (220, 0))
    check = wf.code("Check Link", "check-review-link", (440, 0), each=True)
    valid = wf.if_true("Link Valid?", "={{ $json.valid }}", (660, 0))

    tms = "={{ $env.TMS_BASE_URL }}/api/v1"
    get = wf.http("TMS: Get Shipment", "GET", f"{tms}/shipments/{{{{ $json.shipment_id }}}}", (880, -120), headers=TMS_AUTH)
    is_draft = wf.if_true("Still a Draft?", "={{ $json.status === 'draft' }}", (1100, -120))
    approve = wf.if_true("Approve?", "={{ $('Check Link').item.json.action === 'approve' }}", (1320, -240))

    book = wf.http("TMS: Book Shipment", "PATCH", f"{tms}/shipments/{{{{ $json.id }}}}", (1540, -360), headers=TMS_AUTH,
                   body="={{ JSON.stringify({ status: 'booked', note: 'Approved in Slack' }) }}")
    dispatch = wf.http("TMS: Dispatch Approved", "POST", f"{tms}/shipments/{{{{ $json.id }}}}/dispatch", (1760, -360), headers=TMS_AUTH)
    compose = wf.code("Compose Confirmation", "compose-confirmation", (1980, -360), each=True)
    send = send_confirmation(wf, "Email: Customer Confirmation", (2200, -360))
    slack_ok = slack_post(wf, "Slack: Approved Notice", (
        "={{ JSON.stringify({ text: ((s) => `:white_check_mark: ${s.id} approved and dispatched on ${s.route.id} "
        "(${s.route.driver.name}), pickup ETA ${s.route.pickup_eta}`)($('TMS: Dispatch Approved').item.json) }) }}"), (2420, -360))
    page_ok = wf.code("Page: Approved", "outcome-pages", (2640, -360), each=True, __OUTCOME__="approved")

    cancel = wf.http("TMS: Cancel Shipment", "PATCH", f"{tms}/shipments/{{{{ $json.id }}}}", (1540, -120), headers=TMS_AUTH,
                     body="={{ JSON.stringify({ status: 'cancelled', note: 'Rejected in Slack' }) }}")
    slack_no = slack_post(wf, "Slack: Rejected Notice",
                          "={{ JSON.stringify({ text: `:x: ${$json.id} was rejected and cancelled in the TMS` }) }}", (1760, -120))
    page_no = wf.code("Page: Rejected", "outcome-pages", (1980, -120), each=True, __OUTCOME__="rejected")

    page_handled = wf.code("Page: Already Handled", "outcome-pages", (1320, 40), each=True, __OUTCOME__="handled")
    page_invalid = wf.code("Page: Invalid Link", "outcome-pages", (880, 160), each=True, __OUTCOME__="invalid")

    respond = wf.node("Respond: Result Page", "n8n-nodes-base.respondToWebhook", 1.1, {
        "respondWith": "text",
        "responseBody": RESULT_PAGE,
        "options": {
            "responseCode": "={{ $json.http_status }}",
            "responseHeaders": {"entries": [{"name": "Content-Type", "value": "text/html; charset=utf-8"}]},
        },
    }, (2860, 0))

    wf.chain(hook, verify, check, valid)
    wf.connect(valid, get, 0)
    wf.connect(valid, page_invalid, 1)
    wf.connect(get, is_draft)
    wf.connect(is_draft, approve, 0)
    wf.connect(is_draft, page_handled, 1)
    wf.connect(approve, book, 0)
    wf.connect(approve, cancel, 1)
    wf.chain(book, dispatch, compose, send, slack_ok, page_ok)
    wf.chain(cancel, slack_no, page_no)
    for page in (page_ok, page_no, page_handled, page_invalid):
        wf.connect(page, respond)
    return wf


# --------------------------------------------------------------------------- alerts


def build_alerts() -> Workflow:
    wf = Workflow(ALERTS_ID, "AI Order Intake - Error Alerts")
    trigger = wf.node("On Workflow Error", "n8n-nodes-base.errorTrigger", 1, {}, (0, 0))
    compose = wf.code("Compose Alert", "compose-alert", (220, 0), each=True)
    slack = slack_post(wf, "Slack: Alert Ops", "={{ JSON.stringify($json.slack) }}", (440, 0))
    wf.chain(trigger, compose, slack)
    return wf


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    for filename, wf in (
        ("01-order-intake.json", build_intake()),
        ("02-slack-review-actions.json", build_review()),
        ("03-error-alerts.json", build_alerts()),
    ):
        path = OUT_DIR / filename
        path.write_text(json.dumps(wf.to_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)} ({len(wf.nodes)} nodes)")


if __name__ == "__main__":
    main()
