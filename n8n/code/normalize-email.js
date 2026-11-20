// Input items come from "Extract PDF Attachment", which errors (and passes { error }) when the
// email has no PDF, so the email itself is read from the trigger.
return $input.all().map((item, i) => {
  const email = $('Email: Orders Inbox').itemMatching(i).json;
  const pdfText = item.json.error ? '' : item.json.text ?? '';
  const body = email.text || String(email.html ?? '').replace(/<[^>]+>/g, ' ');

  return {
    json: {
      intake_id: `${$execution.id}-mail-${i}`,
      source: 'email',
      received_at: email.date ? new Date(email.date).toISOString() : new Date().toISOString(),
      sender_email: email.from?.value?.[0]?.address ?? null,
      subject: email.subject ?? null,
      raw_text: [body, pdfText && `--- PDF attachment ---\n${pdfText}`].filter(Boolean).join('\n\n'),
      order: null,
      extraction: null,
    },
  };
});
