// Input is the TMS quote, or { error } when the TMS could not price the order.
const cfg = $('Load Config').first().json.config;
const ctx = $('Apply Address Validation').item.json;
const quote = typeof $json.total === 'number' ? $json : null;

const reasons = [];
if (ctx.extraction.confidence < cfg.min_confidence) {
  reasons.push(`AI confidence ${ctx.extraction.confidence} is below ${cfg.min_confidence}`);
}
reasons.push(...ctx.issues);
if (!quote) {
  const err = $json.error;
  const raw = String((typeof err === 'string' ? err : err?.message ?? err?.description) ?? '');
  const detail = raw.match(/"error\\?":\s*\\?"([^"\\]+)/)?.[1] ?? raw.replace(/^\d{3} - /, '');
  reasons.push(`TMS could not quote this order${detail ? `: ${detail}` : ''}`);
} else if (quote.total > cfg.max_auto_price) {
  reasons.push(`Quote $${quote.total} is above the $${cfg.max_auto_price} auto-book limit`);
}

const withGeo = (stop, g) => ({
  ...stop,
  formatted_address: g.formatted_address ?? null,
  lat: g.lat ?? null,
  lng: g.lng ?? null,
});

const tms_payload = {
  reference_number: ctx.order.reference_number,
  source: ctx.source,
  external_ref: ctx.intake_id,
  customer: ctx.order.customer,
  service_level: ctx.order.service_level,
  pickup: withGeo(ctx.order.pickup, ctx.geo.pickup),
  dropoff: withGeo(ctx.order.dropoff, ctx.geo.dropoff),
  items: ctx.order.items,
  vehicle_type: ctx.order.vehicle_type ?? quote?.vehicle_type ?? null,
  special_instructions: ctx.order.special_instructions,
  quote_id: quote?.quote_id ?? null,
  price: quote?.total ?? null,
  ai: { method: ctx.extraction.method, model: ctx.extraction.model ?? null, confidence: ctx.extraction.confidence },
};

return {
  json: {
    ...ctx,
    quote,
    needs_review: reasons.length > 0,
    review_reasons: reasons,
    review_expires_at: Math.floor(Date.now() / 1000) + 24 * 3600,
    tms_payload,
  },
};
