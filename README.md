# CircuitLab

An integrated **EDA + electronics-simulation** suite for the browser and the
desktop, modelled on [PCBX](https://www.pcbx.com). Design a schematic, browse a
directory of components, wire up an Arduino, write code, hit **Run**, and watch
real firmware drive LEDs, buttons, and serial output — all from one project.

The schematic (EDA) view and the simulation (SIM) view are two windows onto the
**same project**, exactly like PCBX keys both `/eda/sch` and `/sim` off one id.

> **Status:** working MVP foundation. The core spine is complete and verified —
> one codebase → web + desktop, a unified project model, a searchable component
> library, a schematic editor with ERC, and a simulation view that runs both the
> analog solver and real Arduino firmware. Larger PCBX features (PCB layout, full
> SPICE, exports) are architected for and listed in the roadmap below.

## Features

- **One codebase, two targets** — a React + Vite frontend runs as the web app; a
  thin [Tauri](https://tauri.app) shell wraps the identical frontend into a
  native desktop app (Windows/macOS/Linux). Platform differences (file dialogs,
  storage) hide behind a single `PlatformAdapter`.
- **Component library / directory** — a searchable, categorized catalog. Every
  part is *data* (symbol + pins + parameters + a simulation model), so the
  library scales without bespoke code. Includes passives, sources, semiconductors,
  switches, logic, and an Arduino Uno.
- **Unified EDA + SIM project model** — one `Project` holds the schematic as the
  single source of truth. Switching views never copies data.
- **Schematic editor (EDA)** — place from the library, move, rotate, wire
  pin-to-pin with automatic net inference, edit parameters, and see live **ERC**
  (floating pins, output conflicts, missing ground).
- **Simulation (SIM)** — compiles the schematic to a netlist and runs:
  - **Analog** via a Modified Nodal Analysis (MNA) DC solver (resistors, sources,
    diodes/LEDs, switches) → node voltages, LED brightness, probe readouts.
  - **Microcontroller** via [avr8js](https://github.com/wokwi/avr8js): the
    ATmega328P executes **real compiled AVR firmware**, driving GPIO/LEDs, reading
    buttons, and streaming USART to a **serial monitor**.
- **Code IDE** — a CodeMirror editor with bundled, verified example sketches
  (Blink, Button, Serial Hello) plus Intel-HEX loading.
- **Persistence** — create / open / save projects (`.clab` JSON) with autosave.

## Quick start (web)

```bash
npm install
npm run dev        # http://localhost:5173
```

Open the app — it loads a demo project (Arduino Blink + a resistor divider).
Switch to **Simulate** and press **Run**: the LED blinks from real firmware and
the divider probe reads ~2.5 V.

Other scripts:

```bash
npm run build      # type-check + production web build -> dist/
npm test           # unit tests (netlist, MNA solver, ERC, end-to-end blink)
npm run preview    # preview the production build
```

## Desktop (Tauri)

The desktop app reuses the exact web frontend. You need the
[Rust toolchain](https://www.rust-lang.org/tools/install) and your platform's
Tauri prerequisites (e.g. `webkit2gtk` on Linux).

```bash
npm run tauri dev     # run the desktop app against the dev server
npm run tauri build   # produce native installers
```

Native open/save go through Rust commands in `src-tauri/src/lib.rs`. To
regenerate the full cross-platform icon set from one source image:
`npm run tauri icon path/to/icon.png`.

## Architecture

```
src/
  core/                 platform-agnostic domain logic (no React, no platform APIs)
    project/            unified Project model, geometry, (de)serialization, demo
    library/            component catalog: types + seeded parts (incl. Arduino)
    netlist/            schematic -> nets (union-find, ground resolution)
    erc/                electrical rule checks
    sim/
      analog/mna.ts     Modified Nodal Analysis DC solver
      evaluate.ts       assemble stamps from the netlist + runtime state
      engine.ts         sim clock: step CPUs, solve circuit, feed inputs back
      chips/            Chip interface + ATmega328P (avr8js) + Intel-HEX loader
      examples.ts       verified precompiled example firmwares
    platform/           PlatformAdapter interface
  platform-web/         web adapter (File System Access API + localStorage)
  platform-desktop/     Tauri adapter (native dialogs via invoke)
  store/                Zustand stores (project + simulation runtime)
  ui/                   App shell, LibraryBrowser, canvas, EDA/SIM panels, editor
src-tauri/              Tauri desktop shell (Rust)
```

The `Chip` interface keeps microcontrollers pluggable, and the same netlist feeds
both the analog solver and the digital/MCU path — so new chips and a full SPICE
engine slot in without reworking the editor.

## Roadmap — toward full PCBX parity

- **PCB layout**: board canvas, footprint placement, routing, copper/silkscreen
  layers, real-time 3D preview, and **DRC**.
- **Editors**: symbol, footprint, and pad editors.
- **Exports**: Gerber, pick-and-place (CPL), BOM, netlist, PDF.
- **Full analog SPICE**: nonlinear BJT/MOSFET/op-amp models; DC/AC/transient
  sweeps; waveform graphs.
- **More MCUs**: ESP32, RP2040, STM32, and classic microprocessors (8085/8086/Z80)
  behind the same `Chip` interface.
- **Compile backend**: an `arduino-cli` service so any edited C++ sketch compiles,
  not just the bundled examples.
- **Cloud & community**: hosted component library, project gallery, share-by-URL,
  and real-time collaboration.

## Tech

React · TypeScript · Vite · Zustand · avr8js · CodeMirror · Tauri · Vitest.
