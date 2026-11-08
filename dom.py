# -*- coding: utf-8 -*-
"""极简 DOM 节点（带 DOM API）"""

class DomNode:
    __slots__ = ('tag', 'attrs', 'text', 'children', 'parent')

    def __init__(self, tag=None, attrs=None, text=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.text = text
        self.children = []
        self.parent = None

    def append(self, child):
        child.parent = self
        self.children.append(child)

    def get_element_by_id(self, id_val):
        if self.attrs.get('id') == id_val:
            return self
        for c in self.children:
            res = c.get_element_by_id(id_val)
            if res: return res
        return None

    def query_selector_all(self, tag=None, class_name=None):
        res = []
        if (not tag or self.tag == tag) and (
                not class_name or class_name in self.attrs.get('class', '').split()):
            res.append(self)
        for c in self.children:
            res.extend(c.query_selector_all(tag, class_name))
        return res

    def set_inner_html(self, html):
        self.children = []
        self.append(DomNode(text=html))

    def get_inner_text(self):
        texts = []
        if self.text: texts.append(self.text)
        for c in self.children:
            texts.append(c.get_inner_text())
        return ''.join(texts)

    def set_text_content(self, text):
        self.children = []
        self.text = text

    def set_style(self, prop, value):
        style_str = self.attrs.get('style', '')
        self.attrs['style'] = f'{style_str}; {prop}:{value};'

    def get(self, prop):
        if prop == 'innerHTML': return self.get_inner_text()
        if prop == 'textContent': return self.get_inner_text()
        if prop == 'style': return JsStyle(self)
        if prop == 'id' or prop == 'className':
            return self.attrs.get('class' if prop == 'className' else prop, '')
        if prop in self.attrs:
            return self.attrs[prop]
        return ''

    def set(self, prop, value):
        if prop == 'textContent':
            self.set_text_content(str(value))
        elif prop == 'innerHTML':
            self.set_inner_html(str(value))
        elif prop == 'className':
            self.attrs['class'] = str(value)
        else:
            self.attrs[prop] = str(value)

class JsStyle:
    def __init__(self, node):
        self.node = node
    def set(self, prop, value):
        self.node.set_style(prop, value)