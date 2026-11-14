#!/usr/bin/env python3
"""Check a deployed MyTrips PWA's actual install resources, without credentials.

Run on the OCI host first (bypasses Cloudflare Access):
    python3 scripts/check_pwa_install.py --origin http://127.0.0.1:8030

External Cloudflare Access-protected origins may return a login redirect; that
is an expected authentication boundary, not proof that the app is broken.
"""

import argparse
from html.parser import HTMLParser
import json
import struct
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
import zlib


class ManifestLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "link" and "manifest" in values.get("rel", "").split():
            self.links.append(values)


def check(condition, error):
    if not condition:
        raise ValueError(error)


def download(url):
    request = Request(url, headers={"User-Agent": "MyTrips-PWA-Install-Check/1.0"})
    try:
        with urlopen(request, timeout=12) as response:
            payload = response.read(3 * 1024 * 1024 + 1)
            check(len(payload) <= 3 * 1024 * 1024, "Resource exceeds 3 MB")
            actual = response.geturl()
            check(urlsplit(actual).netloc == urlsplit(url).netloc,
                  "Redirected to another host (possibly Cloudflare Access login)")
            return response.headers.get_content_type(), payload
    except HTTPError as exc:
        raise ValueError(f"HTTP {exc.code}: possible missing file or Access policy") from exc
    except URLError as exc:
        raise ValueError(f"Network error: {exc.reason}") from exc


def validate_png(body, size):
    check(body.startswith(b"\x89PNG\r\n\x1a\n"), "Not a PNG (an HTML login page may be returned)")
    check(len(body) >= 45, "PNG too small")
    width, height = struct.unpack_from(">II", body, 16)
    check((width, height) == (size, size),
          f"Expected {size}x{size} PNG; received {width}x{height}")
    offset = 8
    saw_image_data = False
    saw_end = False
    while offset + 12 <= len(body):
        n = struct.unpack_from(">I", body, offset)[0]
        check(n <= 3 * 1024 * 1024, "PNG chunk too large")
        check(offset + 12 + n <= len(body), "Truncated PNG chunk")
        chunk_type = body[offset + 4:offset + 8]
        data = body[offset + 8:offset + 8 + n]
        stored_crc = struct.unpack_from(">I", body, offset + 8 + n)[0]
        check(zlib.crc32(chunk_type + data) == stored_crc,
              f"PNG CRC mismatch in chunk {chunk_type!r}")
        if chunk_type == b"IDAT":
            saw_image_data = True
        if chunk_type == b"IEND":
            saw_end = True
            break
        offset += 12 + n
    check(saw_image_data and saw_end, "PNG has no image data or end marker")


def run(origin):
    origin = origin.rstrip("/") + "/"
    scheme = urlsplit(origin)
    check(scheme.scheme in ("http", "https") and scheme.netloc, "Invalid origin URL")
    check(scheme.scheme == "https" or scheme.hostname in ("127.0.0.1", "localhost", "::1"),
          "Android PWA installation requires HTTPS (except localhost)")

    mime, html = download(origin)
    check(mime == "text/html", f"Root returned {mime}, expected HTML")
    parser = ManifestLinkParser()
    parser.feed(html.decode("utf-8", errors="replace"))
    check(len(parser.links) == 1, f"Expected exactly one manifest link, got {len(parser.links)}")
    link = parser.links[0]
    check(link.get("crossorigin") == "use-credentials",
          "Manifest link lacks crossorigin=use-credentials (required behind Cloudflare Access)")
    print("PASS  HTML + credentialed manifest link")

    manifest_url = urljoin(origin, link.get("href", ""))
    mime, content = download(manifest_url)
    check(mime in ("application/json", "application/manifest+json"),
          f"Manifest Content-Type {mime}, expected JSON; possible Access login")
    try:
        manifest = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Manifest is not valid JSON") from exc
    check(manifest.get("name") == "MyTrips", "Wrong application name")
    check(manifest.get("short_name") == "MyTrips", "Wrong short_name")
    check(manifest.get("display") in ("standalone", "fullscreen", "minimal-ui"),
          "PWA display mode is not installable")
    check(manifest.get("prefer_related_applications") is not True,
          "prefer_related_applications forbids PWA install")
    start = urljoin(manifest_url, manifest.get("start_url", ""))
    check(urlsplit(start).netloc == scheme.netloc, "start_url is not same-origin")
    check(urlsplit(start).path.startswith(urlsplit(urljoin(origin, manifest.get("scope", "/"))).path),
          "start_url falls outside manifest scope")
    print("PASS  Manifest JSON, identity, scope, display mode")

    any_sizes = set()
    maskable_sizes = set()
    for i, icon in enumerate(manifest.get("icons", [])):
        sizes = icon.get("sizes", "").split()
        check(len(sizes) == 1 and "x" in sizes[0], f"Icon {i}: invalid sizes")
        width, height = map(int, sizes[0].split("x"))
        check(width == height and width > 0, f"Icon {i}: invalid dimensions")
        src = icon.get("src", "")
        check(src, f"Icon {i} missing URL")
        icon_url = urljoin(manifest_url, src)
        check(urlsplit(icon_url).netloc == scheme.netloc, f"Icon {i} is cross-origin")
        icon_mime, blob = download(icon_url)
        check(icon_mime == "image/png", f"Icon {i} returned {icon_mime}, expected image/png")
        validate_png(blob, width)
        # A manifest icon can advertise both purposes; it counts for both.
        # Smart Meter Texas uses "any maskable" on its primary 512px icon.
        purposes = set(icon.get("purpose", "any").split())
        check(bool(purposes) and purposes.issubset({"any", "maskable", "monochrome"}),
              f"Icon {i}: invalid purpose")
        if "any" in purposes:
            any_sizes.add(width)
        if "maskable" in purposes:
            maskable_sizes.add(width)
        print(f"PASS  Icon {width}x{height}: image/png, valid PNG chunks")
    check(192 in any_sizes and 512 in any_sizes,
          "Chromium requires both 192x192 and 512x512 regular icons")
    check(512 in maskable_sizes, "512x512 maskable icon is missing")

    sw_mime, sw = download(urljoin(origin, "/sw.js"))
    check(sw_mime in ("text/javascript", "application/javascript"),
          f"Service worker returned {sw_mime}, expected JavaScript")
    check(b"addEventListener('fetch'" in sw, "Service worker fetch handler missing")
    print("PASS  Service worker HTTP response")
    print("\nPASS  MyTrips PWA local installability resources are valid")
    print("NOTE  Android installation can still be blocked by Cloudflare Access, old browser cache, or phone settings")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="http://127.0.0.1:8030",
                        help="MyTrips origin (default: http://127.0.0.1:8030)")
    args = parser.parse_args()
    try:
        run(args.origin)
    except (ValueError, TypeError) as exc:
        parser.exit(1, f"FAIL  {exc}\n")
