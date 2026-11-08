#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MXY 浏览器 — 入口"""

import tkinter as tk
from app import App

if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()