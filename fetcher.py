# -*- coding: utf-8 -*-
"""网络抓取 + 本地文件支持 + gzip/deflate 解压 + cookie 持久化"""

import urllib.request
import urllib.parse
import urllib.error
import http.cookiejar
import re
import gzip
import zlib
import os
import mimetypes

HEADERS_BASE = {
    'User-Agent': ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'),
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'close',
}

_COOKIE_JAR = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(_COOKIE_JAR)
)

def _decode_response(raw, headers):
    enc = (headers.get('Content-Encoding') or '').lower()
    if 'gzip' in enc:
        try: raw = gzip.decompress(raw)
        except: pass
    elif 'deflate' in enc:
        try: raw = zlib.decompress(raw)
        except zlib.error:
            try: raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            except zlib.error: pass
    elif raw[:2] == b'\x1f\x8b':
        try: raw = gzip.decompress(raw)
        except: pass

    charset = headers.get_content_charset()
    if not charset:
        m = re.search(r'charset=([\w-]+)', headers.get('Content-Type', ''))
        charset = m.group(1) if m else 'utf-8'
    return raw.decode(charset, errors='replace')


def fetch(url, limit=3_000_000, timeout=15):
    # 【新增】：支持本地 HTML 文件
    if url.startswith('file://'):
        try:
            path = urllib.request.url2pathname(urllib.parse.urlparse(url).path)
            with open(path, 'rb') as f:
                raw = f.read(limit)
            # 尝试从 HTML 头部嗅探 charset
            head = raw[:2000].decode('ascii', errors='ignore').lower()
            m = re.search(r'charset=["\']?([\w-]+)', head)
            charset = m.group(1) if m else 'utf-8'
            return raw.decode(charset, errors='replace')
        except Exception as e:
            raise RuntimeError(f'本地文件读取失败: {e}')

    try:
        headers = dict(HEADERS_BASE)
        headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme and parsed.hostname:
            headers['Referer'] = f'{parsed.scheme}://{parsed.hostname}/'

        req = urllib.request.Request(url, headers=headers)
        with _OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read(limit)
            return _decode_response(raw, resp.headers)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'HTTP {e.code} {e.reason}')
    except Exception as e:
        raise RuntimeError(f'{type(e).__name__}: {e}')


def fetch_css(url, limit=1_000_000, timeout=5):
    if url.startswith('file://'):
        try:
            path = urllib.request.url2pathname(urllib.parse.urlparse(url).path)
            with open(path, 'rb') as f:
                raw = f.read(limit)
            return raw.decode('utf-8', errors='replace')
        except Exception:
            return ''

    try:
        headers = dict(HEADERS_BASE)
        headers['Accept'] = 'text/css,*/*;q=0.8'
        req = urllib.request.Request(url, headers=headers)
        with _OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read(limit)
            return _decode_response(raw, resp.headers)
    except Exception:
        return ''


def fetch_image(url, timeout=10):
    if url.startswith('file://'):
        try:
            path = urllib.request.url2pathname(urllib.parse.urlparse(url).path)
            with open(path, 'rb') as f:
                return f.read(5_000_000)
        except Exception:
            return None

    try:
        headers = dict(HEADERS_BASE)
        headers['Accept'] = 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
        req = urllib.request.Request(url, headers=headers)
        with _OPENER.open(req, timeout=timeout) as resp:
            return resp.read(5_000_000)
    except Exception:
        return None