"""For each FOMC transcript PDF, report whether it states a statement/announcement
release time (e.g. '2:15'). Prints only short windows that contain both a clock time
and a release-related keyword, to avoid reading transcript substance.
Usage: python3 -I transcript_times.py <transcripts_dir> > out.tsv"""
import os, re, subprocess, sys
D = sys.argv[1]
KW = re.compile(r'(releas|announc|statement|press)', re.I)
for f in sorted(os.listdir(D)):
    if not f.endswith('.pdf'): continue
    txt = subprocess.run(['pdftotext', os.path.join(D, f), '-'], capture_output=True, text=True).stdout
    txt = re.sub(r'\s+', ' ', txt)
    hits = []
    for m in re.finditer(r'\b(1[0-2]|[1-9])[:.](\d{2}) ?(p\.?m\.?|a\.?m\.?|o.clock)?', txt):
        w = txt[max(0, m.start() - 70): m.end() + 30]
        if KW.search(w) and m.group(1) + ':' + m.group(2) in ('2:15', '2:00', '12:30', '2:30'):
            hits.append(m.group(1) + ':' + m.group(2) + ' «' + w.replace('\t', ' ') + '»')
    print(f, len(hits), ' || '.join(hits[:3]), sep='\t')
