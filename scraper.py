import os
import re
import json
import time
import logging
from datetime import datetime
from urllib.parse import urljoin, urlparse

from seleniumwire import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import requests

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

# ── Ayarlar ───────────────────────────────────────────
TARGET_URL   = os.environ.get("TARGET_URL", "https://atomsportv494.top")
OUTPUT_FILE  = "playlist.m3u"
STATS_FILE   = "stats.json"
WAIT_TIME    = 15   # Sayfa yüklenme bekleme süresi (sn)
STREAM_WAIT  = 10   # Stream başlaması için bekleme (sn)

# ── Chrome Ayarları ───────────────────────────────────
def get_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--mute-audio")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Seleniumwire ayarları - tüm istekleri yakala
    sw_options = {
        "verify_ssl": False,
        "suppress_connection_errors": True,
    }

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(
        service=service,
        options=options,
        seleniumwire_options=sw_options
    )

    # Bot tespitini engelle
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    return driver


# ── Network'ten M3U8 Yakala ───────────────────────────
def capture_m3u8_from_network(driver, wait=STREAM_WAIT):
    """
    Tarayıcının yaptığı tüm ağ isteklerini tarayarak
    m3u8 URL'lerini yakalar
    """
    log.info(f"  ⏳ {wait} saniye network trafiği bekleniyor...")
    time.sleep(wait)

    found = set()

    for request in driver.requests:
        url = request.url

        # M3U8 kontrolü
        if ".m3u8" in url:
            found.add(url)
            log.info(f"  🎯 [Network] M3U8 yakalandı: {url}")
            continue

        # Response içinde m3u8 ara
        try:
            if request.response and request.response.body:
                body = request.response.body.decode("utf-8", errors="ignore")
                if ".m3u8" in body or "#EXTM3U" in body or "#EXT-X-" in body:
                    # URL'leri çıkar
                    urls = re.findall(
                        r'https?://[^\s\'"<>]+\.m3u8[^\s\'"<>]*',
                        body
                    )
                    for u in urls:
                        found.add(u)
                        log.info(f"  🎯 [Response] M3U8 bulundu: {u}")
        except Exception:
            pass

    return found


# ── JavaScript'ten M3U8 Çıkar ─────────────────────────
def extract_from_js(driver):
    """JavaScript değişkenlerinden m3u8 çıkar"""
    found = set()

    scripts = [
        # Tüm JS kaynaklarını tara
        "return document.documentElement.innerHTML",
        # JWPlayer
        "try { return JSON.stringify(jwplayer().getPlaylist()) } catch(e) { return '' }",
        # Video.js
        "try { return videojs.getAllPlayers()[0].src() } catch(e) { return '' }",
        # HLS.js
        "try { return hls.url } catch(e) { return '' }",
        # Flowplayer
        "try { return flowplayer().src } catch(e) { return '' }",
        # Clappr
        "try { return player.options.source } catch(e) { return '' }",
        # Global değişkenler
        """
        try {
            var results = [];
            for (var key in window) {
                try {
                    var val = JSON.stringify(window[key]);
                    if (val && val.includes('.m3u8')) {
                        results.push(val);
                    }
                } catch(e) {}
            }
            return results.join('|||');
        } catch(e) { return '' }
        """,
    ]

    for script in scripts:
        try:
            result = driver.execute_script(script)
            if result and ".m3u8" in str(result):
                urls = re.findall(
                    r'https?://[^\s\'"<>\\]+\.m3u8[^\s\'"<>\\]*',
                    str(result)
                )
                for url in urls:
                    url = url.strip().rstrip("\\")
                    found.add(url)
                    log.info(f"  🎯 [JS] M3U8 bulundu: {url}")
        except Exception:
            pass

    return found


# ── iframe'leri Tara ──────────────────────────────────
def scan_iframes(driver):
    """iframe'lere geçerek m3u8 ara"""
    found = set()

    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        log.info(f"  📦 {len(iframes)} iframe bulundu")

        for i, iframe in enumerate(iframes):
            try:
                src = iframe.get_attribute("src") or ""
                log.info(f"  [iframe {i+1}] {src}")

                driver.switch_to.frame(iframe)

                # iframe içinde JS tara
                found.update(extract_from_js(driver))

                # iframe network trafiği
                found.update(capture_m3u8_from_network(driver, wait=5))

                driver.switch_to.default_content()

            except Exception as e:
                log.debug(f"  iframe hatası: {e}")
                driver.switch_to.default_content()

    except Exception as e:
        log.debug(f"  iframe tarama hatası: {e}")

    return found


# ── Video Elementlerini Bul ───────────────────────────
def find_video_sources(driver):
    """Video ve source elementlerinden URL çıkar"""
    found = set()

    try:
        # <video> src
        videos = driver.find_elements(By.TAG_NAME, "video")
        for video in videos:
            src = video.get_attribute("src") or ""
            if ".m3u8" in src:
                found.add(src)

        # <source> src
        sources = driver.find_elements(By.TAG_NAME, "source")
        for source in sources:
            src = source.get_attribute("src") or ""
            if ".m3u8" in src:
                found.add(src)

    except Exception as e:
        log.debug(f"  Video element hatası: {e}")

    return found


# ── Play Butonuna Tıkla ───────────────────────────────
def click_play_button(driver):
    """Oynat butonuna tıklamayı dene"""
    play_selectors = [
        "button.play",
        ".play-button",
        ".btn-play",
        "[class*='play']",
        "button[aria-label='Play']",
        ".jw-icon-playback",
        ".vjs-play-button",
        ".fp-play",
        "button.ytp-play-button",
        ".plyr__control--overlaid",
        "#play-button",
        ".play_btn",
    ]

    for selector in play_selectors:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, selector)
            if btn.is_displayed():
                btn.click()
                log.info(f"  ▶️ Play butonu tıklandı: {selector}")
                time.sleep(3)
                return True
        except Exception:
            pass

    # JavaScript ile tıkla
    try:
        driver.execute_script("""
            var videos = document.querySelectorAll('video');
            for (var v of videos) {
                v.play();
            }
        """)
        log.info("  ▶️ Video JS ile başlatıldı")
        time.sleep(3)
        return True
    except Exception:
        pass

    return False


# ── Ana Sayfadaki Kanal Linklerini Al ────────────────
def get_channel_links(driver):
    """Ana sayfadan tüm kanal linklerini çek"""
    log.info(f"🌐 Ana sayfa açılıyor: {TARGET_URL}")
    driver.get(TARGET_URL)

    try:
        WebDriverWait(driver, WAIT_TIME).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except Exception:
        pass

    time.sleep(5)

    # Sayfayı aşağı kaydır - lazy load için
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(2)
    driver.execute_script("window.scrollTo(0, 0)")
    time.sleep(1)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    links = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(TARGET_URL, href)

        parsed = urlparse(full_url)
        target_parsed = urlparse(TARGET_URL)

        if parsed.netloc == target_parsed.netloc:
            if full_url != TARGET_URL and not any(
                full_url.endswith(ext)
                for ext in [".jpg", ".png", ".gif", ".css", ".js", ".ico", ".xml"]
            ):
                links.add(full_url)

    # Ana sayfayı da ekle
    links.add(TARGET_URL)

    log.info(f"📋 Toplam {len(links)} link bulundu")
    return list(links)


# ── Tek Kanal Tara ────────────────────────────────────
def scrape_channel(driver, url):
    """Bir kanal sayfasını tara ve m3u8 bul"""
    log.info(f"\n{'='*50}")
    log.info(f"🔍 Taranıyor: {url}")
    log.info(f"{'='*50}")

    found = set()

    try:
        # Önceki istekleri temizle
        del driver.requests

        # Sayfayı aç
        driver.get(url)

        # Sayfa yüklensin
        try:
            WebDriverWait(driver, WAIT_TIME).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception:
            pass

        time.sleep(3)

        # 1. Play butonuna tıkla
        click_play_button(driver)

        # 2. Network trafiğini izle
        network_urls = capture_m3u8_from_network(driver, STREAM_WAIT)
        found.update(network_urls)

        # 3. JavaScript'ten çıkar
        js_urls = extract_from_js(driver)
        found.update(js_urls)

        # 4. iframe'leri tara
        iframe_urls = scan_iframes(driver)
        found.update(iframe_urls)

        # 5. Video elementlerini tara
        video_urls = find_video_sources(driver)
        found.update(video_urls)

        # 6. Sayfa kaynağını tara
        page_source = driver.page_source
        source_urls = re.findall(
            r'https?://[^\s\'"<>\\]+\.m3u8[^\s\'"<>\\]*',
            page_source,
            re.IGNORECASE
        )
        for u in source_urls:
            found.add(u.strip())

        # Kanal adını al
        try:
            title = driver.title or url
            channel_name = title.strip()[:60]
        except Exception:
            channel_name = urlparse(url).path.strip("/").replace("/", "_")

        if found:
            log.info(f"✅ {len(found)} M3U8 bulundu!")
            return channel_name, list(found)
        else:
            log.info("❌ M3U8 bulunamadı")
            return channel_name, []

    except Exception as e:
        log.error(f"❌ Hata: {e}")
        return "Hata", []


# ── M3U Oluştur ───────────────────────────────────────
def create_m3u(channels_data):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "#EXTM3U\n",
        f"# Güncelleme: {now} UTC\n",
        f"# Toplam: {len(channels_data)} kanal\n",
        "\n"
    ]

    for item in channels_data:
        name  = item["name"]
        url   = item["url"]
        group = item.get("group", "Genel")
        logo  = item.get("logo", "")

        extinf  = f'#EXTINF:-1'
        extinf += f' tvg-name="{name}"'
        if logo:
            extinf += f' tvg-logo="{logo}"'
        extinf += f' group-title="{group}"'
        extinf += f',{name}\n'

        lines.append(extinf)
        lines.append(f"{url}\n\n")

    return "".join(lines)


# ── Ana Fonksiyon ─────────────────────────────────────
def main():
    log.info("🚀 Scraper başlatılıyor...")
    start = time.time()

    driver = get_driver()
    all_channels = []

    try:
        # Kanal linklerini al
        channel_links = get_channel_links(driver)
        log.info(f"\n📺 {len(channel_links)} kanal taranacak\n")

        for i, link in enumerate(channel_links, 1):
            log.info(f"\n[{i}/{len(channel_links)}]")

            name, m3u8_urls = scrape_channel(driver, link)

            for j, m3u8 in enumerate(m3u8_urls):
                ch_name = name if len(m3u8_urls) == 1 else f"{name} {j+1}"

                # Duplicate kontrolü
                existing = [c["url"] for c in all_channels]
                if m3u8 not in existing:
                    all_channels.append({
                        "name": ch_name,
                        "url": m3u8,
                        "group": "Spor",
                        "logo": ""
                    })

            time.sleep(2)

    finally:
        driver.quit()

    # Sonuçlar
    elapsed = round(time.time() - start, 1)
    log.info(f"\n{'='*50}")
    log.info(f"🏁 Tamamlandı!")
    log.info(f"📺 Toplam kanal: {len(all_channels)}")
    log.info(f"⏱️ Süre: {elapsed}s")
    log.info(f"{'='*50}")

    if all_channels:
        # M3U kaydet
        content = create_m3u(all_channels)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        log.info(f"✅ {OUTPUT_FILE} kaydedildi")

        # Stats kaydet
        stats = {
            "last_update": datetime.now().isoformat(),
            "total": len(all_channels),
            "duration_sec": elapsed,
            "channels": all_channels
        }
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        log.info(f"✅ {STATS_FILE} kaydedildi")

    else:
        log.warning("⚠️ Hiç M3U8 bulunamadı!")
        if not os.path.exists(OUTPUT_FILE):
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n# Kanal bulunamadı\n")


if __name__ == "__main__":
    main()
