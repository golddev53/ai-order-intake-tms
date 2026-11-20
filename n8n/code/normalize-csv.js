// One item per CSV row. Column names match samples/orders.csv.
const fileName = $('Drive: New CSV in Folder').first().json.name ?? 'upload.csv';

return $input.all().map((item, i) => {
  const r = item.json;
  const stop = (prefix) => ({
    name: r[`${prefix}_name`] || null,
    street: r[`${prefix}_street`] || null,
    city: r[`${prefix}_city`] || null,
    state: r[`${prefix}_state`] || null,
    zip: r[`${prefix}_zip`] || null,
    window_start: r[`${prefix}_window_start`] || null,
    window_end: r[`${prefix}_window_end`] || null,
    instructions: r[`${prefix}_instructions`] || null,
  });

  return {
    json: {
      intake_id: `${$execution.id}-csv-${i}`,
      source: 'csv',
      received_at: new Date().toISOString(),
      sender_email: r.contact_email || null,
      subject: `${fileName} row ${i + 2}`,
      raw_text: null,
      order: {
        customer: {
          company: r.customer_company || null,
          contact_name: r.contact_name || null,
          email: r.contact_email || null,
          phone: r.contact_phone || null,
        },
        reference_number: r.reference_number || null,
        service_level: r.service_level || 'scheduled',
        pickup: stop('pickup'),
        dropoff: stop('dropoff'),
        items: [{
          description: r.items_description || 'Freight',
          quantity: parseInt(r.quantity, 10) || null,
          unit: r.unit || 'other',
          weight_lbs: parseFloat(r.weight_lbs) || null,
        }],
        vehicle_type: r.vehicle_type || null,
        special_instructions: r.notes || null,
      },
      extraction: { method: 'structured', confidence: 1, missing_fields: [] },
    },
  };
});
