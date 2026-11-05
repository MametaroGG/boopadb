"""Explicit credential-free source transport. Never used by local verification.

No credentials, cookies, proxy discovery, .netrc or redirects; no retry/fallback.
Source authority still requires stream_source's complete saved Git-root binding.
"""
import contextlib, re, ssl, time, urllib.request

class RefuseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Source redirects are forbidden')

class BoundedResponse:
    def __init__(self,response,url,maximum_bytes,total_seconds,clock):
        self.response=response;self.url=url;self.maximum=maximum_bytes;self.clock=clock
        self.deadline=clock()+total_seconds;self.consumed=0;self.complete=False
        if response.status!=200 or response.geturl()!=url:raise ValueError('Unexpected source HTTP response/origin')
        headers=response.headers
        names=[name.casefold() for name,value in headers.items()]
        if len(names)!=len(set(names)):raise ValueError('Duplicate source response headers')
        if headers.get('Content-Encoding','identity').lower() not in ('','identity'):raise ValueError('Unexpected HTTP content encoding')
        length=headers.get('Content-Length')
        if length is not None and (not re.fullmatch('[0-9]+',length) or int(length)>maximum_bytes):raise ValueError('Invalid/oversized declared source body')
        self.length=None if length is None else int(length)
        self.media_type=headers.get('Content-Type','').split(';',1)[0].strip().lower()
        if self.media_type not in ('application/gzip','application/x-gzip','application/octet-stream','application/x-tar'):raise ValueError('Unexpected source media type')
    def read(self,size):
        if type(size) is not int or size<1 or size>1024*1024:raise ValueError('Bounded positive read required')
        if self.clock()>self.deadline:raise TimeoutError('Source total deadline exceeded')
        raw=self.response.read(min(size,self.maximum-self.consumed+1))
        if not isinstance(raw,bytes):raise ValueError('Nonbyte source response')
        self.consumed+=len(raw)
        if self.consumed>self.maximum:raise ValueError('Source body limit exceeded')
        if self.length is not None and self.consumed>self.length:raise ValueError('Source exceeds declared length')
        if self.clock()>self.deadline:raise TimeoutError('Source total deadline exceeded')
        if not raw:
            if self.length is not None and self.length!=self.consumed:raise ValueError('Truncated declared source body')
            self.complete=True
        return raw

@contextlib.contextmanager
def open_source(binding, maximum_bytes, timeout_seconds=30, total_seconds=900, *, opener=None, clock=time.monotonic):
    """Caller must first authenticate binding through the unchanged resolver.

    Inject opener only for local tests/trusted environment wiring. This never
    silently selects credentials or another transport after a denied request.
    """
    binding.validate()
    if type(maximum_bytes) is not int or maximum_bytes<1:raise ValueError('Explicit source byte cap required')
    if type(timeout_seconds) not in (int,float) or not 0<timeout_seconds<=60 or type(total_seconds) not in (int,float) or not timeout_seconds<=total_seconds<=3600:raise ValueError('Invalid transport deadlines')
    url=binding.archive_url
    if not re.fullmatch(r'https://codeload\.github\.com/MametaroGG/booth-vrc-price-tracker/tar\.gz/[0-9a-f]{40}',url):raise ValueError('Unexpected source URL')
    request=urllib.request.Request(url,method='GET',headers={'Accept':'application/gzip, application/octet-stream','Accept-Encoding':'identity','User-Agent':'Boopadb-source-integrity-v1'})
    # This opener intentionally has no cookie processor, authentication handler,
    # environment proxy support, HTTP downgrade or permissive TLS context.
    if opener is None:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),RefuseRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    started=clock();response=opener.open(request,timeout=timeout_seconds)
    try:
        bounded=BoundedResponse(response,url,maximum_bytes,total_seconds,clock)
        bounded.deadline=started+total_seconds
        yield bounded
    finally:response.close()
