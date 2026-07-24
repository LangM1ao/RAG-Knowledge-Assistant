from dataclasses import dataclass
import os
from typing import Callable

import requests


class ApiClientError(RuntimeError):
    """Readable error raised when a FastAPI request cannot be completed."""


@dataclass(frozen=True)
class HealthCheckResult:
    connected: bool
    status: str
    message: str
    service: str | None = None


class ApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 3.0,
        get: Callable = requests.get,
        post: Callable = requests.post,
        delete: Callable = requests.delete,
    ):
        resolved_base_url = base_url or os.getenv(
            "API_BASE_URL",
            "http://127.0.0.1:8000",
        )
        self.base_url = resolved_base_url.rstrip("/")
        self.timeout = timeout
        self.get = get
        self.post = post
        self.delete = delete

    @staticmethod
    def _response_json(response) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiClientError("后端响应不是有效的 JSON。") from exc

        if response.status_code >= 400:
            detail = payload.get("detail") if isinstance(payload, dict) else None
            raise ApiClientError(detail or f"后端返回异常状态码：{response.status_code}")

        return payload

    @staticmethod
    def _raise_request_error(exc: requests.RequestException) -> None:
        if isinstance(exc, requests.Timeout):
            raise ApiClientError("请求后端超时，请稍后重试。") from exc
        if isinstance(exc, requests.ConnectionError):
            raise ApiClientError("无法连接后端，请先启动 FastAPI 服务。") from exc
        raise ApiClientError(f"请求后端失败：{exc}") from exc

    def check_health(self) -> HealthCheckResult:
        try:
            response = self.get(
                f"{self.base_url}/health",
                timeout=self.timeout,
            )
        except requests.Timeout:
            return HealthCheckResult(
                connected=False,
                status="timeout",
                message="连接后端超时，请确认 FastAPI 是否正常运行。",
            )
        except requests.ConnectionError:
            return HealthCheckResult(
                connected=False,
                status="connection_error",
                message="无法连接后端，请先启动 FastAPI 服务。",
            )
        except requests.RequestException as exc:
            return HealthCheckResult(
                connected=False,
                status="request_error",
                message=f"请求后端失败：{exc}",
            )

        if response.status_code != 200:
            return HealthCheckResult(
                connected=False,
                status="http_error",
                message=f"后端返回异常状态码：{response.status_code}",
            )

        try:
            payload = response.json()
        except ValueError:
            return HealthCheckResult(
                connected=False,
                status="invalid_response",
                message="后端响应不是有效的 JSON。",
            )

        if payload.get("status") != "ok":
            return HealthCheckResult(
                connected=False,
                status="unhealthy",
                message="后端可以访问，但健康状态不是 ok。",
                service=payload.get("service"),
            )

        return HealthCheckResult(
            connected=True,
            status="ok",
            message="后端连接正常",
            service=payload.get("service"),
        )

    def upload_document(
        self,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> dict:
        try:
            response = self.post(
                f"{self.base_url}/documents/upload",
                files={"file": (filename, content, content_type)},
                timeout=30.0,
            )
        except requests.RequestException as exc:
            self._raise_request_error(exc)
        return self._response_json(response)

    def list_documents(self) -> list[dict]:
        try:
            response = self.get(
                f"{self.base_url}/documents/list",
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            self._raise_request_error(exc)
        return self._response_json(response).get("documents", [])

    def delete_document(self, document_id: str) -> dict:
        try:
            response = self.delete(
                f"{self.base_url}/documents/{document_id}",
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            self._raise_request_error(exc)
        return self._response_json(response)

    def rebuild_document(self, document_id: str) -> dict:
        try:
            response = self.post(
                f"{self.base_url}/documents/{document_id}/rebuild",
                timeout=30.0,
            )
        except requests.RequestException as exc:
            self._raise_request_error(exc)
        return self._response_json(response)

    def query(
        self,
        question: str,
        top_k: int = 3,
        retrieval_mode: str | None = None,
        similarity_threshold: float | None = None,
        document_ids: list[str] | None = None,
        source_files: list[str] | None = None,
    ) -> dict:
        payload = {"question": question, "top_k": top_k}
        if retrieval_mode is not None:
            payload["retrieval_mode"] = retrieval_mode
        if similarity_threshold is not None:
            payload["similarity_threshold"] = similarity_threshold
        if document_ids:
            payload["document_ids"] = document_ids
        if source_files:
            payload["source_files"] = source_files

        try:
            response = self.post(
                f"{self.base_url}/chat/query",
                json=payload,
                timeout=60.0,
            )
        except requests.RequestException as exc:
            self._raise_request_error(exc)
        return self._response_json(response)

    def get_chat_history(self, limit: int = 10) -> list[dict]:
        try:
            response = self.get(
                f"{self.base_url}/chat/history",
                params={"limit": limit},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            self._raise_request_error(exc)
        return self._response_json(response).get("history", [])
