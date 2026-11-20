// Shopify orders/create payload. Pickup is left empty so "Validate & Normalize Order" uses the
// default warehouse from the config.
return $input.all().map((item, i) => {
  const o = item.json;
  const ship = o.shipping_address ?? {};

  return {
    json: {
      intake_id: `${$execution.id}-shop-${i}`,
      source: 'shopify',
      received_at: o.created_at ?? new Date().toISOString(),
      sender_email: o.email ?? null,
      subject: `Shopify order ${o.name ?? o.id}`,
      raw_text: null,
      order: {
        customer: {
          company: ship.company ?? null,
          contact_name: ship.name ?? null,
          email: o.email ?? o.customer?.email ?? null,
          phone: ship.phone ?? o.phone ?? o.customer?.phone ?? null,
        },
        reference_number: o.name ?? String(o.id),
        service_level: /same.?day/i.test(o.shipping_lines?.[0]?.title ?? '') ? 'same_day' : 'scheduled',
        pickup: null,
        dropoff: {
          name: ship.company || ship.name || null,
          street: [ship.address1, ship.address2].filter(Boolean).join(' ') || null,
          city: ship.city ?? null,
          state: ship.province_code ?? null,
          zip: ship.zip ?? null,
          window_start: null,
          window_end: null,
          instructions: o.note ?? null,
        },
        items: (o.line_items ?? []).map((li) => ({
          description: li.title,
          quantity: li.quantity ?? 1,
          unit: 'box',
          weight_lbs: li.grams ? Math.round(((li.grams * (li.quantity ?? 1)) / 453.6) * 10) / 10 : null,
        })),
        vehicle_type: null,
        special_instructions: o.note ?? null,
      },
      extraction: { method: 'structured', confidence: 1, missing_fields: [] },
    },
  };
});
