const AGENT_BASE = resolveAgentBase();
const INSTALLER_LINK_ENDPOINT = resolveInstallerLinkEndpoint();
const INSTALLER_FILES = {
  macos: "./downloads/VideoDownloaderAgent-macOS.zip",
  windows: "./downloads/VideoDownloaderAgent-Windows.zip",
};
const TOKEN_KEY = "videoDownloaderAgentToken";
const UPDATE_DISMISS_KEY = "videoDownloaderDismissedUpdate";
const LANGUAGE_KEY = "videoDownloaderLanguage";
const LEGAL_ACCEPT_KEY = "videoDownloaderLegalAccepted:v2";

const STATIC_TRANSLATIONS = [
  ["使用前请阅读", "Read before use"],
  ["使用前请确认你有权保存内容", "Confirm that you have the right to save the content"],
  ["本工具仅用于保存你本人创作、已获得授权，或法律允许用于个人学习、研究、欣赏等合理目的的公开内容。公开可访问不代表可以自由复制、转载、商用或二次发布。使用前请确认你已遵守内容来源平台规则，以及著作权、肖像权、隐私权和个人信息保护等相关要求。", "Use this tool only for public content you created, content you are authorized to save, or content that the law allows you to save for reasonable purposes such as personal study, research, or appreciation. Public access does not mean free copying, reposting, commercial use, or redistribution. Before use, make sure you comply with the source platform rules and applicable copyright, portrait rights, privacy, and personal information protection requirements."],
  ["本工具不提供 VIP、会员、付费内容获取，不绕过 DRM、加密、登录限制、验证码或其他平台访问控制，也不移除、遮盖或篡改署名、水印、版权声明、来源标识或其他权利管理信息。工具仅在平台公开返回原始资源、原图或高清资源时按用户选择保存，不承诺“去水印”，不得用于冒充原创、误导来源或侵害权利人权益。", "This tool does not provide access to VIP, member-only, or paid content, does not bypass DRM, encryption, login restrictions, CAPTCHA, or other platform access controls, and does not remove, cover, or alter attribution, watermarks, copyright notices, source marks, or other rights-management information. It only saves original or high-resolution resources when the platform publicly returns them, does not promise watermark removal, and must not be used to impersonate creators, mislead attribution, or infringe rights."],
  ["解析和下载在你的本地设备，或你主动连接的电脑/NAS 上完成；本站页面不保存、不上传你的链接、解析记录或下载文件。页面提到的平台名称仅用于说明可能兼容的公开链接类型，不代表官方合作、认可或授权。因下载、保存、分享、传播、商用或其他使用行为产生的责任和风险，由使用者自行承担。", "Parsing and downloading happen on your local device, or on the computer/NAS you actively connect to. This site does not save or upload your links, parsing records, or downloaded files. Platform names mentioned on the page only describe possible public-link compatibility and do not imply official partnership, endorsement, or authorization. You are responsible for the risks and liabilities arising from downloading, saving, sharing, distributing, commercial use, or any other use."],
  ["我已了解，并承诺仅下载自己有权保存的内容。", "I understand and promise to download only content I have the right to save."],
  ["我同意，进入网站", "I agree, enter the site"],
  ["视频/图片下载工具", "Video / Image Downloader"],
  ["粘贴公开内容链接，解析和下载都在你的电脑本地完成。", "Paste public content links. Parsing and downloads run locally on your computer."],
  ["粘贴公开内容链接，解析和下载都在你的设备本地完成。", "Paste public content links. Parsing and downloads run locally on your device."],
  ["打开本机控制台", "Open local console"],
  ["检测中", "Checking"],
  ["已连接", "Connected"],
  ["未连接", "Disconnected"],
  ["待连接", "Waiting"],
  ["待打开", "Open required"],
  ["待配对", "Pairing"],
  ["本地助手未连接。", "Local assistant is not connected."],
  ["请先安装或启动本地助手，然后刷新或点击重新检测。", "Install or start the local assistant, then refresh or click recheck."],
  ["重新检测", "Recheck"],
  ["本地助手已启动。", "Local assistant is running."],
  ["正在自动打开本机控制台。如果 Chrome 没有跳转，请点击上面的按钮继续使用。", "Opening the local console automatically. If Chrome does not switch, click the button above."],
  ["安装本地助手", "Install local assistant"],
  ["正在识别你的设备", "Detecting your device"],
  ["为什么需要本地助手？", "Why is a local assistant needed?"],
  ["为了保护你的隐私，网页只负责显示界面和发送本机指令。你粘贴的链接、解析过程、临时会话、下载文件和保存目录都在你的设备本地处理，不上传到本站服务器。", "To protect your privacy, this page only displays the interface and sends commands to your own device. Pasted links, parsing, temporary sessions, downloaded files, and save folders all stay local and are not uploaded to this server."],
  ["网络说明", "Network note"],
  ["安装器会优先使用官方海外源；如果失败，再自动尝试国内镜像。由于国内镜像和平台访问都可能不稳定，如果安装或解析经常失败，建议使用稳定的海外网络环境后再试。", "The installer tries official overseas sources first, then falls back to China mirrors. Some mirrors and platform access may be unstable, so a stable international network may help if installation or parsing often fails."],
  ["移动端说明", "Mobile note"],
  ["手机浏览器不能像电脑一样长期运行本地助手。当前移动端方案是：先在电脑或 NAS 上启动本地助手，再用手机打开电脑/NAS 提供的局域网控制页，把解析和下载任务交给电脑/NAS 处理。", "Mobile browsers cannot keep the local assistant running like a computer. For mobile use, start the assistant on a computer or NAS, then open its LAN control page on your phone and let that device handle parsing and downloads."],
  ["安装运行 01-INSTALL", "Install with 01-INSTALL"],
  ["适合 Mac 用户", "For Mac users"],
  ["适合 Windows 10/11 用户", "For Windows 10/11 users"],
  ["安装使用说明", "Installation guide"],
  ["点击上方与你电脑系统匹配的卡片，下载安装包。", "Click the card that matches your computer system to download the installer."],
  ["在“下载”文件夹里找到 zip 文件，先双击解压缩。", "Find the zip file in Downloads and unzip it first."],
  ["macOS 用户注意", "macOS users"],
  ["如果显示“已阻止 ‘01-INSTALL.command’ 以保护 Mac”或“Apple 无法验证”，不要点击“移到废纸篓”。请打开“系统设置 → 隐私与安全性”，在安全性提示里点击“仍要打开”，再确认打开。", "If macOS says “01-INSTALL.command was blocked to protect your Mac” or “Apple cannot verify”, do not click Move to Trash. Open System Settings → Privacy & Security, click Open Anyway in the security prompt, then confirm Open."],
  ["macOS：打开解压出的 `VideoDownloaderAgent-macOS` 文件夹，双击 `01-INSTALL.command` 安装。如果被系统阻止，请按上方红色提示，到“系统设置 → 隐私与安全性”里点击“仍要打开”。", "macOS: open the extracted `VideoDownloaderAgent-macOS` folder and double-click `01-INSTALL.command`. If macOS blocks it, follow the red note above: go to System Settings → Privacy & Security and click Open Anyway."],
  ["Windows：先右键 zip 选择“全部解压缩”，打开解压出的 `VideoDownloaderAgent-Windows` 文件夹，再双击 `01-INSTALL.bat` 安装；如果是在 Parallels 里使用，`C:\\Mac\\Home\\Desktop` 是 Mac 共享桌面，遇到问题时请把解压后的文件夹复制到 `C:\\Users\\你的Windows用户名\\Desktop` 再运行。安装窗口会保留错误信息，不会一闪而过。", "Windows: right-click the zip and choose Extract All first. Open the extracted `VideoDownloaderAgent-Windows` folder, then double-click `01-INSTALL.bat`. In Parallels, `C:\\Mac\\Home\\Desktop` is the Mac shared desktop; if there is trouble, copy the extracted folder to `C:\\Users\\your-Windows-name\\Desktop` and run it there. The installer window keeps error messages visible."],
  ["安装窗口会自动下载依赖并启动本地助手，完成后会自动打开 `http://127.0.0.1:17890/` 本机控制台。", "The installer downloads dependencies and starts the local assistant. When done, it opens the local console at `http://127.0.0.1:17890/`."],
  ["以后打开本页时，如果显示未连接，先点上方“打开本机控制台”；仍不行再点“重新检测”或重新运行安装脚本。", "Later, if this page says disconnected, click Open local console first. If it still fails, click Recheck or run the installer again."],
  ["macOS 和 Windows 安装器都会先检查 Python、pip、后台浏览器组件和 FFmpeg；缺失时会自动逐项安装。macOS 会优先使用系统自带 Python，避免不必要地跳转到 Python 官网。", "The macOS and Windows installers check Python, pip, the background browser component, and FFmpeg first. Missing items are installed one by one. macOS uses the system Python first to avoid unnecessary redirects to the Python website."],
  ["如果平台规则变化导致解析失败，优先在页面里点击“更新本地助手”；也可以打开同一个解压文件夹，运行 `03-UPDATE`。", "If platform rules change and parsing fails, click Update local assistant first. You can also run `03-UPDATE` in the extracted installer folder."],
  ["如果想重置或卸载本地助手，打开同一个解压文件夹，运行 `02-UNINSTALL` 脚本即可。它只会删除本地助手环境，不会删除你已经下载的视频或图片。", "To reset or uninstall, run `02-UNINSTALL` in the extracted installer folder. It removes the local assistant environment only, not your downloaded videos or images."],
  ["如何更新本地助手", "How to update"],
  ["正常情况下，打开本页后如果检测到新版，会自动出现“更新本地助手”按钮。", "Normally, if a newer version is detected, an Update local assistant button appears automatically."],
  ["更新只替换助手程序和解析依赖，会保留保存目录、配对状态和本地浏览器会话。", "Updates replace the assistant program and parsing dependencies while keeping your save folder, pairing state, and local browser session."],
  ["如果网页按钮无法使用，打开解压出的安装包文件夹，macOS 运行 `03-UPDATE.command`，Windows 运行 `03-UPDATE.bat`。", "If the web button does not work, open the extracted installer folder. Run `03-UPDATE.command` on macOS or `03-UPDATE.bat` on Windows."],
  ["只有遇到 Python、FFmpeg 或系统环境大变化时，才需要重新下载安装包。", "You usually only need to download the installer again when Python, FFmpeg, or the system environment changes significantly."],
  ["如何卸载本地助手", "How to uninstall"],
  ["找到之前解压出的安装包文件夹。", "Find the installer folder you extracted earlier."],
  ["macOS：双击 `02-UNINSTALL.command`；如果系统提示不安全，右键脚本选择“打开”。", "macOS: double-click `02-UNINSTALL.command`. If macOS warns you, right-click the script and choose Open."],
  ["Windows：双击 `02-UNINSTALL.bat`；如果系统弹出安全提示，选择仍要运行。", "Windows: double-click `02-UNINSTALL.bat`. If Windows shows a security prompt, choose to run it anyway."],
  ["卸载后，本地助手、自启动、连接 token、保存设置和临时缓存会被删除；已下载的视频和图片不会被删除。", "Uninstall removes the local assistant, startup entry, connection token, save settings, and temporary cache. Downloaded videos and images are not deleted."],
  ["需要重新使用时，再运行 `01-INSTALL` 即可。", "To use it again, run `01-INSTALL`."],
  ["连接本地助手", "Connect local assistant"],
  ["如果你是手动启动本地助手，请输入窗口里的 6 位配对码。通过上方安装包安装时通常会自动连接。也可以直接打开", "If you started the local assistant manually, enter the 6-digit pairing code shown in its window. The installer usually connects automatically. You can also open the"],
  ["本机控制台", "local console"],
  ["输入配对码", "Enter pairing code"],
  ["连接", "Connect"],
  ["发现新版本", "New version available"],
  ["平台规则变化时，更新本地助手可以刷新解析依赖和平台适配。", "When platform rules change, updating refreshes parsing dependencies and platform adapters."],
  ["更新本地助手", "Update local assistant"],
  ["稍后再说", "Later"],
  ["手机 / NAS 控制", "Phone / NAS control"],
  ["电脑或 NAS 与手机连接同一个网络后，点击下面按钮生成局域网访问地址和配对码。手机打开该地址，输入配对码，就可以在手机上粘贴链接并控制这台设备下载。", "When your computer or NAS is on the same network as your phone, generate a LAN address and pairing code below. Open the address on your phone, enter the code, then paste links and control downloads on this device."],
  ["生成手机连接信息", "Generate phone access"],
  ["粘贴链接", "Paste link"],
  ["支持视频、图片、图集或平台分享文案", "Supports videos, images, albums, and platform share text"],
  ["例如：复制平台分享文案，或粘贴 https://...", "Example: paste platform share text or an https:// link"],
  ["解析", "Parse"],
  ["粘贴链接后点击解析。", "Paste a link, then click Parse."],
  ["解析结果", "Result"],
  ["清除记录", "Clear records"],
  ["标题", "Title"],
  ["作者/频道", "Author / channel"],
  ["内容", "Content"],
  ["来源", "Source"],
  ["打开原始页面", "Open source page"],
  ["下载", "Download"],
  ["停止下载", "Stop download"],
  ["等待下载", "Waiting to download"],
  ["高级格式选择", "Advanced format selection"],
  ["保存设置", "Save settings"],
  ["保存目录", "Save folder"],
  ["选择文件夹", "Choose folder"],
  ["保存", "Save"],
  ["支持平台", "Supported platforms"],
  ["抖音、小红书、TikTok、YouTube、Bilibili、X / Twitter、Instagram，以及其他常见公开视频、图片和图集页面。工具会优先保存平台公开返回的原始资源或高清资源，不承诺去水印；平台名称仅用于说明可能兼容的公开链接类型，实际支持情况以解析结果为准。", "Douyin, Xiaohongshu, TikTok, YouTube, Bilibili, X / Twitter, Instagram, and other common public video, image, and album pages. The tool prioritizes original or high-resolution resources publicly returned by platforms and does not promise watermark removal. Platform names only describe possible public-link compatibility; actual support depends on parsing results."],
  ["使用方法", "How to use"],
  ["启动本地助手后，在本页粘贴链接，点击解析，确认预览和标题后下载。文件直接保存到你的电脑。", "Start the local assistant, paste a link here, click Parse, check the preview and title, then download. Files are saved directly on your computer."],
  ["正在生成...", "Generating..."],
  ["已生成，10 分钟内有效。", "Generated. Valid for 10 minutes."],
  ["生成失败，请确认本地助手已连接。", "Failed to generate. Make sure the local assistant is connected."],
  ["手机配对码", "Phone pairing code"],
  ["推荐手机打开", "Recommended phone URL"],
  ["没有检测到局域网地址", "No LAN address detected"],
  ["显示二维码", "Show QR code"],
  ["隐藏二维码", "Hide QR code"],
  ["手机扫码打开链接", "Scan to open link"],
  ["用手机相机或微信扫码，打开后输入上方配对码。", "Scan with your phone camera or WeChat, then enter the pairing code above."],
  ["备用地址", "Backup addresses"],
  ["如果推荐地址打不开，请确认手机和这台设备在同一个 Wi-Fi，或检查系统防火墙是否允许本地助手接入。", "If the recommended address does not open, make sure your phone and this device are on the same Wi-Fi, or check whether the firewall allows local assistant access."],
  ["已识别为 macOS，推荐下载 macOS 安装包", "macOS detected. The macOS installer is recommended."],
  ["已识别为 Windows，推荐下载 Windows 安装包", "Windows detected. The Windows installer is recommended."],
  ["已识别为 iPhone / iPad，当前需要在电脑上安装本地助手", "iPhone / iPad detected. Install the local assistant on a computer first."],
  ["已识别为 Android，当前需要在电脑上安装本地助手", "Android detected. Install the local assistant on a computer first."],
  ["请选择你的电脑系统安装本地助手", "Choose your computer system to install the local assistant."],
  ["正在准备下载...", "Preparing download..."],
  ["下载链接生成失败，请稍后再试。", "Failed to generate the download link. Please try again later."],
  ["下载已开始。如果浏览器没有反应，请再点一次系统卡片。", "Download started. If the browser does nothing, click the system card again."],
  ["下载安装包失败，请刷新页面后再试。", "Failed to download the installer. Refresh and try again."],
  ["请输入配对码。", "Enter the pairing code."],
  ["连接失败，请检查配对码。", "Connection failed. Check the pairing code."],
  ["读取保存目录失败。", "Failed to read the save folder."],
  ["正在保存...", "Saving..."],
  ["保存目录已更新。", "Save folder updated."],
  ["保存目录不可用。", "Save folder is unavailable."],
  ["正在清除记录...", "Clearing records..."],
  ["记录已清除。", "Records cleared."],
  ["清除记录失败，请更新本地助手后再试。", "Failed to clear records. Update the local assistant and try again."],
  ["正在打开文件夹选择窗口...", "Opening folder picker..."],
  ["已取消选择。", "Selection canceled."],
  ["无法打开文件夹选择窗口，请手动输入目录。", "Could not open the folder picker. Enter the folder manually."],
  ["请先粘贴链接或分享文案。", "Paste a link or share text first."],
  ["正在解析...", "Parsing..."],
  ["解析失败。", "Parsing failed."],
  ["正在准备下载...", "Preparing download..."],
  ["下载失败。", "Download failed."],
  ["正在停止下载...", "Stopping download..."],
  ["停止转换", "Stop conversion"],
  ["正在停止转换...", "Stopping conversion..."],
  ["停止失败，请稍后再试。", "Failed to stop. Please try again."],
  ["下载已停止", "Download stopped"],
  ["下载已停止。", "Download stopped."],
  ["转换已停止", "Conversion stopped"],
  ["转换已停止。", "Conversion stopped."],
  ["正在打开...", "Opening..."],
  ["已打开", "Opened"],
  ["无法打开文件夹。", "Could not open folder."],
  ["任务状态读取失败。", "Failed to read task status."],
  ["解析完成，可以下载。", "Parsed. Ready to download."],
  ["操作失败。", "Operation failed."],
  ["解析失败，请重新复制链接后再试。", "Parsing failed. Copy the link again and try."],
  ["下载完成。", "Download completed."],
  ["未解析到内容", "No content parsed"],
  ["无", "None"],
  ["未命名内容", "Untitled content"],
  ["未知作者", "Unknown author"],
  ["下载全部图片", "Download all images"],
  ["下载最佳 MP4", "Download best MP4"],
  ["本地视频转换", "Local video conversion"],
  ["转为兼容 iPhone 相册的 MP4", "Convert to an MP4 compatible with iPhone Photos"],
  ["选择这台电脑或 NAS 上的视频。原文件会保留，转换版将保存到原文件所在文件夹。", "Choose a video on this computer or NAS. The original file is kept, and the converted version is saved beside it."],
  ["选择本地视频", "Choose local video"],
  ["尚未选择视频", "No video selected"],
  ["已选择", "Selected"],
  ["正在打开视频选择窗口...", "Opening video picker..."],
  ["请选择一个本地视频。", "Choose a local video first."],
  ["该文件已经是 iPhone 相册版。", "This file is already an iPhone Photos version."],
  ["无法打开视频选择窗口，请稍后再试。", "Could not open the video picker. Try again later."],
  ["正在准备本地转换...", "Preparing local conversion..."],
  ["已生成 iPhone 相册版", "iPhone Photos version ready"],
  ["图片预览", "Image preview"],
  ["封面", "Cover"],
  ["分辨率", "Resolution"],
  ["格式", "Format"],
  ["大小", "Size"],
  ["视频", "Video"],
  ["音频", "Audio"],
  ["说明", "Note"],
  ["需要合并", "Needs merge"],
  ["单文件", "Single file"],
  ["已下载文件", "Downloaded file"],
  ["保存到手机", "Save to phone"],
  ["转为 iPhone 相册版", "Convert for iPhone Photos"],
  ["正在转换...", "Converting..."],
  ["正在转换为 iPhone 相册格式...", "Converting for iPhone Photos..."],
  ["正在本机转换为 iPhone 相册格式...", "Converting locally for iPhone Photos..."],
  ["已暂停在线视频预览，转换仅在本机处理。", "Online preview paused. Conversion is local only."],
  ["正在整理转换文件...", "Finalizing converted file..."],
  ["已生成 iPhone 相册版", "iPhone Photos version ready"],
  ["iPhone 相册版", "iPhone Photos version"],
  ["转换失败，请稍后重试。", "Conversion failed. Try again later."],
  ["下载完成后才能转换。", "Download before converting."],
  ["当前文件不是可转换的视频文件。", "This file is not a convertible video."],
  ["该功能需要 FFmpeg，请先安装 FFmpeg 后再转换。", "This feature needs FFmpeg. Install FFmpeg before converting."],
  ["文件已保存", "File saved"],
  ["打开所在文件夹", "Open containing folder"],
  ["等待解析", "Waiting to parse"],
  ["请求失败。", "Request failed."],
  ["当前已经是最新版本。", "You are already on the latest version."],
  ["更新任务已开始。", "Update started."],
  ["更新本地助手和平台解析依赖，保留保存目录、配对状态和本地会话。", "Updates the local assistant and platform parsing dependencies while keeping the save folder, pairing state, and local session."],
  ["正在更新...", "Updating..."],
  ["正在下载并替换本地助手，完成后会自动重启。", "Downloading and replacing the local assistant. It will restart automatically."],
  ["重新更新", "Update again"],
  ["更新启动失败，请稍后再试。", "Failed to start update. Try again later."],
  ["本地助手正在重启，稍等几秒会自动恢复连接。", "The local assistant is restarting. It should reconnect in a few seconds."],
  ["正在更新本地助手...", "Updating local assistant..."],
  ["正在重连...", "Reconnecting..."],
  ["更新已安装，正在重新连接本地助手...", "Update installed. Reconnecting to the local assistant..."],
  ["更新文件可能已安装，但本地助手还没有重启到新版。请重启本地助手，或运行安装包里的 03-UPDATE。", "The update files may be installed, but the assistant has not restarted into the new version. Restart the assistant or run 03-UPDATE from the installer folder."],
  ["配对码已过期，请在电脑/NAS 页面重新生成手机连接信息。", "The pairing code expired. Generate phone access again on the computer/NAS page."],
  ["配对码已过期，请重启本地助手。", "The pairing code expired. Restart the local assistant."],
  ["配对码不正确。", "The pairing code is incorrect."],
  ["请先完成本地助手配对。", "Pair with the local assistant first."],
  ["任务不存在或本地助手已重启。", "The task does not exist, or the local assistant restarted."],
  ["当前没有更新任务。", "No update task is running."],
  ["只能从本机控制台自动连接。", "Automatic connection is only allowed from the local console."],
  ["手机和电脑/NAS 连接同一个网络后，打开下面的地址并输入配对码。", "After your phone and computer/NAS are on the same network, open the address below and enter the pairing code."],
  ["请等待解析完成后再下载。", "Wait for parsing to finish before downloading."],
  ["下载正在进行中。", "Download is already running."],
  ["当前任务正在处理中。", "The current task is still running."],
  ["没有正在下载的任务。", "No download is running."],
  ["下载完成后才能打开文件夹。", "You can open the folder after the download finishes."],
  ["无法打开文件夹，请手动前往保存目录。", "Could not open the folder. Open the save folder manually."],
  ["文件不存在。", "File not found."],
  ["文件路径无效。", "Invalid file path."],
  ["没有可预览资源。", "No preview resource is available."],
  ["没有可预览图片。", "No preview image is available."],
  ["暂时无法获取更新信息，请稍后再试。", "Could not fetch update information. Try again later."],
  ["更新信息格式异常，请稍后再试。", "Update information is invalid. Try again later."],
  ["更新启动失败，请重新下载安装包。", "Failed to start the update. Download the installer again."],
  ["正在获取更新信息...", "Fetching update information..."],
  ["正在下载更新包...", "Downloading update package..."],
  ["更新信息不完整，请稍后再试。", "Update information is incomplete. Try again later."],
  ["更新包校验失败，请稍后重试或重新下载安装包。", "Update package verification failed. Try again later or download the installer again."],
  ["正在解压更新包...", "Extracting update package..."],
  ["正在替换本地助手文件...", "Replacing local assistant files..."],
  ["正在更新 Python 依赖...", "Updating Python dependencies..."],
  ["正在检查后台浏览器组件...", "Checking background browser component..."],
  ["更新完成，正在重启本地助手...", "Update complete. Restarting the local assistant..."],
  ["本地助手已更新，正在重新连接。", "Local assistant updated. Reconnecting..."],
  ["更新失败，请稍后重试或重新下载安装包。", "Update failed. Try again later or download the installer again."],
  ["Python 依赖更新失败。", "Python dependency update failed."],
  ["该内容当前无法无感解析。", "This content cannot be parsed automatically right now."],
  ["解析完成", "Parsed"],
  ["没有可下载格式，请重新解析。", "No downloadable format found. Parse again."],
  ["正在下载...", "Downloading..."],
  ["下载完成", "Download completed"],
  ["下载完成，正在处理文件...", "Download completed. Processing files..."],
  ["正在处理平台验证...", "Handling platform verification..."],
  ["该内容需要平台验证，当前无法无感解析。", "This content requires platform verification and cannot be parsed automatically."],
  ["这条小红书内容没有返回可下载的视频流，也没有拿到可确认的图片资源。请重新复制分享链接后再试。", "This Xiaohongshu post did not return a downloadable video stream or confirmed image resources. Copy the share link again and try."],
  ["平台没有返回可下载的视频资源，请换一个公开链接再试。", "The platform did not return a downloadable video resource. Try another public link."],
  ["暂不支持这个链接，或平台没有返回可解析的内容。", "This link is not supported yet, or the platform did not return parseable content."],
  ["平台没有返回可下载的资源，请重新复制链接并解析后再试。", "The platform did not return downloadable resources. Copy the link again and parse it once more."],
  ["平台没有返回可确认的图片资源，请换一个公开链接再试。", "The platform did not return confirmed image resources. Try another public link."],
  ["网络超时，请稍后重试。", "Network timed out. Try again later."],
  ["磁盘空间不足，请清理空间或更换保存目录。", "Disk space is low. Free up space or choose another save folder."],
  ["该内容当前无法解析，请重新复制链接后再试。", "This content cannot be parsed right now. Copy the link again and try."],
  ["请输入视频链接。", "Enter a video link."],
  ["没有识别到 http(s) 链接，请粘贴视频 URL 或平台分享文案。", "No http(s) link was found. Paste a video URL or platform share text."],
  ["解析结果为空，无法读取视频信息。", "The parse result is empty. Video information cannot be read."],
  ["当前 MVP 只支持单个视频链接，暂不支持播放列表或批量链接。", "This MVP only supports one video link at a time, not playlists or batch links."],
  ["没有找到可下载格式，可能需要登录、cookies，或该视频受限制。", "No downloadable format was found. The video may require login/cookies or be restricted."],
  ["当前解析结果没有可下载图片。", "The current parse result has no downloadable images."],
  ["平台返回的资源地址已失效，正在重新获取下载地址。", "The platform resource URL expired. Refreshing the download URL..."],
  ["平台拒绝了当前下载地址，正在重新获取下载地址。", "The platform rejected the current download URL. Refreshing it..."],
  ["URL 不支持：yt-dlp 暂时无法解析这个网站或链接。", "Unsupported URL: yt-dlp cannot parse this site or link right now."],
  ["该视频需要新的浏览器 cookies。正在自动尝试本机浏览器 cookies。", "This video needs fresh browser cookies. Trying local browser cookies automatically."],
  ["该视频可能需要登录或 cookies。正在自动尝试本机浏览器 cookies。", "This video may require login or cookies. Trying local browser cookies automatically."],
  ["视频不存在或当前不可用。", "The video does not exist or is currently unavailable."],
  ["视频可能存在地区限制，当前网络无法访问。", "The video may be geo-restricted and unavailable on the current network."],
  ["FFmpeg 未安装或不可用。需要合并音视频时请先安装 FFmpeg。", "FFmpeg is not installed or unavailable. Install FFmpeg before merging audio and video."],
  ["网络超时，请稍后重试或检查网络连接。", "Network timed out. Try again later or check your connection."],
  ["所选格式不可用，请重新解析后选择其他格式。", "The selected format is unavailable. Parse again and choose another format."],
  ["磁盘空间不足，请更换下载目录或清理空间。", "Disk space is low. Change the download folder or free up space."],
  ["下载目录没有写入权限，请选择其他目录。", "The download folder is not writable. Choose another folder."],
  ["该视频需要平台验证，当前无法无感解析。", "This video requires platform verification and cannot be parsed automatically."],
  ["正在重新读取公开页面...", "Reading the public page again..."],
  ["平台没有返回可确认的目标视频资源，请重新复制链接后再试。", "The platform did not return a confirmed target video resource. Copy the link again and try."],
  ["链接已失效或平台未返回具体视频，请重新复制分享链接。", "The link expired, or the platform did not return a specific video. Copy the share link again."],
  ["平台没有返回可下载的视频资源，请重新复制链接后再试。", "The platform did not return a downloadable video resource. Copy the link again and try."],
  ["暂不支持这个链接，或平台没有返回可解析的视频。", "This link is not supported yet, or the platform did not return a parseable video."],
  ["下载地址已刷新，正在重新下载...", "Download URL refreshed. Downloading again..."],
  ["等待处理", "Waiting"],
  ["正在解析视频...", "Parsing video..."],
  ["正在直接解析...", "Parsing directly..."],
  ["直接解析成功", "Direct parsing succeeded"],
  ["未命名视频", "Untitled video"],
  ["未命名图片", "Untitled image"],
  ["未知频道", "Unknown channel"],
  ["未知站点", "Unknown site"],
  ["未知", "Unknown"],
  ["平台返回图片", "Platform image"],
  ["必要时合并音视频", "Merge audio and video if needed"],
  ["未知分辨率", "Unknown resolution"],
  ["平台没有返回可确认的图片资源。", "The platform did not return confirmed image resources."],
  ["下载失败，请重新解析后再试。", "Download failed. Parse again and try."],
  ["无法打开文件夹选择窗口，请手动输入保存目录。", "Could not open the folder picker. Enter the save folder manually."],
  ["当前系统缺少文件夹选择组件，请手动输入保存目录。", "This system does not have a folder picker component. Enter the save folder manually."],
  ["目录不可写", "Folder is not writable"],
];

const ZH_TO_EN = new Map(STATIC_TRANSLATIONS);
const EN_TO_ZH = new Map(STATIC_TRANSLATIONS.map(([zh, en]) => [en, zh]));

const els = {
  legalOverlay: document.querySelector("#legalOverlay"),
  legalLanguageToggle: document.querySelector("#legalLanguageToggle"),
  legalConfirmCheckbox: document.querySelector("#legalConfirmCheckbox"),
  legalAgreeButton: document.querySelector("#legalAgreeButton"),
  languageToggle: document.querySelector("#languageToggle"),
  connectionBadge: document.querySelector("#connectionBadge"),
  offlinePanel: document.querySelector("#offlinePanel"),
  consolePanel: document.querySelector("#consolePanel"),
  installPanel: document.querySelector("#installPanel"),
  osHint: document.querySelector("#osHint"),
  macDownloadCard: document.querySelector("#macDownloadCard"),
  windowsDownloadCard: document.querySelector("#windowsDownloadCard"),
  installerDownloadMessage: document.querySelector("#installerDownloadMessage"),
  mobileNotice: document.querySelector("#mobileNotice"),
  retryHealthButton: document.querySelector("#retryHealthButton"),
  retryConsoleButton: document.querySelector("#retryConsoleButton"),
  updatePanel: document.querySelector("#updatePanel"),
  updateVersionText: document.querySelector("#updateVersionText"),
  updateMessage: document.querySelector("#updateMessage"),
  updateButton: document.querySelector("#updateButton"),
  dismissUpdateButton: document.querySelector("#dismissUpdateButton"),
  shareDeviceButton: document.querySelector("#shareDeviceButton"),
  shareDeviceMessage: document.querySelector("#shareDeviceMessage"),
  shareDeviceResult: document.querySelector("#shareDeviceResult"),
  pairPanel: document.querySelector("#pairPanel"),
  pairCodeInput: document.querySelector("#pairCodeInput"),
  pairButton: document.querySelector("#pairButton"),
  pairError: document.querySelector("#pairError"),
  mainPanel: document.querySelector("#mainPanel"),
  sourceInput: document.querySelector("#sourceInput"),
  resolveButton: document.querySelector("#resolveButton"),
  selectLocalVideoButton: document.querySelector("#selectLocalVideoButton"),
  localVideoSelection: document.querySelector("#localVideoSelection"),
  startLocalConversionButton: document.querySelector("#startLocalConversionButton"),
  stopLocalConversionButton: document.querySelector("#stopLocalConversionButton"),
  localConversionProgress: document.querySelector("#localConversionProgress"),
  localConversionProgressBar: document.querySelector("#localConversionProgressBar"),
  localConversionProgressText: document.querySelector("#localConversionProgressText"),
  localConversionResult: document.querySelector("#localConversionResult"),
  resultPanel: document.querySelector("#resultPanel"),
  taskMessage: document.querySelector("#taskMessage"),
  clearRecordsButton: document.querySelector("#clearRecordsButton"),
  previewArea: document.querySelector("#previewArea"),
  mediaTitle: document.querySelector("#mediaTitle"),
  mediaAuthor: document.querySelector("#mediaAuthor"),
  mediaType: document.querySelector("#mediaType"),
  sourceLink: document.querySelector("#sourceLink"),
  downloadButton: document.querySelector("#downloadButton"),
  stopDownloadButton: document.querySelector("#stopDownloadButton"),
  progressBar: document.querySelector("#progressBar"),
  progressText: document.querySelector("#progressText"),
  downloadResult: document.querySelector("#downloadResult"),
  formatDetails: document.querySelector("#formatDetails"),
  formatSelect: document.querySelector("#formatSelect"),
  formatTable: document.querySelector("#formatTable"),
  downloadDirInput: document.querySelector("#downloadDirInput"),
  chooseFolderButton: document.querySelector("#chooseFolderButton"),
  saveSettingsButton: document.querySelector("#saveSettingsButton"),
  settingsMessage: document.querySelector("#settingsMessage"),
};

let token = localStorage.getItem(TOKEN_KEY) || "";
let currentTaskId = "";
let currentTask = null;
let pollTimer = null;
let localVideoSelection = null;
let localConversionTaskId = "";
let localConversionTask = null;
let localConversionPollTimer = null;
let updatePollTimer = null;
let triedLocalToken = false;
let consoleRedirectTimer = null;
let currentLang = localStorage.getItem(LANGUAGE_KEY) === "en" ? "en" : "zh";
let legalAccepted = localStorage.getItem(LEGAL_ACCEPT_KEY) === "1";

consumeTokenFromHash();
setupLanguage();
setupLegalNotice();
setupInstallPanel();
setupInstallerDownloads();

els.languageToggle.addEventListener("click", toggleLanguage);
els.legalLanguageToggle.addEventListener("click", toggleLanguage);
els.legalConfirmCheckbox.addEventListener("change", updateLegalAgreeState);
els.legalAgreeButton.addEventListener("click", acceptLegalNotice);
els.retryHealthButton.addEventListener("click", checkHealth);
els.retryConsoleButton.addEventListener("click", checkHealth);
els.updateButton.addEventListener("click", startAgentUpdate);
els.dismissUpdateButton.addEventListener("click", dismissUpdateNotice);
els.shareDeviceButton.addEventListener("click", shareDeviceAccess);
els.pairButton.addEventListener("click", pairAgent);
els.pairCodeInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") pairAgent();
});
els.resolveButton.addEventListener("click", resolveContent);
els.downloadButton.addEventListener("click", downloadContent);
els.stopDownloadButton.addEventListener("click", stopDownload);
els.selectLocalVideoButton.addEventListener("click", selectLocalVideo);
els.startLocalConversionButton.addEventListener("click", startLocalConversion);
els.stopLocalConversionButton.addEventListener("click", stopLocalConversion);
els.clearRecordsButton.addEventListener("click", clearRecords);
els.chooseFolderButton.addEventListener("click", chooseDownloadFolder);
els.saveSettingsButton.addEventListener("click", saveSettings);

if (legalAccepted) checkHealth();

function setupLanguage() {
  applyLanguage();
}

function toggleLanguage() {
  currentLang = currentLang === "en" ? "zh" : "en";
  localStorage.setItem(LANGUAGE_KEY, currentLang);
  applyLanguage();
  setupInstallPanel();
  if (currentTask) renderTask(currentTask);
  renderLocalVideoSelection();
  if (localConversionTask) renderLocalConversionTask(localConversionTask);
  if (token) checkForUpdates();
}

function applyLanguage() {
  document.documentElement.lang = currentLang === "en" ? "en" : "zh-CN";
  document.title = ui("视频/图片下载工具");
  const description = ui("粘贴公开内容链接，解析和下载都在你的设备本地完成。");
  setMeta("name", "description", description);
  setMeta("property", "og:title", ui("视频/图片下载工具"));
  setMeta("property", "og:description", description);
  els.languageToggle.textContent = currentLang === "en" ? "中文" : "EN";
  els.languageToggle.setAttribute("aria-label", currentLang === "en" ? "Switch to Chinese" : "Switch to English");
  els.legalLanguageToggle.textContent = els.languageToggle.textContent;
  els.legalLanguageToggle.setAttribute("aria-label", els.languageToggle.getAttribute("aria-label"));
  translateTextNodes(document.body);
  translateAttributes(document.body);
}

function setupLegalNotice() {
  if (legalAccepted) {
    hide(els.legalOverlay);
    document.body.classList.remove("legal-locked");
    return;
  }
  document.body.classList.add("legal-locked");
  show(els.legalOverlay);
  updateLegalAgreeState();
}

function updateLegalAgreeState() {
  els.legalAgreeButton.disabled = !els.legalConfirmCheckbox.checked;
}

function acceptLegalNotice() {
  if (!els.legalConfirmCheckbox.checked) return;
  legalAccepted = true;
  localStorage.setItem(LEGAL_ACCEPT_KEY, "1");
  hide(els.legalOverlay);
  document.body.classList.remove("legal-locked");
  checkHealth();
}

function setMeta(attr, name, content) {
  const selector = attr === "property" ? `meta[property="${name}"]` : `meta[name="${name}"]`;
  const element = document.querySelector(selector);
  if (element) element.setAttribute("content", content);
}

function translateTextNodes(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent || ["SCRIPT", "STYLE", "TEXTAREA"].includes(parent.tagName)) {
        return NodeFilter.FILTER_REJECT;
      }
      return node.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    },
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach((node) => {
    node.nodeValue = localizeRawText(node.nodeValue);
  });
}

function translateAttributes(root) {
  root.querySelectorAll("[placeholder], [alt], [aria-label]").forEach((element) => {
    ["placeholder", "alt", "aria-label"].forEach((attribute) => {
      if (!element.hasAttribute(attribute)) return;
      element.setAttribute(attribute, localizeRawText(element.getAttribute(attribute)));
    });
  });
}

function localizeRawText(rawValue) {
  const raw = String(rawValue ?? "");
  const trimmed = raw.trim();
  if (!trimmed) return raw;
  const translated = localizeExact(trimmed);
  if (translated === trimmed) return raw;
  return raw.replace(trimmed, translated);
}

function localizeExact(value) {
  const text = String(value ?? "");
  const map = currentLang === "en" ? ZH_TO_EN : EN_TO_ZH;
  return map.get(text) || text;
}

function ui(value) {
  return currentLang === "en" ? ZH_TO_EN.get(value) || value : value;
}

function localizeUserMessage(message) {
  if (!message) return "";
  const text = String(message);
  const exact = localizeExact(text);
  if (exact !== text) return exact;
  if (currentLang === "en") {
    const imageMatch = text.match(/^(\d+) 张图片$/);
    if (imageMatch) return `${imageMatch[1]} images`;
    const imageProgress = text.match(/^下载中：第 (\d+) \/ (\d+) 张$/);
    if (imageProgress) return `Downloading image ${imageProgress[1]} / ${imageProgress[2]}`;
    const fileProgress = text.match(/^下载中：(.+) \/ (.+)，速度 (.+)，剩余 (.+)$/);
    if (fileProgress) {
      return `Downloading: ${fileProgress[1]} / ${fileProgress[2]}, speed ${fileProgress[3]}, ETA ${fileProgress[4]}`;
    }
    const operationFailed = text.match(/^操作失败：(.+)$/);
    if (operationFailed) return `Operation failed: ${operationFailed[1]}`;
    const unwritableDir = text.match(/^目录不可写：(.+)$/);
    if (unwritableDir) return `Folder is not writable: ${unwritableDir[1]}`;
  }
  return text;
}

function versionLine(currentVersion, latestVersion) {
  return currentLang === "en"
    ? `Current ${currentVersion}, latest ${latestVersion}`
    : `当前 ${currentVersion}，最新 ${latestVersion}`;
}

function targetVersionLine(version, percent) {
  if (currentLang === "en") {
    return `Target ${version}${percent ? `, ${percent}%` : ""}`;
  }
  return `目标版本 ${version}${percent ? `，${percent}%` : ""}`;
}

function waitingForRestartLine(currentVersion, targetVersion) {
  return currentLang === "en"
    ? `Update files installed. Waiting for the local assistant to restart from ${currentVersion} to ${targetVersion}...`
    : `更新文件已安装，正在等待本地助手从 ${currentVersion} 重启到 ${targetVersion}...`;
}

async function checkHealth() {
  setConnection("idle", ui("检测中"));
  hide(els.offlinePanel);
  hide(els.consolePanel);
  hide(els.pairPanel);
  clearConsoleRedirect();
  try {
    const health = await agentFetch("/api/health", { auth: Boolean(token) });
    if (health.authenticated) {
      setConnection("online", ui("已连接"));
      hide(els.pairPanel);
      hide(els.offlinePanel);
      hide(els.consolePanel);
      hide(els.installPanel);
      show(els.mainPanel);
      await loadSettings();
      await restoreLatestResult();
      checkForUpdates();
      return;
    }
    if (isAgentHosted()) {
      if (canUseLocalToken() && !triedLocalToken) {
        triedLocalToken = true;
        const result = await agentFetch("/api/local-token", { auth: false });
        token = result.token;
        localStorage.setItem(TOKEN_KEY, token);
        await checkHealth();
        return;
      }
      setConnection("pairing", ui("待配对"));
      show(els.pairPanel);
      hide(els.offlinePanel);
      hide(els.consolePanel);
      hide(els.installPanel);
      hide(els.mainPanel);
      if (health.pairing_expires_in <= 0) {
        showPairError(ui("配对码已过期，请在电脑/NAS 页面重新生成手机连接信息。"));
      } else {
        hidePairError();
      }
      return;
    }
    if (!canUseLocalToken()) {
      setConnection("pairing", ui("待打开"));
      show(els.consolePanel);
      show(els.installPanel);
      hide(els.offlinePanel);
      hide(els.pairPanel);
      hide(els.mainPanel);
      scheduleConsoleRedirect();
      return;
    }
    if (canUseLocalToken() && !triedLocalToken) {
      triedLocalToken = true;
      const result = await agentFetch("/api/local-token", { auth: false });
      token = result.token;
      localStorage.setItem(TOKEN_KEY, token);
      await checkHealth();
      return;
    }
    setConnection("pairing", ui("待连接"));
    show(els.pairPanel);
    show(els.installPanel);
    hide(els.offlinePanel);
    hide(els.mainPanel);
    if (health.pairing_expires_in <= 0) {
      showPairError(ui("配对码已过期，请重启本地助手。"));
    } else {
      hidePairError();
    }
  } catch (_error) {
    setConnection("offline", ui("未连接"));
    show(els.offlinePanel);
    show(els.installPanel);
    hide(els.updatePanel);
    hide(els.consolePanel);
    hide(els.pairPanel);
    hide(els.mainPanel);
  }
}

async function checkForUpdates() {
  if (!token || !els.updatePanel) return;
  try {
    const payload = await agentFetch("/api/update/check");
    const status = payload.status || {};
    if (["queued", "running", "restarting"].includes(status.state)) {
      renderUpdateStatus(status);
      show(els.updatePanel);
      startUpdatePolling();
      return;
    }
    if (!payload.update_available) {
      hide(els.updatePanel);
      return;
    }
    if (localStorage.getItem(`${UPDATE_DISMISS_KEY}:${payload.latest_version}`) === "1") {
      hide(els.updatePanel);
      return;
    }
    els.updatePanel.dataset.latestVersion = payload.latest_version || "";
    els.updateVersionText.textContent = versionLine(payload.current_version, payload.latest_version);
    els.updateMessage.textContent = localizeUserMessage(payload.notes) || ui("平台规则变化时，更新本地助手可以刷新解析依赖和平台适配。");
    els.updateButton.disabled = false;
    els.updateButton.textContent = ui("更新本地助手");
    els.dismissUpdateButton.disabled = false;
    show(els.updatePanel);
  } catch (_error) {
    hide(els.updatePanel);
  }
}

async function startAgentUpdate() {
  els.updateButton.disabled = true;
  els.dismissUpdateButton.disabled = true;
  els.updateButton.textContent = ui("正在更新...");
  els.updateMessage.textContent = ui("正在下载并替换本地助手，完成后会自动重启。");
  try {
    const status = await agentFetch("/api/update/start", {
      method: "POST",
      body: { force: false },
    });
    renderUpdateStatus(status);
    startUpdatePolling();
  } catch (error) {
    els.updateButton.disabled = false;
    els.dismissUpdateButton.disabled = false;
    els.updateButton.textContent = ui("重新更新");
    els.updateMessage.textContent = localizeUserMessage(error.message) || ui("更新启动失败，请稍后再试。");
  }
}

function startUpdatePolling() {
  if (updatePollTimer) clearInterval(updatePollTimer);
  pollUpdateStatus();
  updatePollTimer = setInterval(pollUpdateStatus, 1600);
}

async function pollUpdateStatus() {
  try {
    const status = await agentFetch("/api/update/status");
    renderUpdateStatus(status);
    if (["completed", "failed"].includes(status.state)) {
      clearInterval(updatePollTimer);
      updatePollTimer = null;
      if (status.state === "completed") {
        verifyUpdateApplied(status.version);
      }
    }
  } catch (_error) {
    els.updateMessage.textContent = ui("本地助手正在重启，稍等几秒会自动恢复连接。");
    els.updateButton.disabled = true;
  }
}

function renderUpdateStatus(status) {
  show(els.updatePanel);
  const percent = Math.round(Number(status.percent || 0) * 100);
  if (status.version) {
    els.updateVersionText.textContent = targetVersionLine(status.version, percent);
  }
  els.updateMessage.textContent = localizeUserMessage(status.message) || ui("正在更新本地助手...");
  if (status.state === "failed") {
    els.updateButton.disabled = false;
    els.dismissUpdateButton.disabled = false;
    els.updateButton.textContent = ui("重新更新");
  } else if (status.state === "completed") {
    els.updateButton.disabled = true;
    els.dismissUpdateButton.disabled = false;
    els.updateButton.textContent = ui("正在重连...");
    els.updateMessage.textContent = localizeUserMessage(status.message) || ui("更新已安装，正在重新连接本地助手...");
  } else {
    els.updateButton.disabled = true;
    els.dismissUpdateButton.disabled = true;
    els.updateButton.textContent = ui("正在更新...");
  }
}

async function verifyUpdateApplied(expectedVersion) {
  const target = String(expectedVersion || "").trim();
  for (let attempt = 0; attempt < 10; attempt += 1) {
    await sleep(1500);
    try {
      const health = await agentFetch("/api/health", { auth: Boolean(token) });
      if (!target || health.version === target) {
        await checkHealth();
        return;
      }
      els.updateMessage.textContent = waitingForRestartLine(health.version, target);
    } catch (_error) {
      els.updateMessage.textContent = ui("本地助手正在重启，稍等几秒会自动恢复连接。");
    }
  }
  els.updateButton.disabled = false;
  els.updateButton.textContent = ui("重新检测");
  els.updateMessage.textContent = ui("更新文件可能已安装，但本地助手还没有重启到新版。请重启本地助手，或运行安装包里的 03-UPDATE。");
}

function dismissUpdateNotice() {
  const version = els.updatePanel.dataset.latestVersion || (els.updateVersionText.textContent || "").match(/最新\\s*([^，\\s]+)/)?.[1];
  if (version) {
    localStorage.setItem(`${UPDATE_DISMISS_KEY}:${version}`, "1");
  }
  hide(els.updatePanel);
}

function resolveAgentBase() {
  if (window.VIDEO_DOWNLOADER_AGENT_BASE) {
    return String(window.VIDEO_DOWNLOADER_AGENT_BASE).replace(/\/$/, "");
  }
  const host = window.location.hostname;
  if (window.location.port === "17890") {
    return window.location.origin;
  }
  return "http://127.0.0.1:17890";
}

function resolveInstallerLinkEndpoint() {
  if (window.VIDEO_DOWNLOADER_DOWNLOAD_LINK_ENDPOINT === null) return "";
  if (window.VIDEO_DOWNLOADER_DOWNLOAD_LINK_ENDPOINT) {
    return String(window.VIDEO_DOWNLOADER_DOWNLOAD_LINK_ENDPOINT);
  }
  return "./api/download-link";
}

function isAgentHosted() {
  return window.location.origin === AGENT_BASE;
}

function canUseLocalToken() {
  return ["127.0.0.1", "localhost", "::1"].includes(window.location.hostname);
}

function scheduleConsoleRedirect() {
  clearConsoleRedirect();
  consoleRedirectTimer = setTimeout(() => {
    window.location.href = `${AGENT_BASE}/`;
  }, 700);
}

function clearConsoleRedirect() {
  if (!consoleRedirectTimer) return;
  clearTimeout(consoleRedirectTimer);
  consoleRedirectTimer = null;
}

async function shareDeviceAccess() {
  els.shareDeviceButton.disabled = true;
  els.shareDeviceMessage.textContent = ui("正在生成...");
  hide(els.shareDeviceResult);
  els.shareDeviceResult.innerHTML = "";
  try {
    const payload = await agentFetch("/api/device/share", { method: "POST" });
    renderShareDeviceAccess(payload);
    els.shareDeviceMessage.textContent = ui("已生成，10 分钟内有效。");
  } catch (error) {
    els.shareDeviceMessage.textContent = localizeUserMessage(error.message) || ui("生成失败，请确认本地助手已连接。");
  } finally {
    els.shareDeviceButton.disabled = false;
  }
}

function renderShareDeviceAccess(payload) {
  const urls = (payload.local_urls || []).filter((url) => !url.includes("127.0.0.1") && !url.includes("localhost"));
  const recommendedUrl = payload.recommended_url && !payload.recommended_url.includes("127.0.0.1")
    ? payload.recommended_url
    : urls[0] || "";
  const backupUrls = urls.filter((url) => url !== recommendedUrl);
  const backupItems = backupUrls
    .filter((url) => !url.includes("127.0.0.1"))
    .map((url) => `<li><a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a></li>`)
    .join("");
  show(els.shareDeviceResult);
  els.shareDeviceResult.innerHTML = `
    <div class="pair-code-box">
      <label>${ui("手机配对码")}</label>
      <strong>${escapeHtml(payload.pair_code || "")}</strong>
    </div>
    <div class="recommended-url-box">
      <label>${ui("推荐手机打开")}</label>
      ${recommendedUrl ? `<a href="${escapeHtml(recommendedUrl)}" target="_blank" rel="noreferrer">${escapeHtml(recommendedUrl)}</a>` : `<span>${ui("没有检测到局域网地址")}</span>`}
      ${payload.recommended_qr_svg ? `<button class="secondary-button qr-toggle-button" type="button">${ui("显示二维码")}</button>` : ""}
    </div>
    ${payload.recommended_qr_svg ? `
      <div class="qr-panel hidden">
        <img alt="${ui("手机扫码打开链接")}" src="data:image/svg+xml;charset=utf-8,${encodeURIComponent(payload.recommended_qr_svg)}" />
        <p class="muted">${ui("用手机相机或微信扫码，打开后输入上方配对码。")}</p>
      </div>
    ` : ""}
    ${backupItems ? `<details class="backup-url-list"><summary>${ui("备用地址")}</summary><ul>${backupItems}</ul></details>` : ""}
    <p class="muted">${ui("如果推荐地址打不开，请确认手机和这台设备在同一个 Wi-Fi，或检查系统防火墙是否允许本地助手接入。")}</p>
  `;
  const qrButton = els.shareDeviceResult.querySelector(".qr-toggle-button");
  const qrPanel = els.shareDeviceResult.querySelector(".qr-panel");
  if (qrButton && qrPanel) {
    qrButton.addEventListener("click", () => {
      const hidden = qrPanel.classList.toggle("hidden");
      qrButton.textContent = hidden ? ui("显示二维码") : ui("隐藏二维码");
    });
  }
}

function consumeTokenFromHash() {
  const rawHash = window.location.hash.startsWith("#") ? window.location.hash.slice(1) : "";
  const params = new URLSearchParams(rawHash);
  const incomingToken = params.get("agentToken") || params.get("token");
  if (!incomingToken) return;
  token = incomingToken;
  localStorage.setItem(TOKEN_KEY, token);
  window.history.replaceState(null, document.title, window.location.pathname + window.location.search);
}

function setupInstallPanel() {
  const ua = navigator.userAgent || "";
  const platform = navigator.platform || "";
  const isIOS = /iPad|iPhone|iPod/.test(ua) || (platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const isAndroid = /Android/i.test(ua);
  const isMac = /Mac/i.test(platform) && !isIOS;
  const isWindows = /Win/i.test(platform);

  els.macDownloadCard.classList.toggle("recommended", isMac);
  els.windowsDownloadCard.classList.toggle("recommended", isWindows);
  els.mobileNotice.classList.toggle("hidden", !(isIOS || isAndroid));

  if (isMac) {
    els.osHint.textContent = ui("已识别为 macOS，推荐下载 macOS 安装包");
  } else if (isWindows) {
    els.osHint.textContent = ui("已识别为 Windows，推荐下载 Windows 安装包");
  } else if (isIOS) {
    els.osHint.textContent = ui("已识别为 iPhone / iPad，当前需要在电脑上安装本地助手");
  } else if (isAndroid) {
    els.osHint.textContent = ui("已识别为 Android，当前需要在电脑上安装本地助手");
  } else {
    els.osHint.textContent = ui("请选择你的电脑系统安装本地助手");
  }
}

function setupInstallerDownloads() {
  [els.macDownloadCard, els.windowsDownloadCard].forEach((card) => {
    if (!card) return;
    card.addEventListener("click", downloadInstaller);
  });
}

async function downloadInstaller(event) {
  event.preventDefault();
  const card = event.currentTarget;
  const platform = card.dataset.platform;
  if (!platform || card.classList.contains("downloading")) return;
  const directUrl = card.dataset.downloadUrl || INSTALLER_FILES[platform];
  const originalLabel = card.querySelector("span")?.textContent || "";
  setInstallerMessage("");
  card.classList.add("downloading");
  card.setAttribute("aria-busy", "true");
  const label = card.querySelector("span");
  if (label) label.textContent = ui("正在准备下载...");
  try {
    let downloadUrl = directUrl;
    if (INSTALLER_LINK_ENDPOINT) {
      try {
        const response = await fetch(`${INSTALLER_LINK_ENDPOINT}?platform=${encodeURIComponent(platform)}`, {
          headers: { Accept: "application/json" },
          cache: "no-store",
        });
        const payload = await response.json().catch(() => null);
        if (response.ok && payload?.url) {
          downloadUrl = payload.url;
        }
      } catch (_error) {
        downloadUrl = directUrl;
      }
    }
    if (!downloadUrl) throw new Error(ui("下载链接生成失败，请稍后再试。"));
    setInstallerMessage(ui("下载已开始。如果浏览器没有反应，请再点一次系统卡片。"));
    window.location.href = downloadUrl;
  } catch (error) {
    setInstallerMessage(localizeUserMessage(error.message) || ui("下载安装包失败，请刷新页面后再试。"));
  } finally {
    card.classList.remove("downloading");
    card.removeAttribute("aria-busy");
    if (label) label.textContent = originalLabel;
  }
}

function setInstallerMessage(message) {
  if (!els.installerDownloadMessage) return;
  els.installerDownloadMessage.textContent = message;
}

async function pairAgent() {
  const code = els.pairCodeInput.value.trim();
  if (!code) {
    showPairError(ui("请输入配对码。"));
    return;
  }
  els.pairButton.disabled = true;
  hidePairError();
  try {
    const result = await agentFetch("/api/pair", {
      method: "POST",
      body: { code },
      auth: false,
    });
    token = result.token;
    localStorage.setItem(TOKEN_KEY, token);
    els.pairCodeInput.value = "";
    await checkHealth();
  } catch (error) {
    showPairError(localizeUserMessage(error.message) || ui("连接失败，请检查配对码。"));
  } finally {
    els.pairButton.disabled = false;
  }
}

async function loadSettings() {
  try {
    const settings = await agentFetch("/api/settings");
    els.downloadDirInput.value = settings.download_dir || "";
    els.settingsMessage.textContent = "";
  } catch (error) {
    els.settingsMessage.textContent = localizeUserMessage(error.message) || ui("读取保存目录失败。");
  }
}

async function restoreLatestResult() {
  if (currentTaskId || !els.resultPanel.classList.contains("hidden")) return;
  try {
    const payload = await agentFetch("/api/tasks/latest-result");
    const task = payload?.task;
    if (!task || !task.result || task.local_conversion) return;
    currentTaskId = task.task_id;
    currentTask = task;
    renderTask(task);
  } catch (_error) {
    // A missing prior result should never block the main page.
  }
}

async function selectLocalVideo() {
  els.selectLocalVideoButton.disabled = true;
  els.localVideoSelection.textContent = ui("正在打开视频选择窗口...");
  try {
    const result = await agentFetch("/api/local-videos/select", { method: "POST" });
    if (result.cancelled) {
      renderLocalVideoSelection();
      return;
    }
    localVideoSelection = result;
    hide(els.localConversionResult);
    els.startLocalConversionButton.disabled = false;
    renderLocalVideoSelection();
  } catch (error) {
    localVideoSelection = null;
    els.startLocalConversionButton.disabled = true;
    els.localVideoSelection.textContent = localizeUserMessage(error.message) || ui("无法打开视频选择窗口，请稍后再试。");
  } finally {
    els.selectLocalVideoButton.disabled = false;
  }
}

function renderLocalVideoSelection() {
  if (!localVideoSelection?.name) {
    els.localVideoSelection.textContent = ui("尚未选择视频");
    return;
  }
  els.localVideoSelection.textContent = `${ui("已选择")}：${localVideoSelection.name}`;
}

async function startLocalConversion() {
  if (!localVideoSelection?.source_path) {
    els.localVideoSelection.textContent = ui("请选择一个本地视频。");
    return;
  }
  els.selectLocalVideoButton.disabled = true;
  els.startLocalConversionButton.disabled = true;
  show(els.localConversionProgress);
  hide(els.localConversionResult);
  setLocalConversionProgress(0, ui("正在准备本地转换..."));
  try {
    const result = await agentFetch("/api/local-conversions/iphone", {
      method: "POST",
      body: { source_path: localVideoSelection.source_path },
    });
    localConversionTaskId = result.task_id;
    startLocalConversionPolling();
  } catch (error) {
    setLocalConversionProgress(0, localizeUserMessage(error.message) || ui("转换失败，请稍后重试。"));
    els.selectLocalVideoButton.disabled = false;
    els.startLocalConversionButton.disabled = false;
  }
}

async function stopLocalConversion() {
  if (!localConversionTaskId) return;
  els.stopLocalConversionButton.disabled = true;
  setLocalConversionProgress(localConversionTask?.progress?.percent || 0, ui("正在停止转换..."));
  try {
    await agentFetch(`/api/tasks/${localConversionTaskId}/cancel`, { method: "POST" });
    startLocalConversionPolling();
  } catch (error) {
    setLocalConversionProgress(localConversionTask?.progress?.percent || 0, localizeUserMessage(error.message) || ui("停止失败，请稍后再试。"));
    els.stopLocalConversionButton.disabled = false;
  }
}

function startLocalConversionPolling() {
  if (localConversionPollTimer) clearInterval(localConversionPollTimer);
  pollLocalConversionTask();
  localConversionPollTimer = setInterval(pollLocalConversionTask, 900);
}

async function pollLocalConversionTask() {
  if (!localConversionTaskId) return;
  try {
    const task = await agentFetch(`/api/tasks/${localConversionTaskId}`);
    localConversionTask = task;
    renderLocalConversionTask(task);
    if (!["queued", "converting"].includes(task.status)) {
      clearInterval(localConversionPollTimer);
    }
  } catch (error) {
    setLocalConversionProgress(0, localizeUserMessage(error.message) || ui("任务状态读取失败。"));
    clearInterval(localConversionPollTimer);
    els.selectLocalVideoButton.disabled = false;
    els.startLocalConversionButton.disabled = false;
  }
}

function renderLocalConversionTask(task) {
  const isConverting = task.status === "converting";
  const progress = task.progress || {};
  show(els.localConversionProgress);
  setLocalConversionProgress(progress.percent || 0, localizeUserMessage(progress.text || task.error || task.message || ""));
  els.selectLocalVideoButton.disabled = isConverting;
  els.startLocalConversionButton.disabled = isConverting || !localVideoSelection?.source_path;
  els.stopLocalConversionButton.disabled = Boolean(task.cancel_requested);
  els.stopLocalConversionButton.classList.toggle("hidden", !isConverting);

  if (task.status === "completed") {
    const file = (task.result?.file_items || []).find((item) => item.iphone_ready) || null;
    if (file) renderLocalConversionResult(task.task_id, task.result.output_dir, file);
  }
}

function renderLocalConversionResult(taskId, outputDir, file) {
  show(els.localConversionResult);
  els.localConversionResult.innerHTML = `
    <div>
      <strong>${ui("已生成 iPhone 相册版")}</strong>
      <p>${escapeHtml(file.name || "")}</p>
      <span>${escapeHtml(outputDir || file.path || "")}</span>
    </div>
    <button class="secondary-button local-open-folder-button" type="button">${ui("打开所在文件夹")}</button>
  `;
  const button = els.localConversionResult.querySelector(".local-open-folder-button");
  if (button) {
    button.addEventListener("click", () =>
      openTaskFolder(taskId, button, (message) => setLocalConversionProgress(localConversionTask?.progress?.percent || 0, message)),
    );
  }
}

function setLocalConversionProgress(percent, text) {
  const normalized = Math.round(Math.max(0, Math.min(1, Number(percent) || 0)) * 100);
  els.localConversionProgressBar.style.width = `${normalized}%`;
  els.localConversionProgressText.textContent = localizeUserMessage(text) || "";
}

async function saveSettings() {
  els.saveSettingsButton.disabled = true;
  els.settingsMessage.textContent = ui("正在保存...");
  try {
    const settings = await agentFetch("/api/settings", {
      method: "PUT",
      body: { download_dir: els.downloadDirInput.value.trim() },
    });
    els.downloadDirInput.value = settings.download_dir || "";
    els.settingsMessage.textContent = ui("保存目录已更新。");
  } catch (error) {
    els.settingsMessage.textContent = localizeUserMessage(error.message) || ui("保存目录不可用。");
  } finally {
    els.saveSettingsButton.disabled = false;
  }
}

async function chooseDownloadFolder() {
  els.chooseFolderButton.disabled = true;
  els.saveSettingsButton.disabled = true;
  els.settingsMessage.textContent = ui("正在打开文件夹选择窗口...");
  try {
    const settings = await agentFetch("/api/settings/select-folder", {
      method: "POST",
    });
    els.downloadDirInput.value = settings.download_dir || els.downloadDirInput.value;
    els.settingsMessage.textContent = settings.cancelled ? ui("已取消选择。") : ui("保存目录已更新。");
  } catch (error) {
    els.settingsMessage.textContent = localizeUserMessage(error.message) || ui("无法打开文件夹选择窗口，请手动输入目录。");
  } finally {
    els.chooseFolderButton.disabled = false;
    els.saveSettingsButton.disabled = false;
  }
}

async function resolveContent() {
  const text = els.sourceInput.value.trim();
  if (!text) {
    setTaskMessage(ui("请先粘贴链接或分享文案。"));
    return;
  }
  resetResult();
  show(els.resultPanel);
  setProgress(0, ui("正在解析..."));
  els.resolveButton.disabled = true;
  els.downloadButton.disabled = true;
  try {
    const result = await agentFetch("/api/tasks/resolve", {
      method: "POST",
      body: { text },
    });
    currentTaskId = result.task_id;
    startPolling();
  } catch (error) {
    setTaskMessage(localizeUserMessage(error.message) || ui("解析失败。"));
    setProgress(0, ui("解析失败"));
    els.resolveButton.disabled = false;
  }
}

async function downloadContent() {
  if (!currentTask || !currentTask.info) return;
  els.downloadButton.disabled = true;
  show(els.stopDownloadButton);
  els.stopDownloadButton.disabled = false;
  setProgress(0, ui("正在准备下载..."));
  const formatKey = currentTask.info.media_type === "video" ? els.formatSelect.value || null : null;
  try {
    await agentFetch(`/api/tasks/${currentTask.task_id}/download`, {
      method: "POST",
      body: { format_key: formatKey },
    });
    startPolling();
  } catch (error) {
    setTaskMessage(localizeUserMessage(error.message) || ui("下载失败。"));
    els.downloadButton.disabled = false;
    hide(els.stopDownloadButton);
  }
}

async function stopDownload() {
  if (!currentTaskId) return;
  const isConverting = currentTask?.status === "converting" || currentTask?.stage === "convert";
  const stoppingText = isConverting ? ui("正在停止转换...") : ui("正在停止下载...");
  els.stopDownloadButton.disabled = true;
  setProgress(currentTask?.progress?.percent || 0, stoppingText);
  try {
    await agentFetch(`/api/tasks/${currentTaskId}/cancel`, {
      method: "POST",
    });
    startPolling();
  } catch (error) {
    setTaskMessage(localizeUserMessage(error.message) || ui("停止失败，请稍后再试。"));
    els.stopDownloadButton.disabled = false;
  }
}

async function openDownloadedFolder(button) {
  if (!currentTaskId) return;
  await openTaskFolder(currentTaskId, button, setTaskMessage);
}

async function openTaskFolder(taskId, button, reportError = setTaskMessage) {
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = ui("正在打开...");
  try {
    await agentFetch(`/api/tasks/${taskId}/open-folder`, {
      method: "POST",
    });
    button.textContent = ui("已打开");
    setTimeout(() => {
      button.textContent = originalText;
      button.disabled = false;
    }, 1200);
  } catch (error) {
    button.textContent = originalText;
    button.disabled = false;
    reportError(localizeUserMessage(error.message) || ui("无法打开文件夹。"));
  }
}

async function convertForIphone(fileIndex, button) {
  if (!currentTaskId) return;
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = ui("正在转换...");
  stopRemoteVideoPreview();
  setTaskMessage(ui("已暂停在线视频预览，转换仅在本机处理。"));
  setProgress(0, ui("正在本机转换为 iPhone 相册格式..."));
  try {
    await agentFetch(`/api/tasks/${currentTaskId}/convert/iphone`, {
      method: "POST",
      body: { file_index: Number(fileIndex || 0) },
    });
    startPolling();
  } catch (error) {
    button.textContent = originalText;
    button.disabled = false;
    setTaskMessage(localizeUserMessage(error.message) || ui("转换失败，请稍后重试。"));
  }
}

function stopRemoteVideoPreview() {
  const video = els.previewArea.querySelector("video");
  if (!video) return;
  video.pause();
  video.removeAttribute("src");
  video.load();
  els.previewArea.replaceChildren();
}

async function clearRecords() {
  els.clearRecordsButton.disabled = true;
  setTaskMessage(ui("正在清除记录..."));
  try {
    await agentFetch("/api/tasks/history", { method: "DELETE" });
    resetResult();
    hide(els.resultPanel);
    els.sourceInput.value = "";
    els.resolveButton.disabled = false;
    els.downloadButton.disabled = true;
    setTaskMessage(ui("记录已清除。"));
  } catch (error) {
    const message = localizeUserMessage(error.message);
    setTaskMessage(message && message !== ui("请求失败。") ? message : ui("清除记录失败，请更新本地助手后再试。"));
  } finally {
    els.clearRecordsButton.disabled = false;
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTask();
  pollTimer = setInterval(pollTask, 900);
}

async function pollTask() {
  if (!currentTaskId) return;
  try {
    const task = await agentFetch(`/api/tasks/${currentTaskId}`);
    currentTask = task;
    renderTask(task);
    if (!["queued", "running", "downloading", "converting"].includes(task.status)) {
      clearInterval(pollTimer);
    }
  } catch (error) {
    setTaskMessage(localizeUserMessage(error.message) || ui("任务状态读取失败。"));
    clearInterval(pollTimer);
    els.resolveButton.disabled = false;
  }
}

function renderTask(task) {
  setTaskMessage(localizeUserMessage(task.error || task.message || ""));
  const isActiveDownload = task.stage === "download" && ["queued", "downloading"].includes(task.status);
  const isConverting = task.status === "converting";
  const isActiveWork = isActiveDownload || isConverting;
  updateClearRecordsButton(task, isActiveDownload || isConverting);
  if (task.info) {
    renderInfo(task.info);
    els.resolveButton.disabled = false;
    els.downloadButton.disabled = isActiveDownload || isConverting;
  }
  els.stopDownloadButton.disabled = Boolean(task.cancel_requested);
  els.stopDownloadButton.textContent = isConverting ? ui("停止转换") : ui("停止下载");
  els.stopDownloadButton.classList.toggle("hidden", !isActiveWork);
  if (task.progress && typeof task.progress.percent === "number") {
    setProgress(task.progress.percent, localizeUserMessage(task.progress.text || task.message || ""));
  }
  if (task.status === "resolved") {
    setProgress(0, ui("解析完成，可以下载。"));
  }
  if (task.status === "failed") {
    setProgress(0, localizeUserMessage(task.error) || ui("操作失败。"));
    els.resolveButton.disabled = false;
    els.downloadButton.disabled = !task.info;
    hide(els.stopDownloadButton);
    if (!task.info) {
      renderResolveError(localizeUserMessage(task.error) || ui("解析失败，请重新复制链接后再试。"));
    }
  }
  if (task.status === "cancelled") {
    const stoppedText = task.stage === "convert" ? ui("转换已停止。") : ui("下载已停止。");
    setProgress(task.progress?.percent || 0, stoppedText);
    els.resolveButton.disabled = false;
    els.downloadButton.disabled = !task.info;
    hide(els.stopDownloadButton);
  }
  if (isConverting && task.result) {
    renderResult(task.result);
  }
  if (task.status === "completed") {
    setProgress(1, ui("下载完成。"));
    els.downloadButton.disabled = false;
    hide(els.stopDownloadButton);
    renderResult(task.result);
  }
}

function updateClearRecordsButton(task, isActiveDownload) {
  const hasRecord = Boolean(task?.info || task?.result || ["failed", "cancelled", "resolved", "completed"].includes(task?.status));
  els.clearRecordsButton.classList.toggle("hidden", !hasRecord || Boolean(isActiveDownload));
  if (!isActiveDownload) {
    els.clearRecordsButton.disabled = false;
  }
}

function renderResolveError(message) {
  els.previewArea.innerHTML = `<div class="error-state">${escapeHtml(message)}</div>`;
  els.mediaTitle.textContent = ui("未解析到内容");
  els.mediaAuthor.textContent = ui("无");
  els.mediaType.textContent = ui("解析失败");
  els.sourceLink.removeAttribute("href");
  els.sourceLink.classList.add("hidden");
  hide(els.formatDetails);
}

function renderInfo(info) {
  show(els.resultPanel);
  els.mediaTitle.textContent = info.title || ui("未命名内容");
  els.mediaAuthor.textContent = info.uploader || info.channel || ui("未知作者");
  els.mediaType.textContent = info.media_type === "image" ? imageCountText(info.image_count || 0) : formatDuration(info.duration);
  els.sourceLink.href = info.webpage_url || "#";
  els.sourceLink.classList.toggle("hidden", !info.webpage_url);
  renderPreview(info);
  renderFormats(info);
  els.downloadButton.textContent = info.media_type === "image" ? ui("下载全部图片") : ui("下载最佳 MP4");
  els.stopDownloadButton.textContent = ui("停止下载");
}

function renderPreview(info) {
  els.previewArea.innerHTML = "";
  if (info.media_type === "image" && info.image_previews && info.image_previews.length) {
    if (info.image_previews.length === 1) {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.alt = info.title || ui("图片预览");
      img.src = withToken(info.image_previews[0]);
      els.previewArea.appendChild(img);
      return;
    }
    const grid = document.createElement("div");
    grid.className = "image-grid";
    info.image_previews.slice(0, 9).forEach((url) => {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.alt = info.title || ui("图片预览");
      img.src = withToken(url);
      grid.appendChild(img);
    });
    els.previewArea.appendChild(grid);
    return;
  }
  if (info.preview_url && info.media_type === "video") {
    const video = document.createElement("video");
    video.controls = true;
    video.preload = "metadata";
    video.src = withToken(info.preview_url);
    if (info.thumbnail) video.poster = info.thumbnail;
    els.previewArea.appendChild(video);
    return;
  }
  if (info.thumbnail) {
    const img = document.createElement("img");
    img.alt = info.title || ui("封面");
    img.src = info.thumbnail;
    els.previewArea.appendChild(img);
  }
}

function renderFormats(info) {
  els.formatSelect.innerHTML = "";
  els.formatTable.innerHTML = "";
  if (info.media_type !== "video" || !info.formats || !info.formats.length) {
    hide(els.formatDetails);
    return;
  }
  show(els.formatDetails);
  info.formats.forEach((format) => {
    const option = document.createElement("option");
    option.value = format.key;
    option.textContent = format.label;
    els.formatSelect.appendChild(option);
  });
  els.formatTable.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>${ui("分辨率")}</th>
          <th>${ui("格式")}</th>
          <th>${ui("大小")}</th>
          <th>${ui("视频")}</th>
          <th>${ui("音频")}</th>
          <th>${ui("说明")}</th>
        </tr>
      </thead>
      <tbody>
        ${info.formats
          .map(
            (format) => `
              <tr>
                <td>${escapeHtml(format.resolution)}</td>
                <td>${escapeHtml(format.ext)}</td>
                <td>${escapeHtml(format.filesize)}</td>
                <td>${escapeHtml(format.video_codec)}</td>
                <td>${escapeHtml(format.audio_codec)}</td>
                <td>${format.needs_merge ? ui("需要合并") : ui("单文件")}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderResult(result) {
  if (!result) return;
  show(els.downloadResult);
  const fileItems = result.file_items || [];
  const files = fileItems.length
    ? fileItems
        .map(
          (file, index) => {
            const fileIndex = Number.isInteger(file.index) ? file.index : index;
            const isBusy = currentTask?.status === "converting";
            const convertButton = file.can_convert_iphone
              ? `<button class="convert-iphone-button" type="button" data-file-index="${fileIndex}" ${isBusy ? "disabled" : ""}>${ui("转为 iPhone 相册版")}</button>`
              : "";
            const readyBadge = file.iphone_ready ? `<span class="iphone-ready-badge">${ui("iPhone 相册版")}</span>` : "";
            return `
            <li class="result-file-item">
              <div class="result-file-text">
                <strong class="result-file-name">${escapeHtml(file.name || ui("已下载文件"))}${readyBadge}</strong>
                <span class="result-file-path">${escapeHtml(file.path || "")}</span>
              </div>
              <div class="result-file-actions">
                ${convertButton}
                <a class="mobile-save-button" href="${escapeHtml(file.url || "#")}" download="${escapeHtml(file.name || "")}">${ui("保存到手机")}</a>
              </div>
            </li>
          `;
          },
        )
        .join("")
    : (result.files || [])
        .map(
          (file) => `
            <li class="result-file-item">
              <div class="result-file-text">
                <strong class="result-file-name">${escapeHtml(file.split("/").pop() || ui("已下载文件"))}</strong>
                <span class="result-file-path">${escapeHtml(file)}</span>
              </div>
            </li>
          `,
        )
        .join("");
  els.downloadResult.innerHTML = `
    <div class="result-head">
      <div>
        <strong>${ui("文件已保存")}</strong>
        <p>${escapeHtml(result.output_dir || "")}</p>
      </div>
      <button class="secondary-button open-folder-button" type="button">${ui("打开所在文件夹")}</button>
    </div>
    <ul>${files}</ul>
  `;
  const button = els.downloadResult.querySelector(".open-folder-button");
  if (button) {
    button.addEventListener("click", () => openDownloadedFolder(button));
  }
  els.downloadResult.querySelectorAll(".convert-iphone-button").forEach((convertButton) => {
    convertButton.addEventListener("click", () => convertForIphone(convertButton.dataset.fileIndex, convertButton));
  });
}

function resetResult() {
  currentTask = null;
  currentTaskId = "";
  if (pollTimer) clearInterval(pollTimer);
  hide(els.downloadResult);
  hide(els.stopDownloadButton);
  hide(els.clearRecordsButton);
  hide(els.formatDetails);
  els.stopDownloadButton.disabled = false;
  els.clearRecordsButton.disabled = false;
  els.downloadButton.disabled = true;
  els.downloadResult.innerHTML = "";
  els.previewArea.innerHTML = "";
  els.mediaTitle.textContent = "";
  els.mediaAuthor.textContent = "";
  els.mediaType.textContent = "";
  els.sourceLink.removeAttribute("href");
  els.sourceLink.classList.add("hidden");
  setTaskMessage("");
  setProgress(0, ui("等待解析"));
}

async function agentFetch(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  const useAuth = options.auth !== false;
  if (useAuth && token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${AGENT_BASE}${path}`, {
    method: options.method || "GET",
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch (_error) {
    payload = null;
  }
  if (!response.ok) {
    if (response.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      token = "";
    }
    throw new Error(localizeUserMessage(payload?.detail) || ui("请求失败。"));
  }
  return payload;
}

function withToken(url) {
  return url.replace("__TOKEN__", encodeURIComponent(token));
}

function setConnection(kind, text) {
  els.connectionBadge.textContent = localizeUserMessage(text);
  els.connectionBadge.className = `status-badge status-${kind}`;
}

function setTaskMessage(message) {
  els.taskMessage.textContent = localizeUserMessage(message) || "";
}

function setProgress(percent, text) {
  els.progressBar.style.width = `${Math.round(Math.max(0, Math.min(1, percent)) * 100)}%`;
  els.progressText.textContent = localizeUserMessage(text) || "";
}

function showPairError(message) {
  els.pairError.textContent = localizeUserMessage(message);
  show(els.pairError);
}

function hidePairError() {
  els.pairError.textContent = "";
  hide(els.pairError);
}

function show(element) {
  element.classList.remove("hidden");
}

function hide(element) {
  element.classList.add("hidden");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function imageCountText(count) {
  const value = Number(count || 0);
  return currentLang === "en" ? `${value} image${value === 1 ? "" : "s"}` : `${value} 张图片`;
}

function formatDuration(seconds) {
  if (!seconds) return ui("视频");
  const value = Number(seconds);
  if (!Number.isFinite(value)) return ui("视频");
  const mins = Math.floor(value / 60);
  const secs = Math.floor(value % 60).toString().padStart(2, "0");
  const hours = Math.floor(mins / 60);
  const remMins = (mins % 60).toString().padStart(2, "0");
  return hours ? `${hours}:${remMins}:${secs}` : `${mins}:${secs}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
