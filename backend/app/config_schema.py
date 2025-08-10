from __future__ import annotations
from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field, PositiveInt, conint

class MQTTConfig(BaseModel):
    host: str = "mqtt"
    port: conint(ge=1, le=65535) = 1883
    user: Optional[str] = None
    password: Optional[str] = None
    topic_prefix: str = "frigate"

class Zone(BaseModel):
    name: str
    points: List[List[int]]  # [[x, y], ...]

class DetectionParams(BaseModel):
    score_threshold: float = Field(0.6, ge=0.0, le=1.0)
    iou_threshold: float = Field(0.45, ge=0.0, le=1.0)

class RetentionPolicy(BaseModel):
    mode: Literal["motion", "all"] = "motion"
    detection_days: PositiveInt = 5
    recording_days: PositiveInt = 2
    pre_capture_sec: conint(ge=0, le=15) = 3
    post_capture_sec: conint(ge=0, le=15) = 3

class FFmpegInput(BaseModel):
    url: str
    hwaccel: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[int] = None

class CameraConfig(BaseModel):
    name: str
    enabled: bool = True
    ffmpeg: FFmpegInput
    zones: List[Zone] = []
    detection: DetectionParams = DetectionParams()
    retention: RetentionPolicy = RetentionPolicy()

class RootConfig(BaseModel):
    mqtt: MQTTConfig = MQTTConfig()
    cameras: Dict[str, CameraConfig] = {}
