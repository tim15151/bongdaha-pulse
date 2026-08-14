import os
import random
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from playwright.sync_api import sync_playwright

SITE = "https://bongdaha.com"
PROXY_HOST = os.environ["PROXY_HOST"]
PROXY_USER = os.environ["PROXY_USER"]
PROXY_PASS = os.environ["PROXY_PASS"]

# Pool endpoint VN đã export: VN-1 ... VN-2393
PROXY_ENDPOINT_MIN = 1
PROXY_ENDPOINT_MAX = 2393

# Scheduled run mặc định: 7-12 view.
# Manual GitHub Actions test có thể override xuống 1-3 view.
VISITS_PER_RUN = int(
    os.getenv("VISITS_PER_RUN")
    or random.randint(7, 12)
)

BLOCK_RESOURCE_TYPES = {
    "image",
    "media",
    "font",
    "stylesheet",
}

GA_HOST_SUFFIX = "google-analytics.com"


def log(msg):
    print(msg, flush=True)


def read_xml(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "BongDaHa-Pulse/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return response.read()


def extract_locs(xml_data):
    root = ET.fromstring(xml_data)
    out = []
    for node in root.iter():
        if node.tag.endswith("loc") and node.text:
            out.append(node.text.strip())
    return out


def is_valid_site_url(url):
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.netloc.lower() != "bongdaha.com":
        return False
    path = parsed.path.lower()
    blocked_paths = (
        "/wp-admin",
        "/wp-login",
        "/feed",
        "/author/",
        "/tag/",
    )
    return not any(x in path for x in blocked_paths)


def get_urls_from_sitemap():
    sitemap_candidates = [
        f"{SITE}/sitemap_index.xml",
        f"{SITE}/wp-sitemap.xml",
        f"{SITE}/post-sitemap.xml",
        f"{SITE}/wp-sitemap-posts-post-1.xml",
    ]
    urls = []
    for sitemap_url in sitemap_candidates:
        try:
            first_level = extract_locs(read_xml(sitemap_url))
            if not first_level:
                continue
            xml_children = [
                x for x in first_level
                if x.lower().endswith(".xml")
            ]
            if xml_children:
                # Ưu tiên sitemap bài viết trước category/page.
                xml_children.sort(
                    key=lambda x: (
                        0 if (
                            "post-sitemap" in x.lower()
                            or "posts-post" in x.lower()
                        ) else 1,
                        x,
                    )
                )
                for child in xml_children[:10]:
                    try:
                        child_urls = extract_locs(read_xml(child))
                        for url in child_urls:
                            if is_valid_site_url(url):
                                urls.append(url)
                    except Exception as exc:
                        log(
                            f"Sitemap child skip | "
                            f"{type(exc).__name__}"
                        )
            else:
                for url in first_level:
                    if is_valid_site_url(url):
                        urls.append(url)
            if urls:
                log(
                    f"Sitemap OK | "
                    f"{sitemap_url} | "
                    f"{len(urls)} URLs"
                )
                break
        except Exception as exc:
            log(
                f"Sitemap skip | "
                f"{sitemap_url} | "
                f"{type(exc).__name__}"
            )
    if not urls:
        urls = [SITE + "/"]
        log("Không đọc được sitemap → fallback homepage")
    return list(dict.fromkeys(urls))


def add_marker(url):
    """Trả về URL gốc, không thêm bất kỳ UTM nào."""
    return url


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


def run_visit(browser, url, index, endpoint_id):
    proxy_user = f"{PROXY_USER}-VN-{endpoint_id}"
    context = None
    try:
        # Browser chỉ launch 1 lần/run.
        # Mỗi context dùng một endpoint Webshare VN khác nhau.
        context = browser.new_context(
            proxy={
                "server": f"http://{PROXY_HOST}",
                "username": proxy_user,
                "password": PROXY_PASS,
            },
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
        )
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
            # Chỉ gắn custom header cho request tới bongdaha.com.
            # Không gắn vào request Google Analytics để tránh ảnh hưởng CORS.
            try:
                host = urllib.parse.urlsplit(req.url).netloc.lower()
            except Exception:
                host = ""
            if host == "bongdaha.com":
                headers = dict(req.headers)
                headers["x-bongdaha-pulse"] = "github-synthetic"
                route.continue_(headers=headers)
            else:
                route.continue_()

        page.on("request", watch_request)
        page.route("**/*", intercept)

        target = add_marker(url)
        log("")
        log("=" * 64)
        log(
            f"[{index}/{VISITS_PER_RUN}] "
            f"{url}"
        )
        log(
            f"Proxy endpoint: VN-{endpoint_id}"
        )
        response = page.goto(
            target,
            wait_until="domcontentloaded",
            timeout=45000,
        )
        status = (
            response.status
            if response
            else "NO_RESPONSE"
        )
        # Cho GTM/gtag có thời gian bắn request.
        wait_seconds = random.randint(7, 11)
        page.wait_for_timeout(wait_seconds * 1000)
        ga_status = "YES" if ga_hits > 0 else "NO"
        log(
            f"HTTP={status} | "
            f"GA_HIT={ga_status} | "
            f"GA_REQ={ga_hits} | "
            f"blocked={blocked} | "
            f"wait={wait_seconds}s"
        )
        return {
            "http_ok": isinstance(status, int) and status < 400,
            "ga_hit": ga_hits > 0,
        }
    except Exception as exc:
        log(
            f"FAIL | VN-{endpoint_id} | "
            f"{type(exc).__name__}: {exc}"
        )
        return {
            "http_ok": False,
            "ga_hit": False,
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
    urls = get_urls_from_sitemap()
    if len(urls) > 1000:
        urls = random.sample(urls, 1000)
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
    log("BONGDAHA PULSE")
    log(f"Site: {SITE}")
    log(f"URL pool: {len(urls)}")
    log(f"Visits/run: {VISITS_PER_RUN}")
    log(
        f"Proxy pool: VN-{PROXY_ENDPOINT_MIN} "
        f"→ VN-{PROXY_ENDPOINT_MAX}"
    )
    http_success = 0
    ga_success = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for i, endpoint_id in enumerate(endpoints, start=1):
                # 1 retry nhẹ nếu endpoint/session lỗi.
                result = run_visit(
                    browser,
                    random.choice(urls),
                    i,
                    endpoint_id,
                )
                if not result["http_ok"]:
                    retry_endpoint = random.randint(
                        PROXY_ENDPOINT_MIN,
                        PROXY_ENDPOINT_MAX,
                    )
                    log(
                        f"Retry visit {i} "
                        f"với VN-{retry_endpoint}"
                    )
                    result = run_visit(
                        browser,
                        random.choice(urls),
                        i,
                        retry_endpoint,
                    )
                if result["http_ok"]:
                    http_success += 1
                if result["ga_hit"]:
                    ga_success += 1
                if i < VISITS_PER_RUN:
                    delay = random.randint(3, 8)
                    log(f"Sleep {delay}s")
                    time.sleep(delay)
        finally:
            browser.close()
    log("")
    log("=" * 64)
    log(
        f"DONE | HTTP_OK={http_success}/{VISITS_PER_RUN} | "
        f"GA_HIT={ga_success}/{VISITS_PER_RUN}"
    )
    # Workflow fail chỉ khi không mở được bất kỳ page nào.
    # GA_HIT=0 vẫn để workflow hoàn tất để log cho biết
    # website có thể chưa gắn GA, consent chặn, hoặc tag không fire.
    if http_success == 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
