/**
 * Seeded component catalog. Grouped by category and consumed by the Library
 * Browser. Symbols are drawn in local space (grid = 20px) with `currentColor`
 * so they theme with light/dark automatically.
 */
import type { ComponentDef } from "./types";
import { arduinoUno } from "./arduino";

const resistor: ComponentDef = {
  id: "resistor",
  name: "Resistor",
  category: "passives",
  keywords: ["resistor", "res", "ohm", "r"],
  description: "Fixed resistor. Limits current; obeys Ohm's law.",
  refPrefix: "R",
  symbol: {
    width: 80,
    height: 20,
    body:
      `<line x1="0" y1="10" x2="24" y2="10" stroke="currentColor"/>` +
      `<rect x="24" y="4" width="32" height="12" fill="none" stroke="currentColor"/>` +
      `<line x1="56" y1="10" x2="80" y2="10" stroke="currentColor"/>`,
    pins: [
      { id: "1", x: 0, y: 10, role: "passive" },
      { id: "2", x: 80, y: 10, role: "passive" },
    ],
  },
  params: [{ key: "resistance", label: "Resistance", default: 220, unit: "Ω", kind: "number" }],
  model: { kind: "resistor", pins: { a: "1", b: "2" }, valueParam: "resistance" },
};

const capacitor: ComponentDef = {
  id: "capacitor",
  name: "Capacitor",
  category: "passives",
  keywords: ["capacitor", "cap", "farad", "c"],
  description: "Non-polarized capacitor. Open circuit at DC steady state (MVP).",
  refPrefix: "C",
  symbol: {
    width: 60,
    height: 40,
    body:
      `<line x1="0" y1="20" x2="26" y2="20" stroke="currentColor"/>` +
      `<line x1="26" y1="4" x2="26" y2="36" stroke="currentColor"/>` +
      `<line x1="34" y1="4" x2="34" y2="36" stroke="currentColor"/>` +
      `<line x1="34" y1="20" x2="60" y2="20" stroke="currentColor"/>`,
    pins: [
      { id: "1", x: 0, y: 20, role: "passive" },
      { id: "2", x: 60, y: 20, role: "passive" },
    ],
  },
  params: [{ key: "capacitance", label: "Capacitance", default: 0.0000001, unit: "F", kind: "number" }],
  model: { kind: "capacitor", pins: { a: "1", b: "2" }, valueParam: "capacitance" },
};

const inductor: ComponentDef = {
  id: "inductor",
  name: "Inductor",
  category: "passives",
  keywords: ["inductor", "coil", "henry", "l"],
  description: "Inductor. Short circuit at DC steady state (MVP).",
  refPrefix: "L",
  symbol: {
    width: 80,
    height: 20,
    body:
      `<line x1="0" y1="10" x2="16" y2="10" stroke="currentColor"/>` +
      `<path d="M16 10 a6 6 0 0 1 12 0 a6 6 0 0 1 12 0 a6 6 0 0 1 12 0 a6 6 0 0 1 12 0" fill="none" stroke="currentColor"/>` +
      `<line x1="64" y1="10" x2="80" y2="10" stroke="currentColor"/>`,
    pins: [
      { id: "1", x: 0, y: 10, role: "passive" },
      { id: "2", x: 80, y: 10, role: "passive" },
    ],
  },
  params: [{ key: "inductance", label: "Inductance", default: 0.001, unit: "H", kind: "number" }],
  model: { kind: "inductor", pins: { a: "1", b: "2" }, valueParam: "inductance" },
};

const potentiometer: ComponentDef = {
  id: "potentiometer",
  name: "Potentiometer",
  category: "passives",
  keywords: ["potentiometer", "pot", "variable resistor", "trimmer"],
  description: "Three-terminal variable resistor. Wiper taps a fraction of the track.",
  refPrefix: "RV",
  symbol: {
    width: 80,
    height: 40,
    body:
      `<line x1="0" y1="30" x2="24" y2="30" stroke="currentColor"/>` +
      `<rect x="24" y="24" width="32" height="12" fill="none" stroke="currentColor"/>` +
      `<line x1="56" y1="30" x2="80" y2="30" stroke="currentColor"/>` +
      `<line x1="40" y1="0" x2="40" y2="18" stroke="currentColor"/>` +
      `<path d="M34 18 L40 24 L46 18" fill="currentColor" stroke="currentColor"/>`,
    pins: [
      { id: "1", x: 0, y: 30, role: "passive" },
      { id: "w", name: "wiper", x: 40, y: 0, role: "passive", labelSide: "up" },
      { id: "2", x: 80, y: 30, role: "passive" },
    ],
  },
  params: [
    { key: "resistance", label: "Resistance", default: 10000, unit: "Ω", kind: "number" },
    { key: "wiper", label: "Wiper", default: 0.5, unit: "0–1", kind: "number" },
  ],
  model: { kind: "potentiometer", pins: { a: "1", w: "w", b: "2" }, valueParam: "resistance" },
};

const dcVoltage: ComponentDef = {
  id: "dc-voltage",
  name: "DC Voltage Source",
  category: "sources",
  keywords: ["battery", "dc", "voltage", "source", "cell", "vcc"],
  description: "Ideal DC voltage source / battery.",
  refPrefix: "V",
  symbol: {
    width: 40,
    height: 60,
    body:
      `<line x1="20" y1="0" x2="20" y2="18" stroke="currentColor"/>` +
      `<line x1="6" y1="18" x2="34" y2="18" stroke="currentColor"/>` +
      `<line x1="12" y1="26" x2="28" y2="26" stroke="currentColor"/>` +
      `<line x1="6" y1="34" x2="34" y2="34" stroke="currentColor"/>` +
      `<line x1="12" y1="42" x2="28" y2="42" stroke="currentColor"/>` +
      `<line x1="20" y1="42" x2="20" y2="60" stroke="currentColor"/>` +
      `<text x="36" y="12" font-size="11" fill="currentColor">+</text>`,
    pins: [
      { id: "pos", name: "+", x: 20, y: 0, role: "power", labelSide: "up" },
      { id: "neg", name: "-", x: 20, y: 60, role: "power", labelSide: "down" },
    ],
  },
  params: [{ key: "voltage", label: "Voltage", default: 5, unit: "V", kind: "number" }],
  model: { kind: "vsource", pins: { pos: "pos", neg: "neg" }, valueParam: "voltage" },
};

const vcc: ComponentDef = {
  id: "vcc-5v",
  name: "Power (5V)",
  category: "sources",
  keywords: ["power", "vcc", "5v", "rail", "supply"],
  description: "5V power rail referenced to ground.",
  refPrefix: "PWR",
  symbol: {
    width: 40,
    height: 40,
    body:
      `<line x1="20" y1="40" x2="20" y2="16" stroke="currentColor"/>` +
      `<path d="M10 16 L20 2 L30 16" fill="none" stroke="currentColor"/>` +
      `<text x="20" y="34" text-anchor="middle" font-size="10" fill="currentColor">5V</text>`,
    pins: [{ id: "p", x: 20, y: 40, role: "power", labelSide: "down" }],
  },
  params: [{ key: "voltage", label: "Voltage", default: 5, unit: "V", kind: "number" }],
  model: { kind: "power", pins: { p: "p" }, valueParam: "voltage" },
};

const ground: ComponentDef = {
  id: "ground",
  name: "Ground",
  category: "sources",
  keywords: ["ground", "gnd", "0v", "reference"],
  description: "Circuit ground / 0V reference.",
  refPrefix: "GND",
  symbol: {
    width: 40,
    height: 40,
    body:
      `<line x1="20" y1="0" x2="20" y2="16" stroke="currentColor"/>` +
      `<line x1="6" y1="16" x2="34" y2="16" stroke="currentColor"/>` +
      `<line x1="11" y1="24" x2="29" y2="24" stroke="currentColor"/>` +
      `<line x1="16" y1="32" x2="24" y2="32" stroke="currentColor"/>`,
    pins: [{ id: "g", x: 20, y: 0, role: "ground", labelSide: "up" }],
  },
  params: [],
  model: { kind: "ground", pins: { g: "g" } },
};

const diode: ComponentDef = {
  id: "diode",
  name: "Diode",
  category: "semiconductors",
  keywords: ["diode", "rectifier", "1n4148", "semiconductor"],
  description: "Rectifier diode. Conducts when forward-biased.",
  refPrefix: "D",
  symbol: {
    width: 60,
    height: 20,
    body:
      `<line x1="0" y1="10" x2="22" y2="10" stroke="currentColor"/>` +
      `<path d="M22 3 L22 17 L38 10 Z" fill="currentColor" stroke="currentColor"/>` +
      `<line x1="38" y1="3" x2="38" y2="17" stroke="currentColor"/>` +
      `<line x1="38" y1="10" x2="60" y2="10" stroke="currentColor"/>`,
    pins: [
      { id: "a", name: "A", x: 0, y: 10, role: "passive" },
      { id: "k", name: "K", x: 60, y: 10, role: "passive" },
    ],
  },
  params: [{ key: "vf", label: "Forward drop", default: 0.7, unit: "V", kind: "number" }],
  model: { kind: "diode", pins: { a: "a", k: "k" }, valueParam: "vf" },
};

const led: ComponentDef = {
  id: "led",
  name: "LED",
  category: "semiconductors",
  keywords: ["led", "light", "diode", "indicator", "lamp"],
  description: "Light-emitting diode. Lights when forward current flows.",
  refPrefix: "LED",
  symbol: {
    width: 60,
    height: 30,
    body:
      `<line x1="0" y1="15" x2="22" y2="15" stroke="currentColor"/>` +
      `<path d="M22 8 L22 22 L38 15 Z" fill="currentColor" stroke="currentColor"/>` +
      `<line x1="38" y1="8" x2="38" y2="22" stroke="currentColor"/>` +
      `<line x1="38" y1="15" x2="60" y2="15" stroke="currentColor"/>` +
      `<path d="M42 4 L48 -2 M46 4 L52 -2" stroke="currentColor"/>`,
    pins: [
      { id: "a", name: "A", x: 0, y: 15, role: "passive" },
      { id: "k", name: "K", x: 60, y: 15, role: "passive" },
    ],
  },
  params: [
    { key: "vf", label: "Forward drop", default: 1.8, unit: "V", kind: "number" },
    { key: "color", label: "Color", default: "red", kind: "select", options: ["red", "green", "blue", "yellow", "white"] },
  ],
  model: { kind: "led", pins: { a: "a", k: "k" }, valueParam: "vf" },
};

const pushbutton: ComponentDef = {
  id: "pushbutton",
  name: "Push Button",
  category: "switches",
  keywords: ["button", "pushbutton", "momentary", "switch", "tactile"],
  description: "Momentary push button. Closed only while held.",
  refPrefix: "SW",
  symbol: {
    width: 80,
    height: 40,
    body:
      `<line x1="0" y1="20" x2="24" y2="20" stroke="currentColor"/>` +
      `<line x1="24" y1="10" x2="24" y2="30" stroke="currentColor"/>` +
      `<line x1="56" y1="10" x2="56" y2="30" stroke="currentColor"/>` +
      `<line x1="56" y1="20" x2="80" y2="20" stroke="currentColor"/>` +
      `<line x1="24" y1="12" x2="56" y2="12" stroke="currentColor"/>` +
      `<line x1="40" y1="12" x2="40" y2="4" stroke="currentColor"/>`,
    pins: [
      { id: "1", x: 0, y: 20, role: "passive" },
      { id: "2", x: 80, y: 20, role: "passive" },
    ],
  },
  params: [],
  model: { kind: "switch", pins: { a: "1", b: "2" }, momentary: true },
};

const spstSwitch: ComponentDef = {
  id: "spst-switch",
  name: "Toggle Switch (SPST)",
  category: "switches",
  keywords: ["switch", "toggle", "spst", "on", "off"],
  description: "Single-pole single-throw toggle switch.",
  refPrefix: "SW",
  symbol: {
    width: 80,
    height: 30,
    body:
      `<line x1="0" y1="20" x2="24" y2="20" stroke="currentColor"/>` +
      `<circle cx="24" cy="20" r="2.5" fill="currentColor"/>` +
      `<line x1="24" y1="20" x2="54" y2="6" stroke="currentColor"/>` +
      `<circle cx="56" cy="20" r="2.5" fill="currentColor"/>` +
      `<line x1="56" y1="20" x2="80" y2="20" stroke="currentColor"/>`,
    pins: [
      { id: "1", x: 0, y: 20, role: "passive" },
      { id: "2", x: 80, y: 20, role: "passive" },
    ],
  },
  params: [{ key: "closed", label: "Closed", default: 0, kind: "select", options: ["0", "1"] }],
  model: { kind: "switch", pins: { a: "1", b: "2" }, momentary: false },
};

// ---- Symbol-only parts (simulation on the roadmap) ----
const npn: ComponentDef = {
  id: "npn-transistor",
  name: "NPN Transistor",
  category: "semiconductors",
  keywords: ["transistor", "npn", "bjt", "2n2222", "bc547"],
  description: "NPN bipolar transistor. Symbol only — device simulation is on the roadmap.",
  refPrefix: "Q",
  symbol: {
    width: 60,
    height: 60,
    body:
      `<line x1="0" y1="30" x2="20" y2="30" stroke="currentColor"/>` +
      `<line x1="20" y1="14" x2="20" y2="46" stroke="currentColor"/>` +
      `<line x1="20" y1="22" x2="44" y2="8" stroke="currentColor"/>` +
      `<line x1="20" y1="38" x2="44" y2="52" stroke="currentColor"/>` +
      `<line x1="44" y1="8" x2="44" y2="0" stroke="currentColor"/>` +
      `<line x1="44" y1="52" x2="44" y2="60" stroke="currentColor"/>` +
      `<path d="M34 46 L44 52 L38 42 Z" fill="currentColor" stroke="currentColor"/>`,
    pins: [
      { id: "b", name: "B", x: 0, y: 30, role: "input" },
      { id: "c", name: "C", x: 44, y: 0, role: "passive", labelSide: "up" },
      { id: "e", name: "E", x: 44, y: 60, role: "passive", labelSide: "down" },
    ],
  },
  params: [{ key: "hfe", label: "hFE", default: 100, kind: "number" }],
  model: { kind: "none" },
};

const andGate: ComponentDef = {
  id: "and-gate",
  name: "AND Gate",
  category: "logic",
  keywords: ["and", "gate", "logic", "7408"],
  description: "2-input AND gate. Symbol only — logic simulation is on the roadmap.",
  refPrefix: "U",
  symbol: {
    width: 80,
    height: 40,
    body:
      `<path d="M20 4 L44 4 A16 16 0 0 1 44 36 L20 36 Z" fill="none" stroke="currentColor"/>` +
      `<line x1="0" y1="12" x2="20" y2="12" stroke="currentColor"/>` +
      `<line x1="0" y1="28" x2="20" y2="28" stroke="currentColor"/>` +
      `<line x1="60" y1="20" x2="80" y2="20" stroke="currentColor"/>`,
    pins: [
      { id: "a", name: "A", x: 0, y: 12, role: "input" },
      { id: "b", name: "B", x: 0, y: 28, role: "input" },
      { id: "y", name: "Y", x: 80, y: 20, role: "output" },
    ],
  },
  params: [],
  model: { kind: "none" },
};

const orGate: ComponentDef = {
  id: "or-gate",
  name: "OR Gate",
  category: "logic",
  keywords: ["or", "gate", "logic", "7432"],
  description: "2-input OR gate. Symbol only — logic simulation is on the roadmap.",
  refPrefix: "U",
  symbol: {
    width: 80,
    height: 40,
    body:
      `<path d="M18 4 Q40 4 60 20 Q40 36 18 36 Q28 20 18 4 Z" fill="none" stroke="currentColor"/>` +
      `<line x1="0" y1="12" x2="22" y2="12" stroke="currentColor"/>` +
      `<line x1="0" y1="28" x2="22" y2="28" stroke="currentColor"/>` +
      `<line x1="60" y1="20" x2="80" y2="20" stroke="currentColor"/>`,
    pins: [
      { id: "a", name: "A", x: 0, y: 12, role: "input" },
      { id: "b", name: "B", x: 0, y: 28, role: "input" },
      { id: "y", name: "Y", x: 80, y: 20, role: "output" },
    ],
  },
  params: [],
  model: { kind: "none" },
};

export const CATALOG: ComponentDef[] = [
  resistor,
  capacitor,
  inductor,
  potentiometer,
  dcVoltage,
  vcc,
  ground,
  diode,
  led,
  pushbutton,
  spstSwitch,
  arduinoUno,
  npn,
  andGate,
  orGate,
];

const byId = new Map(CATALOG.map((c) => [c.id, c]));

export function getComponentDef(id: string): ComponentDef | undefined {
  return byId.get(id);
}
