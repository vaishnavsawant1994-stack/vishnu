const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(require('node:path').join(__dirname,'..','pwa','p202-personal-chat.js'),'utf8');
function check(initial) {
  const tokens = new Set(initial), tasks = [];
  let mutations = 0, refresh = () => {};
  const classList = {
    contains: x => tokens.has(x),
    remove(x) { tokens.delete(x); mutations++; refresh(); },
    toggle(x, force) {
      if(tokens.has(x) === force) return force;
      if(force) tokens.add(x); else tokens.delete(x);
      mutations++; refresh(); return force;
    }
  };
  const document = {
    body: {classList}, readyState:'loading',
    getElementById: () => null, querySelector: () => null,
    addEventListener() {},
    documentElement: {style:{removeProperty(){}}}
  };
  const window = {};
  vm.runInNewContext(source,{document,window,queueMicrotask: f=>tasks.push(f)});
  refresh = window.__vishnuP202A.refresh;
  refresh();
  let iterations = 0;
  while(tasks.length && iterations < 12) { iterations++; tasks.shift()(); }
  assert.equal(tasks.length,0,'Inactive chat must settle rather than starve browser rendering');
  assert(!tokens.has('p202-keyboard-visible'));
  assert(!tokens.has('p202-personal-chat'));
  console.log('PASS: inactive chat settles after',iterations,'microtasks;',mutations,'class changes');
}
check([]);
check(['p202-personal-chat','p202-keyboard-visible']);
