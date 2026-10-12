"""Parse BOJ 'Statements on Monetary Policy' yearly listings (raw/boj/state_YYYY.htm)."""
import re, html, os
def _txt(s): return re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', '', s))).strip()
def listing(raw):
    out = []
    for y in range(2004, 2027):
        t = open(os.path.join(raw, 'boj', f'state_{y}.htm'), 'rb').read().decode('utf-8', 'replace')
        for r in re.findall(r'<tr>(.*?)</tr>', t, re.S):
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.S)
            if len(cells) < 2: continue
            a = re.search(r'href="([^"]+)"', cells[1])
            if not a: continue
            title = _txt(cells[1])
            tm = re.search(r'Announced at ([0-9]{1,2}:[0-9]{2} ?[ap]\.m\.)', title)
            out.append(dict(year=y, date=_txt(cells[0]), href=a.group(1), title=title,
                            listed_time=tm.group(1) if tm else None))
    return out
def primary(raw):
    """One primary policy announcement per date: skip (Reference) docs, 'un*' operation
    notices, joint statements and secondary b/c/d documents when an 'a'/plain doc exists."""
    rows = [r for r in listing(raw) if not r['title'].startswith('(Reference)')
            and not r['href'].rsplit('/', 1)[1].startswith('un')
            and not r['title'].startswith('Joint Statement')]
    by = {}
    for r in rows: by.setdefault(r['date'], []).append(r)
    out = []
    for d, rs in by.items():
        rs.sort(key=lambda r: (re.sub(r'\.\w+$', '', r['href'].rsplit('/', 1)[1])[-1:] not in 'a0123456789', r['href']))
        out.append(dict(rs[0], others=[x['href'] for x in rs[1:]]))
    return out
if __name__ == '__main__':
    import sys
    for r in primary(sys.argv[1]): print(r['date'], r['href'].rsplit('/',1)[1], r['listed_time'], r['others'])
