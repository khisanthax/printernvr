from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


CAMERA_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
OUTPUT_SUBDIR_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class CameraConfigInput(BaseModel):
    id: str
    name: str
    enabled: bool = True
    description: str | None = None

    go2rtc_base_url: str | None = None
    stream_name: str | None = None

    preview_url: str | None = None
    record_url: str | None = None

    output_subdir: str | None = None

    @field_validator("id")
    @classmethod
    def validate_camera_id(cls, value: str) -> str:
        if not CAMERA_ID_RE.match(value):
            raise ValueError("Camera id must match [A-Za-z0-9_-]+")
        return value

    @field_validator("output_subdir")
    @classmethod
    def validate_output_subdir(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not OUTPUT_SUBDIR_RE.match(value):
            raise ValueError("output_subdir must match [A-Za-z0-9_.-]+")
        if value in {".", ".."}:
            raise ValueError("output_subdir must not be '.' or '..'")
        return value

    @model_validator(mode="after")
    def validate_has_config_mode(self) -> "CameraConfigInput":
        has_go2rtc = bool(self.go2rtc_base_url)
        has_manual = bool(self.preview_url or self.record_url)
        if not has_go2rtc and not has_manual:
            raise ValueError(
                "Camera requires either go2rtc_base_url or manual preview/record URLs"
            )
        return self


class ResolvedCamera(BaseModel):
    id: str
    name: str
    enabled: bool = True
    description: str | None = None

    go2rtc_base_url: str | None = None
    stream_name: str | None = None

    preview_url: str | None = None
    record_url: str
    output_subdir: str


class CameraConfigFile(BaseModel):
    cameras: list[CameraConfigInput] = Field(default_factory=list)


class RetentionConfig(BaseModel):
    enabled: bool = False
    cleanup_mode: Literal["disabled", "alert_only", "delete_oldest"] = "disabled"
    max_age_days: int | None = Field(default=None, ge=1)
    max_total_gb: float | None = Field(default=None, gt=0)
    minimum_free_gb: float | None = Field(default=None, gt=0)


class AppSettingsFile(BaseModel):
    retention: RetentionConfig = Field(default_factory=RetentionConfig)


class AppConfig(BaseModel):
    cameras: list[ResolvedCamera]
    retention: RetentionConfig = Field(default_factory=RetentionConfig)


class CameraRuntimeState(BaseModel):
    camera_id: str
    status: Literal["idle", "starting", "recording", "stopping", "error"] = "idle"
    recording: bool = False
    started_at: datetime | None = None
    expected_end_at: datetime | None = None
    output_file: str | None = None
    output_path: str | None = None
    last_error: str | None = None
    last_completed_output: str | None = None


class RecordStartRequest(BaseModel):
    duration: int | None = Field(default=None, ge=1)


class CleanupSummary(BaseModel):
    timestamp: datetime
    triggered_by: str
    cleanup_mode: str
    deleted_files: int = 0
    deleted_bytes: int = 0
    deleted_gb: float = 0.0
    deleted_paths: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class StorageStatus(BaseModel):
    recordings_root: str
    total_recordings_bytes: int
    total_recordings_gb: float
    free_disk_bytes: int
    free_disk_gb: float
    retention_enabled: bool
    cleanup_mode: str
    warning_state: bool
    warnings: list[str] = Field(default_factory=list)
    candidate_cleanup_file_count: int = 0
    last_cleanup_summary: CleanupSummary | None = None
