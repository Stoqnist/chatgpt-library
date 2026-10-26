import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import App, OpenAIProvider, ProviderError, ROUTE_SCHEMA, RESULT_SCHEMA, PLAN_SCHEMA, password_hash

PROMPT='Help me plan my day. I slept well. I want to tidy the kitchen. I have an hour this morning.'
RESULT={'summary':'A manageable next step, based on your report.','suggestions':['Choose one small task.'],'missing_context':['No connected records were checked.'],'question':''}
class FakeProvider:
    def __init__(self, route=None, fail=None, block=None):
        self.calls=[];self.route=route;self.fail=fail;self.block=block
    def call(self,instructions,payload,schema):
        self.calls.append((instructions,payload,schema))
        if schema is ROUTE_SCHEMA:
            if self.block:self.block.wait(3)
            return self.route or {'urgent':False,'tasks':[
                {'domain':'wellbeing','excerpts':['I slept well.']},
                {'domain':'home','excerpts':['I want to tidy the kitchen.']},
                {'domain':'planning','excerpts':['I have an hour this morning.']} ]}
        if schema is PLAN_SCHEMA:
            return {'step_ids':list(payload['suggestions'])[:3], 'question_owner':''}
        if self.fail and self.fail in instructions:raise ProviderError('fake failure containing SECRET')
        return copy.deepcopy(RESULT)

class DailyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.login_hash=password_hash('local-test-access-code')
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.provider=FakeProvider()
        self.app=App(self.tmp.name,'https://daily.example',self.login_hash,self.provider)
        self.app.key_path.write_text('sk-'+('x'*30));os.chmod(self.app.key_path,0o600)
        self.cookie='';self.csrf=''
    def tearDown(self):self.app.pool.shutdown(wait=True);self.tmp.cleanup()
    def request(self,path,body=None,origin='https://daily.example',csrf=None,cookie=None):
        blob=json.dumps(body).encode() if body is not None else b''
        env={'PATH_INFO':path,'REQUEST_METHOD':'POST' if body is not None else 'GET','wsgi.input':io.BytesIO(blob),'CONTENT_LENGTH':str(len(blob)),'CONTENT_TYPE':'application/json','HTTP_ORIGIN':origin,'HTTP_COOKIE':self.cookie if cookie is None else cookie,'HTTP_X_CSRF_TOKEN':self.csrf if csrf is None else csrf}
        capture={}
        def start(status,headers):capture.update(status=int(status.split()[0]),headers=dict(headers))
        raw=b''.join(self.app(env,start));capture['raw']=raw
        if capture['headers']['Content-Type']=='application/json':capture['json']=json.loads(raw)
        return capture
    def login(self):
        r=self.request('/daily/api/login',{'password':'local-test-access-code'})
        self.assertEqual(r['status'],200);self.cookie=r['headers']['Set-Cookie'].split(';')[0]
        self.csrf=self.request('/daily/api/state')['json']['csrf'];return r
    def finish(self):
        self.app.pool.shutdown(wait=True)
        return self.request('/daily/api/state')['json']['runs'][0]
    def submit(self,request_id=None,prompt=PROMPT):return self.request('/daily/api/run',{'prompt':prompt,'request_id':request_id or str(uuid.uuid4())})
    def test_private_state_requires_session_and_shell_has_no_private_data(self):
        for path in ('/daily/api/state','/daily/api/run','/daily/openai-key','/daily/../app.py'):
            self.assertEqual(self.request(path)['status'],401)
        shell=self.request('/daily/');self.assertEqual(shell['status'],200)
        self.assertNotIn(b'sk-xxxxxxxx',shell['raw']);self.assertIn('no-store',shell['headers']['Cache-Control'])
    def test_login_cookie_and_logout_revoke_session(self):
        r=self.login();cookie=r['headers']['Set-Cookie']
        for flag in ('Secure','HttpOnly','SameSite=Strict','Path=/'):self.assertIn(flag,cookie)
        self.assertEqual(self.request('/daily/api/logout',{})['status'],200)
        self.assertEqual(self.request('/daily/api/state')['status'],401)
    def test_mutations_reject_cross_origin_and_bad_csrf(self):
        self.login()
        for path,body in [('/daily/api/settings',{'api_key':'sk-'+('x'*30)}),('/daily/api/run',{'prompt':PROMPT,'request_id':str(uuid.uuid4())}),('/daily/api/clear',{}),('/daily/api/logout',{})]:
            self.assertEqual(self.request(path,body,origin='https://other.example')['status'],403)
            self.assertEqual(self.request(path,body,csrf='wrong')['status'],403)
        self.assertEqual(self.request('/daily/api/login',{'password':'local-test-access-code'},origin='https://other.example')['status'],403)
        self.assertEqual(len(self.provider.calls),0)
    def test_login_rate_limited(self):
        for _ in range(8):self.assertEqual(self.request('/daily/api/login',{'password':'bad'})['status'],401)
        self.assertEqual(self.request('/daily/api/login',{'password':'local-test-access-code'})['status'],429)
    def test_key_saved_private_and_never_returned(self):
        self.login();key='sk-'+('z'*30)
        self.assertEqual(self.request('/daily/api/settings',{'api_key':key})['status'],200)
        self.assertEqual(self.app.key_path.stat().st_mode&0o777,0o600)
        self.assertNotIn(key.encode(),self.request('/daily/api/state')['raw'])
    def test_three_real_dispatches_with_scoped_excerpts(self):
        self.login();self.assertEqual(self.submit()['status'],202)
        run=self.finish();self.assertEqual(run['status'],'completed');self.assertEqual(len(self.provider.calls),5)
        self.assertEqual(len(run['result']['next_steps']),1)
        payloads=[c[1] for c in self.provider.calls[1:] if c[2] is not PLAN_SCHEMA]
        self.assertEqual(sorted([p['user_reported_excerpts'][0] for p in payloads]),sorted(['I slept well.','I want to tidy the kitchen.','I have an hour this morning.']))
        self.assertTrue(all('tools' not in p for p in payloads))

    def test_fictional_unassessed_pain_stretching_advice_is_not_displayed(self):
        prompt = 'A fictional person reports shoulder pain today.'
        self.provider.route = {'urgent': False, 'tasks': [
            {'domain': 'wellbeing', 'excerpts': [prompt]}
        ]}
        original = self.provider.call

        def unsafe(instructions, payload, schema):
            if schema is RESULT_SCHEMA:
                return {**RESULT, 'suggestions': [
                    'Try gentle stretching exercises for the painful shoulder.'
                ]}
            return original(instructions, payload, schema)

        self.provider.call = unsafe
        self.login()
        self.assertEqual(self.submit(prompt=prompt)['status'], 202)
        run = self.finish()
        self.assertEqual(run['status'], 'failed')
        self.assertEqual(run['result']['next_steps'], [])
        self.assertEqual(run['result']['agents'][0]['status'], 'failed')
        self.assertNotIn('stretching', json.dumps(run['result']).lower())
        self.assertEqual(len(self.provider.calls), 1)

    def test_fictional_unassessed_pain_cautious_advice_allowed(self):
        prompt = 'A fictional person reports shoulder pain today.'
        self.provider.route = {'urgent': False, 'tasks': [
            {'domain': 'wellbeing', 'excerpts': [prompt]}
        ]}
        original = self.provider.call

        def cautious(instructions, payload, schema):
            if schema is RESULT_SCHEMA:
                return {**RESULT, 'suggestions': [
                    'Consider professional advice if this is new, worsening or persistent.'
                ]}
            return original(instructions, payload, schema)

        self.provider.call = cautious
        self.login()
        self.assertEqual(self.submit(prompt=prompt)['status'], 202)
        run = self.finish()
        self.assertEqual(run['status'], 'completed')
        self.assertEqual(run['result']['agents'][0]['domain'], 'wellbeing')
        self.assertEqual(len(run['result']['next_steps']), 1)

    def test_wellbeing_contract_for_unassessed_symptoms(self):
        from app import DOMAINS, unsafe_pain_advice
        wellbeing = DOMAINS['wellbeing'][1].lower()
        self.assertIn('unassessed pain', wellbeing)
        self.assertIn('do not diagnose', wellbeing)
        self.assertTrue(unsafe_pain_advice(
            ['fictional shoulder pain'],
            {**RESULT, 'suggestions': ['Try stretches to relieve pain.']}))
        self.assertFalse(unsafe_pain_advice(
            ['fictional shoulder pain'],
            {**RESULT, 'suggestions': ['Consider speaking to a clinician.']}))

    def test_fictional_unassessed_discomfort_warm_compress_is_not_displayed(self):
        prompt = 'A fictional person has shoulder discomfort.'
        self.provider.route = {'urgent': False, 'tasks': [
            {'domain': 'wellbeing', 'excerpts': [prompt]}
        ]}
        original = self.provider.call

        def unsupported(instructions, payload, schema):
            if schema is RESULT_SCHEMA:
                return {**RESULT, 'suggestions': [
                    'Apply a warm compress to the affected area.'
                ]}
            return original(instructions, payload, schema)

        self.provider.call = unsupported
        self.login()
        self.assertEqual(self.submit(prompt=prompt)['status'], 202)
        run = self.finish()
        self.assertEqual(run['status'], 'failed')
        self.assertEqual(run['result']['agents'][0]['status'], 'failed')
        self.assertNotIn('compress', json.dumps(run['result']).lower())
        self.assertEqual(len(self.provider.calls), 1)

    def test_unsupported_remedies_without_an_imperative_are_flagged(self):
        from app import unsafe_pain_advice
        examples = [
            'Consider gently stretching the shoulder region to feel better.',
            'Apply a warm compress to the area.',
            'Use a heating pad for relief.',
            'Try a massage to loosen the muscle.',
            'Use ice packs for soreness.',
            'Take ibuprofen to help the pain.',
            'Should I start stretching to reduce discomfort?',
        ]
        for wording in examples:
            with self.subTest(wording=wording):
                result = {**RESULT, 'suggestions': [wording]}
                self.assertTrue(unsafe_pain_advice(
                    ['A fictional person reports soreness.'], result))
        self.assertFalse(unsafe_pain_advice(
            ['A fictional person reports soreness.'],
            {**RESULT, 'suggestions': [
                'Consider asking a qualified clinician about new or worsening symptoms.'
            ]}))
        self.assertTrue(unsafe_pain_advice(
            ['A fictional person reports shoulder pain.'],
            {**RESULT, 'question': 'Should I start stretching?'}))

    def test_private_health_excerpt_not_sent_to_other_specialists_or_final_coordinator(self):
        prompt = ('My prescription changed. I want to tidy the kitchen. '
                  'I have an hour this morning.')
        self.provider.route = {'urgent': False, 'tasks': [
            {'domain': 'wellbeing', 'excerpts': ['My prescription changed.']},
            {'domain': 'home', 'excerpts': ['I want to tidy the kitchen.']},
            {'domain': 'planning', 'excerpts': ['I have an hour this morning.']},
        ]}
        self.login()
        self.assertEqual(self.submit(prompt=prompt)['status'], 202)
        run = self.finish()
        self.assertEqual(run['status'], 'completed')
        calls = self.provider.calls
        self.assertEqual(len(calls), 5)
        for instructions, payload, schema in calls[1:]:
            if schema is PLAN_SCHEMA:
                self.assertNotIn('check_in', payload)
                self.assertEqual(payload['routine_goals'], [
                    'I want to tidy the kitchen.', 'I have an hour this morning.'])
                self.assertNotIn('prescription', json.dumps(payload).lower())
            elif payload.get('user_reported_excerpts') != ['My prescription changed.']:
                self.assertNotIn('prescription', json.dumps(payload).lower())

    def test_sensitive_health_handoff_to_home_fails_closed(self):
        prompt = 'My prescription changed. I want to tidy the kitchen.'
        self.provider.route = {'urgent': False, 'tasks': [
            {'domain': 'home', 'excerpts': ['My prescription changed.']}
        ]}
        self.login();self.submit(prompt=prompt);run=self.finish()
        self.assertEqual(run['status'], 'failed')
        self.assertEqual(len(self.provider.calls), 1)
        self.assertIn('separate private details', run['result']['message'])

    def test_financial_handoff_to_planning_fails_closed(self):
        prompt = 'My salary changed. I have an hour this morning.'
        self.provider.route = {'urgent': False, 'tasks': [
            {'domain': 'planning', 'excerpts': ['My salary changed.']}
        ]}
        self.login();self.submit(prompt=prompt);run=self.finish()
        self.assertEqual(run['status'], 'failed')
        self.assertEqual(len(self.provider.calls), 1)

    def test_recognizable_pasted_key_rejected_before_storage_or_model(self):
        self.login()
        fake_key = 'sk-proj-' + 'z' * 36  # Nonfunctional fixture, never a credential
        response = self.submit(prompt='Please save ' + fake_key)
        self.assertEqual(response['status'], 400)
        self.assertEqual(self.provider.calls, [])
        with self.app.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM runs').fetchone()[0], 0)
        self.assertNotIn(fake_key, json.dumps(response.get('json', {})))

    def test_one_domain_does_not_invoke_other_agents(self):
        self.provider.route={'urgent':False,'tasks':[{'domain':'planning','excerpts':['I have an hour this morning.']}]}
        self.login();self.submit();run=self.finish();self.assertEqual(len(run['result']['agents']),1);self.assertEqual(len(self.provider.calls),3)
    def test_provider_failure_returns_partial_without_raw_error(self):
        self.provider.fail='home, food';self.login();self.submit();run=self.finish()
        self.assertEqual(run['status'],'partial');self.assertNotIn('SECRET',json.dumps(run))
    def test_fabricated_handoff_and_duplicate_domains_fail_before_specialists(self):
        self.provider.route={'urgent':False,'tasks':[{'domain':'home','excerpts':['Invented inventory: ten apples.']}]}
        self.login();self.submit();run=self.finish();self.assertEqual(run['status'],'failed');self.assertEqual(len(self.provider.calls),1)
    def test_urgent_input_stops_before_specialists(self):
        self.provider.route={'urgent':True,'tasks':[]};self.login();self.submit();run=self.finish()
        self.assertEqual(run['status'],'needs_attention');self.assertEqual(len(self.provider.calls),1)
    def test_duplicate_request_does_not_charge_twice_and_conflicting_reuse_fails(self):
        self.login();rid=str(uuid.uuid4());a=self.submit(rid);b=self.submit(rid)
        self.assertEqual(a['json']['id'],b['json']['id']);self.assertEqual(self.submit(rid,'A different input')['status'],409)
        self.finish();self.assertEqual(len(self.provider.calls),5)
    def test_concurrent_run_and_settings_mutation_blocked(self):
        event=threading.Event();self.provider.block=event;self.login();self.submit()
        try:
            self.assertEqual(self.submit()['status'],409)
            self.assertEqual(self.request('/daily/api/settings',{'api_key':'sk-'+('z'*30)})['status'],409)
            self.assertEqual(self.request('/daily/api/clear',{})['status'],409)
        finally:event.set()
    def test_limit_not_reset_by_clearing_history(self):
        self.login()
        with self.app.db() as db:db.executemany('INSERT INTO usage VALUES (?)',[(time.time(),)]*20)
        self.assertEqual(self.request('/daily/api/clear',{})['status'],200)
        self.assertEqual(self.submit()['status'],429)
    def test_missing_key_prevents_model_call(self):
        self.login();self.app.key_path.unlink();self.assertEqual(self.submit()['status'],503);self.assertEqual(self.provider.calls,[])
    def test_restart_marks_running_interrupted_without_replay(self):
        with self.app.db() as db:db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?)',('x','x','private',time.time(),'running','{}'))
        app2=App(self.tmp.name,'https://daily.example',self.login_hash,self.provider)
        try:
            with app2.db() as db:self.assertEqual(db.execute('SELECT status FROM runs').fetchone()[0],'interrupted')
            self.assertEqual(self.provider.calls,[])
        finally:app2.pool.shutdown()
    def test_expired_sessions_and_retention(self):
        self.login()
        with self.app.db() as db:
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?)',('x','x','old private',time.time()-8*86400,'completed','{}'))
        self.assertEqual(self.request('/daily/api/state')['json']['runs'],[])
        with self.app.db() as db:db.execute('UPDATE sessions SET expires=0')
        self.assertEqual(self.request('/daily/api/state')['status'],401)
    def test_provider_contract_uses_fixed_https_store_false_and_no_tools(self):
        captured={}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return json.dumps({'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(RESULT)}]}]}).encode()
        def send(req,timeout):captured.update(url=req.full_url,body=json.loads(req.data),timeout=timeout);return Response()
        with patch('urllib.request.urlopen',send):
            r=OpenAIProvider(self.app.key_path,'gpt-4.1-mini').call('bounded',{},ROUTE_SCHEMA)
        self.assertEqual(r,RESULT);self.assertFalse(captured['body']['store']);self.assertNotIn('tools',captured['body'])
        self.assertEqual(captured['url'],'https://api.openai.com/v1/responses');self.assertEqual(captured['timeout'],45)
    def test_unowned_coordinator_action_is_rejected(self):
        original=self.provider.call
        def invalid(instructions,payload,schema):
            if schema is PLAN_SCHEMA:return {'step_ids':['invented:0'],'question_owner':''}
            return original(instructions,payload,schema)
        self.provider.call=invalid;self.login();self.submit();run=self.finish()
        self.assertEqual(run['status'],'partial');self.assertEqual(run['result']['next_steps'],[])
        self.assertIn('consolidation_error',run['result'])
    def test_empty_specialist_advice_is_not_a_completed_plan(self):
        original=self.provider.call
        def empty(instructions,payload,schema):
            if schema is not ROUTE_SCHEMA and schema is not PLAN_SCHEMA:
                return {**RESULT,'suggestions':[]}
            return original(instructions,payload,schema)
        self.provider.call=empty;self.login();self.submit();run=self.finish()
        self.assertEqual(run['status'],'partial');self.assertEqual(run['result']['next_steps'],[])
    def test_provider_incomplete_rejected(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return b'{"status":"incomplete"}'
        with patch('urllib.request.urlopen',lambda *a,**k:Response()):
            with self.assertRaises(ProviderError):OpenAIProvider(self.app.key_path,'gpt-4.1-mini').call('bounded',{},ROUTE_SCHEMA)

if __name__=='__main__':unittest.main()
