// Builds the page shown in the reviewer's browser. __OUTCOME__ is set per node by build.py.
const outcome = '__OUTCOME__';
const s = outcome === 'approved' ? $('TMS: Dispatch Approved').item.json
  : outcome === 'rejected' ? $('TMS: Cancel Shipment').item.json
  : $json;

const pages = {
  invalid: () => ({ http_status: 403, tone: 'bad', title: 'Link not valid', message: s.reason }),
  handled: () => ({
    http_status: 409,
    tone: 'info',
    title: `Already ${s.status}`,
    message: `Shipment ${s.id} is already ${s.status}, so nothing was changed.`,
  }),
  approved: () => ({
    http_status: 200,
    tone: 'good',
    title: `${s.id} approved`,
    message: `Booked and dispatched on route ${s.route?.id} with ${s.route?.driver?.name}. Pickup ETA ${String(s.route?.pickup_eta).replace('T', ' ')}. The customer has been emailed.`,
  }),
  rejected: () => ({
    http_status: 200,
    tone: 'bad',
    title: `${s.id} rejected`,
    message: 'The draft was cancelled in the TMS. Reply to the customer if you need more details from them.',
  }),
};

return { json: pages[outcome]() };
