from app.services.catalog.seed_entries import SEED_ENTRIES


def test_curated_catalogue_size_and_provenance() -> None:
    assert 250 <= len(SEED_ENTRIES) <= 400
    assert all(row.source_note and row.aliases for row in SEED_ENTRIES)
    assert {row.category for row in SEED_ENTRIES} >= {
        "GIG_INCOME",
        "TELECOM",
        "UTILITY",
        "EMI",
        "MERCHANT",
        "SALARY",
    }
