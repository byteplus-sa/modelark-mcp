"""Unit tests for the structured stderr JSON logger with redaction."""

from __future__ import annotations

import json

import pytest

from modelark_mcp.observability import logger


def _parse_stderr(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    captured = capsys.readouterr()
    lines = [line for line in captured.err.strip().split("\n") if line]
    return [json.loads(line) for line in lines]


class TestRedaction:
    """Verify sensitive keys are redacted in output."""

    def test_redacts_authorization(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", authorization="Bearer sk-secret")  # pragma: allowlist secret
        records = _parse_stderr(capsys)
        assert records[0]["authorization"] == "[REDACTED]"

    def test_redacts_x_api_key(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", **{"x-api-key": "sk-123"})  # pragma: allowlist secret
        records = _parse_stderr(capsys)
        assert records[0]["x-api-key"] == "[REDACTED]"

    def test_redacts_api_key(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", api_key="sk-123")  # pragma: allowlist secret
        records = _parse_stderr(capsys)
        assert records[0]["api_key"] == "[REDACTED]"

    def test_redacts_apikey(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", apikey="sk-123")  # pragma: allowlist secret
        records = _parse_stderr(capsys)
        assert records[0]["apikey"] == "[REDACTED]"

    def test_redacts_token(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", token="tok-abc")  # pragma: allowlist secret
        records = _parse_stderr(capsys)
        assert records[0]["token"] == "[REDACTED]"

    def test_redacts_secret(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", secret="my-secret")  # pragma: allowlist secret
        records = _parse_stderr(capsys)
        assert records[0]["secret"] == "[REDACTED]"

    def test_redacts_password(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", password="hunter2")  # pragma: allowlist secret
        records = _parse_stderr(capsys)
        assert records[0]["password"] == "[REDACTED]"

    def test_preserves_generic_data(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", data={"count": 3})
        records = _parse_stderr(capsys)
        assert records[0]["data"] == {"count": 3}

    def test_redacts_audio_data(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", audio_data="base64-audio-data")
        records = _parse_stderr(capsys)
        assert records[0]["audio_data"] == "[REDACTED]"

    def test_redacts_prompt(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", prompt="private creative prompt")
        records = _parse_stderr(capsys)
        assert records[0]["prompt"] == "[REDACTED]"

    def test_redacts_media_url(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", video_url="https://example.com/private.mp4")
        records = _parse_stderr(capsys)
        assert records[0]["video_url"] == "[REDACTED]"

    def test_redacts_case_insensitive(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", Authorization="Bearer sk-secret")  # pragma: allowlist secret
        records = _parse_stderr(capsys)
        assert records[0]["Authorization"] == "[REDACTED]"

    def test_redacts_mixed_case_key(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", **{"API_KEY": "sk-123"})  # pragma: allowlist secret
        records = _parse_stderr(capsys)
        assert records[0]["API_KEY"] == "[REDACTED]"

    def test_redacts_uppercase_token(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", TOKEN="tok-abc")  # pragma: allowlist secret
        records = _parse_stderr(capsys)
        assert records[0]["TOKEN"] == "[REDACTED]"


class TestNestedRedaction:
    """Verify sensitive keys in nested dicts are redacted."""

    def test_redacts_nested_dict(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info(
            "test",
            request={"headers": {"authorization": "Bearer sk-secret"}},  # pragma: allowlist secret
        )
        records = _parse_stderr(capsys)
        assert records[0]["request"]["headers"]["authorization"] == "[REDACTED]"

    def test_redacts_deeply_nested_dict(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info(
            "test",
            level1={"level2": {"level3": {"token": "deep-token"}}},
        )
        records = _parse_stderr(capsys)
        assert records[0]["level1"]["level2"]["level3"]["token"] == "[REDACTED]"

    def test_non_sensitive_nested_preserved(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info(
            "test",
            request={"model_id": "dola-seedream", "duration": 5.0},
        )
        records = _parse_stderr(capsys)
        assert records[0]["request"]["model_id"] == "dola-seedream"
        assert records[0]["request"]["duration"] == 5.0

    def test_redacts_in_list_of_dicts(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info(
            "test",
            items=[
                {"api_key": "key1", "name": "item1"},  # pragma: allowlist secret
                {"api_key": "key2", "name": "item2"},  # pragma: allowlist secret
            ],
        )
        records = _parse_stderr(capsys)
        assert records[0]["items"][0]["api_key"] == "[REDACTED]"
        assert records[0]["items"][0]["name"] == "item1"
        assert records[0]["items"][1]["api_key"] == "[REDACTED]"
        assert records[0]["items"][1]["name"] == "item2"

    def test_redacts_in_nested_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info(
            "test",
            outer={"inner_list": [{"secret": "s1"}, {"secret": "s2"}]},  # pragma: allowlist secret
        )
        records = _parse_stderr(capsys)
        assert records[0]["outer"]["inner_list"][0]["secret"] == "[REDACTED]"
        assert records[0]["outer"]["inner_list"][1]["secret"] == "[REDACTED]"

    def test_redacts_in_list_of_lists(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info(
            "test",
            matrix=[[{"password": "p1"}], [{"password": "p2"}]],  # pragma: allowlist secret
        )
        records = _parse_stderr(capsys)
        assert records[0]["matrix"][0][0]["password"] == "[REDACTED]"
        assert records[0]["matrix"][1][0]["password"] == "[REDACTED]"


class TestLogLevels:
    """Verify info/warning/error/debug log at the correct level."""

    def test_info_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("my_event")
        records = _parse_stderr(capsys)
        assert records[0]["level"] == "INFO"

    def test_warning_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.warning("my_event")
        records = _parse_stderr(capsys)
        assert records[0]["level"] == "WARNING"

    def test_error_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.error("my_event")
        records = _parse_stderr(capsys)
        assert records[0]["level"] == "ERROR"

    def test_debug_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        from modelark_mcp.observability.logger import set_level

        set_level("DEBUG")
        try:
            logger.debug("my_event")
            records = _parse_stderr(capsys)
            assert records[0]["level"] == "DEBUG"
        finally:
            set_level("INFO")

    def test_invalid_level_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid log level"):
            logger.set_level("verbose")


class TestJsonFormat:
    """Verify output is valid JSON with expected fields."""

    def test_has_timestamp(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test")
        records = _parse_stderr(capsys)
        assert "ts" in records[0]
        assert isinstance(records[0]["ts"], str)
        assert "T" in records[0]["ts"]

    def test_has_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test")
        records = _parse_stderr(capsys)
        assert "level" in records[0]

    def test_has_msg(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("my_message")
        records = _parse_stderr(capsys)
        assert records[0]["msg"] == "my_message"

    def test_has_extra_fields(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", model_id="dola-seedream", duration=5.0)
        records = _parse_stderr(capsys)
        assert records[0]["model_id"] == "dola-seedream"
        assert records[0]["duration"] == 5.0

    def test_output_is_valid_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", nested={"key": "value"})
        records = _parse_stderr(capsys)
        assert isinstance(records, list)
        assert len(records) == 1
        assert isinstance(records[0], dict)

    def test_each_log_is_separate_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("first")
        logger.info("second")
        logger.info("third")
        records = _parse_stderr(capsys)
        assert len(records) == 3
        assert records[0]["msg"] == "first"
        assert records[1]["msg"] == "second"
        assert records[2]["msg"] == "third"


class TestStderrOutput:
    """Verify logs go to stderr, not stdout."""

    def test_logs_go_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test")
        captured = capsys.readouterr()
        assert captured.err != ""
        assert captured.out == ""

    def test_no_stdout_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.error("important")
        logger.warning("warning")
        logger.debug("debug")
        captured = capsys.readouterr()
        assert captured.out == ""


class TestNonSensitiveData:
    """Verify non-sensitive data is NOT redacted."""

    def test_model_id_preserved(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", model_id="dola-seedream-5-0-pro-260628")
        records = _parse_stderr(capsys)
        assert records[0]["model_id"] == "dola-seedream-5-0-pro-260628"

    def test_artifact_id_preserved(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", artifact_id="550e8400-e29b-41d4-a716-446655440000")
        records = _parse_stderr(capsys)
        assert records[0]["artifact_id"] == "550e8400-e29b-41d4-a716-446655440000"

    def test_duration_preserved(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", duration=5.5)
        records = _parse_stderr(capsys)
        assert records[0]["duration"] == 5.5

    def test_bytes_preserved(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", bytes=1024)
        records = _parse_stderr(capsys)
        assert records[0]["bytes"] == 1024

    def test_request_id_preserved(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", request_id="req-abc-123")
        records = _parse_stderr(capsys)
        assert records[0]["request_id"] == "req-abc-123"

    def test_path_preserved(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", path="/images/generations")
        records = _parse_stderr(capsys)
        assert records[0]["path"] == "/images/generations"

    def test_non_sensitive_key_with_sensitive_substring(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        logger.info("test", request_count=42)
        records = _parse_stderr(capsys)
        assert records[0]["request_count"] == 42


class TestEdgeCases:
    """Verify edge cases: empty dict, None values, deeply nested structures."""

    def test_empty_dict_field(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", empty={})
        records = _parse_stderr(capsys)
        assert records[0]["empty"] == {}

    def test_none_value_preserved(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", request_id=None)
        records = _parse_stderr(capsys)
        assert records[0]["request_id"] is None

    def test_none_value_sensitive_key(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", token=None)
        records = _parse_stderr(capsys)
        assert records[0]["token"] == "[REDACTED]"

    def test_no_extra_fields(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test")
        records = _parse_stderr(capsys)
        assert set(records[0].keys()) == {"ts", "level", "msg"}

    def test_deeply_nested_structure(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info(
            "test",
            payload={
                "level1": {
                    "level2": {
                        "level3": {
                            "level4": {
                                "password": "deep-secret",  # pragma: allowlist secret
                                "model": "dola-seedream",
                            }
                        }
                    }
                }
            },
        )
        records = _parse_stderr(capsys)
        nested = records[0]["payload"]["level1"]["level2"]["level3"]["level4"]
        assert nested["password"] == "[REDACTED]"
        assert nested["model"] == "dola-seedream"

    def test_empty_list_field(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", items=[])
        records = _parse_stderr(capsys)
        assert records[0]["items"] == []

    def test_list_of_primitives(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", seeds=[1, 2, 3])
        records = _parse_stderr(capsys)
        assert records[0]["seeds"] == [1, 2, 3]

    def test_mixed_sensitive_and_non_sensitive(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info(
            "test",
            model_id="dola-seedream",
            api_key="sk-secret",  # pragma: allowlist secret
            duration=5.0,
            authorization="Bearer token",
        )
        records = _parse_stderr(capsys)
        assert records[0]["model_id"] == "dola-seedream"
        assert records[0]["api_key"] == "[REDACTED]"
        assert records[0]["duration"] == 5.0
        assert records[0]["authorization"] == "[REDACTED]"

    def test_integer_value_in_sensitive_key(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", token=12345)
        records = _parse_stderr(capsys)
        assert records[0]["token"] == "[REDACTED]"

    def test_boolean_value_in_sensitive_key(self, capsys: pytest.CaptureFixture[str]) -> None:
        logger.info("test", secret=True)
        records = _parse_stderr(capsys)
        assert records[0]["secret"] == "[REDACTED]"
