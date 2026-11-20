const ctx = $('Decide: Auto-book or Review').item.json;
const draft = $('TMS: Create Draft Shipment').item.json;

return {
  json: {
    status: 'needs_review',
    message: `Saved as draft ${draft.id} in the TMS and sent to Slack for approval.`,
    intake_id: ctx.intake_id,
    shipment_id: draft.id,
    review_reasons: ctx.review_reasons,
    price: ctx.quote?.total ?? null,
    extraction: ctx.extraction,
  },
};
