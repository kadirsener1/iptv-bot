import os
import re
import json
import time
import logging
from datetime import datetime

# ── Logging ───────────────────────────────────────────
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

logging.getLogger("seleniumwire").setLevel(logging.ERROR)
logging.getLogger("hpack").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("selenium").setLevel(logging.ERROR)

# ── Ayarlar ───────────────────────────────────────────
BASE_URL     = "https://atomsportv494.top"
OUTPUT_FILE  = "playlist.m3u"
STATS_FILE   = "stats.json"
CHROMEDRIVER = os.environ.get("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
CHROME_BIN   = os.environ.get("CHROME_BIN", "/usr/local/bin/google-chrome")
STREAM_WAIT  = 15

# ── Taranacak Sayfalar ────────────────────────────────
PAGES = [
    {"slug": "matches?id=bein-sports-1",  "name": "beIN Sports 1",  "group": "Spor"},
    {"slug": "matches?id=bein-sports-2",  "name": "beIN Sports 2",  "group": "Spor"},
    {"slug": "matches?id=bein-sports-3",  "name": "beIN Sports 3",  "group": "Spor"},
    {"slug": "matches?id=bein-sports-4",  "name": "beIN Sports 4",  "group": "Spor"},
    {"slug": "matches?id=bein-sports-5",  "name": "beIN Sports 5",  "group": "Spor"},
    
]

# ── Selenium ──────────────────────────────────────────
try:
    from seleniumwire import webdriver
    WIRE = True
    log.info("✅ SeleniumWire aktif")
except ImportError:
    from selenium import webdriver
    WIRE = False

from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ═══════════════════════════════════════════════════════
#  YARDIMCI
# ═══════════════════════════════════════════════════════
def is_m3u8(url):
    if not url or not isinstance(url, str):
        return False
    lower = url.lower()
    return lower.endswith(".m3u8") or ".m3u8?" in lower


# ═══════════════════════════════════════════════════════
#  DRIVER
# ═══════════════════════════════════════════════════════
def get_driver():
    log.info("🔧 Driver başlatılıyor...")

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
        driver = webdriver.Chrome(
            service=service,
            options=options,
            seleniumwire_options={
                "verify_ssl": False,
                "suppress_connection_errors": True,
            }
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
#  TEK SAYFA TARA
# ═══════════════════════════════════════════════════════
def scrape_page(driver, page):
    slug  = page["slug"]
    name  = page["name"]
    url   = f"{BASE_URL}/{slug}"

    log.info(f"\n{'─'*50}")
    log.info(f"🔍 {name} → {url}")
    log.info(f"{'─'*50}")

    # Önceki istekleri temizle
    if WIRE:
        try:
            del driver.requests
        except Exception:
            pass

    # Sayfayı aç
    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except Exception as e:
        log.warning(f"  ⚠️ Sayfa yükleme: {e}")

    time.sleep(3)

    # Play butonuna tıkla
    click_play(driver)

    # Network bekle
    log.info(f"  📡 {STREAM_WAIT}s bekleniyor...")
    time.sleep(STREAM_WAIT)

    # Sadece m3u8 linklerini topla
    m3u8_url = None

    if WIRE:
        for req in driver.requests:
            if is_m3u8(req.url):
                m3u8_url = req.url
                log.info(f"  🎯 Bulundu: {m3u8_url}")
                break  # İlk m3u8'i al, dur

    # Network'te bulunamadıysa JS'den dene
    if not m3u8_url:
        m3u8_url = find_in_js(driver)

    # JS'de de bulunamadıysa sayfa kaynağından dene
    if not m3u8_url:
        m3u8_url = find_in_source(driver.page_source)

    if m3u8_url:
        log.info(f"  ✅ {name}: {m3u8_url}")
    else:
        log.info(f"  ❌ {name}: M3U8 bulunamadı")

    return m3u8_url


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
    ]
    for sel in selectors:
        try:
            el = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
            )
            el.click()
            log.info(f"  ▶️ {sel}")
            time.sleep(2)
            return
        except Exception:
            pass

    try:
        driver.execute_script("""
            document.querySelectorAll('video').forEach(function(v) {
                v.muted = true;
                v.play().catch(function(e) {});
            });
        """)
        time.sleep(2)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════
#  JS'DEN M3U8 BUL
# ═══════════════════════════════════════════════════════
def find_in_js(driver):
    try:
        result = driver.execute_script("""
            var found = null;

            // Video src
            document.querySelectorAll('video,source').forEach(function(el) {
                if (!found && el.src && el.src.toLowerCase().indexOf('.m3u8') !== -1)
                    found = el.src;
                if (!found && el.currentSrc && el.currentSrc.toLowerCase().indexOf('.m3u8') !== -1)
                    found = el.currentSrc;
            });
            if (found) return found;

            // JWPlayer
            try {
                var jw = jwplayer();
                var item = jw.getPlaylistItem();
                if (item && item.file && item.file.toLowerCase().indexOf('.m3u8') !== -1)
                    return item.file;
            } catch(e) {}

            // HTML içinde ara
            var m = document.documentElement.innerHTML.match(
                /https?:\\/\\/[^\\s'"<>]+\\.m3u8(?:\\?[^\\s'"<>]*)?/i
            );
            return m ? m[0] : null;
        """)
        if result and is_m3u8(result):
            log.info(f"  🎯 [JS] {result}")
            return result
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════
#  KAYNAK'TAN M3U8 BUL
# ═══════════════════════════════════════════════════════
def find_in_source(html):
    match = re.search(
        r'https?://[^\s\'"<>]+\.m3u8(?:\?[^\s\'"<>]*)?',
        html,
        re.IGNORECASE
    )
    if match:
        url = match.group(0)
        if is_m3u8(url):
            log.info(f"  🎯 [HTML] {url}")
            return url
    return None


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
        extinf  = f'#EXTINF:-1'
        extinf += f' tvg-name="{ch["name"]}"'
        extinf += f' group-title="{ch["group"]}"'
        extinf += f',{ch["name"]}\n'
        lines.append(extinf)
        lines.append(f'{ch["url"]}\n\n')
    return "".join(lines)


# ═══════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════
def main():
    log.info("=" * 55)
    log.info("   M3U8 Scraper")
    log.info(f"   Toplam sayfa: {len(PAGES)}")
    log.info("=" * 55)

    start    = time.time()
    driver   = None
    channels = []

    try:
        driver = get_driver()

        for i, page in enumerate(PAGES, 1):
            log.info(f"\n[{i}/{len(PAGES)}]")

            m3u8_url = scrape_page(driver, page)

            if m3u8_url and is_m3u8(m3u8_url):
                channels.append({
                    "name" : page["name"],
                    "url"  : m3u8_url,
                    "group": page["group"],
                })

            time.sleep(2)

    except Exception as e:
        log.error(f"❌ Hata: {e}", exc_info=True)

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
    log.info(f"📺 Kanal : {len(channels)}/{len(PAGES)}")
    log.info(f"⏱️  Süre  : {elapsed}s")
    log.info(f"{'='*55}")

    # M3U kaydet
    content = create_m3u(channels)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    log.info(f"✅ {OUTPUT_FILE} kaydedildi")

    # Stats kaydet
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "last_update"    : datetime.now().isoformat(),
            "total_channels" : len(channels),
            "duration_sec"   : elapsed,
            "channels"       : channels
        }, f, ensure_ascii=False, indent=2)
    log.info(f"✅ {STATS_FILE} kaydedildi")

    if not channels:
        log.warning("⚠️ Hiç M3U8 bulunamadı!")


if __name__ == "__main__":
    main()
