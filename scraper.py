import os
import re
import json
import time
import logging
from datetime import datetime
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests

# ── Logging EN BAŞTA ──────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            f"logs/scraper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            encoding="utf-8"
        ),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# Gereksiz logları sustur
logging.getLogger("seleniumwire").setLevel(logging.ERROR)
logging.getLogger("hpack").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("selenium").setLevel(logging.ERROR)
logging.getLogger("WDM").setLevel(logging.ERROR)

# ── Ayarlar ───────────────────────────────────────────
TARGET_URL = os.environ.get("TARGET_URL", "").strip()
if not TARGET_URL:
    TARGET_URL = "https://atomsportv494.top"

OUTPUT_FILE  = "playlist.m3u"
STATS_FILE   = "stats.json"
CHROMEDRIVER = os.environ.get("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
CHROME_BIN   = os.environ.get("CHROME_BIN", "/usr/local/bin/google-chrome")
PAGE_WAIT    = 15
STREAM_WAIT  = 15

log.info(f"🎯 Hedef URL: {TARGET_URL}")

# ── Selenium ──────────────────────────────────────────
try:
    from seleniumwire import webdriver
    WIRE = True
    log.info("✅ SeleniumWire aktif")
except ImportError:
    from selenium import webdriver
    WIRE = False
    log.warning("⚠️ SeleniumWire yok")

from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ═══════════════════════════════════════════════════════
#  YARDIMCI FONKSİYONLAR
# ═══════════════════════════════════════════════════════
def is_m3u8(url):
    """Kesin m3u8 kontrolü - sadece .m3u8 ile biten veya .m3u8? içeren"""
    if not url or not isinstance(url, str):
        return False
    url_lower = url.lower()
    return url_lower.endswith(".m3u8") or ".m3u8?" in url_lower


def clean_url(url):
    return url.strip().strip("'\"").rstrip("\\")


# ═══════════════════════════════════════════════════════
#  DRIVER
# ═══════════════════════════════════════════════════════
def get_driver():
    log.info(f"🔧 Driver başlatılıyor...")

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--autoplay-policy=no-user-gesture-required")
    options.add_argument("--mute-audio")
    options.add_argument("--disable-web-security")
    options.add_argument("--allow-running-insecure-content")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-notifications")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    if os.path.exists(CHROME_BIN):
        options.binary_location = CHROME_BIN

    service = Service(executable_path=CHROMEDRIVER)

    if WIRE:
        sw_options = {
            "verify_ssl": False,
            "suppress_connection_errors": True,
        }
        driver = webdriver.Chrome(
            service=service,
            options=options,
            seleniumwire_options=sw_options
        )
    else:
        driver = webdriver.Chrome(service=service, options=options)

    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    driver.set_page_load_timeout(30)
    log.info("✅ Driver başlatıldı")
    return driver


# ═══════════════════════════════════════════════════════
#  M3U8 ÇIKARMA
# ═══════════════════════════════════════════════════════
M3U8_PATTERNS = [
    r'https?://[^\s\'"<>()\[\]{}\\]+\.m3u8(?:\?[^\s\'"<>()\[\]{}\\]*)?',
    r'["\']([^"\']*\.m3u8(?:\?[^"\']*)?)["\']',
    r'src\s*[=:]\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    r'file\s*[=:]\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    r'url\s*[=:]\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    r'source\s*[=:]\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    r'stream\s*[=:]\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    r'hls\s*[=:]\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
]

def extract_m3u8(text, base_url=""):
    """Sadece .m3u8 URL'lerini çıkar"""
    found = set()
    if not text:
        return found

    for pattern in M3U8_PATTERNS:
        try:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                url = clean_url(match if isinstance(match, str) else match[0])

                if not url or len(url) < 15:
                    continue

                # Kesin m3u8 kontrolü
                if not is_m3u8(url):
                    continue

                if url.startswith("http"):
                    found.add(url)
                elif url.startswith("//"):
                    found.add("https:" + url)
                elif url.startswith("/") and base_url:
                    candidate = urljoin(base_url, url)
                    if is_m3u8(candidate):
                        found.add(candidate)

        except Exception:
            pass

    return found


def decode_base64(text):
    """Base64 decode - sadece m3u8 içeriyorsa işle"""
    import base64
    found = set()
    if not text:
        return found

    for pattern in [
        r'atob\(["\']([A-Za-z0-9+/=]+)["\']\)',
        r'base64,([A-Za-z0-9+/=]{30,})',
    ]:
        for match in re.findall(pattern, text):
            try:
                decoded = base64.b64decode(match).decode("utf-8", errors="ignore")
                if ".m3u8" in decoded.lower():
                    found.update(extract_m3u8(decoded))
            except Exception:
                pass

    return found


# ═══════════════════════════════════════════════════════
#  NETWORK YAKALAMA - SADECE M3U8
# ═══════════════════════════════════════════════════════
def capture_network(driver, wait=STREAM_WAIT):
    """Network'ten SADECE .m3u8 linklerini yakala"""
    if not WIRE:
        return set()

    log.info(f"  📡 Network bekleniyor ({wait}s)...")
    time.sleep(wait)

    found = set()

    for req in driver.requests:
        url = req.url

        # Sadece URL'de .m3u8 geçenler - kesin kontrol
        if is_m3u8(url):
            found.add(url)
            log.info(f"  🎯 [M3U8] {url}")

    log.info(f"  📡 Bulunan M3U8: {len(found)}")
    return found


# ═══════════════════════════════════════════════════════
#  JAVASCRIPT TARAMA - SADECE M3U8
# ═══════════════════════════════════════════════════════
JS_SCRIPT = """
(function() {
    var found = [];

    // 1. Video elementleri
    try {
        document.querySelectorAll('video,source').forEach(function(el) {
            if (el.src && el.src.includes('.m3u8')) found.push(el.src);
            if (el.currentSrc && el.currentSrc.includes('.m3u8')) found.push(el.currentSrc);
        });
    } catch(e) {}

    // 2. HTML içinde ara
    try {
        var html = document.documentElement.innerHTML;
        var m = html.match(/https?:\\/\\/[^\\s'"<>()\\[\\]{}\\\\]+\\.m3u8(?:\\?[^\\s'"<>()\\[\\]{}\\\\]*)?/gi);
        if (m) found = found.concat(m);
    } catch(e) {}

    // 3. JWPlayer
    try {
        if (typeof jwplayer !== 'undefined') {
            var jw = jwplayer();
            if (jw.getPlaylist) {
                jw.getPlaylist().forEach(function(item) {
                    if (item.file && item.file.includes('.m3u8')) found.push(item.file);
                    if (item.sources) {
                        item.sources.forEach(function(s) {
                            if (s.file && s.file.includes('.m3u8')) found.push(s.file);
                        });
                    }
                });
            }
            try {
                var curr = jw.getPlaylistItem();
                if (curr && curr.file && curr.file.includes('.m3u8')) found.push(curr.file);
            } catch(e2) {}
        }
    } catch(e) {}

    // 4. Video.js
    try {
        if (typeof videojs !== 'undefined') {
            videojs.getAllPlayers().forEach(function(p) {
                var s = p.src();
                if (s && s.includes('.m3u8')) found.push(s);
            });
        }
    } catch(e) {}

    // 5. Hls.js
    try {
        for (var k in window) {
            try {
                var v = window[k];
                if (v && typeof v === 'object') {
                    if (v.url && typeof v.url === 'string' && v.url.includes('.m3u8'))
                        found.push(v.url);
                    if (v.src && typeof v.src === 'string' && v.src.includes('.m3u8'))
                        found.push(v.src);
                    if (v.streamUrl && typeof v.streamUrl === 'string' && v.streamUrl.includes('.m3u8'))
                        found.push(v.streamUrl);
                    if (v.hlsUrl && typeof v.hlsUrl === 'string' && v.hlsUrl.includes('.m3u8'))
                        found.push(v.hlsUrl);
                }
            } catch(e) {}
        }
    } catch(e) {}

    // 6. Config objeleri
    try {
        ['config','playerConfig','streamConfig','videoConfig',
         'hlsConfig','options','settings','setup','params'].forEach(function(name) {
            try {
                var val = JSON.stringify(window[name] || {});
                if (val && val.includes('.m3u8')) {
                    var m2 = val.match(/https?:\\/\\/[^\\s'"<>\\\\]+\\.m3u8(?:\\?[^\\s'"<>\\\\]*)?/gi);
                    if (m2) found = found.concat(m2);
                }
            } catch(e) {}
        });
    } catch(e) {}

    // 7. localStorage
    try {
        for (var i = 0; i < localStorage.length; i++) {
            var lv = localStorage.getItem(localStorage.key(i)) || '';
            if (lv.includes('.m3u8')) {
                var m3 = lv.match(/https?:\\/\\/[^\\s'"]+\\.m3u8(?:\\?[^\\s'"]*)?/gi);
                if (m3) found = found.concat(m3);
            }
        }
    } catch(e) {}

    // Sadece .m3u8 ile biten veya .m3u8? içerenleri döndür
    return [...new Set(found.filter(function(u) {
        if (!u || typeof u !== 'string') return false;
        if (!u.startsWith('http')) return false;
        var lower = u.toLowerCase();
        return lower.endsWith('.m3u8') || lower.indexOf('.m3u8?') !== -1;
    }))];
})();
"""

def scan_js(driver):
    """JavaScript'ten SADECE m3u8 çıkar"""
    found = set()
    try:
        results = driver.execute_script(JS_SCRIPT)
        if results:
            for url in results:
                if is_m3u8(url):
                    found.add(url)
                    log.info(f"  🎯 [JS] {url}")
    except Exception as e:
        log.debug(f"JS hatası: {e}")
    return found


# ═══════════════════════════════════════════════════════
#  IFRAME TARAMA
# ═══════════════════════════════════════════════════════
def scan_iframes(driver, base_url, depth=2):
    if depth <= 0:
        return set()

    found = set()

    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        log.info(f"  📦 {len(iframes)} iframe")

        for i, iframe in enumerate(iframes):
            try:
                src = iframe.get_attribute("src") or "blob/srcdoc"
                log.info(f"  [iframe {i+1}] {src}")

                driver.switch_to.frame(iframe)
                time.sleep(2)

                found.update(scan_js(driver))

                src_html = driver.page_source
                found.update(extract_m3u8(src_html, base_url))
                found.update(decode_base64(src_html))

                if depth > 1:
                    found.update(scan_iframes(driver, base_url, depth - 1))

                driver.switch_to.default_content()

            except Exception as e:
                log.debug(f"iframe[{i}] hatası: {e}")
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass

    except Exception as e:
        log.debug(f"iframe tarama hatası: {e}")

    return found


# ═══════════════════════════════════════════════════════
#  PLAY BUTONU
# ═══════════════════════════════════════════════════════
def click_play(driver):
    selectors = [
        ".play-button", ".btn-play", "#play-button",
        ".jw-icon-playback", ".vjs-play-button",
        ".fp-play", ".plyr__control--overlaid",
        "[class*='play-btn']", "[class*='play_btn']",
        "[class*='play-icon']", "[aria-label='Play']",
        "[title='Play']", "button.play", ".overlay-play",
        ".play-overlay", "#player .play",
    ]

    for sel in selectors:
        try:
            el = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
            )
            el.click()
            log.info(f"  ▶️ Tıklandı: {sel}")
            time.sleep(3)
            return True
        except Exception:
            pass

    try:
        driver.execute_script("""
            document.querySelectorAll('video').forEach(function(v) {
                v.muted = true;
                v.play().catch(function(e) {});
            });
        """)
        log.info("  ▶️ JS ile video oynatıldı")
        time.sleep(3)
        return True
    except Exception:
        pass

    return False


# ═══════════════════════════════════════════════════════
#  REQUESTS FALLBACK
# ═══════════════════════════════════════════════════════
def scrape_with_requests(url):
    found = set()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": TARGET_URL,
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        found.update(extract_m3u8(resp.text, url))
        found.update(decode_base64(resp.text))

        soup = BeautifulSoup(resp.text, "html.parser")
        for script in soup.find_all("script", src=True):
            try:
                s_url  = urljoin(url, script["src"])
                s_resp = requests.get(s_url, headers=headers, timeout=10)
                found.update(extract_m3u8(s_resp.text, url))
            except Exception:
                pass

    except Exception as e:
        log.debug(f"requests hatası: {e}")

    return found


# ═══════════════════════════════════════════════════════
#  KANAL LİNKLERİ
# ═══════════════════════════════════════════════════════
def get_channel_links(driver):
    log.info(f"🌐 Ana sayfa: {TARGET_URL}")

    try:
        driver.get(TARGET_URL)
        WebDriverWait(driver, PAGE_WAIT).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except Exception as e:
        log.warning(f"Sayfa yükleme: {e}")

    time.sleep(5)

    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0)")
        time.sleep(1)
    except Exception:
        pass

    soup  = BeautifulSoup(driver.page_source, "html.parser")
    links = set()
    skip  = [".jpg",".png",".gif",".css",".js",".ico",".xml",".txt",".pdf"]

    for a in soup.find_all("a", href=True):
        href     = a["href"].strip()
        full_url = urljoin(TARGET_URL, href)
        parsed   = urlparse(full_url)
        target   = urlparse(TARGET_URL)

        if parsed.netloc == target.netloc:
            if not any(full_url.lower().endswith(x) for x in skip):
                if full_url != TARGET_URL and "#" not in full_url:
                    links.add(full_url)

    links.add(TARGET_URL)
    log.info(f"📋 {len(links)} link bulundu")
    return list(links)


# ═══════════════════════════════════════════════════════
#  TEK KANAL TARA
# ═══════════════════════════════════════════════════════
def scrape_channel(driver, url):
    log.info(f"\n{'─'*50}")
    log.info(f"🔍 {url}")
    log.info(f"{'─'*50}")

    found = set()

    try:
        if WIRE:
            try:
                del driver.requests
            except Exception:
                pass

        driver.get(url)

        try:
            WebDriverWait(driver, PAGE_WAIT).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception:
            pass

        time.sleep(3)

        # Play
        click_play(driver)

        # 1. Network - sadece m3u8
        if WIRE:
            found.update(capture_network(driver, STREAM_WAIT))

        # 2. JS - sadece m3u8
        found.update(scan_js(driver))

        # 3. iframe - sadece m3u8
        found.update(scan_iframes(driver, url))

        # 4. Sayfa kaynağı - sadece m3u8
        page = driver.page_source
        found.update(extract_m3u8(page, url))
        found.update(decode_base64(page))

        # 5. Script tagları - sadece m3u8
        soup = BeautifulSoup(page, "html.parser")
        for tag in soup.find_all("script"):
            c = tag.string or ""
            if c and ".m3u8" in c.lower():
                found.update(extract_m3u8(c, url))
                found.update(decode_base64(c))

        # 6. Requests fallback
        if not found:
            log.info("  🔄 Requests fallback...")
            found.update(scrape_with_requests(url))

        # Son filtre - kesinlikle sadece m3u8
        found = {u for u in found if is_m3u8(u)}

        if found:
            log.info(f"  ✅ {len(found)} M3U8 bulundu:")
            for x in found:
                log.info(f"     → {x}")
        else:
            log.info(f"  ❌ M3U8 bulunamadı")

        try:
            name = driver.title.strip()[:60] or "Kanal"
        except Exception:
            name = urlparse(url).path.strip("/").replace("/", "_") or "Kanal"

        return name, list(found)

    except Exception as e:
        log.error(f"  ❌ Hata: {e}")
        return "Hata", []


# ═══════════════════════════════════════════════════════
#  M3U OLUŞTUR
# ═══════════════════════════════════════════════════════
def create_m3u(channels):
    now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "#EXTM3U\n",
        f"# Guncelleme: {now} UTC\n",
        f"# Toplam: {len(channels)} kanal\n\n",
    ]
    for ch in channels:
        name  = ch.get("name", "Kanal")
        url   = ch.get("url", "")
        group = ch.get("group", "Genel")
        logo  = ch.get("logo", "")

        # Son güvenlik - sadece m3u8
        if not url or not is_m3u8(url):
            log.warning(f"⛔ Atlandı: {url}")
            continue

        extinf = f'#EXTINF:-1 tvg-name="{name}"'
        if logo:
            extinf += f' tvg-logo="{logo}"'
        extinf += f' group-title="{group}",{name}\n'

        lines.append(extinf)
        lines.append(f"{url}\n\n")

    return "".join(lines)


# ═══════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════
def main():
    log.info("=" * 55)
    log.info("   M3U8 Scraper")
    log.info(f"   Hedef : {TARGET_URL}")
    log.info(f"   Wire  : {WIRE}")
    log.info("=" * 55)

    start    = time.time()
    driver   = None
    channels = []
    seen     = set()

    try:
        driver = get_driver()
        links  = get_channel_links(driver)

        log.info(f"\n📺 {len(links)} sayfa taranacak\n")

        for i, link in enumerate(links, 1):
            log.info(f"\n[{i}/{len(links)}]")

            name, m3u8_list = scrape_channel(driver, link)

            for j, m3u8 in enumerate(m3u8_list, 1):
                # Kesin m3u8 kontrolü
                if not is_m3u8(m3u8):
                    continue

                if m3u8 in seen:
                    continue

                seen.add(m3u8)
                ch_name = name if len(m3u8_list) == 1 else f"{name} {j}"
                channels.append({
                    "name" : ch_name,
                    "url"  : m3u8,
                    "group": "Spor",
                    "logo" : ""
                })
                log.info(f"  ✅ Eklendi: {m3u8}")

            time.sleep(2)

    except Exception as e:
        log.error(f"❌ Genel hata: {e}", exc_info=True)

    finally:
        if driver:
            try:
                driver.quit()
                log.info("🔒 Driver kapatıldı")
            except Exception:
                pass

    # Sonuç
    elapsed = round(time.time() - start, 1)
    log.info(f"\n{'='*55}")
    log.info(f"🏁 Tamamlandı!")
    log.info(f"📺 Kanal  : {len(channels)}")
    log.info(f"⏱️  Süre   : {elapsed}s")
    log.info(f"{'='*55}")

    # Kaydet
    content = create_m3u(channels)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    log.info(f"✅ {OUTPUT_FILE} kaydedildi")

    stats = {
        "last_update"    : datetime.now().isoformat(),
        "total_channels" : len(channels),
        "duration_sec"   : elapsed,
        "source_url"     : TARGET_URL,
        "channels"       : channels
    }
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    log.info(f"✅ {STATS_FILE} kaydedildi")

    if not channels:
        log.warning("⚠️ Hiç M3U8 bulunamadı!")


if __name__ == "__main__":
    main()
