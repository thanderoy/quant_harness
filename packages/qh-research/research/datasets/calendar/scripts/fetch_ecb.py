"""Download ECB monetary policy decision press releases listed in raw/ecb/mopo_YYYY.htm.
Usage: python3 -I fetch_ecb.py <raw_dir>"""
import sys, os, subprocess, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ecb_parse import listing
RAW = sys.argv[1]
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
extra = sys.argv[2:]
hrefs = [r['href'] for r in listing(RAW) if r['title'].lower() == 'monetary policy decisions' or 'PEPP' in r['title']] + extra
for h in hrefs:
    dst = os.path.join(RAW, 'ecb', 'pr', h.rsplit('/', 1)[1])
    if os.path.exists(dst) and os.path.getsize(dst) > 2000: continue
    subprocess.run(['curl', '-sSL', '--compressed', '-A', UA, '-o', dst, 'https://www.ecb.europa.eu' + h])
    print(h, os.path.getsize(dst), flush=True); time.sleep(1)
