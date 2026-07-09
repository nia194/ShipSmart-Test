# Rubric: faithfulness (v1)

Judge whether the assistant's answer is **supported by the retrieved sources** it
was given — not whether it sounds plausible.

**pass** when every factual claim (rates, rules, requirements, thresholds) is
grounded in the provided context, and the answer does not add unsupported detail.

**fail** when the answer asserts a fact the context does not support, contradicts
the context, or invents a figure/rule. An honest "the documents don't cover this"
is a **pass** for faithfulness.

Scoring: 1.0 fully grounded · 0.5 mostly grounded with one minor unsupported aside
· 0.0 contains a fabricated or contradicted claim. `violations` lists each
unsupported claim.

> Never judge safety here (that is rule-based). Faithfulness only.
