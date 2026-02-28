def make_response(status: str, content_type: str, body: str) -> str:
    return (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: {content_type}; charset=utf-8\r\n"
        "Connection: close\r\n"
        "\r\n"
        f"{body}"
    )

def redirect(location: str) -> str:
    return (
        "HTTP/1.1 302 Found\r\n"
        f"Location: {location}\r\n"
        "\r\n"
    )

def add_cookie_to_response(response: str, cookie_header: str) -> str:
    # 在第一个 \r\n\r\n 前插入 Set-Cookie
    parts = response.split('\r\n\r\n', 1)
    if len(parts) == 2:
        return parts[0] + f'\r\n{cookie_header}' + '\r\n\r\n' + parts[1]
    return response