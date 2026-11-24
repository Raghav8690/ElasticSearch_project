"use strict";

/* ---------- tiny fetch wrapper with AbortController (20s) ---------- */
class ApiError extends Error {
  constructor(code, message, status, detail) {
    super(message || code || "Request failed");
    this.name = "ApiError";
    this.code = code || "error";
    this.status = status || 0;
    this.detail = detail || "redacted";
  }
}

const API = {
  async request(path, { method = "GET", params = null, body = null, timeoutMs = 20000, signal = null } = {}) {
    const url = new URL(path, window.location.origin);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
      });
    }
    const controller = new AbortController();
    let abortedBySignal = false;
    const abort = () => controller.abort();
    const abortFromSignal = () => {
      abortedBySignal = true;
      abort();
    };
    if (signal) {
      if (signal.aborted) abortFromSignal();
      else signal.addEventListener("abort", abortFromSignal, { once: true });
    }
    const timer = setTimeout(abort, timeoutMs);
    try {
      const res = await fetch(url, {
        method,
        signal: controller.signal,
        headers: Object.assign(
          { Accept: "application/json" },
          body ? { "Content-Type": "application/json" } : {}
        ),
        body: body ? JSON.stringify(body) : undefined,
      });
      const text = await res.text();
      let payload = {};
      if (text) {
        try {
          payload = JSON.parse(text);
        } catch {
          payload = { raw: text };
        }
      }
      if (!res.ok) {
        const err = (payload && payload.error) || {};
        throw new ApiError(
          err.code || `http_${res.status}`,
          err.message || res.statusText || "Request failed",
          res.status,
          err.detail
        );
      }
      return payload;
    } catch (error) {
      if (error.name === "AbortError") {
        if (abortedBySignal) throw new ApiError("aborted", "Request superseded by a newer request.", 499);
        throw new ApiError("timeout", `Request timed out after ${Math.round(timeoutMs / 1000)}s`, 504);
      }
      throw error;
    } finally {
      clearTimeout(timer);
      if (signal) signal.removeEventListener("abort", abortFromSignal);
    }
  },
  get(path, params, options) {
    return this.request(path, Object.assign({}, options || {}, { params }));
  },
  post(path, body, params) {
    return this.request(path, { method: "POST", body, params });
  },
};

/* ---------- DOM helper (always escapes text via textContent) ---------- */
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([key, value]) => {
    if (value === null || value === undefined || value === false) return;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else el.setAttribute(key, value);
  });
  children.flat(Infinity).forEach((child) => {
    if (child === null || child === undefined || child === false) return;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  });
  return el;
}

/* ---------- shared UI bits ---------- */
function statusClass(status) {
  const s = String(status || "").toLowerCase();
  return ["green", "yellow", "red"].includes(s) ? `is-${s}` : "";
}

function kpi(label, value, cls, sub) {
  return h(
    "div",
    { class: "kpi" },
    h("div", { class: "kpi-label", text: label }),
    h("div", { class: `kpi-value ${cls || ""}`, text: value == null ? "—" : String(value) }),
    h("div", { class: "kpi-sub", text: sub || "" })
  );
}

function kv(label, value, mono) {
  return h(
    "div",
    { class: "kv" },
    h("span", { class: "k", text: label }),
    h("span", { class: `v ${mono ? "mono" : ""}`, text: value == null ? "—" : String(value) })
  );
}

function errorCard(title, err) {
  const message = err ? `${err.code || "error"}: ${err.message || String(err)}` : "No details available.";
  return h("div", { class: "error-card" }, h("h3", { text: title }), h("p", { text: message }));
}

function loading(text) {
  return h("div", { class: "loading", "aria-busy": "true", text });
}

async function withBusy(button, busyLabel, task) {
  if (!button) return task();
  const original = button.textContent;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.textContent = busyLabel;
  try {
    return await task();
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    button.textContent = original;
  }
}

function copyButton(getText) {
  const label = h("span", { text: "Copy", "aria-live": "polite" });
  const button = h("button", { class: "btn btn-ghost copy-btn", type: "button" }, label);
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(getText());
      label.textContent = "Copied";
    } catch {
      label.textContent = "Copy failed";
    }
    setTimeout(() => { label.textContent = "Copy"; }, 1400);
  });
  return button;
}

function setFieldError(input, errorId, message) {
  const error = document.getElementById(errorId);
  if (input) {
    if (message) input.setAttribute("aria-invalid", "true");
    else input.removeAttribute("aria-invalid");
  }
  if (error) error.textContent = message || "";
}

function validateJsonInput(input, errorId, label) {
  if (!input) return true;
  const text = input.value.trim();
  let message = "";
  if (!text) {
    message = `${label} is required.`;
  } else {
    try {
      JSON.parse(text);
    } catch (err) {
      message = `Invalid JSON: ${err.message}`;
    }
  }
  setFieldError(input, errorId, message);
  return !message;
}

function setStatusPill(status) {
  const pill = document.getElementById("cluster-pill");
  if (!pill) return;
  const label = pill.querySelector(".pill-label");
  const s = String(status || "unknown").toLowerCase();
  pill.classList.remove("is-green", "is-yellow", "is-red", "is-unknown");
  pill.classList.add(["green", "yellow", "red"].includes(s) ? `is-${s}` : "is-unknown");
  if (label) {
    if (s === "green") label.textContent = "healthy";
    else if (s === "yellow") label.textContent = "yellow";
    else if (s === "red") label.textContent = "offline";
    else label.textContent = "checking…";
  }
}

/* ---------- dashboard ---------- */
const state = { dashboardLoaded: false };

function indexCard(idx, status) {
  if (!idx) return h("div", { class: "card empty" }, "Configured index not found on the cluster.");
  return h(
    "div",
    { class: "card" },
    h(
      "div",
      { class: "card-head" },
      h("h3", { text: "Configured index" }),
      h("span", { class: `tag tag-${status === "unknown" ? "" : status}`, text: idx.health || "unknown" })
    ),
    h(
      "div",
      { class: "kv-grid" },
      kv("Index", idx.index, true),
      kv("Documents", idx.docs != null ? Number(idx.docs).toLocaleString() : "—"),
      kv("Store size", idx.store || "—"),
      kv("Shards", `${idx.pri ?? "—"} primary / ${idx.rep ?? "—"} replica`),
      kv("Index status", idx.status || "—"),
      kv("Cluster status", status),
      kv("Configured", idx.configured ? "yes" : "no")
    )
  );
}

function yellowCard(health) {
  const unassigned = health.unassigned_shards ?? 0;
  const primaries = health.active_primary_shards ?? 0;
  return h(
    "div",
    { class: "card note" },
    h("div", { class: "card-head" }, h("h3", { text: "Why is the cluster yellow?" })),
    h("p", {
      text:
        `A 1-primary/1-replica index on a single node cannot allocate its replica. ` +
        `Currently ${unassigned} shard(s) are unassigned cluster-wide while ${primaries} primaries are active. ` +
        `This is expected for a single-node teaching setup, not an application failure.`,
    })
  );
}

function capabilitiesCard(caps, capsError) {
  if (!caps) return errorCard("Capabilities unavailable", capsError);
  const features = (caps.capabilities && caps.capabilities.features) || {};
  const entries = Object.entries(features);
  const grid = h(
    "div",
    { class: "caps-grid" },
    ...entries.map(([name, feature]) =>
      h(
        "div",
        { class: `cap ${feature.available ? "is-on" : "is-off"}` },
        h("span", { class: "cap-dot" }),
        h(
          "div",
          { class: "cap-body" },
          h("div", { class: "cap-name" }, h("code", { text: name })),
          h("div", { class: "cap-reason", text: feature.available ? "supported" : "unsupported" }),
          h("div", {
            class: "cap-detail",
            text: feature.available ? "Allowed by the read-only explorer." : feature.reason || "Blocked by the read-only explorer.",
          })
        )
      )
    )
  );
  return h(
    "div",
    { class: "card" },
    h("div", { class: "card-head" }, h("h3", { text: "Detected capabilities" })),
    h("p", {
      class: "muted small",
      text: caps.ready
        ? "Computed from live _mapping (display-only objects) and _field_caps (queryable fields)."
        : "Discovery is incomplete; capabilities may be partial.",
    }),
    grid
  );
}

function renderDashboard(root, ctx) {
  root.replaceChildren();
  if (!ctx.health) {
    root.append(errorCard("Backend unreachable", ctx.healthError));
    return;
  }
  const { health, caps } = ctx;
  const cluster = health.cluster || {};
  const idx = (health.indices || [])[0] || null;
  const status = String(cluster.status || "unavailable").toLowerCase();

  root.append(
    h(
      "div",
      { class: "kpi-grid" },
      kpi(
        "Documents",
        idx && idx.docs != null ? Number(idx.docs).toLocaleString() : "—",
        "",
        "in the configured index"
      ),
      kpi("Store size", idx && idx.store ? idx.store : "—", "", "configured index storage"),
      kpi(
        "Primary shards",
        idx && idx.pri != null ? idx.pri : "—",
        "",
        `${idx && idx.rep != null ? idx.rep : "—"} replica(s) configured`
      ),
      kpi(
        "Unassigned shards",
        health.unassigned_shards ?? "—",
        health.unassigned_shards ? "is-warn" : "is-green",
        `${health.active_primary_shards ?? "—"} active primaries · cluster ${status}`
      )
    ),
    h("div", { class: "grid-2" }, indexCard(idx, status), yellowCard(health)),
    capabilitiesCard(caps, ctx.capsError)
  );

  const errs = Object.entries(health.errors || {});
  if (errs.length) {
    root.append(
      h(
        "div",
        { class: "error-card" },
        h("h3", { text: "Degraded discovery" }),
        h("p", { text: "Some startup calls did not complete; the app is running in degraded mode." }),
        h(
          "ul",
          {},
          ...errs.map(([key, value]) => h("li", {}, h("code", { text: key }), ` — ${value}`))
        )
      )
    );
  }
  if (health.discovered_at) {
    root.append(h("p", { class: "muted small", text: `Discovered at ${health.discovered_at}` }));
  }
}

async function loadDashboard(force = false) {
  const body = document.getElementById("dashboard-body");
  if (!body) return;
  if (!state.dashboardLoaded || force) {
    body.replaceChildren(loading("Loading cluster facts…"));
  }
  const [health, config, caps] = await Promise.allSettled([
    API.get("/api/health"),
    API.get("/api/config"),
    API.get("/api/capabilities"),
  ]);

  const configData = config.status === "fulfilled" ? config.value && config.value.data : null;
  if (configData && configData.host) {
    const host = document.getElementById("es-host");
    if (host) host.textContent = configData.host;
  }

  const healthData = health.status === "fulfilled" ? health.value : null;
  setStatusPill(healthData ? (healthData.cluster || {}).status : "unavailable");

  renderDashboard(body, {
    health: healthData,
    caps: caps.status === "fulfilled" ? caps.value : null,
    healthError: health.status === "rejected" ? health.reason : null,
    capsError: caps.status === "rejected" ? caps.reason : null,
  });
  state.dashboardLoaded = true;
}

/* ---------- projects ---------- */
let projectsLoaded = false;
let suggestTimer = null;

function isSafeUrl(value) {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

function queryDetails(queryUsed, label = "Query used") {
  if (!queryUsed) return document.createTextNode("");
  const pre = h("pre", { text: JSON.stringify(queryUsed, null, 2) });
  return h(
    "details",
    { class: "details" },
    h("summary", { text: label }),
    h("div", { class: "code-actions" }, copyButton(() => pre.textContent)),
    pre
  );
}

function renderHighlighted(text, fragments) {
  const raw = Array.isArray(fragments) && fragments.length ? fragments[0] : text;
  if (raw == null) return document.createTextNode("—");
  const parts = [];
  const regex = /\[\[HL\]\]([\s\S]*?)\[\[\/HL\]\]/g;
  let last = 0;
  let match;
  while ((match = regex.exec(raw)) !== null) {
    if (match.index > last) parts.push(document.createTextNode(raw.slice(last, match.index)));
    parts.push(h("mark", {}, match[1]));
    last = regex.lastIndex;
  }
  if (last < raw.length) parts.push(document.createTextNode(raw.slice(last)));
  return h("span", {}, ...parts);
}

function fillSelect(id, buckets, placeholder) {
  const el = document.getElementById(id);
  if (!el) return;
  const options = [h("option", { value: "", text: placeholder })];
  (buckets || []).forEach((bucket) => {
    options.push(h("option", { value: bucket.key, text: `${bucket.key} (${bucket.doc_count})` }));
  });
  el.replaceChildren(...options);
}

function renderFacets(facets) {
  const body = document.getElementById("facets-body");
  if (!body) return;
  const groups = [
    ["Districts", "districts", 20, "f-district"],
    ["Project types", "project_types", 20, "f-type"],
    ["Statuses", "project_statuses", 20, "f-status"],
    ["Top promoters", "promoters", 10, "f-promoter"],
    ["Prices", "prices", 10, "f-price"],
  ];
  body.replaceChildren(
    ...groups.map(([title, key, limit, selectId]) => {
      const buckets = ((facets[key] || {}).buckets || []).slice(0, limit);
      return h(
        "div",
        { class: "facet-group" },
        h("div", { class: "facet-title", text: title }),
        h(
          "ul",
          { class: "facet-list" },
          ...buckets.map((bucket) =>
            h(
              "li",
              {},
              h(
                "button",
                {
                  class: "facet-item",
                  type: "button",
                  onclick: () => {
                    const select = document.getElementById(selectId);
                    if (select) select.value = bucket.key;
                    runSearch();
                  },
                },
                h("span", { class: "facet-key", text: bucket.key }),
                h("span", { class: "facet-count", text: String(bucket.doc_count) })
              )
            )
          )
        )
      );
    })
  );
}

async function loadFacets() {
  const body = document.getElementById("facets-body");
  if (body) body.replaceChildren(h("div", { class: "facets-loading", text: "Loading facets…" }));
  try {
    const res = await API.get("/api/projects/facets");
    const facets = (res.data && res.data.facets) || {};
    fillSelect("f-district", facets.districts && facets.districts.buckets, "All districts");
    fillSelect("f-taluka", facets.talukas && facets.talukas.buckets, "All talukas");
    fillSelect("f-type", facets.project_types && facets.project_types.buckets, "All types");
    fillSelect("f-status", facets.project_statuses && facets.project_statuses.buckets, "All statuses");
    fillSelect("f-promoter", facets.promoters && facets.promoters.buckets, "All promoters");
    fillSelect("f-price", facets.prices && facets.prices.buckets, "Any price");
    renderFacets(facets);
  } catch (err) {
    if (body) body.replaceChildren(errorCard("Facets unavailable", err));
  }
}

function collectSearchParams() {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : "";
  };
  const params = {};
  const map = {
    q: "q",
    "f-district": "district",
    "f-taluka": "taluka",
    "f-type": "project_type",
    "f-status": "project_status",
    "f-promoter": "promoter",
    "f-price": "price",
    "f-price-prefix": "price_prefix",
    "f-start-from": "start_from",
    "f-start-to": "start_to",
    "f-end-from": "end_from",
    "f-end-to": "end_to",
    "f-min-docs": "min_documents",
    "f-max-docs": "max_documents",
    "f-complete": "scrape_complete",
    "f-downloaded": "docs_downloaded",
    "f-sort": "sort",
    "f-size": "size",
  };
  Object.entries(map).forEach(([id, key]) => {
    const value = val(id);
    if (value !== "") params[key] = value;
  });
  if (!params.size) params.size = "20";
  return params;
}

function resultsTable(hits) {
  if (!hits || !hits.length) {
    return h("div", { class: "placeholder", text: "No projects matched these filters." });
  }
  const columns = ["ID", "Project", "District", "Taluka", "Type", "Status", "Price", "Start", "End", "Docs"];
  const rows = hits.map((hit) => {
    const docs = hit.scrape_status && hit.scrape_status.documents;
    const name = hit.project_name || "—";
    const open = () => openDetail(hit._id || hit.projectId);
    return h(
      "tr",
      { class: "row-click", onclick: open },
      h("td", { class: "mono", text: String(hit._id || hit.projectId || "—") }),
      h("td", { class: "truncate", title: String(name) }, renderHighlighted(hit.project_name, hit.highlight && hit.highlight.project_name)),
      h("td", { text: hit.district || "—" }),
      h("td", { text: hit.taluka || "—" }),
      h("td", { text: hit.project_type || "—" }),
      h("td", { text: hit.project_status || "—" }),
      h("td", { class: "num", text: hit.price || "—" }),
      h("td", { text: hit.start_date || "—" }),
      h("td", { text: hit.end_date || "—" }),
      h("td", { class: "num", text: docs == null ? "—" : String(docs) })
    );
  });
  return h(
    "div",
    { class: "table-wrap" },
    h(
      "table",
      { class: "data-table" },
      h("thead", {}, h("tr", {}, ...columns.map((c) => h("th", { text: c })))),
      h("tbody", {}, ...rows)
    )
  );
}

async function runSearch() {
  const results = document.getElementById("projects-results");
  const metaEl = document.getElementById("projects-meta");
  const queryEl = document.getElementById("projects-query");
  if (!results) return;
  results.replaceChildren(loading("Searching…"));
  if (metaEl) metaEl.replaceChildren();
  if (queryEl) queryEl.replaceChildren();
  try {
    const res = await API.get("/api/projects/search", collectSearchParams());
    const meta = res.meta || {};
    const hits = (res.data && res.data.hits) || [];
    if (metaEl) {
      metaEl.replaceChildren(
        h("span", { class: "meta-item" }, h("strong", { text: Number(meta.total || 0).toLocaleString() }), " matches"),
        h("span", { class: "meta-item", text: `returned ${meta.returned ?? hits.length}` }),
        h("span", { class: "meta-item" }, h("code", { text: "es_took_ms" }), " ", String(meta.es_took_ms ?? "—")),
        h("span", { class: "meta-item" }, h("code", { text: "wall_ms" }), " ", String(meta.wall_ms ?? "—"))
      );
    }
    results.replaceChildren(resultsTable(hits));
    if (queryEl) queryEl.replaceChildren(queryDetails(meta.query_used));
  } catch (err) {
    results.replaceChildren(errorCard("Search failed", err));
  }
}

function resetProjects() {
  const form = document.getElementById("projects-form");
  if (form) form.reset();
  const size = document.getElementById("f-size");
  if (size) size.value = "20";
  runSearch();
}

function ensureProjects() {
  if (projectsLoaded) return;
  projectsLoaded = true;
  loadFacets();
  runSearch();
}

function initSuggest() {
  const input = document.getElementById("q");
  const box = document.getElementById("suggest-box");
  if (!input || !box) return;
  let items = [];
  let activeIndex = -1;

  const close = () => {
    clearTimeout(suggestTimer);
    items = [];
    activeIndex = -1;
    box.hidden = true;
    box.replaceChildren();
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  };

  const setActive = (index) => {
    if (!items.length) return;
    activeIndex = (index + items.length) % items.length;
    const nodes = Array.from(box.querySelectorAll(".suggest-item"));
    nodes.forEach((node, i) => {
      const active = i === activeIndex;
      node.classList.toggle("is-active", active);
      node.setAttribute("aria-selected", active ? "true" : "false");
    });
    input.setAttribute("aria-activedescendant", `suggest-item-${activeIndex}`);
    if (nodes[activeIndex]) nodes[activeIndex].scrollIntoView({ block: "nearest" });
  };

  const choose = (item) => {
    const id = item.id ?? item.projectId ?? item._id;
    input.value = item.label || item.project_name || "";
    close();
    if (id !== undefined && id !== null && id !== "") openDetail(id);
    else runSearch();
  };

  input.addEventListener("input", () => {
    clearTimeout(suggestTimer);
    const q = input.value.trim();
    if (q.length < 2) {
      close();
      return;
    }
    suggestTimer = setTimeout(async () => {
      try {
        const res = await API.get("/api/projects/suggest", { q, size: 8 });
        items = (res.data && res.data.suggestions) || [];
        if (!items.length) {
          close();
          return;
        }
        box.replaceChildren(
          ...items.map((item, index) =>
            h(
              "button",
              {
                id: `suggest-item-${index}`,
                class: "suggest-item",
                type: "button",
                role: "option",
                "aria-selected": "false",
                onclick: () => choose(item),
              },
              h("span", { class: "suggest-name", text: item.label || item.project_name || "—" }),
              h("span", {
                class: "suggest-meta",
                text: [item.match_label, item.meta].filter(Boolean).join(" · "),
              })
            )
          )
        );
        box.hidden = false;
        input.setAttribute("aria-expanded", "true");
        setActive(0);
      } catch {
        close();
      }
    }, 300);
  });

  input.addEventListener("keydown", (event) => {
    if (box.hidden || !items.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive(activeIndex + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive(activeIndex - 1);
    } else if (event.key === "Enter") {
      event.preventDefault();
      choose(items[activeIndex >= 0 ? activeIndex : 0]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      close();
    }
  });

  document.addEventListener("click", (event) => {
    if (!box.contains(event.target) && event.target !== input) close();
  });
}

/* ---------- project detail ---------- */
function isPrimitive(value) {
  return value === null || ["string", "number", "boolean"].includes(typeof value);
}

function isComplex(value) {
  if (value === null || typeof value !== "object") return false;
  if (Array.isArray(value)) return !value.every(isPrimitive);
  return true;
}

function renderPrimitive(value) {
  if (value === null || value === undefined) return document.createTextNode("—");
  if (typeof value === "string" && isSafeUrl(value)) {
    return h("a", { href: value, target: "_blank", rel: "noopener noreferrer", text: value });
  }
  return document.createTextNode(String(value));
}

function summaryFor(value) {
  if (Array.isArray(value)) return `array (${value.length})`;
  return `object (${Object.keys(value || {}).length} keys)`;
}

function renderValue(value, depth = 0) {
  if (isPrimitive(value)) return renderPrimitive(value);
  if (depth > 7) return h("span", { class: "muted", text: "…" });
  if (Array.isArray(value)) {
    if (!value.length) return document.createTextNode("—");
    if (value.every(isPrimitive)) {
      return document.createTextNode(value.map((v) => (v == null ? "" : String(v))).join(", "));
    }
    const shown = value.slice(0, 50);
    return h(
      "div",
      { class: "nested-list" },
      ...shown.map((item, index) =>
        h(
          "details",
          { class: "nested" },
          h("summary", { text: `item ${index + 1}` }),
          h("div", { class: "nested-body" }, renderValue(item, depth + 1))
        )
      ),
      value.length > shown.length
        ? h("p", { class: "muted small", text: `Showing first ${shown.length} of ${value.length}.` })
        : null
    );
  }
  return h(
    "div",
    { class: "kv-table" },
    ...Object.entries(value).map(([key, val]) => renderRow(key, val, depth + 1))
  );
}

function renderRow(key, value, depth) {
  const cell = isComplex(value)
    ? h(
        "details",
        { class: "nested" },
        h("summary", { text: summaryFor(value) }),
        h("div", { class: "nested-body" }, renderValue(value, depth + 1))
      )
    : h("div", { class: "row-val" }, renderPrimitive(value));
  return h("div", { class: "kv-row" }, h("div", { class: "row-key", text: key }), cell);
}

function renderObject(obj, depth = 0) {
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return renderValue(obj, depth);
  return h(
    "div",
    { class: "kv-table" },
    ...Object.entries(obj).map(([key, value]) => renderRow(key, value, depth + 1))
  );
}

function renderArrayTable(items) {
  if (!Array.isArray(items) || !items.length) {
    return h("p", { class: "muted small", text: "No records." });
  }
  const objects = items.filter((x) => x && typeof x === "object" && !Array.isArray(x));
  if (objects.length !== items.length) return renderValue(items);
  const keys = Array.from(new Set(objects.flatMap((o) => Object.keys(o)))).slice(0, 10);
  const shown = items.slice(0, 100);
  return h(
    "div",
    { class: "table-wrap" },
    h(
      "table",
      { class: "data-table compact" },
      h("thead", {}, h("tr", {}, ...keys.map((k) => h("th", { text: k })))),
      h(
        "tbody",
        {},
        ...shown.map((row) => h("tr", {}, ...keys.map((k) => h("td", {}, renderValue(row[k], 1)))))
      )
    ),
    items.length > shown.length
      ? h("p", { class: "muted small", text: `Showing first ${shown.length} of ${items.length} records.` })
      : null
  );
}

function renderSectionCard(name, section) {
  const data = section && section.data;
  const content = Array.isArray(data) ? renderArrayTable(data) : renderObject(data);
  return h(
    "div",
    { class: "card section-card" },
    h(
      "div",
      { class: "card-head" },
      h("h3", { text: name }),
      h("span", { class: "tag tag-muted", text: "not indexed" })
    ),
    content
  );
}

function sourceLink(url) {
  if (!isSafeUrl(url)) return null;
  return h(
    "p",
    { class: "link-row" },
    "Source: ",
    h("a", { href: url, target: "_blank", rel: "noopener noreferrer", text: url })
  );
}

function mapLink(sections) {
  const profile = sections && sections["Project Profile"];
  const locations = profile && profile.data && profile.data["Map Location"];
  if (!Array.isArray(locations) || !locations.length) return null;
  const first = locations[0] || {};
  const lat = parseFloat(first.lat);
  const lng = parseFloat(first.lng);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  if (Math.abs(lat) > 90 || Math.abs(lng) > 180) return null;
  const url = `https://www.google.com/maps?q=${lat},${lng}`;
  return h(
    "p",
    { class: "link-row" },
    "Map: ",
    h("a", { href: url, target: "_blank", rel: "noopener noreferrer", text: `${lat}, ${lng}` })
  );
}

function renderDetail(root, res) {
  const data = res.data || {};
  const project = data.project || {};
  const meta = res.meta || {};
  const sections = data.sections || {};
  root.replaceChildren();

  const coreCard = h(
    "div",
    { class: "card" },
    h(
      "div",
      { class: "card-head" },
      h("h3", { text: project.project_name || `Project ${project.projectId ?? ""}` }),
      project.project_status ? h("span", { class: "tag", text: project.project_status }) : null
    ),
    h(
      "div",
      { class: "kv-grid" },
      kv("projectId", project.projectId, true),
      kv("Reg no", project.reg_no, true),
      kv("Promoter", project.promoter_name),
      kv("District", project.district),
      kv("Taluka", project.taluka),
      kv("Type", project.project_type),
      kv("Status", project.project_status),
      kv("Price", project.price),
      kv("Start date", project.start_date),
      kv("End date", project.end_date),
      kv("Documents", project.scrape_status && project.scrape_status.documents)
    ),
    sourceLink(project.page_url),
    mapLink(sections),
    h("p", {
      class: "muted small",
      text: `Lookup: ${data.lookup || "get_doc"} · es_took_ms ${meta.es_took_ms ?? "—"} · wall_ms ${meta.wall_ms ?? "—"}`,
    })
  );

  const sectionCards = Object.entries(sections).map(([name, section]) => renderSectionCard(name, section));

  const rawToggle = queryDetails(data.raw || {}, "Raw _source JSON");

  root.append(coreCard, ...sectionCards, rawToggle, queryDetails(meta.query_used));
}

async function loadDetail(projectId) {
  const body = document.getElementById("detail-body");
  if (!body) return;
  body.replaceChildren(loading(`Loading project ${projectId}…`));
  try {
    const res = await API.get(`/api/projects/${encodeURIComponent(projectId)}`);
    renderDetail(body, res);
  } catch (err) {
    body.replaceChildren(errorCard(`Could not load project ${projectId}`, err));
  }
}

function openDetail(projectId) {
  const tab = Array.from(document.querySelectorAll(".tab")).find((t) => t.dataset.tab === "detail");
  if (tab) tab.click();
  const idInput = document.getElementById("detail-id");
  if (idInput) idInput.value = projectId;
  loadDetail(projectId);
}

/* ---------- analytics (Chart.js with table fallback) ---------- */
function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

const CHART_PALETTE = [
  ["--accent", "#0284c7"],
  ["--green", "#059669"],
  ["--yellow", "#d97706"],
  ["--cyan", "#0891b2"],
  ["--orange", "#ea580c"],
  ["--pink", "#db2777"],
  ["--lime", "#65a30d"],
  ["--indigo", "#4f46e5"],
].map(([name, fallback]) => cssVar(name, fallback));
let analyticsLoaded = false;
let chartInstances = [];
let pendingCharts = [];

function destroyCharts() {
  chartInstances.forEach((chart) => {
    try { chart.destroy(); } catch { /* already gone */ }
  });
  chartInstances = [];
}

function chartConfig(labels, values, opts = {}) {
  return {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: opts.label || "documents",
          data: values,
          backgroundColor: labels.map((_, i) => CHART_PALETTE[i % CHART_PALETTE.length]),
          borderRadius: 5,
          maxBarThickness: opts.horizontal ? 18 : 34,
        },
      ],
    },
    options: {
      indexAxis: opts.horizontal ? "y" : "x",
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          intersect: false,
          backgroundColor: cssVar("--text", "#0f172a"),
          borderColor: cssVar("--border", "#cbd5e1"),
          borderWidth: 1,
          titleColor: cssVar("--bg-elev", "#ffffff"),
          bodyColor: cssVar("--bg-elev-2", "#f8fafc"),
        },
      },
      scales: {
        x: {
          beginAtZero: true,
          ticks: { color: cssVar("--text-dim", "#334155"), maxRotation: 45, minRotation: 0, autoSkip: true },
          grid: { color: cssVar("--chart-grid", "rgba(148, 163, 184, 0.25)") },
        },
        y: {
          beginAtZero: true,
          ticks: { color: cssVar("--text-dim", "#334155"), autoSkip: true },
          grid: { color: cssVar("--chart-grid", "rgba(148, 163, 184, 0.25)") },
        },
      },
    },
  };
}

function fallbackTable(labels, values, hidden = false) {
  return h(
    "div",
    { class: "table-wrap fallbackTable", hidden },
    h(
      "table",
      { class: "data-table compact" },
      h("thead", {}, h("tr", {}, h("th", { text: "Key" }), h("th", { class: "num", text: "Count" }))),
      h(
        "tbody",
        {},
        ...labels.map((label, i) => h("tr", {}, h("td", { text: label }), h("td", { class: "num", text: Number(values[i]).toLocaleString() })))
      )
    )
  );
}

function chartCard(title, labels, values, opts = {}) {
  const card = h(
    "div",
    { class: "card chart-card" },
    h(
      "div",
      { class: "card-head" },
      h("h3", { text: title }),
      h("span", { class: "tag tag-muted", text: `${values.length} buckets` })
    )
  );
  const table = fallbackTable(labels, values, Boolean(window.Chart && labels.length));
  if (!labels.length) {
    card.append(h("p", { class: "muted small", text: "No buckets returned." }), table);
  } else if (window.Chart) {
    const wrap = h("div", { class: "chart-wrap" });
    const canvas = document.createElement("canvas");
    wrap.append(canvas);
    card.append(wrap, table);
    pendingCharts.push({ canvas, labels, values, opts });
  } else {
    card.append(table);
  }
  return card;
}

function flushCharts() {
  if (!window.Chart) {
    pendingCharts = [];
    return;
  }
  pendingCharts.splice(0).forEach(({ canvas, labels, values, opts }) => {
    try {
      chartInstances.push(new window.Chart(canvas, chartConfig(labels, values, opts)));
    } catch {
      /* a single broken chart should not blank the tab */
    }
  });
}

function bucketsToXY(buckets) {
  const list = buckets || [];
  return { labels: list.map((b) => String(b.key)), values: list.map((b) => b.doc_count || 0) };
}

function dateBucketsToXY(buckets) {
  const list = buckets || [];
  return {
    labels: list.map((b) => String(b.key_as_string || b.key)),
    values: list.map((b) => b.doc_count || 0),
  };
}

function boolCount(buckets, truthy) {
  const target = truthy ? "true" : "false";
  const bucket = (buckets || []).find((b) => String(b.key_as_string ?? b.key).toLowerCase() === target);
  return bucket ? bucket.doc_count : 0;
}

function fmtNumber(value) {
  return value == null ? "—" : Number(value).toLocaleString();
}

function renderAnalytics(root, ctx) {
  destroyCharts();
  pendingCharts = [];
  root.replaceChildren();
  if (!ctx.overview || !ctx.dates) {
    root.append(errorCard("Analytics unavailable", ctx.overviewError || ctx.datesError));
    return;
  }
  const aggs = ((ctx.overview.data || {}).aggregations) || {};
  const stats = (ctx.overview.data || {}).documents_stats || aggs.documents_stats || {};
  const dateAggs = ((ctx.dates.data || {}).aggregations) || {};
  const downloaded = (aggs.docs_downloaded || {}).buckets || [];

  root.append(
    h(
      "div",
      { class: "kpi-grid" },
      kpi("Documents", fmtNumber(stats.count), "", "documents field present"),
      kpi("Average documents", stats.avg != null ? Math.round(stats.avg).toLocaleString() : "—", "", "per project"),
      kpi("Max documents", fmtNumber(stats.max), "", "single project"),
      kpi("Docs downloaded", fmtNumber(boolCount(downloaded, true)), "", "scrape_status.docs_downloaded")
    )
  );

  const grid = h("div", { class: "charts-grid" });
  grid.append(
    chartCard("Projects by district", ...Object.values(bucketsToXY((aggs.districts || {}).buckets)), { horizontal: true, label: "projects" }),
    chartCard("Projects by taluka", ...Object.values(bucketsToXY((aggs.talukas || {}).buckets)), { horizontal: true, label: "projects" }),
    chartCard("Projects by status", ...Object.values(bucketsToXY((aggs.project_statuses || {}).buckets)), { label: "projects" }),
    chartCard("Projects by type", ...Object.values(bucketsToXY((aggs.project_types || {}).buckets)), { label: "projects" }),
    chartCard("Registrations by year (start date)", ...Object.values(dateBucketsToXY((dateAggs.start_years || {}).buckets)), { label: "projects" }),
    chartCard("Start dates by year", ...Object.values(dateBucketsToXY((dateAggs.end_years || {}).buckets)), { label: "projects" })
  );
  if (!window.Chart) {
    root.append(
      h("p", {
        class: "muted small",
        text: "Chart.js could not load (offline?). Bucket values are shown as tables instead.",
      })
    );
  }
  root.append(
    grid,
    h(
      "div",
      { class: "card note" },
      h("div", { class: "card-head" }, h("h3", { text: "Date coverage caveat" })),
      h("p", {
        text: "Yearly histograms cover well-formed dd-MM-yyyy values only. Malformed or empty dates are excluded rather than coerced, so these charts show coverage of valid dates rather than total dataset completeness.",
      })
    )
  );
  flushCharts();
}

async function loadAnalytics(force = false) {
  const body = document.getElementById("analytics-body");
  if (!body) return;
  if (analyticsLoaded && !force) return;
  body.replaceChildren(loading("Loading analytics…"));
  const [overview, dates] = await Promise.allSettled([
    API.get("/api/analytics/overview"),
    API.get("/api/analytics/dates"),
  ]);
  renderAnalytics(body, {
    overview: overview.status === "fulfilled" ? overview.value : null,
    dates: dates.status === "fulfilled" ? dates.value : null,
    overviewError: overview.status === "rejected" ? overview.reason : null,
    datesError: dates.status === "rejected" ? dates.reason : null,
  });
  analyticsLoaded = true;
}

/* ---------- data quality ---------- */
const MISSING_LABELS = {
  missing_price: "price",
  missing_district: "district",
  missing_taluka: "taluka",
  missing_start_date: "start_date",
  missing_end_date: "end_date",
  missing_promoter: "promoter_name.keyword",
  missing_reg_no: "reg_no",
};
let qualityLoaded = false;

function missingCard(missing, total) {
  const rows = Object.entries(MISSING_LABELS).map(([key, label]) => {
    const count = missing[key];
    const pct = total ? ((count || 0) / total) * 100 : null;
    return h(
      "tr",
      {},
        h("td", {}, h("code", { text: label })),
        h("td", { class: "num", text: fmtNumber(count) }),
        h("td", { class: "num", text: pct != null ? `${pct.toFixed(2)}%` : "—" })
    );
  });
  return h(
    "div",
    { class: "card" },
    h("div", { class: "card-head" }, h("h3", { text: "Missing fields" })),
    h(
      "div",
      { class: "table-wrap" },
      h(
        "table",
        { class: "data-table compact" },
          h("thead", {}, h("tr", {}, h("th", { text: "Field" }), h("th", { class: "num", text: "Missing" }), h("th", { class: "num", text: "% of docs" }))),
        h("tbody", {}, ...rows)
      )
    )
  );
}

function scrapeCard(aggs) {
  const downloaded = (aggs.docs_downloaded || {}).buckets || [];
  const stats = aggs.documents_stats || {};
  const errors = (aggs.with_errors || {}).doc_count;
  return h(
    "div",
    { class: "card" },
    h("div", { class: "card-head" }, h("h3", { text: "Scrape coverage" })),
    h(
      "div",
      { class: "kv-grid" },
      kv("docs_downloaded = true", fmtNumber(boolCount(downloaded, true))),
      kv("docs_downloaded = false", fmtNumber(boolCount(downloaded, false))),
      kv("Docs with errors", fmtNumber(errors)),
      kv("documents count", fmtNumber(stats.count)),
      kv("min / max", `${fmtNumber(stats.min)} / ${fmtNumber(stats.max)}`),
      kv("avg / sum", `${stats.avg != null ? Math.round(stats.avg).toLocaleString() : "—"} / ${fmtNumber(stats.sum)}`)
    )
  );
}

function collisionsCard(title, list) {
  const card = h(
    "div",
    { class: "card" },
    h(
      "div",
      { class: "card-head" },
      h("h3", { text: title }),
      h("span", { class: "tag tag-muted", text: `${list.length} group(s)` })
    )
  );
  if (!list.length) {
    card.append(h("p", { class: "muted small", text: "No case/space variants detected." }));
    return card;
  }
  card.append(
    h(
      "div",
      { class: "collision-list" },
      ...list.slice(0, 20).map((group) =>
        h(
          "div",
          { class: "collision" },
          h(
            "div",
            { class: "collision-head" },
            h("code", { text: group.normalized }),
            h("span", { class: "tag tag-warn", text: `${group.total} docs` })
          ),
          h(
            "div",
            { class: "collision-variants" },
            ...group.variants.map((variant) =>
              h("span", { class: "variant" }, h("code", { text: variant.key }), h("span", { class: "small muted", text: ` ${variant.doc_count}` }))
            )
          )
        )
      )
    )
  );
  return card;
}

function renderQuality(res) {
  const data = res.data || {};
  const aggs = data.aggregations || {};
  const missing = data.missing || {};
  const total = data.total_docs;
  const downloaded = (aggs.docs_downloaded || {}).buckets || [];
  const errors = (aggs.with_errors || {}).doc_count;
  const stats = aggs.documents_stats || {};

  const summary = document.getElementById("quality-summary");
  if (summary) {
    summary.replaceChildren(
      h(
        "div",
        { class: "kpi-grid" },
        kpi("Documents", fmtNumber(total), "", "total in index"),
        kpi("Missing price", fmtNumber(missing.missing_price), "", "key data gap"),
        kpi("Missing start date", fmtNumber(missing.missing_start_date), "", "excluded from histograms"),
        kpi("Docs downloaded", fmtNumber(boolCount(downloaded, true)), "", "scrape_status.docs_downloaded"),
        kpi("Scrape errors", fmtNumber(errors), "", "documents with an errors field")
      ),
      h("p", {
        class: "muted small",
        text: `es_took_ms ${(res.meta || {}).es_took_ms ?? "—"} · wall_ms ${(res.meta || {}).wall_ms ?? "—"} · avg documents ${stats.avg != null ? Math.round(stats.avg).toLocaleString() : "—"}`,
      })
    );
  }

  const missingEl = document.getElementById("quality-missing");
  if (missingEl) missingEl.replaceChildren(missingCard(missing, total));

  const scrapeEl = document.getElementById("quality-scrape");
  if (scrapeEl) scrapeEl.replaceChildren(scrapeCard(aggs));

  const collEl = document.getElementById("quality-collisions");
  const collisions = data.casing_collisions || {};
  if (collEl) {
    collEl.replaceChildren(
      h(
        "div",
        { class: "grid-2" },
        collisionsCard("District casing collisions", collisions.districts || []),
        collisionsCard("Taluka casing collisions", collisions.talukas || [])
      )
    );
  }
}

async function loadQuality(force = false) {
  const summary = document.getElementById("quality-summary");
  if (!summary) return;
  if (qualityLoaded && !force) return;
  summary.replaceChildren(loading("Loading quality checks…"));
  try {
    const res = await API.get("/api/quality/scrape");
    renderQuality(res);
    qualityLoaded = true;
  } catch (err) {
    summary.replaceChildren(errorCard("Data quality unavailable", err));
  }
}

async function runPipeline() {
  const input = document.getElementById("pipeline-source");
  const out = document.getElementById("pipeline-output");
  if (!out || !input || !validateJsonInput(input, "pipeline-error", "Pipeline source JSON")) return;
  const source = JSON.parse(input.value);
  out.replaceChildren(loading("Simulating…"));
  try {
    const res = await API.post("/api/quality/pipeline-simulate", { source });
    const data = res.data || {};
    out.replaceChildren(
      h("p", {
        class: "muted small",
        text: `Pipeline: ${data.pipeline_id || "—"} · wall_ms ${(res.meta || {}).wall_ms ?? "—"}`,
      }),
      queryDetails(data.result || {}, "Simulation result"),
      queryDetails((res.meta || {}).query_used)
    );
  } catch (err) {
    if (err.code === "pipeline_missing") {
      out.replaceChildren(
        h(
          "div",
          { class: "card note" },
          h("h3", { text: "Pipeline is not installed" }),
          h("p", { text: err.message }),
          h("p", {
            class: "muted small",
            text: "This is the expected graceful fallback in this teaching environment. The app never creates or edits pipelines.",
          })
        )
      );
    } else {
      out.replaceChildren(errorCard("Simulation failed", err));
    }
  }
}

/* ---------- pagination & export ---------- */
let pagCursor = null;
let pitSessionId = null;
let pitCursor = null;
let paginationLoaded = false;

function pagTable(hits) {
  if (!hits || !hits.length) return h("div", { class: "placeholder", text: "No results." });
  const cols = ["ID", "Project", "District", "Type", "Status", "Price"];
  return h(
    "div",
    { class: "table-wrap" },
    h(
      "table",
      { class: "data-table compact" },
      h("thead", {}, h("tr", {}, ...cols.map((c) => h("th", { text: c })))),
      h(
        "tbody",
        {},
        ...hits.map((hit) =>
          h(
            "tr",
            {},
            h("td", {}, h("span", { class: "mono", text: String(hit.projectId || hit._id || "—") })),
            h("td", { text: hit.project_name || "—" }),
            h("td", { text: hit.district || "—" }),
            h("td", { text: hit.project_type || "—" }),
            h("td", { text: hit.project_status || "—" }),
            h("td", { text: hit.price || "—" })
          )
        )
      )
    )
  );
}

async function pagFromSize() {
  const pageInput = document.getElementById("pag-page");
  const sizeInput = document.getElementById("pag-size");
  const page = parseInt(pageInput ? pageInput.value : "1", 10) || 1;
  const size = parseInt(sizeInput ? sizeInput.value : "20", 10) || 20;
  const results = document.getElementById("pag-from-results");
  const queryEl = document.getElementById("pag-from-query");
  if (!results) return;
  results.replaceChildren(loading("Loading…"));
  try {
    const res = await API.get("/api/projects/page", { page, size });
    const data = res.data || {};
    const meta = res.meta || {};
    results.replaceChildren(
      h("p", {
          class: "muted small mb-8",
        text: `page=${data.page} from=${data.from} returned=${meta.returned} has_more=${data.has_more} · es_took_ms ${meta.es_took_ms ?? "—"} · wall_ms ${meta.wall_ms ?? "—"}`,
      }),
      pagTable(data.hits)
    );
    if (queryEl) queryEl.replaceChildren(queryDetails(meta.query_used, "Page query"));
  } catch (err) {
    results.replaceChildren(errorCard("Page failed", err));
  }
}

async function pagSearchAfter() {
  const results = document.getElementById("pag-cursor-results");
  const info = document.getElementById("pag-cursor-info");
  const queryEl = document.getElementById("pag-cursor-query");
  if (!results) return;
  results.replaceChildren(loading("Loading…"));
  try {
    const params = { size: 100 };
    if (pagCursor) params.cursor = JSON.stringify(pagCursor);
    const res = await API.get("/api/projects/search-after", params);
    const data = res.data || {};
    const meta = res.meta || {};
    pagCursor = data.next_cursor;
    if (info) {
      info.textContent = `cursor=${JSON.stringify(pagCursor)} has_more=${data.has_more} mode=${data.mode} · es_took_ms ${meta.es_took_ms ?? "—"} · wall_ms ${meta.wall_ms ?? "—"}`;
    }
    results.replaceChildren(pagTable(data.hits));
    if (queryEl) queryEl.replaceChildren(queryDetails(meta.query_used, "search_after query"));
  } catch (err) {
    results.replaceChildren(errorCard("search_after failed", err));
  }
}

function setPitStatus(text, cls) {
  const badge = document.getElementById("pit-status");
  if (!badge) return;
  badge.textContent = text;
  badge.className = `tag ${cls}`;
}

async function pitOpen() {
  const info = document.getElementById("pit-info");
  if (info) info.textContent = "Opening PIT session…";
  setPitStatus("opening", "tag-yellow");
  try {
    const res = await API.post("/api/pit");
    const data = res.data || {};
    pitSessionId = data.session_id;
    pitCursor = null;
    if (info) {
      info.textContent = `PIT opened: session=${pitSessionId} keep_alive=${data.keep_alive} expires_in=${data.expires_in_seconds}s`;
    }
    setPitStatus("open", "tag-green");
  } catch (err) {
    if (info) info.textContent = `PIT open failed: ${err.message}`;
    setPitStatus("error", "tag-red");
  }
}

async function pitNext() {
  const results = document.getElementById("pit-results");
  const info = document.getElementById("pit-info");
  if (!pitSessionId) {
    if (info) info.textContent = "No PIT session open. Click 'Open PIT' first.";
    return;
  }
  if (results) results.replaceChildren(loading("Loading…"));
  try {
    const params = { size: 100, session: pitSessionId, pit: true };
    if (pitCursor) params.cursor = JSON.stringify(pitCursor);
    const res = await API.get("/api/projects/search-after", params);
    const data = res.data || {};
    const meta = res.meta || {};
    pitCursor = data.next_cursor;
    if (info) {
      info.textContent = `PIT session=${pitSessionId} cursor=${JSON.stringify(pitCursor)} has_more=${data.has_more} · es_took_ms ${meta.es_took_ms ?? "—"} · wall_ms ${meta.wall_ms ?? "—"}`;
    }
    if (results) results.replaceChildren(pagTable(data.hits));
  } catch (err) {
    if (results) results.replaceChildren(errorCard("PIT search failed", err));
  }
}

async function pitClose() {
  const info = document.getElementById("pit-info");
  if (!pitSessionId) {
    if (info) info.textContent = "No PIT session to close.";
    return;
  }
  try {
    await API.request(`/api/pit/${pitSessionId}`, { method: "DELETE" });
    if (info) info.textContent = `PIT session ${pitSessionId} closed.`;
    pitSessionId = null;
    pitCursor = null;
    setPitStatus("closed", "tag-muted");
  } catch (err) {
    if (info) info.textContent = `PIT close failed: ${err.message}`;
    setPitStatus("error", "tag-red");
  }
}

function updateExportLink() {
  const link = document.getElementById("export-link");
  const limitInput = document.getElementById("export-limit");
  const limit = (limitInput && limitInput.value) || "17271";
  if (link) link.href = `/api/projects/export?limit=${encodeURIComponent(limit)}`;
}

function ensurePagination() {
  if (paginationLoaded) return;
  paginationLoaded = true;
  pagFromSize();
  updateExportLink();
}

/* ---------- mapping & indices ---------- */
let mappingLoaded = false;

async function runAnalyze() {
  const textInput = document.getElementById("analyze-text");
  const fieldSelect = document.getElementById("analyze-field");
  const out = document.getElementById("analyze-output");
  if (!out) return;
  const text = (textInput && textInput.value.trim()) || "";
  if (!text) {
    out.replaceChildren(h("p", { class: "muted small", text: "Enter text to analyze." }));
    return;
  }
  const fieldVal = (fieldSelect && fieldSelect.value) || "";
  const payload = { text };
  if (fieldVal) {
    payload.field = fieldVal;
  } else {
    payload.analyzer = "standard";
  }
  out.replaceChildren(loading("Analyzing…"));
  try {
    const res = await API.post("/api/analyze", payload);
    const tokens = (res.data && res.data.tokens) || [];
    out.replaceChildren(
      h(
        "div",
        { class: "table-wrap mt-8" },
        h(
          "table",
          { class: "data-table compact" },
          h("thead", {}, h("tr", {}, h("th", { text: "Token" }), h("th", { text: "Start" }), h("th", { text: "End" }), h("th", { text: "Position" }), h("th", { text: "Type" }))),
          h(
            "tbody",
            {},
            ...tokens.map((t) =>
              h(
                "tr",
                {},
                h("td", {}, h("strong", { text: t.token })),
                h("td", { text: String(t.start_offset) }),
                h("td", { text: String(t.end_offset) }),
                h("td", { text: String(t.position) }),
                h("td", { text: t.type || "word" })
              )
            )
          )
        )
      ),
      queryDetails((res.meta || {}).query_used, "Analyze query")
    );
  } catch (err) {
    out.replaceChildren(errorCard("Analyze failed", err));
  }
}

async function loadMapping(force = false) {
  if (mappingLoaded && !force) return;
  const statsEl = document.getElementById("mapping-stats");
  const fieldsEl = document.getElementById("mapping-fields");
  const aliasesEl = document.getElementById("mapping-aliases");
  const explainEl = document.getElementById("mapping-explain");
  const queryEl = document.getElementById("mapping-query");
  if (statsEl) statsEl.replaceChildren(loading("Loading mapping & stats…"));

  const index = "gujrat_rera_data";
  const [mappingRes, statsRes, aliasesRes] = await Promise.allSettled([
    API.get(`/api/indices/${index}/mapping`),
    API.get(`/api/indices/${index}/stats`),
    API.get(`/api/indices/${index}/aliases`),
  ]);

  if (statsEl) {
    if (statsRes.status === "fulfilled") {
      const sd = statsRes.value.data || {};
      statsEl.replaceChildren(
        h(
          "div",
          { class: "kpi-grid" },
          kpi("Documents", fmtNumber(sd.docs), "", "total primary count"),
          kpi("Store", sd.store_bytes != null ? `${(sd.store_bytes / 1048576).toFixed(1)} MB` : "—", "", "storage size"),
          kpi("Segments", fmtNumber(sd.segments), "", "searchable segments"),
          kpi("Total queries", fmtNumber(sd.search && sd.search.query_total), "", "search queries executed")
        )
      );
    } else {
      statsEl.replaceChildren(errorCard("Stats unavailable", statsRes.reason));
    }
  }

  if (fieldsEl) {
    if (mappingRes.status === "fulfilled") {
      const md = mappingRes.value.data || {};
      const fields = md.fields || [];
      const meta = mappingRes.value.meta || {};
      fieldsEl.replaceChildren(
        h(
          "div",
          { class: "card" },
          h(
            "div",
            { class: "card-head" },
            h("h3", { text: `Mapping Fields (dynamic: ${md.dynamic ?? "false"})` }),
            h("span", { class: "tag tag-muted", text: `${fields.length} fields` })
          ),
          h(
            "div",
            { class: "table-wrap" },
            h(
              "table",
              { class: "data-table compact" },
              h(
                "thead",
                {},
                h("tr", {}, h("th", { text: "Field name" }), h("th", { text: "Type" }), h("th", { text: "Indexed" }), h("th", { text: "Enabled" }))
              ),
              h(
                "tbody",
                {},
                ...fields.map((f) =>
                  h(
                    "tr",
                    { class: f.indexed ? "" : "row-disabled" },
                    h("td", {}, h("code", { text: f.field })),
                    h("td", { text: f.type || "object" }),
                    h("td", { text: f.indexed ? "✓ true" : "✗ false (stored only)" }),
                    h("td", { text: f.enabled !== false ? "✓ true" : "✗ false" })
                  )
                )
              )
            )
          ),
          h("p", { class: "muted small mt-8", text: `Indexed fields are queryable; non-indexed objects exist only in _source · wall_ms ${meta.wall_ms ?? "—"}` })
        )
      );
    } else {
      fieldsEl.replaceChildren(errorCard("Mapping unavailable", mappingRes.reason));
    }
  }

  if (aliasesEl) {
    if (aliasesRes.status === "fulfilled") {
      const ad = aliasesRes.value.data || {};
      aliasesEl.replaceChildren(
        h(
          "div",
          { class: "card" },
          h("div", { class: "card-head" }, h("h3", { text: "Aliases" }), h("span", { class: "tag tag-muted", text: `${ad.count || 0} alias(es)` })),
          ad.count
            ? h("pre", { text: JSON.stringify(ad.aliases, null, 2) })
            : h("p", { class: "muted small", text: "No aliases configured for gujrat_rera_data." })
        )
      );
    } else {
      aliasesEl.replaceChildren(errorCard("Aliases unavailable", aliasesRes.reason));
    }
  }

  if (explainEl) {
    explainEl.replaceChildren(
      h(
        "div",
        { class: "card note" },
        h("div", { class: "card-head" }, h("h3", { text: "Single Shard + Replica Architecture" })),
        h("p", {
          text:
            "This index defines 1 primary shard and 1 replica. In a single-node cluster (rajiv-omen), " +
            "the replica cannot be assigned to another node. The primary shard is ACTIVE, and the replica is UNASSIGNED. " +
            "This keeps the index health YELLOW as an intentional operational lesson.",
        })
      )
    );
  }

  if (queryEl && mappingRes.status === "fulfilled") {
    queryEl.replaceChildren(queryDetails((mappingRes.value.meta || {}).query_used, "Mapping query"));
  }

  mappingLoaded = true;
}

/* ---------- ops ---------- */
let opsLoaded = false;

async function loadOps(force = false) {
  if (opsLoaded && !force) return;
  const healthEl = document.getElementById("ops-health");
  const nodesEl = document.getElementById("ops-nodes");
  const shardsEl = document.getElementById("ops-shards");
  if (healthEl) healthEl.replaceChildren(loading("Loading ops health…"));

  const [healthRes, nodesRes, shardsRes] = await Promise.allSettled([
    API.get("/api/ops/health"),
    API.get("/api/ops/nodes"),
    API.get("/api/ops/shards"),
  ]);

  if (healthEl) {
    if (healthRes.status === "fulfilled") {
      const hd = (healthRes.value.data && healthRes.value.data.health) || {};
      healthEl.replaceChildren(
        h(
          "div",
          { class: "card" },
          h(
            "div",
            { class: "card-head" },
            h("h3", { text: "Cluster Health" }),
            h("span", { class: `tag tag-${hd.status || ""}`, text: hd.status || "unknown" })
          ),
          h(
            "div",
            { class: "kv-grid" },
            kv("Cluster name", hd.cluster_name || "—"),
            kv("Status", hd.status || "—"),
            kv("Nodes count", hd.number_of_nodes),
            kv("Active primary shards", hd.active_primary_shards),
            kv("Active total shards", hd.active_shards),
            kv("Relocating shards", hd.relocating_shards),
            kv("Initializing shards", hd.initializing_shards),
            kv("Unassigned shards", hd.unassigned_shards)
          )
        )
      );
    } else {
      healthEl.replaceChildren(errorCard("Cluster health unavailable", healthRes.reason));
    }
  }

  if (nodesEl) {
    if (nodesRes.status === "fulfilled") {
      const nd = (nodesRes.value.data && nodesRes.value.data.nodes) || [];
      if (nd.length) {
        nodesEl.replaceChildren(
          h(
            "div",
            { class: "card" },
            h("div", { class: "card-head" }, h("h3", { text: "Cluster Nodes" }), h("span", { class: "tag tag-muted", text: `${nd.length} node(s)` })),
            h(
              "div",
              { class: "table-wrap" },
              h(
                "table",
                { class: "data-table compact" },
                h(
                  "thead",
                  {},
                  h("tr", {}, h("th", { text: "Name" }), h("th", { text: "Roles" }), h("th", { text: "Heap %" }), h("th", { text: "CPU %" }), h("th", { text: "Docs count" }), h("th", { text: "Store size" }))
                ),
                h(
                  "tbody",
                  {},
                  ...nd.map((n) =>
                    h(
                      "tr",
                      {},
                      h("td", { text: n.name || "—" }),
                      h("td", { text: Array.isArray(n.roles) ? n.roles.join(", ") : String(n.roles || "—") }),
                      h("td", { text: n.heap_percent != null ? `${n.heap_percent}%` : "—" }),
                      h("td", { text: n.cpu_percent != null ? `${n.cpu_percent}%` : "—" }),
                      h("td", { text: fmtNumber(n.docs) }),
                      h("td", { text: n.store ? `${(n.store / 1048576).toFixed(1)} MB` : "—" })
                    )
                  )
                )
              )
            )
          )
        );
      } else {
        nodesEl.replaceChildren(h("div", { class: "card" }, h("p", { class: "muted small", text: "No nodes found." })));
      }
    } else {
      nodesEl.replaceChildren(errorCard("Nodes unavailable", nodesRes.reason));
    }
  }

  if (shardsEl) {
    if (shardsRes.status === "fulfilled") {
      const sd = (shardsRes.value.data && shardsRes.value.data.shards) || [];
      shardsEl.replaceChildren(
        h(
          "div",
          { class: "card" },
          h("div", { class: "card-head" }, h("h3", { text: "Shards Allocation" }), h("span", { class: "tag tag-muted", text: `${sd.length} shards total` })),
          h(
            "div",
            { class: "table-wrap" },
            h(
              "table",
              { class: "data-table compact" },
              h(
                "thead",
                {},
                h("tr", {}, h("th", { text: "Index" }), h("th", { text: "Shard" }), h("th", { text: "Type" }), h("th", { text: "State" }), h("th", { text: "Docs" }), h("th", { text: "Store" }), h("th", { text: "Node" }))
              ),
              h(
                "tbody",
                {},
                ...sd.map((s) =>
                  h(
                    "tr",
                    { class: s.state === "UNASSIGNED" ? "row-unassigned" : "" },
                    h("td", {}, h("code", { text: s.index || "—" })),
                    h("td", { text: s.shard ?? "—" }),
                    h("td", { text: s.prirep === "p" ? "primary" : s.prirep === "r" ? "replica" : s.prirep }),
                    h("td", { text: s.state || "—" }),
                    h("td", { text: s.docs != null ? fmtNumber(s.docs) : "—" }),
                    h("td", { text: s.store || "—" }),
                    h("td", { text: s.node || "unassigned" })
                  )
                )
              )
            )
          )
        )
      );
    } else {
      shardsEl.replaceChildren(errorCard("Shards unavailable", shardsRes.reason));
    }
  }

  opsLoaded = true;
}

/* ---------- guarded console ---------- */
async function runConsole() {
  const input = document.getElementById("console-input");
  const results = document.getElementById("console-results");
  const metaEl = document.getElementById("console-meta");
  const queryEl = document.getElementById("console-query");
  if (!results || !input || !validateJsonInput(input, "console-error", "Query body JSON")) return;
  const body = JSON.parse(input.value);

  results.replaceChildren(loading("Running query…"));
  if (metaEl) metaEl.replaceChildren();
  if (queryEl) queryEl.replaceChildren();

  try {
    const res = await API.post("/api/query/gujrat_rera_data", body);
    const meta = res.meta || {};
    const data = res.data || {};
    const hits = (data.hits && data.hits.hits) || [];

    if (metaEl) {
      metaEl.replaceChildren(
        h("span", { class: "meta-item" }, h("strong", { text: fmtNumber(meta.total) }), " matches"),
        h("span", { class: "meta-item", text: `returned ${meta.returned ?? hits.length}` }),
        h("span", { class: "meta-item" }, h("code", { text: "es_took_ms" }), " ", String(meta.es_took_ms ?? "—")),
        h("span", { class: "meta-item" }, h("code", { text: "wall_ms" }), " ", String(meta.wall_ms ?? "—"))
      );
    }

    results.replaceChildren(queryDetails(data, `Query Result (${hits.length} hits)`));

    if (queryEl) queryEl.replaceChildren(queryDetails(meta.query_used, "Executed query"));
  } catch (err) {
    results.replaceChildren(errorCard("Query rejected or failed", err));
  }
}

const boundaryState = {
  map: null,
  featureLayer: null,
  markerLayer: null,
  filterLayer: null,
  visibleItems: new Map(),
  layersById: new Map(),
  facetsLoaded: false,
  initialized: false,
  controller: null,
  generation: 0,
  moveTimer: null,
  ignoreMoves: 0,
  lastBounds: "",
};

function boundaryField(id) {
  const el = document.getElementById(id);
  return el ? el.value.trim() : "";
}

function setBoundaryStatus(text) {
  const el = document.getElementById("boundaries-map-status");
  if (el) el.textContent = text;
}

function ignoreBoundaryMove(action) {
  boundaryState.ignoreMoves += 1;
  try {
    action();
  } finally {
    setTimeout(() => {
      boundaryState.ignoreMoves = Math.max(0, boundaryState.ignoreMoves - 1);
    }, 1500);
  }
}

function initBoundaryMap() {
  const el = document.getElementById("boundaries-map");
  if (!el) return;
  if (typeof L === "undefined") {
    setBoundaryStatus("Leaflet failed to load from the CDN; map rendering is unavailable.");
    return;
  }
  if (boundaryState.map) {
    boundaryState.map.invalidateSize();
    return;
  }
  const map = L.map(el, { preferCanvas: true }).setView([22.2587, 71.1924], 7);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  boundaryState.featureLayer = L.layerGroup().addTo(map);
  boundaryState.markerLayer = L.layerGroup().addTo(map);
  boundaryState.filterLayer = L.layerGroup().addTo(map);
  boundaryState.map = map;
  map.on("zoomend", applyBoundaryStyle);
  map.on("moveend", () => {
    updateBoundaryBboxField();
    if (boundaryState.ignoreMoves > 0) return;
    const useView = document.getElementById("b-use-view");
    if (!useView || !useView.checked) return;
    clearTimeout(boundaryState.moveTimer);
    boundaryState.moveTimer = setTimeout(() => loadBoundaries({ auto: true }), 350);
  });
  updateBoundaryBboxField();
}

async function loadBoundaryFacets() {
  if (boundaryState.facetsLoaded) return;
  boundaryState.facetsLoaded = true;
  try {
    const res = await API.get("/api/projects/facets");
    const facets = (res.data && res.data.facets) || {};
    fillSelect("b-district", facets.districts && facets.districts.buckets, "All districts");
    fillSelect("b-taluka", facets.talukas && facets.talukas.buckets, "All talukas");
    fillSelect("b-type", facets.project_types && facets.project_types.buckets, "All types");
    fillSelect("b-status", facets.project_statuses && facets.project_statuses.buckets, "All statuses");
  } catch {
    setBoundaryStatus("Boundary facets unavailable; indexed filters still work as text fields where applicable.");
  }
}

function updateBoundaryBboxField() {
  if (!boundaryState.map) return;
  const bounds = boundaryState.map.getBounds();
  boundaryState.lastBounds = [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()]
    .map((value) => Number(value).toFixed(4))
    .join(",");
  const useView = document.getElementById("b-use-view");
  const input = document.getElementById("b-bbox");
  if (input && useView && useView.checked) input.value = boundaryState.lastBounds;
}

function clearBoundaryGraphics() {
  [boundaryState.featureLayer, boundaryState.markerLayer, boundaryState.filterLayer].forEach((layer) => {
    if (layer) layer.clearLayers();
  });
  boundaryState.visibleItems.clear();
  boundaryState.layersById.clear();
}

function boundaryPolygonStyle(zoomed) {
  return {
    color: zoomed ? "#0369a1" : "#0284c7",
    weight: zoomed ? 2.4 : 1.3,
    opacity: 0.95,
    fillColor: "#38bdf8",
    fillOpacity: zoomed ? 0.24 : 0.12,
  };
}

function applyBoundaryStyle() {
  if (!boundaryState.map) return;
  const zoomed = boundaryState.map.getZoom() >= 11;
  if (boundaryState.featureLayer) {
    boundaryState.featureLayer.eachLayer((layer) => layer.setStyle(boundaryPolygonStyle(zoomed)));
  }
  if (boundaryState.markerLayer) {
    boundaryState.markerLayer.eachLayer((layer) => {
      layer.setStyle({ color: "#92400e", weight: 2, fillColor: "#f59e0b", fillOpacity: 0.85 });
      if (typeof layer.setRadius === "function") layer.setRadius(zoomed ? 6 : 4);
    });
  }
}

function boundaryPopup(item) {
  return h(
    "div",
    { class: "boundary-popup" },
    h("div", { class: "popup-title", text: item.name || "Project" }),
    h("div", { class: "popup-meta", text: `Project ID ${item.id == null ? "—" : item.id}` }),
    h("div", { class: "popup-meta", text: `District ${item.district || "—"}` }),
    h("div", { class: "popup-meta", text: `Taluka ${item.taluka || "—"}` }),
    h("div", { class: "popup-meta", text: `Status ${item.project_status || "—"}` }),
    h(
      "button",
      {
        class: "btn btn-ghost mt-10",
        type: "button",
        onclick: () => openDetail(item.id),
      },
      "Open project detail"
    )
  );
}

function renderBoundaryGraphics(data) {
  const items = (data.features || []).concat(data.markers || []);
  items.forEach((item) => {
    const key = String(item.id);
    boundaryState.visibleItems.set(key, item);
    if (boundaryState.layersById.has(key)) return;
    const center = Array.isArray(item.center) ? item.center : [22.2587, 71.1924];
    const ring = Array.isArray(item.ring) ? item.ring : [];
    const zoomed = boundaryState.map.getZoom() >= 11;
    let layer;
    if (ring.length >= 3) {
      layer = L.polygon(ring, boundaryPolygonStyle(zoomed));
    } else {
      layer = L.circleMarker(center, {
        radius: 4,
        color: "#92400e",
        weight: 2,
        fillColor: "#f59e0b",
        fillOpacity: 0.85,
      });
    }
    layer.bindPopup(boundaryPopup(item));
    layer.addTo(ring.length >= 3 ? boundaryState.featureLayer : boundaryState.markerLayer);
    boundaryState.layersById.set(key, layer);
  });
}

function renderBoundaryOverlay(params) {
  if (!boundaryState.filterLayer) return;
  boundaryState.filterLayer.clearLayers();
  if (params.bbox) {
    const values = params.bbox.split(",").map(Number);
    if (values.length === 4 && values.every(Number.isFinite)) {
      L.rectangle([[values[1], values[0]], [values[3], values[2]]], {
        color: "#7c3aed",
        weight: 2,
        dashArray: "6 5",
        fillOpacity: 0.03,
      }).addTo(boundaryState.filterLayer);
    }
  }
  if (params.lat && params.lon && params.distance_km) {
    L.circle([Number(params.lat), Number(params.lon)], {
      radius: Number(params.distance_km) * 1000,
      color: "#7c3aed",
      weight: 2,
      dashArray: "6 5",
      fillColor: "#a78bfa",
      fillOpacity: 0.05,
    }).addTo(boundaryState.filterLayer);
  }
  if (params.polygon) {
    const ring = params.polygon
      .split(";")
      .map((pair) => pair.split(",").map(Number))
      .filter((point) => point.length === 2 && point.every(Number.isFinite));
    if (ring.length >= 3) {
      L.polygon(ring, {
        color: "#7c3aed",
        weight: 2,
        dashArray: "6 5",
        fillOpacity: 0.04,
      }).addTo(boundaryState.filterLayer);
    }
  }
}

function focusBoundary(item) {
  if (!boundaryState.map) return;
  const center = Array.isArray(item.center) ? item.center : [22.2587, 71.1924];
  ignoreBoundaryMove(() => boundaryState.map.setView(center, Math.max(boundaryState.map.getZoom(), 14)));
  const layer = boundaryState.layersById.get(String(item.id));
  if (layer) layer.openPopup();
}

function boundaryTable(items) {
  if (!items.length) {
    return h("div", { class: "placeholder", text: "No project boundaries matched these filters." });
  }
  const rows = items.slice(0, 250).map((item) =>
    h(
      "tr",
      { class: "row-click", onclick: () => focusBoundary(item) },
      h("td", { class: "mono", text: String(item.id ?? "—") }),
      h("td", { class: "truncate", title: String(item.name || "—"), text: item.name || "—" }),
      h("td", { text: item.district || "—" }),
      h("td", { text: item.taluka || "—" }),
      h("td", { text: item.project_type || "—" }),
      h("td", { text: item.project_status || "—" })
    )
  );
  return h(
    "div",
    { class: "stack" },
    h(
      "div",
      { class: "table-wrap" },
      h(
        "table",
        { class: "data-table compact" },
        h(
          "thead",
          {},
          h(
            "tr",
            {},
            ...["ID", "Project", "District", "Taluka", "Type", "Status"].map((column) =>
              h("th", { text: column })
            )
          )
        ),
        h("tbody", {}, ...rows)
      )
    ),
    items.length > 250
      ? h("div", { class: "muted small mt-8", text: `Showing the first 250 of ${items.length.toLocaleString()} visible boundaries. Zoom to narrow the view.` })
      : null
  );
}

function validateBoundaryInputs() {
  const lat = boundaryField("b-lat");
  const lon = boundaryField("b-lon");
  const distance = boundaryField("b-distance");
  if ((lat || lon || distance) && !(lat && lon && distance)) {
    setBoundaryStatus("Radius filtering requires latitude, longitude, and distance.");
    return false;
  }
  const size = Number(boundaryField("b-size") || "2000");
  if (!Number.isInteger(size) || size < 1 || size > 10000) {
    setBoundaryStatus("Batch size must be an integer between 1 and 10000.");
    return false;
  }
  return true;
}

function collectBoundaryParams(after) {
  const params = {};
  const fields = {
    q: "b-q",
    district: "b-district",
    taluka: "b-taluka",
    project_type: "b-type",
    project_status: "b-status",
    reg_no: "b-reg-no",
  };
  Object.entries(fields).forEach(([key, id]) => {
    const value = boundaryField(id);
    if (value) params[key] = value;
  });
  const useView = document.getElementById("b-use-view");
  params.bbox = useView && useView.checked ? boundaryState.lastBounds : boundaryField("b-bbox");
  const lat = boundaryField("b-lat");
  const lon = boundaryField("b-lon");
  const distance = boundaryField("b-distance");
  if (lat && lon && distance) {
    params.lat = lat;
    params.lon = lon;
    params.distance_km = distance;
  }
  const polygon = boundaryField("b-polygon");
  if (polygon) params.polygon = polygon;
  params.size = boundaryField("b-size") || "2000";
  if (after !== null && after !== undefined) params.after = String(after);
  return params;
}

function renderBoundaryMeta(data, meta, pages) {
  const queryUsed = (meta && meta.query_used) || {};
  const skipped = (data && data.skipped) || {};
  const metaEl = document.getElementById("boundaries-meta");
  const queryEl = document.getElementById("boundaries-query");
  const items = Array.from(boundaryState.visibleItems.values()).sort((a, b) => Number(a.id || 0) - Number(b.id || 0));
  if (metaEl) {
    metaEl.replaceChildren(
      h("span", {}, h("strong", { text: items.length.toLocaleString() }), " visible"),
      h("span", { text: `scanned ${Number(data.loaded || 0).toLocaleString()} of ${Number(meta.total || 0).toLocaleString()}` }),
      h("span", { text: `skipped ${Number(skipped.degenerate || 0).toLocaleString()} degenerate / ${Number(skipped.unparseable || 0).toLocaleString()} unparseable` }),
      h("span", { text: `batches ${pages}` }),
      h("span", { text: queryUsed.cache_hit ? "cache hit" : "ES scan" }),
      h("span", {}, h("code", { text: "es_took_ms" }), " ", String(meta.es_took_ms ?? "—")),
      h("span", {}, h("code", { text: "wall_ms" }), " ", String(meta.wall_ms ?? "—"))
    );
  }
  if (queryEl) queryEl.replaceChildren(queryDetails(queryUsed, "Boundary query"));
}

function renderBoundaryResultsTable() {
  const results = document.getElementById("boundaries-results");
  if (!results) return;
  const items = Array.from(boundaryState.visibleItems.values()).sort((a, b) => Number(a.id || 0) - Number(b.id || 0));
  results.replaceChildren(boundaryTable(items));
}

async function loadBoundaries(options = {}) {
  initBoundaryMap();
  if (!boundaryState.map) return;
  if (!validateBoundaryInputs()) return;
  if (boundaryState.controller) boundaryState.controller.abort();
  const controller = new AbortController();
  boundaryState.controller = controller;
  const generation = ++boundaryState.generation;
  clearTimeout(boundaryState.moveTimer);
  clearBoundaryGraphics();
  setBoundaryStatus("Loading boundaries…");
  const results = document.getElementById("boundaries-results");
  if (results) results.replaceChildren(loading("Loading boundaries…"));
  let after = null;
  let pages = 0;
  let lastData = null;
  let lastMeta = null;
  let previousAfter = null;
  const maxPages = 20;
  try {
    do {
      const params = collectBoundaryParams(after);
      renderBoundaryOverlay(params);
      const res = await API.get("/api/projects/boundaries", params, { signal: controller.signal });
      if (generation !== boundaryState.generation) return;
      lastData = res.data || {};
      lastMeta = res.meta || {};
      renderBoundaryGraphics(lastData);
      renderBoundaryMeta(lastData, lastMeta, pages + 1);
      pages += 1;
      after = lastData.complete ? null : lastData.next_after;
      if (after === null || after === undefined) break;
      if (String(after) === String(previousAfter)) break;
      previousAfter = after;
    } while (pages < maxPages);
    if (!lastData || !lastData.complete) {
      setBoundaryStatus(`Loaded ${pages} batches; narrow the filters to finish the scan.`);
    } else {
      setBoundaryStatus(`Rendered ${boundaryState.visibleItems.size.toLocaleString()} project boundaries.`);
    }
    renderBoundaryResultsTable();
  } catch (err) {
    if (err && err.code === "aborted") return;
    if (results) results.replaceChildren(errorCard("Boundary load failed", err));
    setBoundaryStatus("Boundary load failed. Check the filters and retry.");
  } finally {
    if (generation === boundaryState.generation) boundaryState.controller = null;
  }
}

function zoomToBoundaries() {
  if (!boundaryState.map) return;
  const layers = Array.from(boundaryState.layersById.values());
  if (!layers.length) {
    setBoundaryStatus("No boundaries loaded to zoom to.");
    return;
  }
  const group = L.featureGroup(layers);
  ignoreBoundaryMove(() => boundaryState.map.fitBounds(group.getBounds(), { padding: [24, 24], maxZoom: 16 }));
}

async function resetBoundaries() {
  if (boundaryState.controller) boundaryState.controller.abort();
  boundaryState.generation += 1;
  boundaryState.controller = null;
  const form = document.getElementById("boundaries-form");
  if (form) form.reset();
  const size = document.getElementById("b-size");
  if (size) size.value = "2000";
  const useView = document.getElementById("b-use-view");
  if (useView) useView.checked = true;
  updateBoundaryBboxField();
  clearBoundaryGraphics();
  const results = document.getElementById("boundaries-results");
  const meta = document.getElementById("boundaries-meta");
  const query = document.getElementById("boundaries-query");
  if (results) results.replaceChildren(h("div", { class: "placeholder", text: "Choose filters, then load boundaries." }));
  if (meta) meta.replaceChildren();
  if (query) query.replaceChildren();
  setBoundaryStatus("Filters reset.");
  await loadBoundaries();
}

function ensureBoundaries() {
  initBoundaryMap();
  loadBoundaryFacets();
  if (boundaryState.map) setTimeout(() => boundaryState.map.invalidateSize(), 0);
}

function initBoundaries() {
  const form = document.getElementById("boundaries-form");
  const load = document.getElementById("boundaries-load");
  const reset = document.getElementById("boundaries-reset");
  const zoom = document.getElementById("boundaries-zoom");
  const useView = document.getElementById("b-use-view");
  if (form) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      withBusy(load, "Loading…", () => loadBoundaries());
    });
  }
  if (load) load.addEventListener("click", () => withBusy(load, "Loading…", () => loadBoundaries()));
  if (reset) reset.addEventListener("click", () => withBusy(reset, "Resetting…", resetBoundaries));
  if (zoom) zoom.addEventListener("click", zoomToBoundaries);
  if (useView) {
    useView.addEventListener("change", () => {
      updateBoundaryBboxField();
      if (useView.checked) loadBoundaries({ auto: true });
    });
  }
}

/* ---------- bootstrap ---------- */
function initProjects() {
  const searchBtn = document.getElementById("projects-search");
  if (searchBtn) searchBtn.addEventListener("click", () => withBusy(searchBtn, "Searching…", runSearch));
  const resetBtn = document.getElementById("projects-reset");
  if (resetBtn) resetBtn.addEventListener("click", () => withBusy(resetBtn, "Resetting…", resetProjects));
  const form = document.getElementById("projects-form");
  if (form) form.addEventListener("submit", (event) => { event.preventDefault(); runSearch(); });

  const detailId = document.getElementById("detail-id");
  const detailLoad = document.getElementById("detail-load");
  const triggerDetail = () => {
    const value = detailId ? detailId.value.trim() : "";
    if (value) loadDetail(value);
  };
  if (detailLoad) detailLoad.addEventListener("click", () => withBusy(detailLoad, "Loading…", triggerDetail));
  if (detailId) {
    detailId.addEventListener("keydown", (event) => {
      if (event.key === "Enter") { event.preventDefault(); triggerDetail(); }
    });
  }
  const back = document.getElementById("detail-back");
  if (back) {
    back.addEventListener("click", () => {
      const tab = Array.from(document.querySelectorAll(".tab")).find((t) => t.dataset.tab === "projects");
      if (tab) tab.click();
    });
  }
  initSuggest();
}

function initTabs() {
  const tabs = Array.from(document.querySelectorAll(".tab"));
  const panels = Array.from(document.querySelectorAll(".panel"));
  const activate = (tab) => {
    tabs.forEach((t) => {
      const isActive = t === tab;
      t.classList.toggle("is-active", isActive);
      t.setAttribute("aria-selected", isActive ? "true" : "false");
      t.tabIndex = isActive ? 0 : -1;
    });
    const name = tab.dataset.tab;
    panels.forEach((p) => p.classList.toggle("is-active", p.dataset.panel === name));
    if (name === "dashboard") loadDashboard(true);
    if (name === "projects") ensureProjects();
    if (name === "analytics") loadAnalytics();
    if (name === "quality") loadQuality();
    if (name === "pagination") ensurePagination();
    if (name === "mapping") loadMapping();
    if (name === "ops") loadOps();
    if (name === "boundaries") ensureBoundaries();
  };
  tabs.forEach((tab, index) => {
    tab.tabIndex = tab.classList.contains("is-active") ? 0 : -1;
    tab.addEventListener("click", () => activate(tab));
    tab.addEventListener("keydown", (event) => {
      let next = null;
      if (event.key === "ArrowRight") next = tabs[(index + 1) % tabs.length];
      else if (event.key === "ArrowLeft") next = tabs[(index - 1 + tabs.length) % tabs.length];
      else if (event.key === "Home") next = tabs[0];
      else if (event.key === "End") next = tabs[tabs.length - 1];
      if (!next) return;
      event.preventDefault();
      next.focus();
      activate(next);
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initProjects();
  initBoundaries();
  const refresh = document.getElementById("refresh-dashboard");
  if (refresh) refresh.addEventListener("click", () => withBusy(refresh, "Refreshing…", () => loadDashboard(true)));
  const analyticsRefresh = document.getElementById("analytics-refresh");
  if (analyticsRefresh) analyticsRefresh.addEventListener("click", () => withBusy(analyticsRefresh, "Refreshing…", () => loadAnalytics(true)));
  const qualityRefresh = document.getElementById("quality-refresh");
  if (qualityRefresh) qualityRefresh.addEventListener("click", () => withBusy(qualityRefresh, "Refreshing…", () => loadQuality(true)));
  const pipelineInput = document.getElementById("pipeline-source");
  if (pipelineInput) pipelineInput.addEventListener("input", () => validateJsonInput(pipelineInput, "pipeline-error", "Pipeline source JSON"));
  const pipelineRun = document.getElementById("pipeline-run");
  if (pipelineRun) pipelineRun.addEventListener("click", () => withBusy(pipelineRun, "Simulating…", runPipeline));

  // Pagination & Export
  const pagGo = document.getElementById("pag-go");
  if (pagGo) pagGo.addEventListener("click", () => withBusy(pagGo, "Loading…", pagFromSize));
  const pagNext = document.getElementById("pag-next");
  if (pagNext) pagNext.addEventListener("click", () => withBusy(pagNext, "Loading…", pagSearchAfter));
  const pagCursorReset = document.getElementById("pag-cursor-reset");
  if (pagCursorReset) {
    pagCursorReset.addEventListener("click", () => {
      pagCursor = null;
      const info = document.getElementById("pag-cursor-info");
      if (info) info.textContent = "Cursor reset to start.";
    });
  }
  const paginationRefresh = document.getElementById("pagination-refresh");
  if (paginationRefresh) {
    paginationRefresh.addEventListener("click", () => withBusy(paginationRefresh, "Refreshing…", () => {
      paginationLoaded = false;
      ensurePagination();
    }));
  }
  const pitOpenBtn = document.getElementById("pit-open");
  if (pitOpenBtn) pitOpenBtn.addEventListener("click", () => withBusy(pitOpenBtn, "Opening…", pitOpen));
  const pitNextBtn = document.getElementById("pit-next");
  if (pitNextBtn) pitNextBtn.addEventListener("click", () => withBusy(pitNextBtn, "Loading…", pitNext));
  const pitCloseBtn = document.getElementById("pit-close");
  if (pitCloseBtn) pitCloseBtn.addEventListener("click", () => withBusy(pitCloseBtn, "Closing…", pitClose));
  const exportLimit = document.getElementById("export-limit");
  if (exportLimit) exportLimit.addEventListener("input", updateExportLink);

  // Mapping & Analyze
  const mappingRefresh = document.getElementById("mapping-refresh");
  if (mappingRefresh) mappingRefresh.addEventListener("click", () => withBusy(mappingRefresh, "Refreshing…", () => loadMapping(true)));
  const analyzeRun = document.getElementById("analyze-run");
  if (analyzeRun) analyzeRun.addEventListener("click", () => withBusy(analyzeRun, "Analyzing…", runAnalyze));

  // Ops
  const opsRefresh = document.getElementById("ops-refresh");
  if (opsRefresh) opsRefresh.addEventListener("click", () => withBusy(opsRefresh, "Refreshing…", () => loadOps(true)));

  // Console
  const consoleRun = document.getElementById("console-run");
  if (consoleRun) consoleRun.addEventListener("click", () => withBusy(consoleRun, "Running…", runConsole));
  const consoleInput = document.getElementById("console-input");
  if (consoleInput) {
    consoleInput.addEventListener("input", () => validateJsonInput(consoleInput, "console-error", "Query body JSON"));
    consoleInput.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        withBusy(consoleRun, "Running…", runConsole);
      }
    });
  }

  loadDashboard(true);
});
