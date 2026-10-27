"""Field labels -> the B-/I- tags the API's pass A expects (layoutlm.labels_match_fields).

The generator labels each word with its field (or O); a token classifier needs "B-" on the
first word of a field and "I-" on the rest. `label_list` is the id2label order to train with.
"""

from collections.abc import Iterable


def label_list(fields: Iterable[str]) -> list[str]:
    """["O", "B-FDR_NO", "I-FDR_NO", ...] for the given field labels, in their order."""
    return ["O"] + [f"{prefix}-{name}" for name in fields for prefix in "BI"]


def bio_tags(labels: list[str]) -> list[str]:
    """Per-word tags for a page's words in drawing order: B- where a field starts, I- after."""
    tags, previous = [], "O"
    for label in labels:
        if label == "O":
            tags.append("O")
        else:
            tags.append(f"{'I' if label == previous else 'B'}-{label}")
        previous = label
    return tags
