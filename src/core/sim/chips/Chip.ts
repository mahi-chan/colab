/**
 * Pluggable chip interface. The engine talks to every microcontroller/processor
 * through this contract, so adding ESP32/RP2040/8085 later means implementing
 * `Chip` — no engine changes.
 */

export type DigitalLevel = "high" | "low" | "input";

export interface Chip {
  readonly clockHz: number;
  /** Reset CPU + peripherals and reload firmware. */
  reset(): void;
  /** Advance the CPU by up to `cycles` clock cycles. */
  execute(cycles: number): void;
  /** Current output level of a component pin id (e.g. "D13"). */
  getPinLevel(pinId: string): DigitalLevel;
  /** True if the CPU has this pin configured as an output. */
  isOutput(pinId: string): boolean;
  /** Drive an input pin (from a wired button / logic level). */
  setInput(pinId: string, high: boolean): void;
  /** Called when any output pin changes; use to refresh the UI. */
  onPinChange?: (pinId: string, level: DigitalLevel) => void;
  /** Serial (USART) bridge, if the chip has one. */
  onSerialByte?: (byte: number) => void;
  /** Send a byte to the chip's serial RX. */
  serialWrite(byte: number): void;
}
