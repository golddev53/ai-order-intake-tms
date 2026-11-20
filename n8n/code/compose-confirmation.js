// Input is a dispatched TMS shipment. Shared by the intake and review workflows.
const s = $json;
const at = (t) => (t ? String(t).replace('T', ' ') : 'TBD');
const place = (stop = {}) => stop.formatted_address || [stop.street, stop.city, stop.state, stop.zip].filter(Boolean).join(', ');
const ref = s.reference_number ? ` (your ref ${s.reference_number})` : '';

const body = [
  `Hi ${s.customer?.contact_name ?? 'there'},`,
  '',
  `Your delivery is booked${ref}.`,
  '',
  `Shipment:      ${s.id}`,
  `Pickup:        ${place(s.pickup)}`,
  `Pickup ETA:    ${at(s.route?.pickup_eta)}`,
  `Deliver to:    ${place(s.dropoff)}`,
  `Delivery ETA:  ${at(s.route?.eta)}`,
  `Vehicle:       ${s.vehicle_type ?? 'Assigned by dispatch'}`,
  `Driver:        ${s.route?.driver?.name ?? 'Assigned shortly'}`,
  s.price != null ? `Price:         $${s.price.toFixed(2)}` : null,
  '',
  s.route?.tracking_url ? `Track it live: ${s.route.tracking_url}` : null,
  '',
  'Reply to this email if anything needs to change.',
  '',
  'Dispatch team',
].filter((line) => line !== null);

return {
  json: {
    shipment_id: s.id,
    email: {
      personalizations: [{ to: [{ email: s.customer?.email }] }],
      subject: `Booked: ${s.id}${ref}`,
      content: [{ type: 'text/plain', value: body.join('\n') }],
    },
  },
};
