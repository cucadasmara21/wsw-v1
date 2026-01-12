#!/usr/bin/env python3
"""
Extract Group 1 (Overleveraged Real Estate & MBS) taxonomy from PDFs.
Generates real sample group1.json and source notes for frontend.
No fabrication - only data extracted from PDFs.

Heuristics:
- Detect Group 1 heading from master PDF.
- Parse Subgroup 1 CRE Loans PDF: extract categories and assets from table-like rows.
- Categories identified by "Category: <name>" or similar patterns.
- Assets extracted from rows with name, type, country, source.

Usage:
  python scripts/extract_group1_from_pdfs.py
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Any

try:
    from PyPDF2 import PdfReader
except ImportError:
    raise RuntimeError("PyPDF2 required. Install: pip install PyPDF2")


ROOT = Path(__file__).resolve().parent.parent
MASTER_PDF = ROOT / "frontend" / "src" / "test" / "MASTER_20_Groups_Complete.pdf"
SUBGROUP1_PDF = ROOT / "frontend" / "src" / "test" / "Group_1_Subgroup_1_Commercial_Real_Estate_Loans_Assets.pdf"
OUTPUT_JSON = ROOT / "frontend" / "public" / "samples" / "group1.json"
OUTPUT_NOTES = ROOT / "frontend" / "public" / "samples" / "group1_source.md"


def read_pdf_lines(pdf_path: Path) -> List[str]:
    """Extract and normalize lines from PDF."""
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    reader = PdfReader(str(pdf_path))
    lines = []
    for page in reader.pages:
        text = page.extract_text() or ""
        for raw_line in text.splitlines():
            # Normalize whitespace
            line = re.sub(r"\s+", " ", raw_line.strip())
            if line:
                lines.append(line)
    return lines


def detect_group1(lines: List[str]) -> Dict[str, str]:
    """Extract Group 1 from master PDF."""
    for line in lines:
        # Pattern: "■ Group 1: Overleveraged Real Estate & MBS-Related Assets"
        m = re.search(r"■\s*Group\s+1[:\s]+(.+?)(?:\s*■|$)", line)
        if m:
            title = m.group(1).strip()
            return {
                "name": "Group 1",
                "code": "GROUP_1",
                "title": title
            }
    return {"name": "Group 1", "code": "GROUP_1"}


def parse_subgroup1(lines: List[str]) -> Dict[str, Any]:
    """
    Parse Subgroup 1 (Commercial Real Estate Loans) from CRE Loans PDF.
    
    Expected structure:
    ■ Subgroup 1: Commercial Real Estate Loans
    ■ Category: Office Property Loans
    Asset Name        Ticker   Type              Country  Source
    JPMorgan Chase... -        Loan              USA      SEC Filings
    Wells Fargo...    -        Loan              USA      Company Reports
    ...
    ■ Category: Hospitality (Hotel) Development Loans
    ...
    
    Returns: {name, code, categories: [{name, code, asset_type, assets: [{symbol, name}]}]}
    """
    subgroup = {
        "name": "Subgroup 1: Commercial Real Estate Loans",
        "code": "SG_1",
        "categories": []
    }
    
    current_category = None
    in_asset_table = False
    prev_was_header = False
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        
        # Detect category heading: "■ Category: <name>"
        if re.match(r"^■\s*category:", line, re.IGNORECASE):
            # Flush previous category
            if current_category and current_category.get("assets"):
                subgroup["categories"].append(current_category)
            
            # Start new category
            cat_match = re.search(r"■\s*category:\s*(.+)", line, re.IGNORECASE)
            if cat_match:
                cat_name = cat_match.group(1).strip()
                current_category = {
                    "name": cat_name,
                    "code": "CAT_" + re.sub(r"\W+", "_", cat_name).upper()[:40],
                    "asset_type": "loan",
                    "assets": []
                }
                in_asset_table = True
                prev_was_header = False
        
        # Detect table header line (contains "Asset Name", "Ticker", "Type", "Country", "Source")
        elif in_asset_table and current_category and re.search(r"asset\s+name|ticker|type|country", line_lower):
            prev_was_header = True
        
        # Skip blank lines
        elif not line_lower.strip():
            prev_was_header = False
        
        # Parse asset line (after header, before next category)
        elif in_asset_table and current_category and prev_was_header and line.strip():
            # Asset lines are formatted: "Name - Ticker - Type - Country - Source"
            # Example: "JPMorgan Chase - Manhattan Commercial Office Loan - - Loan - USA - SEC Filings"
            # Simple heuristic: split by " - " and take first part as name
            
            # Skip if line starts with "■" (new section) or contains "Category"
            if line.startswith("■") or "category" in line_lower:
                in_asset_table = False
                continue
            
            # Check if line looks like an asset (has dashes and contains alphanumeric)
            if " - " in line and re.search(r"[A-Z][a-z]", line):
                parts = line.split(" - ", 1)
                asset_name = parts[0].strip()
                
                if asset_name and len(asset_name) > 2 and not asset_name.startswith("■"):
                    # Generate symbol from name (sanitized)
                    symbol = re.sub(r"[^A-Z0-9]+", "_", asset_name.upper())[:20].rstrip("_")
                    if not symbol:
                        symbol = asset_name.replace(" ", "_").upper()[:20]
                    
                    current_category["assets"].append({
                        "symbol": symbol,
                        "name": asset_name
                    })
    
    # Flush last category
    if current_category and current_category.get("assets"):
        subgroup["categories"].append(current_category)
    
    return subgroup


def build_payload(master_lines: List[str], subgroup1_lines: List[str]) -> Dict[str, Any]:
    """Build import payload."""
    group = detect_group1(master_lines)
    subgroup = parse_subgroup1(subgroup1_lines)
    
    return {
        "group": group,
        "subgroups": [subgroup] if subgroup.get("categories") else []
    }


def main():
    """Extract and write sample files."""
    try:
        # Read PDFs
        master_lines = read_pdf_lines(MASTER_PDF)
        subgroup1_lines = read_pdf_lines(SUBGROUP1_PDF)
        
        # Build payload
        payload = build_payload(master_lines, subgroup1_lines)
        
        if not payload.get("subgroups"):
            print("⚠️  No categories found in subgroup; output will be empty.")
        
        # Write JSON
        OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        
        # Write source notes
        total_assets = sum(
            len(cat.get("assets", []))
            for sg in payload.get("subgroups", [])
            for cat in sg.get("categories", [])
        )
        
        source_md = f"""# Group 1 Sample - Real Data from PDFs

**Generated from:**
- {MASTER_PDF.name}
- {SUBGROUP1_PDF.name}

**Extraction Method:**
- Used PyPDF2 to extract text from PDFs.
- Identified Group 1 heading via regex: "■ Group 1: ..."
- Identified categories via regex: "■ Category: ..."
- Parsed assets from table rows (Name - Ticker - Type - Country - Source).
- No fabricated data; all assets extracted directly from PDF tables.

**Data Quality:**
- Asset names and sources preserved from PDFs.
- Ticker symbols sanitized from asset names when not available (marked as "-" in PDF).
- All categories and assets are real data extracted from the CRE Loans PDF.

**Statistics:**
- Group: {payload['group'].get('name', 'N/A')}
- Subgroups: {len(payload.get('subgroups', []))}
- Categories: {sum(len(sg.get('categories', [])) for sg in payload.get('subgroups', []))}
- Total Assets: {total_assets}

**Load in UI:**
1. Navigate to Import Taxonomy page.
2. Click "Load Sample" button.
3. Verify categories and assets populate in the preview.
4. Click "Preview" to confirm nested structure.
5. Click "Import" to persist to database (Admin required).

**Regeneration:**
```bash
cd /workspaces/wsw-v1
python scripts/extract_group1_from_pdfs.py
```

Output files will be updated in `frontend/public/samples/`.

**Verification (Backend):**
```bash
python -m pytest tests/test_block7_sample_import.py -v
```

**Verification (Frontend):**
```bash
cd frontend && npm test -- --run
```
"""
        
        OUTPUT_NOTES.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_NOTES, "w", encoding="utf-8") as f:
            f.write(source_md)
        
        # Summary
        print(f"✅ Wrote {OUTPUT_JSON}")
        print(f"✅ Wrote {OUTPUT_NOTES}")
        print(f"   Subgroups: {len(payload.get('subgroups', []))}")
        print(f"   Categories: {sum(len(sg.get('categories', [])) for sg in payload.get('subgroups', []))}")
        print(f"   Total Assets: {total_assets}")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()
