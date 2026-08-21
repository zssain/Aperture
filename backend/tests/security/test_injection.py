from app.services.notices.context import NoticeContext


def test_notice_schema_has_no_attacker_controlled_evidence_fields() -> None:
    fields = set(NoticeContext.model_fields)
    assert fields.isdisjoint({"description", "counterparty", "document_text", "ledger"})
