const cfg = $('Load Config').first().json.config;

const clean = (v) => (typeof v === 'string' ? v.trim().replace(/\s+/g, ' ') || null : v ?? null);

const phone = (p) => {
  const d = String(p ?? '').replace(/\D/g, '');
  if (d.length === 10) return `+1${d}`;
  if (d.length === 11 && d.startsWith('1')) return `+${d}`;
  return null;
};

const time = (t) => {
  const m = String(t ?? '').match(/^(\d{4}-\d{2}-\d{2})[T ](\d{1,2}):(\d{2})/);
  return m ? `${m[1]}T${m[2].padStart(2, '0')}:${m[3]}` : null;
};

const stop = (s = {}) => ({
  name: clean(s.name),
  street: clean(s.street),
  city: clean(s.city),
  state: clean(s.state)?.toUpperCase().slice(0, 2) ?? null,
  zip: String(s.zip ?? '').match(/\d{5}/)?.[0] ?? null,
  window_start: time(s.window_start),
  window_end: time(s.window_end),
  instructions: clean(s.instructions),
});

const today = new Date().toISOString().slice(0, 10);
const tomorrow = new Date(Date.now() + 864e5).toISOString().slice(0, 10);

return $input.all().map(({ json: input }) => {
  const src = input.order ?? {};
  const issues = [];

  // Store orders have no pickup: they ship from the default warehouse during opening hours.
  const pickup = src.pickup
    ? stop(src.pickup)
    : stop({ ...cfg.default_pickup, window_start: `${tomorrow}T09:00`, window_end: `${tomorrow}T17:00` });
  const dropoff = stop(src.dropoff ?? {});

  const customer = {
    company: clean(src.customer?.company),
    contact_name: clean(src.customer?.contact_name),
    email: clean(src.customer?.email ?? input.sender_email)?.toLowerCase() ?? null,
    phone: phone(src.customer?.phone),
  };

  const items = (Array.isArray(src.items) ? src.items : []).map((it) => ({
    description: clean(it.description) ?? 'Freight',
    quantity: parseInt(it.quantity, 10) || null,
    unit: ['pallet', 'box', 'piece', 'other'].includes(it.unit) ? it.unit : 'other',
    weight_lbs: Number(it.weight_lbs) || null,
  }));

  const order = {
    customer,
    reference_number: clean(src.reference_number),
    service_level: ['same_day', 'scheduled', 'recurring'].includes(src.service_level) ? src.service_level : 'scheduled',
    pickup,
    dropoff,
    items,
    vehicle_type: clean(src.vehicle_type),
    special_instructions: clean(src.special_instructions),
  };

  for (const [side, s] of [['pickup', pickup], ['dropoff', dropoff]]) {
    const missing = ['street', 'city', 'state', 'zip'].filter((f) => !s[f]);
    if (missing.length) issues.push(`Missing ${side} ${missing.join(', ')}`);
  }
  if (!pickup.window_start) issues.push('Missing pickup date/time');
  else if (pickup.window_start.slice(0, 10) < today) issues.push(`Pickup date ${pickup.window_start.slice(0, 10)} is in the past`);
  if (pickup.window_start && pickup.window_end && pickup.window_end < pickup.window_start) issues.push('Pickup window ends before it starts');
  if (pickup.window_start && dropoff.window_end && dropoff.window_end < pickup.window_start) issues.push('Delivery deadline is before pickup');
  if (!items.length || items.every((i) => !i.quantity)) issues.push('Missing item quantity');
  if (!customer.email) issues.push('No customer email for the confirmation');

  // Same customer + reference + route + day = same order, even if it arrives twice by different channels.
  // Without both streets and a date that key would collide across unrelated orders, so fall back to the content.
  const hasRoute = pickup.street && dropoff.street && pickup.window_start;
  const key_source = (hasRoute
    ? [
        customer.email ?? customer.company ?? '',
        order.reference_number ?? '',
        pickup.street, pickup.zip ?? '',
        dropoff.street, dropoff.zip ?? '',
        pickup.window_start.slice(0, 10),
      ]
    : ['content', input.sender_email ?? '', (input.raw_text ?? JSON.stringify(src)).replace(/\s+/g, ' ')]
  ).join('|').toLowerCase();

  return {
    json: {
      intake_id: input.intake_id,
      source: input.source,
      received_at: input.received_at,
      sender_email: input.sender_email,
      subject: input.subject,
      extraction: input.extraction ?? { method: 'unknown', confidence: 0, missing_fields: [] },
      order,
      issues,
      key_source,
    },
  };
});
