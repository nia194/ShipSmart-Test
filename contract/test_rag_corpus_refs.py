"""Contract: every doc a Layer-2 RAG case cites is a real ShipSmart-API source.

RAG cases score context precision/recall against ``relevant_doc_ids`` and citations
against ``must_cite_any`` (evals §3.1). If either references a document that isn't
in ShipSmart-API's corpus, the case grades against a phantom — a green run that
proves nothing. This asserts the datasets and the corpus can't drift apart: a
renamed/removed corpus file fails here, not silently in a nightly lane.
"""

from __future__ import annotations

from evals.case_model import load_jsonl
from evals.manifest import load_manifest, verify
from sibling import api_corpus_refs


def _rag_suites():
    return [e for e in load_manifest() if e.suite.startswith("rag/")]


def test_there_is_a_rag_suite():
    assert _rag_suites(), "no rag/* suite registered in the dataset manifest"


def test_rag_citations_reference_real_corpus_docs():
    corpus = api_corpus_refs()
    assert corpus, "ShipSmart-API corpus (data/documents/) is empty or missing"

    missing: list[str] = []
    for entry in _rag_suites():
        verify(entry)  # sha256 must match before we trust the file's contents
        for case in load_jsonl(entry.path):
            for ref in (*case.expected.must_cite_any, *case.expected.relevant_doc_ids):
                if ref not in corpus:
                    missing.append(f"{case.id}: {ref!r}")

    assert not missing, "RAG cases cite documents absent from the API corpus:\n" + "\n".join(
        sorted(missing)
    )
