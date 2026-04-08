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
]

# ... (kodun geri kalan kısmı tamamen aynı kalıyor) ...
