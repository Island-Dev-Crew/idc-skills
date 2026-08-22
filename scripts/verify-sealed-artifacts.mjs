#!/usr/bin/env node
/** Dependency-free Chrome DevTools zero-egress verifier for local HTML artifacts. */
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const EXPECTED_CSP = "default-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'; object-src 'none'; connect-src 'none'; font-src 'none'; img-src data: blob:; media-src data: blob:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; worker-src 'none'";

function usage(message) {
  if (message) console.error(`verify-sealed-artifacts: ${message}`);
  console.error("usage: node scripts/verify-sealed-artifacts.mjs [--config FILE] [--output FILE]");
  process.exit(2);
}

let configPath = join(REPO, "ops/mission/sealed-artifacts.json");
let outputPath = join(REPO, "ops/mission/evidence/2.0.4/g3-sealed-browser.json");
for (let i = 2; i < process.argv.length; i += 1) {
  if (process.argv[i] === "--config" && process.argv[i + 1]) configPath = resolve(process.argv[++i]);
  else if (process.argv[i] === "--output" && process.argv[i + 1]) outputPath = resolve(process.argv[++i]);
  else usage(`unknown or incomplete option ${process.argv[i]}`);
}

const config = JSON.parse(readFileSync(configPath, "utf8"));
if (config.schema !== "idc-sealed-artifacts/v1" || !Array.isArray(config.artifacts) || !config.artifacts.length) {
  usage("config does not satisfy idc-sealed-artifacts/v1");
}
if (!Number.isInteger(config.observationMs) || config.observationMs < 250 || config.observationMs > 10000) {
  usage("observationMs must be an integer from 250 through 10000");
}

const chromeCandidates = [
  process.env.IDC_CHROME_PATH,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
].filter(Boolean);
const chromePath = chromeCandidates.find((candidate) => existsSync(candidate));
if (!chromePath) {
  console.error("verify-sealed-artifacts: FAIL — no supported local Chrome/Chromium executable found");
  process.exit(1);
}

const delay = (milliseconds) => new Promise((accept) => setTimeout(accept, milliseconds));
const sha256 = (path) => `sha256:${createHash("sha256").update(readFileSync(path)).digest("hex")}`;
const safeScheme = (url) => /^(?:file|data|blob|about|devtools):/i.test(url);

class CDP {
  constructor(url) {
    this.url = url;
    this.socket = null;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
  }

  async open() {
    this.socket = new WebSocket(this.url);
    await new Promise((accept, reject) => {
      const timer = setTimeout(() => reject(new Error("timed out opening DevTools WebSocket")), 5000);
      this.socket.addEventListener("open", () => { clearTimeout(timer); accept(); }, { once: true });
      this.socket.addEventListener("error", (error) => { clearTimeout(timer); reject(error); }, { once: true });
    });
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (message.id) {
        const waiter = this.pending.get(message.id);
        if (!waiter) return;
        this.pending.delete(message.id);
        clearTimeout(waiter.timer);
        if (message.error) waiter.reject(new Error(message.error.message));
        else waiter.resolve(message.result ?? {});
        return;
      }
      for (const listener of this.listeners.get(message.method) ?? []) listener(message.params ?? {});
    });
    const rejectPending = () => {
      for (const [id, waiter] of this.pending) {
        clearTimeout(waiter.timer);
        waiter.reject(new Error(`DevTools socket closed while waiting for ${waiter.method} (${id})`));
      }
      this.pending.clear();
    };
    this.socket.addEventListener("close", rejectPending);
    this.socket.addEventListener("error", rejectPending);
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolvePromise, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`timed out in DevTools method ${method}`));
      }, 10000);
      this.pending.set(id, { resolve: resolvePromise, reject, timer, method });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) ?? [];
    listeners.push(listener);
    this.listeners.set(method, listeners);
  }

  once(method, timeoutMs = 10000) {
    return new Promise((accept, reject) => {
      const timer = setTimeout(() => reject(new Error(`timed out waiting for ${method}`)), timeoutMs);
      const listener = (params) => {
        clearTimeout(timer);
        const listeners = this.listeners.get(method) ?? [];
        this.listeners.set(method, listeners.filter((entry) => entry !== listener));
        accept(params);
      };
      this.on(method, listener);
    });
  }

  close() {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.close();
  }
}

async function waitForPort(profile) {
  const activePort = join(profile, "DevToolsActivePort");
  for (let attempt = 0; attempt < 200; attempt += 1) {
    if (existsSync(activePort)) {
      const [port] = readFileSync(activePort, "utf8").trim().split(/\r?\n/);
      if (/^[0-9]+$/.test(port)) return Number(port);
    }
    await delay(25);
  }
  throw new Error("Chrome did not publish a DevTools port within five seconds");
}

async function evaluate(cdp, expression, awaitPromise = false) {
  const result = await cdp.send("Runtime.evaluate", {
    expression,
    awaitPromise,
    returnByValue: true,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || "page evaluation failed");
  return result.result?.value;
}

async function verifyState(port, artifactPath, state, observationMs) {
  const created = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {
    method: "PUT",
    signal: AbortSignal.timeout(5000),
  });
  if (!created.ok) throw new Error(`Chrome target creation failed: HTTP ${created.status}`);
  const target = await created.json();
  const cdp = new CDP(target.webSocketDebuggerUrl);
  await cdp.open();
  const attempts = [];
  const consoleErrors = [];
  const serviceWorkerEvents = [];
  cdp.on("Fetch.requestPaused", (event) => {
    const url = event.request?.url ?? "";
    if (!safeScheme(url)) attempts.push({ url, method: event.request?.method ?? "?", resourceType: event.resourceType ?? "?" });
    const method = safeScheme(url) ? "Fetch.continueRequest" : "Fetch.failRequest";
    const params = safeScheme(url) ? { requestId: event.requestId } : { requestId: event.requestId, errorReason: "BlockedByClient" };
    cdp.send(method, params).catch((error) => consoleErrors.push(`request interception: ${error.message}`));
  });
  cdp.on("Runtime.exceptionThrown", (event) => consoleErrors.push(event.exceptionDetails?.text ?? "runtime exception"));
  cdp.on("Log.entryAdded", (event) => {
    if (["error", "warning"].includes(event.entry?.level)) consoleErrors.push(event.entry.text);
  });
  cdp.on("ServiceWorker.workerRegistrationUpdated", (event) => serviceWorkerEvents.push(event.registrations ?? []));

  try {
    await Promise.all([
      cdp.send("Page.enable"),
      cdp.send("Runtime.enable"),
      cdp.send("Log.enable"),
      cdp.send("Network.enable"),
      cdp.send("Fetch.enable", { patterns: [{ urlPattern: "*" }] }),
      cdp.send("ServiceWorker.enable"),
    ]);
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: state.width,
      height: state.height,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await cdp.send("Emulation.setEmulatedMedia", {
      media: state.media,
      features: [{ name: "prefers-reduced-motion", value: "reduce" }],
    });
    const loaded = cdp.once("Page.loadEventFired");
    await cdp.send("Page.navigate", { url: pathToFileURL(artifactPath).href });
    await loaded;
    await evaluate(
      cdp,
      `(() => { document.querySelectorAll('details').forEach((node) => { node.open = true; }); scrollTo(0, document.documentElement.scrollHeight); return true; })()`,
    );
    await delay(observationMs);
    const page = await evaluate(
      cdp,
      `(async () => {
        let registrations = 0;
        try { registrations = navigator.serviceWorker ? (await navigator.serviceWorker.getRegistrations()).length : 0; } catch {}
        const csp = document.querySelector('meta[http-equiv="Content-Security-Policy" i]')?.content ?? '';
        const isClippedByAncestor = (node, rect) => {
          for (let parent = node.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
            const style = getComputedStyle(parent);
            const parentRect = parent.getBoundingClientRect();
            if (/(auto|scroll|hidden|clip)/.test(style.overflowX) && rect.right > parentRect.right + 0.5) return true;
          }
          return false;
        };
        const overflowingElements = [...document.querySelectorAll('body *')]
          .map((node) => ({ node, rect: node.getBoundingClientRect() }))
          .filter(({ node, rect }) => rect.right > innerWidth + 0.5 && getComputedStyle(node).position !== 'fixed' && !isClippedByAncestor(node, rect))
          .slice(0, 12)
          .map(({ node, rect }) => ({
            tag: node.tagName,
            className: String(node.className || '').slice(0, 120),
            right: Math.round(rect.right),
            width: Math.round(rect.width),
            text: String(node.textContent || '').trim().slice(0, 120),
          }));
        return {
          readyState: document.readyState,
          title: document.title,
          csp,
          registrationCount: registrations,
          viewportWidth: innerWidth,
          scrollWidth: document.documentElement.scrollWidth,
          horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
          overflowingElements,
          tableWraps: [...document.querySelectorAll('.table-wrap')].slice(0, 8).map((node) => ({
            left: Math.round(node.getBoundingClientRect().left),
            right: Math.round(node.getBoundingClientRect().right),
            clientWidth: node.clientWidth,
            scrollWidth: node.scrollWidth,
            overflowX: getComputedStyle(node).overflowX,
          })),
          bodyTextBytes: new TextEncoder().encode(document.body?.innerText ?? '').length,
        };
      })()`,
      true,
    );
    const printModeEmulated = state.media === "print";
    const artifactServiceWorkers = serviceWorkerEvents
      .flat(2)
      .filter((registration) => !String(registration.scopeURL ?? "").startsWith("chrome-extension://"));
    const passed =
      attempts.length === 0 &&
      consoleErrors.length === 0 &&
      artifactServiceWorkers.length === 0 &&
      page.registrationCount === 0 &&
      page.readyState === "complete" &&
      page.csp === EXPECTED_CSP &&
      page.viewportWidth === state.width &&
      page.horizontalOverflow === false &&
      page.bodyTextBytes > 0;
    return { state, passed, attempts, consoleErrors, serviceWorkerEvents, artifactServiceWorkers, page, printModeEmulated };
  } finally {
    cdp.close();
    await fetch(`http://127.0.0.1:${port}/json/close/${target.id}`, {
      signal: AbortSignal.timeout(5000),
    }).catch(() => {});
  }
}

const profile = mkdtempSync(join(tmpdir(), "idc-sealed-chrome-"));
const chrome = spawn(
  chromePath,
  [
    "--headless=new",
    "--remote-debugging-port=0",
    `--user-data-dir=${profile}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-domain-reliability",
    "--disable-extensions",
    "--disable-features=ServiceWorker,BackForwardCache,MediaRouter",
    "--disable-sync",
    "--metrics-recording-only",
    "--no-pings",
    "--allow-file-access-from-files",
    "--host-resolver-rules=MAP * 0.0.0.0, EXCLUDE localhost, EXCLUDE 127.0.0.1",
    "about:blank",
  ],
  { stdio: "ignore" },
);

let evidence;
try {
  const port = await waitForPort(profile);
  const versionResponse = await fetch(`http://127.0.0.1:${port}/json/version`, {
    signal: AbortSignal.timeout(5000),
  });
  const version = await versionResponse.json();
  const artifacts = [];
  for (const entry of config.artifacts) {
    if (!entry || typeof entry.path !== "string" || !Array.isArray(entry.states) || !entry.states.length) {
      throw new Error("artifact entry is invalid");
    }
    const artifactPath = isAbsolute(entry.path) ? entry.path : resolve(REPO, entry.path);
    if (!existsSync(artifactPath)) throw new Error(`artifact does not exist: ${artifactPath}`);
    const states = [];
    for (const state of entry.states) {
      if (!["screen", "print"].includes(state.media) || !Number.isInteger(state.width) || !Number.isInteger(state.height)) {
        throw new Error(`invalid state for ${entry.path}`);
      }
      states.push(await verifyState(port, artifactPath, state, config.observationMs));
    }
    artifacts.push({
      path: entry.path,
      label: entry.label ?? entry.path,
      sha256: sha256(artifactPath),
      passed: states.every((state) => state.passed),
      states,
    });
  }
  evidence = {
    schema: "idc-sealed-browser-evidence/v1",
    generatedAt: new Date().toISOString(),
    enforced: {
      network: "all non-local request attempts intercepted and failed",
      serviceWorkers: "disabled by ephemeral browser launch and asserted empty",
      csp: EXPECTED_CSP,
      observationMs: config.observationMs,
    },
    browser: { product: version.Browser, protocolVersion: version["Protocol-Version"], executable: chromePath },
    passed: artifacts.every((artifact) => artifact.passed),
    artifacts,
  };
} catch (error) {
  evidence = {
    schema: "idc-sealed-browser-evidence/v1",
    generatedAt: new Date().toISOString(),
    passed: false,
    error: error instanceof Error ? error.message : String(error),
  };
} finally {
  chrome.kill("SIGTERM");
  await delay(200);
  if (!chrome.killed) chrome.kill("SIGKILL");
  rmSync(profile, { recursive: true, force: true });
}

writeFileSync(outputPath, `${JSON.stringify(evidence, null, 2)}\n`, "utf8");
if (!evidence.passed) {
  console.error(`verify-sealed-artifacts: FAIL — see ${outputPath}`);
  if (evidence.error) console.error(`  ${evidence.error}`);
  process.exit(1);
}
console.log(`verify-sealed-artifacts: PASS — ${evidence.artifacts.length} artifact(s), 4-state sealed matrix`);
console.log(`  evidence: ${outputPath}`);
