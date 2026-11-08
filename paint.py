# -*- coding: utf-8 -*-
"""绘制到 Canvas（异步增量绘制 + 防止 UI 卡死）"""

from box_tree import ReplacedBox
import time

def style_key(s):
    return (s.font_size, s.font_weight, s.font_style, s.font_family, 
            s.color, s.bg, s.text_decoration)

class Painter:
    def __init__(self, canvas, font_manager):
        self.canvas = canvas
        self.fm = font_manager
        self.link_rects = []
        self.input_rects = []
        self.base_url = ''
        self.selection = None
        
        # 异步绘制队列
        self.draw_queue = []
        self.is_drawing = False
        self.generation = 0

    def paint_async(self, root_box, base_url, on_complete=None):
        """异步绘制入口，不阻塞 UI 线程"""
        self.generation += 1
        gen = self.generation
        
        self.canvas.delete('all')
        self.link_rects = []
        self.input_rects = []
        self.base_url = base_url
        self.draw_queue = []
        
        if root_box:
            self._collect_draw_ops(root_box)
            
        self.is_drawing = True
        self._process_draw_queue(gen, on_complete)

    def _collect_draw_ops(self, box):
        """收集需要绘制的操作，存入队列"""
        style = box.style
        if style.visibility == 'hidden': return

        if isinstance(box, ReplacedBox) and box.kind == 'hr':
            self.draw_queue.append(('line', box.x, box.y, box.x + box.width, box.y, style.border_color or '#999999'))
            return

        if style.bg:
            self.draw_queue.append(('rect', box.x, box.y, box.x + box.width, box.y + box.height, style.bg, ''))
        
        if style.border_top > 0:
            self.draw_queue.append(('rect', box.x, box.y, box.x + box.width, box.y + box.height, '', style.border_color or '#000000', max(1, int(style.border_top))))

        if isinstance(box, ReplacedBox) and box.kind == 'image':
            if box._image_obj:
                self.draw_queue.append(('image', box.x, box.y, box._image_obj))
            else:
                self.draw_queue.append(('rect', box.x, box.y, box.x + box.width, box.y + box.height, '#f0f0f0', '#cccccc'))
                self.draw_queue.append(('text', box.x + box.width/2, box.y + box.height/2, f'[图片: {box.alt}]', ('Sans', 10), '#888888', 'center'))

        if box.line_boxes:
            for line in box.line_boxes:
                self._collect_line_ops(line)

        for child in box.children:
            self._collect_draw_ops(child)

    def _collect_line_ops(self, line):
        line_top = line['y']
        line_bottom = line['y'] + line['height']
        pending_link = None

        def flush_link():
            if pending_link and pending_link['x2'] > pending_link['x1']:
                self.link_rects.append({
                    'x1': pending_link['x1'], 'y1': line_top - 1,
                    'x2': pending_link['x2'] + 1, 'y2': line_bottom + 1,
                    'href': pending_link['href'],
                })

        frags = line['fragments']
        i = 0
        n = len(frags)

        while i < n:
            frag = frags[i]
            x = line['x'] + frag['x']
            y = line['y']
            style = frag['style']
            font = frag['font']
            kind = frag.get('kind', 'text')

            if kind == 'input':
                flush_link()
                pending_link = None
                inp = frag['input_box']
                w = frag['width']; h = frag['height']
                inp.x = x; inp.y = y; inp.width = w; inp.height = h
                
                if inp.input_type in ('submit', 'button', 'reset'):
                    bg = '#ffe0e0' if inp.input_type == 'reset' else '#f0f0f0'
                    self.draw_queue.append(('rect', x, y, x + w, y + h, bg, '#999999'))
                    label = inp.value or ('提交' if inp.input_type == 'submit' else '重置' if inp.input_type == 'reset' else '按钮')
                    self.draw_queue.append(('text', x + w / 2, y + h / 2, label, font, '#000000', 'center'))
                else:
                    self.draw_queue.append(('rect', x, y, x + w, y + h, 'white', '#999999'))
                    text = inp.value or inp.placeholder
                    color = '#000000' if inp.value else '#999999'
                    if text: self.draw_queue.append(('text', x + 6, y + h / 2, text, font, color, 'w'))

                self.input_rects.append({'x1': x, 'y1': y, 'x2': x + w, 'y2': y + h, 'box': inp})
                i += 1
                continue

            text = frag['text']
            width = frag['width']
            link = frag.get('link')
            current_key = style_key(style)
            j = i + 1
            while j < n:
                nxt = frags[j]
                if nxt.get('kind') == 'input': break
                if style_key(nxt['style']) != current_key: break
                if nxt.get('link') != link: break
                if nxt.get('kind') == 'image' or frag.get('kind') == 'image': break
                if len(text) > 2000: break
                text += nxt['text']
                width += nxt['width']
                j += 1

            line_h = font.metrics('linespace')

            if self.selection:
                sx1, sy1, sx2, sy2 = self.selection
                x1 = min(sx1, sx2); x2 = max(sx1, sx2)
                y1 = min(sy1, sy2); y2 = max(sy1, sy2)
                if not (x + width < x1 or x > x2 or y + line_h < y1 or y > y2):
                    self.draw_queue.append(('rect', x, y, x + width, y + line_h, '#cce6ff', ''))

            color = style.color
            if kind == 'image': color = '#888888'

            clean_text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
            if clean_text.strip():
                self.draw_queue.append(('text', x, y, clean_text, font, color, 'nw'))

            if style.text_decoration and 'underline' in style.text_decoration:
                uy = y + line_h - 2
                self.draw_queue.append(('line', x, uy, x + width, uy, color))

            if link:
                if pending_link and pending_link['href'] == link:
                    pending_link['x2'] = x + width
                else:
                    flush_link()
                    pending_link = {'href': link, 'x1': x, 'x2': x + width}
            else:
                flush_link()
                pending_link = None

            i = j

        flush_link()

    def _process_draw_queue(self, gen, on_complete):
        """每次只画 100 个操作，然后让出主线程"""
        if self.generation != gen:
            return # 期间用户切了页面，丢弃旧任务
            
        start_t = time.time()
        count = 0
        
        while self.draw_queue and count < 100:
            op = self.draw_queue.pop(0)
            try:
                if op[0] == 'rect':
                    _, x1, y1, x2, y2, fill, outline, *args = op
                    width = args[0] if args else 1
                    self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=width)
                elif op[0] == 'text':
                    _, x, y, text, font, fill, anchor = op
                    self.canvas.create_text(x, y, text=text, font=font, fill=fill, anchor=anchor)
                elif op[0] == 'line':
                    _, x1, y1, x2, y2, fill = op
                    self.canvas.create_line(x1, y1, x2, y2, fill=fill)
                elif op[0] == 'image':
                    _, x, y, img = op
                    self.canvas.create_image(x, y, image=img, anchor='nw')
            except Exception:
                pass
            count += 1

        if self.draw_queue:
            # 还有剩余，10 毫秒后继续画
            self.canvas.after(10, self._process_draw_queue, gen, on_complete)
        else:
            self.is_drawing = False
            if on_complete:
                on_complete()