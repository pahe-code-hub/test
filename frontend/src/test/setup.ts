import "@testing-library/jest-dom/vitest";

// jsdom implementiert EventSource nicht - ein minimaler Stub genügt, damit
// Komponenten, die useProjectEvents (SSE) einbinden, in Tests nicht an
// einer fehlenden globalen Klasse scheitern. Echte Event-Zustellung wird
// gezielt in useProjectEvents.test.ts über eine Test-Variante dieser
// Klasse geprüft, nicht hier.
class StubEventSource {
  static instances: StubEventSource[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  constructor(public url: string) { StubEventSource.instances.push(this); }
  addEventListener(type: string, cb: (e: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(cb);
  }
  close() {}
}
// @ts-expect-error - Test-Stub, kein vollständiges EventSource-Interface
globalThis.EventSource = StubEventSource;
