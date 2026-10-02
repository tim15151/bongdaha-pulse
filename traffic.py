import os
import random
import time
import urllib.parse

from playwright.sync_api import sync_playwright


SITE = "https://bongdaha.com"
NEWS_PAGE = f"{SITE}/tin-bongda"
ARTICLE_PREFIX = "/tin-bongda/"

PROXY_HOST = os.environ.get("PROXY_HOST", "")
PROXY_USER = os.environ.get("PROXY_USER", "")
PROXY_PASS = os.environ.get("PROXY_PASS", "")

PROXY_ENDPOINT_MIN = 1
PROXY_ENDPOINT_MAX = 2393

VISITS_PER_RUN = int(
    os.getenv("VISITS_PER_RUN")
    or random.randint(7, 12)
)

# Chặn image, media, font để tiết kiệm bandwidth proxy.
# KHÔNG chặn stylesheet (CSS) để trang tính toán layout và scroll event chuẩn GA4.
BLOCK_RESOURCE_TYPES = {
    "image",
    "media",
    "font",
}

GA_HOST_SUFFIX = "google-analytics.com"

# Pool thiết bị thật (User-Agent + Viewport chuẩn)
DEVICE_PROFILES = [
    {
        "name": "Desktop Win11 Chrome",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "viewport": {"width": 1920, "height": 1080},
        "device_scale_factor": 1,
        "is_mobile": False,
        "has_touch": False,
    },
    {
        "name": "Laptop Win10 Chrome",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "viewport": {"width": 1366, "height": 768},
        "device_scale_factor": 1,
        "is_mobile": False,
        "has_touch": False,
    },
    {
        "name": "iPhone 16 Pro Safari",
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
        "viewport": {"width": 393, "height": 852},
        "device_scale_factor": 3,
        "is_mobile": True,
        "has_touch": True,
    },
    {
        "name": "Samsung Galaxy S24 Android",
        "user_agent": "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Mobile Safari/537.36",
        "viewport": {"width": 412, "height": 915},
        "device_scale_factor": 2.625,
        "is_mobile": True,
        "has_touch": True,
    },
    {
        "name": "Xiaomi 14 Android",
        "user_agent": "Mozilla/5.0 (Linux; Android 14; 23127PN0CG) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Mobile Safari/537.36",
        "viewport": {"width": 393, "height": 873},
        "device_scale_factor": 2.75,
        "is_mobile": True,
        "has_touch": True,
    },
]

# Danh sách nguồn truy cập (Organic Search, Social, Direct)
EXTERNAL_REFERRERS = [
    "https://www.google.com.vn/",
    "https://www.google.com/",
    "https://m.facebook.com/",
    "https://l.facebook.com/",
    None,  # Direct
]

# Script xóa dấu vết automation (Stealth) chạy trước khi trang nạp JS
STEALTH_INIT_SCRIPT = """
// 1. Xóa cờ automation webdriver
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
    configurable: true
});

// 2. Giả lập chrome runtime
window.chrome = {
    app: {
        isInstalled: false,
        InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
        RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
    },
    runtime: {
        OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
        OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
        PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
        PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
        PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
        RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }
    },
    csi: function(){},
    loadTimes: function(){}
};

// 3. Giả lập plugins (tránh mảng rỗng đặc trưng của bot)
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
        { name: 'Chromium PDF Viewer', filename: 'internal-nacl-plugin', description: '' }
    ],
    configurable: true
});

// 4. Chuẩn hóa danh sách ngôn ngữ Việt Nam
Object.defineProperty(navigator, 'languages', {
    get: () => ['vi-VN', 'vi', 'en-US', 'en'],
    configurable: true
});

// 5. Spoof permissions query
if (window.navigator.permissions) {
    const origPermissionsQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            origPermissionsQuery(parameters)
    );
}
"""


def log(msg):
    print(msg, flush=True)


def is_ga_collect(url):
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception:
        return False

    host = parsed.netloc.lower().split(":")[0]
    path = parsed.path.lower()

    return (
        host.endswith(GA_HOST_SUFFIX)
        and (
            "/g/collect" in path
            or path.endswith("/collect")
        )
    )


def normalize_article_url(href):
    if not href:
        return None

    try:
        absolute = urllib.parse.urljoin(SITE + "/", href)
        parsed = urllib.parse.urlsplit(absolute)
    except Exception:
        return None

    if parsed.scheme not in {"http", "https"}:
        return None

    if parsed.netloc.lower() != "bongdaha.com":
        return None

    path = parsed.path or "/"

    if not path.startswith(ARTICLE_PREFIX):
        return None

    rest = path[len(ARTICLE_PREFIX):].strip("/")
    if not rest:
        return None

    lowered = path.lower()
    blocked = (
        "/feed",
        "/page/",
        "/author/",
        "/tag/",
        "/wp-",
    )

    if any(x in lowered for x in blocked):
        return None

    return urllib.parse.urlunsplit(
        (
            "https",
            "bongdaha.com",
            path,
            "",
            "",
        )
    )


def collect_article_urls(page):
    hrefs = page.eval_on_selector_all(
        "a[href]",
        "els => els.map(a => a.getAttribute('href'))",
    )

    urls = []
    for href in hrefs:
        url = normalize_article_url(href)
        if url:
            urls.append(url)

    return list(dict.fromkeys(urls))


def wait_and_collect_articles(page):
    """
    /tin-bongda render bài bằng JS.
    Thử vài vòng + scroll nhẹ trước khi kết luận ARTICLE_POOL=0.
    """
    for attempt in range(1, 5):
        urls = collect_article_urls(page)
        if urls:
            return urls

        log(f"Chờ danh sách bài... attempt {attempt}/4")
        try:
            page.evaluate(
                "window.scrollTo(0, Math.max(document.body.scrollHeight, 1200))"
            )
        except Exception:
            pass

        page.wait_for_timeout(2500)

    return []


def simulate_human_reading(page, is_mobile=False):
    """
    Mô phỏng hành vi người đọc thật:
    - Cuộn từ từ xuống các mốc (25%, 50%, 75%, 90%+)
    - GA4 kích hoạt event 'scroll' (mốc 90% mặc định)
    - Di chuyển chuột tự nhiên trên Desktop
    - Giữ chân trên trang 20s - 32s (tạo Engaged Session chuẩn GA4)
    """
    total_height = 2000
    try:
        total_height = page.evaluate("() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight, 1600)")
    except Exception:
        pass

    # Chờ 2 - 3s đọc sapo/tiêu đề
    page.wait_for_timeout(random.randint(2000, 3500))

    checkpoints = [0.25, 0.50, 0.75, 0.92]
    for pct in checkpoints:
        target_y = int(total_height * pct) + random.randint(-40, 40)
        try:
            page.evaluate(f"window.scrollTo({{top: {target_y}, behavior: 'smooth'}})")
        except Exception:
            pass

        if not is_mobile:
            try:
                page.mouse.move(random.randint(150, 650), random.randint(200, 600))
            except Exception:
                pass

        # Thời gian đọc giữa các đoạn (4s - 7s)
        dwell_ms = random.randint(4000, 7000)
        page.wait_for_timeout(dwell_ms)


def run_visit(browser, index, endpoint_id, cached_articles=None):
    proxy_user = f"{PROXY_USER}-VN-{endpoint_id}"
    context = None
    device = random.choice(DEVICE_PROFILES)

    try:
        ctx_args = {
            "locale": "vi-VN",
            "timezone_id": "Asia/Ho_Chi_Minh",
            "user_agent": device["user_agent"],
            "viewport": device["viewport"],
            "device_scale_factor": device["device_scale_factor"],
            "is_mobile": device["is_mobile"],
            "has_touch": device["has_touch"],
        }
        if PROXY_HOST:
            ctx_args["proxy"] = {
                "server": f"http://{PROXY_HOST}",
                "username": proxy_user,
                "password": PROXY_PASS,
            }

        context = browser.new_context(**ctx_args)
        # Bơm script chống phát hiện tự động
        context.add_init_script(STEALTH_INIT_SCRIPT)

        page = context.new_page()

        blocked = 0
        ga_hits = 0

        def watch_request(request):
            nonlocal ga_hits
            if is_ga_collect(request.url):
                ga_hits += 1

        def intercept(route):
            nonlocal blocked
            req = route.request

            if req.resource_type in BLOCK_RESOURCE_TYPES:
                blocked += 1
                route.abort()
                return

            # Không gắn bất kỳ custom header nhận diện lộ liễu nào
            route.continue_()

        page.on("request", watch_request)
        page.route("**/*", intercept)

        log("")
        log("=" * 72)
        log(f"[{index}/{VISITS_PER_RUN}] Thiết bị: {device['name']} | Proxy: VN-{endpoint_id}")

        article_urls = cached_articles or []
        home_status = "N/A"
        news_status = "N/A"

        # Nếu chưa có bài hoặc ngẫu nhiên 50% chạy theo funnel Home -> News -> Article
        run_full_funnel = (not article_urls) or (random.random() < 0.50)

        if run_full_funnel:
            # STEP 1: vào homepage
            home_response = page.goto(
                SITE + "/",
                wait_until="domcontentloaded",
                timeout=45000,
            )
            home_status = home_response.status if home_response else "NO_RESPONSE"
            page.wait_for_timeout(random.randint(1800, 3000))

            # STEP 2: lướt sang TIN THỂ THAO
            news_response = page.goto(
                NEWS_PAGE,
                wait_until="domcontentloaded",
                timeout=45000,
            )
            news_status = news_response.status if news_response else "NO_RESPONSE"
            page.wait_for_timeout(2000)

            article_urls = wait_and_collect_articles(page)

        if not article_urls:
            log(
                f"HOME={home_status} | "
                f"NEWS={news_status} | "
                f"ARTICLE_POOL=0 | "
                f"GA_REQ={ga_hits} | "
                f"blocked={blocked}"
            )
            return {
                "http_ok": False,
                "ga_hit": ga_hits > 0,
                "article_urls": [],
            }

        # STEP 3: Vào bài viết
        article_url = random.choice(article_urls)
        chosen_referrer = None

        if not run_full_funnel:
            # Mô phỏng nguồn từ Google Tìm Kiếm hoặc Mạng xã hội
            chosen_referrer = random.choice(EXTERNAL_REFERRERS)
            log(f"Nguồn truy cập (Referer): {chosen_referrer or 'Direct'}")

        goto_kwargs = {
            "wait_until": "domcontentloaded",
            "timeout": 45000,
        }
        if chosen_referrer:
            goto_kwargs["referer"] = chosen_referrer

        article_response = page.goto(article_url, **goto_kwargs)
        article_status = article_response.status if article_response else "NO_RESPONSE"

        # Mô phỏng hành vi đọc thật (cuộn, dừng đọc, kích hoạt scroll GA4)
        simulate_human_reading(page, is_mobile=device["is_mobile"])

        ga_status = "YES" if ga_hits > 0 else "NO"

        log(f"ARTICLE_POOL={len(article_urls)}")
        log(f"ARTICLE={article_url}")
        log(
            f"HOME={home_status} | "
            f"NEWS={news_status} | "
            f"ARTICLE_HTTP={article_status} | "
            f"GA_HIT={ga_status} | "
            f"GA_REQ={ga_hits} | "
            f"blocked={blocked}"
        )

        http_ok = isinstance(article_status, int) and article_status < 400

        return {
            "http_ok": http_ok,
            "ga_hit": ga_hits > 0,
            "article_urls": article_urls,
        }

    except Exception as exc:
        log(f"FAIL | VN-{endpoint_id} | {type(exc).__name__}: {exc}")
        return {
            "http_ok": False,
            "ga_hit": False,
            "article_urls": cached_articles or [],
        }

    finally:
        if context:
            try:
                context.close()
            except Exception:
                pass


def main():
    if VISITS_PER_RUN < 1:
        raise ValueError("VISITS_PER_RUN phải >= 1")

    endpoint_count = PROXY_ENDPOINT_MAX - PROXY_ENDPOINT_MIN + 1
    if VISITS_PER_RUN <= endpoint_count:
        endpoints = random.sample(
            range(PROXY_ENDPOINT_MIN, PROXY_ENDPOINT_MAX + 1),
            VISITS_PER_RUN,
        )
    else:
        endpoints = [
            random.randint(PROXY_ENDPOINT_MIN, PROXY_ENDPOINT_MAX)
            for _ in range(VISITS_PER_RUN)
        ]

    log("")
    log("========================================================================")
    log("BONGDAHA PULSE V2 - STEALTH & REALISTIC HUMAN VISITATION")
    log(f"Site: {SITE}")
    log(f"News page: {NEWS_PAGE}")
    log(f"Article prefix: {ARTICLE_PREFIX}")
    log(f"Visits/run: {VISITS_PER_RUN}")
    log(f"Proxy pool: VN-{PROXY_ENDPOINT_MIN} → VN-{PROXY_ENDPOINT_MAX}")
    log("========================================================================")

    http_success = 0
    ga_success = 0
    discovered_articles = []

    with sync_playwright() as p:
        # Chromium launch arguments chống flag automation
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )

        try:
            for i, endpoint_id in enumerate(endpoints, start=1):
                result = run_visit(
                    browser,
                    i,
                    endpoint_id,
                    cached_articles=discovered_articles,
                )

                if result.get("article_urls"):
                    discovered_articles = result["article_urls"]

                # Retry nhẹ 1 lần nếu kết nối lỗi
                if not result["http_ok"]:
                    retry_endpoint = random.randint(PROXY_ENDPOINT_MIN, PROXY_ENDPOINT_MAX)
                    log(f"Retry visit {i} với VN-{retry_endpoint}")
                    result = run_visit(
                        browser,
                        i,
                        retry_endpoint,
                        cached_articles=discovered_articles,
                    )
                    if result.get("article_urls"):
                        discovered_articles = result["article_urls"]

                if result["http_ok"]:
                    http_success += 1

                if result["ga_hit"]:
                    ga_success += 1

                if i < VISITS_PER_RUN:
                    delay = random.randint(4, 9)
                    log(f"Nghỉ giữa các lượt: {delay}s...")
                    time.sleep(delay)

        finally:
            browser.close()

    log("")
    log("=" * 72)
    log(
        f"DONE | "
        f"HTTP_OK={http_success}/{VISITS_PER_RUN} | "
        f"GA_HIT={ga_success}/{VISITS_PER_RUN}"
    )

    if http_success == 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
