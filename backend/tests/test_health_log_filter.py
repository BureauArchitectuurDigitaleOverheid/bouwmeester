"""Successful health probes stay out of the access log; failing ones do not."""

import logging

import pytest

from bouwmeester.core.app import HealthCheckAccessFilter


def _access_record(path: str, status: int) -> logging.LogRecord:
    # The shape uvicorn.access logs with.
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("10.0.0.1:1234", "GET", path, "1.1", status),
        exc_info=None,
    )


@pytest.mark.parametrize(
    ("path", "status", "kept"),
    [
        ("/api/health/ready", 200, False),
        ("/api/health/live", 200, False),
        ("/api/health/ready", 500, True),
        ("/api/leads", 200, True),
    ],
)
def test_filter(path, status, kept):
    assert HealthCheckAccessFilter().filter(_access_record(path, status)) is kept


def test_filter_leaves_other_records_alone():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "plain", None, None)
    assert HealthCheckAccessFilter().filter(record) is True
