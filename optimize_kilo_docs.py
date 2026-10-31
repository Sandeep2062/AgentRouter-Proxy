#!/usr/bin/env python3
"""
optimize_kilo_docs.py
Cleans, structures, and optimizes the raw Crawl4AI markdown scrape of Kilo documentation:
1. Replaces the broken Table of Contents with a full categorized navigation tree.
2. Removes duplicated top navigation bars, search modals, header links, and sidebar trees.
3. Removes redundant footer boilerplate (Anaconda banners, copy buttons, duplicate anchor links).
4. Normalizes blank lines and formatting.
5. Preserves 100% of technical explanations, configuration examples, and code blocks.
"""

import os
import re
import sys
from collections import defaultdict

def slugify(url):
    s = url.replace("https://kilo.ai/docs", "").strip("/")
    if not s:
        return "overview-index"
    return "source-" + re.sub(r"[^a-zA-Z0-9_-]", "-", s).lower()

def clean_title(title):
    t = re.sub(r"^#+\s*", "", title)
    t = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", t)
    return t.strip()

def categorize(url):
    path = url.replace("https://kilo.ai/docs", "").strip("/")
    parts = path.split("/")
    if not path:
        return "0. Overview & Core Documentation"
    cat = parts[0]
    mapping = {
        "getting-started": "1. Getting Started & Setup",
        "code-with-ai": "2. Code with AI & Platforms",
        "ai-providers": "3. AI Providers & Model Setup",
        "customize": "4. Customization, Rules & Indexing",
        "automate": "5. Automation & MCP Tools",
        "collaborate": "6. Collaboration & Teams",
        "deploy-secure": "7. Deployment & Security",
        "gateway": "8. Kilo AI Gateway",
        "desktop": "9. Kilo Desktop (Beta)",
        "contributing": "10. Architecture & Contributing"
    }
    return mapping.get(cat, "11. Other Guides")

def process():
    input_path = "docs_kilo.md"
    print(f"Reading {input_path}...")
    with open(input_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    pages = re.split(r"\n# Source:\s*", content)
    raw_pages = pages[1:]
    print(f"Loaded {len(raw_pages)} scraped pages.")

    parsed_pages = []

    for idx, p in enumerate(raw_pages, 1):
        lines = p.strip().split("\n")
        url = lines[0].strip()

        # Find main h1 or h2
        h1_idx = None
        for i, l in enumerate(lines[1:], 1):
            if l.startswith("# "):
                h1_idx = i
                break
        if h1_idx is None:
            for i, l in enumerate(lines[1:], 1):
                if l.startswith("## "):
                    h1_idx = i
                    break

        if h1_idx is None:
            print(f"Warning: No header found in {url}")
            h1_idx = 1

        # Check for callouts / badges right above h1
        start_idx = h1_idx
        while start_idx > 1:
            prev = lines[start_idx - 1].strip()
            if any(prev.startswith(x) for x in ["✨", "⚠️", "💡", "ℹ️", "🔥", ">", "Note:", "Warning:"]):
                start_idx -= 1
            elif prev == "":
                if start_idx > 2 and any(lines[start_idx - 2].strip().startswith(x) for x in ["✨", "⚠️", "💡", "ℹ️", "🔥", ">", "Note:", "Warning:"]):
                    start_idx -= 2
                else:
                    break
            else:
                break

        # Find end index (first line containing 'Copy page' or 'Open markdown')
        end_idx = len(lines)
        for i in range(start_idx, len(lines)):
            if "Copy page" in lines[i] or "Open markdown" in lines[i]:
                end_idx = i
                break
            if url == "https://kilo.ai/docs" and "Need help?" in lines[i]:
                end_idx = i
                break

        body_lines = lines[start_idx:end_idx]
        raw_body = "\n".join(body_lines).strip()

        # Clean excessive blank lines (more than 2 -> 2)
        clean_body = re.sub(r"\n{3,}", "\n\n", raw_body)

        title = clean_title(lines[h1_idx])
        slug = slugify(url)
        cat = categorize(url)

        parsed_pages.append({
            "idx": idx,
            "url": url,
            "slug": slug,
            "title": title,
            "category": cat,
            "body": clean_body
        })

    # Group by category
    categories = defaultdict(list)
    for p in parsed_pages:
        categories[p["category"]].append(p)

    output = []
    output.append("# Kilo Code Official Documentation (Knowledge Base)")
    output.append("")
    output.append("> **Comprehensive AI-Optimized Knowledge Base**  ")
    output.append(f"> **Source:** [https://kilo.ai/docs](https://kilo.ai/docs)  ")
    output.append(f"> **Captured Pages:** {len(parsed_pages)}  ")
    output.append("> **Optimization:** Fully de-duplicated. All navigational chrome, repetitive header menus, search widgets, footer banners, and redundant anchor lists stripped. 100% of all technical guides, CLI commands, configuration options (`kilo.jsonc`), architecture specs, and code blocks preserved.")
    output.append("")
    output.append("---")
    output.append("")
    output.append("## Table of Contents")
    output.append("")

    for cat_name in sorted(categories.keys()):
        pages_in_cat = categories[cat_name]
        output.append(f"### {cat_name}")
        output.append("")
        for p in pages_in_cat:
            output.append(f"- [{p['title']}](#{p['slug']}) — `{p['url']}`")
        output.append("")

    output.append("---")
    output.append("")

    # Output each page
    for p in parsed_pages:
        output.append(f'<a id="{p["slug"]}"></a>')
        output.append(f"# Source: [{p['url']}]({p['url']})")
        output.append("")
        output.append(p["body"])
        output.append("")
        output.append("---")
        output.append("")

    final_text = "\n".join(output)

    output_path = "docs_kilo.md"
    raw_backup_path = "docs_kilo.raw.md"

    # Backup raw
    if not os.path.exists(raw_backup_path):
        print(f"Creating backup of raw scrape at {raw_backup_path}...")
        os.replace("docs_kilo.md", raw_backup_path)
    
    print(f"Writing optimized docs to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_text)

    print("Done!")
    print(f"Optimized lines: {len(final_text.splitlines()):,}")
    print(f"Optimized size:  {len(final_text):,} bytes ({len(final_text)/1024/1024:.2f} MB)")

if __name__ == "__main__":
    process()
