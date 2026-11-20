// Input is the draft shipment plus review_sig from "Sign Review Link".
const cfg = $('Load Config').first().json.config;
const ctx = $('Decide: Auto-book or Review').item.json;
const draft = $json;
const order = ctx.order;

const link = (action) =>
  `${cfg.public_url}/webhook/order-review?shipment_id=${encodeURIComponent(draft.id)}` +
  `&action=${action}&exp=${ctx.review_expires_at}&sig=${draft.review_sig}`;

const place = (s) => [s.street, s.city, s.state, s.zip].filter(Boolean).join(', ') || '_missing_';
const items = order.items.map((i) => `${i.quantity ?? '?'} ${i.unit} - ${i.description}`).join('\n') || '_none_';

const slack = {
  text: `Order needs review: ${draft.id}`,
  blocks: [
    { type: 'header', text: { type: 'plain_text', text: `Order needs review: ${draft.id}` } },
    { type: 'section', text: { type: 'mrkdwn', text: `*Why it was held*\n${ctx.review_reasons.map((r) => `- ${r}`).join('\n')}` } },
    {
      type: 'section',
      fields: [
        { type: 'mrkdwn', text: `*Customer*\n${order.customer.company ?? order.customer.email ?? '_unknown_'}` },
        { type: 'mrkdwn', text: `*Reference*\n${order.reference_number ?? '_none_'}` },
        { type: 'mrkdwn', text: `*Pickup*\n${place(order.pickup)}\n${order.pickup.window_start ?? '_no time_'}` },
        { type: 'mrkdwn', text: `*Dropoff*\n${place(order.dropoff)}\n${order.dropoff.window_end ? `by ${order.dropoff.window_end}` : ''}` },
        { type: 'mrkdwn', text: `*Items*\n${items}` },
        { type: 'mrkdwn', text: `*Quote*\n${ctx.quote ? `$${ctx.quote.total} - ${ctx.quote.vehicle_type}` : '_not priced_'}` },
      ],
    },
    {
      type: 'context',
      elements: [{ type: 'mrkdwn', text: `Source: ${ctx.source} | AI confidence ${ctx.extraction.confidence} | ${ctx.subject ?? 'no subject'}` }],
    },
    {
      type: 'actions',
      elements: [
        { type: 'button', style: 'primary', text: { type: 'plain_text', text: 'Approve & dispatch' }, url: link('approve') },
        { type: 'button', style: 'danger', text: { type: 'plain_text', text: 'Reject' }, url: link('reject') },
        { type: 'button', text: { type: 'plain_text', text: 'Edit in TMS' }, url: `${cfg.tms_ui_url}/?shipment=${encodeURIComponent(draft.id)}` },
      ],
    },
  ],
};

return { json: { shipment_id: draft.id, slack } };
