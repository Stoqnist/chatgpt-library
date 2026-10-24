#!/usr/bin/env python3
"""Dependency-free localization build, translation exchange and film handoff."""
import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOKEN = re.compile(r'\{\{([\w.]+)\}\}')
PARAM = re.compile(r'\{(\w+)\}')
CODE = re.compile(r'[a-z]{2,3}(?:-[A-Z]{2})?\Z')
SPECIAL = {'locale', 'language_nav', 'locale_head', 'video_section'}

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'

def fingerprint(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]

def film_keys(film):
    return [key for scene in film['scenes'] for key in [scene['narration'], *scene['onScreen']]] + film['screenKeys']

def film_hash(film, messages):
    return fingerprint(dump({'revision':film['revision'], 'scenes':film['scenes'], 'copy':{k:messages[k] for k in film_keys(film)}}))

def path_for(code, default='en'):
    return '/' if code == default else f'/{code}/'

def load(root=ROOT):
    registry = read(root/'locales/registry.json')
    codes = [v['code'] for v in registry['locales']]
    assert len(codes) == len(set(codes)) and all(CODE.fullmatch(c) for c in codes), 'Invalid/duplicate locale code'
    assert registry['default'] == 'en', 'English is the default language'
    enabled = [v for v in registry['locales'] if v['enabled']]
    assert any(v['code']=='en' for v in enabled), 'English must be enabled'
    catalogs = {c:read(root/'locales'/f'{c}.json') for c in codes}
    source = catalogs['en']['messages']
    assert source and all(isinstance(v,str) and v.strip() for v in source.values()), 'Empty English source'
    template = (root/'templates/index.html').read_text(encoding='utf-8')
    assert set(TOKEN.findall(template)) <= set(source)|SPECIAL, 'Uncatalogued template token'
    for config in enabled:
        code=config['code']; catalog=catalogs[code]; messages=catalog['messages']
        assert catalog['locale']==code, f'{code}: catalog locale mismatch'
        assert messages.keys()==source.keys(), f'{code}: missing/extra translation keys'
        for key, value in messages.items():
            assert isinstance(value,str) and value.strip(), f'{code}: empty {key}'
            assert set(PARAM.findall(value))==set(PARAM.findall(source[key])), f'{code}: placeholders in {key}'
            if code!='en':
                assert catalog['sourceHashes'].get(key)==fingerprint(source[key]), f'{code}: stale translation {key}; export/import reviewed copy'
    cases=read_cases(root)
    source_keys={v:k for k,v in source.items() if k.startswith(('claim.','question.','case.'))}
    for value in case_prose(cases):
        assert value in source_keys, f'Uncatalogued coordinator prose: {value}'
    film=read(root/'media/gunter-morning.json')
    assert film['id']=='gunter-morning'
    assert len({s['id'] for s in film['scenes']})==len(film['scenes'])
    assert all(isinstance(s['duration'],(int,float)) and s['duration']>0 for s in film['scenes'])
    assert set(film_keys(film)) <= set(source), 'Uncatalogued film copy'
    validate_media(root, film, catalogs, enabled)
    return registry, catalogs, template, film, source_keys

def read_cases(root):
    return json.loads((root/'cases.js').read_text(encoding='utf-8').split('=',1)[1].strip().removesuffix(';'))

def case_prose(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ('title','detail','claim'): yield item
            elif key == 'unresolved_questions': yield from item
            else: yield from case_prose(item)
    elif isinstance(value,list):
        for item in value: yield from case_prose(item)

def validate_media(root, film, catalogs, enabled):
    codes={v['code'] for v in enabled}
    assert set(film.get('fallbacks',{})) <= codes, 'Fallback locale is not enabled'
    for code in codes:
        variant=film['variants'].get(code)
        assert variant, f'{code}: add a film variant, even if planned'
        assert variant['status'] in ('planned','captioned','ready'), 'Invalid media status'
        if variant['status']=='planned':
            assert code not in film.get('fallbacks',{}), f'{code}: fallback needs final captions'
            continue
        assert variant['sourceRevision']==film['revision'], f'{code}: stale video revision'
        assert variant['contentHash']==film_hash(film,catalogs[code]['messages']), f'{code}: stale film copy'
        assert variant['timingStatus']=='final', f'{code}: final caption timing required'
        check_asset(root,variant['captions'],code,'vtt')
        captions=(root/variant['captions'].lstrip('/')).read_text(encoding='utf-8')
        assert captions.startswith('WEBVTT\n') and '-->' in captions and 'PROVISIONAL' not in captions, f'{code}: invalid/final captions'
        # Captions must cover every spoken scene in the selected language.
        for scene in film['scenes']:
            assert catalogs[code]['messages'][scene['narration']] in captions, f'{code}: missing spoken caption {scene["id"]}'
        if variant['status']=='ready':
            assert variant['audioLocale']==code, f'{code}: declared audio must match variant'
            check_asset(root,variant['video'],code,'mp4')
        else:
            target=film.get('fallbacks',{}).get(code)
            assert target in codes and film['variants'][target]['status']=='ready', f'{code}: captioned variant needs explicit ready fallback'
        if variant.get('poster'):check_asset(root,variant['poster'],code,'webp')

def check_asset(root,url,code,suffix):
    assert url==f'/media/gunter-morning-{code}.{suffix}', f'{code}: invalid {suffix} asset path'
    assert (root/url.lstrip('/')).is_file(), f'{code}: missing asset {url}'

def render_video(code, film, messages, registry):
    esc=html.escape
    items=''.join('<li>'+esc(messages[s['narration']])+'</li>' for s in film['scenes'])
    variant=film['variants'][code]
    player=''
    if variant['status'] in ('ready','captioned'):
        audio=code if variant['status']=='ready' else film['fallbacks'][code]
        ready=film['variants'][audio]
        poster=f' poster="{esc(ready["poster"],quote=True)}"' if ready.get('poster') else ''
        # The approved English master already burns in English subtitles.
        # Keep optional English CC selectable; default translated fallback CC on.
        default_captions = ' default' if variant['status']=='captioned' else ''
        video=f'<video id="story-video" controls playsinline preload="none"{poster} aria-label="{esc(messages["video.description"],quote=True)}"><source src="{ready["video"]}" type="video/mp4"><track kind="captions" src="{variant["captions"]}" srclang="{code}" label="{esc(messages["video.captions"],quote=True)}"{default_captions}></video>'
        # JavaScript reveals this overlay only after binding the click listener.
        # Without JavaScript, the native player remains usable.
        button=f'<button id="film-play" class="film-play" type="button" hidden aria-label="{esc(messages["video.play"],quote=True)}"><span class="film-play-icon" aria-hidden="true">▶</span><span class="film-play-label">{esc(messages["video.play"])}</span></button>'
        seconds=ready.get('durationSeconds')
        runtime=f'<span id="film-runtime" class="film-runtime" aria-hidden="true">{int(seconds)//60}:{int(seconds)%60:02}</span>' if seconds else ''
        player=f'<div class="film-player">{video}{button}{runtime}</div>'
        status=''
        if audio!=code:
            name=next(v['name'] for v in registry['locales'] if v['code']==audio)
            status=messages['video.fallback'].replace('{language}',name)
        player+=f'<p id="video-status" role="status" class="micro">{esc(status)}</p>'
    return f'<section class="film-story" aria-labelledby="film-title"><p class="eyebrow">{esc(messages["video.label"])}</p><h2 id="film-title">{esc(messages["video.title"])}</h2><p class="film-teaser-copy">{esc(messages["video.description"])}</p>{player}<details id="film-transcript"><summary>{esc(messages["video.read"])}</summary><ol>{items}</ol></details>'+ (f'<p class="micro">{esc(messages["video.note"])}</p>' if variant['status']=='planned' else '')+'</section>'

def outputs(root=ROOT):
    registry,catalogs,template,film,source_keys=load(root)
    # Resolve the generator relative to the selected root, including test copies.
    import importlib.util
    spec=importlib.util.spec_from_file_location('demo_page_routes',root/'page_routes.py')
    route_module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(route_module)
    enabled=[v for v in registry['locales'] if v['enabled']]
    files={}
    for config in enabled:
        code=config['code']; messages=catalogs[code]['messages']; path=path_for(code)
        nav='<nav class="language-nav" aria-label="'+html.escape(messages['nav.language'],quote=True)+'"><span>'+html.escape(messages['nav.language'])+'</span>'
        for other in enabled:
            current=' aria-current="page"' if other['code']==code else ''
            nav+=f'<a data-language-link href="{path_for(other["code"])}" lang="{other["code"]}" hreflang="{other["code"]}"{current}>{html.escape(other["name"])}</a>'
        nav+='</nav>'
        head=f'<link rel="canonical" href="https://stoq.page{path}">\n'
        head+='\n'.join(f'<link rel="alternate" hreflang="{v["code"]}" href="https://stoq.page{path_for(v["code"])}">' for v in enabled)
        head+='\n<link rel="alternate" hreflang="x-default" href="https://stoq.page/">'
        special={'locale':code,'language_nav':nav,'locale_head':head,'video_section':render_video(code,film,messages,registry)}
        page=TOKEN.sub(lambda m:special[m[1]] if m[1] in special else html.escape(messages[m[1]],quote=True),template)
        assert not TOKEN.search(page), 'Unresolved template token'
        for suffix, route_page in route_module.render_pages(page,code,messages).items():
            prefix='' if code=='en' else f'{code}/'
            files[prefix+suffix]=route_page
        payload={'locale':code,'messages':messages,'sourceTextKeys':source_keys}
        files[f'locales/{code}.js']='// Generated by demo/localize.py; edit locale JSON sources.\nwindow.STOQ_LOCALE = '+dump(payload).rstrip()+';\n'
    # Generate narrow public routes from enabled locales and ready media, not arbitrary files.
    routes=['location = / { try_files /index.html =404; }','location = /index.html { try_files $uri =404; }']
    for config in enabled:
        code=config['code']
        if code!='en':
            routes += [f'location = /{code} {{ return 301 /{code}/; }}',f'location = /{code}/ {{ try_files /{code}/index.html =404; }}',f'location = /{code}/index.html {{ try_files $uri =404; }}']
        routes += [f'location = /locales/{code}.js {{ try_files $uri =404; }}']
        for section in ('demos', 'demos/gunter', 'demos/purchase'):
            url=route_module.route(code,section+'/')
            routes += [f'location = {url[:-1]} {{ return 301 {url}; }}',
                       f'location = {url} {{ try_files {url}index.html =404; }}',
                       f'location = {url}index.html {{ try_files $uri =404; }}']
    for code,variant in film['variants'].items():
        if code not in [v['code'] for v in enabled] or variant['status']=='planned':continue
        for name in ('video','captions','poster'):
            if variant.get(name):routes.append(f'location = {variant[name]} {{ try_files $uri =404; }}')
    files['locale-routes.conf']='\n'.join(routes)+'\n'
    copies=[]
    context=['Dockerfile','nginx.conf','locale-routes.conf','index.html','style.css','journey.css','brand-journey.css','localization.css','app.js','cases.js','i18n.js','assets/','assets/*.webp','assets/stoqnist-banner.svg','assets/stoqnist-banner-mobile.svg','locales/']
    for config in enabled:
        code=config['code']
        copies.append(f'COPY locales/{code}.js /usr/share/nginx/html/locales/{code}.js')
        context.append(f'locales/{code}.js')
        if code!='en':
            copies.append(f'COPY {code}/index.html /usr/share/nginx/html/{code}/index.html')
            context.extend([code+'/',code+'/index.html'])
        prefix='' if code=='en' else f'{code}/'
        for section in ('demos', 'demos/gunter', 'demos/purchase'):
            asset=f'{prefix}{section}/index.html'
            copies.append(f'COPY {asset} /usr/share/nginx/html/{asset}')
            context.extend([prefix+'demos/',prefix+section+'/',asset])
        variant=film['variants'][code]
        if variant['status']!='planned':
            for name in ('video','captions','poster'):
                if variant.get(name):
                    asset=variant[name].lstrip('/')
                    copies.append(f'COPY {asset} /usr/share/nginx/html/{asset}')
                    context.extend(['media/',asset])
    files['Dockerfile']=(root/'templates/Dockerfile').read_text(encoding='utf-8').replace('{{localized_copies}}','\n'.join(copies))
    files['.dockerignore']='# Generated by demo/localize.py. Only public files enter the image build.\n*\n'+'\n'.join('!'+path+('\n'+path+'*' if path.endswith('/') else '') for path in dict.fromkeys(context))+'\n'
    return files

def build(check=False,root=ROOT):
    files=outputs(root)
    for name,content in files.items():
        path=root/name
        if check:assert path.is_file() and path.read_text(encoding='utf-8')==content, f'Stale generated file: {name}; run python3 demo/localize.py build'
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8')
    print(f'PASS: {len(files)} localization outputs verified' if check else f'Built {len(files)} localization outputs')

def add(code,name):
    assert CODE.fullmatch(code), 'Use a language tag such as pt, pl, ro or pt-BR'
    registry=read(ROOT/'locales/registry.json')
    assert code not in [v['code'] for v in registry['locales']], 'Locale already exists'
    source=read(ROOT/'locales/en.json')['messages']
    catalog={'locale':code,'review':'draft-translation','messages':{k:'' for k in source},'sourceHashes':{}}
    (ROOT/'locales'/f'{code}.json').write_text(dump(catalog),encoding='utf-8')
    registry['locales'].append({'code':code,'name':name,'enabled':False})
    (ROOT/'locales/registry.json').write_text(dump(registry),encoding='utf-8')
    film=read(ROOT/'media/gunter-morning.json')
    film['variants'][code]={'status':'planned','audioLocale':code,'video':None,'captions':None,'poster':None,'timingStatus':'provisional','sourceRevision':film['revision'],'contentHash':None}
    (ROOT/'media/gunter-morning.json').write_text(dump(film),encoding='utf-8')
    print(f'Created disabled locale {code}. Export, translate, import, then enable it in registry.json.')

def exchange(code,path,importing=False):
    registry=read(ROOT/'locales/registry.json')
    assert code in [v['code'] for v in registry['locales']] and code!='en', 'Choose a registered target locale'
    source=read(ROOT/'locales/en.json')['messages'];target=read(ROOT/'locales'/f'{code}.json')
    if not importing:
        packet={'locale':code,'entries':[{'key':k,'source':v,'sourceHash':fingerprint(v),'translation':target['messages'].get(k,''),'state':'missing' if not target['messages'].get(k) else 'stale' if target['sourceHashes'].get(k)!=fingerprint(v) else 'current'} for k,v in source.items()]}
        path.write_text(dump(packet),encoding='utf-8')
    else:
        packet=read(path);assert packet['locale']==code, 'Wrong locale packet'
        assert len({e['key'] for e in packet['entries']})==len(packet['entries']), 'Duplicate import key'
        for entry in packet['entries']:
            k=entry['key'];v=entry['translation']
            assert k in source and entry['sourceHash']==fingerprint(source[k]), f'Source changed since export: {k}'
            assert isinstance(v,str) and v.strip(), f'Empty translation: {k}'
            assert set(PARAM.findall(v))==set(PARAM.findall(source[k])), f'Placeholder mismatch: {k}'
            target['messages'][k]=v;target['sourceHashes'][k]=entry['sourceHash']
        target['messages']={k:v for k,v in target['messages'].items() if k in source}
        target['sourceHashes']={k:v for k,v in target['sourceHashes'].items() if k in source}
        (ROOT/'locales'/f'{code}.json').write_text(dump(target),encoding='utf-8')
    print('Imported reviewed translation packet' if importing else 'Exported translation packet')

def timestamp(seconds):
    ms=round(seconds*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
    return f'{h:02}:{m:02}:{s:02}.{ms:03}'

def video_export(code,destination,timings=None):
    registry,catalogs,_,film,_=load()
    assert code in catalogs
    messages=catalogs[code]['messages'];assert all(messages.get(k) for k in film_keys(film)), 'Translate all film copy first'
    final=read(timings) if timings else None
    if final:
        assert final['locale']==code and final['contentHash']==film_hash(film,messages), 'Timing sheet must match this locale and current film content hash'
        assert final['duration']>0 and len(final['cues'])==len(film['scenes']), 'Timing sheet must cover every scene'
    scenes=[];cues=[];offset=0;previous_end=0
    for i,scene in enumerate(film['scenes']):
        timing=final['cues'][i] if final else {'id':scene['id'],'start':offset+.9,'end':offset+scene['duration']-.2}
        assert timing['id']==scene['id'] and previous_end<=timing['start']<timing['end'], 'Invalid/overlapping caption timing'
        if final:assert timing['end']<=final['duration'], 'Cue extends beyond rendered film'
        previous_end=timing['end']
        cues.append(f'{scene["id"]}\n{timestamp(timing["start"])} --> {timestamp(timing["end"])}\n{messages[scene["narration"]]}\n')
        scenes.append({**scene,'narration':messages[scene['narration']],'onScreen':[messages[k] for k in scene['onScreen']],'captionStart':timing['start'],'captionEnd':timing['end']})
        offset+=scene['duration']
    destination.mkdir(parents=True,exist_ok=True)
    packet={'id':film['id'],'locale':code,'sourceRevision':film['revision'],'contentHash':film_hash(film,messages),'timingStatus':'final' if final else 'provisional','scenes':scenes,'screens':{k:messages[k] for k in film['screenKeys']}}
    (destination/'production.json').write_text(dump(packet),encoding='utf-8')
    (destination/'narration.txt').write_text('\n\n'.join(s['narration'] for s in scenes)+'\n',encoding='utf-8')
    name=f'gunter-morning-{code}'+('.vtt' if final else '.draft.vtt')
    (destination/name).write_text('WEBVTT\n\n'+('' if final else 'NOTE PROVISIONAL — retime against the final localized voice recording.\n\n')+'\n'.join(cues),encoding='utf-8')
    (destination/'timings.json').write_text(dump({'locale':code,'contentHash':packet['contentHash'],'duration':final['duration'] if final else offset,'cues':[{'id':s['id'],'start':s['captionStart'],'end':s['captionEnd']} for s in scenes]}),encoding='utf-8')
    print(f'Exported {code} film package ({packet["timingStatus"]} timing) to {destination}')

def report():
    registry=read(ROOT/'locales/registry.json');source=read(ROOT/'locales/en.json')['messages'];film=read(ROOT/'media/gunter-morning.json')
    for config in registry['locales']:
        code=config['code'];c=read(ROOT/'locales'/f'{code}.json')
        missing=[k for k in source if not c['messages'].get(k)]
        stale=[] if code=='en' else [k for k in source if c['messages'].get(k) and c['sourceHashes'].get(k)!=fingerprint(source[k])]
        print(f'{code}: {len(source)-len(missing)}/{len(source)} messages; {len(stale)} stale; {"enabled" if config["enabled"] else "disabled"}; copy review: {c["review"]}; film: {film["variants"][code]["status"]}')
        if missing:print('  Missing: '+', '.join(missing))
        if stale:print('  Stale: '+', '.join(stale))

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('build');sub.add_parser('check');sub.add_parser('report')
    p=sub.add_parser('add');p.add_argument('locale');p.add_argument('--name',required=True)
    for name in ('export','import'):
        p=sub.add_parser(name);p.add_argument('locale');p.add_argument('path',type=Path)
    p=sub.add_parser('video-export');p.add_argument('locale');p.add_argument('destination',type=Path);p.add_argument('--timings',type=Path)
    args=parser.parse_args()
    if args.command in ('build','check'):build(args.command=='check')
    elif args.command=='report':report()
    elif args.command=='add':add(args.locale,args.name)
    elif args.command in ('export','import'):exchange(args.locale,args.path,args.command=='import')
    elif args.command=='video-export':video_export(args.locale,args.destination,args.timings)

if __name__=='__main__':
    try:main()
    except (AssertionError,KeyError,ValueError) as error:
        print(f'Localization error: {error}',file=sys.stderr);sys.exit(1)
