import preset from "../packages/ui/tailwind-preset.js";

/** Identical preset to the portal - one design system, two bundles (D-104). */
export default {
  presets: [preset],
  content: [
    "./index.html",
    "./src/**/*.{js,jsx}",
    "../packages/ui/src/**/*.{js,jsx}"
  ]
};
