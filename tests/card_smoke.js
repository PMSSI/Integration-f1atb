// Renders the card with a minimal DOM and a fake hass: node tests/card_smoke.js
const fs = require("fs");
const path = require("path");
class FakeRoot {
  constructor() { this.innerHTML = ""; this.activeElement = null; this.renders = 0; }
  addEventListener() {}
  querySelectorAll() { return []; }
}
global.HTMLElement = class { attachShadow() { return new FakeRoot(); } };
const registry = {};
global.customElements = { get: (n) => registry[n], define: (n, c) => { registry[n] = c; } };
global.window = {};
eval(fs.readFileSync(path.join(__dirname, "../custom_components/f1atb/f1atb-card.js"), "utf8"));
const Card = registry["f1atb-card"];

const P = "sensor.routeur_solaire_";
function hassFor(lang, opts = {}) {
  const off = !!opts.unavailable;
  const st = (id, state, attrs) => [id, { entity_id: id, state: off && !attrs.f1atb_language ? "unavailable" : state,
    last_updated: (opts.stamp || "t1") + id, attributes: off && !attrs.f1atb_language ? {} : attrs }];
  const act = (kind, extra) => Object.assign({ f1atb_kind: kind, action_index: 1, action_name: "Chauffe<b>Eau</b>" }, extra || {});
  const fr = lang === "fr";
  const states = Object.fromEntries([
    st("binary_sensor.routeur_solaire_connecte", off ? "off" : "on", { f1atb_kind: "connected", f1atb_language: lang }),
    st(P + "soutiree_reseau", "12", { f1atb_kind: "grid_import_power" }),
    st(P + "injectee_reseau", "340", { f1atb_kind: "grid_export_power" }),
    st(P + "puissance_routee", "1879", { f1atb_kind: "routed_power" }),
    st(P + "r1_ouverture", "64", act("ouverture")),
    st("select.routeur_solaire_r1_forme_d_onde", fr ? "Demi-sinus" : "Half-sine",
      act("forme_onde", { options: fr ? ["Inactif", "On/Off", "Demi-sinus"] : ["Inactive", "On/Off", "Half-sine"] })),
    st("select.routeur_solaire_r1_forcage", fr ? "Forcé Marche" : "Forced on",
      act("forcage", { options: fr ? ["Auto", "Forcé Marche", "Forcé Arrêt"] : ["Auto", "Forced on", "Forced off"] })),
    st("number.routeur_solaire_r1_ouverture_max", "24", act("ouverture_max")),
    st("number.routeur_solaire_r1_ouverture_max_auto", "58", act("auto_ouverture_max")),
    st("number.routeur_solaire_r1_puissance_max", "2336", act("puissance_max", { calibrating: false })),
    st("number.routeur_solaire_r1_marche_forcee_w", "1400", act("marche_forcee_w", { puissance_max: 2336 })),
    st("button.routeur_solaire_r1_calibrer", "unknown", act("calibrer")),
  ]);
  const entities = Object.fromEntries(Object.keys(states).map((e) => [e, { platform: "f1atb", device_id: "d1" }]));
  return { states, entities, devices: { d1: { name: "Routeur solaire" } }, language: lang, callService() {} };
}
const expect = (cond, msg) => { if (!cond) throw new Error(msg); };

// French
let c = new Card(); c.setConfig({}); c.hass = hassFor("fr");
let html = c._root.innerHTML;
expect(html.includes("Forme d'onde") && html.includes("Marche forcée") && html.includes("En ligne"), "fr labels");
expect(html.includes('class="on marche" data-opt="Forcé Marche"'), "fr override highlighted by index");
expect(!html.includes("<b>Eau"), "action name escaped");
console.log("ok fr");

// English (integration language = en, HA in French: the integration setting wins)
c = new Card(); c.setConfig({}); const h = hassFor("en"); h.language = "fr"; c.hass = h;
html = c._root.innerHTML;
expect(html.includes("Waveform") && html.includes("Forced on") && html.includes("Online"), "en labels");
expect(html.includes('class="on marche" data-opt="Forced on"'), "en override highlighted by index");
console.log("ok en");

// Same states again: no re-render
const before = c._root.innerHTML; c._root.innerHTML = "SENTINEL"; c.hass = h;
expect(c._root.innerHTML === "SENTINEL", "re-rendered although nothing changed");
c._root.innerHTML = before;
console.log("ok no re-render when unchanged");

// Entities become unavailable after a first render: layout kept (cached meta), offline shown
c.hass = hassFor("en", { unavailable: true, stamp: "t2" });
html = c._root.innerHTML;
expect(html.includes("Offline") && html.includes("ChauffeEau") === false && html.includes("Chauffe&lt;b&gt;Eau"), "action block kept while unavailable");
expect(!html.includes("Waveform"), "unavailable controls hidden");
console.log("ok unavailable keeps layout");

// Pointer down: update deferred
c._pointer = true; c._root.innerHTML = "HOLD"; c.hass = hassFor("en", { stamp: "t3" });
expect(c._root.innerHTML === "HOLD" && c._pending, "render while pointer down");
c._pointer = false; c._flush();
expect(c._root.innerHTML.includes("Waveform"), "pending render flushed");
console.log("ok pointer guard");

// No entity at all
c = new Card(); c.setConfig({}); c.hass = { states: {}, entities: {}, devices: {}, language: "fr" };
expect(c._root.innerHTML.includes("Le routeur ne répond pas"), "empty state");
console.log("ok empty");
