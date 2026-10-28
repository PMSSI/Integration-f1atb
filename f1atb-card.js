/**
 * Interactive Lovelace card for the F1ATB Solar Router integration.
 * Finds the integration's entities by itself (no configuration needed) and controls each
 * active action: waveform, max opening, override (auto / forced on / forced off).
 * Labels follow the language chosen in the integration setup (French or English).
 *
 * Loaded automatically by the integration. Manual install (without the integration's auto-load):
 * copy this file to <config>/www/ and add the resource  /local/f1atb-card.js  (JavaScript module).
 * Then in a view, add a card:  type: custom:f1atb-card
 */
const F1ATB_CARD_VERSION = "0.6.1";

const LOGO = `
<svg viewBox="44 60 186 128" class="logo">
 <rect x="118" y="96" width="72" height="86" rx="14" fill="#54565c" stroke="#2f3036" stroke-width="3.5"/>
 <g stroke="#eef0f2" stroke-width="2.8" stroke-linecap="round" fill="none">
  <path d="M154,116 L154,132"/><path d="M135,133 L173,133"/><path d="M135,133 L135,151"/><path d="M154,133 L154,153"/><path d="M173,133 L173,151"/></g>
 <circle cx="154" cy="115" r="5" fill="#eef0f2"/><circle cx="154" cy="133" r="3.6" fill="#eef0f2"/>
 <circle cx="135" cy="155" r="4.6" fill="#eef0f2"/><circle cx="154" cy="157" r="4.6" fill="#eef0f2"/><circle cx="173" cy="155" r="4.6" fill="#eef0f2"/>
 <text x="154" y="177" fill="#e6e7ea" font-family="Arial" font-weight="700" font-size="14" text-anchor="middle">F1ATB</text>
 <g stroke="#17181c" stroke-width="5.5" stroke-linecap="round"><path d="M192,120 L214,120"/><path d="M192,139 L214,139"/><path d="M192,158 L214,158"/></g>
 <polygon points="224,120 213,113.5 213,126.5" fill="#17181c"/><polygon points="224,139 213,132.5 213,145.5" fill="#17181c"/><polygon points="224,158 213,151.5 213,164.5" fill="#17181c"/>
 <path d="M100,120 C100,142 106,150 118,150" fill="none" stroke="#17181c" stroke-width="8" stroke-linecap="round"/>
 <polygon points="70,66 160,88 138,128 48,106" fill="#17181c"/><polygon points="72.1,67.9 156.6,88.5 135.9,126.1 51.4,105.5" fill="#ffffff"/>
 <polygon points="75.1,71.6 97.3,77 89.3,91.6 67.1,86.2" fill="#3f4149"/><polygon points="101.8,78.1 124,83.5 116,98.1 93.8,92.7" fill="#3f4149"/><polygon points="128.5,84.6 150.7,90 142.7,104.6 120.5,99.2" fill="#3f4149"/>
 <polygon points="65.3,89.4 87.5,94.8 79.5,109.4 57.3,104" fill="#3f4149"/><polygon points="92,95.9 114.2,101.3 106.2,115.9 84,110.5" fill="#3f4149"/><polygon points="118.7,102.4 140.9,107.8 132.9,122.4 110.7,117" fill="#3f4149"/>
</svg>`;

const STYLE = `
:host{
 /* Semantic colours (fixed: they carry meaning) */
 --imp:#f0663d;--exp:#12b981;--triac:#2f7ff0;--relais:#0ea5a5;
 /* Surfaces / text / lines: follow the HA theme (dark <-> light) */
 --ink:var(--primary-text-color,#141821);
 --ink2:var(--secondary-text-color,#565c6a);
 --muted:var(--secondary-text-color,#8a909c);
 --line:var(--divider-color,#e6e8ee);
 --surf:var(--ha-card-background,var(--card-background-color,#fff));
 --plane:var(--secondary-background-color,#f4f6f9);
}
.wrap{background:var(--surf);border-radius:16px;overflow:hidden;font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif);color:var(--ink)}
.head{display:flex;align-items:center;gap:12px;padding:14px 18px}
.logo{height:44px;width:auto;flex:0 0 auto}
.title{font-size:17px;font-weight:700}
.sub{font-size:12px;color:var(--muted);display:flex;align-items:center;gap:6px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--muted);flex:none}
.dot.on{background:var(--exp)}.dot.off{background:var(--imp)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;padding:0 18px 14px}
.kpi{background:var(--plane);border:1px solid var(--line);border-radius:12px;padding:11px 13px}
.kpi .l{font-size:10.5px;text-transform:uppercase;letter-spacing:.4px;color:var(--muted);font-weight:600;display:flex;align-items:center;gap:6px}
.kpi .v{font-size:22px;font-weight:680;letter-spacing:-.5px;margin-top:5px;line-height:1}
.kpi .v small{font-size:12px;font-weight:500;color:var(--ink2)}
.tag{width:8px;height:8px;border-radius:3px;display:inline-block}
.temps{display:flex;flex-wrap:wrap;gap:8px;padding:0 18px 14px;margin-top:-4px}
.tchip{display:flex;align-items:center;gap:6px;background:var(--plane);border:1px solid var(--line);border-radius:20px;padding:6px 12px;font-size:12.5px}
.tchip .tn{color:var(--ink2);font-weight:600}
.tchip .tv{color:var(--ink);font-weight:700;font-variant-numeric:tabular-nums}
.act{margin:0 14px 14px;border:1px solid var(--line);border-radius:14px;padding:14px 16px;background:var(--surf)}
.act .top{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px}
.act .nm{font-size:15px;font-weight:650}
.act .ouv{font-size:15px;font-weight:700;color:var(--triac)}
.bar{height:8px;border-radius:5px;background:var(--line);overflow:hidden;margin-bottom:14px}
.bar i{display:block;height:100%;border-radius:5px;background:var(--triac);transition:width .4s}
.row{margin-bottom:12px}
.row>.lab{font-size:11.5px;color:var(--ink2);font-weight:600;margin-bottom:6px;display:flex;justify-content:space-between}
.seg{display:flex;flex-wrap:wrap;gap:6px}
.seg button{flex:1 1 auto;min-width:64px;border:1px solid var(--line);background:var(--plane);color:var(--ink2);border-radius:9px;padding:8px 10px;font-size:12.5px;font-weight:600;cursor:pointer;transition:all .12s}
.seg button:hover{border-color:var(--primary-color,var(--triac))}
.seg button.on{background:var(--triac);border-color:var(--triac);color:#fff;box-shadow:0 2px 7px rgba(47,127,240,.3)}
.forc button.on.marche{background:var(--exp);border-color:var(--exp);box-shadow:0 2px 7px rgba(18,185,129,.3)}
.forc button.on.arret{background:var(--imp);border-color:var(--imp);box-shadow:0 2px 7px rgba(240,102,61,.3)}
.slider{display:flex;align-items:center;gap:10px}
.slider input[type=range]{flex:1;accent-color:var(--triac)}
.slider .val{font-size:14px;font-weight:700;min-width:44px;text-align:right}
.hint{color:var(--triac);font-weight:700}
.hint2{color:var(--muted);font-weight:500;font-size:11px}
.pwr{display:flex;align-items:center;gap:9px}
.pwr input[type=number],.pmax input[type=number]{border:1px solid var(--line);border-radius:10px;background:var(--plane);color:var(--ink);font-weight:650;font-variant-numeric:tabular-nums}
.pwr input[type=number]{width:96px;padding:9px 11px;font-size:16px}
.u{color:var(--muted);font-size:13px}
.ghost{margin-left:auto;padding:9px 15px;border:1px solid var(--line);border-radius:10px;background:var(--plane);color:var(--ink2);font-weight:600;cursor:pointer;font-size:13px;transition:all .12s}
.ghost:hover{border-color:var(--primary-color,var(--triac))}
.pmax{display:flex;align-items:center;gap:7px;font-size:11.5px;color:var(--muted);margin-top:9px;flex-wrap:wrap}
.pmax input[type=number]{width:78px;padding:6px 9px;font-size:12.5px;font-weight:600}
.cal{margin-left:auto;padding:6px 12px;border:1px solid var(--triac);border-radius:9px;background:transparent;color:var(--triac);font-weight:700;font-size:12px;cursor:pointer;transition:all .12s}
.cal:hover{background:var(--triac);color:#fff}
.cal.busy{border-color:var(--muted);color:var(--muted);cursor:progress}
.cal.busy:hover{background:transparent;color:var(--muted)}
.empty{padding:26px;text-align:center;color:var(--muted);font-size:13px}
`;

const I18N = {
  fr: {
    router: "Routeur F1ATB", unavailable: "Indisponible", online: "En ligne", offline: "Hors ligne",
    noAnswer: "Le routeur ne répond pas (hors tension ?).<br>La carte se remplit dès qu'il est joignable.",
    noAction: "Aucune action active.<br>Activez une action sur le routeur pour la piloter ici.",
    offlineActions: "Routeur hors ligne.<br>Les commandes réapparaîtront à la remise sous tension.",
    grid_import: "Soutirée", grid_export: "Injectée", routed: "Routée", channel: "Canal",
    waveform: "Forme d'onde", autoMax: "Ouverture max (Auto)", autoHint: "routage normal",
    forcedOpening: "Ouverture (marche forcée)", forcedHint: "si forcé", override: "Forçage",
    overrideLabels: ["Auto", "Marche forcée", "Arrêt forcé"],
    forcedPower: "Marche forcée à une puissance", clear: "Effacer", clearTitle: "Remettre à 0 (retour Auto)",
    maxPower: "Puissance max de l'appareil", calibrate: "⚙ Calibrer", calibrating: "Calibration…",
    action: "Action", broken: "Carte F1ATB momentanément indisponible.", tank: "Ballon",
  },
  en: {
    router: "F1ATB router", unavailable: "Unavailable", online: "Online", offline: "Offline",
    noAnswer: "The router does not answer (powered off?).<br>The card fills in as soon as it is reachable.",
    noAction: "No active action.<br>Enable an action on the router to control it here.",
    offlineActions: "Router offline.<br>The controls come back when it is powered on again.",
    grid_import: "Grid import", grid_export: "Grid export", routed: "Routed", channel: "Channel",
    waveform: "Waveform", autoMax: "Max opening (auto)", autoHint: "normal routing",
    forcedOpening: "Forced-on opening", forcedHint: "when forced", override: "Override",
    overrideLabels: ["Auto", "Forced on", "Forced off"],
    forcedPower: "Forced on at a given power", clear: "Clear", clearTitle: "Reset to 0 (back to auto)",
    maxPower: "Appliance max power", calibrate: "⚙ Calibrate", calibrating: "Calibrating…",
    action: "Action", broken: "F1ATB card temporarily unavailable.", tank: "Tank",
  },
};
const OVERRIDE_CLS = ["", "marche", "arret"]; // by option index: auto, forced on, forced off

// HTML escaping: router / action / probe names are free text (firmware) injected into innerHTML.
const ESC = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const OK = (s) => !!s && s.state !== "unavailable" && s.state !== "unknown";

class F1atbCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._sig = null;
  }

  set hass(hass) {
    this._hass = hass;
    // Never rebuild while the user is typing in a number field or has a finger/mouse down on
    // a control: the rebuild would drop the focus, the typed value, the tap or the slider drag.
    const ae = this._root && this._root.activeElement;
    if (this._pointer || (ae && ae.tagName === "INPUT" && ae.type === "number")) {
      this._pending = true;
      return;
    }
    this._render();
  }

  _lang() {
    const conn = this._connEid ? this._hass.states[this._connEid] : null;
    const chosen = conn && conn.attributes && conn.attributes.f1atb_language;
    const ha = String(this._hass.language || (this._hass.locale && this._hass.locale.language) || "en");
    return chosen === "fr" || chosen === "en" ? chosen : (ha.toLowerCase().indexOf("fr") === 0 ? "fr" : "en");
  }

  _entities() {
    // Entities of the integration: by registry platform when available (keeps working while
    // they are unavailable), else by their f1atb_kind attribute. Unavailable entities lose
    // their attributes, so the last known kind / action of each entity is cached.
    const states = this._hass.states || {};
    const reg = this._hass.entities || {};
    this._meta = this._meta || {};
    const out = [];
    Object.keys(states).forEach((eid) => {
      const s = states[eid];
      const a = (s && s.attributes) || {};
      const ours = reg[eid] ? reg[eid].platform === "f1atb" : !!a.f1atb_kind;
      if (!ours) return;
      if (a.f1atb_kind) {
        this._meta[eid] = { kind: a.f1atb_kind, index: a.action_index, name: a.action_name, ch: a.temp_channel, nom: a.nom };
      }
      if (this._meta[eid]) out.push(eid);
    });
    return out;
  }

  _st(eid) { return this._hass.states[eid]; }

  _bindRootOnce() {
    if (this._rootBound) return;
    this._rootBound = true;
    this._root.addEventListener("pointerdown", () => { this._pointer = true; }, true);
    const release = () => {
      this._pointer = false;
      // Let the click / change event fire on the current DOM before re-rendering.
      setTimeout(() => this._flush(), 300);
    };
    this._root.addEventListener("pointerup", release, true);
    this._root.addEventListener("pointercancel", release, true);
    this._root.addEventListener("focusout", () => setTimeout(() => this._flush(), 0), true);
  }

  _flush() {
    if (!this._pending || this._pointer) return;
    const ae = this._root.activeElement;
    if (ae && ae.tagName === "INPUT" && ae.type === "number") return;
    this._pending = false;
    this._render();
  }

  _render() {
    if (!this._hass) return;
    if (!this._root) this._root = this.attachShadow({ mode: "open" });
    this._bindRootOnce();
    // Never throw (HA would show "configuration error"), e.g. while entities are unavailable.
    try {
      this._renderInner();
    } catch (e) {
      console.error("f1atb-card:", e);
      this._sig = null;
      const t = I18N[this._lang ? this._lang() : "en"] || I18N.en;
      this._root.innerHTML = `<ha-card><div style="padding:18px;color:var(--secondary-text-color,#888)">${t.broken}</div></ha-card>`;
    }
  }

  _renderInner() {
    const eids = this._entities();
    const meta = this._meta;
    this._connEid = eids.filter((e) => meta[e].kind === "connected")[0] || null;
    const lang = this._lang();
    const t = I18N[lang];
    const locale = lang === "fr" ? "fr-FR" : "en-US";
    const FMT = (n, d) => (n == null || isNaN(n)) ? "—" : Number(n).toLocaleString(locale, { maximumFractionDigits: d || 0, minimumFractionDigits: d || 0 });

    // Re-render only when one of OUR entities changed (set hass fires for every state change
    // in Home Assistant, several times per second).
    const sig = lang + "|" + eids.map((e) => { const s = this._st(e); return e + ":" + (s ? s.last_updated + s.state : ""); }).join("|");
    if (sig === this._sig) return;
    this._sig = sig;

    if (!eids.length) {
      this._root.innerHTML = `<style>${STYLE}</style>
        <ha-card><div class="wrap">
          <div class="head">${LOGO}<div><div class="title">${t.router}</div>
            <div class="sub"><span class="dot off"></span>${t.unavailable}</div></div></div>
          <div class="empty">${t.noAnswer}</div>
        </div></ha-card>`;
      return;
    }

    const globals = {};
    const actions = {}; // index -> {kind: eid}
    for (const eid of eids) {
      const m = meta[eid];
      if (m.index !== undefined && m.index !== null) {
        const A = (actions[m.index] = actions[m.index] || {});
        A[m.kind] = eid;
        if (m.name) A.name = m.name;
      } else {
        globals[m.kind] = eid;
      }
    }
    // Router name from the device of an entity (hass.entities / devices may be missing).
    let routerName = t.router;
    const ents = this._hass.entities || {};
    const devs = this._hass.devices || {};
    const ent = ents[eids[0]];
    const dev = ent && ent.device_id ? devs[ent.device_id] : null;
    if (dev && dev.name_by_user) routerName = dev.name_by_user;
    else if (dev && dev.name) routerName = dev.name;

    const online = this._connEid ? ((this._st(this._connEid) || {}).state === "on") : true;

    const kpi = (kind, label, tagVar, unit) => {
      const s = globals[kind] ? this._st(globals[kind]) : null;
      const v = OK(s) ? Number(s.state) : null;
      return `<div class="kpi"><div class="l"><span class="tag" style="background:var(${tagVar})"></span>${label}</div>
        <div class="v">${FMT(v, 0)}<small>${unit}</small></div></div>`;
    };

    // Hot-water tank model (optional): charge % and litres at 40 °C still available
    let tankHtml = "";
    const tankS = globals.tank_charge ? this._st(globals.tank_charge) : null;
    if (OK(tankS)) {
      const waterS = globals.tank_hot_water ? this._st(globals.tank_hot_water) : null;
      const litres = OK(waterS) ? ` · ${FMT(Number(waterS.state), 0)} L` : "";
      tankHtml = `<div class="kpi"><div class="l"><span class="tag" style="background:var(--relais)"></span>${t.tank}</div>
        <div class="v">${FMT(Number(tankS.state), 0)}<small>%${litres}</small></div></div>`;
    }

    // Temperatures (configured channels): chips sorted by channel
    const tempEids = eids.filter((e) => meta[e].kind === "temperature")
      .sort((a, b) => (meta[a].ch || 0) - (meta[b].ch || 0));
    let tempHtml = "";
    if (tempEids.length) {
      tempHtml = `<div class="temps">` + tempEids.map((e) => {
        const s = this._st(e);
        const ch = meta[e].ch;
        const nm = meta[e].nom || (t.channel + " " + (ch === undefined || ch === null ? "?" : ch));
        const disp = OK(s) && !isNaN(Number(s.state)) ? FMT(Number(s.state), 1) + "°C" : "—";
        return `<div class="tchip">🌡<span class="tn">${ESC(nm)}</span><span class="tv">${disp}</span></div>`;
      }).join("") + `</div>`;
    }

    const actIdx = Object.keys(actions).map(Number).sort((a, b) => a - b);
    let actionsHtml = "";
    if (actIdx.length === 0) {
      actionsHtml = `<div class="empty">${online ? t.noAction : t.offlineActions}</div>`;
    }
    for (const i of actIdx) {
      const A = actions[i];
      const ouvS = A.ouverture ? this._st(A.ouverture) : null;
      const ouv = OK(ouvS) ? Number(ouvS.state) : null;
      const fondeS = A.forme_onde ? this._st(A.forme_onde) : null;
      const omS = A.ouverture_max ? this._st(A.ouverture_max) : null;
      const forcS = A.forcage ? this._st(A.forcage) : null;
      const autoS = A.auto_ouverture_max ? this._st(A.auto_ouverture_max) : null;

      // waveform: segmented buttons (options already in the chosen language)
      let ondeHtml = "";
      if (OK(fondeS)) {
        const opts = fondeS.attributes.options || [];
        ondeHtml = `<div class="row"><div class="lab"><span>${t.waveform}</span></div><div class="seg" data-eid="${A.forme_onde}">` +
          opts.map((o) => `<button class="${o === fondeS.state ? "on" : ""}" data-opt="${ESC(o)}">${ESC(o)}</button>`).join("") + `</div></div>`;
      }
      // max opening in AUTO routing: slider
      let autoHtml = "";
      if (OK(autoS)) {
        const av = Number(autoS.state);
        autoHtml = `<div class="row"><div class="lab"><span>${t.autoMax}</span><span class="hint2">${t.autoHint}</span></div>
          <div class="slider"><input type="range" min="0" max="100" step="1" value="${av}" data-role="om" data-eid="${A.auto_ouverture_max}">
          <span class="val">${FMT(av)}%</span></div></div>`;
      }
      // opening applied while FORCED ON (ForceOuvre): slider
      let omHtml = "";
      if (OK(omS)) {
        const val = Number(omS.state);
        omHtml = `<div class="row"><div class="lab"><span>${t.forcedOpening}</span><span class="hint2">${t.forcedHint}</span></div>
          <div class="slider"><input type="range" min="0" max="100" step="1" value="${val}" data-role="om" data-eid="${A.ouverture_max}">
          <span class="val">${FMT(val)}%</span></div></div>`;
      }
      // override: auto / forced on / forced off. data-opt = the entity's REAL option;
      // meaning and style come from the option index, so it works in every language.
      let forcHtml = "";
      if (OK(forcS)) {
        const opts = forcS.attributes.options || [];
        forcHtml = `<div class="row"><div class="lab"><span>${t.override}</span></div><div class="seg forc" data-eid="${A.forcage}">` +
          opts.map((v, k) => `<button class="${forcS.state === v ? "on " + (OVERRIDE_CLS[k] || "") : ""}" data-opt="${ESC(v)}">${ESC(t.overrideLabels[k] || v)}</button>`).join("") + `</div></div>`;
      }

      // forced on at a given power (the opening is computed automatically)
      let mfHtml = "";
      const mfS = A.marche_forcee_w ? this._st(A.marche_forcee_w) : null;
      if (OK(mfS)) {
        const pmaxS = A.puissance_max ? this._st(A.puissance_max) : null;
        const pmax = (OK(pmaxS) ? Number(pmaxS.state) : Number(mfS.attributes.puissance_max)) || 3000;
        const calibrating = !!(OK(pmaxS) && pmaxS.attributes.calibrating);
        const mfVal = Number(mfS.state) || 0;
        const op = pmax ? Math.max(0, Math.min(100, Math.round(mfVal / pmax * 100))) : 0;
        const calBtn = A.calibrer
          ? `<button class="cal ${calibrating ? "busy" : ""}" data-role="cal" data-eid="${A.calibrer}" ${calibrating ? "disabled" : ""}>${calibrating ? t.calibrating : t.calibrate}</button>`
          : ``;
        mfHtml = `<div class="row"><div class="lab"><span>${t.forcedPower}</span><span class="hint" data-role="mfpct">→ ${op} %</span></div>
          <div class="pwr">
            <input type="number" inputmode="numeric" min="0" max="${pmax}" step="50" value="${mfVal}" data-role="mfw" data-eid="${A.marche_forcee_w}" data-pmax="${pmax}"><span class="u">W</span>
            <button class="ghost" data-role="mfauto" data-eid="${A.marche_forcee_w}" title="${t.clearTitle}">${t.clear}</button>
          </div>`
          + (A.puissance_max ? `<div class="pmax">${t.maxPower} <input type="number" inputmode="numeric" min="0" step="50" value="${pmax}" data-role="pmax" data-eid="${A.puissance_max}"><span class="u">W</span>${calBtn}</div>` : ``)
          + `</div>`;
      }

      actionsHtml += `<div class="act">
        <div class="top"><div class="nm">${ESC(A.name || t.action + " " + i)}</div><div class="ouv">${ouv == null ? "" : FMT(ouv) + " %"}</div></div>
        <div class="bar"><i style="width:${Math.max(0, Math.min(100, ouv || 0))}%"></i></div>
        ${ondeHtml}${autoHtml}${forcHtml}${omHtml}${mfHtml}
      </div>`;
    }

    this._root.innerHTML = `<style>${STYLE}</style>
      <ha-card><div class="wrap">
        <div class="head">${LOGO}<div><div class="title">${ESC(routerName)}</div>
          <div class="sub"><span class="dot ${online ? "on" : "off"}"></span>${online ? t.online : t.offline}</div></div></div>
        <div class="kpis">
          ${kpi("grid_import_power", t.grid_import, "--imp", "W")}
          ${kpi("grid_export_power", t.grid_export, "--exp", "W")}
          ${kpi("routed_power", t.routed, "--triac", "W")}
          ${tankHtml}
        </div>
        ${tempHtml}
        ${actionsHtml}
      </div></ha-card>`;

    this._bind();
  }

  _bind() {
    // Segmented selects (waveform + override)
    this._root.querySelectorAll(".seg").forEach((seg) => {
      const eid = seg.getAttribute("data-eid");
      seg.querySelectorAll("button").forEach((b) => {
        b.onclick = () => {
          this._hass.callService("select", "select_option", { entity_id: eid, option: b.getAttribute("data-opt") });
        };
      });
    });
    // Opening sliders
    this._root.querySelectorAll('input[data-role="om"]').forEach((sl) => {
      const eid = sl.getAttribute("data-eid");
      const val = sl.parentElement.querySelector(".val");
      sl.oninput = () => { if (val) val.textContent = sl.value + "%"; };
      sl.onchange = () => {
        this._hass.callService("number", "set_value", { entity_id: eid, value: Number(sl.value) });
      };
    });
    // Forced-on power (W): the opening % updates live, writing forces the routing on
    this._root.querySelectorAll('input[data-role="mfw"]').forEach((inp) => {
      const eid = inp.getAttribute("data-eid");
      const pmax = Number(inp.getAttribute("data-pmax")) || 3000;
      const row = inp.closest(".row");
      const pct = row ? row.querySelector('[data-role="mfpct"]') : null;
      inp.oninput = () => {
        const op = pmax ? Math.max(0, Math.min(100, Math.round((Number(inp.value) || 0) / pmax * 100))) : 0;
        if (pct) pct.textContent = "→ " + op + " %";
      };
      inp.onchange = () => {
        const v = Math.min(pmax, Math.max(0, Number(inp.value) || 0)); // capped at the max power
        inp.value = v;
        this._hass.callService("number", "set_value", { entity_id: eid, value: v });
      };
    });
    // Clear: ends the forced-on (sets 0)
    this._root.querySelectorAll('button[data-role="mfauto"]').forEach((b) => {
      const eid = b.getAttribute("data-eid");
      b.onclick = () => {
        const row = b.closest(".row");
        const inp = row ? row.querySelector('input[data-role="mfw"]') : null;
        if (inp) inp.value = 0;
        const pct = row ? row.querySelector('[data-role="mfpct"]') : null;
        if (pct) pct.textContent = "→ 0 %";
        this._hass.callService("number", "set_value", { entity_id: eid, value: 0 });
      };
    });
    // MANUAL entry of the appliance max power
    this._root.querySelectorAll('input[data-role="pmax"]').forEach((inp) => {
      const eid = inp.getAttribute("data-eid");
      inp.onchange = () => {
        this._hass.callService("number", "set_value", { entity_id: eid, value: Math.max(0, Number(inp.value) || 0) });
      };
    });
    // Calibrate: automatic measurement of the max power
    this._root.querySelectorAll('button[data-role="cal"]').forEach((b) => {
      const eid = b.getAttribute("data-eid");
      b.onclick = () => {
        if (b.classList.contains("busy")) return;
        this._hass.callService("button", "press", { entity_id: eid });
      };
    });
  }

  getCardSize() { return 6; }
  static getStubConfig() { return {}; }
}

// IDEMPOTENT registration. The file may be loaded TWICE: automatically by the integration
// (add_extra_js_url) AND through a manually added Lovelace resource. Without this guard,
// customElements.define() throws "already defined", the module crashes and the frontend
// (especially the mobile app) shows "unable to load the application".
if (customElements.get("f1atb-card")) {
  // Already defined: ANOTHER copy was loaded first (typically an old manual Lovelace
  // resource `/local/f1atb-card.js` that HACS never updates).
  console.warn(
    `[f1atb-card] v${F1ATB_CARD_VERSION} ignored: "f1atb-card" is already defined by another file. ` +
    `Remove the manual Lovelace resource (Settings → Dashboards → Resources) ` +
    `and /config/www/f1atb-card.js: the integration loads the card automatically.`
  );
} else {
  customElements.define("f1atb-card", F1atbCard);
  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c && c.type === "f1atb-card")) {
    window.customCards.push({
      type: "f1atb-card",
      name: "F1ATB Solar Router",
      description: "Interactive card to control the F1ATB solar router (waveform, max opening, override, forced on at a given power).",
      preview: true,
    });
  }
  console.info(`%c F1ATB-CARD %c v${F1ATB_CARD_VERSION} `, "background:#2f7ff0;color:#fff;border-radius:4px 0 0 4px;padding:2px 6px", "background:#17181c;color:#fff;border-radius:0 4px 4px 0;padding:2px 6px");
}
