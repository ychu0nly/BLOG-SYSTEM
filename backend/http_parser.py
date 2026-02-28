from urllib.parse import parse_qs, urlparse

def parse_http_request(request_text: str) -> dict | None:
    if not request_text.strip():
        return None
    lines = request_text.split('\r\n')
    request_line = lines[0]
    parts = request_line.split(' ')
    if len(parts) < 3:
        return None
    method, path_and_query, _ = parts

    parsed_url = urlparse(path_and_query)
    path = parsed_url.path
    query_params = parse_qs(parsed_url.query)

    headers = {}
    body = ""
    i = 1
    while i < len(lines) and lines[i] != '':
        if ':' in lines[i]:
            key, value = lines[i].split(':', 1)
            headers[key.strip()] = value.strip()
        i += 1
    if i < len(lines):
        body = '\r\n'.join(lines[i+1:])

    post_data = {}
    if method == 'POST' and headers.get('Content-Type') == 'application/x-www-form-urlencoded':
        post_data = parse_qs(body)

    return {
        'method': method,
        'path': path,
        'query': query_params,
        'headers': headers,
        'body': body,
        'post_data': post_data
    }