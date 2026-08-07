import preset from "../packages/ui/tailwind-preset.js";

/**
 * The app declares only its content globs. Every colour, font and keyframe comes
 * from the shared preset (D-104) - redeclaring one here would be the first step
 * toward the two surfaces drifting apart.
 *
 * The packages/ui glob is essential: without it Tailwind purges the classes used
 * by shared primitives and they render unstyled.
 */
export default {
  presets: [preset],
  content: [
    "./index.html",
    "./src/**/*.{js,jsx}",
    "../packages/ui/src/**/*.{js,jsx}"
  ]
};
