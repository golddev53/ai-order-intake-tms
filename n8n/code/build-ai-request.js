const cfg = $('Load Config').first().json.config;
const ORDER_SCHEMA = __ORDER_SCHEMA__;

const system = [
  'You extract B2B delivery orders for a logistics company and return JSON matching the schema.',
  'Rules:',
  '- Use only information in the message. Never invent addresses, dates, phone numbers or references. Use null when a value is missing and list its path in missing_fields.',
  '- Resolve relative dates ("tomorrow", "Monday") from the received timestamp and timezone.',
  '- Times are local, formatted YYYY-MM-DDTHH:MM. A single "deliver by" time is dropoff.window_end.',
  '- state is the 2-letter US code and zip is 5 digits.',
  '- customer is the company placing the order. Use the sender email if no other contact email is given.',
  '- service_level is same_day for today/ASAP/urgent, recurring if it repeats, otherwise scheduled.',
  '- confidence is 0.95 or higher only when both full addresses, the pickup time and the item quantities are stated explicitly.',
].join('\n');

const user = [
  `Received: ${$json.received_at} (timezone ${cfg.timezone})`,
  `From: ${$json.sender_email ?? 'unknown'}`,
  `Subject: ${$json.subject ?? ''}`,
  '',
  $json.raw_text ?? '',
].join('\n');

return {
  json: {
    ...$json,
    ai_request: {
      model: cfg.openai_model,
      temperature: 0,
      response_format: {
        type: 'json_schema',
        json_schema: { name: 'logistics_order', strict: true, schema: ORDER_SCHEMA },
      },
      messages: [
        { role: 'system', content: system },
        { role: 'user', content: user },
      ],
    },
  },
};
