exports.handler = async function (context, event, callback) {
  const response = new Twilio.Response();
  response.appendHeader("Content-Type", "application/json");

  try {
    const client = context.getTwilioClient();
    const from = event.From || event.from || context.DEFAULT_SMS_FROM;
    const body = event.Body || event.body;
    const rawRecipients = event.To || event.to || event.recipients;

    if (!from) {
      throw new Error("Missing From");
    }
    if (!body) {
      throw new Error("Missing Body");
    }
    if (!rawRecipients) {
      throw new Error("Missing recipients");
    }

    const recipients = Array.isArray(rawRecipients)
      ? rawRecipients
      : String(rawRecipients)
          .split(/[,\n]/)
          .map((item) => item.trim())
          .filter(Boolean);

    if (!recipients.length) {
      throw new Error("No recipients provided");
    }

    const results = await Promise.allSettled(
      recipients.map((to) => client.messages.create({ to, from, body }))
    );

    const success = results.filter((item) => item.status === "fulfilled").length;
    const failures = results
      .filter((item) => item.status === "rejected")
      .map((item) => item.reason && item.reason.message)
      .filter(Boolean);

    response.setBody({
      ok: failures.length === 0,
      sent: success,
      failed: failures.length,
      errors: failures,
    });
    return callback(null, response);
  } catch (error) {
    response.setStatusCode(400);
    response.setBody({ ok: false, error: error.message });
    return callback(null, response);
  }
};
