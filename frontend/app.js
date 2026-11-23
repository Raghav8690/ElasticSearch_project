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
  async request(path, { method = "GET", params = null, body = null, timeoutMs = 20000 } = {}) {
    const url = new URL(path, window.location.origin);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
      });
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
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
        throw new ApiError("timeout", `Request timed out after ${Math.round(timeoutMs / 1000)}s`, 504);
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  },
  get(path, params) {
    return this.request(path, { params });
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

function setStatusPill(status) {
  const pill = document.getElementById("cluster-pill");
  if (!pill) return;
  const label = pill.querySelector(".pill-label");
  const s = String(status || "unknown").toLowerCase();
  pill.classList.remove("is-green", "is-yellow", "is-red", "is-unknown");
  pill.classList.add(["green", "yellow", "red"].includes(s) ? `is-${s}` : "is-unknown");
  if (label) label.textContent = s;
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
      kv("Status", idx.status || "—"),
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
          h("div", {
            class: "cap-reason",
            text: feature.available ? "available" : feature.reason || "unavailable",
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
      kpi("Cluster status", status, statusClass(status), `${cluster.nodes ?? "—"} node(s) in cluster`),
      kpi("Elasticsearch", health.version || "unknown", "", "server version"),
      kpi(
        "Documents",
        idx && idx.docs != null ? Number(idx.docs).toLocaleString() : "—",
        "",
        "in the configured index"
      ),
      kpi(
        "Unassigned shards",
        health.unassigned_shards ?? "—",
        health.unassigned_shards ? "is-warn" : "is-green",
        `${health.active_primary_shards ?? "—"} active primaries`
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
    body.replaceChildren(h("div", { class: "loading", text: "Loading cluster facts…" }));
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
  return h(
    "details",
    { class: "details" },
    h("summary", { text: label }),
    h("pre", { text: JSON.stringify(queryUsed, null, 2) })
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
    parts.push(h("em", {}, match[1]));
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
    const open = () => openDetail(hit._id || hit.projectId);
    return h(
      "tr",
      { class: "row-click", onclick: open },
      h("td", {}, h("span", { class: "mono", text: String(hit._id || hit.projectId || "—") })),
      h("td", {}, renderHighlighted(hit.project_name, hit.highlight && hit.highlight.project_name)),
      h("td", { text: hit.district || "—" }),
      h("td", { text: hit.taluka || "—" }),
      h("td", { text: hit.project_type || "—" }),
      h("td", { text: hit.project_status || "—" }),
      h("td", { text: hit.price || "—" }),
      h("td", { text: hit.start_date || "—" }),
      h("td", { text: hit.end_date || "—" }),
      h("td", { text: docs == null ? "—" : String(docs) })
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
  results.replaceChildren(h("div", { class: "loading", text: "Searching…" }));
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
  input.addEventListener("input", () => {
    clearTimeout(suggestTimer);
    const q = input.value.trim();
    if (q.length < 2) {
      box.hidden = true;
      box.replaceChildren();
      return;
    }
    suggestTimer = setTimeout(async () => {
      try {
        const res = await API.get("/api/projects/suggest", { q, size: 8 });
        const items = (res.data && res.data.suggestions) || [];
        if (!items.length) {
          box.hidden = true;
          box.replaceChildren();
          return;
        }
        box.replaceChildren(
          ...items.map((item) =>
            h(
              "button",
              {
                class: "suggest-item",
                type: "button",
                onclick: () => {
                  input.value = item.project_name || "";
                  box.hidden = true;
                  runSearch();
                },
              },
              h("span", { class: "suggest-name", text: item.project_name || "—" }),
              h("span", {
                class: "suggest-meta",
                text: [item.district, item.project_type].filter(Boolean).join(" · "),
              })
            )
          )
        );
        box.hidden = false;
      } catch {
        box.hidden = true;
      }
    }, 300);
  });
  document.addEventListener("click", (event) => {
    if (!box.contains(event.target) && event.target !== input) box.hidden = true;
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

  const rawToggle = h(
    "details",
    { class: "details" },
    h("summary", { text: "Raw _source JSON" }),
    h("pre", { text: JSON.stringify(data.raw || {}, null, 2) })
  );

  root.append(coreCard, ...sectionCards, rawToggle, queryDetails(meta.query_used));
}

async function loadDetail(projectId) {
  const body = document.getElementById("detail-body");
  if (!body) return;
  body.replaceChildren(h("div", { class: "loading", text: `Loading project ${projectId}…` }));
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
const CHART_PALETTE = ["#4f8cff", "#38d6b0", "#f4b740", "#ef6b8a", "#a78bfa", "#31c3e6", "#f97316", "#84cc16", "#e879f9", "#64748b"];
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
      plugins: { legend: { display: false }, tooltip: { intersect: false } },
      scales: {
        x: {
          beginAtZero: true,
          ticks: { color: "#9aa8c7", maxRotation: 45, minRotation: 0, autoSkip: true },
          grid: { color: "rgba(36,48,79,.45)" },
        },
        y: {
          beginAtZero: true,
          ticks: { color: "#9aa8c7", autoSkip: true },
          grid: { color: "rgba(36,48,79,.45)" },
        },
      },
    },
  };
}

function fallbackTable(labels, values) {
  return h(
    "div",
    { class: "table-wrap" },
    h(
      "table",
      { class: "data-table compact" },
      h("thead", {}, h("tr", {}, h("th", { text: "Key" }), h("th", { text: "Count" }))),
      h(
        "tbody",
        {},
        ...labels.map((label, i) => h("tr", {}, h("td", { text: label }), h("td", { text: Number(values[i]).toLocaleString() })))
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
  if (!labels.length) {
    card.append(h("p", { class: "muted small", text: "No buckets returned." }));
  } else if (window.Chart) {
    const wrap = h("div", { class: "chart-wrap" });
    const canvas = document.createElement("canvas");
    wrap.append(canvas);
    card.append(wrap);
    pendingCharts.push({ canvas, labels, values, opts });
  } else {
    card.append(fallbackTable(labels, values));
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
    chartCard("Districts", ...Object.values(bucketsToXY((aggs.districts || {}).buckets)), { horizontal: true, label: "projects" }),
    chartCard("Project types", ...Object.values(bucketsToXY((aggs.project_types || {}).buckets))),
    chartCard("Statuses", ...Object.values(bucketsToXY((aggs.project_statuses || {}).buckets))),
    chartCard("Top promoters", ...Object.values(bucketsToXY((aggs.top_promoters || {}).buckets)), { horizontal: true }),
    chartCard("Start year", ...Object.values(dateBucketsToXY((dateAggs.start_years || {}).buckets))),
    chartCard("End year", ...Object.values(dateBucketsToXY((dateAggs.end_years || {}).buckets)))
  );
  if (!window.Chart) {
    root.append(
      h("p", {
        class: "muted small",
        text: "Chart.js could not load (offline?). Bucket values are shown as tables instead.",
      })
    );
  }
  root.append(grid);
  flushCharts();
}

async function loadAnalytics(force = false) {
  const body = document.getElementById("analytics-body");
  if (!body) return;
  if (analyticsLoaded && !force) return;
  body.replaceChildren(h("div", { class: "loading", text: "Loading analytics…" }));
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
      h("td", { text: fmtNumber(count) }),
      h("td", { text: pct != null ? `${pct.toFixed(2)}%` : "—" })
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
        h("thead", {}, h("tr", {}, h("th", { text: "Field" }), h("th", { text: "Missing" }), h("th", { text: "% of docs" }))),
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
  summary.replaceChildren(h("div", { class: "loading", text: "Loading quality checks…" }));
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
  if (!out) return;
  let source;
  try {
    source = JSON.parse((input && input.value) || "{}");
  } catch (err) {
    out.replaceChildren(h("div", { class: "error-card" }, h("h3", { text: "Invalid JSON" }), h("p", { text: err.message })));
    return;
  }
  out.replaceChildren(h("div", { class: "loading", text: "Simulating…" }));
  try {
    const res = await API.post("/api/quality/pipeline-simulate", { source });
    const data = res.data || {};
    out.replaceChildren(
      h("p", {
        class: "muted small",
        text: `Pipeline: ${data.pipeline_id || "—"} · wall_ms ${(res.meta || {}).wall_ms ?? "—"}`,
      }),
      h(
        "details",
        { class: "details", open: true },
        h("summary", { text: "Simulation result" }),
        h("pre", { text: JSON.stringify(data.result || {}, null, 2) })
      ),
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

/* ---------- bootstrap ---------- */
function initProjects() {
  const searchBtn = document.getElementById("projects-search");
  if (searchBtn) searchBtn.addEventListener("click", runSearch);
  const resetBtn = document.getElementById("projects-reset");
  if (resetBtn) resetBtn.addEventListener("click", resetProjects);
  const form = document.getElementById("projects-form");
  if (form) form.addEventListener("submit", (event) => { event.preventDefault(); runSearch(); });

  const detailId = document.getElementById("detail-id");
  const detailLoad = document.getElementById("detail-load");
  const triggerDetail = () => {
    const value = detailId ? detailId.value.trim() : "";
    if (value) loadDetail(value);
  };
  if (detailLoad) detailLoad.addEventListener("click", triggerDetail);
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
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.toggle("is-active", t === tab));
      const name = tab.dataset.tab;
      panels.forEach((p) => p.classList.toggle("is-active", p.dataset.panel === name));
      if (name === "dashboard") loadDashboard(true);
      if (name === "projects") ensureProjects();
      if (name === "analytics") loadAnalytics();
      if (name === "quality") loadQuality();
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initProjects();
  const refresh = document.getElementById("refresh-dashboard");
  if (refresh) refresh.addEventListener("click", () => loadDashboard(true));
  const analyticsRefresh = document.getElementById("analytics-refresh");
  if (analyticsRefresh) analyticsRefresh.addEventListener("click", () => loadAnalytics(true));
  const qualityRefresh = document.getElementById("quality-refresh");
  if (qualityRefresh) qualityRefresh.addEventListener("click", () => loadQuality(true));
  const pipelineRun = document.getElementById("pipeline-run");
  if (pipelineRun) pipelineRun.addEventListener("click", runPipeline);
  loadDashboard(true);
});
