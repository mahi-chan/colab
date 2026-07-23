/**
 * ATmega328P chip: a thin wrapper over avr8js that runs real compiled AVR
 * firmware and maps Arduino pin ids (D0–D13, A0–A5) to AVR ports.
 *
 *   D0–D7  -> PORTD (PD0–PD7)
 *   D8–D13 -> PORTB (PB0–PB5)
 *   A0–A5  -> PORTC (PC0–PC5)
 */
import {
  AVRIOPort,
  AVRTimer,
  AVRUSART,
  CPU,
  PinState,
  avrInstruction,
  portBConfig,
  portCConfig,
  portDConfig,
  timer0Config,
  timer1Config,
  timer2Config,
  usart0Config,
} from "avr8js";
import type { Chip, DigitalLevel } from "./Chip";
import { hexToProgram } from "./hex";

type PortName = "B" | "C" | "D";
interface PinMap {
  port: PortName;
  bit: number;
}

function buildPinMap(): Record<string, PinMap> {
  const map: Record<string, PinMap> = {};
  for (let d = 0; d <= 7; d++) map[`D${d}`] = { port: "D", bit: d };
  for (let d = 8; d <= 13; d++) map[`D${d}`] = { port: "B", bit: d - 8 };
  for (let a = 0; a <= 5; a++) map[`A${a}`] = { port: "C", bit: a };
  // Serial aliases.
  map["RX"] = { port: "D", bit: 0 };
  map["TX"] = { port: "D", bit: 1 };
  return map;
}

const PIN_MAP = buildPinMap();

export class ATmega328P implements Chip {
  readonly clockHz: number;
  private program: Uint16Array;
  private cpu!: CPU;
  private portB!: AVRIOPort;
  private portC!: AVRIOPort;
  private portD!: AVRIOPort;
  private usart!: AVRUSART;

  onPinChange?: (pinId: string, level: DigitalLevel) => void;
  onSerialByte?: (byte: number) => void;

  constructor(hex: string, clockHz = 16_000_000) {
    this.clockHz = clockHz;
    this.program = hexToProgram(hex);
    this.build();
  }

  private build(): void {
    this.cpu = new CPU(this.program);
    this.portB = new AVRIOPort(this.cpu, portBConfig);
    this.portC = new AVRIOPort(this.cpu, portCConfig);
    this.portD = new AVRIOPort(this.cpu, portDConfig);
    // Timers self-register with the CPU clock (delay(), millis(), PWM); the CPU
    // retains them via its clock-event callbacks, so we don't need to store them.
    new AVRTimer(this.cpu, timer0Config);
    new AVRTimer(this.cpu, timer1Config);
    new AVRTimer(this.cpu, timer2Config);
    this.usart = new AVRUSART(this.cpu, usart0Config, this.clockHz);
    this.usart.onByteTransmit = (b) => this.onSerialByte?.(b);

    const notify = (port: PortName) => () => {
      if (!this.onPinChange) return;
      for (const [pinId, m] of Object.entries(PIN_MAP)) {
        if (m.port === port) this.onPinChange(pinId, this.getPinLevel(pinId));
      }
    };
    this.portB.addListener(notify("B"));
    this.portC.addListener(notify("C"));
    this.portD.addListener(notify("D"));
  }

  loadHex(hex: string): void {
    this.program = hexToProgram(hex);
    this.build();
  }

  reset(): void {
    this.build();
  }

  execute(cycles: number): void {
    const target = this.cpu.cycles + cycles;
    while (this.cpu.cycles < target) {
      avrInstruction(this.cpu);
      this.cpu.tick();
    }
  }

  private portOf(name: PortName): AVRIOPort {
    return name === "B" ? this.portB : name === "C" ? this.portC : this.portD;
  }

  getPinLevel(pinId: string): DigitalLevel {
    const m = PIN_MAP[pinId];
    if (!m) return "input";
    const state = this.portOf(m.port).pinState(m.bit);
    if (state === PinState.High) return "high";
    if (state === PinState.Low) return "low";
    return "input";
  }

  isOutput(pinId: string): boolean {
    const m = PIN_MAP[pinId];
    if (!m) return false;
    const state = this.portOf(m.port).pinState(m.bit);
    return state === PinState.High || state === PinState.Low;
  }

  setInput(pinId: string, high: boolean): void {
    const m = PIN_MAP[pinId];
    if (!m) return;
    this.portOf(m.port).setPin(m.bit, high);
  }

  serialWrite(byte: number): void {
    this.usart.writeByte(byte);
  }
}
