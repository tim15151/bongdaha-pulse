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

VISITS_PER_RUN = random.randint(7, 12)

BLOCK_RESOURCE_TYPES = {
    "image",
    "media",
    "font",
    "stylesheet",
}


def log(msg):
    print(msg, flush=True)


def read_xml(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "BongDaHa-Pulse/1.0"}
    )

    with urllib.request.urlopen(req, timeout=15) as response:
        return response.read()


def extract_locs(xml_data):
    root = ET.fromstring(xml_data)

    output = []

    for node in root.iter():
        if node.tag.endswith("loc") and node.text:
            output.append(node.text.strip())

    return output


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

            # Sitemap index
            xml_children = [
                x for x in first_level
                if x.lower().endswith(".xml")
            ]

            if xml_children:

                random.shuffle(xml_children)

                for child in xml_children[:8]:

                    try:
                        child_urls = extract_locs(read_xml(child))

                        for url in child_urls:

                            if (
                                url.startswith(SITE)
                                and not url.lower().endswith(".xml")
                            ):
                                urls.append(url)

                    except Exception:
                        pass

            else:

                for url in first_level:

                    if (
                        url.startswith(SITE)
                        and not url.lower().endswith(".xml")
                    ):
                        urls.append(url)

            if urls:

                log(
                    f"Sitemap OK | "
                    f"{len(urls)} URLs"
                )

                break

        except Exception as exc:

            log(
                f"Sitemap skip | "
                f"{type(exc).__name__}"
            )

    if not urls:

        urls = [SITE + "/"]

        log(
            "Không đọc được sitemap "
            "→ fallback homepage"
        )

    urls = list(dict.fromkeys(urls))

    return urls


def add_marker(url):

    parsed = urllib.parse.urlsplit(url)

    query = urllib.parse.parse_qsl(
        parsed.query,
        keep_blank_values=True
    )

    query.extend([
        ("utm_source", "github"),
        ("utm_medium", "synthetic"),
        ("utm_campaign", "bongdaha_pulse"),
    ])

    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(query),
            parsed.fragment,
        )
    )


def run_visit(playwright, url, index):

    session_id = random.randint(
        100000,
        999999
    )

    proxy_user = (
        f"{PROXY_USER}-VN-{session_id}"
    )

    browser = None

    try:

        browser = playwright.chromium.launch(
            headless=True,
            proxy={
                "server": f"http://{PROXY_HOST}",
                "username": proxy_user,
                "password": PROXY_PASS,
            }
        )

        context = browser.new_context(
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
            extra_http_headers={
                "X-BongDaHa-Pulse":
                    "github-synthetic"
            },
        )

        page = context.new_page()

        blocked = 0

        def intercept(route):

            nonlocal blocked

            if (
                route.request.resource_type
                in BLOCK_RESOURCE_TYPES
            ):

                blocked += 1

                route.abort()

            else:

                route.continue_()

        page.route(
            "**/*",
            intercept
        )

        target = add_marker(url)

        log("")
        log("=" * 55)

        log(
            f"[{index}/{VISITS_PER_RUN}] "
            f"{url}"
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

        # Để JS + GA tag có thời gian chạy
        wait = random.randint(5, 9)

        page.wait_for_timeout(
            wait * 1000
        )

        log(
            f"HTTP={status} | "
            f"blocked={blocked} | "
            f"proxy_session=VN-{session_id}"
        )

        context.close()

        return (
            isinstance(status, int)
            and status < 400
        )

    except Exception as exc:

        log(
            f"FAIL | "
            f"{type(exc).__name__}: {exc}"
        )

        return False

    finally:

        if browser:

            try:
                browser.close()
            except Exception:
                pass


def main():

    urls = get_urls_from_sitemap()

    if len(urls) > 1000:
        urls = random.sample(
            urls,
            1000
        )

    log("")
    log("BONGDAHA PULSE")
    log(f"URL pool: {len(urls)}")
    log(
        f"Visits/run: "
        f"{VISITS_PER_RUN}"
    )

    success = 0

    with sync_playwright() as p:

        for i in range(
            1,
            VISITS_PER_RUN + 1
        ):

            url = random.choice(urls)

            if run_visit(
                p,
                url,
                i
            ):

                success += 1

            if i < VISITS_PER_RUN:

                delay = random.randint(
                    4,
                    10
                )

                log(
                    f"Sleep {delay}s"
                )

                time.sleep(delay)

    log("")
    log("=" * 55)

    log(
        f"DONE "
        f"{success}/{VISITS_PER_RUN}"
    )


if __name__ == "__main__":
    main()
