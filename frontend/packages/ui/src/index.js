/**
 * MateAssist shared UI - public surface.
 *
 * Both apps import primitives from here and nowhere else. If a component is
 * needed in both, it belongs in this package; if it is used by one, it stays in
 * that app. That rule is what keeps the two bundles from drifting (D-104).
 */

export { Wordmark } from "./components/Wordmark.jsx";
export { Pill, TONE, TONE_DOT } from "./components/Pill.jsx";
export { Metric } from "./components/Metric.jsx";
export { Switch } from "./components/Switch.jsx";
export { QuickAction } from "./components/QuickAction.jsx";
export { Toast, TOAST_TIMEOUT_MS } from "./components/Toast.jsx";
