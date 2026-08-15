/**
 * MateAssist design system - Tailwind preset.
 *
 * D-101/D-102/D-104: the palette and typography live here ONCE and are inherited
 * by both apps. Neither app re-declares a colour or a font family, so the two
 * surfaces cannot drift apart. Values are preserved byte-for-byte from the
 * reference prototypes - do not "tidy" them.
 */

/** @type {Partial<import('tailwindcss').Config>} */
export default {
  theme: {
    extend: {
      colors: {
        ink: "#0B1220",
        ink2: "#101C2E",
        ink3: "#0F1B2D",
        hairline: "#E2E8F0"
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
        wordmark: ['"HemiHead"', '"IBM Plex Sans"', "sans-serif"]
      },
      keyframes: {
        toastIn: {
          "0%": { opacity: "0", transform: "translateX(16px)" },
          "100%": { opacity: "1", transform: "translateX(0)" }
        },
        // A sheen crossing a short track, used while the assistant is working.
        // Defined here rather than as an arbitrary value in the component so
        // both surfaces animate identically (D-104).
        shimmer: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(300%)" }
        }
      },
      animation: {
        toastIn: "toastIn 200ms ease-out",
        shimmer: "shimmer 1.4s ease-in-out infinite"
      }
    }
  },
  plugins: []
};
