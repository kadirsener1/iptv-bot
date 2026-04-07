import re
import time
import os
import requests
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

DOMAIN = "https://atomsportv494.top/"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# 🔧 driver
def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    return webdriver.Chrome(options=options)

# 📺 1. kanal listesini çek
def get_channels():
    r = requests.get(DOMAIN, headers=HEADERS, timeout=10)
    ids = re.findall(r'matches\?id=([a-zA-Z0-9\-]+)', r.text)

    unique_ids = list(set(ids))
    print(f"📺 {len(unique_ids)} kanal bulundu")

    return unique_ids

# 📡 2. m3u8 yakala (network)
def get_m3u8(driver, cid):
    try:
        url = urljoin(DOMAIN, f"matches?id={cid}")
        print(f"🔍 {cid}")

        driver.get(url)
        time.sleep(6)

        logs = driver.get_log("performance")

        for log in logs:
            msg = log["message"]
            if ".m3u8" in msg:
                start = msg.find("http")
                end = msg.find(".m3u8") + 5
                link = msg[start:end]

                print(f"✅ bulundu: {cid}")
                return link

        print(f"❌ bulunamadı: {cid}")

    except Exception as e:
        print(f"⚠️ hata: {cid} - {e}")

    return None

# ✍️ 3. M3U güncelle (sadece değişen)
def update_m3u(filename, new_links, referer):
    if not os.path.exists(filename):
        print("⛔ M3U yok")
        return

    with open(filename, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    updated = []
    i = 0

    while i < len(lines):
        line = lines[i]
        updated.append(line)

        if line.startswith("#EXTINF") and 'tvg-id="' in line:
            match = re.search(r'tvg-id="([^"]+)"', line)
            if match:
                cid = match.group(1)

                if cid in new_links:
                    new_url = new_links[cid]

                    j = i + 1
                    if j < len(lines) and lines[j].startswith("#EXTVLCOPT"):
                        j += 1
                    if j < len(lines):
                        old_url = lines[j]

                    if new_url != old_url:
                        print(f"🔄 güncellendi: {cid}")

                        i += 1
                        if i < len(lines) and lines[i].startswith("#EXTVLCOPT"):
                            i += 1
                        if i < len(lines) and lines[i].startswith("http"):
                            i += 1

                        updated.append(f"#EXTVLCOPT:http-referrer={referer}")
                        updated.append(new_url)
                        continue

        i += 1

    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(updated))

    print("✅ M3U güncellendi")

# 🚀 ANA AKIŞ
channels = get_channels()

driver = create_driver()

found = {}

for cid in channels:
    link = get_m3u8(driver, cid)
    if link:
        found[cid] = link

driver.quit()

if found:
    update_m3u("cafe.m3u", found, DOMAIN)
else:
    print("❌ hiç link yok")
