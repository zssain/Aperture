from app.core.pii_filter import pii_allowlist_processor


def test_pii_values_are_removed_from_log_event() -> None:
    fixture = "Applicant PII 4111111111111111"
    filtered = pii_allowlist_processor(
        None,
        "info",
        {"event": "received", "display_name": fixture, "description": fixture, "password": fixture},
    )
    assert fixture not in repr(filtered)


def test_narration_and_embedding_vectors_are_removed() -> None:
    fixture = "UPI private narration 998877"
    vector = [0.123456, 0.654321]
    filtered = pii_allowlist_processor(
        None,
        "info",
        {
            "event": "classified",
            "normalized_narration": fixture,
            "embedding_vector": vector,
            "match_similarity": 0.91,
        },
    )
    assert fixture not in repr(filtered)
    assert repr(vector) not in repr(filtered)
