import "@testing-library/jest-dom";

import { toHaveNoViolations } from "jest-axe";
import { expect } from "vitest";

expect.extend(toHaveNoViolations);

// --- jsdom polyfills required by Radix overlays ---
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

if (!("ResizeObserver" in globalThis)) {
  globalThis.ResizeObserver =
    ResizeObserverStub as unknown as typeof ResizeObserver;
}

if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = (): boolean => false;
  Element.prototype.setPointerCapture = (): void => {};
  Element.prototype.releasePointerCapture = (): void => {};
}

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = (): void => {};
}
