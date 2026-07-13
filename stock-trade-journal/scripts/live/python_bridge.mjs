import { spawn } from "node:child_process";


function cleanStderr(value) {
  return String(value || "")
    .replace(/(api[_-]?key|authorization|token|secret)\s*[=:]\s*\S+/gi, "$1=[REDACTED]")
    .slice(0, 1200);
}

function terminate(child) {
  if (!child || child.killed || child.exitCode !== null) return;
  child.kill("SIGTERM");
  const timer = setTimeout(() => {
    if (child.exitCode === null) child.kill("SIGKILL");
  }, 1200);
  timer.unref();
}

export function runPythonJson({ python = "python3", script, args = [], input = "", timeoutMs = 45_000, maxBytes = 16 * 1024 * 1024 }) {
  return new Promise((resolve, reject) => {
    const child = spawn(python, [script, ...args], {
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
      env: process.env,
    });
    const stdout = [];
    const stderr = [];
    let size = 0;
    const timer = setTimeout(() => {
      terminate(child);
      const error = new Error("data worker timeout");
      error.status = 504;
      error.code = "WORKER_TIMEOUT";
      reject(error);
    }, timeoutMs);
    timer.unref();
    child.stdout.on("data", (chunk) => {
      size += chunk.length;
      if (size > maxBytes) {
        terminate(child);
        const error = new Error("data worker output too large");
        error.status = 502;
        error.code = "WORKER_OUTPUT_TOO_LARGE";
        reject(error);
        return;
      }
      stdout.push(chunk);
    });
    child.stderr.on("data", (chunk) => {
      if (Buffer.concat(stderr).length < 4096) stderr.push(chunk);
    });
    child.on("error", (cause) => {
      clearTimeout(timer);
      const error = new Error("failed to start data worker", { cause });
      error.status = 502;
      error.code = "WORKER_START_FAILED";
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      const raw = Buffer.concat(stdout).toString("utf8").trim();
      let payload;
      try {
        payload = raw ? JSON.parse(raw) : null;
      } catch (cause) {
        const error = new Error(`invalid data worker response: ${cleanStderr(Buffer.concat(stderr).toString("utf8"))}`, { cause });
        error.status = 502;
        error.code = "WORKER_INVALID_JSON";
        reject(error);
        return;
      }
      if (payload && typeof payload === "object") {
        resolve(payload);
        return;
      }
      const error = new Error(cleanStderr(Buffer.concat(stderr).toString("utf8")) || `data worker exited ${code}`);
      error.status = 502;
      error.code = "WORKER_FAILED";
      reject(error);
    });
    child.stdin.end(input || "");
  });
}

export function streamPythonNdjson({ req, res, python = "python3", script, args = [], input, timeoutMs = 310_000 }) {
  return new Promise((resolve, reject) => {
    const child = spawn(python, [script, ...args], {
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
      env: process.env,
    });
    let responseStarted = false;
    let stderr = "";
    const timer = setTimeout(() => {
      terminate(child);
      if (!responseStarted) {
        const error = new Error("chat worker timeout");
        error.status = 504;
        error.code = "WORKER_TIMEOUT";
        reject(error);
      } else {
        res.write(`${JSON.stringify({ type: "error", code: "WORKER_TIMEOUT", message: "AI 生成超时", retryable: true })}\n`);
        res.end();
        resolve();
      }
    }, timeoutMs);
    timer.unref();

    const abort = () => terminate(child);
    req.on("aborted", abort);
    res.on("close", () => {
      if (!res.writableEnded) abort();
    });

    child.stdout.on("data", (chunk) => {
      if (!responseStarted) {
        responseStarted = true;
        res.statusCode = 200;
        res.setHeader("content-type", "application/x-ndjson; charset=utf-8");
        res.setHeader("cache-control", "no-store");
        res.setHeader("x-content-type-options", "nosniff");
      }
      res.write(chunk);
    });
    child.stderr.on("data", (chunk) => {
      if (stderr.length < 1200) stderr += chunk.toString("utf8");
    });
    child.on("error", (cause) => {
      clearTimeout(timer);
      const error = new Error("failed to start chat worker", { cause });
      error.status = 502;
      error.code = "WORKER_START_FAILED";
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (!responseStarted && code !== 0) {
        const error = new Error(cleanStderr(stderr) || "chat worker failed");
        error.status = 502;
        error.code = "WORKER_FAILED";
        reject(error);
        return;
      }
      if (!res.writableEnded) res.end();
      resolve();
    });
    child.stdin.end(JSON.stringify(input));
  });
}
