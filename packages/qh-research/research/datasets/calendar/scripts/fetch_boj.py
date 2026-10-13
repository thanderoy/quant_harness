"""Download primary BOJ monetary policy statements. Usage: python3 -I fetch_boj.py <raw_dir>"""
import sys, os, subprocess, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from boj_parse import primary
RAW = sys.argv[1]
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
for r in primary(RAW):
    h = r['href']
    dst = os.path.join(RAW, 'boj', 'docs', h.rsplit('/', 1)[1])
    if os.path.exists(dst) and os.path.getsize(dst) > 1000: continue
    subprocess.run(['curl', '-sSL', '--compressed', '-A', UA, '-o', dst, 'https://www.boj.or.jp' + h])
    print(h, os.path.getsize(dst), flush=True); time.sleep(1)
