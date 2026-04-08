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
#  BASE URL OTOMATİK BUL
# ═══════════════════════════════════════════════════════
MIN_NUMBER  = 25
MAX_NUMBER  = 60
DOMAIN_BASE = "patronizle"
DOMAIN_TLD  = "cfd"

EXTRA_DOMAINS = [
    "https://patronizle29.cfd",
    "https://patronizle.cfd",
    "https://www.patronizle.cfd",
]


def generate_domains():
    domains = []
    for i in range(MIN_NUMBER, MAX_NUMBER + 1):
        domains.append(f"https://{DOMAIN_BASE}{i}.{DOMAIN_TLD}")
    domains.extend(EXTRA_DOMAINS)
    return domains


def find_base_url():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    log.info(f"🔎 Domain taranıyor: {DOMAIN_BASE}{MIN_NUMBER}.{DOMAIN_TLD} → {DOMAIN_BASE}{MAX_NUMBER}.{DOMAIN_TLD}")

    for domain in generate_domains():
        try:
            resp = req_lib.get(
                domain,
                headers=headers,
                timeout=8,
                allow_redirects=True
            )
            if resp.status_code == 200:
                final_url = resp.url.rstrip("/")
                log.info(f"  ✅ Aktif domain: {final_url}")
                return final_url
            else:
                log.debug(f"  {domain} → {resp.status_code}")
        except Exception:
            log.debug(f"  {domain} → bağlantı hatası")

    log.warning("⚠️ Çalışan domain bulunamadı, varsayılan kullanılıyor.")
    return "https://patronizle29.cfd"


# ── Ayarlar ───────────────────────────────────────────
BASE_URL     = find_base_url()
OUTPUT_FILE  = "playlist.m3u"
STATS_FILE   = "stats.json"
CHROMEDRIVER = os.environ.get("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
CHROME_BIN   = os.environ.get("CHROME_BIN",        "/usr/local/bin/google-chrome")
STREAM_WAIT  = 12

log.info(f"🌐 BASE_URL: {BASE_URL}")


# ═══════════════════════════════════════════════════════
#  TARANACAK SAYFALAR
#  Format: https://patronizle29.cfd/ch.html?id=KANAL_ID
# ═══════════════════════════════════════════════════════
PAGES = [
    # ── beIN Sports ───────────────────────────────────
    {"slug": "ch.html?id=bein1",          "name": "beIN Sports 1",      "group": "Spor"},
    {"slug": "ch.html?id=bein2",          "name": "beIN Sports 2",      "group": "Spor"},
    {"slug": "ch.html?id=bein3",          "name": "beIN Sports 3",      "group": "Spor"},
    {"slug": "ch.html?id=bein4",          "name": "beIN Sports 4",      "group": "Spor"},
    {"slug": "ch.html?id=bein5",          "name": "beIN Sports 5",      "group": "Spor"},
    {"slug": "ch.html?id=beinmax1",       "name": "beIN Sports Max 1",  "group": "Spor"},
    {"slug": "ch.html?id=beinmax2",       "name": "beIN Sports Max 2",  "group": "Spor"},
    {"slug": "ch.html?id=beinmax3",       "name": "beIN Sports Max 3",  "group": "Spor"},
    {"slug": "ch.html?id=beinmax4",       "name": "beIN Sports Max 4",  "group": "Spor"},
    # ── S Sport ───────────────────────────────────────
    {"slug": "ch.html?id=ssport",         "name": "S Sport",            "group": "Spor"},
    {"slug": "ch.html?id=ssport2",        "name": "S Sport 2",          "group": "Spor"},
    # ── Tivibu ────────────────────────────────────────
    {"slug": "ch.html?id=tivibu1",        "name": "Tivibu Spor 1",      "group": "Spor"},
    {"slug": "ch.html?id=tivibu2",        "name": "Tivibu Spor 2",      "group": "Spor"},
    {"slug": "ch.html?id=tivibu3",        "name": "Tivibu Spor 3",      "group": "Spor"},
    # ── TRT ───────────────────────────────────────────
    {"slug": "ch.html?id=trtspor",        "name": "TRT Spor",           "group": "Spor"},
    {"slug": "ch.html?id=trtsporYildiz",  "name": "TRT Spor Yıldız",    "group": "Spor"},
    # ── Diğer ─────────────────────────────────────────
    {"slug": "ch.html?id=aspor",          "name": "A Spor",             "group": "Spor"},
    {"slug": "ch.html?id=patron",         "name": "Patron TV",          "group": "Genel"},
    {"slug": "ch.html?id=tv8",            "name": "TV8",                "group": "Genel"},
    {"slug": "ch.html?id=tv85",           "name": "TV8,5",              "group": "Genel"},
]


# ═══════════════════════════════════════════════════════
#  SELENIUM
# ═══════════════════════════════════════════════════════
try:
    from seleniumwire import webdriver
    WIRE = True
    log.info("✅ SeleniumWire aktif")
except ImportError:
    from selenium import webdriver
    WIRE = False
    log.warning("⚠️ SeleniumWire yok, normal Selenium kullanılıyor")

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
    log.info("✅ Driver hazır")
    return driver


# ═══════════════════════════════════════════════════════
#  POPUP / REKLAM KAPAT
# ═══════════════════════════════════════════════════════
def close_popups(driver):
    selectors = [
        ".close", ".popup-close", "#close",
        "[class*='close']", ".modal-close",
        ".overlay-close", "[aria-label='Close']",
        "[aria-label='Kapat']", ".btn-close",
        "button.close", ".ad-close", "#ad-close",
    ]
    for sel in selectors:
        try:
            el = WebDriverWait(driver, 1).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
            )
            el.click()
            log.info(f"  ❎ Popup kapatıldı: {sel}")
            time.sleep(0.5)
        except Exception:
            pass


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
        "[aria-label='Oynat']", "[title='Play']",
        "[title='Oynat']", "button.play",
        ".overlay-play", ".player-overlay",
        ".video-overlay", ".start-player",
    ]
    for sel in selectors:
        try:
            el = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
            )
            el.click()
            log.info(f"  ▶️  Tıklandı: {sel}")
            time.sleep(1)
            return
        except Exception:
            pass

    # JS ile video başlat
    try:
        driver.execute_script("""
            document.querySelectorAll('video').forEach(function(v) {
                v.muted = true;
                v.play().catch(function() {});
            });
        """)
        time.sleep(1)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════
#  IFRAME İÇİNDE ARA
# ═══════════════════════════════════════════════════════
def handle_iframes(driver):
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        log.info(f"  🖼️  {len(iframes)} iframe bulundu")

        for idx, iframe in enumerate(iframes):
            try:
                src = iframe.get_attribute("src") or ""
                log.info(f"  🖼️  iframe[{idx}]: {src[:100]}")

                driver.switch_to.frame(iframe)
                time.sleep(1)

                # iframe içinde play bas
                click_play(driver)
                time.sleep(2)

                # iframe içinde JS ara
                result = find_in_js(driver)
                if result:
                    driver.switch_to.default_content()
                    return result

                # iframe içinde HTML ara
                result = find_in_source(driver.page_source)
                if result:
                    driver.switch_to.default_content()
                    return result

                driver.switch_to.default_content()

            except Exception as e:
                log.debug(f"  iframe[{idx}] hata: {e}")
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass

    except Exception as e:
        log.debug(f"  iframe handler: {e}")

    return None


# ═══════════════════════════════════════════════════════
#  JS'DEN M3U8 BUL
# ═══════════════════════════════════════════════════════
def find_in_js(driver):
    try:
        result = driver.execute_script("""
            var found = null;

            // Video / source elementleri
            document.querySelectorAll('video, source').forEach(function(el) {
                if (!found && el.src && el.src.toLowerCase().indexOf('.m3u8') !== -1)
                    found = el.src;
                if (!found && el.currentSrc && el.currentSrc.toLowerCase().indexOf('.m3u8') !== -1)
                    found = el.currentSrc;
            });
            if (found) return found;

            // JW Player
            try {
                var jw = jwplayer();
                var item = jw.getPlaylistItem();
                if (item && item.file && item.file.toLowerCase().indexOf('.m3u8') !== -1)
                    return item.file;
                var srcs = jw.getConfig().playlist[0].sources;
                for (var i = 0; i < srcs.length; i++) {
                    if (srcs[i].file && srcs[i].file.toLowerCase().indexOf('.m3u8') !== -1)
                        return srcs[i].file;
                }
            } catch(e) {}

            // Video.js
            try {
                var vjs = videojs.getPlayers();
                for (var k in vjs) {
                    var s = vjs[k].currentSrc();
                    if (s && s.toLowerCase().indexOf('.m3u8') !== -1)
                        return s;
                }
            } catch(e) {}

            // Hls.js
            try {
                if (window.hls && window.hls.url && window.hls.url.indexOf('.m3u8') !== -1)
                    return window.hls.url;
            } catch(e) {}

            // window._streamUrl gibi custom değişkenler
            try {
                var keys = ['streamUrl','stream_url','hlsUrl','hls_url',
                            'videoUrl','video_url','src','source','file'];
                for (var i = 0; i < keys.length; i++) {
                    if (window[keys[i]] && typeof window[keys[i]] === 'string'
                        && window[keys[i]].indexOf('.m3u8') !== -1)
                        return window[keys[i]];
                }
            } catch(e) {}

            // HTML regex
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
#  HTML KAYNAĞINDAN M3U8 BUL
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
#  TEK SAYFA TARA
# ═══════════════════════════════════════════════════════
def scrape_page(driver, page):
    slug = page["slug"]
    name = page["name"]
    url  = f"{BASE_URL}/{slug}"

    log.info(f"\n{'─'*55}")
    log.info(f"🔍 {name}")
    log.info(f"   URL : {url}")
    log.info(f"{'─'*55}")

    # Önceki istekleri temizle
    if WIRE:
        try:
            del driver.requests
        except Exception:
            pass

    # Sayfayı yükle
    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except Exception as e:
        log.warning(f"  ⚠️ Sayfa yükleme: {e}")

    time.sleep(2)

    # Popup kapat
    close_popups(driver)

    # Play bas
    click_play(driver)
    time.sleep(2)

    m3u8_url = None

    # ── 1. SeleniumWire Network ────────────────────────
    if WIRE:
        log.info(f"  📡 Network izleniyor ({STREAM_WAIT}s)...")
        for elapsed in range(STREAM_WAIT):
            for r in driver.requests:
                if is_m3u8(r.url):
                    m3u8_url = r.url
                    log.info(f"  🎯 [{elapsed+1}s] Network: {m3u8_url}")
                    break
            if m3u8_url:
                break
            time.sleep(1)
    else:
        time.sleep(STREAM_WAIT)

    # ── 2. JS ──────────────────────────────────────────
    if not m3u8_url:
        log.info("  🔎 JS ile aranıyor...")
        m3u8_url = find_in_js(driver)

    # ── 3. iframe ─────────────────────────────────────
    if not m3u8_url:
        log.info("  🖼️  iframe içinde aranıyor...")
        m3u8_url = handle_iframes(driver)

    # ── 4. HTML Kaynak ────────────────────────────────
    if not m3u8_url:
        log.info("  📄 HTML kaynağında aranıyor...")
        m3u8_url = find_in_source(driver.page_source)

    # Sonuç
    if m3u8_url:
        log.info(f"  ✅ BULUNDU → {m3u8_url}")
    else:
        log.warning(f"  ❌ {name}: M3U8 bulunamadı")

    return m3u8_url


# ═══════════════════════════════════════════════════════
#  M3U PLAYLIST OLUŞTUR
# ═══════════════════════════════════════════════════════
def create_m3u(channels):
    now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "#EXTM3U\n",
        f"# Site      : patronizle\n",
        f"# Güncelleme: {now}\n",
        f"# Toplam    : {len(channels)} kanal\n\n",
    ]
    for ch in channels:
        extinf  = '#EXTINF:-1'
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
    log.info("   M3U8 Scraper → PATRONİZLE")
    log.info(f"   Base URL : {BASE_URL}")
    log.info(f"   Toplam   : {len(PAGES)} sayfa")
    log.info("=" * 55)

    start    = time.time()
    driver   = None
    channels = []

    try:
        driver = get_driver()

        for i, page in enumerate(PAGES, 1):
            log.info(f"\n[{i}/{len(PAGES)}] işleniyor...")
            m3u8_url = scrape_page(driver, page)

            if m3u8_url and is_m3u8(m3u8_url):
                channels.append({
                    "name" : page["name"],
                    "url"  : m3u8_url,
                    "group": page["group"],
                })

            time.sleep(1.5)

    except Exception as e:
        log.error(f"❌ Kritik hata: {e}", exc_info=True)

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
    log.info(f"📺 Bulunan : {len(channels)} / {len(PAGES)}")
    log.info(f"⏱️  Süre    : {elapsed}s")
    log.info(f"{'='*55}")

    # Playlist kaydet
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(create_m3u(channels))
    log.info(f"✅ {OUTPUT_FILE} kaydedildi")

    # İstatistik kaydet
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "site"           : "patronizle",
            "last_update"    : datetime.now().isoformat(),
            "base_url"       : BASE_URL,
            "total_channels" : len(channels),
            "duration_sec"   : elapsed,
            "channels"       : channels
        }, f, ensure_ascii=False, indent=2)
    log.info(f"✅ {STATS_FILE} kaydedildi")

    if not channels:
        log.warning("⚠️ Hiç M3U8 bulunamadı! PAGES listesindeki id'leri kontrol edin.")


if __name__ == "__main__":
    main()
