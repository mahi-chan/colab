/**
 * Serial monitor: shows USART output from the running MCU and lets the user send
 * bytes back to its RX.
 */
import { useEffect, useRef, useState } from "react";
import { useSimStore } from "../../store/simStore";

export function SerialMonitor({ componentId }: { componentId: string | null }) {
  const serial = useSimStore((s) => (componentId ? s.serial[componentId] : "") ?? "");
  const running = useSimStore((s) => s.running);
  const sendSerial = useSimStore((s) => s.sendSerial);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [serial]);

  const send = () => {
    if (!componentId || !input) return;
    sendSerial(componentId, input + "\n");
    setInput("");
  };

  return (
    <>
      <div className="serial" ref={scrollRef}>
        {serial || (running ? "" : "Run the simulation to see serial output…")}
      </div>
      <div className="serial-input">
        <input
          placeholder={componentId ? "Send to serial…" : "No microcontroller in circuit"}
          value={input}
          disabled={!componentId || !running}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
        />
        <button onClick={send} disabled={!componentId || !running}>
          Send
        </button>
      </div>
    </>
  );
}
