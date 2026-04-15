import os
import re
import json
import time
import logging
from datetime import datetime
import requests as req_lib

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


# ═══════════════════════════════════════════════════════
#  BASE URL OTOMATİK BUL (ARALIKLI)
# ═══════════════════════════════════════════════════════
MIN_NUMBER = 490   # Başlangıç numarası
MAX_NUMBER = 520   # Bitiş numarası (İhtiyacına göre artırabilirsin)

def generate_domains():
    """atomsportv490.top ile atomsportv520.top arası otomatik oluşturur"""
    domains = []
    for i in range(MIN_NUMBER, MAX_NUMBER + 1):
        domains.append(f"https://atomsportv{i}.top")
    
    # Ekstra bilinen domainler (opsiyonel)
    domains.extend([
        "https://atomsport.top",
        "https://atomsportv.top",
    ])
    return domains


def find_base_url():
    """Çalışan domaini otomatik bulur"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    log.info(f"🔎 Domain aralığı taranıyor: atomsportv{MIN_NUMBER}.top - atomsportv{MAX_NUMBER}.top")

    for domain in generate_domains():
        try:
            resp = req_lib.get(domain, headers=headers, timeout=8, allow_redirects=True)
            if resp.status_code == 200:
                final_url = resp.url.rstrip("/")
                log.info(f"  ✅ Aktif domain bulundu: {final_url}")
                return final_url
            else:
                log.debug(f"  {domain} → {resp.status_code}")
        except Exception:
            log.debug(f"  {domain} → bağlantı hatası")

    log.warning("⚠️ Hiçbir domain çalışmadı, varsayılan kullanılıyor.")
    return f"https://atomsportv{MIN_NUMBER}.top"


# ── Ayarlar ───────────────────────────────────────────
BASE_URL     = find_base_url()          # ← Otomatik bulunuyor
OUTPUT_FILE  = "playlist.m3u"
STATS_FILE   = "stats.json"
CHROMEDRIVER = os.environ.get("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
CHROME_BIN   = os.environ.get("CHROME_BIN", "/usr/local/bin/google-chrome")
STREAM_WAIT  = 8

log.info(f"🌐 Kullanılan BASE_URL: {BASE_URL}")

# ── Taranacak Sayfalar ────────────────────────────────
PAGES = [
    {"slug": "matches?id=bein-sports-1",  "name": "beIN Sports 1",  "group": "Spor"},
    {"slug": "matches?id=bein-sports-2",  "name": "beIN Sports 2",  "group": "Spor"},
    {"slug": "matches?id=bein-sports-3",  "name": "beIN Sports 3",  "group": "Spor"},
    {"slug": "matches?id=bein-sports-4",  "name": "beIN Sports 4",  "group": "Spor"},
    {"slug": "matches?id=bein-sports-5",  "name": "beIN Sports 5",  "group": "Spor"},
    {"slug": "matches?id=bein-sports-max-1",  "name": "beIN Sports Max 1",  "group": "Spor"},
    {"slug": "matches?id=bein-sports-max-2",  "name": "beIN Sports Max 2",  "group": "Spor"},
    {"slug": "matches?id=s-sport",  "name": "S Sport",  "group": "Spor"},
    {"slug": "matches?id=s-sport-2",  "name": "S Sport 2",  "group": "Spor"},
    {"slug": "matches?id=tivibu-spor-1",  "name": "Tivibu Spor 1",  "group": "Spor"},
    {"slug": "matches?id=tivibu-spor-2",  "name": "Tivibu Spor 2",  "group": "Spor"},
    {"slug": "matches?id=tivibu-spor-3",  "name": "Tivibu Spor 3",  "group": "Spor"},
    {"slug": "matches?id=tivibu-spor-4",  "name": "Tivibu Spor 4",  "group": "Spor"},
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
    slug = page["slug"]
    name = page["name"]
    url  = f"{BASE_URL}/{slug}"

    log.info(f"\n{'─'*50}")
    log.info(f"🔍 {name} → {url}")
    log.info(f"{'─'*50}")

    if WIRE:
        try:
            del driver.requests
        except Exception:
            pass

    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except Exception as e:
        log.warning(f"  ⚠️ Sayfa yükleme: {e}")

    time.sleep(2)

    click_play(driver)

    log.info(f"  📡 M3U8 bekleniyor (max {STREAM_WAIT}s)...")
    m3u8_url = None

    if WIRE:
        for elapsed in range(STREAM_WAIT):
            for req in driver.requests:
                if is_m3u8(req.url):
                    m3u8_url = req.url
                    log.info(f"  🎯 {elapsed+1}s'de bulundu: {m3u8_url}")
                    break
            if m3u8_url:
                break
            time.sleep(1)
    else:
        time.sleep(STREAM_WAIT)

    if not m3u8_url:
        m3u8_url = find_in_js(driver)

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
            time.sleep(1)
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
        time.sleep(1)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════
#  JS'DEN M3U8 BUL
# ═══════════════════════════════════════════════════════
def find_in_js(driver):
    try:
        result = driver.execute_script("""
            var found = null;

            document.querySelectorAll('video,source').forEach(function(el) {
                if (!found && el.src && el.src.toLowerCase().indexOf('.m3u8') !== -1)
                    found = el.src;
                if (!found && el.currentSrc && el.currentSrc.toLowerCase().indexOf('.m3u8') !== -1)
                    found = el.currentSrc;
            });
            if (found) return found;

            try {
                var jw = jwplayer();
                var item = jw.getPlaylistItem();
                if (item && item.file && item.file.toLowerCase().indexOf('.m3u8') !== -1)
                    return item.file;
            } catch(e) {}

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
    log.info(f"   Base URL : {BASE_URL}")
    log.info(f"   Toplam   : {len(PAGES)} sayfa")
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

            time.sleep(1)

    except Exception as e:
        log.error(f"❌ Hata: {e}", exc_info=True)

    finally:
        if driver:
            try:
                driver.quit()
                log.info("🔒 Driver kapatıldı")
            except Exception:
                pass

    elapsed = round(time.time() - start, 1)
    log.info(f"\n{'='*55}")
    log.info(f"🏁 Tamamlandı!")
    log.info(f"📺 Kanal : {len(channels)}/{len(PAGES)}")
    log.info(f"⏱️  Süre  : {elapsed}s")
    log.info(f"{'='*55}")

    content = create_m3u(channels)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    log.info(f"✅ {OUTPUT_FILE} kaydedildi")

    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "last_update"    : datetime.now().isoformat(),
            "total_channels" : len(channels),
            "duration_sec"   : elapsed,
            "base_url"       : BASE_URL,
            "channels"       : channels
        }, f, ensure_ascii=False, indent=2)
    log.info(f"✅ {STATS_FILE} kaydedildi")

    if not channels:
        log.warning("⚠️ Hiç M3U8 bulunamadı!")


if __name__ == "__main__":
    main()
