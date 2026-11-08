# -*- coding: utf-8 -*-
"""MXY 浏览器主界面"""

import tkinter as tk
from tkinter import ttk
import urllib.parse
import threading
import base64
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed

from font_manager import FontManager
from html_parser import DOMBuilder
from css_engine import get_style_rules
from box_tree import build_box_tree, InputBox, ReplacedBox
from layout import Layout
from paint import Painter
from fetcher import fetch, fetch_css, fetch_image
from pages import build_about_html, build_js_test_html, build_css_test_html

CLICK_DISTANCE_SQ = 25
DRAG_START_SQ = 25
MAX_EXTERNAL_CSS = 5
MAX_CSS_BYTES = 2_000_000
CSS_TOTAL_TIMEOUT = 3

class App:
    def __init__(self, root):
        self.root = root
        root.title('MXY 浏览器')
        root.geometry('1000x720')

        bar = ttk.Frame(root, padding=4)
        bar.pack(fill='x')
        ttk.Button(bar, text='←', width=3, command=self.go_back).pack(side='left')
        ttk.Button(bar, text='→', width=3, command=self.go_forward).pack(side='left')
        ttk.Button(bar, text='刷新', width=6, command=self.reload).pack(side='left')
        self.entry = ttk.Entry(bar)
        self.entry.pack(side='left', fill='x', expand=True, padx=4)
        self.entry.insert(0, 'mxy:')
        self.entry.bind('<Return>', lambda e: self.go(self.entry.get()))
        ttk.Button(bar, text='打开', command=lambda: self.go(self.entry.get())).pack(side='left')

        body = ttk.Frame(root)
        body.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(body, bg='white', highlightthickness=0)
        vsb = ttk.Scrollbar(body, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')

        self.status = tk.StringVar(value='就绪')
        ttk.Label(root, textvariable=self.status, anchor='w', relief='sunken', padding=(6, 2)).pack(fill='x')

        self.font_manager = FontManager()
        self.layout_engine = Layout(self.font_manager)
        self.painter = Painter(self.canvas, self.font_manager)
        self.css_executor = ThreadPoolExecutor(max_workers=5)
        self.img_executor = ThreadPoolExecutor(max_workers=8)

        self.root_box = None
        self.current_base_url = ''
        self.current_title = ''
        
        self.history = []
        self.history_pos = -1
        self.current_url = ''
        
        self._resize_job = None
        self._base_status = '就绪'
        self._hover_url = None
        self._pending_navigate = None
        self._image_refs = []

        self.press_pos = None
        self.press_canvas = None
        self._temp_rect = None
        self._dragging = False

        self._active_entry = None
        self._active_input = None

        self.canvas.bind('<ButtonPress-1>', self._on_button_press)
        self.canvas.bind('<B1-Motion>', self._on_button_motion)
        self.canvas.bind('<ButtonRelease-1>', self._on_button_release)
        self.canvas.bind('<Motion>', self._on_motion)
        self.canvas.bind('<Configure>', self._on_canvas_configure)
        self.canvas.bind('<MouseWheel>', self._on_wheel)
        self.canvas.bind('<Button-4>', self._on_wheel)
        self.canvas.bind('<Button-5>', self._on_wheel)

        self.root.bind('<Control-c>', self._on_copy)
        self.root.bind('<Control-C>', self._on_copy)
        self.root.bind('<Escape>', self._clear_selection)

        self.root.after(100, lambda: self.go('mxy:'))

    def go(self, url, from_history=False):
        if not url: return
        
        if not from_history and self.current_url and self.history_pos >= 0:
            self.history[self.history_pos]['pos'] = self.canvas.yview()[0]

        url = url.strip()
        
        if not url.startswith(('mxy:', 'data:', 'mailto:', 'file:', 'http://', 'https://')):
            if '.' in url and ' ' not in url and not url.startswith('.') and not url.endswith('.'):
                url = 'https://' + url
            else:
                url = 'https://cn.bing.com/search?q=' + urllib.parse.quote(url)
                
        if self.current_base_url and not url.startswith(('mxy:', 'data:', 'mailto:', 'javascript:')):
            if not url.startswith(('http://', 'https://', 'file:')):
                url = urllib.parse.urljoin(self.current_base_url, url)
        
        self.current_url = url
        self._pending_navigate = None
        self.entry.delete(0, 'end')
        self.entry.insert(0, url)
        
        if not from_history:
            if self.history_pos < len(self.history) - 1:
                self.history = self.history[:self.history_pos + 1]
            if not self.history or self.history[-1]['url'] != url:
                self.history.append({'url': url, 'pos': 0.0})
            self.history_pos = len(self.history) - 1
            
        if url.startswith('mxy:'):
            self._set_status(f'加载中… {url}')
        else:
            self._set_status(f'加载中…（最长 15 秒） {url}')
        self.painter.selection = None
        threading.Thread(target=self._load, args=(url,), daemon=True).start()

    def _schedule_navigate(self, url):
        if not url or self._pending_navigate: return
        self._pending_navigate = url
        self.root.after(0, self._do_pending_navigate)

    def _do_pending_navigate(self):
        target = self._pending_navigate
        self._pending_navigate = None
        if target: self.go(target)

    def _load(self, url):
        try:
            if url == 'mxy:js': html = build_js_test_html()
            elif url == 'mxy:css': html = build_css_test_html()
            elif url.startswith('mxy:'): html = build_about_html()
            else: html = fetch(url)

            parser = DOMBuilder(
                callbacks={
                    'navigate': lambda u: self._schedule_navigate(self._abs_from(u, url)),
                    'set_title': lambda t: self.root.after(0, lambda: self._set_title(t)),
                    'refresh': lambda u: self._schedule_navigate(self._abs_from(u, url)),
                },
                current_url=url,
            )
            parser.feed(html)
            
            # 执行 BigJS 过滤后的脚本
            parser.run_scripts()

            base = parser.base_href or url
            if base != url: base = urllib.parse.urljoin(url, base)

            css_parts = list(parser.css_chunks)
            external_count = 0
            if parser.external_css_urls:
                external = self._fetch_external_css(parser.external_css_urls, base)
                external_count = len(external)
                css_parts.extend(external)

            rules = get_style_rules('\n'.join(css_parts))
            self.root.after(0, self._render, parser, rules, base, external_count)
        except Exception as e:
            self.root.after(0, self._err, url, str(e))

    def _fetch_external_css(self, urls, base):
        if not urls: return []
        deduped = []; seen = set()
        for u in urls:
            abs_u = self._abs_from(u, base)
            if abs_u in seen: continue
            seen.add(abs_u); deduped.append(abs_u)
            if len(deduped) >= MAX_EXTERNAL_CSS: break

        futures = {self.css_executor.submit(fetch_css, u): u for u in deduped}
        results = []; total = 0
        try:
            for fut in as_completed(futures, timeout=CSS_TOTAL_TIMEOUT):
                try: css = fut.result(timeout=0)
                except: css = ''
                if not css: continue
                if total + len(css) > MAX_CSS_BYTES:
                    css = css[:max(0, MAX_CSS_BYTES - total)]
                total += len(css); results.append(css)
                if total >= MAX_CSS_BYTES: break
        except: pass
        for fut in futures:
            if not fut.done(): fut.cancel()
        return results

    def _abs_from(self, href, base):
        if not href: return base
        href = href.strip()
        if '://' in href or href.startswith(('mxy:', 'data:', 'mailto:', 'javascript:')): return href
        if href.startswith('//'):
            scheme = urllib.parse.urlparse(base).scheme or 'https'
            return f'{scheme}:{href}'
        return urllib.parse.urljoin(base, href)

    def _set_title(self, t):
        t = t.strip()
        if t:
            self.current_title = t
            self.root.title(f'{t} — MXY 浏览器')

    def _render(self, parser, rules, base_url, external_count=0):
        try:
            self.current_base_url = base_url
            self.current_title = parser.title.strip() or 'MXY 浏览器'
            self.root.title(f'{self.current_title} — MXY 浏览器')

            self.root_box = build_box_tree(parser.root, rules)
            self._image_refs = []

            width = self.canvas.winfo_width()
            if width < 100: width = max(600, self.root.winfo_width() - 40)

            self.layout_engine.layout(self.root_box, width)
            self.painter.selection = None
            
            self.canvas.configure(scrollregion=(0, 0, width, self.root_box.height + 24))

            # 异步增量绘制
            def on_paint_done():
                css_info = f'  ·  外部 CSS {external_count}' if external_count else ''
                self._set_status(f'{base_url}   —   高度 {int(self.root_box.height)}px  ·  链接 {len(self.painter.link_rects)} 个{css_info}')
                if self.history_pos >= 0:
                    pos = self.history[self.history_pos].get('pos', 0.0)
                    self.canvas.yview_moveto(pos)

            self.painter.paint_async(self.root_box, base_url, on_paint_done)
            self._set_status(f'渲染中… {base_url}')

            self._download_images(self.root_box, base_url)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._err(base_url, f'渲染错误：{e}')

    def _download_images(self, box, base_url):
        if isinstance(box, ReplacedBox) and box.kind == 'image' and box.src:
            abs_src = self._abs_from(box.src, base_url)
            self.img_executor.submit(self._fetch_and_apply_image, abs_src, box)
        for child in box.children:
            self._download_images(child, base_url)

    def _fetch_and_apply_image(self, url, box):
        data = fetch_image(url)
        if not data: return
        try:
            b64 = base64.b64encode(data).decode()
            self.root.after(0, self._apply_image, box, b64)
        except Exception:
            pass

    def _apply_image(self, box, b64_data):
        try:
            img = tk.PhotoImage(data=b64_data)
            if img.width() > 800:
                img = img.subsample(2, 2)
            box._image_obj = img
            self._image_refs.append(img)
            self.painter.paint_async(self.root_box, self.current_base_url)
        except Exception:
            pass

    def _err(self, url, msg):
        self.canvas.delete('all')
        self._set_status(f'加载失败 — {url}')
        hint = ''
        if 'timed out' in msg or 'timeout' in msg.lower(): hint = '可能原因：目标响应慢 / 被屏蔽'
        elif 'Name or service not known' in msg: hint = '可能原因：DNS 解析失败'
        elif 'CERTIFICATE' in msg.upper() or 'SSL' in msg.upper(): hint = '可能原因：HTTPS 证书校验失败'
        elif '403' in msg: hint = '可能原因：服务器拒绝请求（反爬）'
        self.canvas.create_text(16, 16, anchor='nw', font=('Helvetica', -14),
            text=f'加载失败\n\n网址：{url}\n错误：{msg}\n{hint}\n\n试试在地址栏输入 mxy: 回到首页', fill='#cc0000')
        self.canvas.configure(scrollregion=(0, 0, 800, 400))

    def _set_status(self, text):
        self._base_status = text
        self.status.set(text)

    def _hit_link(self, cx, cy):
        for r in self.painter.link_rects:
            if r['x1'] <= cx <= r['x2'] and r['y1'] <= cy <= r['y2']:
                return r
        return None

    def _hit_input(self, cx, cy):
        for r in self.painter.input_rects:
            if r['x1'] <= cx <= r['x2'] and r['y1'] <= cy <= r['y2']:
                return r
        return None

    def _focus_input(self, rect):
        self._commit_active_input(submit=False)
        box = rect['box']
        ox = self.canvas.canvasx(0); oy = self.canvas.canvasy(0)
        wx = rect['x1'] - ox; wy = rect['y1'] - oy
        w = rect['x2'] - rect['x1']; h = rect['y2'] - rect['y1']

        font_tuple = (box.style.font_family, -int(box.style.font_size))
        entry = tk.Entry(self.canvas, font=font_tuple, relief='solid', borderwidth=1)
        entry.insert(0, box.value)
        entry.select_range(0, 'end')
        entry.place(x=wx, y=wy, width=w, height=h)
        entry.focus_set()

        entry.bind('<Return>', lambda e: self._commit_active_input(submit=True))
        entry.bind('<Escape>', lambda e: self._cancel_active_input())
        entry.bind('<FocusOut>', lambda e: self._commit_active_input(submit=False))

        self._active_entry = entry
        self._active_input = box

    def _commit_active_input(self, submit=False):
        if not self._active_entry or not self._active_input: return
        entry = self._active_entry; box = self._active_input
        self._active_entry = None; self._active_input = None
        try: val = entry.get()
        except tk.TclError: val = ''
        try: entry.destroy()
        except tk.TclError: pass

        if isinstance(box, InputBox):
            box.value = val; box.node.attrs['value'] = val
        self.painter.paint_async(self.root_box, self.current_base_url)
        if submit: self._submit_for_input(box)

    def _cancel_active_input(self):
        if not self._active_entry: return
        entry = self._active_entry
        self._active_entry = None; self._active_input = None
        try: entry.destroy()
        except tk.TclError: pass

    def _find_form(self, node):
        while node is not None:
            if node.tag == 'form': return node
            node = node.parent
        return None

    def _collect_form_fields(self, form, overrides=None):
        fields = {}; overrides = overrides or {}
        def visit(node):
            if node.tag == 'input':
                t = (node.attrs.get('type') or 'text').lower()
                if t in ('submit', 'button', 'reset', 'image', 'file'): return
                name = node.attrs.get('name', '')
                if name:
                    fields[name] = overrides[name] if name in overrides else node.attrs.get('value', '')
            elif node.tag == 'textarea':
                name = node.attrs.get('name', '')
                if name:
                    fields[name] = ''.join(c.text or '' for c in node.children if c.text is not None)
            for c in node.children: visit(c)
        visit(form); return fields

    def _submit_for_input(self, box):
        form = self._find_form(box.node)
        if form is None:
            if box.name:
                url = self.current_base_url
                sep = '&' if '?' in url else '?'
                self.go(url + sep + urllib.parse.urlencode({box.name: box.value}))
            return
        overrides = {box.name: box.value} if box.name else {}
        fields = self._collect_form_fields(form, overrides)
        self._navigate_form(form, fields)

    def _submit_form_button(self, box):
        form = self._find_form(box.node)
        if form is None: return
        fields = self._collect_form_fields(form)
        self._navigate_form(form, fields)

    def _navigate_form(self, form, fields):
        action = form.attrs.get('action', '').strip()
        target = urllib.parse.urljoin(self.current_base_url, action) if action else self.current_base_url
        query = urllib.parse.urlencode(fields, encoding='utf-8')
        if not query: self.go(target); return
        sep = '&' if '?' in target else '?'
        self.go(target + sep + query)

    def _on_button_press(self, e):
        self.canvas.focus_set()
        self._commit_active_input(submit=False)
        cx = self.canvas.canvasx(e.x); cy = self.canvas.canvasy(e.y)
        self.press_pos = (e.x, e.y); self.press_canvas = (cx, cy)
        self._dragging = False
        if self._temp_rect:
            self.canvas.delete(self._temp_rect); self._temp_rect = None

    def _on_button_motion(self, e):
        if not self.press_pos: return
        dx = e.x - self.press_pos[0]; dy = e.y - self.press_pos[1]
        if not self._dragging and (dx * dx + dy * dy) > DRAG_START_SQ:
            self._dragging = True
        if not self._dragging: return
        cx1, cy1 = self.press_canvas
        cx2 = self.canvas.canvasx(e.x); cy2 = self.canvas.canvasy(e.y)
        x1, y1 = min(cx1, cx2), min(cy1, cy2)
        x2, y2 = max(cx1, cx2), max(cy1, cy2)
        if self._temp_rect: self.canvas.coords(self._temp_rect, x1, y1, x2, y2)
        else: self._temp_rect = self.canvas.create_rectangle(x1, y1, x2, y2, outline='#0066cc', width=1, dash=(3, 2))

    def _on_button_release(self, e):
        if not self.press_pos: return
        try:
            if self._temp_rect:
                self.canvas.delete(self._temp_rect); self._temp_rect = None
            cx = self.canvas.canvasx(e.x); cy = self.canvas.canvasy(e.y)
            sx, sy = self.press_canvas
            dist_sq = (cx - sx) ** 2 + (cy - sy) ** 2

            if dist_sq <= CLICK_DISTANCE_SQ:
                r = self._hit_input(cx, cy)
                if r:
                    box = r['box']
                    if box.input_type in ('submit', 'button'): self._submit_form_button(box)
                    elif box.input_type == 'reset': self.painter.paint_async(self.root_box, self.current_base_url)
                    else: self._focus_input(r)
                    return

                r = self._hit_link(cx, cy)
                if r:
                    url = self._abs(r['href'])
                    if (e.state & 0x0004) or e.num == 2:
                        webbrowser.open(url)
                    else:
                        self.go(url)
                    return

                if self.painter.selection:
                    self.painter.selection = None; self.painter.paint_async(self.root_box, self.current_base_url)
            else:
                self.painter.selection = (sx, sy, cx, cy)
                self.painter.paint_async(self.root_box, self.current_base_url)
        finally:
            self.press_pos = None; self.press_canvas = None; self._dragging = False

    def _on_motion(self, e):
        cx = self.canvas.canvasx(e.x); cy = self.canvas.canvasy(e.y)
        ri = self._hit_input(cx, cy)
        if ri:
            box = ri['box']
            self.canvas.configure(cursor='xterm' if box.input_type in ('text', 'search', 'password', 'email', 'number') else 'hand2')
            if self._hover_url is not None:
                self._hover_url = None; self.status.set(self._base_status)
            return
        r = self._hit_link(cx, cy)
        if r:
            self.canvas.configure(cursor='hand2')
            if r['href'] != self._hover_url:
                self._hover_url = r['href']
                self.status.set(f'🔗 {r["href"]}')
        else:
            self.canvas.configure(cursor='arrow')
            if self._hover_url is not None:
                self._hover_url = None; self.status.set(self._base_status)

    def _on_wheel(self, e):
        self._commit_active_input(submit=False)
        if getattr(e, 'num', None) == 4: self.canvas.yview_scroll(-3, 'units')
        elif getattr(e, 'num', None) == 5: self.canvas.yview_scroll(3, 'units')
        else:
            delta = getattr(e, 'delta', 0)
            if delta: self.canvas.yview_scroll(-1 * int(delta / 120) * 3, 'units')

    def _on_canvas_configure(self, e):
        if self.root_box is None: return
        if self._resize_job: self.root.after_cancel(self._resize_job)
        width = e.width
        self._resize_job = self.root.after(150, lambda: self._relayout(width))

    def _relayout(self, width):
        self._resize_job = None
        if self.root_box is None or width < 100: return
        self._commit_active_input(submit=False)
        self.layout_engine.layout(self.root_box, width)
        self.painter.paint_async(self.root_box, self.current_base_url)

    def _on_copy(self, e=None):
        text = self._get_selected_text()
        if text:
            self.root.clipboard_clear(); self.root.clipboard_append(text)
            self.status.set(f'已复制 {len(text)} 个字符')
        return 'break'

    def _clear_selection(self, e=None):
        if self._active_entry:
            self._cancel_active_input(); return
        if self.painter.selection:
            self.painter.selection = None; self.painter.paint_async(self.root_box, self.current_base_url)

    def _get_selected_text(self):
        if not self.painter.selection: return ''
        sx1, sy1, sx2, sy2 = self.painter.selection
        x1 = min(sx1, sx2); x2 = max(sx1, sx2); y1 = min(sy1, sy2); y2 = max(sy1, sy2)
        lines_text = []
        for box in self._iter_boxes(self.root_box):
            if not box.line_boxes: continue
            for line in box.line_boxes:
                ly1 = line['y']; ly2 = line['y'] + line['height']
                if ly2 < y1 or ly1 > y2: continue
                parts = []
                for frag in line['fragments']:
                    if frag.get('kind') == 'input': continue
                    fx1 = line['x'] + frag['x']; fx2 = fx1 + frag['width']
                    fy1 = line['y']; fy2 = line['y'] + frag['font'].metrics('linespace')
                    if fx2 < x1 or fx1 > x2 or fy2 < y1 or fy1 > y2: continue
                    parts.append(frag['text'])
                if parts: lines_text.append(''.join(parts))
        return '\n'.join(lines_text)

    def _iter_boxes(self, box):
        if box is None: return
        yield box
        for child in box.children: yield from self._iter_boxes(child)

    def _abs(self, href):
        if not href: return self.current_base_url
        if '://' in href or href.startswith(('mxy:', 'data:', 'mailto:', 'javascript:')): return href
        return urllib.parse.urljoin(self.current_base_url, href)

    def go_back(self):
        if self.history_pos > 0:
            self.history[self.history_pos]['pos'] = self.canvas.yview()[0]
            self.history_pos -= 1
            self.go(self.history[self.history_pos]['url'], from_history=True)

    def go_forward(self):
        if self.history_pos < len(self.history) - 1:
            self.history[self.history_pos]['pos'] = self.canvas.yview()[0]
            self.history_pos += 1
            self.go(self.history[self.history_pos]['url'], from_history=True)

    def reload(self):
        if self.current_url: self.go(self.current_url, from_history=True)