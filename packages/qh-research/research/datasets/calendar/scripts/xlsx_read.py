"""Minimal stdlib xlsx reader: returns {sheet_name: [[cell values]]}."""
import zipfile, re, xml.etree.ElementTree as ET
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
def _col(ref):
    n = 0
    for ch in re.match(r'[A-Z]+', ref).group(0): n = n * 26 + ord(ch) - 64
    return n - 1
def read(path):
    z = zipfile.ZipFile(path)
    ss = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', NS):
            ss.append(''.join(t.text or '' for t in si.iter('{%s}t' % NS['m'])))
    wb = ET.fromstring(z.read('xl/workbook.xml'))
    rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    rmap = {r.get('Id'): r.get('Target') for r in rels}
    out = {}
    for s in wb.find('m:sheets', NS):
        tgt = rmap[s.get('{%s}id' % NS['r'])].lstrip('/')
        tgt = tgt if tgt.startswith('xl/') else 'xl/' + tgt
        rows = []
        for row in ET.fromstring(z.read(tgt)).iter('{%s}row' % NS['m']):
            vals = {}
            for c in row.findall('m:c', NS):
                v = c.find('m:v', NS); t = c.get('t')
                if t == 'inlineStr':
                    val = ''.join(x.text or '' for x in c.iter('{%s}t' % NS['m']))
                elif v is None: continue
                elif t == 's': val = ss[int(v.text)]
                else: val = v.text
                vals[_col(c.get('r'))] = val
            if vals: rows.append([vals.get(i) for i in range(max(vals) + 1)])
        out[s.get('name')] = rows
    return out
