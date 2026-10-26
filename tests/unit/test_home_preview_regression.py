from app.services.home_preview_regression import successful_streak


def test_transport_retry_without_json_does_not_invalidate_committed_schema_tests():
    assert (
        successful_streak(
            [
                {"state": "passed"},
                {"state": "passed"},
                {"state": "failed", "http_status": 429},
                {"state": "passed"},
            ]
        )
        == 3
    )


def test_failed_payload_schema_or_content_resets_the_streak():
    assert (
        successful_streak(
            [
                {"state": "passed"},
                {"state": "passed"},
                {"state": "failed", "error": "invalid_payload_structure"},
                {"state": "passed"},
            ]
        )
        == 1
    )


def test_partial_model_output_is_a_generation_failure_and_resets_the_streak():
    assert (
        successful_streak(
            [
                {"state": "passed"},
                {"state": "failed", "finish_reason": "MAX_TOKENS"},
                {"state": "passed"},
            ]
        )
        == 1
    )
