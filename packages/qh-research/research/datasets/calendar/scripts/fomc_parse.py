"""Parse FOMC calendar pages (raw/fomc) into meeting records with statement URLs."""
import re, os, html
MONTHS = 'January February March April May June July August September October November December'.split()
def _strip(s): return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s))).strip()
def parse_hist(path, year):
    t = open(path, encoding='utf-8').read()
    parts = re.split(r'<h5[^>]*>(.*?)</h5>', t, flags=re.S)
    out = []
    for i in range(1, len(parts), 2):
        head = _strip(parts[i]); body = parts[i + 1]
        if not re.search(r'- %d$' % year, head): continue
        stmts = re.findall(r'<a href="([^"]+)">\s*Statement\s*</a>', body)
        prs = re.findall(r'<a href="([^"]+)">\s*Press Release\s*</a>', body)
        out.append(dict(year=year, heading=head, statements=stmts, press_releases=prs, page=os.path.basename(path)))
    return out
def parse_current(path):
    t = open(path, encoding='utf-8').read()
    out = []
    for yblock in re.split(r'(?=<h4><a[^>]*>\d{4} FOMC Meetings)', t)[1:]:
        year = int(re.search(r'(\d{4}) FOMC Meetings', yblock).group(1))
        for row in re.split(r'<div class="[^"]*\brow fomc-meeting"', yblock)[1:]:
            mon = re.search(r'fomc-meeting__month[^>]*>(.*?)</div>', row, re.S)
            day = re.search(r'fomc-meeting__date[^>]*>(.*?)</div>', row, re.S)
            if not mon or not day: continue
            stm = re.findall(r'<strong>Statement:</strong>.*?<a href="([^"]+\.htm)">HTML</a>', row, re.S)
            stm += re.findall(r'<a href="([^"]+)">\s*Statement\s*</a>', row)
            prs = re.findall(r'<a href="([^"]+)">\s*Press Release\s*</a>', row)
            out.append(dict(year=year, heading=f'{_strip(mon.group(1))} {_strip(day.group(1))} - {year}', statements=stm, press_releases=prs, page='fomccalendars.htm'))
    return out
def all_meetings(raw):
    m = []
    for y in range(2004, 2021): m += parse_hist(os.path.join(raw, 'fomc', f'hist_{y}.htm'), y)
    m += parse_current(os.path.join(raw, 'fomc', 'fomccalendars.htm'))
    return m
if __name__ == '__main__':
    import sys
    for r in all_meetings(sys.argv[1]): print(r['heading'], '|', r['statements'], r['press_releases'])
