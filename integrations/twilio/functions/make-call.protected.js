exports.handler = async function (context, event, callback) {
  const response = new Twilio.Response();
  response.appendHeader("Content-Type", "application/json");

  try {
    const client = context.getTwilioClient();
    const to = event.To || event.to;
    const from = event.From || event.from || context.DEFAULT_CALLER_ID;
    const twiml = event.twiml || event.Twiml;
    const url = event.url || event.Url;

    if (!to) {
      throw new Error("Missing To");
    }
    if (!from) {
      throw new Error("Missing From");
    }
    if (!twiml && !url) {
      throw new Error("Provide twiml or url");
    }

    const payload = { to, from };
    if (twiml) {
      payload.twiml = twiml;
    }
    if (url) {
      payload.url = url;
    }

    const call = await client.calls.create(payload);
    response.setBody({ ok: true, sid: call.sid });
    return callback(null, response);
  } catch (error) {
    response.setStatusCode(400);
    response.setBody({ ok: false, error: error.message });
    return callback(null, response);
  }
};
