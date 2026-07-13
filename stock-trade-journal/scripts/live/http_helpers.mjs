import crypto from "node:crypto";

export function isLoopbackHost(host) {
  const value = String(host || "").trim().toLowerCase();
  return value === "127.0.0.1" || value === "localhost" || value === "::1" || value === "[::1]";
}

export function sendJson(res, payload, status = 200) {
  res.statusCode = status;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.setHeader("cache-control", "no-store");
  res.end(JSON.stringify(payload));
}

export function sendText(res, text, status = 200, contentType = "text/plain; charset=utf-8") {
  res.statusCode = status;
  res.setHeader("content-type", contentType);
  res.end(String(text ?? ""));
}

export async function readJson(req, maxBytes = 1024 * 1024) {
  const chunks = [];
  let total = 0;
  for await (const chunk of req) {
    total += chunk.length;
    if (total > maxBytes) {
      const error = new Error("request body too large");
      error.status = 413;
      error.code = "BODY_TOO_LARGE";
      throw error;
    }
    chunks.push(chunk);
  }
  if (!chunks.length) return {};
  try {
    const value = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    if (!value || Array.isArray(value) || typeof value !== "object") throw new Error("object required");
    return value;
  } catch (cause) {
    const error = new Error("invalid JSON body", { cause });
    error.status = 400;
    error.code = "INVALID_JSON";
    throw error;
  }
}

function safeEqual(left, right) {
  const a = Buffer.from(String(left || ""));
  const b = Buffer.from(String(right || ""));
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

export function authorize(req, apiKey) {
  if (!apiKey) return true;
  const header = String(req.headers.authorization || "");
  const supplied = header.startsWith("Bearer ") ? header.slice(7) : "";
  return safeEqual(supplied, apiKey);
}

export function assertJsonWrite(req, expectedOrigin) {
  const contentType = String(req.headers["content-type"] || "").toLowerCase();
  if (!contentType.startsWith("application/json")) {
    const error = new Error("Content-Type must be application/json");
    error.status = 415;
    error.code = "UNSUPPORTED_MEDIA_TYPE";
    throw error;
  }
  const origin = String(req.headers.origin || "");
  if (origin && expectedOrigin && origin !== expectedOrigin) {
    const error = new Error("cross-origin write rejected");
    error.status = 403;
    error.code = "ORIGIN_REJECTED";
    throw error;
  }
}

export function publicError(error) {
  const status = Number(error?.status) || 500;
  return {
    status,
    payload: {
      ok: false,
      data: null,
      meta: {
        status,
        warnings: [status >= 500 ? "服务暂时不可用" : String(error?.message || "请求失败")],
      },
      errors: [{
        scope: "http",
        provider: null,
        code: String(error?.code || (status >= 500 ? "INTERNAL_ERROR" : "REQUEST_ERROR")),
        message: status >= 500 ? "服务内部错误" : String(error?.message || "请求失败"),
        retryable: status >= 500,
      }],
    },
  };
}
