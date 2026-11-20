const ctx = $('Apply Address Validation').item.json;
const existing = $json.data[0];

return {
  json: {
    status: 'duplicate',
    message: `Already in the TMS as ${existing.id} (${existing.status}). Nothing new was created.`,
    intake_id: ctx.intake_id,
    shipment_id: existing.id,
    shipment_status: existing.status,
    idempotency_key: ctx.idempotency_key,
  },
};
