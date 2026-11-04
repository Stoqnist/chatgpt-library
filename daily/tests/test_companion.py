"""Private conversation acceptance tests; no live model or personal data."""
import json
import os
import threading
import time
import unittest
import uuid
import test_daily as daily_tests
from app import App
from companion import SCHEMA


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
            self.assertIs(schema, SCHEMA)
            return {'reply': reply}
        self.app.provider.call=call
        return calls

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
        background='Synthetic preference: concise answers.'
        self.assertEqual(self.request('/daily/api/chat/context',{'text':background,'revision':0})['status'],200)
        text='  '+('🙂български\n'*600)+'tail  '
        rid=str(uuid.uuid4());first=self.chat(text,rid);self.assertEqual(first['status'],202)
        state=self.complete()
        self.assertEqual(state['turns'][0]['prompt'],text)
        self.assertEqual(state['turns'][0]['status'],'completed')
        self.assertEqual(calls[0][1]['owner_written_background'],background)
        self.assertEqual(self.chat(text,rid)['json']['id'],first['json']['id'])
        self.assertEqual(self.chat(text+'changed',rid)['status'],409)
        self.assertEqual(len(calls),1)
        self.app=App(self.tmp.name,'https://daily.example',self.login_hash,self.app.provider)
        self.assertEqual(self.chat('What did I say?')['status'],202)
        state=self.complete()
        self.assertEqual(len(state['turns']),2)
        self.assertEqual(calls[1][1]['history'][0]['user'],text)
        self.assertEqual(calls[1][1]['history'][0]['assistant'],'A synthetic reply.')
        self.assertNotIn('calendar_availability',calls[1][1])
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

    def test_shared_concurrency_and_usage_guard(self):
        self.login();event=threading.Event()
        def wait(*args):event.wait(4);return {'reply':'done'}
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
        self.assertEqual(self.request('/daily/api/chat/context',{'text':'sk-proj-'+('z'*40),'revision':0})['status'],400)
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
        self.assertEqual(len(calls[0][1]['history']),2)
        exported=self.request('/daily/api/chat/export')
        self.assertIn('attachment',exported['headers']['Content-Disposition'])
        self.assertEqual(len(exported['json']['turns']),6)
        self.assertEqual(self.request('/daily/api/chat/clear',{})['status'],200)
        self.assertEqual(self.request('/daily/api/chat/export')['json']['turns'],[])
        self.assertEqual(self.request('/daily/api/chat/state')['json']['remaining'],19)

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

if __name__ == '__main__':unittest.main()
