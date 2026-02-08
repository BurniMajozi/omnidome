exports.handler = async function (context, event, callback) {
  const response = new Twilio.Response();
  response.appendHeader("Content-Type", "application/json");

  try {
    const client = context.getTwilioClient();
    const to = event.To || event.to;
    const from = event.From || event.from || context.DEFAULT_SMS_FROM;
    const body = event.Body || event.body;

    if (!to) {
      throw new Error("Missing To");
    }
    if (!from) {
      throw new Error("Missing From");
    }
    if (!body) {
      throw new Error("Missing Body");
    }

    const message = await client.messages.create({ to, from, body });
    response.setBody({ ok: true, sid: message.sid });
    return callback(null, response);
  } catch (error) {
    response.setStatusCode(400);
    response.setBody({ ok: false, error: error.message });
    return callback(null, response);
  }
};
