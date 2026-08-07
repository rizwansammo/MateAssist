/**
 * Design-system guard for D-100: geometric precision, no exceptions.
 *
 * The global `* { border-radius: 0 !important }` rule in packages/ui already
 * makes rounded corners impossible to render. This lint exists for the other
 * half of the decision: keeping the SOURCE honest. A stray `rounded-lg` that
 * renders square today is a lie in the code, and it would come back the moment
 * anyone weakened the global rule.
 *
 * Fails on any rounded-* utility other than rounded-none, and on any non-zero
 * border-radius declaration.
 *
 *     node scripts/check-radius.mjs
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));

const SCAN_DIRS = ["portal/src", "admin/src", "packages/ui/src"];
const EXTENSIONS = [".js", ".jsx", ".ts", ".tsx", ".css", ".html"];

// rounded-none is the allowed spelling. Catches directional forms too
// (rounded-t-lg, rounded-tl-[4px]) and the bare `rounded` utility.
const ROUNDED_UTILITY =
  /\brounded(?:-(?:t|r|b|l|tl|tr|br|bl|s|e|ss|se|es|ee))?-(?!none\b)[a-z0-9[\]().%-]+/g;
const BARE_ROUNDED = /\brounded(?![-\w])/g;
// Capture the value, then judge it in code. A negative lookahead here is not
// safe: `\s*` backtracks to zero-width, sliding the lookahead past the space
// and letting `border-radius: 0` through as a violation.
const CSS_RADIUS = /border-radius\s*:\s*([^;}]+)/gi;

const ZERO_VALUE = /^0(px|rem|em|%)?$/i;

/**
 * Strip comments before scanning.
 *
 * Without this, prose explaining the rule trips the rule - the word "rounded"
 * in a sentence like "a rounded pill toggle would leak the design system" is
 * not a violation. A linter that flags its own documentation gets switched off.
 */
function stripComments(source) {
  return (
    source
      // Block comments, including CSS and JSDoc.
      .replace(/\/\*[\s\S]*?\*\//g, " ")
      // Line comments, but not the `//` inside a URL such as https://example.com.
      .replace(/(^|[^:"'`\\])\/\/[^\n]*/g, "$1")
  );
}

function walk(dir) {
  const out = [];
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return out; // directory not created yet
  }
  for (const entry of entries) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "node_modules" || entry === "dist") continue;
      out.push(...walk(full));
    } else if (EXTENSIONS.some((ext) => entry.endsWith(ext))) {
      out.push(full);
    }
  }
  return out;
}

const violations = [];

for (const dir of SCAN_DIRS) {
  for (const file of walk(join(ROOT, dir))) {
    const relPath = relative(ROOT, file).replace(/\\/g, "/");
    const lines = stripComments(readFileSync(file, "utf8")).split(/\r?\n/);

    lines.forEach((line, index) => {
      const record = (text) => violations.push({ file: relPath, line: index + 1, text: text.trim() });

      for (const pattern of [ROUNDED_UTILITY, BARE_ROUNDED]) {
        pattern.lastIndex = 0;
        let match;
        while ((match = pattern.exec(line)) !== null) record(match[0]);
      }

      CSS_RADIUS.lastIndex = 0;
      let cssMatch;
      while ((cssMatch = CSS_RADIUS.exec(line)) !== null) {
        // Normalise away `!important` and surrounding space before judging.
        const value = cssMatch[1].replace(/!important/i, "").trim();
        if (!ZERO_VALUE.test(value)) record(cssMatch[0]);
      }
    });
  }
}

if (violations.length > 0) {
  console.error(`\n  D-100 violation: ${violations.length} rounded corner(s) in source.\n`);
  for (const v of violations) {
    console.error(`    ${v.file}:${v.line}  ${v.text}`);
  }
  console.error("\n  MateAssist has zero border-radius everywhere. Use `rounded-none`.\n");
  process.exit(1);
}

console.log("  D-100 clean: no rounded corners in source.");
