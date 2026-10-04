import ast
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch(headless=True)
        except playwright.Error as error:
            if "Executable doesn't exist" in str(error):
                pytest.skip("Playwright Chromium is not installed")
            raise
        yield browser
        browser.close()


def task_fixture(status="downloading", local=False):
    info = {"title": "Public-domain test fixture", "media_type": "video", "duration": 1,
            "preview_url": "/fixture-media.mp4", "webpage_url": "https://example.test/fixture",
            "formats": [{"key": key, "label": key, "ext": "mp4"} for key in ("first", "second")]}
    return {"task_id": "fixture", "status": status, "stage": "convert" if local else "download",
            "info": None if local else info, "local_conversion": local,
            "progress": {"percent": 0.4, "text": "Fixture progress"},
            "result": {"output_dir": "Fixture folder", "files": [], "file_items": []}}


def open_fixture(browser, task, width):
    context = browser.new_context(viewport={"width": width, "height": 900})
    context.add_init_script("localStorage.setItem('videoDownloaderLegalAccepted:v2', '1'); localStorage.setItem('videoDownloaderAgentToken', 'fixture-only'); window.VIDEO_DOWNLOADER_AGENT_BASE = location.origin;")
    requests = []
    errors = []
    state = {"task": task, "fail_next": False}

    def route(route):
        path = urlsplit(route.request.url).path
        requests.append((route.request.method, path))
        if path in {"/", "/app.js", "/styles.css"}:
            file = ROOT / "web" / ("index.html" if path == "/" else path.lstrip("/"))
            route.fulfill(path=str(file))
            return
        if path == "/api/health":
            data = {"ok": True, "version": "0.1.52", "authenticated": True, "build_id": "fixture"}
        elif path == "/api/settings":
            data = {"download_dir": "Fixture folder"}
        elif path == "/api/update/check":
            data = {"current_version": "0.1.52", "latest_version": "0.1.52", "update_available": False}
        elif path == "/api/tasks/latest-result":
            data = {"task": state["task"]}
        elif path == "/api/tasks/fixture":
            if state["fail_next"]:
                state["fail_next"] = False
                route.fulfill(status=503, json={"detail": "Fixture temporary outage"})
                return
            data = state["task"]
        elif path == "/api/tasks/fixture/cancel":
            state["task"]["status"] = "cancelled"
            data = state["task"]
        elif path == "/api/tasks/history":
            data = {"cleared": 1}
            state["task"] = None
        elif path == "/fixture-media.mp4":
            route.fulfill(content_type="video/mp4", body=b"fixture")
            return
        else:
            route.fulfill(status=404, body="fixture route not found")
            return
        route.fulfill(json=data)

    context.route("**/*", route)
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://127.0.0.1:17890/")
    page.wait_for_function("document.querySelector('#mainPanel') && !document.querySelector('#mainPanel').classList.contains('hidden')")
    return context, page, state, requests, errors


@pytest.mark.parametrize("width", [390, 1280])
def test_polling_preserves_preview_and_format_and_stop(browser, width):
    context, page, state, requests, errors = open_fixture(browser, task_fixture(), width)
    try:
        page.wait_for_selector("#previewArea video")
        page.evaluate("document.querySelector('#previewArea video').dataset.fixtureIdentity = 'original'; document.querySelector('#formatSelect').value = 'second'")
        state["fail_next"] = True
        page.wait_for_timeout(2200)
        assert page.locator("#previewArea video").get_attribute("data-fixture-identity") == "original"
        assert page.locator("#formatSelect").input_value() == "second"
        assert sum(path == "/fixture-media.mp4" for _, path in requests) == 1
        state["task"].update(status="converting", stage="convert")
        page.wait_for_function("document.querySelector('#stopDownloadButton').textContent.includes('停止转换')")
        assert page.locator("#previewArea video").count() == 0
        page.wait_for_timeout(1000)
        assert sum(path == "/fixture-media.mp4" for _, path in requests) == 1
        page.locator("#stopDownloadButton").click()
        page.wait_for_function("currentTask?.status === 'cancelled'")
        page.locator("#clearRecordsButton").click()
        page.wait_for_function("document.querySelector('#resultPanel').classList.contains('hidden')")
        assert ("DELETE", "/api/tasks/history") in requests
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors
    finally:
        context.close()


def test_refresh_restores_local_conversion_stop_button(browser):
    context, page, state, requests, errors = open_fixture(browser, task_fixture("converting", local=True), 390)
    try:
        page.wait_for_selector("#stopLocalConversionButton")
        page.reload()
        page.wait_for_selector("#stopLocalConversionButton")
        page.locator("#stopLocalConversionButton").click()
        page.wait_for_function("localConversionTask?.status === 'cancelled'")
        assert ("POST", "/api/tasks/fixture/cancel") in requests
        assert not any(path == "/fixture-media.mp4" for _, path in requests)
        assert not errors
    finally:
        context.close()


def test_instagram_structured_post_ignores_recommendations(browser):
    source = ast.parse((ROOT / "video_downloader/browser_session.py").read_text())
    expression = next(node.args[0].value for node in ast.walk(source)
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                      and node.func.attr == "evaluate" and isinstance(node.args[0], ast.Constant))
    image = lambda name: {"media_type": 1, "image_versions2": {"candidates": [{"url": f"https://example.test/{name}.jpg", "width": 640, "height": 640}]}}
    partial = {"code": "fixture", "media_type": 8, "carousel_media": [image("one")]}
    complete = {"code": "fixture", "media_type": 8, "carousel_media_count": 3,
                "carousel_media": [image("one"), image("two"), image("three")]}
    recommendation = {"code": "unrelated", "media_type": 2, "image_versions2": image("recommendation")["image_versions2"]}
    page = browser.new_page()
    page.route("**/*", lambda route: route.fulfill(content_type="text/html", body="<body></body>"))
    page.goto("https://www.instagram.com/p/fixture/")
    try:
        page.set_content(f'<script type="application/json">{json.dumps(partial)}</script><script type="application/json">{json.dumps([recommendation, complete])}</script>')
        data = page.evaluate(expression)
        assert data["postImageUrls"] == [f"https://example.test/{name}.jpg" for name in ("one", "two", "three")]
        assert data["postMediaType"] == 8
        assert not data["postHasVideo"]
        assert not data["postIncomplete"]
        complete["carousel_media"][1]["media_type"] = 2
        complete["carousel_media_count"] = 4
        page.set_content(f'<script type="application/json">{json.dumps(complete)}</script>')
        mixed = page.evaluate(expression)
        assert mixed["postHasVideo"]
        assert mixed["postIncomplete"]
        assert "https://example.test/two.jpg" not in mixed["postImageUrls"]
    finally:
        page.close()


def test_douyin_gallery_images_are_scoped_to_slides(browser):
    source = ast.parse((ROOT / "video_downloader/browser_session.py").read_text())
    expression = next(node.args[0].value for node in ast.walk(source)
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                      and node.func.attr == "evaluate" and isinstance(node.args[0], ast.Constant))
    page = browser.new_page()
    page.route("**/*", lambda route: route.fulfill(content_type="text/html", body="<body></body>"))
    page.goto("https://www.douyin.com/note/7676089518466771683")
    try:
        page.set_content('''
            <div class="dySwiperSlide"><img src="https://example.test/one.jpg"></div>
            <div class="dySwiperSlide"><img src="https://example.test/two.jpg"></div>
            <img src="https://example.test/recommended.jpg">
        ''')
        data = page.evaluate(expression)
        assert data["douyinImageUrls"] == [
            "https://example.test/one.jpg", "https://example.test/two.jpg",
        ]
    finally:
        page.close()


def test_tiktok_photo_images_ignore_duplicate_slides_and_recommendations(browser):
    source = ast.parse((ROOT / "video_downloader/browser_session.py").read_text())
    expression = next(node.args[0].value for node in ast.walk(source)
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                      and node.func.attr == "evaluate" and isinstance(node.args[0], ast.Constant))
    page = browser.new_page()
    page.route("**/*", lambda route: route.fulfill(content_type="text/html", body="<body></body>"))
    page.goto("https://www.tiktok.com/@ryanair/photo/7579672560401452311")
    try:
        page.set_content('''
            <div class="swiper-slide swiper-slide-duplicate"><img class="ImgPhotoSlide" src="https://example.test/one.jpg"></div>
            <div class="swiper-slide"><img class="ImgPhotoSlide" src="https://example.test/one.jpg"></div>
            <div class="swiper-slide"><img class="ImgPhotoSlide" src="https://example.test/two.jpg"></div>
            <img src="https://example.test/recommended.jpg">
        ''')
        data = page.evaluate(expression)
        assert data["tiktokImageUrls"] == [
            "https://example.test/one.jpg", "https://example.test/two.jpg",
        ]
    finally:
        page.close()
