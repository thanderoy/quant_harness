"""Download the press-release PDF linked from each pre-Aug-2015 BoE MPC news page.
Usage: python3 -I fetch_boe_pdfs.py <raw_dir>"""
import sys, os, re, subprocess, time
RAW = sys.argv[1]
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
d = os.path.join(RAW, 'boe', 'pages')
for f in sorted(os.listdir(d)):
    if not re.match(r'news__\d{4}__[a-z]+__mpc-[a-z]+-\d{4}\.htm$', f): continue
    t = open(os.path.join(d, f), encoding='utf-8', errors='replace').read()
    m = re.search(r'href="(/-/media/boe/files/news/[^"]+\.pdf)', t)
    if not m: print(f, 'no pdf link', flush=True); continue
    dst = os.path.join(RAW, 'boe', 'pdf', f[:-4] + '.pdf')
    if os.path.exists(dst) and os.path.getsize(dst) > 1000: continue
    subprocess.run(['curl', '-sSL', '-A', UA, '-o', dst, 'https://www.bankofengland.co.uk' + m.group(1)])
    print(f, os.path.getsize(dst), flush=True); time.sleep(1)
