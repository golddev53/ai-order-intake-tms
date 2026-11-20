// expected_sig comes from "Verify Signature" (HMAC of shipment_id.exp with REVIEW_SIGNING_SECRET).
const { shipment_id, action, exp, sig } = $json.query ?? {};
const expected = $json.expected_sig ?? '';

let diff = typeof sig === 'string' && sig.length === expected.length ? 0 : 1;
for (let i = 0; !diff && i < expected.length; i++) diff |= expected.charCodeAt(i) ^ sig.charCodeAt(i);

let reason = null;
if (diff) reason = 'This review link is not valid.';
else if (Number(exp) < Date.now() / 1000) reason = 'This review link has expired. Open the order in the TMS instead.';
else if (!['approve', 'reject'].includes(action)) reason = `Unknown action "${action}".`;

return { json: { valid: !reason, reason, shipment_id, action } };
