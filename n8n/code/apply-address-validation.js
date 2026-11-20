const ctx = JSON.parse(JSON.stringify($('Idempotency Key').item.json));

const PRECISE = ['ROOFTOP', 'RANGE_INTERPOLATED'];
const readGeocode = (res) => {
  const r = res?.results?.[0];
  if (res?.status !== 'OK' || !r) return { verified: false, status: res?.status ?? 'ERROR' };
  return {
    verified: PRECISE.includes(r.geometry.location_type) && !r.partial_match,
    status: res.status,
    location_type: r.geometry.location_type,
    formatted_address: r.formatted_address,
    lat: r.geometry.location.lat,
    lng: r.geometry.location.lng,
    place_id: r.place_id,
  };
};

ctx.geo = {
  pickup: readGeocode($('Maps: Geocode Pickup').item.json),
  dropoff: readGeocode($json),
};

for (const side of ['pickup', 'dropoff']) {
  const g = ctx.geo[side];
  if (!g.verified) ctx.issues.push(`Google Maps could not verify the ${side} address (${g.location_type ?? g.status})`);
}

ctx.quote_request = {
  pickup: { lat: ctx.geo.pickup.lat ?? null, lng: ctx.geo.pickup.lng ?? null },
  dropoff: { lat: ctx.geo.dropoff.lat ?? null, lng: ctx.geo.dropoff.lng ?? null },
  items: ctx.order.items,
  service_level: ctx.order.service_level,
  vehicle_type: ctx.order.vehicle_type,
};

return { json: ctx };
