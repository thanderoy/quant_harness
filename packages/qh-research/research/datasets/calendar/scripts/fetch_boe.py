"""Download BoE MPC announcement pages: listing-derived URLs (raw/boe/api_*.json) plus
generated /news/YYYY/<month>/mpc-<month>-YYYY candidates for 2004-06..2015-07.
Usage: python3 -I fetch_boe.py <raw_dir>"""
import sys, os, re, json, glob, html, subprocess, time
RAW = sys.argv[1]
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
MONTHS = 'january february march april may june july august september october november december'.split()
def listing_urls():
    out = set()
    for f in glob.glob(os.path.join(RAW, 'boe', 'api_*_p*.json')):
        r = json.load(open(f))['Results']
        for m in re.finditer(r'<a href="([^"]+)"', r):
            u = m.group(1)
            if u.startswith('/monetary-policy-summary-and-minutes/20') or re.match(r'/news/20\d\d/', u):
                if int(u.split('/')[2]) >= 2004: out.add(u)
    return out
def generated():
    out = set()
    for y in range(2004, 2016):
        for i, mo in enumerate(MONTHS):
            if (y, i + 1) < (2004, 6) or (y, i + 1) > (2015, 7): continue
            out.add(f'/news/{y}/{mo}/mpc-{mo}-{y}')
    return out
def local(u): return u.strip('/').replace('/', '__') + '.htm'
if __name__ == '__main__':
    urls = sorted(listing_urls() | generated() | set(sys.argv[2:]))
    for u in urls:
        dst = os.path.join(RAW, 'boe', 'pages', local(u))
        if os.path.exists(dst): continue
        r = subprocess.run(['curl', '-sSL', '--compressed', '-A', UA, '-o', dst, '-w', '%{http_code}',
                            'https://www.bankofengland.co.uk' + u], capture_output=True, text=True)
        if r.stdout != '200':
            os.replace(dst, dst + '.http' + r.stdout)
        print(u, r.stdout, flush=True); time.sleep(1)
