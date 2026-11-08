# -*- coding: utf-8 -*-
"""布局引擎：block + inline + flex + float + 字体缓存 + 递归熔断"""

from box_tree import (
    BlockBox, InlineBox, TextBox, ReplacedBox, InputBox, BLOCK_DISPLAYS,
)
from css_engine import ComputedStyle


def split_text(text, preserve_ws=False):
    result = []
    buf = []
    for ch in text:
        if ch == '\n':
            if buf:
                result.append(''.join(buf)); buf = []
            result.append('\n')
        elif ord(ch) > 0x2E80:
            if buf:
                result.append(''.join(buf)); buf = []
            result.append(ch)
        elif ch == ' ':
            buf.append(ch)
            result.append(''.join(buf)); buf = []
        elif ch == '\t':
            buf.append('    ')
        else:
            buf.append(ch)
    if buf:
        result.append(''.join(buf))
    return [w for w in result if w]


class Layout:
    def __init__(self, font_manager):
        self.fm = font_manager
        self._width_cache = {}

    def layout(self, root_box, viewport_width):
        width = max(80, viewport_width - 24)
        self._layout_block(root_box, 12, 12, width, depth=0)

    def _layout_block(self, box, x, y, width, depth=0):
        style = box.style
        box.x = x
        box.y = y
        box.width = width
        
        # 【熔断保护】：防止 DOM 树无限嵌套导致堆栈溢出卡死
        if depth > 50:
            box.height = 0
            return

        if style.display == 'flex':
            if style.flex_direction in ('row', 'row-reverse'):
                self._layout_flex_row(box, x, y, width, depth)
                return

        content_x = x + style.border_left + style.padding_left
        content_y = y + style.border_top + style.padding_top
        content_width = (width - style.border_left - style.border_right
                         - style.padding_left - style.padding_right)
        if content_width < 0:
            content_width = 0

        groups = []
        for child in box.children:
            is_blk = isinstance(child, BlockBox) or (
                isinstance(child, ReplacedBox) and child.style.display in BLOCK_DISPLAYS
            )
            if child.style.float in ('left', 'right'):
                groups.append(('float', child))
            elif is_blk:
                groups.append(('block', child))
            else:
                if groups and groups[-1][0] == 'inline':
                    groups[-1][1].append(child)
                else:
                    groups.append(('inline', [child]))

        hanging = 0
        for kind, val in groups:
            if kind == 'inline' and val:
                first = val[0]
                if isinstance(first, TextBox) and box.tag == 'li':
                    font = self.fm.get_font(first.style)
                    hanging = font.measure(first.text)
                break

        new_children = []
        cur_y = content_y
        pending_margin = 0
        float_lefts = []
        float_rights = []

        for kind, val in groups:
            if kind == 'float':
                fw = val.style.width or 150
                fh = 100
                if isinstance(val, ReplacedBox) and val.kind == 'image':
                    fw = val.style.width or 150
                    fh = val.style.height or 100
                elif val.style.height:
                    fh = val.style.height

                if val.style.float == 'left':
                    if float_lefts:
                        fx = float_lefts[-1]['x'] + float_lefts[-1]['w']
                    else:
                        fx = content_x
                    val.x = fx
                    val.y = cur_y
                    val.width = fw
                    val.height = fh
                    float_lefts.append({'x': fx, 'y': cur_y, 'w': fw, 'h': fh, 'box': val})
                else:
                    if float_rights:
                        fx = float_rights[-1]['x'] - fw
                    else:
                        fx = content_x + content_width - fw
                    val.x = fx
                    val.y = cur_y
                    val.width = fw
                    val.height = fh
                    float_rights.append({'x': fx, 'y': cur_y, 'w': fw, 'h': fh, 'box': val})
                new_children.append(val)

            elif kind == 'block':
                mt = val.style.margin_top
                mb = val.style.margin_bottom
                
                if val.style.clear in ('both', 'left'):
                    cur_y = max([f['y'] + f['h'] for f in float_lefts] + [cur_y])
                if val.style.clear in ('both', 'right'):
                    cur_y = max([f['y'] + f['h'] for f in float_rights] + [cur_y])

                if pending_margin > 0 and mt > 0:
                    gap = max(pending_margin, mt)
                else:
                    gap = pending_margin + mt
                cur_y += gap

                left_shift = 0
                for f in float_lefts:
                    if f['y'] + f['h'] > cur_y:
                        left_shift = max(left_shift, f['x'] + f['w'] - content_x)
                right_shift = 0
                for f in float_rights:
                    if f['y'] + f['h'] > cur_y:
                        right_shift = max(right_shift, content_x + content_width - f['x'])

                child_x = content_x + val.style.margin_left + left_shift
                child_width = content_width - val.style.margin_left - val.style.margin_right - left_shift - right_shift
                if child_width < 0:
                    child_width = 0

                if isinstance(val, ReplacedBox) and val.kind == 'hr':
                    val.x = child_x
                    val.y = cur_y
                    val.width = child_width
                    val.height = max(1, int(val.style.border_top) or 1)
                    cur_y += val.height
                else:
                    self._layout_block(val, child_x, cur_y, child_width, depth+1)
                    cur_y += val.height

                pending_margin = mb
                new_children.append(val)
            else:
                cur_y += pending_margin
                pending_margin = 0

                anon_style = ComputedStyle()
                anon_style.font_size = style.font_size
                anon_style.color = style.color
                anon_style.text_align = style.text_align
                anon_style.text_indent = style.text_indent
                anon = BlockBox(anon_style, tag='anon')
                anon.x = content_x
                anon.y = cur_y
                anon.width = content_width
                h = self._layout_inline(
                    val, content_x, cur_y, content_width, anon,
                    hanging_indent=hanging,
                    text_indent=style.text_indent,
                )
                anon.height = h
                cur_y += h
                new_children.append(anon)

        box.children = new_children
        
        max_float_y = cur_y
        for f in float_lefts + float_rights:
            max_float_y = max(max_float_y, f['y'] + f['h'])
            
        box.height = max(0, max_float_y - y) + style.padding_bottom + style.border_bottom
        if style.height is not None:
            box.height = max(box.height, style.height)

    def _layout_flex_row(self, box, x, y, width, depth=0):
        style = box.style
        box.x = x
        box.y = y
        box.width = width

        content_x = x + style.border_left + style.padding_left
        content_y = y + style.border_top + style.padding_top
        content_width = (width - style.border_left - style.border_right
                         - style.padding_left - style.padding_right)
        if content_width < 0:
            content_width = 0

        items = []
        inline_buf = []
        for child in box.children:
            is_blk = isinstance(child, BlockBox) or (
                isinstance(child, ReplacedBox) and child.style.display in BLOCK_DISPLAYS
            )
            if is_blk:
                if inline_buf:
                    anon_style = ComputedStyle()
                    anon_style.font_size = style.font_size
                    anon_style.color = style.color
                    anon = BlockBox(anon_style, tag='anon-flex')
                    anon._flex_inline_children = inline_buf
                    items.append(anon)
                    inline_buf = []
                items.append(child)
            else:
                inline_buf.append(child)
        if inline_buf:
            anon_style = ComputedStyle()
            anon_style.font_size = style.font_size
            anon_style.color = style.color
            anon = BlockBox(anon_style, tag='anon-flex')
            anon._flex_inline_children = inline_buf
            items.append(anon)

        if not items:
            box.height = (style.padding_top + style.padding_bottom
                          + style.border_top + style.border_bottom)
            return

        n = len(items)
        gap = style.gap or 0
        total_gap = gap * (n - 1)

        grow_total = sum(getattr(it.style, 'flex_grow', 0) for it in items)
        base_widths = []
        for it in items:
            w = getattr(it.style, 'width', None)
            fb = getattr(it.style, 'flex_basis', None)
            if fb is not None:
                base_widths.append(fb)
            elif w is not None:
                base_widths.append(w)
            elif it.tag == 'input' or (isinstance(it, ReplacedBox) and it.kind == 'image'):
                base_widths.append(100)
            else:
                base_widths.append(None)

        assigned = sum(w for w in base_widths if w is not None)
        remaining = max(0, content_width - total_gap - assigned)
        auto_count = sum(1 for w in base_widths if w is None)

        widths = []
        for i, it in enumerate(items):
            w = base_widths[i]
            if w is not None:
                widths.append(max(20, w))
            else:
                if grow_total > 0:
                    gw = getattr(it.style, 'flex_grow', 0)
                    if gw > 0:
                        widths.append(max(30, remaining * gw / grow_total))
                    elif auto_count > 0:
                        widths.append(max(30, remaining / auto_count))
                    else:
                        widths.append(max(30, remaining / n))
                elif auto_count > 0:
                    widths.append(max(30, remaining / auto_count))
                else:
                    widths.append(max(30, (content_width - total_gap) / n))

        total_used = sum(widths) + total_gap
        start_x = content_x
        if style.justify_content in ('center',):
            start_x += (content_width - total_used) / 2
        elif style.justify_content in ('flex-end', 'end'):
            start_x += content_width - total_used
        elif style.justify_content in ('space-between',) and n > 1:
            extra = (content_width - sum(widths)) / (n - 1) if content_width > sum(widths) else gap
            gap = extra

        max_height = 0
        cur_x = start_x
        new_children = []

        for i, it in enumerate(items):
            cw = widths[i]
            if hasattr(it, '_flex_inline_children') and it.tag == 'anon-flex':
                it.x = cur_x
                it.y = content_y
                it.width = cw
                h = self._layout_inline(
                    it._flex_inline_children, cur_x, content_y, cw, it,
                    hanging_indent=0, text_indent=0,
                )
                it.height = h
            elif isinstance(it, ReplacedBox) and it.kind == 'hr':
                it.x = cur_x
                it.y = content_y
                it.width = cw
                it.height = max(1, int(it.style.border_top) or 1)
            else:
                self._layout_block(it, cur_x, content_y, cw, depth+1)
            max_height = max(max_height, it.height)
            cur_x += cw + gap
            new_children.append(it)

        box.children = new_children
        box.height = (max_height + style.padding_top + style.padding_bottom
                      + style.border_top + style.border_bottom)
        if style.height is not None:
            box.height = max(box.height, style.height)

    def _layout_inline(self, items, x, y, available_width, parent,
                       hanging_indent=0, text_indent=0):
        lines = []
        state = {
            'line': self._new_line(x + text_indent),
            'cur_x': 0,
            'first_line': True,
        }

        def flush_line():
            if state['line']['fragments']:
                lines.append(state['line'])

        def new_line():
            flush_line()
            state['first_line'] = False
            offset = hanging_indent if len(lines) > 0 else 0
            state['line'] = self._new_line(x + offset)
            state['cur_x'] = 0

        def add_word(text, style, link, kind='text', nowrap=False):
            if not text: return
            if style.is_link and style.link_href:
                link = style.link_href
            
            font_key = (style.font_family, style.font_size, style.font_weight, style.font_style)
            cache_key = (font_key, text)
            
            if cache_key in self._width_cache:
                w = self._width_cache[cache_key]
                font = self.fm.get_font(style)
            else:
                font = self.fm.get_font(style)
                w = font.measure(text)
                self._width_cache[cache_key] = w
                
            line_h = max(font.metrics('linespace'), int(style.line_height or 0))

            if available_width < 50:
                nowrap = True

            if (state['cur_x'] + w > available_width
                    and state['cur_x'] > 0
                    and style.white_space not in ('nowrap', 'pre')
                    and not nowrap):
                new_line()

            line = state['line']
            line['fragments'].append({
                'x': state['cur_x'], 'text': text, 'style': style,
                'font': font, 'width': w, 'link': link, 'kind': kind,
            })
            state['cur_x'] += w
            line['width'] = state['cur_x']
            line['height'] = max(line['height'], line_h)

        def add_input(inp):
            font = self.fm.get_font(inp.style)
            if inp.input_type in ('submit', 'button', 'reset'):
                label = inp.value or ('提交' if inp.input_type == 'submit' else '按钮')
                w = max(font.measure(label) + 24, 60)
            else:
                w = max(font.measure('M') * inp.size + 12, 120)
            h = font.metrics('linespace') + 8

            if state['cur_x'] + w > available_width and state['cur_x'] > 0:
                new_line()

            line = state['line']
            line['fragments'].append({
                'x': state['cur_x'], 'text': '', 'style': inp.style,
                'font': font, 'width': w, 'link': None, 'kind': 'input',
                'input_box': inp, 'height': h,
            })
            state['cur_x'] += w
            line['width'] = state['cur_x']
            line['height'] = max(line['height'], h)

        def flatten(item, link):
            if getattr(item, 'tag', None) == 'br':
                new_line()
                return
            if isinstance(item, TextBox):
                preserve = item.style.white_space in ('pre', 'pre-wrap')
                for word in split_text(item.text, preserve_ws=preserve):
                    if word == '\n':
                        new_line()
                    else:
                        add_word(word, item.style, link)
            elif isinstance(item, InlineBox):
                sub_link = item.style.link_href if item.style.is_link else link
                for c in item.children:
                    flatten(c, sub_link)
            elif isinstance(item, InputBox):
                add_input(item)
            elif isinstance(item, ReplacedBox):
                if item.kind == 'image':
                    add_word(f'[图片: {item.alt}]', item.style, link, kind='image', nowrap=True)

        for item in items:
            flatten(item, None)

        flush_line()

        total_h = 0
        for l in lines:
            l['y'] = y + total_h
            total_h += l['height']

        for l in lines:
            if not l['fragments']:
                continue
            align = l['fragments'][0]['style'].text_align
            if align == 'center':
                offset = (available_width - l['width']) / 2
                if offset > 0:
                    l['x'] += offset
            elif align == 'right':
                offset = available_width - l['width']
                if offset > 0:
                    l['x'] += offset

        parent.line_boxes = lines
        return total_h if lines else 0

    def _new_line(self, x):
        return {
            'x': x, 'y': 0, 'width': 0, 'height': 0,
            'fragments': [],
        }