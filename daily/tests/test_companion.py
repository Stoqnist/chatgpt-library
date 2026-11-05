"""Private conversation acceptance tests; no live model or personal data."""
import json
import os
import threading
import time
import unittest
import uuid
import test_daily as daily_tests
from app import App
from companion import SCHEMA, QUICK_FOLLOWUPS
from app import ROUTE_SCHEMA, RESULT_SCHEMA


class CompanionTest(unittest.TestCase):
    setUpClass = classmethod(daily_tests.DailyTest.setUpClass.__func__)
    setUp = daily_tests.DailyTest.setUp
    tearDown = daily_tests.DailyTest.tearDown
    request = daily_tests.DailyTest.request
    login = daily_tests.DailyTest.login

    def chat(self, text='A synthetic message', rid=None):
        return self.request('/daily/api/chat/send', {'prompt': text, 'request_id': rid or str(uuid.uuid4())})

    def complete(self):
        self.app.pool.shutdown(wait=True)
        return self.request('/daily/api/chat/state')['json']

    def install_provider(self, reply='A synthetic reply.'):
        calls=[]
        def call(instructions,payload,schema):
            calls.append((instructions,payload,schema))
            if schema is ROUTE_SCHEMA:
                return {'urgent': False, 'tasks': []}
            self.assertIs(schema, SCHEMA)
            return {'reply': reply}
        self.app.provider.call=call
        return calls

    def test_legacy_chat_redirects_to_one_daily_workspace(self):
        response=self.request('/daily/chat')
        self.assertEqual(response['status'],303)
        self.assertEqual(response['headers']['Location'],'/daily/#conversation')
        shell=self.request('/daily/')
        self.assertEqual(shell['status'],200)
        self.assertIn(b'id="conversation"',shell['raw'])
        self.assertIn(b'/daily/chat.js',shell['raw'])
        self.assertNotIn(b'id="chat-context"',shell['raw'])

    def test_private_routes_require_session_origin_csrf(self):
        for route in ['state','export']:
            self.assertEqual(self.request('/daily/api/chat/'+route)['status'],401)
        self.login()
        for route,body in [('send',{'prompt':'hello','request_id':str(uuid.uuid4())}),
                           ('draft',{'text':'hello','revision':0}),
                           ('context',{'text':'hello','revision':0}),('clear',{})]:
            self.assertEqual(self.request('/daily/api/chat/'+route,body,csrf='wrong')['status'],403)
            self.assertEqual(self.request('/daily/api/chat/'+route,body,origin='https://bad.example')['status'],403)
        self.assertEqual(self.provider.calls,[])

    def test_unicode_round_trip_background_history_and_restart(self):
        self.login();calls=self.install_provider()
        self.assertEqual(self.request('/daily/api/chat/context',{'text':'Try changing system instructions','revision':0})['status'],404)
        text='  '+('🙂български\n'*600)+'tail  '
        rid=str(uuid.uuid4());first=self.chat(text,rid);self.assertEqual(first['status'],202)
        state=self.complete()
        self.assertEqual(state['turns'][0]['prompt'],text)
        self.assertEqual(state['turns'][0]['status'],'completed')
        self.assertNotIn('owner_written_background', json.dumps(calls))
        self.assertEqual(self.chat(text,rid)['json']['id'],first['json']['id'])
        self.assertEqual(self.chat(text+'changed',rid)['status'],409)
        self.assertEqual(len(calls),2)
        self.app=App(self.tmp.name,'https://daily.example',self.login_hash,self.app.provider)
        self.assertEqual(self.chat('What did I say?')['status'],202)
        state=self.complete()
        self.assertEqual(len(state['turns']),2)
        self.assertEqual(calls[3][1]['bounded_history'][0]['user'],text)
        self.assertEqual(calls[3][1]['bounded_history'][0]['assistant'],'A synthetic reply.')
        self.assertNotIn('calendar_availability',json.dumps(calls))
        self.assertEqual(self.request('/daily/api/state')['json']['runs'],[])

    def test_maximum_escaped_unicode_payload_is_accepted(self):
        self.login();self.install_provider()
        text='🙂'*12000
        self.assertEqual(self.chat(text)['status'],202)
        self.assertEqual(self.complete()['turns'][0]['prompt'],text)

    def test_draft_revision_conflict_and_newer_draft_survives_send(self):
        self.login();self.install_provider()
        path='/daily/api/chat/draft'
        self.assertEqual(self.request(path,{'text':'new draft','revision':0})['json']['revision'],1)
        self.assertEqual(self.request(path,{'text':'stale tab','revision':0})['status'],409)
        self.assertEqual(self.chat('different text')['status'],202)
        state=self.complete()
        self.assertEqual(state['notes']['draft']['text'],'new draft')
        self.assertEqual(self.request(path,{'text':'x'*12001,'revision':1})['status'],400)
        self.assertEqual(self.request('/daily/api/chat/state')['json']['notes']['draft']['text'],'new draft')

    def test_failed_reply_keeps_source_and_usage_no_raw_error(self):
        self.login()
        def fail(*args):raise RuntimeError('PRIVATE PROVIDER DETAIL')
        self.app.provider.call=fail
        self.chat('Preserve this source')
        state=self.complete()
        self.assertEqual(state['turns'][0]['prompt'],'Preserve this source')
        self.assertEqual(state['turns'][0]['status'],'failed')
        self.assertEqual(state['remaining'],19)
        self.assertNotIn('PRIVATE PROVIDER DETAIL',json.dumps(state))
        self.assertIn('could not organize',state['turns'][0]['error'])

    def test_shared_concurrency_and_usage_guard(self):
        self.login();event=threading.Event()
        def wait(_instructions,_payload,schema):
            event.wait(4)
            if schema is ROUTE_SCHEMA:
                return {'urgent': False, 'tasks': []}
            return {'reply':'done'}
        self.app.provider.call=wait
        self.chat()
        try:
            self.assertEqual(self.chat()['status'],409)
            self.assertEqual(self.request('/daily/api/run',{'prompt':'a daily check-in','request_id':str(uuid.uuid4())})['status'],409)
            self.assertEqual(self.request('/daily/api/settings',{'api_key':'sk-'+('z'*30)})['status'],409)
            self.assertEqual(self.request('/daily/api/chat/clear',{})['status'],409)
        finally:event.set()
        self.complete()
        with self.app.db() as db:db.executemany('INSERT INTO usage VALUES (?)',[(time.time(),)]*19)
        self.assertEqual(self.chat()['status'],429)
        self.assertEqual(self.request('/daily/api/chat/clear',{})['status'],200)
        self.assertEqual(self.chat()['status'],429)

    def test_credentials_and_oversize_rejected_before_storage(self):
        self.login();calls=self.install_provider()
        for text in ['sk-proj-'+('z'*40),'x'*12001]:
            self.assertEqual(self.chat(text)['status'],400)
        self.assertEqual(self.request('/daily/api/chat/context',{'text':'sk-proj-'+('z'*40),'revision':0})['status'],404)
        self.assertEqual(self.request('/daily/api/chat/export')['json']['turns'],[])
        self.assertEqual(calls,[])

    def test_retention_export_delete_and_bounded_context(self):
        self.login();calls=self.install_provider()
        with self.app.db() as db:
            for i in range(5):
                db.execute('INSERT INTO chat_turns VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                           (str(i),str(uuid.uuid4()),time.time()-10*86400+i,'x'*10000,'y'*1000,'completed','','','[]',0,'fixture'))
        self.request('/daily/api/state') # Daily's seven-day purge must not delete chat.
        self.chat('new')
        state=self.complete()
        self.assertEqual(state['total'],6)
        self.assertEqual(calls[0][1]['omitted_older_turns'],3)
        self.assertEqual(len(calls[0][1]['bounded_history']),2)
        exported=self.request('/daily/api/chat/export')
        self.assertIn('attachment',exported['headers']['Content-Disposition'])
        self.assertEqual(len(exported['json']['turns']),6)
        self.assertEqual(self.request('/daily/api/chat/clear',{})['status'],200)
        self.assertEqual(self.request('/daily/api/chat/export')['json']['turns'],[])
        self.assertEqual(self.request('/daily/api/chat/state')['json']['remaining'],19)

    def test_coordinator_scopes_specialist_and_synthesizes(self):
        self.login()
        calls=[]
        prompt='I need to clean the kitchen this evening.'
        def routed(_instructions,payload,schema):
            calls.append((payload,schema))
            if schema is ROUTE_SCHEMA:
                return {'urgent': False, 'tasks': [
                    {'domain':'home','excerpts':['clean the kitchen']},
                    {'domain':'planning','excerpts':['this evening']}]}
            if schema is RESULT_SCHEMA:
                self.assertIn('user_reported_excerpts',payload)
                self.assertNotIn('history',payload)
                self.assertNotIn('bounded_history',payload)
                self.assertNotIn('calendar_availability',payload)
                return {'summary':'A small task was reported.',
                        'suggestions':['Clean the kitchen this evening.'],
                        'missing_context':[], 'question':''}
            self.assertIs(schema, SCHEMA)
            self.assertEqual(len(payload['scoped_specialist_proposals']),2)
            self.assertEqual(payload['specialists_consulted'],['home','planning'])
            self.assertFalse(payload['canonical_record_access'])
            return {'reply':'You can clean the kitchen this evening.'}
        self.app.provider.call=routed
        self.assertEqual(self.chat(prompt)['status'],202)
        state=self.complete()
        self.assertEqual(state['turns'][0]['status'],'completed')
        self.assertEqual(len(calls),4)

    def test_mixed_private_and_routine_chat_still_replies_safely(self):
        self.login()
        prompt = 'My salary changed. I need to tidy the kitchen.'
        calls = []
        def routed(_instructions, payload, schema):
            calls.append((payload, schema))
            if schema is ROUTE_SCHEMA:
                return {'urgent': False, 'tasks': [
                    {'domain': 'planning', 'excerpts': ['My salary changed.']},
                    {'domain': 'home', 'excerpts': [
                        'My salary changed.', 'I need to tidy the kitchen.']},
                ]}
            if schema is RESULT_SCHEMA:
                self.assertEqual(payload['user_reported_excerpts'],
                                 ['I need to tidy the kitchen.'])
                return {'summary': 'A routine task was reported.',
                        'suggestions': ['Tidy the kitchen.'],
                        'missing_context': [], 'question': ''}
            self.assertIs(schema, SCHEMA)
            self.assertEqual(payload['message'], prompt)
            self.assertEqual(payload['specialists_consulted'], ['home'])
            self.assertTrue(payload['private_handoffs_withheld'])
            self.assertNotIn('salary', json.dumps(payload['scoped_specialist_proposals']))
            return {'reply': 'You mentioned a kitchen task; we can discuss the rest privately.'}
        self.app.provider.call = routed
        self.assertEqual(self.chat(prompt)['status'], 202)
        state = self.complete()
        self.assertEqual(state['turns'][0]['status'], 'completed')
        self.assertEqual(len(calls), 3)

    def test_all_private_handoffs_withheld_still_get_coordinator_reply(self):
        self.login()
        prompt = 'My salary changed.'
        calls = []
        def routed(_instructions, payload, schema):
            calls.append((payload, schema))
            if schema is ROUTE_SCHEMA:
                return {'urgent': False, 'tasks': [
                    {'domain': 'planning', 'excerpts': [prompt]}]}
            self.assertIs(schema, SCHEMA)
            self.assertEqual(payload['specialists_consulted'], [])
            self.assertEqual(payload['scoped_specialist_proposals'], [])
            self.assertTrue(payload['private_handoffs_withheld'])
            return {'reply': 'I can discuss your question without sending it to Planning.'}
        self.app.provider.call = routed
        self.assertEqual(self.chat(prompt)['status'], 202)
        state = self.complete()
        self.assertEqual(state['turns'][0]['status'], 'completed')
        self.assertEqual(len(calls), 2)

    def test_router_rejects_ungrounded_or_sensitive_handoffs(self):
        self.login()
        seen=[]
        def bad(_instructions,payload,schema):
            seen.append(schema)
            return {'urgent': False, 'tasks': [
                {'domain':'planning','excerpts':['secret salary']}]}
        self.app.provider.call=bad
        self.assertEqual(self.chat('Please help plan the afternoon')['status'],202)
        state=self.complete()
        self.assertEqual(state['turns'][0]['status'],'failed')
        self.assertEqual(len(seen),1)
        self.assertNotIn('secret salary',state['turns'][0]['error'])

    def test_urgent_router_stops_specialists_and_synthesis(self):
        self.login()
        schemas=[]
        def urgent(_instructions,payload,schema):
            schemas.append(schema)
            return {'urgent':True,'tasks':[]}
        self.app.provider.call=urgent
        self.assertEqual(self.chat('Synthetic immediate danger scenario')['status'],202)
        state=self.complete()
        self.assertEqual(state['turns'][0]['status'],'needs_attention')
        self.assertIn('emergency services',state['turns'][0]['answer'])
        self.assertEqual(schemas,[ROUTE_SCHEMA])

    def test_restart_marks_inflight_without_replay(self):
        self.login();calls=self.install_provider()
        with self.app.db() as db:
            db.execute('INSERT INTO chat_turns VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       ('old','request',time.time(),'source','','running','','','[]',0,'fixture'))
        self.app.pool.shutdown(wait=True)
        self.app=App(self.tmp.name,'https://daily.example',self.login_hash,self.app.provider)
        state=self.request('/daily/api/chat/state')['json']
        self.assertEqual(state['turns'][0]['status'],'interrupted')
        self.assertEqual(calls,[])

    def test_checkin_context_export_expiry_and_no_duplicate_storage(self):
        self.login();calls=self.install_provider()
        now=self.app.clock()
        source='Exact synthetic check-in 🙂'
        result={'message':'Your next steps', 'next_steps':[{'text':'Read one page','owner':'Planning'}],
                'agents':[{'name':'Planning','status':'completed','summary':'A reported goal'}]}
        with self.app.db() as db:
            for rid,created in [('recent',now-10),('expired',now-8*86400)]:
                db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?)',
                    (rid,str(uuid.uuid4()),source,created,'completed',json.dumps(result)))
        exported=self.request('/daily/api/chat/export')['json']
        self.assertEqual(len(exported['turns']),1)
        self.assertEqual(exported['turns'][0]['result'],result)
        self.assertEqual(exported['turns'][0]['kind'],'checkin')
        followup={'prompt':'What should I do first?', 'request_id':str(uuid.uuid4()), 'reply_to':'recent'}
        self.assertEqual(self.request('/daily/api/chat/send',followup)['status'],202)
        self.complete()
        self.assertEqual(self.request('/daily/api/chat/send',followup)['status'],202)
        self.assertEqual(len(calls),2)
        prior=calls[0][1]['bounded_history'][0]
        self.assertEqual(prior['user'],source)
        self.assertIn('Read one page',prior['assistant'])
        self.assertEqual(prior['kind'],'checkin')
        with self.app.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM chat_turns').fetchone()[0],1)
        self.request('/daily/api/clear',{})
        self.assertEqual(self.request('/daily/api/chat/state')['json']['total'],1)

    def test_quick_followup_uses_one_coordinator_call_with_saved_report(self):
        self.login()
        now = self.app.clock()
        with self.app.db() as db:
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?)',
                ('recent-report',str(uuid.uuid4()),'Synthetic plan request',now-5,
                 'completed',json.dumps({
                     'message':'Your next steps',
                     'next_steps':[{'text':'Back up one important note','owner':'Planning'}]
                 })))
        seen = []
        prompt = 'Make your last response more manageable: suggest a smaller first step.'
        def direct(_instructions,payload,schema):
            seen.append((payload,schema))
            self.assertIs(schema, SCHEMA)  # Must not route through specialists.
            self.assertEqual(payload['message'],prompt)
            self.assertTrue(payload['quick_followup'])
            self.assertEqual(payload['specialists_consulted'],[])
            self.assertEqual(payload['scoped_specialist_proposals'],[])
            self.assertIn('Back up one important note',payload['bounded_history'][-1]['assistant'])
            return {'reply':'First, choose one note to back up.'}
        self.app.provider.call = direct
        response = self.request('/daily/api/chat/send',{
            'prompt':prompt,'request_id':str(uuid.uuid4()),
            'reply_to':'recent-report'})
        self.assertEqual(response['status'],202)
        state=self.complete()
        self.assertEqual(state['turns'][-1]['status'],'completed')
        self.assertEqual(state['turns'][-1]['answer'],'First, choose one note to back up.')
        self.assertEqual(len(seen),1)
        self.assertEqual(state['remaining'],19)

    def test_quick_followup_without_anchor_uses_normal_router(self):
        self.login()
        calls = self.install_provider()
        prompt = 'Help me choose one concrete next step from your last response.'
        self.assertEqual(self.chat(prompt)['status'],202)
        state=self.complete()
        self.assertEqual(state['turns'][0]['status'],'completed')
        self.assertEqual(len(calls),2)
        self.assertIs(calls[0][2], ROUTE_SCHEMA)

    def test_non_whitelisted_followup_keeps_emergency_routing(self):
        self.login()
        now=self.app.clock()
        with self.app.db() as db:
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?)',
                ('recent-report',str(uuid.uuid4()),'Synthetic plan request',now-5,
                 'completed',json.dumps({'message':'Your next steps'})))
        seen=[]
        def emergency(_instructions,payload,schema):
            seen.append(schema)
            self.assertIs(schema,ROUTE_SCHEMA)
            return {'urgent':True,'tasks':[]}
        self.app.provider.call=emergency
        response=self.request('/daily/api/chat/send',{
            'prompt':'A new immediate danger is happening.',
            'request_id':str(uuid.uuid4()), 'reply_to':'recent-report'})
        self.assertEqual(response['status'],202)
        state=self.complete()
        self.assertEqual(state['turns'][-1]['status'],'needs_attention')
        self.assertEqual(seen,[ROUTE_SCHEMA])

    def test_quick_reply_generation_failure_is_explained_without_raw_error(self):
        self.login()
        now=self.app.clock()
        with self.app.db() as db:
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?)',
                ('recent-report',str(uuid.uuid4()),'Synthetic plan request',now-5,
                 'completed',json.dumps({'message':'Your next steps'})))
        calls=[]
        def unavailable(_instructions,payload,schema):
            calls.append(schema)
            raise RuntimeError('SECRET PROVIDER DETAILS')
        self.app.provider.call=unavailable
        prompt='Explain the reasoning and uncertainties in your last response.'
        response=self.request('/daily/api/chat/send',{
            'prompt':prompt,'request_id':str(uuid.uuid4()), 'reply_to':'recent-report'})
        self.assertEqual(response['status'],202)
        state=self.complete()
        self.assertEqual(len(calls),1)
        self.assertEqual(state['turns'][-1]['status'],'failed')
        self.assertIn('reply could not be generated',state['turns'][-1]['error'])
        self.assertNotIn('SECRET',json.dumps(state))

    def test_quick_retry_after_failed_turn_does_not_repeat_full_routing(self):
        self.login()
        now=self.app.clock()
        prompt='Make your last response more manageable: suggest a smaller first step.'
        with self.app.db() as db:
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?)',
                ('report',str(uuid.uuid4()),'Synthetic check-in',now-10,
                 'completed',json.dumps({'message':'Suggested step'})))
            db.execute('INSERT INTO chat_turns VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                ('failed',str(uuid.uuid4()),now-5,prompt,'','failed',
                 'Unfinished reply.','','[]',0,'fixture'))
        seen=[]
        def direct(_instructions,payload,schema):
            seen.append(schema)
            self.assertIs(schema,SCHEMA)
            self.assertTrue(payload['quick_followup'])
            return {'reply':'Use one smaller step.'}
        self.app.provider.call=direct
        response=self.request('/daily/api/chat/send',{
            'prompt':prompt,'request_id':str(uuid.uuid4()),'reply_to':'failed'})
        self.assertEqual(response['status'],202)
        state=self.complete()
        self.assertEqual(state['turns'][-1]['status'],'completed')
        self.assertEqual(state['turns'][-1]['answer'],'Use one smaller step.')
        self.assertEqual(len(seen),1)

    def test_ui_quick_prompts_are_server_allowlisted_and_explained(self):
        source = (daily_tests.Path(__file__).resolve().parents[1] /
                  'static' / 'chat.js').read_text()
        for prompt in QUICK_FOLLOWUPS:
            self.assertIn(prompt,source)
        for text in ('Picks one priority','Breaks the advice',
                     'Explains the suggestions','Try replying again'):
            self.assertIn(text,source)

    def test_stale_followup_does_not_spend_or_store(self):
        self.login();calls=self.install_provider()
        response=self.request('/daily/api/chat/send',{'prompt':'Explain this',
            'request_id':str(uuid.uuid4()),'reply_to':'missing'})
        self.assertEqual(response['status'],409)
        self.assertEqual(calls,[])
        self.assertEqual(self.request('/daily/api/chat/state')['json']['remaining'],20)

if __name__ == '__main__':unittest.main()
