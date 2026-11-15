import json
import re
import socket
import threading
from urllib.error import HTTPError,URLError
import pytest
from urllib.request import Request,urlopen

from omr_check import review
from omr_check.catalog import Catalog


def test_review_requires_token_and_preserves_revision_and_verification(tmp_path,monkeypatch):
    file=tmp_path/'keys.json'
    exam={'id':'test','name':'Test','collection':'Fixture','status':'draft','revision':0,'answers':{},'issues':['Unverified'],'sources':[]}
    file.write_text(json.dumps({'schema_version':1,'exams':[exam]}))
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    real=review.ThreadingHTTPServer; captured={}; ready=threading.Event()
    def server_factory(address,handler):
        server=real(address,handler);captured['server']=server;ready.set();return server
    monkeypatch.setattr(review,'ThreadingHTTPServer',server_factory)
    thread=threading.Thread(target=review.serve,args=(file,port),daemon=True);thread.start();assert ready.wait(5)
    base=f'http://127.0.0.1:{port}'
    def request(path,body=None,token=None):
        headers={'Content-Type':'application/json'}
        if token:headers['X-Review-Token']=token
        data=json.dumps(body).encode() if body is not None else None
        try:
            with urlopen(Request(base+path,data=data,headers=headers),timeout=5) as response:return response.status,response.read().decode()
        except HTTPError as exc:return exc.code,exc.read().decode()
        except URLError as exc:
            if isinstance(exc.reason,PermissionError) and getattr(exc.reason,"winerror",None)==10013:
                pytest.skip("This execution sandbox blocks loopback sockets (WinError 10013)")
            raise
    try:
        status,html=request('/');assert status==200
        token=json.loads(re.search(r'const TOKEN=("[^";]+")',html).group(1))
        assert request('/api/keys')[0]==403
        assert request('/api/keys',token=token)[0]==200
        assert request('/api/save',{'id':'test','answers':{'1':['A']},'revision':0,'verify':False},token)[0]==200
        assert request('/api/save',{'id':'test','answers':{'1':['A']},'revision':0,'verify':False},token)[0]==409
        assert request('/api/save',{'id':'test','answers':{'1':['A']},'revision':1,'verify':True,'reviewer':'Fixture'},token)[0]==400
        answers={str(i):['A'] for i in range(1,101)}
        assert request('/api/save',{'id':'test','answers':answers,'revision':1,'verify':True,'reviewer':'Fixture'},token)[0]==200
        assert Catalog(file).exams['test'].verified
        assert file.with_name('keys.before-review.json').exists()
    finally:
        captured['server'].shutdown();captured['server'].server_close();thread.join(3)
