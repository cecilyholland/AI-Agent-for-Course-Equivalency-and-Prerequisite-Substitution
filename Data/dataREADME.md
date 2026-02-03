
**Everything inside here is the source of truth for the agent.**

**Question	                         Where it lives**
Where did the data come from?	    Raw/inputs/*.pdf
How was it extracted?	            Raw/RawDataParser.py
When was it extracted?	            Processed/extraction_manifest.json
What did we extract?	            Processed/ParsedData.csv
What text supports each claim?     	Processed/CitationChunks.csv

Data/
├── Raw/
│   ├── Inputs/
│   └── RawDataParser.py
├── Processed/
│   ├── ParsedData.csv
│   ├── CitationChunks.csv
│   └── extraction_manifest.json
└── dataREADME.md

**Immutability & transformation rules**

Raw/Inputs contains immutable source documents.
These files must not be edited, renamed, or overwritten once added.

All transformations must occur via Raw/RawDataParser.py, and all derived artifacts must be written to Processed/.

This ensures a clear, auditable provenance chain from source documents to extracted data.


**How the AI agent uses this data**

The AI agent reasons only over artifacts in Processed/.

For every claim it makes (e.g., credits, prerequisites, general education category), the agent must cite one or more entries from CitationChunks.csv, which contain the verbatim source text and page references.

**Citation policy for the reasoning engine**

All conclusions, equivalency decisions, and factual claims produced by the reasoning engine must be grounded in one or more entries from Processed/CitationChunks.csv.
Each claim must reference the associated chunk_id(s), ensuring that every decision is traceable to the exact source document and page from which the evidence was extracted.


**How to run the extraction**

From the repository root: python Data/Raw/RawDataParser.py


This will automatically:

read all PDFs in Data/Raw/Inputs

generate:

    Processed/ParsedData.csv

    Processed/CitationChunks.csv

    Processed/extraction_manifest.json

**IMPORTANT: Re-running the parser**

This script should only be re-run when new source documents are added to Raw/Inputs.

The extraction logic lives in Raw/RawDataParser.py.
The files in Processed/ are derived artifacts and should be treated as read-only outputs of a specific extraction run, as documented in extraction_manifest.json.

**Environment & dependencies (Data Extraction)**

This pipeline requires Python 3.10+ and the following packages:

Required Python packages: pdfplumber

Installed automatically as dependencies

pdfminer.six
pypdfium2
cryptography
cffi

Installation
Activate the project environment, then run: pip install pdfplumber

Verification: python -c "import pdfplumber; print(pdfplumber.__version__)"