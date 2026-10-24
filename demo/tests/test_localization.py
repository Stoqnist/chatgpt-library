"""Release gates: untranslated/stale prose, wrong placeholders and premature films."""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('localize',ROOT/'localize.py')
l10n=importlib.util.module_from_spec(spec);spec.loader.exec_module(l10n)

class LocalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'demo'
        shutil.copytree(ROOT,self.root,ignore=shutil.ignore_patterns('__pycache__','tests','assets'))
    def edit(self,name,callback):
        p=self.root/name;data=json.loads(p.read_text());callback(data);p.write_text(json.dumps(data))
    def test_generated_pages_are_complete_and_distinct(self):
        l10n.build(True,self.root)
        files=l10n.outputs(self.root)
        for code in ('en','nl','bg'):
            prefix='' if code=='en' else code+'/'
            home=files[prefix+'index.html']
            catalog=files[prefix+'demos/index.html']
            gunter=files[prefix+'demos/gunter/index.html']
            purchase=files[prefix+'demos/purchase/index.html']
            self.assertIn(f'<html lang="{code}">',home)
            self.assertIn('href="/'+prefix+'demos/gunter/"',catalog)
            self.assertIn('href="/'+prefix+'demos/purchase/"',catalog)
            self.assertIn('id="recovery"',home)  # legacy /#recovery links land on its card
            self.assertIn('id="demo"',home)  # legacy /#demo links land on its card
            self.assertNotIn('id="story-video"',home)
            self.assertNotIn('id="scenarios"',home)
            self.assertIn('id="mood"',gunter)
            self.assertNotIn('id="scenarios"',gunter)
            self.assertIn('id="scenarios"',purchase)
            self.assertNotIn('id="mood"',purchase)
            self.assertIn('href="https://stoq.page/'+prefix+'demos/gunter/"',gunter)
            self.assertIn('href="https://stoq.page/'+prefix+'demos/purchase/"',purchase)
            self.assertNotIn('{{',catalog)
            self.assertNotIn('{{',gunter)
            self.assertNotIn('{{',purchase)
            self.assertIn('id="safety"',gunter)
            self.assertIn('id="privacy"',purchase)
            if code=='en':
                self.assertIn('poster="/media/gunter-morning-en.webp"',gunter)
                self.assertIn('id="film-play" class="film-play" type="button" hidden',gunter)
                self.assertIn('Watch the 55-second film',gunter)
                self.assertIn('id="film-runtime"',gunter)
            else:
                self.assertNotIn('<video',gunter)
            self.assertIn('href="/'+prefix+'demos/gunter/"',home)
        for file in ('demos/index.html','demos/gunter/index.html','demos/purchase/index.html',
                     'nl/demos/index.html','bg/demos/index.html'):
            self.assertIn('COPY '+file+' /usr/share/nginx/html/'+file,files['Dockerfile'])
        self.assertIn('/media/gunter-morning-en.webp',files['locale-routes.conf'])

    def test_new_language_translation_exchange_and_build(self):
        previous=l10n.ROOT;l10n.ROOT=self.root
        try:
            l10n.add('pt','Português')
            packet=self.root/'packet.json';l10n.exchange('pt',packet)
            data=l10n.read(packet)
            self.assertTrue(all(e['state']=='missing' for e in data['entries']))
            # Synthetic translation fixture; tests exchange/routing, not Portuguese quality.
            for entry in data['entries']:entry['translation']='PT '+entry['source']
            packet.write_text(l10n.dump(data));l10n.exchange('pt',packet,True)
            self.edit('locales/registry.json',lambda d:d['locales'][-1].update({'enabled':True}))
            files=l10n.outputs(self.root)
            self.assertIn('pt/index.html',files)
            self.assertIn('/pt/',files['locale-routes.conf'])
            self.assertIn('COPY pt/index.html',files['Dockerfile'])
        finally:l10n.ROOT=previous
    def test_video_export_requires_matching_final_timing(self):
        previous=l10n.ROOT;l10n.ROOT=self.root
        original_load=l10n.load
        try:
            l10n.load=lambda:original_load(self.root)
            output=self.root/'packet';l10n.video_export('bg',output)
            self.assertIn('PROVISIONAL',(output/'gunter-morning-bg.draft.vtt').read_text())
            l10n.video_export('bg',output/'final',output/'timings.json')
            self.assertNotIn('PROVISIONAL',(output/'final/gunter-morning-bg.vtt').read_text())
            timings=l10n.read(output/'timings.json');timings['cues'][1]['start']=0
            (output/'bad.json').write_text(l10n.dump(timings))
            with self.assertRaisesRegex(AssertionError,'overlapping'):
                l10n.video_export('bg',output/'bad',output/'bad.json')
        finally:l10n.ROOT=previous;l10n.load=original_load
    def test_missing_key_fails(self):
        self.edit('locales/nl.json',lambda d:d['messages'].pop('privacy.body2'))
        with self.assertRaisesRegex(AssertionError,'missing/extra'):l10n.load(self.root)
    def test_source_edits_require_translation_refresh(self):
        self.edit('locales/en.json',lambda d:d['messages'].update({'help.note':'New source meaning.'}))
        with self.assertRaisesRegex(AssertionError,'stale translation'):l10n.load(self.root)
    def test_wrong_placeholder_fails(self):
        self.edit('locales/bg.json',lambda d:d['messages'].update({'mood.selected':'Избор: {wrong}'}))
        with self.assertRaisesRegex(AssertionError,'placeholders'):l10n.load(self.root)
    def test_coordinator_prose_drift_fails(self):
        p=self.root/'cases.js';p.write_text(p.read_text().replace('Was desk-lamp actually received into the household?','A new question?'))
        with self.assertRaisesRegex(AssertionError,'Uncatalogued coordinator'):l10n.load(self.root)
    def test_unreviewed_video_cannot_publish(self):
        self.edit('media/gunter-morning.json',lambda d:d['variants']['bg'].update({'status':'ready'}))
        with self.assertRaisesRegex(AssertionError,'stale film copy'):l10n.load(self.root)
    def test_ready_video_needs_final_timing_and_files(self):
        film=l10n.read(self.root/'media/gunter-morning.json');messages=l10n.read(self.root/'locales/bg.json')['messages']
        self.edit('media/gunter-morning.json',lambda d:d['variants']['bg'].update({'status':'ready','contentHash':l10n.film_hash(film,messages)}))
        with self.assertRaisesRegex(AssertionError,'final caption timing'):l10n.load(self.root)
    def test_planned_fallback_is_rejected(self):
        self.edit('media/gunter-morning.json',lambda d:d['fallbacks'].update({'bg':'nl'}))
        with self.assertRaisesRegex(AssertionError,'final captions'):l10n.load(self.root)
    def test_translator_text_is_escaped(self):
        self.edit('locales/bg.json',lambda d:d['messages'].update({'idea.heading1':'<script>alert(1)</script>'}))
        self.assertIn('&lt;script&gt;',l10n.outputs(self.root)['bg/index.html'])
    def test_source_template_has_no_uncatalogued_visible_prose(self):
        from html.parser import HTMLParser
        class CopyCheck(HTMLParser):
            def handle_data(inner,text):
                text=l10n.TOKEN.sub('',text).strip()
                self.assertFalse(any(c.isalpha() for c in text) and text!='stoqnist.',text)
            def handle_starttag(inner,tag,attrs):
                for key,value in attrs:
                    if key in ('alt','aria-label') or (tag=='meta' and key=='content' and 'viewport' not in dict(attrs).get('name','')):
                        self.assertTrue(l10n.TOKEN.fullmatch(value),f'{tag}: {key}={value}')
        CopyCheck().feed((self.root/'templates/index.html').read_text())

if __name__=='__main__':unittest.main()
