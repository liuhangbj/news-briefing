#!/usr/bin/env python3
"""Markdown 到 HTML 转换器（新闻简报专用）"""
import re

def markdown_to_html(text):
    """将简报 Markdown 转换为 HTML"""
    lines = text.split('\n')
    html_parts = []
    in_list = False
    in_paragraph = False
    list_type = None
    in_summary = False
    summary_lines = []
    
    def flush_list():
        nonlocal in_list, list_type
        if in_list:
            if list_type == 'ul':
                html_parts.append('</ul>')
            elif list_type == 'ol':
                html_parts.append('</ol>')
            in_list = False
            list_type = None
    
    def flush_para():
        nonlocal in_paragraph
        if in_paragraph:
            html_parts.append('</p>')
            in_paragraph = False
    
    def flush_summary():
        nonlocal in_summary, summary_lines
        if in_summary and summary_lines:
            paras = []
            cur = []
            for line in summary_lines:
                if line:
                    cur.append(line)
                else:
                    if cur:
                        paras.append(' '.join(cur))
                        cur = []
            if cur:
                paras.append(' '.join(cur))
            if paras:
                html_parts.append('<blockquote>')
                for para in paras:
                    html_parts.append(f'<p>{para}</p>')
                html_parts.append('</blockquote>')
            summary_lines = []
            in_summary = False
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        if not stripped:
            if in_summary:
                summary_lines.append('')
            else:
                flush_para()
                flush_list()
            html_parts.append('')
            i += 1
            continue
        
        if stripped.startswith('# '):
            flush_summary()
            flush_para()
            flush_list()
            content = inline_format(stripped[2:])
            html_parts.append(f'<h1>{content}</h1>')
            i += 1
            continue
        elif stripped.startswith('## '):
            flush_summary()
            flush_para()
            flush_list()
            content = inline_format(stripped[3:])
            html_parts.append(f'<h2>{content}</h2>')
            i += 1
            continue
        elif stripped.startswith('### '):
            flush_summary()
            flush_para()
            flush_list()
            content = inline_format(stripped[4:])
            html_parts.append(f'<h3>{content}</h3>')
            i += 1
            continue
        elif stripped.startswith('#### '):
            flush_summary()
            flush_para()
            flush_list()
            content = inline_format(stripped[5:])
            html_parts.append(f'<h4>{content}</h4>')
            i += 1
            continue
        
        if stripped == '---':
            flush_summary()
            flush_para()
            flush_list()
            html_parts.append('<hr>')
            i += 1
            continue
        
        if re.match(r'\*\*综述\*\*\s*[:：]', stripped):
            flush_para()
            flush_list()
            content = stripped.replace('**综述**', '综述').replace('**', '')
            content = inline_format(content)
            html_parts.append(f'<p class="summary-label"><strong>{content}</strong></p>')
            in_summary = True
            summary_lines = []
            i += 1
            continue
        
        if re.match(r'\*\*相关阅读\*\*\s*[:：]', stripped):
            flush_summary()
            flush_para()
            flush_list()
            content = stripped.replace('**相关阅读**', '相关阅读').replace('**', '')
            content = inline_format(content)
            html_parts.append(f'<p class="reading-label"><strong>{content}</strong></p>')
            i += 1
            continue
        
        ordered_match = re.match(r'^(\d+)\.\s+(.+)$', stripped)
        if ordered_match:
            flush_summary()
            flush_para()
            if not in_list or list_type != 'ol':
                flush_list()
                html_parts.append('<ol>')
                in_list = True
                list_type = 'ol'
            content = inline_format(ordered_match.group(2))
            j = i + 1
            sub_items = []
            while j < len(lines) and lines[j].strip().startswith('- '):
                sub_items.append(inline_format(lines[j].strip()[2:]))
                j += 1
            if sub_items:
                for sub in sub_items:
                    content += f'<br>{sub}'
                i = j
            html_parts.append(f'<li>{content}</li>')
            continue
        
        if stripped.startswith('- ') or stripped.startswith('* '):
            flush_summary()
            flush_para()
            if not in_list or list_type != 'ul':
                flush_list()
                html_parts.append('<ul>')
                in_list = True
                list_type = 'ul'
            content = inline_format(stripped[2:])
            html_parts.append(f'<li>{content}</li>')
            i += 1
            continue
        
        if stripped.startswith('> '):
            flush_summary()
            flush_para()
            flush_list()
            content = inline_format(stripped[2:])
            html_parts.append(f'<blockquote><p>{content}</p></blockquote>')
            i += 1
            continue
        
        if in_summary:
            content = inline_format(stripped)
            if line.rstrip().endswith('  '):
                content += '<br>'
            summary_lines.append(content)
            i += 1
            continue
        
        if not in_paragraph:
            html_parts.append('<p>')
            in_paragraph = True
        content = inline_format(stripped)
        if line.rstrip().endswith('  '):
            content += '<br>'
        elif re.match(r'\*\*[^*]+\*\*\s*[:：]', stripped):
            content += '<br>'
        html_parts.append(content)
        i += 1
    
    flush_summary()
    flush_para()
    flush_list()
    
    body = '\n'.join(html_parts)
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>全球新闻简报</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.8; color: #333; padding: 20px; }}

h1 {{ font-size: 24px; font-weight: 700; border-bottom: 2px solid #333; padding-bottom: 10px; margin-top: 0; color: #333; }}
h2 {{ font-size: 20px; font-weight: 700; margin-top: 30px; margin-bottom: 15px; color: #c41e3a; border-left: 4px solid #c41e3a; padding-left: 12px; }}
h3 {{ font-size: 17px; font-weight: 700; margin-top: 25px; margin-bottom: 12px; color: #c41e3a; border-left: 3px solid #c41e3a; padding-left: 10px; margin-left: 15px; }}
h4 {{ font-size: 15px; font-weight: 700; margin-top: 18px; margin-bottom: 8px; color: #c41e3a; border-left: 2px solid #c41e3a; padding-left: 8px; margin-left: 30px; }}

a {{ color: #1a73e8; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
hr {{ border: none; border-top: 1px solid #ddd; margin: 25px 0; }}

blockquote {{ background: #f8f9fa; border-left: 3px solid #e0e0e0; padding: 15px 20px; margin: 10px 0 10px 30px; }}
blockquote p {{ margin: 0 0 10px; }}
blockquote p:last-child {{ margin-bottom: 0; }}

ul, ol {{ margin: 10px 0; padding-left: 20px; margin-left: 30px; }}
li {{ margin-bottom: 6px; }}

p {{ margin: 10px 0; }}
strong {{ color: #c41e3a; }}

.summary-label {{ padding-left: 20px; margin-left: 15px; }}
.summary-label strong {{ color: #e53935; }}
.reading-label {{ padding-left: 20px; margin-left: 15px; }}
.reading-label strong {{ color: #e53935; }}
</style>
</head>
<body>

{body}
</body>
</html>'''
    
    return html


def inline_format(text):
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'&lt;(https?://[^&]+)&gt;', r'<a href="\1">\1</a>', text)
    return text
