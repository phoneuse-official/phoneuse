# Third-party components

This repository's license covers its original source, not external dependencies, trademarks or Apple tools.
Dependency versions are recorded in `platform/requirements.lock.txt` and `platform/web/package-lock.json`.
Review installed packages' license files when redistributing dependencies or binaries.

Major upstream projects: [Appium WebDriverAgent](https://github.com/appium/WebDriverAgent),
[pymobiledevice3](https://github.com/doronz88/pymobiledevice3), [FastAPI](https://github.com/fastapi/fastapi),
[React](https://github.com/facebook/react), [Next.js](https://github.com/vercel/next.js),
[Vinext](https://github.com/cloudflare/vinext), and [Codex](https://github.com/openai/codex).
WebDriverAgent, Codex and Xcode are obtained separately. No Apple developer images, pre-signed IPA,
third-party phone installer, vendor SDK binary, personal media, or runtime capture is included.

The web lockfile pins a patched `fflate` 0.7.5 for Satori through an npm override.
It also pins `minimatch` 11.0.4 for the shadcn CLI's `@ts-morph/common` (GHSA-g3hv-75wg-m249); the CLI is
only used when adding UI components. Remove each override when upstream dependencies adopt a patched release
and audit remains clean.
