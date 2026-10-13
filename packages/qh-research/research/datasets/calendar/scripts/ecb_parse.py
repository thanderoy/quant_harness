"""Parse ECB yearly monetary-policy-decision listings (raw/ecb/mopo_YYYY.htm)."""
import re, html, os
def listing(raw):
    out = []
    for y in range(2004, 2027):
        t = open(os.path.join(raw, 'ecb', f'mopo_{y}.htm'), encoding='utf-8').read()
        blocks = re.split(r'<dt', t)[1:]
        for b in blocks:
            d = re.search(r'>\s*(\d{1,2} [A-Z][a-z]+ \d{4})\s*<', b)
            a = re.search(r'<a href="([^"]+\.en\.html)"[^>]*>(.*?)</a>', b, re.S)
            if not a: continue
            title = re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', '', a.group(2)))).strip()
            out.append(dict(list_year=y, date=d.group(1) if d else None, href=a.group(1), title=title))
    return out
if __name__ == '__main__':
    import sys
    for r in listing(sys.argv[1]): print(r)
