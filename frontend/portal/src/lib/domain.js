/**
 * The base domain this deployment is served under.
 *
 * Derived from the browser's own location rather than baked in at build time.
 * The literal string ".mateassist.io" was hardcoded in two places and the
 * product now runs on mateassist.site, so the login form told every user to
 * enter a workspace on a domain that does not exist. A value read from where
 * the page is actually being served cannot drift like that.
 *
 * A tenant reaches the portal at `<slug>.example.com`, so the base domain is
 * the hostname minus its first label. Anything with two labels or fewer -
 * `example.com`, `localhost` - is already the base.
 */
export function baseDomain() {
  const host = window.location.hostname;
  const labels = host.split(".");
  return labels.length > 2 ? labels.slice(1).join(".") : host;
}

/** `netamate.mateassist.site` - what a workspace's own URL looks like. */
export function workspaceHost(slug) {
  return slug ? `${slug}.${baseDomain()}` : "";
}
