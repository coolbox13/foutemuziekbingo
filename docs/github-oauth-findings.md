## GitHub guidance on OAuth for web apps: findings

- **Primary flow for web apps**: Use the OAuth 2.0 authorization code flow with a server-side code exchange. GitHub documents this as the “web application flow.” The client secret must not be exposed to the browser. You exchange the code on the server, then establish the user’s session for the web app.
  - Reference: [Authorizing OAuth Apps (web application flow)](https://docs.github.com/en/developers/apps/building-oauth-apps/authorizing-oauth-apps)

- **State parameter (CSRF protection)**: Always send a unique, unguessable `state` value with the authorization request and verify it on callback. This is the canonical CSRF protection for OAuth.
  - Reference: [Authorizing OAuth Apps — use of `state` to protect against CSRF](https://docs.github.com/en/developers/apps/building-oauth-apps/authorizing-oauth-apps#parameters)

- **Redirect URI rules**: Register exact callback URLs and ensure the redirect used during auth matches what’s configured. Do not accept arbitrary redirect targets; validate and enforce allowlists.
  - Reference: [Redirect users to request GitHub access](https://docs.github.com/en/developers/apps/building-oauth-apps/authorizing-oauth-apps#redirecting-users-to-request-github-access)

- **Device flow is not for web apps**: GitHub supports the device authorization flow for CLI/TV devices and other input‑constrained clients. Do not use it for a browser‑based web app where the standard authorization code flow is appropriate.
  - Reference: [Authorizing OAuth Apps — device flow](https://docs.github.com/en/developers/apps/building-oauth-apps/authorizing-oauth-apps#device-flow)

- **SPA considerations**: GitHub’s OAuth Apps require a client secret for the code exchange; do not perform the code exchange in a public client. For browser‑only SPAs, use a backend to perform the exchange and to issue a session to the browser. Avoid legacy implicit flows.
  - Reference: [OAuth Apps overview and security model](https://docs.github.com/en/developers/apps/building-oauth-apps)

- **Session vs tokens for web dashboards**: For traditional server‑rendered web apps and dashboards, prefer a session cookie established after the server‑side exchange, rather than pushing raw bearer tokens into the browser. Use the server session to authenticate subsequent requests.
  - Rationale aligned with GitHub’s web application flow documentation and common OAuth 2.1 guidance (implicit grant deprecated; server‑side code exchange recommended).

- **Cookie security**: When using sessions, set cookies with `HttpOnly`, `Secure`, appropriate `SameSite` (typically `Lax` for top‑level navigations), explicit `Path`, and tight `Domain` scoping. Ensure HTTPS everywhere so `Secure` is effective. Verify `Set-Cookie` headers appear on the callback response that completes login.
  - Reference: GitHub general security guidance; aligns with modern browser cookie hardening and OAuth best practices surfaced in GitHub engineering/security materials.

- **Do not mix multiple auth systems**: Avoid combining parallel mechanisms (e.g., session cookies, ad‑hoc JWTs, and legacy IP‑based sessions). Pick one primary mechanism consistent with the app type (session for web apps) to prevent inconsistent auth state and hard‑to‑debug failures.
  - Reference: General best practice reflected across GitHub’s guidance to use the appropriate OAuth flow for the client type and to keep secrets server‑side.

- **Error handling and scopes**: Request the minimum necessary scopes for the app’s features; handle errors explicitly (denials, mismatched state, invalid_code). Log and surface actionable error information during auth.
  - Reference: [About scopes for OAuth Apps](https://docs.github.com/en/developers/apps/building-oauth-apps/scopes-for-oauth-apps)

- **Testing the end‑to‑end flow**: Include tests that validate the full browser flow: redirect to GitHub, successful code exchange on the server, `Set-Cookie` on the final response, and access to protected routes using that cookie. Ensure callback responses do not swap out the response object after cookies are set (which can drop headers).
  - Reference: Practice consistent with GitHub’s documented flow and common OAuth security testing guidance.

### Practical architecture pattern for a GitHub‑style web app

- **Callback handler**: Perform code exchange on the server; create user/session; set secure cookie; redirect to dashboard.
- **Protected routes**: Read session cookie on each request; no bearer tokens stored in the browser.
- **Remove legacy pathways**: Eliminate implicit grants, ad‑hoc JWTs to the browser, and legacy IP‑based sessions.
- **Observability**: Log authorization request IDs, state values, and code‑exchange outcomes to trace failures safely.

These findings reflect GitHub’s OAuth App documentation for web application flow, the use of `state`, device flow boundaries, and widely adopted best practices consistent with OAuth 2.1 guidance for web applications.


