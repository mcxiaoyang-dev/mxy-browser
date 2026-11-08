# -*- coding: utf-8 -*-
"""字体缓存与测量"""

import tkinter.font as tkfont


class FontManager:
    def __init__(self):
        self.cache = {}

    def get_font(self, style):
        key = (style.font_family, style.font_size, style.font_weight, style.font_style)
        if key in self.cache:
            return self.cache[key]
        f = tkfont.Font(
            family=style.font_family,
            size=-int(style.font_size),
            weight=style.font_weight,
            slant='italic' if style.font_style == 'italic' else 'roman',
        )
        self.cache[key] = f
        return f