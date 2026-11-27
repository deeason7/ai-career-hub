import { handleApi } from "../../../lib/api-proxy.ts";

export const runtime = "nodejs";

async function api(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return handleApi(request, (await context.params).path);
}

export { api as GET, api as POST, api as PATCH, api as DELETE };
