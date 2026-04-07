import requests
import re
import os

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# 🔎 1. Aktif domain bul
def find_working_domain(start=493, end=520):
    print("🧭 atomsport domain taranıyor...")
    for i in range(start, end + 1):
        url = f"https://atomsportv{i}.top/"
        try:
            r = requests.get(url, headers=HEADERS, timeout=5)
            if r.status_code == 200:
                print(f"✅ Aktif domain: {url}")
                return url
        except:
            print(f"❌ Hata: {url}")
    return None


# 🔎 2. iframe çek
def extract_iframe(html):
    match = re.search(r'<iframe[^>]+src="([^"]+)"', html)
    return match.group(1) if match else None


# 🔎 3. m3u8 çek
def extract_m3u8(html):
    match = re.search(r'https?://[^"\']+\.m3u8', html)
    return match.group(0) if match else None


# 🔎 4. kanal linkini bul
def get_channel_stream(domain, channel_id):
    try:
        url = f"{domain}matches?id={channel_id}"
        res = requests.get(url, headers=HEADERS, timeout=5)

        iframe = extract_iframe(res.text)
        if iframe:
            iframe_res = requests.get(iframe, headers=HEADERS, timeout=5)
            m3u8 = extract_m3u8(iframe_res.text)

            if m3u8:
                print(f"✅ {channel_id}: bulundu")
                return m3u8

        print(f"❌ {channel_id}: bulunamadı")
    except Exception as e:
        print(f"⚠️ {channel_id}: hata - {e}")

    return None


# ✍️ 5. SADECE DEĞİŞENLERİ GÜNCELLE
def update_m3u(filename, new_links, referer):
    if not os.path.exists(filename):
        print("⛔ M3U dosyası yok!")
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

                    # eski url'yi al
                    j = i + 1
                    old_url = ""
                    if j < len(lines) and lines[j].startswith("#EXTVLCOPT"):
                        j += 1
                    if j < len(lines):
                        old_url = lines[j]

                    # sadece değişmişse güncelle
                    if new_url != old_url:
                        print(f"🔄 Güncellendi: {cid}")

                        i += 1
                        if i < len(lines) and lines[i].startswith("#EXTVLCOPT"):
                            i += 1
                        if i < len(lines) and lines[i].startswith("http"):
                            i += 1

                        updated.append(f"#EXTVLCOPT:http-referrer={referer}")
                        updated.append(new_url)
                        continue
                    else:
                        print(f"✔ Değişmedi: {cid}")

        i += 1

    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(updated))

    print("✅ M3U güncelleme tamamlandı")


# 📺 Kanal listesi (tvg-id ile aynı olmalı)
channels = [
    "bein-sports-1",
    "bein-sports-2",
    "ssport",
    "tivibu-spor-1"
]


# 🚀 ANA AKIŞ
domain = find_working_domain()

if domain:
    found_links = {}

    for ch in channels:
        link = get_channel_stream(domain, ch)
        if link:
            found_links[ch] = link

    if found_links:
        update_m3u("cafe.m3u", found_links, domain)
    else:
        print("❌ Hiç link bulunamadı")
else:
    print("❌ Domain bulunamadı")
