# Rubric: answer_relevance (v1)

Judge whether the answer **addresses what the user actually asked**.

**pass** when the response resolves the user's question or clearly states the next
step needed; it stays on the asked topic and does not dodge with boilerplate.

**fail** when it answers a different question, buries the answer, or responds with
generic filler that ignores the specifics of the ask.

Scoring: 1.0 directly and completely answers · 0.5 partially answers or answers
with notable padding · 0.0 off-topic or non-responsive. `violations` names what
the user asked that went unaddressed.

> Relevance is independent of correctness — a relevant answer can still be wrong;
> that is caught by faithfulness. Judge only relevance here.
