const { execution = {}, workflow = {} } = $json;
const error = execution.error ?? {};

const blocks = [
  { type: 'header', text: { type: 'plain_text', text: `Workflow failed: ${workflow.name ?? 'unknown'}` } },
  {
    type: 'section',
    text: {
      type: 'mrkdwn',
      text: `*Node:* ${execution.lastNodeExecuted ?? error.node?.name ?? 'unknown'}\n*Error:* ${error.message ?? 'no message'}\n*Mode:* ${execution.mode ?? '-'} | *Execution:* ${execution.id ?? '-'}`,
    },
  },
];

if (execution.url) {
  blocks.push({
    type: 'actions',
    elements: [{ type: 'button', text: { type: 'plain_text', text: 'Open execution' }, url: execution.url }],
  });
}

return { json: { slack: { text: `Workflow failed: ${workflow.name}`, blocks } } };
