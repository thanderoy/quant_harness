"""Return the first ~600 chars of text of a BOJ statement (htm or pdf). Usage: boj_doctext.py <file> [n]"""
import sys, re, html, subprocess
f = sys.argv[1]; n = int(sys.argv[2]) if len(sys.argv) > 2 else 600
if f.endswith('.pdf'):
    s = subprocess.run(['pdftotext', '-l', '1', f, '-'], capture_output=True, text=True).stdout
else:
    t = open(f, 'rb').read().decode('utf-8', 'replace')
    i = t.find('id="contents"'); t = t[i:] if i > 0 else t
    t = re.sub(r'<script.*?</script>|<style.*?</style>', '', t, flags=re.S)
    s = html.unescape(re.sub(r'<[^>]+>', ' ', t))
print(re.sub(r'\s+', ' ', s)[:n])
