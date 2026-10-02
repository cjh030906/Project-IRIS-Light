from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
handler = partial(SimpleHTTPRequestHandler, directory=str(Path(__file__).resolve().parent))
print('WEB-READY-8877', flush=True)
HTTPServer(('127.0.0.1', 8877), handler).serve_forever()
