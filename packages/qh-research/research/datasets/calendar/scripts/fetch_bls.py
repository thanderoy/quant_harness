"""Fetch every BLS Employment Situation / CPI archived release listed on the
official archive index pages, so the embargo line (date + time) can be parsed.
Usage: python3 -I fetch_bls.py <raw_dir>"""
import re, sys, time, os, subprocess
RAW = sys.argv[1]
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
def items(fname, prefix):
    t = open(os.path.join(RAW, 'bls', fname), encoding='utf-8', errors='replace').read()
    t = re.sub(r'<!--.*?-->', '', t, flags=re.S)
    out = []
    for li in re.findall(r'<li>.*?</li>', t, flags=re.S):
        if 'archives' not in li and 'history' not in li: continue
        m = re.search(r'([A-Z][a-z]+ \d{4}) (Employment Situation|Consumer Price Index)', li)
        if not m: continue
        hrefs = re.findall(r'href="(?:https://www\.bls\.gov)?(/news\.release/[^"]+)"', li)
        pref = [h for h in hrefs if h.endswith('.htm')] or [h for h in hrefs if h.endswith('.txt')] or hrefs
        if pref: out.append((m.group(1), pref[0]))
    return out
if __name__ == '__main__':
    for fname, prefix in [('empsit.htm', 'empsit'), ('cpi.htm', 'cpi')]:
        for ref, href in items(fname, prefix):
            yr = int(ref.split()[1])
            if yr < 2004: continue
            dst = os.path.join(RAW, 'bls', 'docs', href.rsplit('/', 1)[1])
            if os.path.exists(dst) and os.path.getsize(dst) > 5000: continue
            subprocess.run(['curl', '-sS', '--compressed', '-A', UA, '-H', 'Accept: text/html,text/plain',
                            '-H', 'Accept-Language: en-US,en;q=0.5', '-o', dst, 'https://www.bls.gov' + href])
            print(ref, href, os.path.getsize(dst) if os.path.exists(dst) else -1, flush=True)
            time.sleep(1.5)
