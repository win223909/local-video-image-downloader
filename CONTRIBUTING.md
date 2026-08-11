# Contributing

Thanks for helping improve the project. Please keep contributions focused, reviewable, and compatible with the local-first design.

## Before opening an issue

- Use a recent supported version.
- Search existing Issues first.
- Include the operating system, Agent version, browser, relevant dependency versions, reproduction steps, expected behavior, and actual behavior.
- Sanitize logs. Do not include cookies, tokens, pairing codes, passwords, private URLs, complete personal file paths, or private media.

Use a Bug Report for broken behavior and a Feature Request for a new capability. Security issues must follow [SECURITY.md](SECURITY.md), not a public Issue.

## Development workflow

1. Fork the repository and create a focused branch.
2. Set up Python 3.11 or newer and install `requirements-agent.txt`.
3. Make the smallest change that addresses one goal.
4. Add or update tests for behavior that can be tested without real platform downloads.
5. Run the checks described below.
6. Open a pull request with a clear summary and the requested checklist.

## Checks

```bash
python -m compileall local_agent video_downloader
pytest -q
git diff --check
```

Do not run large third-party download tests in CI or include downloaded media in the repository.

## Coding guidelines

- Prefer existing project patterns and small, explicit changes.
- Keep network, filesystem, and subprocess behavior bounded and cancellable.
- Do not log cookies, tokens, private URLs, or local personal data.
- Preserve the local Agent and trusted-LAN product boundary.
- Keep user-facing compliance wording accurate.

The project does not accept contributions for DRM, paywall, CAPTCHA, forced-login, platform access-control, watermark, attribution, or copyright-information removal.

