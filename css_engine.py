# -*- coding: utf-8 -*-
"""CSS 解析 + 计算样式（使用哈希索引加速匹配）"""

import re

LENGTH_RE = re.compile(r'^(-?[\d.]+)(px|pt|em|rem|%)?$')

SUPPORTED_PROPS = {
    'display', 'font-size', 'font-weight', 'font-style', 'font-family',
    'color', 'background-color', 'text-decoration', 'text-align',
    'text-indent', 'white-space', 'visibility', 'list-style-type',
    'margin', 'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
    'padding', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
    'border', 'border-top', 'border-right', 'border-bottom', 'border-left',
    'border-width', 'border-color', 'border-style',
    'width', 'height', 'max-width', 'min-width', 'line-height',
    'flex', 'flex-direction', 'flex-grow', 'flex-shrink', 'flex-basis',
    'justify-content', 'align-items', 'gap', 'overflow',
    'float', 'clear', 'background',
}

NAMED_COLORS = {
    'black': '#000000', 'white': '#ffffff', 'red': '#ff0000', 'blue': '#0000ff',
    'green': '#008000', 'gray': '#808080', 'grey': '#808080', 'yellow': '#ffff00',
    'orange': '#ffa500', 'purple': '#800080', 'pink': '#ffc0cb',
    'brown': '#a52a2a', 'silver': '#c0c0c0', 'navy': '#000080',
    'teal': '#008080', 'maroon': '#800000', 'lime': '#00ff00',
    'aqua': '#00ffff', 'cyan': '#00ffff', 'fuchsia': '#ff00ff',
    'magenta': '#ff00ff', 'olive': '#808000', 'darkgray': '#a9a9a9',
    'lightgray': '#d3d3d3', 'lightgrey': '#d3d3d3', 'darkgrey': '#a9a9a9',
    'transparent': None,
}


def css_color(v):
    v = v.strip().lower()
    if v in NAMED_COLORS: return NAMED_COLORS[v]
    if re.match(r'^#[0-9a-f]{3}$', v): return '#' + ''.join(c * 2 for c in v[1:])
    if re.match(r'^#[0-9a-f]{6}$', v): return v
    if re.match(r'^#[0-9a-f]{8}$', v): return v[:7]
    m = re.match(r'rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)', v)
    if m:
        r, g, b = (int(float(x)) for x in m.groups())
        return '#%02x%02x%02x' % (min(r, 255), min(g, 255), min(b, 255))
    return None


def parse_length(v, em_base=16):
    if v is None: return None
    v = v.strip().lower()
    if not v or v in ('auto', 'none', 'normal', 'inherit', 'initial'): return None
    m = LENGTH_RE.match(v)
    if not m: return None
    n = float(m.group(1)); unit = m.group(2) or 'px'
    if unit == 'px': return n
    if unit == 'pt': return n * 4 / 3
    if unit in ('em', 'rem'): return n * em_base
    if unit == '%': return None
    return None


def _strip_at_rules(text):
    out = []; i = 0; n = len(text)
    while i < n:
        if text[i] == '@':
            m = re.match(r'@([\w-]+)', text[i:])
            if m:
                j = i + m.end()
                while j < n and text[j] in ' \t\n\r': j += 1
                if j < n and text[j] == '{':
                    depth = 1; k = j + 1; in_str = None
                    while k < n and depth > 0:
                        c = text[k]
                        if in_str:
                            if c == '\\': k += 2; continue
                            if c == in_str: in_str = None
                        elif c in ('"', "'"): in_str = c
                        elif c == '{': depth += 1
                        elif c == '}': depth -= 1
                        k += 1
                    i = k; continue
                else:
                    while j < n and text[j] != ';': j += 1
                    i = j + 1; continue
        out.append(text[i]); i += 1
    return ''.join(out)


def _parse_simple_selector(s):
    if not s: return None
    tag = None; classes = []; id_ = None; attrs = []; pseudos = []; spec = [0, 0, 0]
    i = 0; n = len(s)
    while i < n:
        c = s[i]
        if c == '*': i += 1; continue
        if c == '.':
            m = re.match(r'\.([a-zA-Z_][\w-]*)', s[i:])
            if not m: return None
            classes.append(m.group(1)); spec[1] += 1; i += m.end()
        elif c == '#':
            m = re.match(r'#([a-zA-Z_][\w-]*)', s[i:])
            if not m: return None
            id_ = m.group(1); spec[0] += 1; i += m.end()
        elif c == '[':
            m = re.match(r'\[([\w-]+)(?:([~|^$*]?=)["\']?([^"\'\]]+)["\']?)?\]', s[i:])
            if not m: return None
            attrs.append((m.group(1).lower(), m.group(2), m.group(3)))
            spec[1] += 1; i += m.end()
        elif c == ':':
            if s.startswith('::', i):
                return None
            m = re.match(r':([\w-]+)(?:\(([^()]*)\))?', s[i:])
            if not m: return None
            name, argument = m.group(1).lower(), m.group(2)
            if name not in {
                'first-child', 'last-child', 'only-child', 'nth-child',
                'first-of-type', 'last-of-type', 'only-of-type',
                'nth-of-type', 'not', 'empty', 'root', 'checked',
                'disabled', 'enabled', 'link',
            }:
                return None
            if name in ('nth-child', 'nth-of-type', 'not') and argument is None:
                return None
            pseudos.append((name, argument))
            if name == 'not' and argument:
                inner = _parse_simple_selector(argument.strip())
                if inner is None:
                    return None
                for j in range(3): spec[j] += inner[1][j]
            else:
                spec[1] += 1
            i += m.end()
        elif re.match(r'[a-zA-Z]', c):
            m = re.match(r'([a-zA-Z][\w-]*)', s[i:])
            tag = m.group(1).lower(); spec[2] += 1; i += m.end()
        else: return None
    if tag is None and not classes and id_ is None and not attrs and not pseudos: return None
    return (tag, classes, id_, attrs, pseudos), tuple(spec)


def _parse_selector(sel):
    s = re.sub(r'\s*>\s*', ' > ', sel.strip())
    s = re.sub(r'\s*\+\s*', ' + ', s)
    s = re.sub(r'\s*~\s*', ' ~ ', s)
    s = re.sub(r'\s+', ' ', s)
    if not s: return None
    tokens = s.split(' '); parts = []; total_spec = [0, 0, 0]; combinator = None
    for tok in tokens:
        if tok in ('>', '+', '~'): combinator = tok; continue
        parsed = _parse_simple_selector(tok)
        if parsed is None: return None
        simple, spec = parsed
        parts.append((simple, combinator if parts else None))
        for i in range(3): total_spec[i] += spec[i]
        combinator = ' '
    if not parts: return None
    return parts, tuple(total_spec)


class CSSRule:
    __slots__ = ('parts', 'props', 'order', 'specificity')
    def __init__(self, parts, props, order, specificity):
        self.parts = parts; self.props = props
        self.order = order; self.specificity = specificity


class StyleSheet:
    def __init__(self, rules):
        self.by_tag = {}
        self.by_class = {}
        self.by_id = {}
        self.by_any = []
        for r in rules:
            key_simple = r.parts[-1][0]
            tag, classes, id_, attrs, pseudos = key_simple
            if id_:
                self.by_id.setdefault(id_, []).append(r)
            elif classes:
                for c in classes:
                    self.by_class.setdefault(c, []).append(r)
            elif tag:
                self.by_tag.setdefault(tag, []).append(r)
            else:
                self.by_any.append(r)

    def get_matched(self, dom):
        candidates = []
        if dom.tag: candidates.extend(self.by_tag.get(dom.tag, []))
        if dom.attrs.get('id'): candidates.extend(self.by_id.get(dom.attrs['id'], []))
        if dom.attrs.get('class'):
            for c in dom.attrs['class'].split():
                candidates.extend(self.by_class.get(c, []))
        candidates.extend(self.by_any)
        
        matched = [r for r in set(candidates) if _matches(dom, r)]
        matched.sort(key=lambda r: (r.specificity, r.order))
        return matched


def parse_css(text):
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    text = _strip_at_rules(text)
    rules = []; order = 0
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', text):
        sel_group, body = m.group(1).strip(), m.group(2)
        props = {}
        for decl in _split_css_values(body, ';'):
            if ':' in decl:
                k, v = decl.split(':', 1)
                k = k.strip().lower()
                v = re.sub(r'\s*!important\s*$', '', v.strip(), flags=re.I)
                if k in SUPPORTED_PROPS and v: props[k] = v
        if not props: continue
        for sel in _split_css_values(sel_group, ','):
            sel = sel.strip()
            if not sel: continue
            parsed = _parse_selector(sel)
            if parsed is None: continue
            parts, spec = parsed
            rules.append(CSSRule(parts, props, order, spec))
            order += 1
    return StyleSheet(rules)


def _split_css_values(text, separator):
    values = []
    start = 0
    depth = 0
    quote = None
    escaped = False
    for i, char in enumerate(text):
        if escaped:
            escaped = False
        elif char == '\\':
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in ('"', "'"):
            quote = char
        elif char in '([':
            depth += 1
        elif char in ')]':
            depth = max(0, depth - 1)
        elif char == separator and depth == 0:
            values.append(text[start:i].strip())
            start = i + 1
    values.append(text[start:].strip())
    return values


DEFAULT_CSS = """
html { display: block; }
body { display: block; margin: 8px; }
div, p, section, article, header, footer, nav, main, aside, blockquote,
address, figure, figcaption, details, summary, dialog, hgroup, search,
h1, h2, h3, h4, h5, h6, ul, ol, li, table, tr, pre, form, fieldset, dl, dt, dd {
    display: block;
}
h1 { font-size: 2em; font-weight: bold; margin: 0.67em 0; }
h2 { font-size: 1.5em; font-weight: bold; margin: 0.83em 0; }
h3 { font-size: 1.17em; font-weight: bold; margin: 1em 0; }
h4 { font-size: 1em; font-weight: bold; margin: 1.33em 0; }
h5 { font-size: 0.83em; font-weight: bold; margin: 1.67em 0; }
h6 { font-size: 0.67em; font-weight: bold; margin: 2.33em 0; }
p { margin: 1em 0; }
ul, ol { margin: 1em 0; padding-left: 40px; }
li { display: list-item; }
blockquote { margin: 1em 40px; }
pre { font-family: Courier; margin: 1em 0; white-space: pre; }
dl { margin: 1em 0; }
dd { margin-left: 40px; }
hr { display: block; border-top: 1px solid #999999; margin: 0.5em 0; }
b, strong { font-weight: bold; }
i, em { font-style: italic; }
code, kbd, samp, tt { font-family: Courier; }
a { color: #0066cc; text-decoration: underline; display: inline-block; }
head, script, style, meta, title, noscript, base, link { display: none; }
img, input, button, select, textarea { display: inline-block; }
[hidden] { display: none; }
"""


def get_style_rules(user_css):
    return parse_css(DEFAULT_CSS + "\n" + (user_css or ''))


class ComputedStyle:
    __slots__ = (
        'display', 'font_size', 'font_weight', 'font_style', 'font_family',
        'color', 'bg', 'text_decoration', 'text_align', 'text_indent',
        'white_space', 'visibility', 'list_style_type',
        'margin_top', 'margin_right', 'margin_bottom', 'margin_left',
        'padding_top', 'padding_right', 'padding_bottom', 'padding_left',
        'border_top', 'border_right', 'border_bottom', 'border_left',
        'border_color', 'width', 'height', 'line_height',
        'flex_direction', 'flex_grow', 'flex_basis',
        'justify_content', 'align_items', 'gap',
        'float', 'clear',
        'is_link', 'link_href',
    )

    def __init__(self):
        self.display = 'inline'; self.font_size = 16
        self.font_weight = 'normal'; self.font_style = 'normal'
        self.font_family = 'Helvetica'; self.color = '#000000'
        self.bg = None; self.text_decoration = None
        self.text_align = 'left'; self.text_indent = 0
        self.white_space = 'normal'; self.visibility = 'visible'
        self.list_style_type = 'disc'
        self.margin_top = self.margin_right = self.margin_bottom = self.margin_left = 0
        self.padding_top = self.padding_right = self.padding_bottom = self.padding_left = 0
        self.border_top = self.border_right = self.border_bottom = self.border_left = 0
        self.border_color = '#000000'
        self.width = self.height = self.line_height = None
        self.flex_direction = 'row'; self.flex_grow = 0; self.flex_basis = None
        self.justify_content = 'flex-start'; self.align_items = 'stretch'; self.gap = 0
        self.float = 'none'; self.clear = 'none'
        self.is_link = False; self.link_href = None

    def copy(self):
        s = ComputedStyle()
        for slot in self.__slots__: setattr(s, slot, getattr(self, slot))
        return s


def _match_simple(dom, simple):
    if dom is None or dom.tag is None: return False
    tag, classes, id_, attrs, pseudos = simple
    if tag is not None and dom.tag != tag: return False
    if id_ is not None and dom.attrs.get('id') != id_: return False
    if classes:
        dom_classes = dom.attrs.get('class', '').split()
        for c in classes:
            if c not in dom_classes: return False
    for name, op, val in attrs:
        actual = dom.attrs.get(name)
        if actual is None: return False
        if op is None: continue
        if op == '=':
            if actual != val: return False
        elif op == '~=':
            if val not in actual.split(): return False
        elif op == '|=':
            if actual != val and not actual.startswith(val + '-'): return False
        elif op == '^=':
            if not actual.startswith(val): return False
        elif op == '$=':
            if not actual.endswith(val): return False
        elif op == '*=':
            if val not in actual: return False
    for name, argument in pseudos:
        if not _matches_pseudo(dom, name, argument):
            return False
    return True


def _element_siblings(dom, of_type=False):
    if dom.parent is None:
        return []
    siblings = [node for node in dom.parent.children if node.tag is not None]
    if of_type:
        siblings = [node for node in siblings if node.tag == dom.tag]
    return siblings


def _matches_nth(index, expression):
    value = re.sub(r'\s+', '', (expression or '').lower())
    if value == 'odd':
        return index % 2 == 1
    if value == 'even':
        return index % 2 == 0
    if re.fullmatch(r'[+-]?\d+', value):
        return index == int(value)
    match = re.fullmatch(r'([+-]?\d*)n([+-]\d+)?', value)
    if not match:
        return False
    coefficient = match.group(1)
    a = -1 if coefficient == '-' else 1 if coefficient in ('', '+') else int(coefficient)
    b = int(match.group(2) or 0)
    difference = index - b
    return difference == 0 if a == 0 else difference % a == 0 and difference // a >= 0


def _matches_pseudo(dom, name, argument):
    if name in ('first-child', 'last-child', 'only-child',
                'first-of-type', 'last-of-type', 'only-of-type',
                'nth-child', 'nth-of-type'):
        of_type = name.endswith('of-type')
        siblings = _element_siblings(dom, of_type)
        try:
            index = siblings.index(dom) + 1
        except ValueError:
            return False
        if name.startswith('first-'):
            return index == 1
        if name.startswith('last-'):
            return index == len(siblings)
        if name.startswith('only-'):
            return len(siblings) == 1
        return _matches_nth(index, argument)
    if name == 'not':
        inner = _parse_simple_selector((argument or '').strip())
        return inner is not None and not _match_simple(dom, inner[0])
    if name == 'empty':
        return not any(child.tag is not None or (child.text or '') for child in dom.children)
    if name == 'root':
        return dom.parent is not None and dom.parent.tag == 'root'
    if name == 'checked':
        return 'checked' in dom.attrs or 'selected' in dom.attrs
    if name == 'disabled':
        return 'disabled' in dom.attrs
    if name == 'enabled':
        return dom.tag in ('input', 'button', 'select', 'textarea') and 'disabled' not in dom.attrs
    if name == 'link':
        return dom.tag == 'a' and 'href' in dom.attrs
    return False


def _matches(dom, rule):
    if dom is None or dom.tag is None: return False
    parts = rule.parts
    idx = len(parts) - 1
    node = dom
    if not _match_simple(node, parts[idx][0]):
        return False
    while idx > 0:
        combinator = parts[idx][1]
        simple = parts[idx - 1][0]
        if combinator == '>':
            node = node.parent
            if not _match_simple(node, simple):
                return False
        elif combinator == ' ':
            ancestor = node.parent
            while ancestor is not None and not _match_simple(ancestor, simple):
                ancestor = ancestor.parent
            if ancestor is None:
                return False
            node = ancestor
        elif combinator in ('+', '~'):
            if node.parent is None:
                return False
            siblings = [child for child in node.parent.children if child.tag is not None]
            try:
                sibling_index = siblings.index(node)
            except ValueError:
                return False
            preceding = siblings[:sibling_index]
            if combinator == '+':
                if not preceding:
                    return False
                candidate = preceding[-1]
                if not _match_simple(candidate, simple):
                    return False
            else:
                candidate = next((sibling for sibling in reversed(preceding)
                                  if _match_simple(sibling, simple)), None)
                if candidate is None:
                    return False
            node = candidate
        else:
            return False
        idx -= 1
    return True


def select_nodes(root, selector):
    parsed = _parse_selector(selector)
    if parsed is None:
        return []
    parts, specificity = parsed
    rule = CSSRule(parts, {}, 0, specificity)
    matches = []
    pending = list(reversed(root.children))
    while pending:
        node = pending.pop()
        if _matches(node, rule):
            matches.append(node)
        pending.extend(reversed(node.children))
    return matches


def _apply_box(style, prefix, key, v, em_base):
    if key == prefix:
        parts = v.split()
        values = [parse_length(p, em_base) or 0 for p in parts]
        if len(values) == 1: t = r = b = l = values[0]
        elif len(values) == 2: t = b = values[0]; r = l = values[1]
        elif len(values) == 3: t, r, b = values; l = r
        elif len(values) >= 4: t, r, b, l = values[:4]
        else: return
        setattr(style, f'{prefix}_top', t); setattr(style, f'{prefix}_right', r)
        setattr(style, f'{prefix}_bottom', b); setattr(style, f'{prefix}_left', l)
    else:
        side = key[len(prefix) + 1:]
        if side in ('top', 'right', 'bottom', 'left'):
            n = parse_length(v, em_base) or 0
            setattr(style, f'{prefix}_{side}', n)


def _apply_border(style, key, v):
    if key == 'border':
        parts = v.split(); width = None; color = None
        for p in parts:
            pl = parse_length(p)
            if pl is not None: width = pl
            else:
                c = css_color(p)
                if c: color = c
        if width is not None:
            style.border_top = style.border_right = style.border_bottom = style.border_left = width
        if color: style.border_color = color
    elif key == 'border-width':
        n = parse_length(v)
        if n is not None:
            style.border_top = style.border_right = style.border_bottom = style.border_left = n
    elif key == 'border-color':
        c = css_color(v)
        if c: style.border_color = c
    elif key.startswith('border-'):
        side = key[7:]
        if side in ('top', 'right', 'bottom', 'left'):
            for p in v.split():
                pl = parse_length(p)
                if pl is not None: setattr(style, f'border_{side}', pl)
                else:
                    c = css_color(p)
                    if c: style.border_color = c


def _apply_prop(style, k, v, parent_style):
    parent_fs = parent_style.font_size if parent_style else 16
    v = v.strip()
    if not v: return
    if k == 'font-size':
        n = parse_length(v, parent_fs)
        if n is not None: style.font_size = max(6, n)
    elif k == 'font-weight':
        vv = v.lower()
        if vv in ('bold', 'bolder'): style.font_weight = 'bold'
        elif vv == 'normal': style.font_weight = 'normal'
        elif vv.isdigit() and int(vv) >= 600: style.font_weight = 'bold'
    elif k == 'font-style':
        style.font_style = 'italic' if v.lower() in ('italic', 'oblique') else 'normal'
    elif k == 'font-family':
        first = v.split(',')[0].strip().strip('"\'').lower()
        if 'mono' in first or 'courier' in first: style.font_family = 'Courier'
        elif 'serif' in first and 'sans' not in first: style.font_family = 'Times'
        else: style.font_family = 'Helvetica'
    elif k == 'color':
        c = css_color(v)
        if c: style.color = c
    elif k in ('background-color', 'background'):
        c = css_color(v)
        if c is None:
            c = next((css_color(part) for part in v.split()
                      if css_color(part) is not None), None)
        if c: style.bg = c
    elif k == 'text-decoration': style.text_decoration = v.lower()
    elif k == 'text-align': style.text_align = v.lower()
    elif k == 'text-indent':
        n = parse_length(v, style.font_size)
        if n is not None: style.text_indent = n
    elif k == 'white-space':
        vv = v.lower()
        if vv in ('normal', 'nowrap', 'pre', 'pre-wrap', 'pre-line'): style.white_space = vv
    elif k == 'visibility':
        vv = v.lower()
        if vv in ('visible', 'hidden'): style.visibility = vv
    elif k == 'list-style-type': style.list_style_type = v.lower()
    elif k == 'display':
        vv = v.lower()
        if vv in ('block', 'inline', 'inline-block', 'none', 'list-item',
                  'flex', 'inline-flex', 'grid', 'inline-grid', 'table',
                  'table-row', 'table-cell'):
            if vv in ('inline-flex',): style.display = 'flex'
            elif vv in ('inline-grid',): style.display = 'grid'
            elif vv in ('table', 'table-row', 'table-cell'): style.display = 'block'
            else: style.display = vv
    elif k == 'float':
        vv = v.lower()
        if vv in ('left', 'right', 'none'): style.float = vv
    elif k == 'clear':
        vv = v.lower()
        if vv in ('both', 'left', 'right', 'none'): style.clear = vv
    elif k == 'flex-direction':
        vv = v.lower()
        if vv in ('row', 'row-reverse', 'column', 'column-reverse'): style.flex_direction = vv
    elif k == 'flex-grow':
        try: style.flex_grow = float(v)
        except: pass
    elif k == 'flex-basis':
        n = parse_length(v, style.font_size)
        if n is not None: style.flex_basis = n
        elif v.lower() in ('auto', '0'): style.flex_basis = 0 if v == '0' else None
    elif k == 'flex':
        parts = v.split()
        if parts:
            for p in parts:
                if p.isdigit(): style.flex_grow = float(p)
                else:
                    n = parse_length(p, style.font_size)
                    if n is not None: style.flex_basis = n
    elif k == 'justify-content':
        vv = v.lower()
        if vv in ('flex-start', 'flex-end', 'center', 'space-between',
                  'space-around', 'space-evenly', 'start', 'end'):
            style.justify_content = vv
    elif k == 'align-items':
        vv = v.lower()
        if vv in ('flex-start', 'flex-end', 'center', 'stretch', 'baseline', 'start', 'end'):
            style.align_items = vv
    elif k == 'gap':
        n = parse_length(v.split()[0], style.font_size)
        if n is not None: style.gap = n
    elif k.startswith('margin'): _apply_box(style, 'margin', k, v, style.font_size)
    elif k.startswith('padding'): _apply_box(style, 'padding', k, v, style.font_size)
    elif k.startswith('border'): _apply_border(style, k, v)
    elif k == 'width':
        n = parse_length(v, style.font_size)
        if n is not None: style.width = n
    elif k in ('max-width', 'min-width'):
        n = parse_length(v, style.font_size)
        if n is not None and style.width is None: style.width = n
    elif k == 'height':
        n = parse_length(v, style.font_size)
        if n is not None: style.height = n
    elif k == 'line-height':
        vv = v.strip()
        if vv.endswith(('px', 'pt', 'em', 'rem', '%')):
            n = parse_length(vv, style.font_size)
            if n is not None: style.line_height = n
        else:
            try: style.line_height = float(vv) * style.font_size
            except: pass


def compute_style(dom, parent_style, stylesheet):
    style = ComputedStyle()
    if parent_style is not None:
        inherited = (
            'font_size', 'font_weight', 'font_style', 'font_family',
            'color', 'text_decoration', 'text_align', 'text_indent',
            'white_space', 'visibility', 'list_style_type', 'line_height',
        )
        for name in inherited:
            setattr(style, name, getattr(parent_style, name))

    matched = stylesheet.get_matched(dom)

    inline_props = {}
    if 'style' in dom.attrs:
        for decl in dom.attrs['style'].split(';'):
            if ':' in decl:
                k, v = decl.split(':', 1)
                k = k.strip().lower()
                v = re.sub(r'\s*!important\s*$', '', v.strip(), flags=re.I)
                inline_props[k] = v

    for r in matched:
        if 'font-size' in r.props:
            _apply_prop(style, 'font-size', r.props['font-size'], parent_style)
    if 'font-size' in inline_props:
        _apply_prop(style, 'font-size', inline_props['font-size'], parent_style)

    for r in matched:
        for k, v in r.props.items():
            if k != 'font-size': _apply_prop(style, k, v, parent_style)
    for k, v in inline_props.items():
        if k != 'font-size': _apply_prop(style, k, v, parent_style)

    if 'hidden' in dom.attrs: style.display = 'none'
    if dom.tag == 'a' and 'href' in dom.attrs:
        style.is_link = True; style.link_href = dom.attrs['href']
    return style