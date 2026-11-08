# -*- coding: utf-8 -*-
"""DOM → Box Tree"""

from css_engine import compute_style, ComputedStyle


BLOCK_DISPLAYS = {'block', 'list-item', 'table', 'flex', 'grid'}


class Box:
    __slots__ = ('style', 'children', 'parent', 'x', 'y', 'width', 'height',
                 'line_boxes', 'tag', '_flex_inline_children', '_image_obj')

    def __init__(self, style, tag=None):
        self.style = style
        self.children = []
        self.parent = None
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0
        self.line_boxes = None
        self.tag = tag
        self._flex_inline_children = None
        self._image_obj = None


class BlockBox(Box):
    __slots__ = ()


class InlineBox(Box):
    __slots__ = ()


class TextBox(Box):
    __slots__ = ('text',)

    def __init__(self, text, style):
        super().__init__(style)
        self.text = text


class ReplacedBox(Box):
    __slots__ = ('kind', 'alt', 'src')

    def __init__(self, kind, alt, style, src=''):
        super().__init__(style)
        self.kind = kind
        self.alt = alt
        self.src = src


class InputBox(Box):
    __slots__ = ('node', 'input_type', 'name', 'value', 'placeholder', 'size')

    def __init__(self, style, node):
        super().__init__(style, tag='input')
        self.node = node
        self.input_type = (node.attrs.get('type') or 'text').lower()
        self.name = node.attrs.get('name', '')
        self.value = node.attrs.get('value', '')
        self.placeholder = node.attrs.get('placeholder', '')
        try:
            self.size = int(node.attrs.get('size', '20'))
        except (ValueError, TypeError):
            self.size = 20


def build_box_tree(root_dom, rules):
    root_style = ComputedStyle()
    root_style.display = 'block'
    root_style.font_size = 16
    root_style.font_family = 'Helvetica'
    root = BlockBox(root_style, tag='root')

    for child_dom in root_dom.children:
        box = _build_recursive(child_dom, root, None, rules)
        if box:
            box.parent = root
            root.children.append(box)

    return root


def _build_recursive(dom, parent_box, parent_style, rules):
    style = compute_style(dom, parent_style, rules)

    if style.display == 'none':
        return None

    if dom.text is not None:
        return TextBox(dom.text, style)

    if dom.tag == 'input':
        if (dom.attrs.get('type') or '').lower() == 'hidden':
            return None
        return InputBox(style, dom)

    if dom.tag == 'img':
        return ReplacedBox('image', dom.attrs.get('alt', '图片'), style, dom.attrs.get('src', ''))
    if dom.tag == 'hr':
        return ReplacedBox('hr', None, style)

    is_block = style.display in BLOCK_DISPLAYS
    box = BlockBox(style, tag=dom.tag) if is_block else InlineBox(style, tag=dom.tag)

    if dom.tag == 'li' and dom.parent and dom.parent.tag in ('ul', 'ol'):
        if style.list_style_type != 'none':
            if dom.parent.tag == 'ol':
                try:
                    idx = dom.parent.children.index(dom) + 1
                except ValueError:
                    idx = 1
                prefix = f'{idx}. '
            else:
                prefix = '• '
            pbox = TextBox(prefix, style)
            pbox.parent = box
            box.children.append(pbox)

    for child_dom in dom.children:
        cbox = _build_recursive(child_dom, box, style, rules)
        if cbox:
            cbox.parent = box
            box.children.append(cbox)

    return box