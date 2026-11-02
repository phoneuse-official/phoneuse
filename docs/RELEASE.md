# Release and launch checklist

The repository is `phoneuse-official/phoneuse` and is public. Every release goes through a reviewed pull
request with green `Checks`.

## Repository settings

- Description: Open-source local iPhone automation. Control your USB-connected iPhone with prompts, live video, REST and MCP. Built by PhoneUse.
- Homepage: https://phoneuse.com/?utm_source=github&utm_medium=repo_homepage&utm_campaign=phoneuse-local
- Topics: iphone, ios, automation, webdriveragent, mcp, ai-agents, macos, phoneuse.
- Private vulnerability reporting enabled (Settings → Code security).
- Branch protection on `main`: require a pull request and the `Checks` jobs (`public-tree`, `backend`, `web`).
- Dependabot alerts and security updates enabled.

## Before each release

- Run the checks in [CONTRIBUTING.md](../CONTRIBUTING.md) and `python3 scripts/check-public-tree.py` on the exact commit.
- Review dependency licenses and audit results; record any new override in `THIRD_PARTY.md`.
- Update `CHANGELOG.md`.
- On a real Mac and iPhone, confirm install, live video, one manual action and one reversible prompt.
  Record versions in `docs/VALIDATION.md`. Local tests do not prove a fresh Mac works.
- Commit with a GitHub `noreply` address, not a personal email.

## Demo media

Review every frame before publishing: use a test phone with no personal data, and hide notifications,
contacts, device names and identifiers. Host recordings as GitHub attachments rather than committing them;
the public-tree scan rejects video, JPEG and binary files.

Publish only Git source from this repository. Never upload local state, signed apps or Apple support images.
