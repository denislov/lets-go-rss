"""
Lightweight scraper modules for various platforms.

Architecture:
- Tier 1 (Native RSS): Vimeo, Behance — direct RSS feed parsing
- Tier 1b (yt-dlp):    YouTube — uses yt-dlp for metadata extraction
- Tier 2 (RSSHub):     Bilibili, Weibo, Douyin, Xiaohongshu — via local RSSHub

Environment variables:
- RSSHUB_BASE_URL: Base URL of self-hosted RSSHub (default: http://localhost:1200)
"""

import re
import os
import json
import hashlib
import subprocess
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from datetime import datetime
import time
import httpx
from urllib.parse import urlparse, parse_qs


# ============================================================
#  Base classes
# ============================================================

class BaseScraper:
    """Base scraper with common HTTP functionality"""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
        }
        self.timeout = float(os.environ.get("RSS_HTTP_TIMEOUT", "10"))
        self.max_retries = max(1, int(os.environ.get("RSS_HTTP_RETRIES", "2")))
        self.retry_backoff = float(os.environ.get("RSS_HTTP_BACKOFF", "0.8"))
        self.last_error = None

    def get(self, url: str, headers: Optional[Dict] = None,
            timeout: Optional[float] = None,
            retries: Optional[int] = None) -> httpx.Response:
        """Make GET request with retry logic"""
        request_timeout = timeout if timeout is not None else self.timeout
        max_retries = max(1, retries if retries is not None else self.max_retries)
        request_headers = {**self.headers, **(headers or {})}
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=request_timeout, follow_redirects=True) as client:
                    response = client.get(url, headers=request_headers)
                    response.raise_for_status()
                    return response
            except Exception:
                if attempt == max_retries - 1:
                    raise
                time.sleep(self.retry_backoff * (attempt + 1))


class NativeRSSScraper(BaseScraper):
    """Base class for scrapers that parse native RSS/Atom feeds"""

    def parse_rss_xml(self, xml_text: str, platform: str = "") -> List[Dict[str, Any]]:
        """Parse standard RSS 2.0 or Atom feed XML into item dicts"""
        items = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            print(f"    ⚠️  XML parse error: {e}")
            return []

        # Atom feed (YouTube uses this)
        atom_ns = "http://www.w3.org/2005/Atom"
        media_ns = "http://search.yahoo.com/mrss/"

        if root.tag == f"{{{atom_ns}}}feed" or root.tag == "feed":
            # Extract feed/channel title
            feed_title_el = root.find(f"{{{atom_ns}}}title")
            channel_title = feed_title_el.text.strip() if feed_title_el is not None and feed_title_el.text else ""

            entries = root.findall(f"{{{atom_ns}}}entry")
            for entry in entries[:20]:
                title_el = entry.find(f"{{{atom_ns}}}title")
                link_el = entry.find(f"{{{atom_ns}}}link")
                published_el = entry.find(f"{{{atom_ns}}}published")
                updated_el = entry.find(f"{{{atom_ns}}}updated")
                summary_el = entry.find(f"{{{media_ns}}}group/{{{media_ns}}}description")

                title = title_el.text if title_el is not None and title_el.text else ""
                link = link_el.get("href", "") if link_el is not None else ""
                pub_date = (published_el.text if published_el is not None
                           else updated_el.text if updated_el is not None else "")
                description = summary_el.text if summary_el is not None and summary_el.text else ""

                item_id = f"{platform}_{hashlib.md5(link.encode()).hexdigest()[:12]}"
                items.append({
                    "item_id": item_id,
                    "title": title.strip(),
                    "description": description[:500] if description else "",
                    "link": link,
                    "pub_date": pub_date,
                    "metadata": {"_channel_title": channel_title}
                })
        else:
            # RSS 2.0 format
            channel = root.find("channel")
            # Extract channel title
            channel_title = ""
            if channel is not None:
                ch_title_el = channel.find("title")
                channel_title = ch_title_el.text.strip() if ch_title_el is not None and ch_title_el.text else ""
            item_elements = channel.findall("item") if channel is not None else root.findall(".//item")

            for item_el in item_elements[:20]:
                title_el = item_el.find("title")
                link_el = item_el.find("link")
                desc_el = item_el.find("description")
                pubdate_el = item_el.find("pubDate")
                guid_el = item_el.find("guid")

                title = title_el.text if title_el is not None and title_el.text else ""
                link = link_el.text if link_el is not None and link_el.text else ""
                description = desc_el.text if desc_el is not None and desc_el.text else ""
                pub_date = pubdate_el.text if pubdate_el is not None and pubdate_el.text else ""
                guid = guid_el.text if guid_el is not None and guid_el.text else link

                # Strip HTML tags from description for cleaner text
                clean_desc = re.sub(r'<[^>]+>', '', description)[:500]

                item_id = f"{platform}_{hashlib.md5(guid.encode()).hexdigest()[:12]}"
                items.append({
                    "item_id": item_id,
                    "title": title.strip(),
                    "description": clean_desc.strip(),
                    "link": link,
                    "pub_date": pub_date,
                    "metadata": {"_channel_title": channel_title}
                })

        return items


class RSSHubScraper(NativeRSSScraper):
    """Base class for scrapers that fetch via self-hosted RSSHub"""

    RSSHUB_BASE = os.environ.get("RSSHUB_BASE_URL", "http://localhost:1200")

    def __init__(self, route_template: str):
        super().__init__()
        self.route_template = route_template

    def extract_user_id(self, url: str) -> Optional[str]:
        """Override in subclass to extract platform-specific user ID"""
        raise NotImplementedError

    def fetch_items(self, url: str) -> List[Dict[str, Any]]:
        """Fetch via RSSHub route"""
        self.last_error = None
        user_id = self.extract_user_id(url)
        if not user_id:
            print(f"    ⚠️  Cannot extract user ID from: {url}")
            self.last_error = f"Cannot extract user ID from {url}"
            return []

        rsshub_url = f"{self.RSSHUB_BASE}{self.route_template.format(id=user_id)}"
        print(f"    📡 RSSHub: {rsshub_url}")

        try:
            response = self.get(rsshub_url)
            ct = response.headers.get("content-type", "")
            if "xml" in ct or "rss" in ct:
                return self.parse_rss_xml(response.text, self._platform_name())
            else:
                # Might be an error page
                print(f"    ⚠️  RSSHub returned non-RSS content (HTTP {response.status_code})")
                self.last_error = f"Non-RSS content from RSSHub (HTTP {response.status_code})"
                return []
        except Exception as e:
            self.last_error = str(e)
            print(f"    ❌ RSSHub fetch failed: {e}")
            return []

    def _platform_name(self) -> str:
        return self.__class__.__name__.replace("Scraper", "").lower()


# ============================================================
#  Tier 1: Native RSS scrapers (zero maintenance)
# ============================================================

class VimeoScraper(NativeRSSScraper):
    """Vimeo scraper — uses native RSS feed at /{username}/videos/rss"""

    def extract_user_id(self, url: str) -> Optional[str]:
        """Extract username from Vimeo URL"""
        match = re.search(r"vimeo\.com/([^/?#]+)", url)
        return match.group(1) if match else None

    def fetch_items(self, url: str) -> List[Dict[str, Any]]:
        self.last_error = None
        username = self.extract_user_id(url)
        if not username:
            self.last_error = f"Cannot extract Vimeo username from {url}"
            return []

        rss_url = f"https://vimeo.com/{username}/videos/rss"
        print(f"    📡 Native RSS: {rss_url}")

        try:
            response = self.get(rss_url)
            return self.parse_rss_xml(response.text, "vimeo")
        except Exception as e:
            self.last_error = str(e)
            print(f"    ❌ Vimeo RSS fetch failed: {e}")
            return []


class BehanceScraper(NativeRSSScraper):
    """Behance scraper — uses native RSS feed at /feeds/user?username={user}"""

    def extract_user_id(self, url: str) -> Optional[str]:
        """Extract username from Behance URL"""
        match = re.search(r"behance\.net/([^/?#]+)", url)
        return match.group(1) if match else None

    def fetch_items(self, url: str) -> List[Dict[str, Any]]:
        self.last_error = None
        username = self.extract_user_id(url)
        if not username:
            self.last_error = f"Cannot extract Behance username from {url}"
            return []

        rss_url = f"https://www.behance.net/feeds/user?username={username}"
        print(f"    📡 Native RSS: {rss_url}")

        try:
            response = self.get(rss_url)
            return self.parse_rss_xml(response.text, "behance")
        except Exception as e:
            err = str(e)
            # Behance occasionally rate-limits with 403; treat as temporary skip.
            if "403" in err:
                print("    ⚠️  Behance rate-limited (403), skip this cycle")
                self.last_error = None
                return []
            self.last_error = err
            print(f"    ❌ Behance RSS fetch failed: {e}")
            return []


# ============================================================
#  Tier 1b: YouTube via yt-dlp (no API key needed)
# ============================================================

class YouTubeScraper(BaseScraper):
    """YouTube scraper — uses yt-dlp, with native Atom feed fallback."""

    def _fetch_via_atom_feed(self, channel_ref: str) -> List[Dict[str, Any]]:
        """Fallback: parse YouTube's native Atom feed (no yt-dlp needed).

        Works when yt-dlp is blocked by bot checks or times out.
        """
        channel_id = ""
        if channel_ref.startswith("UC"):
            channel_id = channel_ref
        else:
            # Resolve channel_id from page HTML
            if channel_ref.startswith("@"):
                page_url = f"https://www.youtube.com/{channel_ref}/videos"
            else:
                page_url = f"https://www.youtube.com/channel/{channel_ref}/videos"
            try:
                resp = self.get(page_url, timeout=12, retries=2)
                m = re.search(r'"externalId":"([A-Za-z0-9_-]+)"', resp.text)
                if not m:
                    m = re.search(r'"browseId":"(UC[A-Za-z0-9_-]+)"', resp.text)
                if m:
                    channel_id = m.group(1)
            except Exception:
                return []

        if not channel_id:
            return []

        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        try:
            response = self.get(feed_url, timeout=12, retries=2)
            parser = NativeRSSScraper()
            items = parser.parse_rss_xml(response.text, "youtube")
            if items:
                print(f"    ✓ YouTube Atom feed fallback: {len(items)} items")
            return items
        except Exception:
            return []

    def extract_channel_id(self, url: str) -> Optional[str]:
        """Extract @handle or channel path from YouTube URL"""
        # Match @handle format
        match = re.search(r"youtube\.com/(@[\w-]+)", url)
        if match:
            return match.group(1)
        # Match /channel/ID format
        match = re.search(r"youtube\.com/channel/([\w-]+)", url)
        if match:
            return match.group(1)
        # Match /c/name format
        match = re.search(r"youtube\.com/c/([\w-]+)", url)
        if match:
            return match.group(1)
        return None

    def fetch_items(self, url: str) -> List[Dict[str, Any]]:
        self.last_error = None
        channel_ref = self.extract_channel_id(url)
        if not channel_ref:
            self.last_error = f"Cannot extract YouTube channel from {url}"
            return []

        # Construct videos URL
        if channel_ref.startswith("@"):
            videos_url = f"https://www.youtube.com/{channel_ref}/videos"
        else:
            videos_url = f"https://www.youtube.com/channel/{channel_ref}/videos"

        print(f"    📡 yt-dlp: {videos_url}")

        # Use --print to get structured fields including upload_date
        # --flat-playlist + --dump-json does NOT include upload_date
        SEPARATOR = "|||"
        PRINT_FORMAT = SEPARATOR.join([
            "%(id)s", "%(title)s", "%(upload_date)s",
            "%(duration)s", "%(view_count)s", "%(channel)s",
            "%(description).500s",
        ])

        try:
            ytdlp_timeout = int(os.environ.get("RSS_YTDLP_TIMEOUT", "20"))
            result = subprocess.run(
                [
                    "yt-dlp",
                    "--print", PRINT_FORMAT,
                    "--playlist-items", "1:15",
                    "--no-warnings",
                    videos_url,
                ],
                capture_output=True,
                text=True,
                timeout=ytdlp_timeout,
            )

            if result.returncode != 0:
                err_text = result.stderr[:200] or "yt-dlp returned non-zero status"
                print(f"    ⚠️  yt-dlp error: {err_text}")
                # Fallback to native Atom feed
                fallback = self._fetch_via_atom_feed(channel_ref)
                if fallback:
                    self.last_error = None
                    return fallback
                self.last_error = err_text
                return []

            items = []
            for line in result.stdout.strip().split("\n"):
                if not line or SEPARATOR not in line:
                    continue
                parts = line.split(SEPARATOR, 6)
                if len(parts) < 6:
                    continue

                video_id, title, upload_date, duration, view_count, channel = parts[:6]
                description = parts[6] if len(parts) > 6 else ""

                # Parse upload_date (format: YYYYMMDD)
                pub_date = ""
                if upload_date and upload_date != "NA":
                    try:
                        pub_date = datetime.strptime(upload_date, "%Y%m%d").isoformat()
                    except ValueError:
                        pass

                # Parse numeric fields safely
                try:
                    duration_int = int(duration) if duration and duration != "NA" else 0
                except ValueError:
                    duration_int = 0
                try:
                    view_int = int(view_count) if view_count and view_count != "NA" else 0
                except ValueError:
                    view_int = 0

                items.append({
                    "item_id": f"youtube_{video_id}",
                    "title": title,
                    "description": description,
                    "link": f"https://www.youtube.com/watch?v={video_id}",
                    "pub_date": pub_date,
                    "metadata": {
                        "video_id": video_id,
                        "duration": duration_int,
                        "view_count": view_int,
                        "channel": channel,
                    }
                })

            return items

        except subprocess.TimeoutExpired:
            self.last_error = "yt-dlp timed out"
            print(f"    ❌ yt-dlp timed out ({ytdlp_timeout}s)")
            fallback = self._fetch_via_atom_feed(channel_ref)
            if fallback:
                self.last_error = None
                return fallback
            return []
        except FileNotFoundError:
            self.last_error = "yt-dlp not found"
            print("    ❌ yt-dlp not found. Install: pip install yt-dlp")
            fallback = self._fetch_via_atom_feed(channel_ref)
            if fallback:
                self.last_error = None
                return fallback
            return []
        except Exception as e:
            self.last_error = str(e)
            print(f"    ❌ YouTube fetch error: {e}")
            fallback = self._fetch_via_atom_feed(channel_ref)
            if fallback:
                self.last_error = None
                return fallback
            return []


# ============================================================
#  Tier 2: RSSHub-based scrapers
# ============================================================

class BilibiliScraper(RSSHubScraper):
    """Bilibili scraper via RSSHub — tries /video route first, falls back to /dynamic."""

    def __init__(self):
        super().__init__("/bilibili/user/video/{id}")
        self._fallback_route = "/bilibili/user/dynamic/{id}"

    def extract_user_id(self, url: str) -> Optional[str]:
        match = re.search(r"space\.bilibili\.com/(\d+)", url)
        return match.group(1) if match else None

    def fetch_items(self, url: str) -> List[Dict[str, Any]]:
        """Try video route first; on 503 (anti-bot), fall back to dynamic route."""
        self.last_error = None
        user_id = self.extract_user_id(url)
        if not user_id:
            self.last_error = f"Cannot extract Bilibili user ID from {url}"
            return []

        # Try primary /video route
        video_url = f"{self.RSSHUB_BASE}/bilibili/user/video/{user_id}"
        print(f"    📡 RSSHub: {video_url}")
        try:
            response = self.get(video_url)
            ct = response.headers.get("content-type", "")
            if "xml" in ct or "rss" in ct:
                items = self.parse_rss_xml(response.text, "bilibili")
                if items:
                    return items
        except Exception as e:
            err_msg = str(e)
            if "503" in err_msg or "风控" in err_msg:
                # Anti-bot triggered, try dynamic route
                dynamic_url = f"{self.RSSHUB_BASE}/bilibili/user/dynamic/{user_id}"
                print(f"    ⚠️  Video route blocked, trying dynamic: {dynamic_url}")
                try:
                    response = self.get(dynamic_url)
                    ct = response.headers.get("content-type", "")
                    if "xml" in ct or "rss" in ct:
                        items = self.parse_rss_xml(response.text, "bilibili")
                        if items:
                            return items
                except Exception as e2:
                    self.last_error = f"Both routes failed: video={err_msg[:60]}, dynamic={e2}"
                    print(f"    ❌ Dynamic fallback also failed: {e2}")
                    return []
            self.last_error = err_msg
            print(f"    ❌ RSSHub fetch failed: {e}")
            return []

        return []


class WeiboScraper(RSSHubScraper):
    """Weibo scraper via RSSHub — works without cookie for most users"""

    def __init__(self):
        super().__init__("/weibo/user/{id}")

    def extract_user_id(self, url: str) -> Optional[str]:
        # Match /u/123456 or /userid
        match = re.search(r"weibo\.com/u/(\d+)", url)
        if match:
            return match.group(1)
        match = re.search(r"weibo\.com/(\d+)", url)
        return match.group(1) if match else None


class DouyinScraper(RSSHubScraper):
    """Douyin scraper via RSSHub — works without cookie for most users"""

    def __init__(self):
        super().__init__("/douyin/user/{id}")

    def extract_user_id(self, url: str) -> Optional[str]:
        # Direct user URL
        match = re.search(r"douyin\.com/user/([A-Za-z0-9_-]+)", url)
        if match:
            return match.group(1)

        # Short URL — need to resolve redirect
        if "v.douyin.com" in url or "douyin.com" in url:
            try:
                with httpx.Client(timeout=10, follow_redirects=True) as client:
                    resp = client.get(url, headers=self.headers)
                    final_url = str(resp.url)
                    match = re.search(r"user/([A-Za-z0-9_-]+)", final_url)
                    if match:
                        return match.group(1)
            except Exception as e:
                print(f"    ⚠️  Douyin URL resolve failed: {e}")

        return None


class XiaohongshuScraper(BaseScraper):
    """Xiaohongshu scraper — uses Playwright with rednote-mcp cookies.

    Strategy: load user profile page in headless browser, intercept the XHR
    response from the `user_posted` API. The browser handles request signing
    automatically, bypassing the 406 error from direct API calls.

    Cookie source: ~/.mcp/rednote/cookies.json (managed by rednote-mcp init)
    Fallback: RSSHub route (may fail due to XHS anti-scraping)
    """

    RSSHUB_BASE = os.environ.get("RSSHUB_BASE_URL", "http://localhost:1200")
    COOKIE_PATH = os.path.expanduser("~/.mcp/rednote/cookies.json")

    def __init__(self):
        super().__init__()
        self.timeout = float(os.environ.get("RSS_XHS_TIMEOUT", "15"))
        self._pw_cookies = self._load_pw_cookies()

    def _load_pw_cookies(self) -> list:
        """Load Playwright-format cookies from rednote-mcp store."""
        try:
            with open(self.COOKIE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def extract_user_id(self, url: str) -> Optional[str]:
        match = re.search(r"user/profile/([a-zA-Z0-9]+)", url)
        if match:
            return match.group(1)
        match = re.search(r"xiaohongshu\.com/([a-zA-Z0-9]+)", url)
        return match.group(1) if match else None

    def fetch_items(self, url: str) -> List[Dict[str, Any]]:
        self.last_error = None
        user_id = self.extract_user_id(url)
        if not user_id:
            self.last_error = f"Cannot extract XHS user ID from {url}"
            return []

        # Try Playwright with rednote-mcp cookies
        if self._pw_cookies:
            items = self._fetch_via_playwright(user_id)
            if items:
                return items

        # Fallback: RSSHub
        return self._fetch_via_rsshub(user_id)

    def _fetch_via_playwright(self, user_id: str) -> List[Dict[str, Any]]:
        """Fetch user notes by intercepting XHR in a headless browser."""
        print(f"    📡 XHS Playwright: user={user_id}")
        captured_notes = []

        try:
            from playwright.sync_api import sync_playwright

            def handle_response(response):
                """Capture the user_posted API response."""
                if "user_posted" in response.url or "user/posted" in response.url:
                    try:
                        data = response.json()
                        notes = data.get("data", {}).get("notes", [])
                        if notes:
                            captured_notes.extend(notes)
                    except Exception:
                        pass

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=self.headers["User-Agent"],
                    viewport={"width": 1280, "height": 800},
                )
                # Load rednote-mcp cookies
                context.add_cookies(self._pw_cookies)

                page = context.new_page()
                page.on("response", handle_response)

                profile_url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
                page.goto(profile_url, timeout=int(self.timeout * 1000), wait_until="domcontentloaded")

                # Check for captcha/login redirect (cookies expired)
                current_url = page.url
                if "captcha" in current_url or "login" in current_url:
                    print("    ⚠️  XHS cookies expired (captcha/login redirect)")
                    print("    💡 Fix: run 'npx rednote-mcp init' to re-login")
                    self.last_error = "XHS cookies expired — run 'npx rednote-mcp init'"
                    browser.close()
                    return []

                # Wait for notes to load (either via XHR interception or DOM)
                try:
                    page.wait_for_selector(
                        ".note-item, .feeds-container, section.note-item",
                        timeout=8000,
                    )
                    # Small delay for XHR to complete
                    page.wait_for_timeout(1500)
                except Exception:
                    pass  # XHR may have already been captured

                # If XHR interception worked, parse captured_notes
                if captured_notes:
                    items = self._parse_api_notes(captured_notes, user_id, page)
                    browser.close()
                    if items:
                        print(f"  ✓ XHS: {len(items)} notes via Playwright XHR")
                        return items

                # Fallback: try to extract from DOM
                items = self._parse_dom_notes(page, user_id)
                browser.close()
                if items:
                    print(f"  ✓ XHS: {len(items)} notes via DOM")
                return items

        except ImportError:
            print("    ⚠️  Playwright not available")
            return []
        except Exception as e:
            print(f"    ⚠️  XHS Playwright failed: {e}")
            return []

    def _parse_api_notes(self, notes: list, user_id: str, page) -> List[Dict[str, Any]]:
        """Parse notes from intercepted API response."""
        items = []
        # Try to get author name from page
        author = ""
        try:
            author_el = page.query_selector(".user-name, .info .username")
            if author_el:
                author = author_el.inner_text().strip()
        except Exception:
            pass

        for note in notes[:20]:
            note_id = note.get("note_id", "")
            if not note_id:
                continue
            display_title = note.get("display_title", "")
            timestamp_ms = note.get("time", 0) or note.get("last_update_time", 0)
            pub_date = ""
            if timestamp_ms:
                try:
                    pub_date = datetime.fromtimestamp(timestamp_ms / 1000).isoformat()
                except (ValueError, OSError):
                    pass

            link = f"https://www.xiaohongshu.com/explore/{note_id}"
            item_id = f"xiaohongshu_{hashlib.md5(note_id.encode()).hexdigest()[:12]}"

            cover = note.get("cover", {})
            cover_url = cover.get("url", "") if isinstance(cover, dict) else ""
            note_author = note.get("user", {}).get("nickname", "") or author

            items.append({
                "item_id": item_id,
                "title": display_title or "(无标题)",
                "description": "",
                "link": link,
                "pub_date": pub_date,
                "metadata": {
                    "_channel_title": note_author,
                    "note_id": note_id,
                    "cover_url": cover_url,
                    "liked_count": note.get("liked_count", ""),
                }
            })
        return items

    def _parse_dom_notes(self, page, user_id: str) -> List[Dict[str, Any]]:
        """Fallback: extract notes directly from DOM."""
        items = []
        seen_ids = set()

        # Get author name from page header
        author = ""
        try:
            author_el = page.query_selector(".user-name, .info .username, .user-nickname")
            if author_el:
                author = author_el.inner_text().strip()
        except Exception:
            pass

        try:
            # Each section.note-item contains a cover link and title text
            note_sections = page.query_selector_all("section.note-item")
            if not note_sections:
                note_sections = page.query_selector_all(".note-item")

            for section in note_sections[:20]:
                # Extract note_id from cover link href
                cover = section.query_selector("a.cover")
                if not cover:
                    continue
                href = cover.get_attribute("href") or ""
                # Pattern: /user/profile/{uid}/{note_id}?... or /explore/{note_id}
                note_match = re.search(r"/([a-f0-9]{24})(?:\?|$)", href)
                if not note_match:
                    note_match = re.search(r"/explore/([a-f0-9]+)", href)
                if not note_match:
                    continue

                note_id = note_match.group(1)
                if note_id in seen_ids:
                    continue
                seen_ids.add(note_id)

                # Extract title from section inner_text
                title = ""
                try:
                    text = section.inner_text().strip()
                    # inner_text contains: optional "置顶\n", title, author, likes
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    # Skip "置顶" tag and author/likes at end
                    for line in lines:
                        if line in ("置顶",) or line.isdigit():
                            continue
                        if line == author:
                            continue
                        title = line
                        break
                except Exception:
                    pass

                link = f"https://www.xiaohongshu.com/explore/{note_id}"
                item_id = f"xiaohongshu_{hashlib.md5(note_id.encode()).hexdigest()[:12]}"

                items.append({
                    "item_id": item_id,
                    "title": title or "(无标题)",
                    "description": "",
                    "link": link,
                    "pub_date": "",
                    "metadata": {
                        "_channel_title": author,
                        "note_id": note_id,
                    }
                })
        except Exception as e:
            print(f"    ⚠️  DOM extraction failed: {e}")
        return items

    def _fetch_via_rsshub(self, user_id: str) -> List[Dict[str, Any]]:
        """Fallback: fetch via RSSHub (may fail due to XHS anti-scraping)."""
        rsshub_url = f"{self.RSSHUB_BASE}/xiaohongshu/user/{user_id}/notes"
        print(f"    📡 RSSHub fallback: {rsshub_url}")
        try:
            response = self.get(rsshub_url, timeout=6, retries=1)
            ct = response.headers.get("content-type", "")
            if "xml" in ct or "rss" in ct:
                parser = NativeRSSScraper()
                return parser.parse_rss_xml(response.text, "xiaohongshu")
            else:
                self.last_error = f"Non-RSS content from RSSHub (HTTP {response.status_code})"
                return []
        except Exception as e:
            self.last_error = str(e)
            print(f"    ❌ RSSHub fallback also failed: {e}")
            return []


# ============================================================
#  Tier 1c: Twitter/X via Syndication API (zero config)
# ============================================================

class TwitterScraper(BaseScraper):
    """Twitter/X scraper — uses the public Syndication API (no auth needed).

    Primary:  syndication.twitter.com (embedded __NEXT_DATA__ JSON)
    Fallback: RSSHub /twitter/user/{id} (requires TWITTER_AUTH_TOKEN in RSSHub)
    """

    SYNDICATION_URL = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}"
    RSSHUB_BASE = os.environ.get("RSSHUB_BASE_URL", "http://localhost:1200")

    def extract_user_id(self, url: str) -> Optional[str]:
        """Extract username from x.com or twitter.com URL."""
        match = re.search(r"(?:x\.com|twitter\.com)/(@?[\w]+)", url)
        if match:
            username = match.group(1).lstrip("@")
            # Skip non-user paths
            if username.lower() in ("home", "explore", "search", "notifications",
                                     "messages", "settings", "i", "compose"):
                return None
            return username
        return None

    def fetch_items(self, url: str) -> List[Dict[str, Any]]:
        self.last_error = None
        username = self.extract_user_id(url)
        if not username:
            self.last_error = f"Cannot extract Twitter username from {url}"
            return []

        # Try Syndication API first (zero config)
        items = self._fetch_via_syndication(username)
        if items:
            return items

        # Fallback: RSSHub (needs TWITTER_AUTH_TOKEN configured in RSSHub)
        return self._fetch_via_rsshub(username)

    def _fetch_via_syndication(self, username: str) -> List[Dict[str, Any]]:
        """Fetch tweets from the public Twitter Syndication API."""
        syndication_url = self.SYNDICATION_URL.format(username=username)
        print(f"    📡 Twitter Syndication: {syndication_url}")

        try:
            response = self.get(syndication_url, timeout=15)
            html = response.text

            # Extract __NEXT_DATA__ JSON from the HTML page
            match = re.search(
                r'<script\s+id="__NEXT_DATA__"\s+type="application/json">\s*({.+?})\s*</script>',
                html, re.DOTALL
            )
            if not match:
                print("    ⚠️  Cannot find __NEXT_DATA__ in Syndication response")
                self.last_error = "No __NEXT_DATA__ in Syndication response"
                return []

            data = json.loads(match.group(1))
            timeline = (data.get("props", {})
                            .get("pageProps", {})
                            .get("timeline", {}))

            # timeline.entries[] contains tweet data
            entries = timeline.get("entries", [])
            if not entries:
                print("    ⚠️  No entries in Syndication timeline")
                self.last_error = "Empty timeline from Syndication API"
                return []

            # Extract user display name from first entry
            channel_title = ""

            items = []
            for entry in entries[:20]:
                content = entry.get("content", {})
                tweet = content.get("tweet", content)  # some entries nest under "tweet"

                tweet_id = tweet.get("id_str", "")
                if not tweet_id:
                    continue

                full_text = tweet.get("full_text", tweet.get("text", ""))
                created_at = tweet.get("created_at", "")
                screen_name = tweet.get("user", {}).get("screen_name", username)
                display_name = tweet.get("user", {}).get("name", "")

                if not channel_title and display_name:
                    channel_title = display_name

                # Parse created_at (format: "Thu Jun 19 02:01:31 +0000 2025")
                pub_date = ""
                if created_at:
                    try:
                        dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
                        pub_date = dt.isoformat()
                    except ValueError:
                        pass

                # Build tweet link
                link = f"https://x.com/{screen_name}/status/{tweet_id}"

                # Clean text: remove t.co URLs for cleaner title
                clean_text = re.sub(r'https?://t\.co/\S+', '', full_text).strip()
                # Truncate for title use
                title = clean_text[:120] + "..." if len(clean_text) > 120 else clean_text
                if not title:
                    title = f"Tweet by @{screen_name}"

                item_id = f"twitter_{hashlib.md5(tweet_id.encode()).hexdigest()[:12]}"
                items.append({
                    "item_id": item_id,
                    "title": title,
                    "description": full_text[:500],
                    "link": link,
                    "pub_date": pub_date,
                    "metadata": {
                        "_channel_title": channel_title or f"@{screen_name}",
                        "tweet_id": tweet_id,
                        "favorite_count": tweet.get("favorite_count", 0),
                        "retweet_count": tweet.get("retweet_count", 0),
                    }
                })

            if items:
                print(f"    ✓ Twitter: {len(items)} tweets via Syndication API")
            return items

        except Exception as e:
            self.last_error = str(e)
            print(f"    ⚠️  Twitter Syndication failed: {e}")
            return []

    def _fetch_via_rsshub(self, username: str) -> List[Dict[str, Any]]:
        """Fallback: fetch via RSSHub (requires TWITTER_AUTH_TOKEN)."""
        rsshub_url = f"{self.RSSHUB_BASE}/twitter/user/{username}"
        print(f"    📡 RSSHub fallback: {rsshub_url}")
        try:
            response = self.get(rsshub_url, timeout=10)
            ct = response.headers.get("content-type", "")
            if "xml" in ct or "rss" in ct:
                parser = NativeRSSScraper()
                return parser.parse_rss_xml(response.text, "twitter")
            else:
                self.last_error = f"Non-RSS content from RSSHub (HTTP {response.status_code})"
                return []
        except Exception as e:
            self.last_error = str(e)
            print(f"    ❌ RSSHub fallback also failed: {e}")
            return []


# ============================================================
#  Tier 1d: 知识星球 via pub-api (zero config)
# ============================================================

class ZsxqScraper(BaseScraper):
    """知识星球 scraper — uses the public API (no auth needed for public groups).

    Primary:  pub-api.zsxq.com/v2/groups/{id} (zero config)
    Fallback: RSSHub /zsxq/group/{id} (requires ZSXQ_ACCESS_TOKEN in RSSHub)
    """

    PUB_API = "https://pub-api.zsxq.com/v2/groups/{group_id}"
    RSSHUB_BASE = os.environ.get("RSSHUB_BASE_URL", "http://localhost:1200")

    def extract_user_id(self, url: str) -> Optional[str]:
        """Extract group_id from various zsxq URL formats."""
        # Direct group_id in URL: wx.zsxq.com/group/123 or m.zsxq.com/groups/123
        match = re.search(r'zsxq\.com(?:/dweb2/index)?/groups?/(\d+)', url)
        if match:
            return match.group(1)

        # Short link: t.zsxq.com/xxxxx — need to follow redirect
        if 't.zsxq.com' in url:
            return self._resolve_short_link(url)

        # group_id as query parameter
        match = re.search(r'group_id=(\d+)', url)
        if match:
            return match.group(1)

        return None

    def _resolve_short_link(self, url: str) -> Optional[str]:
        """Follow t.zsxq.com short link to extract group_id."""
        try:
            response = self.get(url, timeout=10)
            # Check final URL for group_id
            final_url = str(response.url) if hasattr(response, 'url') else ''
            match = re.search(r'/groups?/(\d+)', final_url)
            if match:
                return match.group(1)
            # Also search in page HTML
            match = re.search(r'/groups?/(\d{10,})', response.text)
            if match:
                return match.group(1)
        except Exception as e:
            print(f"    ⚠️  Cannot resolve zsxq short link: {e}")
        return None

    def fetch_items(self, url: str) -> List[Dict[str, Any]]:
        self.last_error = None
        group_id = self.extract_user_id(url)
        if not group_id:
            self.last_error = f"Cannot extract 知识星球 group_id from {url}"
            return []

        # Try public API first (zero config)
        items = self._fetch_via_pub_api(group_id)
        if items:
            return items

        # Fallback: RSSHub (needs ZSXQ_ACCESS_TOKEN configured)
        return self._fetch_via_rsshub(group_id)

    def _fetch_via_pub_api(self, group_id: str) -> List[Dict[str, Any]]:
        """Fetch topics from the public 知识星球 API."""
        api_url = self.PUB_API.format(group_id=group_id)
        print(f"    📡 知识星球 pub-api: group/{group_id}")

        try:
            response = self.get(
                api_url,
                timeout=10,
                headers={
                    "Origin": "https://wx.zsxq.com",
                    "Referer": "https://wx.zsxq.com/",
                }
            )
            data = response.json()

            if not data.get("succeeded"):
                self.last_error = data.get("info", "API returned failure")
                return []

            resp = data.get("resp_data", {})
            group = resp.get("group", {})
            group_name = group.get("name", "")
            topics = resp.get("topics", [])

            if not topics:
                print("    ⚠️  No topics in pub-api response")
                self.last_error = "Empty topics from pub-api"
                return []

            items = []
            for topic in topics[:20]:
                topic_id = str(topic.get("topic_id", ""))
                if not topic_id:
                    continue

                # Extract text from talk/question/answer
                talk = topic.get("talk", {})
                question = topic.get("question", {})
                text = ""
                if talk:
                    text = talk.get("text", "")
                elif question:
                    text = question.get("text", "")

                title = topic.get("title", "") or text[:120]
                if not title:
                    title = f"知识星球主题 #{topic_id[-6:]}"

                # Clean title
                title = title.replace("\n", " ").strip()
                if len(title) > 120:
                    title = title[:120] + "..."

                # Parse create_time
                pub_date = ""
                create_time = topic.get("create_time", "")
                if create_time:
                    try:
                        dt = datetime.fromisoformat(create_time)
                        pub_date = dt.isoformat()
                    except ValueError:
                        pass

                link = f"https://wx.zsxq.com/topic/{topic_id}"
                item_id = f"zsxq_{hashlib.md5(topic_id.encode()).hexdigest()[:12]}"

                # Author
                author = ""
                owner = (talk or question).get("owner", {})
                if owner:
                    author = owner.get("name", "")

                items.append({
                    "item_id": item_id,
                    "title": title,
                    "description": text[:500] if text else "",
                    "link": link,
                    "pub_date": pub_date,
                    "metadata": {
                        "_channel_title": group_name,
                        "topic_id": topic_id,
                        "author": author,
                        "likes_count": topic.get("likes_count", 0),
                    }
                })

            if items:
                print(f"    ✓ 知识星球: {len(items)} topics via pub-api")
            return items

        except Exception as e:
            self.last_error = str(e)
            print(f"    ⚠️  知识星球 pub-api failed: {e}")
            return []

    def _fetch_via_rsshub(self, group_id: str) -> List[Dict[str, Any]]:
        """Fallback: fetch via RSSHub (requires ZSXQ_ACCESS_TOKEN)."""
        rsshub_url = f"{self.RSSHUB_BASE}/zsxq/group/{group_id}"
        print(f"    📡 RSSHub fallback: {rsshub_url}")
        try:
            response = self.get(rsshub_url, timeout=10)
            ct = response.headers.get("content-type", "")
            if "xml" in ct or "rss" in ct:
                parser = NativeRSSScraper()
                return parser.parse_rss_xml(response.text, "zsxq")
            else:
                self.last_error = f"Non-RSS from RSSHub (HTTP {response.status_code})"
                return []
        except Exception as e:
            self.last_error = str(e)
            print(f"    ❌ RSSHub fallback also failed: {e}")
            return []


# ============================================================

class ScraperFactory:
    """Factory to get appropriate scraper for a platform"""

    @staticmethod
    def detect_platform(url: str) -> str:
        """Detect platform from URL"""
        url_lower = url.lower()

        if "bilibili.com" in url_lower:
            return "bilibili"
        elif "xiaohongshu.com" in url_lower or "xhslink.com" in url_lower:
            return "xiaohongshu"
        elif "weibo.com" in url_lower:
            return "weibo"
        elif "youtube.com" in url_lower or "youtu.be" in url_lower:
            return "youtube"
        elif "vimeo.com" in url_lower:
            return "vimeo"
        elif "behance.net" in url_lower:
            return "behance"
        elif "douyin.com" in url_lower:
            return "douyin"
        elif "x.com" in url_lower or "twitter.com" in url_lower:
            return "twitter"
        elif "zsxq.com" in url_lower:
            return "zsxq"
        else:
            return "unknown"

    @staticmethod
    def get_scraper(platform: str) -> Optional[BaseScraper]:
        """Get scraper instance for platform"""
        scrapers = {
            "bilibili": BilibiliScraper,
            "xiaohongshu": XiaohongshuScraper,
            "weibo": WeiboScraper,
            "youtube": YouTubeScraper,
            "vimeo": VimeoScraper,
            "behance": BehanceScraper,
            "douyin": DouyinScraper,
            "twitter": TwitterScraper,
            "zsxq": ZsxqScraper,
        }

        scraper_class = scrapers.get(platform.lower())
        return scraper_class() if scraper_class else None
