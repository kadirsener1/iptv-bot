import os
import re
import json
import time
import logging
from datetime import datetime
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

# ── Logging ÖNCE Tanımla ──────────────────────────────
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

# ── Ayarlar ───────────────────────────────────────────
TARGET_URL      = os.environ.get("TARGET_URL", "https://atomsportv494.top")
OUTPUT_FILE     = "playlist.m3u"
STATS_FILE      = "stats.json"
CHROMEDRIVER    = os.environ.get("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
CHROME_BIN      = os.environ.get("CHROME_BIN", "/usr/local/bin/google-chrome")
PAGE_WAIT       = 15
STREAM_WAIT     = 12

# ── Selenium Import ───────────────────────────────────
try:
    from seleniumwire import webdriver
    WIRE = True
    log.info("✅ SeleniumWire aktif")
except ImportError:
    from selenium import webdriver
    WIRE = False
    log.info("⚠️ SeleniumWire yok, normal Selenium kullanılıyor")

from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ═════════════════════════════════════════════════════
#                   DRIVER
# ═════════════════════════════════════════════════════
def get_driver():
    log.info("🔧 Driver başlatılıyor...")
    log.info(f"   Chrome  : {CHROME_BIN}")
    log.info(f"   Driver  : {CHROMEDRIVER}")

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
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Chrome binary
    if os.path.exists(CHROME_BIN):
        options.binary_location = CHROME_BIN
        log.info(f"✅ Chrome binary bulundu")
    else:
        log.warning(f"⚠️ Chrome binary bulunamadı: {CHROME_BIN}")

    # ChromeDriver path
    driver_path = CHROMEDRIVER
    if not os.path.exists(driver_path):
        import shutil
        found = shutil.which("chromedriver")
        driver_path = found if found else "chromedriver"
        log.warning(f"⚠️ ChromeDriver path değişti: {driver_path}")

    service = Service(executable_path=driver_path)

    try:
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
            driver = webdriver.Chrome(
                service=service,
                options=options
            )

        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        driver.set_page_load_timeout(30)
        log.info("✅ Driver başarıyla başlatıldı")
        return driver

    except Exception as e:
        log.error(f"❌ Driver başlatma hatası: {e}")
        raise


# ═════════════════════════════════════════════════════
#                   M3U8 ÇIKARMA
# ═════════════════════════════════════════════════════
M3U8_PATTERNS = [
    r'https?://[^\s\'"<>\\]+\.m3u8[^\s\'"<>\\]*',
    r'["\']([^"\']*\.m3u8[^"\']*)["\']',
    r'src\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    r'file\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    r'url\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    r'hls\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    r'stream\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    r'source\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    r'playlist\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
]

def extract_m3u8(text, base_url=""):
    """Metin içinden m3u8 URL'lerini çıkar"""
    found = set()
    for pattern in M3U8_PATTERNS:
        try:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                url = match if isinstance(match, str) else match[0]
                url = url.strip().strip("'\"").rstrip("\\")
                if not url or len(url) < 10:
                    continue
                if url.startswith("http"):
                    found.add(url)
                elif url.startswith("//"):
                    found.add("https:" + url)
                elif url.startswith("/") and base_url:
                    found.add(urljoin(base_url, url))
        except Exception as e:
            log.debug(f"Pattern hatası: {e}")
    return found


def decode_base64(text):
    """Base64 encoded URL'leri çöz"""
    import base64
    found = set()
    patterns = [
        r'atob\(["\']([A-Za-z0-9+/=]+)["\']\)',
        r'base64,([A-Za-z0-9+/=]{20,})',
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            try:
                decoded = base64.b64decode(match).decode("utf-8", errors="ignore")
                found.update(extract_m3u8(decoded))
            except Exception:
                pass
    return found


# ═════════════════════════════════════════════════════
#                   NETWORK YAKALAMA
# ═════════════════════════════════════════════════════
def capture_network(driver, wait=STREAM_WAIT):
    """Network isteklerinden m3u8 yakala"""
    if not WIRE:
        return set()

    log.info(f"  📡 Network bekleniyor ({wait}s)...")
    time.sleep(wait)

    found = set()
    keywords = [".m3u8", ".ts", "stream", "hls", "live", "playlist", "chunk"]

    log.info(f"  📡 Toplam istek: {len(driver.requests)}")

    for req in driver.requests:
        url = req.url
        if ".m3u8" in url:
            found.add(url)
            log.info(f"  🎯 [Network] {url}")
            continue

        # Response body'den ara
        try:
            if req.response and req.response.body:
                body = req.response.body.decode("utf-8", errors="ignore")
                if ".m3u8" in body:
                    urls = extract_m3u8(body)
                    found.update(urls)
                    for u in urls:
                        log.info(f"  🎯 [Response] {u}")
        except Exception:
            pass

    return found


# ═════════════════════════════════════════════════════
#                   JAVASCRIPT TARAMA
# ═════════════════════════════════════════════════════
JS_EXTRACT = """
(function() {
    var found = [];

    // Video elementleri
    document.querySelectorAll('video, source').forEach(function(el) {
        if (el.src && el.src.includes('.m3u8')) found.push(el.src);
        if (el.currentSrc && el.currentSrc.includes('.m3u8')) found.push(el.currentSrc);
    });

    // innerHTML tara
    var html = document.documentElement.innerHTML;
    var matches = html.match(/https?:\\/\\/[^\\s'"<>\\\\]+\\.m3u8[^\\s'"<>\\\\]*/gi);
    if (matches) found = found.concat(matches);

    // JWPlayer
    try {
        if (typeof jwplayer !== 'undefined') {
            var jw = jwplayer();
            if (jw.getPlaylist) {
                jw.getPlaylist().forEach(function(item) {
                    if (item.file) found.push(item.file);
                    if (item.sources) item.sources.forEach(function(s) {
                        if (s.file) found.push(s.file);
                    });
                });
            }
        }
    } catch(e) {}

    // Video.js
    try {
        if (typeof videojs !== 'undefined') {
            videojs.getAllPlayers().forEach(function(p) {
                var src = p.src();
                if (src && src.includes('.m3u8')) found.push(src);
            });
        }
    } catch(e) {}

    // Hls.js
    try {
        for (var key in window) {
            try {
                var obj = window[key];
                if (obj && typeof obj === 'object') {
                    if (obj.url && obj.url.includes('.m3u8')) found.push(obj.url);
                    if (obj.src && obj.src.includes('.m3u8')) found.push(obj.src);
                    if (obj.streamUrl && obj.streamUrl.includes('.m3u8')) found.push(obj.streamUrl);
                }
            } catch(e) {}
        }
    } catch(e) {}

    // Window değişkenleri
    try {
        var keys = Object.keys(window);
        keys.forEach(function(key) {
            try {
                var val = JSON.stringify(window[key]);
                if (val && val.includes('.m3u8')) {
                    var m = val.match(/https?:\\/\\/[^\\s'"<>\\\\]+\\.m3u8[^\\s'"<>\\\\]*/gi);
                    if (m) found = found.concat(m);
                }
            } catch(e) {}
        });
    } catch(e) {}

    // Config objeleri
    try {
        ['config', 'playerConfig', 'streamConfig', 'videoConfig',
         'hlsConfig', 'options', 'settings', 'player_vars'].forEach(function(name) {
            try {
                var val = JSON.stringify(window[name]);
                if (val && val.includes('.m3u8')) {
                    var m = val.match(/https?:\\/\\/[^\\s'"<>\\\\]+\\.m3u8[^\\s'"<>\\\\]*/gi);
                    if (m) found = found.concat(m);
                }
            } catch(e) {}
        });
    } catch(e) {}

    return [...new Set(found.filter(function(u) {
        return u && u.includes('.m3u8');
    }))];
})();
"""

def scan_js(driver):
    """JavaScript'ten m3u8 çıkar"""
    found = set()
    try:
        results = driver.execute_script(JS_EXTRACT)
        if results:
            for url in results:
                if url and ".m3u8" in url:
                    found.add(url)
                    log.info(f"  🎯 [JS] {url}")
    except Exception as e:
        log.debug(f"  JS tarama hatası: {e}")
    return found


# ═════════════════════════════════════════════════════
#                   IFRAME TARAMA
# ═════════════════════════════════════════════════════
def scan_iframes(driver, base_url, depth=2):
    """iframe'leri tara"""
    if depth <= 0:
        return set()

    found = set()

    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        log.info(f"  📦 {len(iframes)} iframe bulundu")

        for i, iframe in enumerate(iframes):
            try:
                src = iframe.get_attribute("src") or ""
                log.info(f"  [iframe {i+1}] {src}")

                driver.switch_to.frame(iframe)
                time.sleep(2)

                # JS tara
                found.update(scan_js(driver))

                # Kaynak tara
                source = driver.page_source
                found.update(extract_m3u8(source, base_url))
                found.update(decode_base64(source))

                # Nested iframe
                if depth > 1:
                    found.update(scan_iframes(driver, base_url, depth - 1))

                driver.switch_to.default_content()

            except Exception as e:
                log.debug(f"  iframe[{i}] hatası: {e}")
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass

    except Exception as e:
        log.debug(f"  iframe tarama hatası: {e}")

    return found


# ═════════════════════════════════════════════════════
#                   PLAY BUTONU
# ═════════════════════════════════════════════════════
def click_play(driver):
    """Play butonuna tıkla"""
    selectors = [
        ".play-button", ".btn-play", "#play-button",
        ".jw-icon-playback", ".vjs-play-button",
        ".fp-play", ".plyr__control--overlaid",
        "[class*='play-btn']", "[class*='play_btn']",
        "[aria-label='Play']", "[title='Play']",
        "button.play", ".overlay-play",
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

    # JS ile oynat
    try:
        driver.execute_script("""
            document.querySelectorAll('video').forEach(function(v) {
                v.muted = true;
                v.play().catch(function(e) {});
            });
        """)
        log.info("  ▶️ Video JS ile başlatıldı")
        time.sleep(3)
        return True
    except Exception:
        pass

    return False


# ═════════════════════════════════════════════════════
#                   KANAL LİNKLERİ
# ═════════════════════════════════════════════════════
def get_channel_links(driver):
    """Ana sayfadan kanal linklerini topla"""
    log.info(f"🌐 Ana sayfa: {TARGET_URL}")

    try:
        driver.get(TARGET_URL)
        WebDriverWait(driver, PAGE_WAIT).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except Exception as e:
        log.warning(f"Sayfa yüklenme hatası: {e}")

    time.sleep(5)

    # Lazy load için scroll
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0)")
        time.sleep(1)
    except Exception:
        pass

    soup  = BeautifulSoup(driver.page_source, "html.parser")
    links = set()

    for a in soup.find_all("a", href=True):
        href     = a["href"].strip()
        full_url = urljoin(TARGET_URL, href)
        parsed   = urlparse(full_url)
        target   = urlparse(TARGET_URL)

        if parsed.netloc == target.netloc:
            skip_ext = [".jpg",".png",".gif",".css",".js",".ico",".xml",".txt"]
            if not any(full_url.lower().endswith(x) for x in skip_ext):
                if full_url != TARGET_URL:
                    links.add(full_url)

    links.add(TARGET_URL)
    log.info(f"📋 {len(links)} kanal linki bulundu")
    return list(links)


# ═════════════════════════════════════════════════════
#                   TEK KANAL TARA
# ═════════════════════════════════════════════════════
def scrape_channel(driver, url):
    """Bir kanalı tara"""
    log.info(f"\n{'─'*50}")
    log.info(f"🔍 {url}")
    log.info(f"{'─'*50}")

    found = set()

    try:
        # Önceki istekleri temizle
        if WIRE:
            try:
                del driver.requests
            except Exception:
                pass

        # Sayfayı aç
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

        # 1. Network
        if WIRE:
            found.update(capture_network(driver, STREAM_WAIT))

        # 2. JavaScript
        found.update(scan_js(driver))

        # 3. iframe
        found.update(scan_iframes(driver, url))

        # 4. Sayfa kaynağı
        source = driver.page_source
        found.update(extract_m3u8(source, url))
        found.update(decode_base64(source))

        # 5. Script tagları
        soup = BeautifulSoup(source, "html.parser")
        for script in soup.find_all("script"):
            content = script.string or ""
            if content:
                found.update(extract_m3u8(content, url))
                found.update(decode_base64(content))

        # Kanal adı
        try:
            name = driver.title.strip()[:60] or "Kanal"
        except Exception:
            name = urlparse(url).path.strip("/").replace("/", "_") or "Kanal"

        if found:
            log.info(f"  ✅ {len(found)} M3U8 bulundu")
        else:
            log.info(f"  ❌ M3U8 bulunamadı")

        return name, list(found)

    except Exception as e:
        log.error(f"  ❌ Hata: {e}")
        return "Hata", []


# ═════════════════════════════════════════════════════
#                   M3U DOSYASI
# ═════════════════════════════════════════════════════
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

        if not url:
            continue

        extinf  = f'#EXTINF:-1 tvg-name="{name}"'
        extinf += f' tvg-logo="{logo}"' if logo else ""
        extinf += f' group-title="{group}",{name}\n'

        lines.append(extinf)
        lines.append(f"{url}\n\n")

    return "".join(lines)


# ═════════════════════════════════════════════════════
#                   MAIN
# ═════════════════════════════════════════════════════
def main():
    log.info("=" * 55)
    log.info("   M3U8 Scraper Baslatiliyor")
    log.info(f"   Hedef : {TARGET_URL}")
    log.info(f"   Wire  : {WIRE}")
    log.info("=" * 55)

    start    = time.time()
    driver   = None
    channels = []

    try:
        driver = get_driver()

        # Kanal linklerini al
        links = get_channel_links(driver)
        log.info(f"\n📺 {len(links)} sayfa taranacak\n")

        seen_urls = set()

        for i, link in enumerate(links, 1):
            log.info(f"\n[{i}/{len(links)}]")

            name, m3u8_list = scrape_channel(driver, link)

            for j, m3u8 in enumerate(m3u8_list, 1):
                if m3u8 in seen_urls:
                    continue
                seen_urls.add(m3u8)

                ch_name = f"{name}" if len(m3u8_list) == 1 else f"{name} {j}"
                channels.append({
                    "name" : ch_name,
                    "url"  : m3u8,
                    "group": "Spor",
                    "logo" : ""
                })

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

    # ── Sonuçlar ──────────────────────────────────────
    elapsed = round(time.time() - start, 1)
    log.info(f"\n{'='*55}")
    log.info(f"🏁 Tamamlandı!")
    log.info(f"📺 Kanal : {len(channels)}")
    log.info(f"⏱️  Süre  : {elapsed}s")
    log.info(f"{'='*55}")

    # M3U kaydet
    content = create_m3u(channels)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    log.info(f"✅ {OUTPUT_FILE} kaydedildi")

    # Stats kaydet
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
