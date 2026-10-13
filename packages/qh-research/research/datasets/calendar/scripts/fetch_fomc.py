"""Download every FOMC statement / press-release page linked from the calendars.
Usage: python3 -I fetch_fomc.py <raw_dir>"""
import sys, os, subprocess, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fomc_parse import all_meetings
RAW = sys.argv[1]
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
def local_name(href): return href.strip('/').replace('/', '__')
urls = []
for m in all_meetings(RAW): urls += m['statements'] + m['press_releases']
for h in urls:
    dst = os.path.join(RAW, 'fomc', 'stmt', local_name(h))
    if os.path.exists(dst) and os.path.getsize(dst) > 2000: continue
    subprocess.run(['curl', '-sSL', '-A', UA, '-o', dst, 'https://www.federalreserve.gov' + h])
    print(h, os.path.getsize(dst), flush=True); time.sleep(1)
