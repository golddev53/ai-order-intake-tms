const ctx = $('Decide: Auto-book or Review').item.json;
const shipment = $('TMS: Dispatch to Route').item.json;

return {
  json: {
    status: 'booked',
    message: `Booked and dispatched as ${shipment.id}. Confirmation emailed to ${shipment.customer?.email}.`,
    intake_id: ctx.intake_id,
    shipment_id: shipment.id,
    route_id: shipment.route?.id ?? null,
    driver: shipment.route?.driver?.name ?? null,
    pickup_eta: shipment.route?.pickup_eta ?? null,
    delivery_eta: shipment.route?.eta ?? null,
    price: ctx.quote?.total ?? null,
    extraction: ctx.extraction,
  },
};
