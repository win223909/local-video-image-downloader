# Video / Image Link Downloader

English | [中文](README.md) | [License](LICENSE) | [Third-party notices](THIRD_PARTY_NOTICES.md)

A local-first downloader for public video links, image links, and gallery pages. The current product shape is a **local Agent + self-hosted web page**: the web page is only the control and installation entry, while parsing, previewing, downloading, merging, and saving files run on the user's own computer or NAS.

## Compliance Notice

- Use this tool only for public content that you have the right to save.
- This tool does not crack VIP, member-only, paid, DRM-protected, or otherwise restricted content.
- This tool does not remove, cover, or alter watermarks, attribution, copyright notices, source marks, or other rights-management information. It only saves original or high-resolution resources when the platform publicly returns them, and it does not promise "watermark removal".
- This tool does not include piracy APIs or paid-content bypass services.
- In Agent mode, the web page talks to the local assistant on `127.0.0.1` or a LAN address. The hosted page does not store task URLs, parsing results, download history, or downloaded media files.
- Platform support depends on the real runtime result. Websites change frequently, so platform adapters or dependencies may need updates.
- Platform names are used only to describe public-link compatibility targets. They do not imply official partnership, endorsement, or authorization.

## Features

- Paste video, image, gallery URLs, or full platform share text. Share text from platforms such as Douyin or Xiaohongshu is automatically cleaned to extract the `http(s)` link.
- Show video title, author/channel, cover, duration, and source platform.
- Show image/gallery title, author/channel, image count, and thumbnail previews.
- Show downloadable video formats: resolution, extension, file size, codecs, and whether FFmpeg merging is needed.
- Download selected video formats to a local folder. Images are saved into a title-based folder, and the save directory can be changed with a system folder picker.
- Show download progress, speed, and ETA.
- Open the saved folder after download.
- Try to handle short links and normal public-page verification automatically. The resolver uses `yt-dlp` first, then a local background browser when needed.
- Prefer public original or high-resolution resources when available. If a platform only returns a watermarked or source-marked version, the tool does not erase, cover, alter, or bypass it.
- Pairing-code protection for the local Agent. The first connection requires the 6-digit code shown by the local Agent; the browser then stores a local token.
- Online updates. When a newer version is detected, users can update from the web page or run the `03-UPDATE` script in the installer folder.

## Install Python

Python 3.11 or newer is recommended.

macOS with Homebrew:

```bash
brew install python
```

Windows:

```text
https://www.python.org/downloads/
```

Check the installed version:

```bash
python3 --version
```

On Windows, use this if `python3` is not available:

```powershell
python --version
```

## Install FFmpeg

FFmpeg is used to merge separate video and audio streams. Many high-quality video formats need it, so installation is recommended.

macOS:

```bash
brew install ffmpeg
```

Windows with winget:

```powershell
winget install Gyan.FFmpeg
```

Or download it from:

```text
https://ffmpeg.org/download.html
```

Verify the installation:

```bash
ffmpeg -version
ffprobe -version
```

## Install Dependencies for Development

For development or manually running the Agent:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

## Run Mode: Local Agent + Self-Hosted Web Page

This mode is suitable for GitHub Pages, Cloudflare Pages, a VPS, a NAS with nginx/Caddy, or any static hosting service. Actual parsing and downloading still happen on the user's own computer or NAS.

The project does not depend on a fixed domain or fixed server by default:

- The static page downloads installers from same-site `./downloads/` by default.
- If the deployer provides an optional `/api/download-link` anti-abuse endpoint, the page uses it first; if unavailable, it falls back to direct installer links.
- The update manifest is `web/downloads/update.json` by default. When building installers, `PUBLIC_BASE_URL` can be used to write your own online update URL.
- The local Agent trusts local development origins by default. If `PUBLIC_BASE_URL` is set while building installers, that origin is written into the Agent's allowed origins.

### Installation for End Users

The installation page shows the correct installer for the user's operating system:

- macOS: download `VideoDownloaderAgent-macOS.zip`, unzip it, then double-click `01-INSTALL.command`. If macOS says the script was blocked or Apple cannot verify it, do not click "Move to Trash". Open "System Settings -> Privacy & Security", click "Open Anyway", then confirm. Use `03-UPDATE.command` to update and `02-UNINSTALL.command` to reset or uninstall.
- Windows: download `VideoDownloaderAgent-Windows.zip`, right-click it and choose "Extract All", open the extracted folder, then double-click `01-INSTALL.bat`. Use `03-UPDATE.bat` to update and `02-UNINSTALL.bat` to reset or uninstall. If you are using Parallels, `C:\Mac\Home\Desktop` is the Mac shared desktop; if there is trouble, copy the extracted folder to `C:\Users\your-Windows-name\Desktop` and run it there. The installer keeps the window open on failure so users can take a screenshot of the error.
- iOS / Android: mobile browsers cannot run the local Agent continuously. The current MVP supports mobile by letting the phone control a computer or NAS that already has the Agent running.

Build installers:

```bash
python3 scripts/build_installers.py
```

For publishing to your own domain, build with:

```bash
PUBLIC_BASE_URL="https://your-domain.example" python3 scripts/build_installers.py
```

This lets the generated installers remember your site for future updates and browser-to-Agent CORS access. For local testing or private distribution, `PUBLIC_BASE_URL` can be omitted.

Generated files are placed in `web/downloads/`:

- `agent-source.zip`: local Agent source package, embedded into both macOS and Windows installers under `_internal/`.
- `update.json`: online update manifest with the latest version, source package URL, and SHA256.
- `VideoDownloaderAgent-macOS.zip`: macOS installer bundle with `01-INSTALL.command`, `03-UPDATE.command`, and `02-UNINSTALL.command`.
- `VideoDownloaderAgent-Windows.zip`: Windows installer bundle with `01-INSTALL.bat`, `03-UPDATE.bat`, and `02-UNINSTALL.bat`.

Updating the local Agent:

- Recommended: open the local console and click "Update local assistant" when a newer version is detected.
- Fallback: run `03-UPDATE` from the extracted installer folder.
- Updates download the latest `agent-source.zip`, verify SHA256, replace the local Agent code, and run `pip install --upgrade -r requirements-agent.txt`.
- Updates keep `.runtime/`, including pairing tokens, save-folder settings, browser sessions, and temporary state.
- Updates do not delete downloaded videos or images.
- Users usually only need to download a new installer when Python, FFmpeg, or the system environment changes significantly.

Uninstalling the local Agent:

- macOS: run `02-UNINSTALL.command`.
- Windows: run `02-UNINSTALL.bat`.
- The uninstall script stops the Agent, removes startup entries, removes the Agent program directory, tokens, settings, and temporary cache.
- It does not delete videos or images that the user has already downloaded.

The installer creates a local Python virtual environment, installs Agent dependencies, registers startup, and passes a local token back to the local console using a URL fragment. URL fragments are not sent to the hosted server.

Notes for restricted or unstable network environments:

- macOS and Windows installers embed `_internal/agent-source.zip`, so the core code usually does not need to be downloaded again during installation.
- `pip` tries official PyPI first: `https://pypi.org/simple`; if it fails, the installer tries configured mirrors. You can override the order with `PIP_INDEX_URLS`, or set the first source with `PIP_INDEX_URL`.
- Playwright Chromium tries the official download source first, then configured mirrors such as npmmirror. You can override with `PLAYWRIGHT_DOWNLOAD_HOSTS` or `PLAYWRIGHT_DOWNLOAD_HOST`.
- The macOS and Windows installers check Python, pip, the background browser component, and FFmpeg. Missing items are installed one by one when possible.
- The current macOS installer is not notarized with an Apple Developer certificate. Do not disable Gatekeeper globally; allow the script only once through "System Settings -> Privacy & Security -> Open Anyway". A fully signed and notarized installer would remove this warning in a future release.

After installation, the control page opens at:

```text
http://127.0.0.1:17890/
```

Because the page and Agent API are same-origin in this mode, it avoids browser restrictions around public HTTPS pages calling local loopback services.

### 1. Start the Local Agent Manually

```bash
source .venv/bin/activate
python -m local_agent.server
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m local_agent.server
```

The terminal prints a local URL and a 6-digit pairing code:

```text
Local downloader agent is running
URL: http://127.0.0.1:17890
Pairing code: 123456
```

The pairing code is valid for 10 minutes. It only needs to be entered once for a browser session.

### 2. Preview the Web Page Locally

For development or local testing:

```bash
python3 -m http.server 8080 -d web
```

Open:

```text
http://127.0.0.1:8080
```

The page detects the local Agent at `http://127.0.0.1:17890`. Pasting links, parsing, and downloading all call the local Agent. The installer version prefers the same-origin local console at `http://127.0.0.1:17890/`.

### Phone Controls Computer/NAS Downloads

The mobile MVP lets the phone control a computer or NAS. The phone does not run the parser. Parsing, downloading, merging, and saving happen on the computer or NAS where the local Agent is running.

Steps:

1. Start the local Agent on a computer or NAS.
2. Open `http://127.0.0.1:17890/` on that device.
3. Expand "Phone / NAS control" and click "Generate phone access".
4. Connect the phone to the same network, then open the recommended LAN URL, for example `http://192.168.1.x:17890/`. The page tries to filter out VPN and virtual-network addresses that phones usually cannot reach.
5. Enter the 6-digit pairing code shown on the computer/NAS page.
6. Paste links, preview content, and start downloads from the phone.
7. After a download finishes, the phone page can show a file list and a "Save to phone" action. Desktop users can click "Open containing folder".

Notes:

- The VPS or hosted page does not proxy video or image files in this mode.
- The phone must be able to reach the computer/NAS LAN address. If it cannot, confirm both devices are on the same Wi-Fi and that the computer firewall allows the local Agent.
- For external access to a home NAS, a later setup can put the NAS Agent behind Cloudflare Tunnel + Access.

### 3. Self-Hosting

Host the `web/` directory as static files. Once users have installed and started the local Agent, video and image files do not pass through your server.

Common deployment options:

- GitHub Pages: publish the repository and serve `web/`.
- Cloudflare Pages: connect the repository, leave the build command empty, and set the output directory to `web`.
- VPS / NAS: serve `web/` with nginx, Caddy, or any static file server.

Self-hosting workflow:

1. Build installers with your public site URL:

   ```bash
   PUBLIC_BASE_URL="https://your-domain.example" python3 scripts/build_installers.py
   ```

2. Publish the whole `web/` directory.
3. Confirm these files are reachable:

   ```text
   https://your-domain.example/
   https://your-domain.example/downloads/update.json
   https://your-domain.example/downloads/VideoDownloaderAgent-macOS.zip
   https://your-domain.example/downloads/VideoDownloaderAgent-Windows.zip
   https://your-domain.example/downloads/agent-source.zip
   ```

4. Users download the installer from your site. Parsing, downloading, previewing, merging, and saving still happen locally on the user's device.

Optional installer download protection:

Static hosting works by itself. If you are concerned about installer download abuse, you can additionally deploy `server_guard/download_gate.py`. The page asks `/api/download-link` for a short-lived installer link. This is optional and does not affect normal static deployment.

Environment variables:

```bash
export VIDEO_DOWNLOADER_DOWNLOAD_SECRET="a-long-random-secret"
export VIDEO_DOWNLOADER_DOWNLOAD_ROOT="/path/to/your-site/downloads"
python3 server_guard/download_gate.py
```

These limits only protect installer-download traffic. User video and image downloads still happen on their own computer or NAS.

When running the Agent manually, you can allow your hosted page origin with:

```bash
export LOCAL_AGENT_ALLOWED_ORIGINS="https://your-domain.example"
python -m local_agent.server
```

Multiple origins are comma-separated:

```bash
export LOCAL_AGENT_ALLOWED_ORIGINS="https://your-domain.example,http://127.0.0.1:8080"
```

To manually set an update manifest:

```bash
export LOCAL_AGENT_UPDATE_MANIFEST_URL="https://your-domain.example/downloads/update.json"
python -m local_agent.server
```

The Agent listens on `0.0.0.0:17890` by default so phones on the same LAN can control a computer or NAS. Sensitive APIs require a local token or pairing code.

## Update yt-dlp

In a development environment, if a platform suddenly fails, update `yt-dlp` first:

```bash
pip install -U yt-dlp
```

End users should prefer the web page's "Update local assistant" button or the installer's `03-UPDATE` script.

## Third-Party Projects and Licenses

This project relies on mature open-source tools for parsing, browser automation, and local serving. It does not bundle piracy APIs or paid-content bypass services, and the listed projects or platforms do not endorse, authorize, or partner with this project. If you redistribute installers, keep this section or an equivalent third-party notice.

| Component | Purpose | License / note |
| --- | --- | --- |
| `yt-dlp` | Public-site parsing and download core | Unlicense / public-domain style |
| Playwright Python | Local background browser for public-page redirects and preview fallback | Apache-2.0 |
| FastAPI | Local Agent HTTP API | MIT |
| Uvicorn | Local Agent ASGI server | BSD-3-Clause |
| Pydantic | API data validation | MIT |
| certifi | CA certificate bundle | MPL-2.0 |
| python-qrcode | Phone-access QR code generation | BSD-3-Clause; "QR Code" is a registered trademark of DENSO WAVE INCORPORATED |
| FFmpeg / ffprobe | Local audio/video merging, installed by the user or downloaded by the installer | FFmpeg builds may be LGPL or GPL depending on build options; this project does not modify FFmpeg and only invokes system or upstream packages |

If you distribute or commercialize this project publicly, add your own contact information, applicable jurisdiction, takedown/complaint process, and have the final wording reviewed by qualified counsel.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the full notice list. This project itself is released under the [MIT License](LICENSE).

## FAQ

### FFmpeg is missing

Choose a single-file format that does not need merging, or install FFmpeg. Installing FFmpeg is recommended because high-quality videos often require merging separate video and audio streams.

### The platform requires verification

The tool automatically tries normal public-page verification in the background. It does not bypass CAPTCHA, forced login, age verification, paid walls, or DRM.

### A platform cannot be parsed

`yt-dlp` support changes as websites change. Update the local Agent or `yt-dlp` first. If it still fails, the link may require login, be region-restricted, be unavailable, or not yet be supported.

### Why does Agent mode need a local assistant?

A browser page cannot directly run `yt-dlp`, FFmpeg, or a background browser, and it cannot freely write to local folders. The local Agent performs the real local work; the web page is only the control panel.

### Will this use VPS traffic?

Normally, no large media files go through the VPS. The VPS or static host only serves the web page, installers, and update manifest. Parsing, preview proxying, downloading, and merging run inside the user's local Agent.

### What is the original-resource boundary?

The tool prefers original video streams, original images, high-resolution images, or confirmed resources that the platform publicly returns. If a platform only returns watermarked or source-marked versions, the tool does not erase, cover, or alter those marks and does not crack restricted APIs.

### Douyin share text fails to parse

You can paste the entire Douyin share text. The tool extracts links such as `https://v.douyin.com/...` automatically. If the short link redirects to the Douyin home page instead of a specific video, the link may be expired, incomplete, or affected by platform risk controls. Copy the share text again or paste the full video detail URL.

The background browser fallback may help, but it does not bypass CAPTCHA, forced login, paid content, or DRM.
