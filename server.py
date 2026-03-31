import http.server
import socketserver
import subprocess
import json
import webbrowser

PORT = 8080

class Handler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        if self.path.startswith('/api/run'):
            self._run_scripts()
        else:
            super().do_GET()

    def _run_scripts(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        try:
            print('\n  [Refresh] Scraping data...')
            subprocess.run(['python', 'scraper.py'], check=True, capture_output=True)
            print('  [Refresh] Scoring...')
            subprocess.run(['python', 'scorer.py'],  check=True, capture_output=True)
            print('  [Refresh] Selesai.\n')
            self.wfile.write(json.dumps({'status': 'ok'}).encode())
        except subprocess.CalledProcessError as e:
            self.wfile.write(json.dumps({'status': 'error', 'msg': str(e)}).encode())

    def log_message(self, format, *args):
        if 'favicon' not in str(args):
            print(f'  {args[0]} {args[1]}')

print('╔══════════════════════════════════════╗')
print(f'║  DiviWatch  —  localhost:{PORT}        ║')
print('║  Ctrl+C untuk stop                   ║')
print('╚══════════════════════════════════════╝')

webbrowser.open(f'http://localhost:{PORT}/dashboard.html')

with socketserver.TCPServer(('', PORT), Handler) as httpd:
    httpd.serve_forever()
