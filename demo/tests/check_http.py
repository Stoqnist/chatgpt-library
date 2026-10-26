"""Check the production container's locale routing and public/private boundary."""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
base=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8092'
registry=json.loads((ROOT/'locales/registry.json').read_text())
film=json.loads((ROOT/'media/gunter-morning.json').read_text())
public={'/':'index.html'}
for config in registry['locales']:
    if not config['enabled']:continue
    code=config['code']
    public[f'/locales/{code}.js']=f'locales/{code}.js'
    prefix='' if code=='en' else code+'/'
    for leaf in ('demos','demos/gunter','demos/purchase'):
        asset=f'{prefix}{leaf}/index.html'
        public['/'+prefix+leaf+'/']=asset
        public['/'+prefix+leaf]=asset
        public['/'+asset]=asset
    if code!='en':public[f'/{code}/']=f'{code}/index.html';public[f'/{code}']=f'{code}/index.html'
    variant=film['variants'][code]
    if variant['status']!='planned':
        for key in ('video','captions','poster'):
            if variant.get(key):public[variant[key]]=variant[key].lstrip('/')
for name in ['index.html','style.css','journey.css','brand-journey.css','localization.css','app.js','i18n.js','cases.js']:
    public['/'+name]=name
for name in ['stoqnist-banner.svg','stoqnist-banner-mobile.svg','stoqnist-mark.svg','everyday-room.webp','stoqnist-family-hero.webp','stoqnist-family-mobile.webp','stoqnist-family-clean.webp']:
    if (ROOT/'assets'/name).exists():public['/assets/'+name]='assets/'+name
# Check the exact versioned URLs browsers request, not only the bare filenames.
for path in list(public.values()):
    if path.endswith('.html'):
        for url in re.findall(r'(?:href|src)="(/[^"?]+\.(?:css|js)\?v=[a-f0-9]{16})"', (ROOT/path).read_text()):
            public[url] = url.split('?', 1)[0].lstrip('/')
for url,path in public.items():
    with urllib.request.urlopen(base+url) as response:
        assert response.status==200,url
        assert response.read()==(ROOT/path).read_bytes(),url+' differs from committed asset'
        assert "media-src 'self'" in response.headers['Content-Security-Policy']
        assert response.headers['X-Content-Type-Options']=='nosniff'
private=['/auth/','/README.md','/localize.py','/build.py','/compose.yaml','/templates/index.html','/locales/en.json','/locales/registry.json','/locale-routes.conf','/media/gunter-morning.json','/media/gunter-morning-bg.mp4','/tests/check_http.py','/publicity/launch.md','/assets/unknown.svg','/pt/','/unknown']
# A planned MP4 is private/absent; once approved it becomes a deliberate public asset.
for url in private:
    if url in public:continue
    try:urllib.request.urlopen(base+url)
    except urllib.error.HTTPError as error:assert error.code==404,(url,error.code)
    else:raise AssertionError('Unexpected public path: '+url)
print(f'PASS: {len(public)} public locale/assets routes and {len(private)} private/unknown paths')

# Every route is served from the deliberate locale allowlist. Unknown child pages stay private.
for url in ('/demos/unknown/','/nl/demos/unknown/','/bg/demos/gunter/private','/demos/gunter/production.json'):
    try:urllib.request.urlopen(base+url)
    except urllib.error.HTTPError as error:assert error.code==404,(url,error.code)
    else:raise AssertionError('Unexpected public route: '+url)
