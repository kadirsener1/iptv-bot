import os
import re
import json
import time
import logging
from datetime import datetime
from urllib.parse import urljoin, urlparse

try:
    from seleniumwire import webdriver
    WIRE = True
except ImportError:
    from selenium import webdriver
    WIRE = False

from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# ── Logging ───────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("debug.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

TARGET_URL = "https://atomsportv494.top"

def get_driver():
    options = Options()
    # Debug için headless KAPALII - tarayıcıyı görmek için
    # options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--autoplay-policy=no-user-gesture-required")
    options.add_argument("--mute-audio")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    options.add_experimental_option(
        "excludeSwitches", ["enable-automation"]
    )
    options.add_experimental_option("useAutomationExtension", False)

    # Seleniumwire varsa kullan
    if WIRE:
        sw_options = {
            "verify_ssl": False,
            "suppress_connection_errors": True,
            "enable_har": True,
        }
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(
            service=service,
            options=options,
            seleniumwire_options=sw_options
        )
    else:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def analyze_page(driver, url):
    """Sayfayı detaylı analiz et"""
    log.info(f"\n{'='*60}")
    log.info(f"ANALİZ: {url}")
    log.info(f"{'='*60}")

    results = {
        "url": url,
        "m3u8_found": [],
        "iframes": [],
        "scripts": [],
        "network_requests": [],
        "page_source_snippet": "",
    }

    try:
        # ── 1. Sayfayı Aç ──────────────────────────────
        if WIRE:
            del driver.requests

        driver.get(url)
        log.info("✅ Sayfa açıldı")

        # Yüklenmeyi bekle
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(5)

        log.info(f"📄 Sayfa başlığı: {driver.title}")

        # ── 2. Sayfa Kaynağını Kaydet ──────────────────
        page_source = driver.page_source
        with open("debug_page_source.html", "w", encoding="utf-8") as f:
            f.write(page_source)
        log.info("💾 Sayfa kaynağı debug_page_source.html'e kaydedildi")

        # ── 3. iframe Tespiti ──────────────────────────
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        log.info(f"\n📦 iframe sayısı: {len(iframes)}")
        for i, iframe in enumerate(iframes):
            src  = iframe.get_attribute("src") or "YOK"
            name = iframe.get_attribute("name") or ""
            iid  = iframe.get_attribute("id") or ""
            log.info(f"  iframe[{i}]: src={src} id={iid} name={name}")
            results["iframes"].append({
                "src": src, "id": iid, "name": name
            })

        # ── 4. Script Tespiti ──────────────────────────
        scripts = driver.find_elements(By.TAG_NAME, "script")
        log.info(f"\n📜 Script sayısı: {len(scripts)}")
        for i, script in enumerate(scripts):
            src     = script.get_attribute("src") or ""
            content = script.get_attribute("innerHTML") or ""
            if ".m3u8" in content or ".m3u8" in src:
                log.info(f"  🎯 Script[{i}] M3U8 içeriyor!")
                log.info(f"     src: {src}")
                log.info(f"     içerik: {content[:200]}")

        # ── 5. Video Elementleri ───────────────────────
        videos = driver.find_elements(By.TAG_NAME, "video")
        log.info(f"\n🎬 Video elementi sayısı: {len(videos)}")
        for i, video in enumerate(videos):
            src = video.get_attribute("src") or ""
            log.info(f"  video[{i}]: src={src}")

        # ── 6. Kaynak Kodu M3U8 Ara ────────────────────
        log.info("\n🔍 Sayfa kaynağında M3U8 aranıyor...")
        patterns = [
            r'https?://[^\s\'"<>]+\.m3u8[^\s\'"<>]*',
            r'["\']([^"\']*\.m3u8[^"\']*)["\']',
        ]
        for pat in patterns:
            matches = re.findall(pat, page_source, re.IGNORECASE)
            for m in matches:
                u = m if isinstance(m, str) else m[0]
                if u not in results["m3u8_found"]:
                    results["m3u8_found"].append(u)
                    log.info(f"  🎯 KAYNAK'TA BULUNDU: {u}")

        # ── 7. Play Butonlarını Bul ────────────────────
        log.info("\n▶️ Play elementleri aranıyor...")
        play_selectors = [
            "button", ".play", ".btn-play", "[class*='play']",
            "[id*='play']", ".jw-icon-playback", ".vjs-play-button",
        ]
        for sel in play_selectors:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed():
                        txt = el.text or el.get_attribute("class") or ""
                        log.info(f"  Buton: {sel} → '{txt[:50]}'")
            except Exception:
                pass

        # ── 8. Play Butonuna Tıkla ─────────────────────
        log.info("\n▶️ Play butonuna tıklanıyor...")
        clicked = False
        click_selectors = [
            ".play-button", ".btn-play", ".jw-icon-playback",
            ".vjs-play-button", "[class*='play-btn']",
            "[class*='play_btn']", "button.play",
        ]
        for sel in click_selectors:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    el.click()
                    log.info(f"  ✅ Tıklandı: {sel}")
                    clicked = True
                    time.sleep(3)
                    break
            except Exception:
                pass

        if not clicked:
            # JS ile video oynat
            try:
                driver.execute_script("""
                    document.querySelectorAll('video').forEach(v => {
                        v.muted = true;
                        v.play().catch(e => console.log(e));
                    });
                """)
                log.info("  ✅ Video JS ile başlatıldı")
                time.sleep(3)
            except Exception:
                pass

        # ── 9. Network İsteklerini Yakala ──────────────
        if WIRE:
            log.info(f"\n🌐 Network istekleri bekleniyor (15s)...")
            time.sleep(15)

            log.info(f"\n📡 Toplam istek sayısı: {len(driver.requests)}")

            for req in driver.requests:
                req_url = req.url
                method  = req.method

                # Tüm istekleri logla (debug için)
                if any(ext in req_url for ext in [
                    ".m3u8", ".ts", ".mpd", "stream", "live",
                    "hls", "chunk", "segment", "playlist"
                ]):
                    log.info(f"  🎯 İLGİLİ: [{method}] {req_url}")
                    results["network_requests"].append(req_url)

                    if ".m3u8" in req_url:
                        results["m3u8_found"].append(req_url)
                        log.info(f"  ✅ M3U8 NETWORK'TE BULUNDU: {req_url}")

        # ── 10. iframe İçine Gir ───────────────────────
        log.info("\n📦 iframe'ler taranıyor...")
        for i, iframe in enumerate(iframes):
            try:
                driver.switch_to.frame(iframe)
                log.info(f"  iframe[{i}]'e girildi")

                # iframe kaynağını kaydet
                iframe_source = driver.page_source
                with open(f"debug_iframe_{i}.html", "w",
                          encoding="utf-8") as f:
                    f.write(iframe_source)
                log.info(f"  💾 debug_iframe_{i}.html kaydedildi")

                # iframe'de m3u8 ara
                for pat in patterns:
                    matches = re.findall(
                        pat, iframe_source, re.IGNORECASE
                    )
                    for m in matches:
                        u = m if isinstance(m, str) else m[0]
                        if u not in results["m3u8_found"]:
                            results["m3u8_found"].append(u)
                            log.info(
                                f"  🎯 iframe[{i}]'de M3U8: {u}"
                            )

                # iframe'de JS çalıştır
                js_results = driver.execute_script("""
                    var found = [];

                    // Video src
                    document.querySelectorAll('video').forEach(v => {
                        if (v.src) found.push(v.src);
                    });

                    // innerHTML'de ara
                    var html = document.documentElement.innerHTML;
                    var matches = html.match(
                        /https?:\\/\\/[^\\s'"<>]+\\.m3u8[^\\s'"<>]*/gi
                    );
                    if (matches) found = found.concat(matches);

                    // JWPlayer
                    try {
                        var jw = jwplayer();
                        if (jw) {
                            var list = jw.getPlaylist();
                            if (list && list[0] && list[0].file) {
                                found.push(list[0].file);
                            }
                            found.push(jw.getPlaylistItem().file);
                        }
                    } catch(e) {}

                    // Hls.js
                    try {
                        if (typeof Hls !== 'undefined') {
                            for (var key in window) {
                                try {
                                    if (window[key] instanceof Hls) {
                                        found.push(window[key].url);
                                    }
                                } catch(e) {}
                            }
                        }
                    } catch(e) {}

                    // Global window tarama
                    for (var k in window) {
                        try {
                            var v2 = String(window[k]);
                            if (v2.includes('.m3u8')) {
                                var m2 = v2.match(
                                    /https?:\\/\\/[^\\s'"]+\\.m3u8[^\\s'"]*/g
                                );
                                if (m2) found = found.concat(m2);
                            }
                        } catch(e) {}
                    }

                    return [...new Set(found)];
                """)

                if js_results:
                    for u in js_results:
                        if u and ".m3u8" in u:
                            log.info(f"  🎯 iframe JS'de M3U8: {u}")
                            results["m3u8_found"].append(u)

                driver.switch_to.default_content()

            except Exception as e:
                log.warning(f"  ❌ iframe[{i}] hatası: {e}")
                driver.switch_to.default_content()

        # ── 11. Tüm Window Değişkenlerini Tara ─────────
        log.info("\n🔍 JavaScript window değişkenleri taranıyor...")
        try:
            js_scan = driver.execute_script("""
                var found = [];
                var keys  = Object.keys(window);
                var result = {found: [], keys: []};

                for (var i = 0; i < keys.length; i++) {
                    var key = keys[i];
                    try {
                        var val = JSON.stringify(window[key]);
                        if (val && val.includes('.m3u8')) {
                            result.found.push({key: key, val: val});
                        }
                    } catch(e) {}
                }

                // localStorage
                try {
                    for (var j = 0; j < localStorage.length; j++) {
                        var k  = localStorage.key(j);
                        var v3 = localStorage.getItem(k);
                        if (v3 && v3.includes('.m3u8')) {
                            result.found.push({
                                key: 'localStorage:' + k,
                                val: v3
                            });
                        }
                    }
                } catch(e) {}

                return result;
            """)

            if js_scan and js_scan.get("found"):
                for item in js_scan["found"]:
                    log.info(
                        f"  🎯 JS Değişken: {item['key']} → "
                        f"{item['val'][:100]}"
                    )
                    urls = re.findall(
                        r'https?://[^\s\'"\\]+\.m3u8[^\s\'"\\]*',
                        item["val"]
                    )
                    results["m3u8_found"].extend(urls)

        except Exception as e:
            log.warning(f"  JS tarama hatası: {e}")

        # ── 12. Cookies & Headers Kaydet ───────────────
        cookies = driver.get_cookies()
        with open("debug_cookies.json", "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        log.info(f"\n🍪 Cookies kaydedildi ({len(cookies)} adet)")

        # ── 13. Screenshot Al ──────────────────────────
        driver.save_screenshot("debug_screenshot.png")
        log.info("📸 Ekran görüntüsü: debug_screenshot.png")

    except Exception as e:
        log.error(f"❌ Analiz hatası: {e}", exc_info=True)

    return results


def main():
    log.info("🚀 Debug Scraper Başlatılıyor...")
    log.info(f"🌐 Hedef: {TARGET_URL}")
    log.info(f"🔌 SeleniumWire: {'AÇIK' if WIRE else 'KAPALI'}")

    driver = get_driver()
    all_results = []

    try:
        # ── Ana Sayfayı Analiz Et ──────────────────────
        result = analyze_page(driver, TARGET_URL)
        all_results.append(result)

        # ── Kanal Linklerini Bul ───────────────────────
        soup = BeautifulSoup(driver.page_source, "html.parser")
        links = set()

        for a in soup.find_all("a", href=True):
            href     = a["href"]
            full_url = urljoin(TARGET_URL, href)
            parsed   = urlparse(full_url)
            target   = urlparse(TARGET_URL)

            if parsed.netloc == target.netloc:
                if not any(full_url.endswith(x) for x in [
                    ".jpg", ".png", ".css", ".js", ".ico"
                ]):
                    links.add(full_url)

        log.info(f"\n📋 {len(links)} kanal linki bulundu:")
        for lnk in list(links)[:5]:
            log.info(f"  → {lnk}")

        # ── İlk 3 Kanalı Analiz Et ────────────────────
        for url in list(links)[:3]:
            result = analyze_page(driver, url)
            all_results.append(result)
            time.sleep(2)

        # ── Sonuçları Kaydet ───────────────────────────
        with open("debug_results.json", "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)

        # ── Özet ──────────────────────────────────────
        log.info(f"\n{'='*60}")
        log.info("📊 ÖZET")
        log.info(f"{'='*60}")

        all_m3u8 = []
        for r in all_results:
            for u in r["m3u8_found"]:
                if u not in all_m3u8:
                    all_m3u8.append(u)

        if all_m3u8:
            log.info(f"✅ Toplam {len(all_m3u8)} M3U8 bulundu!")
            for u in all_m3u8:
                log.info(f"  → {u}")
        else:
            log.warning("❌ HİÇ M3U8 BULUNAMADI!")
            log.info("\n💡 Öneriler:")
            log.info("  1. debug_screenshot.png'ye bak - site açıldı mı?")
            log.info("  2. debug_page_source.html'e bak - içerik var mı?")
            log.info("  3. debug.log'a bak - hata var mı?")
            log.info("  4. Site CloudFlare arkasında olabilir")
            log.info("  5. Site farklı bir player kullanıyor olabilir")

        log.info(f"\n📁 Oluşturulan dosyalar:")
        log.info("  → debug.log")
        log.info("  → debug_page_source.html")
        log.info("  → debug_screenshot.png")
        log.info("  → debug_cookies.json")
        log.info("  → debug_results.json")

    finally:
        input("\n⏸️ Tarayıcıyı kapatmak için Enter'a bas...")
        driver.quit()


if __name__ == "__main__":
    main()
