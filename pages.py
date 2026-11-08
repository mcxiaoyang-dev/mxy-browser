# -*- coding: utf-8 -*-
"""内置页面"""

def build_about_html():
    return """<!DOCTYPE html>
<html>
<head>
<title>关于 — MXY 浏览器</title>
<style>
h1 { color: #1a1a1a; font-size: 26px; }
h2 { color: #333333; font-size: 15px; }
p { color: #444444; font-size: 12px; }
li { color: #444444; font-size: 12px; }
a { color: #0066cc; text-decoration: underline; }
code { color: #cc0000; }
.lead { color: #666666; font-size: 13px; }
.meta { color: #999999; font-size: 10px; }
</style>
</head>
<body>
<h1>MXY 浏览器</h1>
<p class="lead">从零手写的实验性浏览器。不依赖 Blink、WebKit、Gecko。</p>
<hr>

<h2>搜索</h2>
<form action="https://cn.bing.com/search" method="get">
<p>Bing 搜索：
<input type="text" name="q" placeholder="输入关键词" size="40">
<input type="submit" value="Bing 搜索">
</p>
</form>

<form action="https://www.baidu.com/s" method="get">
<p>百度搜索：
<input type="text" name="wd" placeholder="输入关键词" size="40">
<input type="submit" value="百度一下">
</p>
</form>

<hr>

<h2>能做什么</h2>
<ul>
<li>抓取 HTTP / HTTPS 页面，自动解压 gzip / deflate</li>
<li>解析 HTML，构建 DOM，支持常见 HTML5 语义标签和省略闭合标签</li>
<li>解析 CSS（属性、组合与结构伪类选择器，盒模型、文字样式、Flex / Float）</li>
<li>手动画布渲染：文字、边框、背景、下划线、链接热区、图片（PNG/GIF）</li>
<li>运行受限的内联 JavaScript：变量、基本表达式、条件、Math、DOM 查询和 document.write</li>
<li>真实输入框：点击后浮出原生输入控件，Enter 触发搜索</li>
<li>框选文本并 Ctrl+C 复制</li>
<li>自动识别普通词汇并走 Bing 搜索，识别域名直接访问</li>
<li>Ctrl + 点击链接可以调起系统浏览器打开</li>
</ul>

<h2>试试这些</h2>
<ul>
<li><a href="mxy:js">JS 测试页</a></li>
<li><a href="mxy:css">CSS 测试页</a></li>
<li><a href="https://cn.bing.com">Bing 主页</a></li>
<li><a href="https://www.python.org">python.org</a></li>
<li><a href="https://www.gnu.org">GNU 项目</a></li>
<li><a href="http://info.cern.ch">世界第一个网页（CERN）</a></li>
</ul>

<h2>不支持</h2>
<ul>
<li>JPEG / WebP 图片（纯标准库限制，只能显示 PNG/GIF 或占位符）</li>
<li>完整 JavaScript（函数、循环、事件、异步和现代框架仍不支持）</li>
<li>外部脚本</li>
<li>CSS Grid、媒体查询、表格布局、绝对定位等复杂布局</li>
<li>Cookie、登录态、POST 请求（表单都走 GET）</li>
</ul>
<p class="meta">React / Vue 这类 SPA 站点通常需要完整 JavaScript 引擎，页面内容可能无法显示。</p>

<hr>
<h2>使用</h2>
<p>地址栏输入网址回车。输入普通词汇会直接搜索。输入 <code>mxy:</code> 回本页。</p>
<hr>
<p class="meta">MXY 浏览器 5.0 · 纯 Python 标准库 · <a href="mxy:">首页</a></p>
</body>
</html>"""

def build_js_test_html():
    return """<!DOCTYPE html>
<html>
<head><title>MiniJS 测试 — MXY 浏览器</title></head>
<style>
h1 { color: #1a1a1a; font-size: 24px; }
h2 { color: #333333; font-size: 15px; }
p  { color: #444444; font-size: 12px; }
code { color: #cc0000; }
</style>
<body>
<h1>MiniJS 测试页</h1>
<p>下面几段内容由 &lt;script&gt; 里的 document.write 生成。</p>
<hr>

<h2>测试 1：字符串拼接</h2>
<script>
var name = "MXY";
var version = "5.0";
document.write("<p><b>Hello, " + name + " " + version + "!</b></p>");
</script>

<h2>测试 2：算术和比较</h2>
<script>
var a = 3;
var b = 4;
document.write("<p>a + b = " + (a + b) + "</p>");
document.write("<p>a * b = " + (a * b) + "</p>");
if (a < b) {
  document.write("<p>a &lt; b 为真</p>");
}
</script>

<h2>测试 3：+= 和 ++</h2>
<script>
var n = 0;
n = n + 5;
n += 3;
n++;
document.write("<p>n 最终 = " + n + "</p>");
</script>

<h2>测试 4：Math 和字符串方法</h2>
<script>
var r = Math.floor(Math.random() * 100);
document.write("<p>随机整数: " + r + "</p>");
var s = "hello world";
document.write("<p>转大写: " + s.toUpperCase() + "</p>");
document.write("<p>长度: " + s.length + "</p>");
</script>

<h2>测试 5：document.title</h2>
<script>
document.title = "MXY 测试页 - 已改标题";
</script>
<p>窗口标题已经被脚本改过了。</p>

<hr>
<p>下面是纯 HTML，和上面的脚本输出并列显示。</p>
<script>
var msg = "脚本 6";
document.write("<p>【" + msg + "】</p>");
</script>
<p>结束。<a href="mxy:">回首页</a></p>
</body>
</html>"""

def build_css_test_html():
    return """<!DOCTYPE html>
<html>
<head>
<title>CSS 测试 — MXY 浏览器</title>
<style>
h1 { color: #222222; font-size: 24px; }
h2 { color: #444444; font-size: 16px; }
p { color: #333333; font-size: 13px; }
* { font-family: Helvetica; }
.box { background-color: #f0f8ff; padding: 8px; border: 1px solid #0066cc; margin: 4px 0; }
.warn { color: #cc0000; font-weight: bold; }
a { color: #0066cc; text-decoration: underline; }
.centered { text-align: center; }
.indent { text-indent: 30px; }
.mono { font-family: Courier; white-space: pre; }
.hidden { visibility: hidden; }
ul { padding-left: 30px; }
li { color: #444444; font-size: 13px; }
</style>
</head>
<body>
<h1>CSS 测试页</h1>
<p>每一段测试一种 CSS 特性。</p>
<hr>

<h2>1. class 选择器 + 背景 + 边框</h2>
<div class="box">这是一个 .box 容器，应该有浅蓝背景和蓝色边框。</div>

<h2>2. 复合选择器</h2>
<p>下面这行应该是红色加粗：</p>
<p class="warn">这是红色加粗文字。</p>

<h2>3. text-align: center</h2>
<p class="centered">这段文字应该居中显示。</p>

<h2>4. text-indent</h2>
<p class="indent">这段首行应该有 30px 缩进。换行后的第二行和后面几行应该顶格显示，不会缩进。再写长一点好看到换行效果。</p>

<h2>5. white-space: pre（等宽字体）</h2>
<div class="mono">line 1
  line 2 indented
    line 3 more indented</div>

<h2>6. visibility: hidden</h2>
<p>下面这行看不见，但它占位置：</p>
<p class="hidden">这一行是隐藏的。</p>
<p>上面应该有一段空白。</p>

<h2>7. 表单 + 输入框</h2>
<form action="https://cn.bing.com/search" method="get">
<p>Bing 搜索：
<input type="text" name="q" placeholder="输入关键词" size="25">
<input type="submit" value="搜索">
</p>
</form>

<h2>8. list-style-type: none</h2>
<ul>
<li>带 bullet 的项</li>
</ul>
<ul style="list-style-type: none;">
<li>没有 bullet 的项</li>
</ul>

<h2>9. 链接</h2>
<p>访问 <a href="https://www.python.org">python.org</a> 或 <a href="mxy:">回首页</a>。</p>

<hr>
<p>结束。<a href="mxy:">返回首页</a></p>
</body>
</html>"""