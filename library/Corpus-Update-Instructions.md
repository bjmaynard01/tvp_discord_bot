# Here's the synopsis, designed to be dropped at the top of a new chat to preserve context on our RAG methodology:

## TVP Chatbot Corpus Update Procedure — Session Handoff

What This Bot Is

The TVP Chatbot is a Discord bot backed by Open WebUI (gpt.maynardfolks.com) serving a curated RAG knowledge base on transgender health, research, sociology, and policy. Currently runs gemma4:e4b at 32k context on a local RTX 3090. RAG config: top_k=12, relevance threshold 0.55, hybrid search ON, PyPDF extraction.

## Two-Layer RAG Architecture (Non-Negotiable)

Every source in the corpus lives in two places. Missing either layer causes retrieval failures.

Layer 1: Source Index (TVP_Source_Index.md) — Uploaded to the OWI knowledge base collection. Maps natural-language question phrasings to sources and findings. This is the primary retrieval routing mechanism because academic PDFs embed poorly against conversational queries. The index entry carries the citation load when the underlying document doesn't retrieve.

Layer 2: System Prompt CORPUS Section — One-line-per-source awareness list in the workspace model's system prompt. Tells the model what exists in the corpus even when retrieval is incomplete. Not a retrieval mechanism — it's a map.

## Procedure for Adding a New Source

Assess the source — text-extractable or scanned? Dense academic or plain-language? Peer-reviewed or white paper? What question topics does it answer?
Draft a corpus line — 1-2 lines, format: - Author et al. Year (Journal/Publisher): [what it is, coverage, key finding in one sentence]
Draft a Source Index entry — topic heading phrased as a user would ask the question (not as source title). Include: source citation, 2-4 sentence description, "Key citable finding" spelled out in plain language with statistics/percentages/named conclusions, and comprehensive question variants covering informal and adversarial phrasings.
Create plain-language summary .md if needed — for scanned PDFs, paywalled abstract-only sources, or anything with embedding-hostile language. Filename: Author_Year_Summary.md.
Upload and verify — PDF (and summary if applicable) to OWI knowledge base, updated TVP_Source_Index.md replacing old version, updated system prompt into workspace config. Test with an appropriate question. If retrieval fails, add more verbose language and question variants to the index entry.
Key Index Entry Rules
Topic headings match user intent, not source titles ("Is being trans genetic?" not "Hare 2009")
Verbose entries for hard-to-retrieve sources — spell out all findings explicitly
Lean entries for easy-to-retrieve sources — focus on routing and question variants
Always include the key finding inline — never assume the PDF will retrieve
Question variants must include how users actually ask — informal, confused, and adversarial framings all represented
Multi-topic sources get multiple entries — one per topic
When sources overlap, combine into one entry listing both sources


### Filename Convention

Author_Year_Descriptive_Title.pdf — snake case, includes primary author, year, and enough context to identify the paper at a glance. Example: Kurth_Gaser_Sanchez_Luders_2022_Brain_Sex_Transgender_Women_Shifted_Gender_Identity.pdf

Epistemic Framing (Cite Appropriately)
Peer-reviewed primary research — cite directly
Systematic reviews / meta-analyses — cite as stronger evidence than individual studies; note sample sizes
Clinical guidelines (WPATH, Endocrine Society, WHO, etc.) — cite as authoritative recommendations
White papers and expert reports — cite as "[Institution] white paper" or "researchers at [Institution]"; not peer-reviewed but may be rigorous
Association studies — note association ≠ causation
Community resources / anecdotal — use for phenomenology; route clinical questions elsewhere
Scanned / low-quality ingestion — index entry and summary carry the load
Working Session Task Framings
Add new source: "Here is [source name, citation, findings]. Generate corpus line, index entry, and summary if needed."
Update failing index entry: "The bot isn't citing [source] on [question]. Revise index entry to be more verbose and add question variants."
Coverage gaps: "What topics likely have poor retrieval? What sources are missing?"
Draft a summary: "Here is the abstract and findings from [source]. Draft a summary .md in the standard format."
Audit the index: "Review current entries for thinness, missing question variants, or unspelled key findings."
Current State Documentation Needed

To work productively, upload alongside this synopsis:

Current TVP_Source_Index.md
Current system prompt (or at least the CORPUS section)
List of ingested source files with brief description
Any known retrieval problems or gaps