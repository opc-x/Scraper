# Agent instructions

## iOS PWA viewport

- Keep `frontend/index.html` without `viewport-fit=cover` and keep `apple-mobile-web-app-status-bar-style` set to `default`.
- Do not “fix” the bottom tab bar by adding inferred safe-area padding or screen-height arithmetic. On the tested iPhone in standalone mode, `cover` + `black-translucent` shortens the WebView while `env(safe-area-inset-*)` remains `0`, leaving the fixed bottom navigation visibly suspended above the physical screen bottom.
- Let iOS inset the viewport; `bottom: 0` is the correct anchor. Keep `env(safe-area-inset-bottom, 0px)` only for platforms that report it correctly.
- For deeper background and a known-good reference, read `/Users/cuijian/opc-x/Ogden850App/CLAUDE.md` under “PWA viewport & safe area”. Validate final behavior on a real iPhone installed as a PWA, not only desktop device emulation.
