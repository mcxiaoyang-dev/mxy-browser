# -*- coding: utf-8 -*-
"""BigJS+ — 支持赋值、DOM 操作（修复死循环，带熔断保护）"""

import re
import math
import random
from dom import DomNode
from css_engine import select_nodes

class Token:
    def __init__(self, type_, val):
        self.type = type_
        self.val = val
    def __repr__(self): return f'{self.type}:{self.val}'

class Lexer:
    def __init__(self, code):
        self.code = code
        self.pos = 0
        self.tokens = []
        self.tokenize()

    def tokenize(self):
        while self.pos < len(self.code):
            ch = self.code[self.pos]
            if ch in ' \t\n\r': self.pos += 1; continue
            operator = next((op for op in (
                '===', '!==', '==', '!=', '<=', '>=', '&&', '||',
                '++', '--', '+=', '-=', '*=', '/=', '=>',
            ) if self.code.startswith(op, self.pos)), None)
            if operator:
                self.tokens.append(Token('PUNC', operator))
                self.pos += len(operator)
                continue
            if ch in '(){}[];,.-+*/%=<>!&|':
                self.tokens.append(Token('PUNC', ch)); self.pos += 1; continue
            if ch in ('"', "'", '`'): self.read_string(ch); continue
            if ch.isdigit(): self.read_number(); continue
            if ch.isalpha() or ch in '_$': self.read_identifier(); continue
            self.pos += 1

    def read_string(self, quote):
        self.pos += 1; start = self.pos
        while self.pos < len(self.code) and self.code[self.pos] != quote:
            if self.code[self.pos] == '\\': self.pos += 2
            else: self.pos += 1
        val = self.code[start:self.pos]
        self.pos += 1
        self.tokens.append(Token('STR', val))

    def read_number(self):
        start = self.pos
        while self.pos < len(self.code) and (self.code[self.pos].isdigit() or self.code[self.pos] == '.'):
            self.pos += 1
        val = self.code[start:self.pos]
        self.tokens.append(Token('NUM', float(val) if '.' in val else int(val)))

    def read_identifier(self):
        start = self.pos
        while self.pos < len(self.code) and (self.code[self.pos].isalnum() or self.code[self.pos] in '_$'):
            self.pos += 1
        self.tokens.append(Token('ID', self.code[start:self.pos]))

class Scope:
    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent
    def get(self, name):
        if name in self.vars: return self.vars[name]
        if self.parent: return self.parent.get(name)
        return ''
    def set(self, name, val): self.vars[name] = val

class JsObject:
    def __init__(self, props=None): self.props = props or {}
    def get(self, name): return self.props.get(name, '')
    def set(self, name, val): self.props[name] = val

class BigJS:
    def __init__(self, document_root=None, output_callback=None):
        self.output = output_callback or (lambda s: None)
        self.document = document_root
        self.global_scope = Scope()
        self.global_scope.set('document', self._make_document_obj())
        self.global_scope.set('console', JsObject({'log': lambda *args: None}))
        self.global_scope.set('Math', JsObject({
            'abs': abs, 'ceil': math.ceil, 'floor': math.floor,
            'max': max, 'min': min, 'round': round, 'random': random.random,
        }))
        self.max_steps = 5000
        self.steps = 0

    def _make_document_obj(self):
        return JsObject({
            'getElementById': lambda id_: self.document.get_element_by_id(id_) if self.document else None,
            'querySelector': self._query_selector,
            'querySelectorAll': lambda sel: (
                select_nodes(self.document, str(sel)) if self.document else []
            ),
            'createElement': lambda tag: DomNode(tag),
            'write': lambda *parts: self.output(''.join(map(str, parts))),
            'writeln': lambda *parts: self.output(''.join(map(str, parts)) + '\n'),
        })

    def _query_selector(self, selector):
        if not self.document:
            return None
        nodes = select_nodes(self.document, str(selector))
        return nodes[0] if nodes else None

    def run(self, code):
        if not code: return
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.S)
        code = re.sub(r'(?<!:)//[^\n]*', '', code)
        lexer = Lexer(code)
        self.pos = 0
        self.tokens = lexer.tokens
        self.steps = 0
        try:
            self._exec_scope(self.global_scope)
        except RuntimeError as e:
            if str(e) == 'TOO_MANY_STEPS':
                pass # 静默终止，防止打印卡顿

    def _peek(self): return self.tokens[self.pos] if self.pos < len(self.tokens) else None
    def _next(self):
        self.steps += 1
        if self.steps > self.max_steps:
            raise RuntimeError('TOO_MANY_STEPS')
        t = self._peek()
        self.pos += 1
        return t

    def _exec_scope(self, scope):
        while self.pos < len(self.tokens):
            t = self._peek()
            if t.type == 'PUNC' and t.val == '}': return
            
            start_pos = self.pos
            self._exec_statement(scope)
            
            # 【死循环终极修复】：如果执行语句没有消耗任何 token，强制跳过
            if self.pos == start_pos:
                self.pos += 1

    def _skip_block(self):
        depth = 1
        while self.pos < len(self.tokens):
            t = self._next()
            if t.type == 'PUNC' and t.val == '{': depth += 1
            if t.type == 'PUNC' and t.val == '}': depth -= 1
            if depth == 0: return

    def _exec_statement(self, scope):
        t = self._peek()
        if not t: return

        if t.type == 'ID' and t.val == 'function':
            self._next(); name = self._next().val
            self._next() # (
            params = []
            while self._peek() and self._peek().val != ')':
                params.append(self._next().val)
                if self._peek() and self._peek().val == ',': self._next()
            self._next() # )
            self._next() # {
            scope.set(name, ('function', params, self.pos))
            self._skip_block(); return

        if t.type == 'ID' and t.val == 'if':
            self._next(); self._next() # (
            cond = self._eval_expr(scope)
            self._next() # )
            self._next() # {
            if cond: self._exec_scope(scope)
            else: self._skip_block()
            if cond and self._peek() and self._peek().val == '}':
                self._next()
            return

        if t.type == 'ID' and t.val in ('for', 'while'):
            self._next(); self._skip_block(); return

        if t.type == 'ID' and t.val in ('var', 'let', 'const'):
            self._next(); name = self._next().val
            if self._peek() and self._peek().val == '=':
                self._next()
                val = self._eval_expr(scope)
                scope.set(name, val)
            return

        if t.type == 'ID' and self.pos + 1 < len(self.tokens):
            op = self.tokens[self.pos + 1].val
            if op in ('++', '--'):
                name = self._next().val
                self._next()
                delta = 1 if op == '++' else -1
                scope.set(name, self._to_number(scope.get(name)) + delta)
                return

        eq_idx = -1
        for i in range(self.pos, min(len(self.tokens), self.pos + 100)):
            if self.tokens[i].type == 'PUNC' and self.tokens[i].val in ('=', '+=', '-=', '*=', '/='):
                eq_idx = i; break
            if self.tokens[i].type == 'PUNC' and self.tokens[i].val in (';', '{', '}'):
                break
            
        if eq_idx != -1:
            left_tokens = self.tokens[self.pos:eq_idx]
            assignment_op = self.tokens[eq_idx].val
            self.pos = eq_idx + 1
            right_val = self._eval_expr(scope)
            
            if left_tokens:
                if assignment_op != '=':
                    old_value = self._eval_expr_from_tokens(left_tokens, scope)
                    if assignment_op == '+=':
                        right_val = (str(old_value) + str(right_val)
                                     if isinstance(old_value, str) or isinstance(right_val, str)
                                     else self._to_number(old_value) + self._to_number(right_val))
                    else:
                        left_number = self._to_number(old_value)
                        right_number = self._to_number(right_val)
                        operation = assignment_op[0]
                        if operation == '-': right_val = left_number - right_number
                        elif operation == '*': right_val = left_number * right_number
                        elif operation == '/': right_val = left_number / right_number if right_number else 0
                if len(left_tokens) == 1 and left_tokens[0].type == 'ID':
                    scope.set(left_tokens[0].val, right_val)
                elif len(left_tokens) >= 3 and left_tokens[-2].val == '.':
                    obj = self._eval_expr_from_tokens(left_tokens[:-2], scope)
                    if hasattr(obj, 'set'):
                        obj.set(left_tokens[-1].val, right_val)
            return

        self._eval_expr(scope)

    def _eval_expr_from_tokens(self, tokens, scope):
        old_tokens = self.tokens
        old_pos = self.pos
        self.tokens = tokens
        self.pos = 0
        res = self._eval_expr(scope)
        self.tokens = old_tokens
        self.pos = old_pos
        return res

    def _eval_expr(self, scope):
        return self._eval_binary(scope, 0)

    def _eval_binary(self, scope, min_precedence):
        t = self._peek()
        if not t: return ''
        
        left = None
        if t.type == 'STR': left = self._unescape(t.val); self._next()
        elif t.type == 'NUM': left = t.val; self._next()
        elif t.type == 'ID':
            self._next()
            if t.val == 'true': left = True
            elif t.val == 'false': left = False
            elif t.val == 'null': left = None
            elif t.val == 'undefined': left = ''
            else:
                left = scope.get(t.val)
        elif t.type == 'PUNC' and t.val in ('!', '-', '+'):
            self._next()
            operand = self._eval_binary(scope, 7)
            if t.val == '!':
                left = not bool(operand)
            elif t.val == '-':
                left = -self._to_number(operand)
            else:
                left = self._to_number(operand)
        elif t.type == 'PUNC' and t.val == '(':
            self._next()
            left = self._eval_expr(scope)
            if self._peek() and self._peek().val == ')':
                self._next()
        elif t.type == 'PUNC' and t.val == '[':
            self._next()
            left = []
            while self._peek() and self._peek().val != ']':
                left.append(self._eval_expr(scope))
                if self._peek() and self._peek().val == ',':
                    self._next()
                else:
                    break
            if self._peek() and self._peek().val == ']':
                self._next()
        else:
            self._next()

        while self._peek():
            token = self._peek()
            if token.val == '.':
                self._next()
                prop = self._next()
                if not prop:
                    return ''
                left = self._get_property(left, prop.val)
                continue
            if token.val == '[':
                self._next()
                key = self._eval_expr(scope)
                if self._peek() and self._peek().val == ']':
                    self._next()
                left = self._get_property(left, str(key))
                continue
            if token.val == '(':
                self._next()
                args = []
                while self._peek() and self._peek().val != ')':
                    args.append(self._eval_expr(scope))
                    if self._peek() and self._peek().val == ',':
                        self._next()
                    else:
                        break
                if self._peek() and self._peek().val == ')':
                    self._next()
                left = left(*args) if callable(left) else ''
                continue

            op = self._peek().val
            precedence = {
                '||': 1, '&&': 2, '==': 3, '!=': 3, '===': 3,
                '!==': 3, '<': 4, '>': 4, '<=': 4, '>=': 4,
                '+': 5, '-': 5, '*': 6, '/': 6, '%': 6,
            }.get(op, -1)
            if token.type != 'PUNC' or precedence < min_precedence:
                break
            self._next()
            right = self._eval_binary(scope, precedence + 1)
            if op == '+':
                if isinstance(left, str) or isinstance(right, str): left = str(left) + str(right)
                else: left = self._to_number(left) + self._to_number(right)
            elif op == '-':
                left = self._to_number(left) - self._to_number(right)
            elif op == '*':
                left = self._to_number(left) * self._to_number(right)
            elif op == '/':
                divisor = self._to_number(right)
                left = self._to_number(left) / divisor if divisor else 0
            elif op == '%':
                divisor = self._to_number(right)
                left = self._to_number(left) % divisor if divisor else 0
            elif op == '==': left = (left == right or str(left) == str(right))
            elif op == '===': left = (left == right)
            elif op == '!=': left = (str(left) != str(right))
            elif op == '!==': left = (left != right)
            elif op == '<': left = self._compare(left, right, '<')
            elif op == '>': left = self._compare(left, right, '>')
            elif op == '<=': left = self._compare(left, right, '<=')
            elif op == '>=': left = self._compare(left, right, '>=')
            elif op == '&&': left = bool(left) and bool(right)
            elif op == '||': left = bool(left) or bool(right)
            
        return left

    @staticmethod
    def _to_number(value):
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0
        return int(number) if number.is_integer() else number

    @staticmethod
    def _compare(left, right, operator):
        if isinstance(left, str) and isinstance(right, str):
            a, b = left, right
        else:
            a = BigJS._to_number(left)
            b = BigJS._to_number(right)
        if operator == '<': return a < b
        if operator == '>': return a > b
        if operator == '<=': return a <= b
        return a >= b

    @staticmethod
    def _get_property(value, name):
        if hasattr(value, 'get'):
            return value.get(name)
        if isinstance(value, str):
            if name == 'length': return len(value)
            if name == 'toUpperCase': return value.upper
            if name == 'toLowerCase': return value.lower
            if name == 'includes': return value.__contains__
            if name == 'indexOf': return value.find
        if isinstance(value, (list, tuple)):
            if name == 'length': return len(value)
            if name == 'join': return lambda sep=',': str(sep).join(map(str, value))
        if isinstance(value, dict):
            return value.get(name, '')
        if name.isdigit() and isinstance(value, (list, tuple, str)):
            index = int(name)
            return value[index] if index < len(value) else ''
        return ''

    def _unescape(self, s):
        return s.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace("\\'", "'")