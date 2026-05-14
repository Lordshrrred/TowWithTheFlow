import { handler as netlifyBacklinkHandler } from '../netlify/functions/backlinks.js';

function normalizeBody(body) {
  if (!body) return '';
  if (typeof body === 'string') return body;
  return JSON.stringify(body);
}

export default async function handler(req, res) {
  const event = {
    httpMethod: req.method,
    queryStringParameters: req.query || {},
    body: normalizeBody(req.body),
  };

  const result = await netlifyBacklinkHandler(event);
  for (const [key, value] of Object.entries(result.headers || {})) {
    res.setHeader(key, value);
  }
  res.status(result.statusCode || 200).send(result.body || '');
}
