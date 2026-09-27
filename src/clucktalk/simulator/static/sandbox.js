// MCP Apps sandbox proxy (spec 2026-01-26, "Sandbox proxy"), modelled on the ext-apps reference host.
// Host (Simulator page) <-> this proxy (other loopback origin) <-> card (inner iframe, same origin as this proxy).
"use strict";
(function () {
  const HOST_PATTERN = /^http:\/\/(127\.0\.0\.1|localhost):\d+$/;
  if (window.self === window.top) throw new Error("The card sandbox only runs inside the Simulator.");
  const hostOrigin = document.referrer ? new URL(document.referrer).origin : "";
  if (!HOST_PATTERN.test(hostOrigin)) throw new Error("Embedding page not allowed: " + hostOrigin);
  const ownOrigin = window.location.origin;
  if (ownOrigin === hostOrigin) throw new Error("Spec: host and sandbox MUST have different origins.");
  // Only the Simulator page that serves this proxy (same port, the other loopback name) may drive it.
  if (new URL(hostOrigin).port !== window.location.port) throw new Error("Embedding page not allowed: " + hostOrigin);

  // Self-test: reaching into the host page must fail. If it works, isolation is broken; stop here.
  let isolated = false;
  try { void window.top.document; } catch (e) { isolated = true; }
  if (!isolated) throw new Error("Sandbox is not isolated from the host page.");

  const inner = document.createElement("iframe");
  inner.setAttribute("sandbox", "allow-scripts allow-same-origin");
  inner.setAttribute("title", "Card");
  document.body.appendChild(inner);

  window.addEventListener("message", (event) => {
    if (event.source === window.parent) {
      if (event.origin !== hostOrigin) return;             // only the embedding Simulator page
      const m = event.data;
      if (m && m.method === "ui/notifications/sandbox-resource-ready") {
        const html = m.params && m.params.html;
        if (typeof html !== "string") return;
        const doc = inner.contentDocument;
        doc.open(); doc.write(html); doc.close();            // the card inherits this document's CSP
        return;
      }
      if (inner.contentWindow) inner.contentWindow.postMessage(m, "*");
    } else if (event.source === inner.contentWindow) {
      if (event.origin !== ownOrigin) return;
      const m = event.data;
      if (m && typeof m.method === "string" && m.method.startsWith("ui/notifications/sandbox-")) return;
      window.parent.postMessage(m, hostOrigin);
    }
  });

  window.parent.postMessage({ jsonrpc: "2.0", method: "ui/notifications/sandbox-proxy-ready", params: {} }, hostOrigin);
})();
