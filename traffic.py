import os
import random
import time
import urllib.parse

from playwright.sync_api import sync_playwright

SITE = "https://bongdaha.com"
ARTICLE_PREFIX = "/tin-bongda/"

PROXY_HOST = os.environ["PROXY_HOST"]
PROXY_USER = os.environ["PROXY_USER"]
PROXY_PASS = os.environ["PROXY_PASS"]

PROXY_ENDPOINT_MIN = 1
PROXY_ENDPOINT_MAX = 2393

VISITS_PER_RUN = int(os.getenv("VISITS_PER_RUN") or random.randint(7, 12))

BLOCK_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}
GA_HOST_SUFFIX = "google-analytics.com"


def log(msg):
    print(msg, flush=True)


def is_ga_collect(url):
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception:
        return False

    host = parsed.netloc.lower().split(":")[0]
    path = parsed.path.lower()
    return host.endswith(GA_HOST_SUFFIX) and (
        "/g/collect" in path or path.endswith("/collect")
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
    blocked = ("/feed", "/page/", "/author/", "/tag/", "/wp-")
    if any(x in lowered for x in blocked):
        return None

    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


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


def run_visit(browser, index, endpoint_id):
    proxy_user = f"{PROXY_USER}-VN-{endpoint_id}"
    context = None

    try:
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

        log("")
        log("=" * 68)
        log(f"[{index}/{VISITS_PER_RUN}] Proxy endpoint: VN-{endpoint_id}")

        home_response = page.goto(
            SITE + "/",
            wait_until="domcontentloaded",
            timeout=45000,
        )
        home_status = home_response.status if home_response else "NO_RESPONSE"

        page.wait_for_timeout(random.randint(2500, 4500))
        article_urls = collect_article_urls(page)

        if not article_urls:
            log(
                f"HOME={home_status} | ARTICLE_POOL=0 | "
                f"GA_REQ={ga_hits} | blocked={blocked}"
            )
            return {"http_ok": False, "ga_hit": ga_hits > 0, "article_pool": 0}

        article_url = random.choice(article_urls)
        article_response = page.goto(
            article_url,
            wait_until="domcontentloaded",
            timeout=45000,
        )
        article_status = article_response.status if article_response else "NO_RESPONSE"

        wait_seconds = random.randint(6, 10)
        page.wait_for_timeout(wait_seconds * 1000)

        ga_status = "YES" if ga_hits > 0 else "NO"

        log(f"ARTICLE_POOL={len(article_urls)}")
        log(f"ARTICLE={article_url}")
        log(
            f"HOME={home_status} | ARTICLE_HTTP={article_status} | "
            f"GA_HIT={ga_status} | GA_REQ={ga_hits} | "
            f"blocked={blocked} | wait={wait_seconds}s"
        )

        http_ok = (
            isinstance(home_status, int)
            and home_status < 400
            and isinstance(article_status, int)
            and article_status < 400
        )

        return {
            "http_ok": http_ok,
            "ga_hit": ga_hits > 0,
            "article_pool": len(article_urls),
        }

    except Exception as exc:
        log(f"FAIL | VN-{endpoint_id} | {type(exc).__name__}: {exc}")
        return {"http_ok": False, "ga_hit": False, "article_pool": 0}

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
    log("BONGDAHA PULSE - HOME → TIN BONG DA")
    log(f"Site: {SITE}")
    log(f"Article prefix: {ARTICLE_PREFIX}")
    log(f"Visits/run: {VISITS_PER_RUN}")
    log(f"Proxy pool: VN-{PROXY_ENDPOINT_MIN} → VN-{PROXY_ENDPOINT_MAX}")

    http_success = 0
    ga_success = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        try:
            for i, endpoint_id in enumerate(endpoints, start=1):
                result = run_visit(browser, i, endpoint_id)

                if not result["http_ok"]:
                    retry_endpoint = random.randint(
                        PROXY_ENDPOINT_MIN,
                        PROXY_ENDPOINT_MAX,
                    )
                    log(f"Retry visit {i} với VN-{retry_endpoint}")
                    result = run_visit(browser, i, retry_endpoint)

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
    log("=" * 68)
    log(
        f"DONE | HTTP_OK={http_success}/{VISITS_PER_RUN} | "
        f"GA_HIT={ga_success}/{VISITS_PER_RUN}"
    )

    if http_success == 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
