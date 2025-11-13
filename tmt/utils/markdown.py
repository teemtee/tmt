"""
Markdown to HTML conversion utilities.

Simple markdown-to-HTML converter for basic formatting in reports and exports.
"""

import html
import re
from typing import Optional


def markdown_to_html(text: str, escape: bool = False) -> str:
    """
    Convert simple markdown syntax to HTML.
    
    This function converts basic markdown elements to HTML for display
    in reporting systems like Polarion, ReportPortal, etc.
    
    Supported markdown syntax:
    - Headers: ## H2, ### H3
    - Bold text: **text**
    - Inline code: `code`
    - Numbered lists: 1. item, 2. item
    - Bullet lists: - item, * item
    - Code blocks: indented with 4 spaces or tab
    
    Args:
        text: Markdown text to convert
        escape: Whether to HTML-escape the text first (default: False)
        
    Returns:
        HTML string with markdown converted to HTML tags
        
    Example:
        >>> markdown_to_html("## Header\\n\\n**Bold** text with `code`")
        '<h2>Header</h2><strong>Bold</strong> text with <code>code</code>'
    """
    if not text:
        return ''
    
    # HTML escape if requested
    if escape:
        text = html.escape(text)
    
    # Process block-level elements line by line
    lines = text.split('\n')
    html_lines = []
    in_code_block = False
    in_list = False
    list_type: Optional[str] = None  # 'ul' or 'ol'
    
    for line in lines:
        # Code blocks (indented with 4 spaces or tab)
        if line.startswith('    ') or line.startswith('\t'):
            if in_list:
                html_lines.append(f'</{list_type}>')
                in_list = False
                list_type = None
            if not in_code_block:
                html_lines.append('<pre><code>')
                in_code_block = True
            html_lines.append(line)
            continue
        
        if in_code_block:
            html_lines.append('</code></pre>')
            in_code_block = False
        
        # Empty lines - close lists
        if not line.strip():
            if in_list:
                html_lines.append(f'</{list_type}>')
                in_list = False
                list_type = None
            html_lines.append('')
            continue
        
        # Headers (### H3, ## H2)
        if line.startswith('### '):
            if in_list:
                html_lines.append(f'</{list_type}>')
                in_list = False
                list_type = None
            html_lines.append(f'<h3>{line[4:].strip()}</h3>')
            continue
        
        if line.startswith('## '):
            if in_list:
                html_lines.append(f'</{list_type}>')
                in_list = False
                list_type = None
            html_lines.append(f'<h2>{line[3:].strip()}</h2>')
            continue
        
        # Numbered lists (1. item)
        numbered_match = re.match(r'^(\d+)\.\s+(.+)$', line)
        if numbered_match:
            content = numbered_match.group(2)
            if not in_list or list_type != 'ol':
                if in_list:
                    html_lines.append(f'</{list_type}>')
                html_lines.append('<ol>')
                list_type = 'ol'
                in_list = True
            html_lines.append(f'<li>{content}</li>')
            continue
        
        # Bullet lists (- item or * item)
        if line.startswith('- ') or line.startswith('* '):
            content = line[2:].strip()
            if not in_list or list_type != 'ul':
                if in_list:
                    html_lines.append(f'</{list_type}>')
                html_lines.append('<ul>')
                list_type = 'ul'
                in_list = True
            html_lines.append(f'<li>{content}</li>')
            continue
        
        # Regular line - close list if open
        if in_list:
            html_lines.append(f'</{list_type}>')
            in_list = False
            list_type = None
        
        html_lines.append(line)
    
    # Close any open blocks
    if in_code_block:
        html_lines.append('</code></pre>')
    if in_list:
        html_lines.append(f'</{list_type}>')
    
    # Join and process inline markdown
    html_text = '\n'.join(html_lines)
    
    # Bold: **text** -> <strong>text</strong>
    html_text = re.sub(r'\*\*([^\*]+)\*\*', r'<strong>\1</strong>', html_text)
    
    # Inline code: `code` -> <code>code</code>
    html_text = re.sub(r'`([^`]+)`', r'<code>\1</code>', html_text)
    
    # Convert newlines to <br/> except around block elements
    block_tags = ['h1', 'h2', 'h3', 'h4', 'ul', 'ol', 'pre', 'li']
    lines = html_text.split('\n')
    result_lines = []
    
    for i, line in enumerate(lines):
        is_block = any(
            line.rstrip().endswith(f'</{tag}>') or
            line.lstrip().startswith(f'<{tag}>') or
            line.lstrip().startswith(f'<{tag} ')
            for tag in block_tags
        )
        
        result_lines.append(line)
        
        # Add <br/> between regular text lines
        if i < len(lines) - 1 and line.strip() and not is_block:
            next_line = lines[i + 1]
            next_is_block = any(
                next_line.lstrip().startswith(f'<{tag}>') or
                next_line.lstrip().startswith(f'<{tag} ')
                for tag in block_tags
            )
            if next_line.strip() and not next_is_block:
                result_lines.append('<br/>')
    
    return ''.join(result_lines)


def sanitize_for_xml(text: str) -> str:
    """
    Remove invalid XML 1.0 characters from text.
    
    XML 1.0 only allows specific character ranges. This removes or replaces
    characters that would cause XML parsing errors.
    
    Valid: tab (0x9), newline (0xA), carriage return (0xD),
           #x20-#xD7FF, #xE000-#xFFFD, #x10000-#x10FFFF
    
    Args:
        text: Text to sanitize
        
    Returns:
        Text with invalid XML characters removed
    """
    if not text:
        return ''
    
    valid_chars = []
    for char in text:
        code = ord(char)
        if (code in (0x9, 0xA, 0xD) or
            0x20 <= code <= 0xD7FF or
            0xE000 <= code <= 0xFFFD or
            0x10000 <= code <= 0x10FFFF):
            valid_chars.append(char)
        elif code != 0x0:  # Skip null bytes, replace other invalid with space
            valid_chars.append(' ')
    
    return ''.join(valid_chars)

