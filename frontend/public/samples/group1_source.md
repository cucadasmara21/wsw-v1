# Group 1 Sample - Real Data from PDFs

**Generated from:**
- MASTER_20_Groups_Complete.pdf
- Group_1_Subgroup_1_Commercial_Real_Estate_Loans_Assets.pdf

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
- Group: Group 1
- Subgroups: 1
- Categories: 9
- Total Assets: 85

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
