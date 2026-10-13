"""Download FOMC meeting transcripts (2004-2013) linked from historical calendar pages.
Usage: python3 -I fetch_fomc_transcripts.py <raw_dir>"""
import re, sys, os, subprocess, time
RAW = sys.argv[1]
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
for y in range(2004, 2014):
    t = open(os.path.join(RAW, 'fomc', f'hist_{y}.htm'), encoding='utf-8').read()
    for h in sorted(set(re.findall(r'href="(/monetarypolicy/files/FOMC\d{8}(?:meeting|confcall)\.pdf)"', t))):
        dst = os.path.join(RAW, 'fomc', 'transcripts', h.rsplit('/', 1)[1])
        if os.path.exists(dst) and os.path.getsize(dst) > 10000: continue
        subprocess.run(['curl', '-sSL', '-A', UA, '-o', dst, 'https://www.federalreserve.gov' + h])
        print(h, os.path.getsize(dst), flush=True); time.sleep(1)
