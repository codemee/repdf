"""Connect the packaged worker before loading PDF and image libraries."""
import json
import socket


def serve_socket(port, token):
    with socket.create_connection(('127.0.0.1', port), timeout=30) as connection:
        connection.settimeout(None)
        with connection.makefile('r', encoding='utf-8') as reader, connection.makefile('w', encoding='utf-8') as writer:
            print(json.dumps({'type': 'starting', 'token': token}), file=writer, flush=True)
            try:
                from repdf.render_worker import serve
            except Exception as error:
                print(json.dumps({'type': 'startup_error', 'token': token,
                                  'message': f'{type(error).__name__}: {error}'}), file=writer, flush=True)
                return 1
            return serve(reader, writer, token)
