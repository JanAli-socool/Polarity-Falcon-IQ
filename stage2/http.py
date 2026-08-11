"""Bounded HTTP client with observable retry and failure behavior."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
import requests

from stage2.operating import OperatingLog, now_utc

USER_AGENT = "FalconFamilyOfficeResearch/2.0 (+https://github.com/JanAli-socool/falcon-fo)"
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class Observation:
    url: str
    final_url: str
    observed_at: str
    status_code: int
    content_type: str
    text: str
    content_sha256: str
    elapsed_ms: int


class ObservableHttpClient:
    def __init__(
        self,
        log: OperatingLog,
        *,
        timeout_seconds: float = 20,
        max_attempts: int = 3,
        min_interval_seconds: float = 0.15,
    ) -> None:
        self.log = log
        self.timeout = timeout_seconds
        self.max_attempts = max_attempts
        self.min_interval = min_interval_seconds
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json,text/plain;q=0.8,*/*;q=0.5",
        })
        self._last_request = 0.0

    def get(self, url: str, *, purpose: str, allow_binary: bool = False) -> Observation:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            wait = max(0.0, self.min_interval - (time.monotonic() - self._last_request))
            if wait:
                time.sleep(wait)
            started = time.monotonic()
            self.log.count("http_attempts")
            self.log.emit("http.request.started", url=url, purpose=purpose, attempt=attempt)
            try:
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                self._last_request = time.monotonic()
                elapsed_ms = round((self._last_request - started) * 1000)
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                self.log.emit(
                    "http.request.completed",
                    url=url,
                    final_url=response.url,
                    purpose=purpose,
                    attempt=attempt,
                    status_code=response.status_code,
                    elapsed_ms=elapsed_ms,
                    content_type=content_type,
                    bytes=len(response.content),
                )
                if response.status_code in RETRYABLE_STATUS:
                    raise requests.HTTPError(f"retryable HTTP {response.status_code}", response=response)
                response.raise_for_status()
                if not allow_binary and content_type and not (
                    content_type.startswith("text/")
                    or "html" in content_type
                    or "json" in content_type
                    or "xml" in content_type
                ):
                    raise ValueError(f"unsupported content type: {content_type}")
                self.log.count("http_succeeded")
                return Observation(
                    url=url,
                    final_url=response.url,
                    observed_at=now_utc(),
                    status_code=response.status_code,
                    content_type=content_type,
                    text=response.text if not allow_binary else "",
                    content_sha256=hashlib.sha256(response.content).hexdigest(),
                    elapsed_ms=elapsed_ms,
                )
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                self.log.emit(
                    "http.request.failed",
                    url=url,
                    purpose=purpose,
                    attempt=attempt,
                    error_type=type(exc).__name__,
                    error=str(exc)[:500],
                    status_code=status,
                )
                if attempt < self.max_attempts and (status in RETRYABLE_STATUS or status is None):
                    self.log.count("retries")
                    delay = min(8, 2 ** (attempt - 1))
                    self.log.emit("http.request.retry_scheduled", url=url, attempt=attempt, delay_seconds=delay)
                    time.sleep(delay)
                    continue
                break
        self.log.count("http_failed")
        raise RuntimeError(f"GET failed after {self.max_attempts} attempt(s): {url}: {last_error}") from last_error

    def dependency_failure_exercise(self) -> None:
        """Exercise real retry/recovery control, explicitly labelled as induced."""
        unavailable = "https://httpstat.us/503"
        self.log.emit(
            "dependency.exercise.started",
            dependency="httpstat.us",
            induced=True,
            reason="Transparent source-side 503 exercise; no production evidence depends on this endpoint.",
        )
        try:
            self.get(unavailable, purpose="induced_dependency_failure")
            self.log.emit("dependency.exercise.unexpected_success", dependency="httpstat.us", induced=True)
        except RuntimeError as exc:
            self.log.emit(
                "dependency.failure.handled",
                dependency="httpstat.us",
                induced=True,
                disposition="bounded_retries_exhausted_then_cycle_continued",
                error=str(exc)[:500],
            )
        recovery_url = "https://www.sec.gov/robots.txt"
        try:
            self.get(recovery_url, purpose="dependency_recovery_probe")
            self.log.emit(
                "dependency.recovery.confirmed",
                dependency="public_https",
                induced=True,
                fallback_url=recovery_url,
            )
        except RuntimeError as exc:
            self.log.emit(
                "dependency.recovery.failed",
                dependency="public_https",
                induced=True,
                fallback_url=recovery_url,
                error=str(exc)[:500],
            )
