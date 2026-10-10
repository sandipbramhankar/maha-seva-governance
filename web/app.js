/* Seva Governance Console
   Reads the API and renders four views. No framework: the page is a handful of
   tables and the data arrives already aggregated, so a build step would cost
   more than it saves. */

const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const esc = (v) => String(v ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const n = (v, d = 0) => Number(v ?? 0).toLocaleString("en-IN",
  { minimumFractionDigits: d, maximumFractionDigits: d });

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} returned ${r.status}`);
  return r.json();
}

const STATE = { data: {}, district: null, dept: "" };

/* ------------------------------------------------------------------ KPIs */

function renderKpis(s) {
  const tiles = [
    { k: "Open requests",   v: n(s.open) },
    { k: "SLA breached",    v: n(s.breached), cls: s.breached ? "crit" : "good" },
    { k: "Breach rate",     v: `${s.breach_rate}%`, cls: s.breach_rate > 8 ? "crit" : "" },
    { k: "Closed on time",  v: `${s.on_time_rate}%`, cls: "good" },
    { k: "Avg age (open)",  v: `${s.avg_open_age}d` },
    { k: "Oldest open",     v: `${s.oldest_open}d`, cls: "high" },
    { k: "Closed to date",  v: n(s.closed) },
  ];
  $("#kpis").innerHTML = tiles.map((t) => `
    <div class="kpi ${t.cls || ""}">
      <div class="v">${esc(t.v)}</div>
      <div class="k">${esc(t.k)}</div>
    </div>`).join("");
}

/* -------------------------------------------------------------- Overview */

function barPanel(title, hint, rows, valueKey, labelKey, fmt) {
  const max = Math.max(...rows.map((r) => r[valueKey]), 1);
  return `
  <section class="panel">
    <header><h2>${esc(title)}</h2><span class="hint">${esc(hint)}</span></header>
    <div style="padding:8px 0">
      ${rows.map((r) => `
        <div class="bar-row">
          <span class="lbl">${esc(r[labelKey])}</span>
          <span class="bar"><span style="width:${(r[valueKey] / max) * 100}%"></span></span>
          <span class="val">${esc(fmt(r))}</span>
        </div>`).join("")}
    </div>
  </section>`;
}

function trendSvg(rows) {
  const W = 1200, H = 190, P = { t: 14, r: 16, b: 28, l: 44 };
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const max = Math.max(...rows.flatMap((r) => [r.filed, r.closed]), 1);
  const step = iw / Math.max(rows.length - 1, 1);
  const x = (i) => P.l + i * step;
  const y = (v) => P.t + ih - (v / max) * ih;
  const line = (key) => rows.map((r, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(r[key]).toFixed(1)}`).join(" ");

  const ticks = [0, Math.round(max / 2), max];
  return `
  <svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img"
       aria-label="Requests filed against requests closed, by week">
    ${ticks.map((t) => `
      <line x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}"
            stroke="var(--line-soft)" stroke-width="1"/>
      <text x="${P.l - 6}" y="${y(t) + 3.5}" text-anchor="end" font-size="11"
            fill="var(--ink-3)" font-family="var(--font-body)">${t}</text>`).join("")}
    <path d="${line("filed")}"  fill="none" stroke="var(--accent)" stroke-width="2.5"/>
    <path d="${line("closed")}" fill="none" stroke="var(--good)"   stroke-width="2.5"
          stroke-dasharray="5 4"/>
    ${rows.map((r, i) => (i % 2 === 0 || i === rows.length - 1) ? `
      <text x="${x(i)}" y="${H - 7}" text-anchor="middle" font-size="11"
            fill="var(--ink-3)" font-family="var(--font-body)">${esc(r.week)}</text>` : "").join("")}
    <circle cx="${x(rows.length - 1)}" cy="${y(rows[rows.length - 1].filed)}" r="4.5"
            fill="var(--accent)"/>
    <circle cx="${x(rows.length - 1)}" cy="${y(rows[rows.length - 1].closed)}" r="4.5"
            fill="var(--good)"/>
  </svg>`;
}

function renderOverview() {
  const { departments, bottlenecks, trend, districts } = STATE.data;
  // A district with four open requests can show a 50% breach rate on two
  // files. Ranking those alongside Pune would put noise at the top of the
  // Chief Minister's screen, so the chart needs a floor; the full table on the
  // Districts tab still lists every district, floor or no floor.
  const MIN_OPEN = 10;
  const ranked = districts.filter((d) => d.open >= MIN_OPEN);
  const worst = (ranked.length >= 5 ? ranked : districts).slice(0, 8);

  $("#view-overview").innerHTML = `
    <section class="panel">
      <header>
        <h2>Departments</h2>
        <span class="hint">Every citizen request enters through one Seva ID, whichever department owns it</span>
      </header>
      <div class="scroll"><table>
        <thead><tr>
          <th>Department</th><th class="num">Open</th><th class="num">Closed</th>
          <th class="num">Breached</th><th class="num">Breach rate</th>
          <th class="num">Avg age</th><th>Largest service</th>
        </tr></thead>
        <tbody>${departments.map((d) => `
          <tr>
            <td style="font-weight:600">${esc(d.department)}</td>
            <td class="num">${n(d.open)}</td>
            <td class="num">${n(d.closed)}</td>
            <td class="num">${d.breached ? `<span class="pill red">${n(d.breached)}</span>` : "0"}</td>
            <td class="num">${d.breach_rate}%</td>
            <td class="num">${d.avg_age}d</td>
            <td style="color:var(--ink-2)">${esc(d.top_service)}</td>
          </tr>`).join("")}
        </tbody>
      </table></div>
    </section>

    <div class="grid-2">
      ${barPanel(
        "Where the days go", "Average time a file has been sitting on each desk",
        bottlenecks.slice(0, 7), "avg_days", "role",
        (r) => `${r.avg_days}d · ${r.pending}`)}
      ${barPanel(
        "Districts by breach rate", `Open requests past their statutory period \u00b7 districts with ${MIN_OPEN}+ open`,
        worst, "breach_rate", "district",
        (r) => `${r.breach_rate}% · ${r.open}`)}
    </div>

    <section class="panel">
      <header>
        <h2>Filed against closed</h2>
        <span class="hint">
          <span style="color:var(--accent);font-weight:600">&mdash; filed</span> &nbsp;
          <span style="color:var(--good);font-weight:600">--- closed</span>
        </span>
      </header>
      <div style="padding:10px 14px">${trendSvg(trend)}</div>
      <p class="footnote">
        A line that stays above the other is a backlog forming. This is the figure
        a weekly review should open with, and no current system reports it.
      </p>
    </section>`;
}

/* ------------------------------------------------------------- Districts */

function deptFilter(id) {
  const opts = ["", ...STATE.data.departments.map((d) => d.department)];
  return `<label style="font-size:12px;color:var(--ink-3)">Department
    <select id="${id}">${opts.map((o) => `
      <option value="${esc(o)}" ${o === STATE.dept ? "selected" : ""}>${esc(o || "All")}</option>`).join("")}
    </select></label>`;
}

function renderDistricts() {
  const rows = STATE.data.districts;
  $("#view-districts").innerHTML = `
    <section class="panel">
      <header>
        <h2>District pendency</h2>
        <span class="hint">Select a district to open its talukas</span>
        <span class="spacer"></span>
        ${deptFilter("dept-districts")}
      </header>
      <div class="scroll" style="max-height:62vh"><table>
        <thead><tr>
          <th>District</th><th>Division</th>
          <th class="num">Open</th><th class="num">Breached</th>
          <th class="num">Breach rate</th><th class="num">Avg age</th>
          <th>Slowest desk</th><th class="num">Flags</th>
        </tr></thead>
        <tbody>${rows.map((r) => `
          <tr class="clickable ${r.district === STATE.district ? "sel" : ""}"
              data-district="${esc(r.district)}">
            <td class="stripe ${r.breach_rate > 15 ? "red" : r.breach_rate > 8 ? "orange" : r.breach_rate > 0 ? "yellow" : "green"}"
                style="font-weight:600">${esc(r.district)}</td>
            <td style="color:var(--ink-3);font-size:12px">${esc(r.division)}</td>
            <td class="num">${n(r.open)}</td>
            <td class="num">${r.breached || "0"}</td>
            <td class="num" style="font-weight:600">${r.breach_rate}%</td>
            <td class="num">${r.avg_age}d</td>
            <td style="color:var(--ink-2);font-size:12px">
              ${esc(r.worst_stage || "—")}
              ${r.worst_stage_days ? `<span style="color:var(--ink-3)"> ${r.worst_stage_days}d</span>` : ""}</td>
            <td class="num" style="white-space:nowrap">
              ${r.red ? `<span class="pill red">${r.red}</span> ` : ""}
              ${r.orange ? `<span class="pill orange">${r.orange}</span> ` : ""}
              ${r.yellow ? `<span class="pill yellow">${r.yellow}</span>` : ""}
              ${!r.red && !r.orange && !r.yellow ? `<span class="pill green">clear</span>` : ""}
            </td>
          </tr>`).join("")}
        </tbody>
      </table></div>
    </section>
    <div id="taluka-panel"></div>`;

  $("#dept-districts").addEventListener("change", async (e) => {
    STATE.dept = e.target.value;
    STATE.data.districts = await api(`/api/districts${STATE.dept ? `?department=${encodeURIComponent(STATE.dept)}` : ""}`);
    renderDistricts();
    if (STATE.district) loadTalukas(STATE.district);
  });

  $$("#view-districts tr[data-district]").forEach((tr) => {
    tr.addEventListener("click", () => loadTalukas(tr.dataset.district));
  });

  if (STATE.district) loadTalukas(STATE.district);
}

async function loadTalukas(district) {
  STATE.district = district;
  $$("#view-districts tr[data-district]").forEach((tr) =>
    tr.classList.toggle("sel", tr.dataset.district === district));

  const q = STATE.dept ? `?department=${encodeURIComponent(STATE.dept)}` : "";
  const [rows, flags] = await Promise.all([
    api(`/api/districts/${encodeURIComponent(district)}/talukas${q}`),
    api(`/api/red-flags?limit=15&district=${encodeURIComponent(district)}${STATE.dept ? `&department=${encodeURIComponent(STATE.dept)}` : ""}`),
  ]);

  $("#taluka-panel").innerHTML = `
    <section class="panel">
      <header>
        <h2>${esc(district)} &mdash; talukas</h2>
        <span class="hint">${rows.length} talukas</span>
      </header>
      <div class="scroll"><table>
        <thead><tr>
          <th>Taluka</th><th class="num">Open</th><th class="num">Breached</th>
          <th class="num">Breach rate</th><th class="num">Avg age</th><th class="num">Flags</th>
        </tr></thead>
        <tbody>${rows.map((r) => `
          <tr>
            <td class="stripe ${r.breach_rate > 15 ? "red" : r.breach_rate > 8 ? "orange" : r.breach_rate > 0 ? "yellow" : "green"}">${esc(r.taluka)}</td>
            <td class="num">${n(r.open)}</td>
            <td class="num">${r.breached || "0"}</td>
            <td class="num" style="font-weight:600">${r.breach_rate}%</td>
            <td class="num">${r.avg_age}d</td>
            <td class="num">
              ${r.red ? `<span class="pill red">${r.red}</span> ` : ""}
              ${r.orange ? `<span class="pill orange">${r.orange}</span> ` : ""}
              ${r.yellow ? `<span class="pill yellow">${r.yellow}</span>` : ""}
              ${!r.red && !r.orange && !r.yellow ? `<span class="pill ghost">—</span>` : ""}
            </td>
          </tr>`).join("")}
        </tbody>
      </table></div>
    </section>
    ${flags.length ? `
    <section class="panel">
      <header><h2>Overdue in ${esc(district)}</h2>
        <span class="hint">Worst first. Select a row for the file.</span></header>
      <div class="scroll">${ticketTable(flags)}</div>
    </section>` : ""}`;

  wireTicketRows($("#taluka-panel"));
}

/* --------------------------------------------------------------- Tickets */

function ticketTable(rows) {
  return `<table>
    <thead><tr>
      <th>Seva ID</th><th>Applicant</th><th>Service</th>
      <th>Stage</th><th>Officer</th>
      <th class="num">Age</th><th class="num">SLA</th><th>Status</th>
    </tr></thead>
    <tbody>${rows.map((r) => `
      <tr class="clickable" data-seva="${esc(r.seva_id)}">
        <td class="stripe ${r.flag} mono" style="white-space:nowrap">${esc(r.seva_id)}</td>
        <td style="font-weight:600">${esc(r.citizen)}</td>
        <td style="font-size:12px;color:var(--ink-2)">${esc(r.service)}</td>
        <td style="font-size:12px">${esc(r.role || r.stage)}</td>
        <td style="font-size:12px;color:var(--ink-2)">${esc(r.officer)}</td>
        <td class="num">${r.age_days}d</td>
        <td class="num" style="color:var(--ink-3)">${r.sla_days}d</td>
        <td>
          <span class="pill ${r.flag}">${r.breached ? "breached" : r.flag}</span>
          ${r.verdict ? ` <span class="verdict ${esc(r.verdict)}">${esc(r.verdict)}</span>` : ""}
        </td>
      </tr>`).join("")}
    </tbody></table>`;
}

function wireTicketRows(root) {
  $$("tr[data-seva]", root).forEach((tr) =>
    tr.addEventListener("click", () => openTicket(tr.dataset.seva)));
}

function renderTickets() {
  const { showcase, redflags } = STATE.data;
  $("#view-tickets").innerHTML = `
    <section class="panel">
      <header>
        <h2>Verified by the engine</h2>
        <span class="hint">
          These nine ran through the full pipeline: identity resolution, cross-source
          checks, fraud graph, agent vote. Open one to see the reasoning.
        </span>
      </header>
      <div class="scroll">${ticketTable(showcase)}</div>
    </section>

    <section class="panel">
      <header>
        <h2>Statewide overdue queue</h2>
        <span class="hint">Open requests past or near their statutory period</span>
      </header>
      <div class="scroll" style="max-height:52vh">${ticketTable(redflags)}</div>
      <p class="footnote">
        Background load is synthetic. Workflow, officer assignment and the Right to
        Services clock are computed; verification scores on these rows are sampled.
      </p>
    </section>`;
  wireTicketRows($("#view-tickets"));
}

/* ------------------------------------------------------------- Integrity */

function renderIntegrity() {
  const rows = STATE.data.overrides;
  $("#view-integrity").innerHTML = `
    <section class="panel">
      <header>
        <h2>Override watch</h2>
        <span class="hint">Officers who closed a stage while a raised flag was still standing</span>
      </header>
      ${rows.length ? `<div class="scroll"><table>
        <thead><tr>
          <th>Officer</th><th>Posting</th>
          <th class="num">Files closed</th><th class="num">Overrides</th>
          <th class="num">Override rate</th>
        </tr></thead>
        <tbody>${rows.map((r) => `
          <tr>
            <td class="stripe ${r.override_rate > 50 ? "red" : r.override_rate > 25 ? "orange" : "yellow"}"
                style="font-weight:600">${esc(r.officer)}
              <div class="mono" style="color:var(--ink-3)">${esc(r.officer_id)}</div></td>
            <td style="font-size:12px;color:var(--ink-2)">${esc(r.posting)}</td>
            <td class="num">${n(r.files_closed)}</td>
            <td class="num">${n(r.overrides)}</td>
            <td class="num" style="font-weight:600">${r.override_rate}%</td>
          </tr>`).join("")}
        </tbody></table></div>` : `<div class="empty">No officer has overridden a flag yet.</div>`}
      <p class="footnote">
        An override is legitimate and often correct: the record may be wrong and the
        officer may know the family. What this list shows is a pattern worth a
        question, never a finding. An officer who overrides on most of their files is
        where an inspection starts, not where it concludes.
      </p>
    </section>`;
}

/* ---------------------------------------------------------------- drawer */

function checksTable(checks) {
  const icon = { match: "✓", mismatch: "✗", not_available: "–" };
  const cls  = { match: "green", mismatch: "red", not_available: "ghost" };
  return `<table>
    <thead><tr><th>Attribute</th><th>Source</th><th>Claimed</th><th>Found</th><th></th></tr></thead>
    <tbody>${checks.map((c) => `
      <tr>
        <td style="font-size:12px">${esc(c.attribute)}</td>
        <td style="font-size:12px;color:var(--ink-2)">${esc(c.source)}</td>
        <td style="font-size:12px">${esc(c.claimed ?? "—")}</td>
        <td style="font-size:12px">${esc(c.found ?? "—")}</td>
        <td><span class="pill ${cls[c.status]}">${icon[c.status]}</span></td>
      </tr>
      ${c.note ? `<tr><td colspan="5" style="padding-top:0;font-size:12px;color:var(--ink-2);border-bottom:1px solid var(--line-soft)">${esc(c.note)}</td></tr>` : ""}
    `).join("")}</tbody></table>`;
}

function renderDetail(d) {
  const v = d.verification;
  const cd = d.citizen_detail || {};

  const scores = v ? `
    <div class="scorebox">
      ${[["GTS", v.scores.GTS], ["DCS", v.scores.DCS], ["PCS", v.scores.PCS],
         ["FRS", v.scores.FRS], ["NCS", v.scores.CS], ["ERS", v.scores.ERS],
         ["CGS", v.scores.CGS]]
        .map(([k, val]) => `<div><div class="s-v">${val}</div><div class="s-k">${k}</div></div>`).join("")}
    </div>` : "";

  const votes = v ? `
    <table><thead><tr><th>Agent</th><th class="num">Weight</th><th>Vote</th></tr></thead>
    <tbody>${v.consensus.votes.map((x) => `
      <tr>
        <td style="font-size:12px">${esc(x.agent)}
          <div style="color:var(--ink-3);font-size:11.5px">${esc(x.why)}</div></td>
        <td class="num">${x.weight}</td>
        <td><span class="pill ${x.vote === "Approve" ? "green" : x.vote === "Reject" ? "red" : "yellow"}">${esc(x.vote)}</span></td>
      </tr>`).join("")}</tbody></table>` : "";

  return `
    <div class="sect">
      <h3>Status</h3>
      <dl class="kv">
        <dt>Stage</dt><dd>${esc(d.role || d.stage)}</dd>
        <dt>With</dt><dd>${esc(d.officer)} <span class="mono" style="color:var(--ink-3)">${esc(d.officer_id)}</span></dd>
        <dt>Statutory clock</dt>
        <dd><span class="pill ${d.flag}">${d.age_days}d of ${d.sla_days}d</span></dd>
        <dt>On this desk</dt><dd>${d.stage_days}d</dd>
        <dt>Reason</dt><dd>${esc(d.clock.reason)}</dd>
      </dl>
    </div>

    <div class="sect">
      <h3>Applicant</h3>
      <dl class="kv">
        <dt>Name</dt><dd>${esc(cd.full_name)}</dd>
        <dt>Aadhaar</dt><dd class="mono">XXXX XXXX ${esc(cd.aadhaar_last4)}</dd>
        ${cd.dob ? `<dt>Date of birth</dt><dd>${esc(cd.dob)}</dd>` : ""}
        ${cd.father_name ? `<dt>Father</dt><dd>${esc(cd.father_name)}</dd>` : ""}
        ${cd.grandfather_name ? `<dt>Grandfather</dt><dd>${esc(cd.grandfather_name)}</dd>` : ""}
        ${cd.claimed_caste ? `<dt>Category claimed</dt><dd>${esc(cd.claimed_caste)}</dd>` : ""}
        ${cd.claimed_income != null ? `<dt>Income declared</dt><dd>Rs ${n(cd.claimed_income)}</dd>` : ""}
        <dt>Place</dt><dd>${esc([d.village, d.taluka, d.district].filter(Boolean).join(", "))}</dd>
      </dl>
    </div>

    ${v ? `
    <div class="sect">
      <h3>Automated verdict &mdash; <span class="verdict ${esc(v.verdict)}">${esc(v.verdict)}</span></h3>
      ${scores}
      <ul class="reasons" style="margin-top:10px">
        ${v.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}
      </ul>
    </div>

    <div class="sect">
      <h3>What each source says</h3>
      <div class="scroll">${checksTable(v.checks)}</div>
    </div>

    <div class="sect">
      <h3>Agent vote &mdash; consensus ${v.consensus.NCS}</h3>
      <div class="scroll">${votes}</div>
    </div>

    ${v.fraud.FRS > 0 ? `
    <div class="sect">
      <h3>Linked applicants &mdash; fraud risk ${v.fraud.FRS}</h3>
      <ul class="reasons">${v.fraud.findings.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>
    </div>` : ""}
    ` : `<div class="sect"><h3>Verification</h3>
         <p style="font-size:13px;color:var(--ink-2)">
         This ticket is part of the synthetic background load. Its workflow and
         statutory clock are computed; it was not run through the engine.</p></div>`}

    <div class="sect">
      <h3>File movement</h3>
      <div class="timeline">
        ${d.history.map((h) => `
          <div class="tl-item ${h.exited ? "done" : "now"}">
            <div class="who">${esc(h.role || h.stage)} &mdash; ${esc(h.officer)}</div>
            <div class="meta">
              ${esc(h.entered.slice(0, 10))}
              ${h.exited ? ` → ${esc(h.exited.slice(0, 10))} · ${esc(h.action || "")}` : " · still here"}
            </div>
            ${h.remark ? `<div class="meta">${esc(h.remark)}</div>` : ""}
            ${h.overrode && h.overrode.length
              ? `<div class="meta"><span class="pill orange">overrode ${h.overrode.length} flag(s)</span></div>` : ""}
          </div>`).join("")}
      </div>
    </div>

    ${d.audit ? `
    <div class="sect">
      <h3>Audit chain &mdash;
        <span class="${d.audit.intact ? "intact" : ""}" style="${d.audit.intact ? "" : "color:var(--crit)"}">
          ${d.audit.intact ? "intact" : `broken at ${esc(d.audit.broken_at)}`}
        </span>
      </h3>
      ${d.audit.entries.map((e) => `
        <div style="margin-bottom:9px">
          <div style="font-size:12.5px"><strong>${esc(e.sequence)}. ${esc(e.event)}</strong>
            &mdash; ${esc(e.actor_name)}</div>
          <div class="hash">${esc(e.entry_hash)}</div>
        </div>`).join("")}
      <p style="font-size:11.5px;color:var(--ink-3);margin:6px 0 0">
        Each hash covers the one before it. Altering any earlier entry breaks every
        hash after it, so a record cannot be rewritten once the next decision is taken.
      </p>
    </div>` : ""}`;
}

async function openTicket(sevaId) {
  const drawer = $("#drawer"), scrim = $("#scrim");
  $("#dr-title").textContent = "Loading…";
  $("#dr-id").textContent = sevaId;
  $("#dr-body").innerHTML = `<div class="empty">Fetching file…</div>`;
  drawer.classList.add("open"); scrim.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");

  try {
    const d = await api(`/api/tickets/${encodeURIComponent(sevaId)}`);
    $("#dr-title").textContent = `${d.citizen} · ${d.service}`;
    $("#dr-body").innerHTML = renderDetail(d);
  } catch (err) {
    $("#dr-title").textContent = "Could not open file";
    $("#dr-body").innerHTML = `<div class="err">${esc(err.message)}</div>`;
  }
}

function closeDrawer() {
  $("#drawer").classList.remove("open");
  $("#scrim").classList.remove("open");
  $("#drawer").setAttribute("aria-hidden", "true");
}

/* ------------------------------------------------------------------ boot */

function showView(name) {
  ["overview", "districts", "tickets", "integrity"].forEach((v) => {
    $(`#view-${v}`).hidden = v !== name;
  });
  $$("#tabs .tab").forEach((t) =>
    t.setAttribute("aria-selected", String(t.dataset.view === name)));
}

async function boot() {
  try {
    const [summary, departments, districts, bottlenecks, overrides, redflags, trend, showcase] =
      await Promise.all([
        api("/api/summary"), api("/api/departments"), api("/api/districts"),
        api("/api/bottlenecks"), api("/api/overrides"),
        api("/api/red-flags?limit=60"), api("/api/trend?weeks=12"),
        api("/api/showcase"),
      ]);

    STATE.data = { summary, departments, districts, bottlenecks, overrides, redflags, trend, showcase };

    $("#boot").remove();
    renderKpis(summary);
    renderOverview();
    renderDistricts();
    renderTickets();
    renderIntegrity();
    showView("overview");
  } catch (err) {
    $("#boot").innerHTML = `<div class="err">Could not reach the API: ${esc(err.message)}</div>`;
  }
}

$("#tabs").addEventListener("click", (e) => {
  const tab = e.target.closest(".tab");
  if (tab) showView(tab.dataset.view);
});
$("#dr-close").addEventListener("click", closeDrawer);
$("#scrim").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

boot();
