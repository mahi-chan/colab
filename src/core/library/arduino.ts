/**
 * Arduino Uno (ATmega328P) component definition, generated programmatically
 * because of its pin count. Pins carry ids the ATmega328P sim model maps to
 * AVR ports (D0–D13 -> PORTD/PORTB, A0–A5 -> PORTC).
 */
import type { ComponentDef, PinDef } from "./types";

const GRID = 20;
const ROW = GRID; // vertical spacing between pins

// Right-side digital header, top -> bottom.
const RIGHT_PINS = [
  "D13", "D12", "D11", "D10", "D9", "D8", "D7", "D6", "D5", "D4", "D3", "D2", "D1", "D0",
];
// Left-side: power + analog, top -> bottom.
const LEFT_PINS = ["5V", "3V3", "GND", "VIN", "A0", "A1", "A2", "A3", "A4", "A5"];

const pad = GRID; // inner padding
const rows = Math.max(RIGHT_PINS.length, LEFT_PINS.length);
const bodyH = (rows + 1) * ROW;
const bodyW = 200;
const leadLen = GRID;

function buildPins(): PinDef[] {
  const pins: PinDef[] = [];
  RIGHT_PINS.forEach((id, i) => {
    pins.push({
      id,
      name: id,
      x: leadLen + bodyW + leadLen,
      y: pad + (i + 1) * ROW,
      role: /^D|^A/.test(id) ? "bidir" : "power",
      labelSide: "left",
    });
  });
  LEFT_PINS.forEach((id, i) => {
    pins.push({
      id,
      name: id,
      x: 0,
      y: pad + (i + 1) * ROW,
      role: id === "GND" ? "ground" : id === "5V" || id === "3V3" || id === "VIN" ? "power" : "bidir",
      labelSide: "right",
    });
  });
  return pins;
}

function buildBody(): string {
  const parts: string[] = [];
  const bx = leadLen;
  parts.push(
    `<rect x="${bx}" y="${pad}" width="${bodyW}" height="${bodyH}" rx="10" fill="rgba(0,150,170,0.08)" stroke="currentColor" stroke-width="1.5"/>`,
  );
  parts.push(
    `<text x="${bx + bodyW / 2}" y="${pad + bodyH / 2}" text-anchor="middle" font-size="16" font-weight="600" fill="currentColor" transform="rotate(-90 ${bx + bodyW / 2} ${pad + bodyH / 2})">ARDUINO UNO</text>`,
  );
  // Pin leads + labels.
  RIGHT_PINS.forEach((id, i) => {
    const y = pad + (i + 1) * ROW;
    parts.push(`<line x1="${bx + bodyW}" y1="${y}" x2="${bx + bodyW + leadLen}" y2="${y}" stroke="currentColor"/>`);
    parts.push(`<text x="${bx + bodyW - 6}" y="${y + 4}" text-anchor="end" font-size="10" fill="currentColor">${id}</text>`);
  });
  LEFT_PINS.forEach((id, i) => {
    const y = pad + (i + 1) * ROW;
    parts.push(`<line x1="0" y1="${y}" x2="${leadLen}" y2="${y}" stroke="currentColor"/>`);
    parts.push(`<text x="${leadLen + 6}" y="${y + 4}" text-anchor="start" font-size="10" fill="currentColor">${id}</text>`);
  });
  return parts.join("");
}

export const arduinoUno: ComponentDef = {
  id: "arduino-uno",
  name: "Arduino Uno",
  category: "ic-mcu",
  keywords: ["arduino", "uno", "atmega328p", "avr", "microcontroller", "mcu"],
  description: "ATmega328P microcontroller board. Runs real compiled AVR firmware via the built-in emulator.",
  refPrefix: "U",
  symbol: {
    width: leadLen * 2 + bodyW,
    height: bodyH + pad * 2,
    body: buildBody(),
    pins: buildPins(),
  },
  params: [{ key: "clock", label: "Clock", default: 16, unit: "MHz", kind: "number" }],
  model: {
    kind: "mcu-atmega328p",
    // Map Arduino pin ids to AVR (port, bit). D0-7 -> D, D8-13 -> B, A0-5 -> C.
    ledPin: "D13",
  },
};
