# -*- coding: utf-8 -*-
"""HTML → DOM（HTML5 常见省略闭合处理与受限脚本执行）"""

import re
from html.parser import HTMLParser
from dom import DomNode
from bigjs import BigJS

VOID_TAGS = {'meta', 'link', 'img', 'br', 'hr', 'input', 'source', 'area', 'base', 'col', 'embed', 'param', 'track', 'wbr'}
PRESERVE_WS_TAGS = {'pre', 'textarea', 'code'}

BLOCK_START_TAGS = {
    'address', 'article', 'aside', 'blockquote', 'div', 'dl', 'fieldset',
    'figcaption', 'figure', 'footer', 'form', 'h1', 'h2', 'h3', 'h4',
    'h5', 'h6', 'header', 'hr', 'main', 'nav', 'ol', 'p', 'pre', 'section',
    'table', 'ul',
}


def _is_javascript(attrs):
    script_type = (attrs.get('type') or '').strip().lower()
    if not script_type:
        return True
    return script_type in (
        'text/javascript', 'application/javascript', 'text/ecmascript',
        'application/ecmascript',
    )

class DOMBuilder(HTMLParser):
    def __init__(self, callbacks=None, current_url=''):
        super().__init__(convert_charrefs=True)
        self.root = DomNode('root')
        self.stack = [self.root]
        self.css_chunks = []
        self.external_css_urls = []
        self.in_style = False
        self.in_script = False
        self.in_title = False
        self.in_pre = 0
        self.title = ''
        self.base_href = ''
        self.script_buf = []
        self.script_executable = True
        self.callbacks = callbacks or {}
        self.current_url = current_url
        
        self.js = BigJS(document_root=self.root, output_callback=self._write_document)
        self.scripts = []
        self.script_count = 0

    def _write_document(self, content):
        fragment = DOMBuilder(current_url=self.current_url)
        fragment.feed(str(content))
        for node in fragment.root.children:
            self.root.append(node)

    def _preserving_ws(self):
        if self.in_pre: return True
        for node in reversed(self.stack):
            if node.tag in PRESERVE_WS_TAGS: return True
            if node.tag in ('div', 'p', 'body', 'section', 'article'): return False
        return False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in BLOCK_START_TAGS:
            self._close_open('p')
        if tag == 'li':
            self._close_open('li')
        elif tag in ('dt', 'dd'):
            self._close_any(('dt', 'dd'))
        elif tag == 'option':
            self._close_open('option')
        elif tag in ('td', 'th'):
            self._close_any(('td', 'th'))
        elif tag == 'tr':
            self._close_any(('td', 'th'))
            self._close_open('tr')
        elif tag in ('thead', 'tbody', 'tfoot'):
            self._close_any(('td', 'th', 'tr'))
            self._close_any(('thead', 'tbody', 'tfoot'))
        elif tag == 'a':
            self._close_open('a')
        if tag == 'style': self.in_style = True; return
        if tag == 'script': 
            self.in_script = True
            self.script_buf = []
            self.script_executable = _is_javascript(a) and not a.get('src')
            return
        if tag == 'title': self.in_title = True; return
        if tag == 'base':
            if 'href' in a: self.base_href = a['href']
            return
        if tag == 'link' and 'stylesheet' in (a.get('rel') or '').lower() and a.get('href'):
            self.external_css_urls.append(a['href']); return
        if tag == 'pre': self.in_pre += 1

        node = DomNode(tag, a)
        self.stack[-1].append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def _close_open(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def _close_any(self, tags):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag in tags:
                del self.stack[i:]
                return

    def handle_endtag(self, tag):
        if tag == 'style': self.in_style = False; return
        if tag == 'script':
            if self.in_script:
                code = ''.join(self.script_buf).strip()
                if self.script_executable and code and len(code) < 102400:
                    self.scripts.append(code)
                    self.script_count += 1
            self.in_script = False; self.script_buf = []; return
        if tag == 'title': self.in_title = False; return
        if tag == 'pre': self.in_pre = max(0, self.in_pre - 1)
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]; break

    def handle_data(self, data):
        if self.in_style: self.css_chunks.append(data); return
        if self.in_script: self.script_buf.append(data); return
        if self.in_title: self.title += data; return
        if not data: return
        if self._preserving_ws():
            text = data.replace('\xa0', ' ')
        else:
            text = re.sub(r'[\t\n\r ]+', ' ', data.replace('\xa0', '\u00A0'))
        if not text: return
        self.stack[-1].append(DomNode(text=text))

    def run_scripts(self):
        for code in self.scripts[:20]:
            try: self.js.run(code)
            except Exception: pass