# Third-Party Notices

This project is a local-first control page and local Agent. It relies on third-party open-source tools, but it does not imply endorsement, authorization, or partnership by those projects or by any supported content platform.

Redistributors should keep this notice, keep upstream copyright/license notices where required, and review the final package with qualified counsel if distributing commercially.

## Python Packages

| Package | Purpose | Upstream | License / notice |
| --- | --- | --- | --- |
| yt-dlp | Public-site metadata extraction and downloading | https://github.com/yt-dlp/yt-dlp | Unlicense; see the upstream [LICENSE](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE) |
| Playwright Python | Local background browser automation for public pages | https://github.com/microsoft/playwright-python | Apache-2.0 |
| FastAPI | Local Agent HTTP API framework | https://github.com/fastapi/fastapi | MIT |
| Uvicorn | ASGI server for the local Agent | https://github.com/encode/uvicorn | BSD-3-Clause |
| Pydantic | Request/response data validation | https://github.com/pydantic/pydantic | MIT |
| certifi | CA certificate bundle | https://github.com/certifi/python-certifi | MPL-2.0 |
| python-qrcode | QR code generation for LAN phone pairing | https://github.com/lincolnloop/python-qrcode | BSD-3-Clause. "QR Code" is a registered trademark of DENSO WAVE INCORPORATED. |

## External Tools

| Tool | Purpose | Upstream | License / notice |
| --- | --- | --- | --- |
| FFmpeg / ffprobe | Optional local audio/video merging | https://ffmpeg.org/ | FFmpeg builds may be LGPL or GPL depending on build options and included libraries. This project does not modify FFmpeg and only invokes the user's system installation or upstream-distributed packages. |
| Chromium browser binaries installed by Playwright | Local background browser component | https://playwright.dev/ | Needs verification for each redistributed bundle. Review Playwright and Chromium browser binary notices before redistributing offline bundles. |

## Platform Names

Names such as Douyin, Xiaohongshu, TikTok, YouTube, Bilibili, X / Twitter, and Instagram are mentioned only to describe possible public-link compatibility targets. They are trademarks of their respective owners and do not imply partnership, endorsement, authorization, or platform approval.
