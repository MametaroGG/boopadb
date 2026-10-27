"""Local browser regression: HTTP/SW staleness, reload migration, offline cache, user data."""
import threading, json, time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
state={'version':1,'worker':'old','mtime':'Wed, 01 Jan 2020 00:00:00 GMT','fail':False}
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def do_HEAD(self): self.respond(True)
 def do_GET(self): self.respond(False)
 def respond(self,head):
  path=self.path.split('?')[0]
  if path.endswith('sw.js'):
   content=(ROOT/'tests/fixtures/sw-v1.js' if state['worker']=='old' else ROOT/'sw.js').read_bytes();ctype='text/javascript'
  elif path.endswith('site-update.js'):content=(ROOT/'site-update.js').read_bytes();ctype='text/javascript'
  elif path.endswith('asset.txt'):content=f"asset-v{state['version']}".encode();ctype='text/plain'
  elif path.endswith('.json'):content=b'{"test":true}';ctype='application/json'
  else:
   content=('<!doctype html><title>Test</title><input id="edit"><p id="version">'+str(state['version'])+'</p>' + ('<script>navigator.serviceWorker.register("sw.js")</script>' if state['worker']=='old' else '<script src="site-update.js" defer></script>')).encode();ctype='text/html'
  self.send_response(503 if state['fail'] else 200);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(content)));self.send_header('Cache-Control','max-age=600');self.send_header('Last-Modified',state['mtime']);self.end_headers()
  if not head:self.wfile.write(content)
srv=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=srv.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{srv.server_port}/boopadb/'
results=[]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 context=browser.new_context();page=context.new_page();page.goto(base);page.evaluate('navigator.serviceWorker.ready');page.reload();page.evaluate("localStorage.setItem('boopadb_bm','keep'); caches.open('unrelated-app-cache')")
 assert page.evaluate("fetch('asset.txt').then(r=>r.text())")=='asset-v1'
 time.sleep(.3);state['version']=2
 assert page.evaluate("fetch('asset.txt').then(r=>r.text())")=='asset-v1';results.append('Original worker reproduces stale asset with HTTP max-age=600')
 state['worker']='new'
 page.evaluate("navigator.serviceWorker.getRegistration().then(r=>r.update())")
 page.wait_for_function("navigator.serviceWorker.controller && navigator.serviceWorker.controller.state === 'activated'")
 time.sleep(1)
 assert page.evaluate("fetch('asset.txt').then(r=>r.text())")=='asset-v2';results.append('Upgraded worker returns fresh asset on first request')
 keys=page.evaluate('caches.keys()');assert 'boopadb-shell-v1' not in keys and 'unrelated-app-cache' in keys;results.append('Migration deletes only BoopaDB shell cache')
 page.goto(base+'index.html?filter=kept#anchor');page.wait_for_function("document.querySelector('#version').textContent==='2'")
 state['version']=3;state['mtime']='Fri, 01 Jan 2021 00:00:00 GMT'
 # Bypass the 30s throttle without waiting by advancing Date.now, not page lifecycle state.
 page.evaluate("{const old=Date.now; Date.now=()=>old()+31000; document.activeElement.blur(); dispatchEvent(new Event('pageshow'));}")
 page.wait_for_function("document.querySelector('#version').textContent==='3'")
 assert 'filter=kept' in page.url and page.url.endswith('#anchor') and '__boopadb_update' not in page.url
 assert page.evaluate("localStorage.getItem('boopadb_bm')")=='keep';results.append('Resume updates HTML while preserving query/hash and bookmarks')
 page.locator('#edit').fill('unfinished');state['version']=4;state['mtime']='Sat, 01 Jan 2022 00:00:00 GMT'
 page.evaluate("{const old=Date.now;Date.now=()=>old()+31000;dispatchEvent(new Event('pageshow'));}");time.sleep(.5)
 assert page.locator('#edit').input_value()=='unfinished' and page.locator('#version').inner_text()=='3';results.append('Focused input blocks disruptive reload')
 # Avoid update probe while checking offline fallback.
 context.set_offline(True);page.goto(base+'index.html?filter=kept#anchor');assert page.locator('#version').inner_text()=='3';results.append('Offline navigation keeps last good HTML')
 context.set_offline(False);page.evaluate("fetch('sample.json').then(r=>r.json())");assert not page.evaluate("caches.open('boopadb-shell-v2').then(c=>c.keys()).then(rs=>rs.some(r=>r.url.includes('sample.json')))");results.append('JSON is not stored in shell cache')
 page.close();context.close();browser.close()
 try:
  w=p.webkit.launch(headless=True);w.close();results.append('WebKit available')
 except Exception as e:results.append('WebKit unavailable: '+str(e).splitlines()[0])
srv.shutdown();print(json.dumps(results,indent=2));(ROOT/'tests/results.json').write_text(json.dumps(results,indent=2))
