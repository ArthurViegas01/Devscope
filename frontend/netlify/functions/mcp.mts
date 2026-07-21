/**
 * Netlify Function: same-origin proxy for the MCP endpoint.
 *
 * The public demo cannot ship the bearer token in the JS bundle, so this
 * function receives browser requests at /mcp and forwards them to the Railway
 * backend with the Authorization header injected server-side. The token lives
 * only in Netlify env vars (MCP_AUTH_TOKEN), never in the client.
 */

const HOP_BY_HOP = ["host", "connection", "content-length", "accept-encoding"];

export default async (req: Request): Promise<Response> => {
  const token = process.env.MCP_AUTH_TOKEN;
  const backend = process.env.MCP_BACKEND_URL;

  if (!token || !backend) {
    return new Response(
      JSON.stringify({ error: "proxy_not_configured" }),
      { status: 500, headers: { "content-type": "application/json" } },
    );
  }

  const headers = new Headers(req.headers);
  for (const h of HOP_BY_HOP) headers.delete(h);
  headers.set("authorization", `Bearer ${token}`);

  const upstream = await fetch(backend, {
    method: req.method,
    headers,
    body: req.body,
    // Required by undici to stream a request body.
    // @ts-expect-error duplex is not in the fetch types yet
    duplex: "half",
  });

  // fetch already decompressed the body; keeping these headers would corrupt
  // the response for the browser.
  const respHeaders = new Headers(upstream.headers);
  respHeaders.delete("content-encoding");
  respHeaders.delete("content-length");

  return new Response(upstream.body, {
    status: upstream.status,
    headers: respHeaders,
  });
};

export const config = { path: "/mcp" };
