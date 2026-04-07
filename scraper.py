import requests
from bs4 import BeautifulSoup
import re
import base64
import os
import json
import time
import logging
from urllib.parse import urljoin, urlparse
from datetime import datetime

# ── Logging ayarla ────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"logs/scraper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ── Ayarlar (GitHub Secrets'dan al) ──────────────────
TARGET_URL = os.environ.get("TARGET_URL", "https://atomsportv494.top")
OUTPUT_FILE = "playlist.m3u"
STATS_FILE = "stats.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": TARGET_URL,
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# ── M3U8 Pattern'leri ─────────────────────────────────
M3U8_PATTERNS = [
    r'https?://[^\s\'"<>]+\.m3u8[^\s\'"<>]*',
    r'["\']([^"\']*\.m3u8[^"\']*)["\']',
    r'src\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    r'file\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    r'hls["\']?\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    r'stream["\']?\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    r'source\s+src=["\']([^"\']+\.m3u8[^"\']*)["\']',
    r'url\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    r'playlist\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
]

def safe_get(url, timeout=15, retries=3):
    """Güvenli HTTP GET isteği"""
    for attempt in range(retries):
        try:
            resp = SESSION.get(url, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            log.warning(f"[{attempt+1}/{retries}] İstek başarısız: {url} → {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
    return None

def extract_m3u8(text, base_url=""):
    """Metin içinden m3u8 URL'lerini çıkar"""
    found = set()
    
    for pattern in M3U8_PATTERNS:
        try:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                url = match[0] if isinstance(match, tuple) else match
                url = url.strip().strip("'\"")
                
                if not url:
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

def decode_base64_urls(text):
    """Base64 encoded URL'leri çöz"""
    found = set()
    
    patterns = [
        r'atob\(["\']([A-Za-z0-9+/=]+)["\']\)',
        r'base64,([A-Za-z0-9+/=]{20,})',
        r'decode\(["\']([A-Za-z0-9+/=]+)["\']\)',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                decoded = base64.b64decode(match).decode("utf-8", errors="ignore")
                urls = extract_m3u8(decoded)
                found.update(urls)
            except Exception:
                pass
    
    return found

def scan_scripts(soup, base_url):
    """JavaScript içeriğini tara"""
    found = set()
    
    for script in soup.find_all("script"):
        content = script.string or ""
        if not content:
            # External script
            src = script.get("src", "")
            if src:
                full_src = urljoin(base_url, src)
                resp = safe_get(full_src)
                if resp:
                    content = resp.text
        
        if content:
            found.update(extract_m3u8(content, base_url))
            found.update(decode_base64_urls(content))
    
    return found

def scan_iframes(soup, base_url, depth=2):
    """iframe içeriklerini tara"""
    found = set()
    
    if depth <= 0:
        return found
    
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src", "")
        if not src or src.startswith("javascript"):
            continue
        
        full_src = urljoin(base_url, src)
        log.info(f"  [iframe] {full_src}")
        
        resp = safe_get(full_src)
        if not resp:
            continue
        
        iframe_soup = BeautifulSoup(resp.text, "html.parser")
        
        # Direkt ara
        found.update(extract_m3u8(resp.text, full_src))
        
        # Script'leri tara
        found.update(scan_scripts(iframe_soup, full_src))
        
        # Nested iframe (1 seviye daha)
        found.update(scan_iframes(iframe_soup, full_src, depth - 1))
        
        time.sleep(1)
    
    return found

def get_channel_info(url, soup):
    """Kanal bilgilerini çıkar"""
    name = "Bilinmiyor"
    logo = ""
    group = "Genel"
    
    # İsim
    for selector in ["h1", "h2", ".channel-name", ".title", "title"]:
        el = soup.select_one(selector)
        if el and el.text.strip():
            name = el.text.strip()[:50]  # Max 50 karakter
            name = re.sub(r'\s+', ' ', name)
            break
    
    # Logo
    for selector in [".channel-logo img", ".logo img", "img.logo"]:
        el = soup.select_one(selector)
        if el and el.get("src"):
            logo = urljoin(url, el["src"])
            break
    
    # Grup/Kategori
    path_parts = urlparse(url).path.strip("/").split("/")
    if len(path_parts) > 1:
        group = path_parts[0].replace("-", " ").title()
    
    return {
        "name": name,
        "logo": logo,
        "group": group,
        "url": url
    }

def get_all_channel_links():
    """Ana sayfadan tüm kanal linklerini topla"""
    log.info(f"Ana sayfa taranıyor: {TARGET_URL}")
    
    resp = safe_get(TARGET_URL)
    if not resp:
        log.error("Ana sayfa alınamadı!")
        return [], ""
    
    soup = BeautifulSoup(resp.text, "html.parser")
    links = set()
    
    # Tüm linkleri topla
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(TARGET_URL, href)
        
        # Aynı domain kontrolü
        if urlparse(full_url).netloc == urlparse(TARGET_URL).netloc:
            # Geçerli sayfa linki mi?
            if not any(full_url.endswith(ext) for ext in [
                ".jpg", ".png", ".gif", ".css", ".js", ".ico"
            ]):
                links.add(full_url)
    
    # Ana sayfayı da ekle
    links.add(TARGET_URL)
    
    log.info(f"Toplam {len(links)} link bulundu")
    return list(links), resp.text

def scrape_channel(url):
    """Tek bir kanalı tara"""
    log.info(f"→ Taranıyor: {url}")
    
    resp = safe_get(url)
    if not resp:
        return None, set()
    
    soup = BeautifulSoup(resp.text, "html.parser")
    channel_info = get_channel_info(url, soup)
    
    found = set()
    
    # 1. Direkt HTML'den
    found.update(extract_m3u8(resp.text, url))
    
    # 2. Script'lerden
    found.update(scan_scripts(soup, url))
    
    # 3. iframe'lerden
    found.update(scan_iframes(soup, url))
    
    # 4. Base64 decode
    found.update(decode_base64_urls(resp.text))
    
    if found:
        log.info(f"  ✅ {len(found)} M3U8 bulundu")
        for link in found:
            log.info(f"     → {link}")
    else:
        log.info(f"  ❌ M3U8 bulunamadı")
    
    return channel_info, found

def validate_m3u8(url, timeout=10):
    """M3U8 URL'inin çalışıp çalışmadığını kontrol et"""
    try:
        resp = SESSION.head(url, timeout=timeout, allow_redirects=True)
        return resp.status_code in [200, 206]
    except:
        try:
            resp = SESSION.get(url, timeout=timeout, stream=True)
            first_bytes = next(resp.iter_content(64), b"")
            return b"#EXTM3U" in first_bytes or b"#EXT-X" in first_bytes
        except:
            return False

def create_m3u_content(channels_data):
    """M3U formatında içerik oluştur"""
    lines = [
        "#EXTM3U\n",
        f"# Güncelleme: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n",
        f"# Toplam: {len(channels_data)} kanal\n",
        "\n"
    ]
    
    for data in channels_data:
        info = data["info"]
        url = data["m3u8_url"]
        
        name = info.get("name", "Kanal")
        logo = info.get("logo", "")
        group = info.get("group", "Genel")
        
        extinf = f'#EXTINF:-1'
        extinf += f' tvg-name="{name}"'
        extinf += f' tvg-logo="{logo}"' if logo else ''
        extinf += f' group-title="{group}"'
        extinf += f',{name}\n'
        
        lines.append(extinf)
        lines.append(f'{url}\n')
        lines.append('\n')
    
    return "".join(lines)

def save_stats(stats):
    """İstatistikleri kaydet"""
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    log.info(f"İstatistikler kaydedildi: {STATS_FILE}")

def main():
    start_time = time.time()
    log.info("=" * 60)
    log.info("   M3U8 Scraper - GitHub Actions")
    log.info("=" * 60)
    
    # Tüm linkleri al
    channel_links, main_html = get_all_channel_links()
    
    # Ana sayfadan direkt M3U8 ara
    all_data = []
    direct_urls = extract_m3u8(main_html, TARGET_URL)
    
    for i, url in enumerate(direct_urls):
        all_data.append({
            "info": {
                "name": f"Kanal {i+1}",
                "logo": "",
                "group": "Direkt"
            },
            "m3u8_url": url
        })
    
    # Her kanalı tara
    for ch_url in channel_links:
        if ch_url == TARGET_URL:
            continue
        
        try:
            info, m3u8_urls = scrape_channel(ch_url)
            
            for m3u8_url in m3u8_urls:
                # Duplicate kontrolü
                existing_urls = [d["m3u8_url"] for d in all_data]
                if m3u8_url not in existing_urls:
                    all_data.append({
                        "info": info or {"name": "Bilinmiyor", "logo": "", "group": "Genel"},
                        "m3u8_url": m3u8_url
                    })
            
            time.sleep(1.5)  # Rate limiting
            
        except Exception as e:
            log.error(f"Kanal tarama hatası: {ch_url} → {e}")
    
    # M3U dosyası oluştur
    elapsed = time.time() - start_time
    
    log.info("\n" + "=" * 60)
    log.info(f"Tarama tamamlandı!")
    log.info(f"Toplam kanal: {len(all_data)}")
    log.info(f"Süre: {elapsed:.1f} saniye")
    log.info("=" * 60)
    
    if all_data:
        # M3U kaydet
        content = create_m3u_content(all_data)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        log.info(f"✅ Playlist kaydedildi: {OUTPUT_FILE}")
        
        # İstatistik kaydet
        stats = {
            "last_update": datetime.now().isoformat(),
            "total_channels": len(all_data),
            "scan_duration_seconds": round(elapsed, 1),
            "source_url": TARGET_URL,
            "channels": [
                {
                    "name": d["info"].get("name"),
                    "group": d["info"].get("group"),
                    "url": d["m3u8_url"]
                }
                for d in all_data
            ]
        }
        save_stats(stats)
    else:
        log.warning("⚠️ Hiç M3U8 bulunamadı!")
        # Boş dosya oluşturma - eski playlist korunsun
        if not os.path.exists(OUTPUT_FILE):
            with open(OUTPUT_FILE, "w") as f:
                f.write("#EXTM3U\n# Kanal bulunamadı\n")

if __name__ == "__main__":
    main()
