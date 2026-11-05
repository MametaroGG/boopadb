"""Versioned GET-only trial transport. Import performs no IO.

The caller supplies each credential explicitly. Signed artifact URLs are accepted
only once after this instance receives that exact URL from GitHub's artifact GET.
Contents encoding:none is normalized using verified bytes from its immutable Git
blob, not a raw/main fallback. This provides bytes, never source eligibility.
"""
import base64
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.github.com'
REPOSITORIES = ('MametaroGG/boopadb', 'MametaroGG/booth-vrc-price-tracker')
LIVE = 'https://mametarogg.github.io/boopadb/'
LIVE_FILES = frozenset(('release-manifest.json', 'snapshot-manifest.json', 'index.html', 'item.html'))
MAX_FILE = 8 * 1024 * 1024
MAX_JSON = 16 * 1024 * 1024
MAX_ARTIFACT = 8 * 1024 * 1024
DOWNLOAD_SUFFIXES = ('.blob.core.windows.net', '.actions.githubusercontent.com')

class Refused(ValueError):
    """Contains no URLs, bodies, paths, or credential values."""

def need(condition):
    if not condition:
        raise Refused('Trial GET refused')

def strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result)
            result[key] = value
        return result
    try:
        obj = json.loads(raw, object_pairs_hook=pairs,
                         parse_constant=lambda _: need(False))
        need(type(obj) is dict)
        return obj
    except Exception:
        raise Refused('Trial GET refused') from None

def url_parts(url):
    need(type(url) is str and 0 < len(url) <= 16384)
    need(all(32 < ord(c) < 127 for c in url) and '\\' not in url)
    try:
        p = urllib.parse.urlsplit(url)
        need(p.scheme == 'https' and p.hostname and not p.username and not p.password)
        need(p.port in (None, 443) and p.netloc in (p.hostname, p.hostname + ':443') and not p.fragment)
        need(re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', p.hostname))
        need(all(label and len(label) <= 63 and not label.startswith('-') and
                 not label.endswith('-') for label in p.hostname.split('.')))
        need(p.path.startswith('/') and not p.path.startswith('//') and '//' not in p.path)
        need(not re.search(r'%(?![0-9a-fA-F]{2})', p.path))
        decoded = urllib.parse.unquote(p.path, errors='strict')
        need(all(32 < ord(c) < 127 for c in decoded) and '\\' not in decoded and '%' not in decoded)
        need(decoded.count('/') == p.path.count('/'))
        need(all(s not in ('', '.', '..') for s in decoded[1:].split('/')))
        need(not re.search(r'%(?:0[0-9a-f]|1[0-9a-f]|7f)', p.query, re.I))
        return p
    except Exception:
        raise Refused('Trial GET refused') from None

def classify(url):
    p = url_parts(url)
    if p.hostname == 'api.github.com':
        need(p.netloc == 'api.github.com')
        need(re.fullmatch(r'/[A-Za-z0-9_./%-]+', p.path))
        pairs = urllib.parse.parse_qsl(p.query, keep_blank_values=True, strict_parsing=True)
        need(len(pairs) == len(dict(pairs)))
        validators = {
            'ref': lambda s: re.fullmatch('[a-f0-9]{40}', s),
            'branch': lambda s: re.fullmatch('[A-Za-z0-9_.-]{1,200}', s),
            'status': lambda s: s == 'completed',
            'per_page': lambda s: s.isdigit() and 1 <= int(s) <= 100,
            'page': lambda s: s.isdigit() and 1 <= int(s) <= 1000,
            'name': lambda s: re.fullmatch('[A-Za-z0-9_.-]{1,256}', s),
        }
        need(all(k in validators and validators[k](v) for k, v in pairs))
        for repo in REPOSITORIES:
            prefix = '/repos/' + repo
            if p.path == prefix or p.path.startswith(prefix + '/'):
                artifact = re.fullmatch(re.escape(prefix) + r'/actions/artifacts/[1-9][0-9]*/zip', p.path)
                need(not artifact or not p.query)
                return ('artifact' if artifact else 'api'), repo, MAX_ARTIFACT if artifact else MAX_JSON
        need(False)
    if p.hostname == 'mametarogg.github.io':
        need(p.netloc == p.hostname and not p.query and url.startswith(LIVE) and url[len(LIVE):] in LIVE_FILES)
        return 'live', None, MAX_FILE
    need(any(p.hostname.endswith(suffix) for suffix in DOWNLOAD_SUFFIXES))
    return 'download', None, MAX_ARTIFACT

def request_headers(headers, kind):
    need(type(headers) is dict)
    allowed = {'authorization', 'accept', 'x-github-api-version', 'user-agent', 'cache-control', 'accept-encoding'}
    seen = set()
    for key, value in headers.items():
        need(type(key) is str and type(value) is str and key.lower() in allowed and key.lower() not in seen)
        seen.add(key.lower())
        need(value and all(32 <= ord(c) < 127 for c in value))
        if key.lower() == 'authorization':
            need(kind in ('api', 'artifact') and value.startswith('Bearer ') and
                 0 < len(value[7:]) <= 4096 and all(32 < ord(c) < 127 for c in value[7:]))
        if key.lower() == 'accept-encoding':
            need(value == 'identity')
    need(kind not in ('api', 'artifact') or 'authorization' in seen)
    # Never let content negotiation or ambient compression weaken byte checks.
    return {**headers, 'Accept-Encoding': 'identity'} if 'accept-encoding' not in seen else dict(headers)

def response_headers(items, limit):
    out = {}
    for key, value in items:
        need(type(key) is str and type(value) is str and key.lower() not in out)
        need(all(32 <= ord(c) < 127 for c in key + value))
        out[key.lower()] = value
    if 'content-length' in out:
        need(re.fullmatch(r'[0-9]{1,12}', out['content-length']) and int(out['content-length']) <= limit)
    need(out.get('content-encoding', 'identity').lower() == 'identity')
    if 'transfer-encoding' in out:
        need(out['transfer-encoding'].lower() == 'chunked' and 'content-length' not in out)
    return out

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class GET:
    """Bounded explicit GETs; no retries, proxy/netrc/cookie lookup or auto redirects.

    Inject opener and clock only for tests. The regular controller uses defaults.
    A returned non-200 response remains a failure to the sealed consumer.
    """
    def __init__(self, *, opener=None, clock=time.monotonic, timeout=30, request_seconds=120):
        need(type(timeout) in (int, float) and 0 < timeout <= 30)
        need(type(request_seconds) in (int, float) and timeout <= request_seconds <= 180)
        self.opener = opener if opener is not None else urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect())
        self.clock, self.timeout, self.request_seconds = clock, timeout, request_seconds
        self.pending_download = None
        self.calls = 0

    def _get(self, url, headers):
        kind, repo, limit = classify(url)
        clean = request_headers(headers, kind)
        if kind == 'download':
            need(self.pending_download is not None and url == self.pending_download)
            self.pending_download = None  # One attempt, including errors.
        start = self.clock()
        request = urllib.request.Request(url, headers=clean, method='GET')
        self.calls += 1
        try:
            response = self.opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            need(response.geturl() == url and type(response.status) is int and 100 <= response.status <= 599)
            rh = response_headers(list(response.headers.items()), limit)
            chunks, total = [], 0
            while True:
                need(self.clock() - start <= self.request_seconds)
                chunk = response.read(min(65536, limit - total + 1))
                need(type(chunk) is bytes)
                total += len(chunk)
                need(total <= limit and self.clock() - start <= self.request_seconds)
                if not chunk:
                    break
                chunks.append(chunk)
            body = b''.join(chunks)
            need('content-length' not in rh or int(rh['content-length']) == len(body))
            status = response.status
            if status in range(300, 400):
                need(kind == 'artifact' and status == 302 and self.pending_download is None)
                location = rh.get('location')
                need(classify(location)[0] == 'download')
                self.pending_download = location
            return status, rh, body

    def __call__(self, url, headers):
        try:
            status, rh, body = self._get(url, headers)
            p = url_parts(url)
            # Not a fallback after denied reads. Only an explicitly successful
            # Contents metadata response can authorize its exact Git-blob GET.
            match = re.fullmatch(r'/repos/(MametaroGG/(?:boopadb|booth-vrc-price-tracker))/contents/(.+)', p.path)
            if status != 200 or p.hostname != 'api.github.com' or match is None:
                return status, rh, body
            item = strict(body)
            if item.get('encoding') != 'none':
                return status, rh, body
            query = urllib.parse.parse_qs(p.query)
            need(set(query) == {'ref'} and len(query['ref']) == 1 and re.fullmatch('[a-f0-9]{40}', query['ref'][0]))
            name = urllib.parse.unquote(match[2], errors='strict')
            need(item.get('type') == 'file' and item.get('path') == name and item.get('content') == '')
            sha, size = item.get('sha'), item.get('size')
            need(type(sha) is str and re.fullmatch('[a-f0-9]{40}', sha) and type(size) is int and 0 <= size <= MAX_FILE)
            blob_url = API + '/repos/' + match[1] + '/git/blobs/' + sha
            need(item.get('git_url') == blob_url)
            bs, _, bb = self._get(blob_url, headers)
            need(bs == 200)
            blob = strict(bb)
            need(blob.get('sha') == sha and type(blob.get('size')) is int and blob['size'] == size and blob.get('encoding') == 'base64')
            need(type(blob.get('content')) is str)
            content = ''.join(blob['content'].split())
            need(len(content) == 4 * ((size + 2) // 3))
            raw = base64.b64decode(content, validate=True)
            need(len(raw) == size and hashlib.sha1(b'blob ' + str(size).encode() + b'\0' + raw).hexdigest() == sha)
            normalized = json.dumps({**item, 'encoding': 'base64', 'content': content}, separators=(',', ':'), allow_nan=False).encode()
            need(len(normalized) <= MAX_JSON)
            # Response length now describes normalized bytes, not original wire.
            return status, {**rh, 'content-length': str(len(normalized))}, normalized
        except Exception:
            raise Refused('Trial GET refused') from None
