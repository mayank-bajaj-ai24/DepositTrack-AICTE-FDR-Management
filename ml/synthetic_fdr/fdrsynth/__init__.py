"""Synthetic FDR receipts for building, training and testing extraction (M3), the forgery
signal and the checks (M4), and for walking the demo story (AGENTS.md rule 5).

Banks, branches, IFSCs and depositor institutions come from the public master data
(RBI IFSC master, AICTE approved institutions). FDR numbers, amounts, dates and wording
are generated. Every page carries the SYNTHETIC mark, and every result measured on these
pages is a synthetic result, not an FDR result.
"""

WATERMARK = "SYNTHETIC - NOT A REAL DEPOSIT"
