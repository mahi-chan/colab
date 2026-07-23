/**
 * Geometry helpers. Absolute pin positions must match exactly how the schematic
 * renderer draws a component so wires attach correctly. Both use the transform:
 *   translate(comp.x, comp.y) then rotate(r) about the symbol center (w/2, h/2)
 * which is equivalent to SVG `translate(x y) rotate(r cx cy)`.
 */
import type { ComponentDef, PinDef } from "../library/types";
import type { Rotation, SchematicComponent } from "./types";

export interface Point {
  x: number;
  y: number;
}

/** Rotate a local point about the symbol center, matching SVG's rotate(). */
export function rotateLocal(p: Point, rotation: Rotation, w: number, h: number): Point {
  const cx = w / 2;
  const cy = h / 2;
  const dx = p.x - cx;
  const dy = p.y - cy;
  let rx = dx;
  let ry = dy;
  switch (rotation) {
    case 90:
      rx = -dy;
      ry = dx;
      break;
    case 180:
      rx = -dx;
      ry = -dy;
      break;
    case 270:
      rx = dy;
      ry = -dx;
      break;
  }
  return { x: rx + cx, y: ry + cy };
}

/** Absolute position of a pin on a placed component. */
export function pinPosition(comp: SchematicComponent, def: ComponentDef, pin: PinDef): Point {
  const local = rotateLocal({ x: pin.x, y: pin.y }, comp.rotation, def.symbol.width, def.symbol.height);
  return { x: comp.x + local.x, y: comp.y + local.y };
}

export function pinKey(componentId: string, pinId: string): string {
  return `${componentId}:${pinId}`;
}
