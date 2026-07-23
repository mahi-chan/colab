/**
 * Bundled example firmwares. Each ships with Arduino-style source (for reading
 * and editing) and a precompiled Intel-HEX image that actually runs on the
 * ATmega328P emulator. The hex was generated from hand-assembled AVR and
 * verified to toggle the correct pins. Compiling arbitrary edited source needs
 * a toolchain (an arduino-cli backend) and is on the roadmap.
 */
export interface FirmwareExample {
  id: string;
  name: string;
  description: string;
  source: string;
  hex: string;
}

export const BLINK: FirmwareExample = {
  id: "blink",
  name: "Blink",
  description: "Toggles the on-board LED on pin 13 about 1.5 times a second.",
  source: `// Blink — toggles pin 13 (built-in LED)
void setup() {
  pinMode(13, OUTPUT);
}

void loop() {
  digitalWrite(13, HIGH);
  delay(330);
  digitalWrite(13, LOW);
  delay(330);
}
`,
  hex: ":10000000259A1D9A24E180E090E00197F1F72A9566\n:04001000D1F7F7CF5E\n:00000001FF\n",
};

export const BUTTON: FirmwareExample = {
  id: "button",
  name: "Button → LED",
  description: "Mirrors a push button on pin 2 to the LED on pin 13.",
  source: `// Button — LED on pin 13 follows the button on pin 2
void setup() {
  pinMode(13, OUTPUT);
  pinMode(2, INPUT);
}

void loop() {
  digitalWrite(13, digitalRead(2));
}
`,
  hex: ":0E000000259A4A9902C02D98FCCF2D9AFACF6E\n:00000001FF\n",
};

export const SERIAL: FirmwareExample = {
  id: "serial",
  name: "Serial Hello",
  description: 'Prints "Hi" repeatedly over the serial port at 9600 baud.',
  source: `// Serial — prints "Hi" over and over
void setup() {
  Serial.begin(9600);
}

void loop() {
  Serial.println("Hi");
  delay(500);
}
`,
  hex:
    ":1000000007E60093C40000E00093C50008E00093F9\n" +
    ":10001000C10048E45091C00055FFFCCF4093C6009A\n" +
    ":1000200049E65091C00055FFFCCF4093C6004AE01E\n" +
    ":100030005091C00055FFFCCF4093C60028E080E0FF\n" +
    ":0C00400090E00197F1F72A95D1F7E3CF8B\n" +
    ":00000001FF\n",
};

export const EXAMPLES: FirmwareExample[] = [BLINK, BUTTON, SERIAL];

export function getExample(id: string): FirmwareExample | undefined {
  return EXAMPLES.find((e) => e.id === id);
}
