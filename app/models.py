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


class ConfigFile(BaseModel):
    cameras: list[CameraConfigInput] = Field(default_factory=list)


class AppConfig(BaseModel):
    cameras: list[ResolvedCamera]


class CameraRuntimeState(BaseModel):
    camera_id: str
    status: Literal["idle", "starting", "recording", "stopping", "error"] = "idle"
    started_at: datetime | None = None
    expected_end_at: datetime | None = None
    output_path: str | None = None
    last_error: str | None = None
    last_completed_output: str | None = None
