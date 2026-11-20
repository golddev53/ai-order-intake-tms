const { ai_request, ...envelope } = $('Build AI Request').item.json;
const content = $json.choices?.[0]?.message?.content;

let extracted;
try {
  extracted = JSON.parse(content);
} catch (e) {
  throw new Error(`AI returned invalid JSON for intake ${envelope.intake_id}: ${String(content).slice(0, 200)}`);
}

const { confidence = 0, missing_fields = [], ...order } = extracted;

return {
  json: {
    ...envelope,
    order,
    extraction: { method: 'ai', model: $json.model, confidence, missing_fields },
  },
};
