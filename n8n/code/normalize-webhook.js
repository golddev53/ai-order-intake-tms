// Webhook body is either an unstructured order ({ from, subject, text }) such as a forwarded
// email or pasted PDF text, or a structured order ({ source, order }) from a portal or ERP.
return $input.all().map((item, i) => {
  const body = item.json.body ?? {};
  return {
    json: {
      intake_id: `${$execution.id}-wh-${i}`,
      source: body.source || 'webhook',
      received_at: new Date().toISOString(),
      sender_email: body.from ?? null,
      subject: body.subject ?? null,
      raw_text: body.text ?? null,
      order: body.order ?? null,
      extraction: body.order ? { method: 'structured', confidence: 1, missing_fields: [] } : null,
    },
  };
});
