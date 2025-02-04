import http.server
import socketserver
import threading


class Handler(http.server.SimpleHTTPRequestHandler):
    def send_error(self, code, message=None):
        """Override to match GitHub's error format"""
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if code == 404:
            self.wfile.write(b"404 Client Error: Not Found")


def run_server(port=8000):
    """Run HTTP server in a daemon thread.

    Args:
        port: Port number to listen on (default: 8000)
    """
    httpd = socketserver.TCPServer(("", port), Handler)
    server_thread = threading.Thread(target=httpd.serve_forever)
    server_thread.daemon = True
    server_thread.start()


if __name__ == '__main__':
    run_server()
    # Keep the script running
    import time
    while True:
        time.sleep(1)
