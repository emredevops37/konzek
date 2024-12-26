from http.server import SimpleHTTPRequestHandler, HTTPServer
import socket

host = "0.0.0.0"
port = 8080

class CustomHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        hostname = socket.gethostname()  # Container'ın hostname'ini al
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(f"2---Hello, World from {hostname}!".encode())  # Yanıt mesajına hostname ekle

if __name__ == "__main__":
    with HTTPServer((host, port), CustomHandler) as server:
        print(f"Server running on {host}:{port}")
        server.serve_forever()
