import requests
import re
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# m3u8 bul (her yerde ara)
def find_m3u8(text):
    matches = re.findall(r'https?://[^"\']+\.m3u8', text)
    return matches[0] if matches else None

# iframe bul
def find_iframes(html):
    return re.findall(r'<iframe[^>]+src="([^"]+)"', html)

# 🔥 ASIL FONKSİYON (çok güçlü)
def get_stream(domain, cid):
    try:
        url = urljoin(domain, f"matches?id={cid}")
        print(f"\n🔍 {cid} kontrol ediliyor...")

        r1 = requests.get(url, headers=HEADERS, timeout=10)

        # 1️⃣ direkt m3u8 var mı?
        m3u8 = find_m3u8(r1.text)
        if m3u8:
            print("✅ Direkt bulundu")
            return m3u8

        # 2️⃣ iframe'leri tara
        iframes = find_iframes(r1.text)

        for iframe in iframes:
            iframe_url = urljoin(domain, iframe)
            r2 = requests.get(iframe_url, headers=HEADERS, timeout=10)

            m3u8 = find_m3u8(r2.text)
            if m3u8:
                print("✅ iframe içinde bulundu")
                return m3u8

            # 3️⃣ iç iframe varsa tekrar tara
            inner_iframes = find_iframes(r2.text)
            for inner in inner_iframes:
                inner_url = urljoin(domain, inner)
                r3 = requests.get(inner_url, headers=HEADERS, timeout=10)

                m3u8 = find_m3u8(r3.text)
                if m3u8:
                    print("✅ iç iframe içinde bulundu")
                    return m3u8

        print("❌ bulunamadı")

    except Exception as e:
        print(f"⚠️ hata: {e}")

    return None


# 🔎 test
domain = "https://atomsportv494.top/"

channels = [
    "bein-sports-1",
    "bein-sports-2",
    "bein-sports-3",
    "bein-sports-4",
    "bein-sports-5",
    "bein-sports-max-1",
    "bein-sports-max-2",
    "s-sport",
    "s-sport-2",
    "tivibu-spor-1"
]

results = {}

for ch in channels:
    link = get_stream(domain, ch)
    if link:
        results[ch] = link

print("\n📡 SONUÇ:")
for k, v in results.items():
    print(k, "=>", v)
