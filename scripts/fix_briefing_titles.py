#!/usr/bin/env python3
"""
Fix briefing file titles to standardized format.

Standard format:
- Regular: # 全球新闻简报 · YYYY年M月D日
- Deep: # 全球新闻简报 · YYYY年M月D日（深度版）

Issues fixed:
1. "财经" → "新闻" (content covers more than finance)
2. "（深入版）" → "（深度版）" (consistent with guide naming)
"""

import os
import re
from pathlib import Path
from datetime import datetime


def extract_date_from_filename(filename: str) -> tuple[str, bool] | None:
    """
    Extract date from filename like briefing_20260606.md or briefing_20260606_deep.md.
    Returns (date_str, is_deep) or None if no match.
    """
    # Match patterns like briefing_20260606.md, briefing_20260606_v2.md, briefing_20260606_deep.md
    match = re.search(r'briefing_(\d{8})(?:_(\w+))?', filename)
    if not match:
        return None
    
    date_str = match.group(1)
    suffix = match.group(2) or ''
    
    # Parse date
    try:
        dt = datetime.strptime(date_str, '%Y%m%d')
        formatted_date = f"{dt.year}年{dt.month}月{dt.day}日"
    except ValueError:
        return None
    
    # Determine if deep version (only _deep and _v3 suffixes indicate deep version)
    is_deep = suffix in ('deep', 'v3')
    
    return formatted_date, is_deep


def fix_title(filename: str, first_line: str) -> str | None:
    """
    Fix the title line if it matches known patterns.
    Returns the corrected title line, or None if no fix needed.
    """
    date_info = extract_date_from_filename(filename)
    if not date_info:
        return None
    
    date_str, is_deep = date_info
    
    # Check if first line is a markdown title
    if not first_line.startswith('#'):
        return None
    
    # Build correct title
    suffix = '（深度版）' if is_deep else ''
    correct_title = f"# 全球新闻简报 · {date_str}{suffix}"
    
    # Check if current title needs fixing
    # Match patterns like: # 全球财经简报 · 2026年6月6日（深入版）
    old_pattern = r'^#\s+全球(?:财经|新闻)简报\s+·\s+\d{4}年\d+月\d+日(?:（[^）]+）)?\s*$'
    
    if re.match(old_pattern, first_line):
        if first_line.strip() != correct_title:
            return correct_title
    
    return None


def process_file(filepath: Path) -> bool:
    """
    Process a single briefing file and fix its title if needed.
    Returns True if file was modified.
    """
    try:
        content = filepath.read_text(encoding='utf-8')
    except Exception as e:
        print(f"  ❌ Error reading {filepath}: {e}")
        return False
    
    lines = content.split('\n')
    if not lines:
        return False
    
    first_line = lines[0]
    new_title = fix_title(filepath.name, first_line)
    
    if new_title:
        lines[0] = new_title
        new_content = '\n'.join(lines)
        
        try:
            filepath.write_text(new_content, encoding='utf-8')
            print(f"  ✅ Fixed: {filepath.name}")
            print(f"     Old: {first_line.strip()}")
            print(f"     New: {new_title}")
            return True
        except Exception as e:
            print(f"  ❌ Error writing {filepath}: {e}")
            return False
    
    return False


def find_briefing_files(base_dir: Path) -> list[Path]:
    """Find all briefing markdown files recursively."""
    files = []
    
    for root, _, filenames in os.walk(base_dir):
        for fname in filenames:
            if fname.startswith('briefing_') and fname.endswith('.md'):
                files.append(Path(root) / fname)
    
    return sorted(files)


def main():
    project_dir = Path(__file__).parent.parent
    
    print(f"Scanning for briefing files in {project_dir}...")
    files = find_briefing_files(project_dir)
    
    if not files:
        print("No briefing files found.")
        return
    
    print(f"Found {len(files)} briefing file(s):\n")
    
    modified_count = 0
    
    for filepath in files:
        if process_file(filepath):
            modified_count += 1
            print()
    
    print(f"Done. Modified {modified_count} file(s).")


if __name__ == '__main__':
    main()
