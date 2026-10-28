'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {questions,buildPrompt} = require('../static/morning.js');

test('three bounded conversational morning questions', () => {
  assert.equal(questions.length, 3);
  assert.deepEqual(questions.map(q=>q.label),[
    'Sleep and physical comfort','Energy and mood','Priorities and commitments'
  ]);
  assert.ok(questions.every(q=>q.question.endsWith('?')));
});

test('blank optional answers never produce a plan or a fabricated report', () => {
  assert.equal(buildPrompt(['','','']), '');
  assert.throws(()=>buildPrompt(['missing one answer']));
});

test('draft preserves chosen answers and explicitly protects obligations and focus', () => {
  const draft=buildPrompt([
    'Sleep was okay.',
    'Energy is low; I have a creative idea.',
    'One urgent email, meals and hygiene.'
  ]);
  for(const part of ['Sleep was okay.','Energy is low','urgent email','deadlines',
                     'hygiene','uninterrupted focus block','Do not invent appointments']) {
    assert.ok(draft.includes(part),part);
  }
  assert.ok(draft.length<4000);
});

test('answers are bounded to keep the existing server check-in limit', () => {
  const draft=buildPrompt(['x'.repeat(1200),'y'.repeat(1200),'z'.repeat(1200)]);
  assert.ok(draft.length<=4000);
  assert.ok(draft.includes('x'.repeat(900)));
  assert.ok(!draft.includes('x'.repeat(901)));
});

test('voice is explicit and never posts or persists on its own', () => {
  const js=fs.readFileSync(path.join(__dirname,'../static/morning.js'),'utf8');
  const html=fs.readFileSync(path.join(__dirname,'../static/index.html'),'utf8');
  const app=fs.readFileSync(path.join(__dirname,'../static/app.js'),'utf8');
  assert.match(js,/dictate.addEventListener\('click'/);
  assert.match(js,/read.addEventListener\('click'/);
  assert.match(js,/readPlan.addEventListener\('click'/);
  assert.doesNotMatch(js,/localStorage|sessionStorage|indexedDB|fetch\(|sendBeacon|MediaRecorder/);
  assert.match(html,/id="morning-open"/);
  assert.match(html,/id="morning-answer"/);
  assert.match(html,/id="read-plan"/);
  assert.match(html,/Some browsers send microphone audio/);
  assert.match(js,/No automatic submission/);
  assert.match(app,/daily:locked/);
});
