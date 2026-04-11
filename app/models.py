from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


CAMERA_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
OUTPUT_SUBDIR_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

CameraMode = Literal["go2rtc_helper", "manual_urls", "gopro"]
CameraPreviewModeInput = Literal["none", "external_link", "stream_proxy"]
CameraPreviewMode = Literal["none", "external_link"]
BackendType = Literal["ffmpeg", "gopro"]
CameraStatus = Literal["idle", "starting", "recording", "stopping", "downloading", "error"]
CameraAction = Literal["idle", "starting", "recording", "stopping", "downloading", "error"]
PrinterConnectionState = Literal["online", "offline", "unknown"]
PrinterPreviewMode = Literal["embedded", "external_link", "none"]


class CameraConfigInput(BaseModel):
    id: str
    name: str
    enabled: bool = True
    description: str | None = None
    mode: CameraMode | None = None
    printer_id: str | None = None
    printer_name: str | None = None
    default_live_view: bool = False
    moonraker_url: str | None = None
    display_order: int | None = Field(default=None, ge=0)

    go2rtc_base_url: str | None = None
    stream_name: str | None = None

    preview_url: str | None = None
    record_url: str | None = None

    gopro_host: str | None = None
    preview_mode: CameraPreviewModeInput | None = None
    auto_download_after_stop: bool = True
    download_timeout_seconds: int = Field(default=120, ge=5, le=900)
    file_stabilization_wait_seconds: int = Field(default=5, ge=0, le=120)

    output_subdir: str | None = None

    @field_validator("id")
    @classmethod
    def validate_camera_id(cls, value: str) -> str:
        if not CAMERA_ID_RE.match(value):
            raise ValueError("Camera id must match [A-Za-z0-9_-]+")
        return value

    @field_validator("printer_id")
    @classmethod
    def validate_printer_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not CAMERA_ID_RE.match(value):
            raise ValueError("printer_id must match [A-Za-z0-9_-]+")
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
    def validate_mode_fields(self) -> "CameraConfigInput":
        mode = self.mode or infer_input_mode(self)
        if mode == "gopro":
            if not self.gopro_host:
                raise ValueError("gopro_host is required for gopro mode")
            preview_mode = self.preview_mode or "none"
            if preview_mode == "stream_proxy":
                raise ValueError("preview_mode 'stream_proxy' is not implemented yet")
            if preview_mode == "external_link" and not (self.preview_url or "").strip():
                raise ValueError("preview_url is required when preview_mode is external_link")
            return self

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
    mode: CameraMode
    backend_type: BackendType
    printer_id: str
    printer_name: str
    default_live_view: bool = False
    moonraker_url: str | None = None
    display_order: int | None = None

    go2rtc_base_url: str | None = None
    stream_name: str | None = None

    preview_url: str | None = None
    record_url: str | None = None

    gopro_host: str | None = None
    preview_mode: CameraPreviewMode | None = None
    auto_download_after_stop: bool = True
    download_timeout_seconds: int = 120
    file_stabilization_wait_seconds: int = 5

    output_subdir: str


class CameraConfigFile(BaseModel):
    cameras: list[CameraConfigInput] = Field(default_factory=list)


class CameraUpsertRequest(BaseModel):
    name: str = Field(min_length=1)
    id: str | None = None
    enabled: bool = True
    output_subdir: str | None = None
    description: str | None = None
    mode: CameraMode = "go2rtc_helper"
    printer_id: str | None = None
    printer_name: str | None = None
    default_live_view: bool = False
    moonraker_url: str | None = None
    display_order: int | None = Field(default=None, ge=0)
    go2rtc_base_url: str | None = None
    stream_name: str | None = None
    preview_url: str | None = None
    record_url: str | None = None
    gopro_host: str | None = None
    preview_mode: CameraPreviewModeInput | None = None
    auto_download_after_stop: bool = True
    download_timeout_seconds: int = Field(default=120, ge=5, le=900)
    file_stabilization_wait_seconds: int = Field(default=5, ge=0, le=120)

    @model_validator(mode="after")
    def validate_mode_fields(self) -> "CameraUpsertRequest":
        if self.mode == "go2rtc_helper" and not self.go2rtc_base_url:
            raise ValueError("go2rtc_base_url is required for go2rtc_helper mode")
        if self.mode == "manual_urls" and not self.record_url:
            raise ValueError("record_url is required for manual_urls mode")
        if self.mode == "gopro":
            if not self.gopro_host:
                raise ValueError("gopro_host is required for gopro mode")
            preview_mode = self.preview_mode or "none"
            if preview_mode == "stream_proxy":
                raise ValueError("preview_mode 'stream_proxy' is not implemented yet")
            if preview_mode == "external_link" and not self.preview_url:
                raise ValueError("preview_url is required when preview_mode is external_link")
        return self


class CameraManagementItem(BaseModel):
    id: str
    name: str
    enabled: bool
    output_subdir: str
    description: str | None = None
    mode: CameraMode
    printer_id: str
    printer_name: str
    default_live_view: bool = False
    moonraker_url: str | None = None
    display_order: int | None = None
    go2rtc_base_url: str | None = None
    stream_name: str | None = None
    preview_url: str | None = None
    record_url: str | None = None
    gopro_host: str | None = None
    preview_mode: CameraPreviewMode | None = None
    auto_download_after_stop: bool = True
    download_timeout_seconds: int = 120
    file_stabilization_wait_seconds: int = 5
    resolved_preview_url: str | None = None
    resolved_record_url: str | None = None


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
    backend_type: BackendType
    status: CameraStatus = "idle"
    in_progress_action: CameraAction = "idle"
    recording: bool = False
    started_at: datetime | None = None
    expected_end_at: datetime | None = None
    requested_duration_seconds: int | None = None
    output_file: str | None = None
    output_path: str | None = None
    last_error: str | None = None
    last_error_details: str | None = None
    last_ffmpeg_command: str | None = None
    last_ffmpeg_exit_code: int | None = None
    last_downloaded_filename: str | None = None
    last_download_status: str | None = None
    last_action_message: str | None = None
    last_completed_output: str | None = None


class RecordStartRequest(BaseModel):
    duration: int | None = Field(default=None, ge=1)


class CameraProbeResult(BaseModel):
    reachable: bool
    record_url: str
    diagnostic_status: Literal["ok", "no_video_stream", "input_open_failure"] = "ok"
    message: str | None = None
    codec: str | None = None
    width: int | None = None
    height: int | None = None
    stream_type: str | None = None
    video_stream_found: bool = False
    error: str | None = None
    details: str | None = None
    command: str | None = None
    streams: list[dict] = Field(default_factory=list)


class GoProPreviewResult(BaseModel):
    available: bool
    preview_mode: CameraPreviewMode | str
    open_url: str | None = None
    message: str | None = None


class GoProMediaItem(BaseModel):
    folder: str
    filename: str
    relative_key: str
    created_timestamp: int | None = None
    created_at: datetime | None = None
    size_bytes: int | None = None
    download_url: str
    is_video: bool = True


class GoProStatusResult(BaseModel):
    reachable: bool
    host: str
    message: str | None = None
    error: str | None = None
    details: str | None = None
    http_status: int | None = None
    recording: bool | None = None
    battery: int | None = None
    command: str | None = None
    raw_status: dict = Field(default_factory=dict)


class GoProDownloadResult(BaseModel):
    success: bool
    camera_id: str
    downloaded_files: list[str] = Field(default_factory=list)
    message: str | None = None
    error: str | None = None
    details: str | None = None


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


class ClipItem(BaseModel):
    camera_id: str
    filename: str
    relative_path: str
    created_at: datetime
    size_bytes: int
    size_human: str
    active: bool = False


class PrinterStatusSnapshot(BaseModel):
    connection_state: PrinterConnectionState = "unknown"
    printer_status_text: str = "Status unavailable"
    current_file_name: str | None = None
    progress_percent: float | None = None
    extruder_current_temp: float | None = None
    extruder_target_temp: float | None = None
    bed_current_temp: float | None = None
    bed_target_temp: float | None = None
    eta_text: str | None = None
    error_message: str | None = None


class PrinterViewOption(BaseModel):
    camera_id: str
    camera_name: str
    preview_url: str | None = None
    preview_mode: PrinterPreviewMode = "none"
    preview_available: bool = False
    default_live_view: bool = False
    enabled: bool = True
    display_order: int | None = None


class PrinterCard(BaseModel):
    printer_id: str
    printer_name: str
    camera_id: str | None = None
    camera_name: str | None = None
    default_camera_id: str | None = None
    default_camera_name: str | None = None
    preview_url: str | None = None
    preview_mode: PrinterPreviewMode = "none"
    preview_available: bool = False
    connection_state: PrinterConnectionState = "unknown"
    printer_status_text: str = "Status unavailable"
    current_file_name: str | None = None
    progress_percent: float | None = None
    extruder_current_temp: float | None = None
    extruder_target_temp: float | None = None
    bed_current_temp: float | None = None
    bed_target_temp: float | None = None
    eta_text: str | None = None
    available_camera_ids: list[str] = Field(default_factory=list)
    available_camera_count: int = 0
    available_views: list[PrinterViewOption] = Field(default_factory=list)
    moonraker_url: str | None = None
    display_order: int | None = None
    error_message: str | None = None


def infer_input_mode(camera: CameraConfigInput) -> CameraMode:
    if camera.mode:
        return camera.mode
    if camera.gopro_host:
        return "gopro"
    if camera.go2rtc_base_url and not (camera.preview_url or camera.record_url):
        return "go2rtc_helper"
    return "manual_urls"
