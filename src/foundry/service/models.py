"""Typed capture format, separate from the complete v1 exchange dataset."""
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ProcessType = Literal["etching", "annealing", "deposition", "cleaning", "lithography", "other"]
PARAMETERS = {
    "duration": {"label": "持续时间", "unit": "s", "units": {"s": (1, 0), "min": (60, 0), "h": (3600, 0)}},
    "temperature": {"label": "温度", "unit": "K", "units": {"K": (1, 0), "°C": (1, 273.15)}},
    "pressure": {"label": "压力", "unit": "Pa", "units": {"Pa": (1, 0), "kPa": (1000, 0), "mTorr": (0.133322368, 0), "Torr": (133.322368, 0)}},
    "power": {"label": "功率", "unit": "W", "units": {"W": (1, 0)}},
    "rf_power": {"label": "RF 功率", "unit": "W", "units": {"W": (1, 0)}},
    "icp_power": {"label": "ICP 功率", "unit": "W", "units": {"W": (1, 0)}},
    "target_thickness": {"label": "目标膜厚（非实测）", "unit": "nm", "units": {"nm": (1, 0), "um": (1000, 0)}},
}
for gas in ("Ar", "O2", "N2", "H2", "SF6", "CHF3", "CF4", "SiH4", "N2O"):
    PARAMETERS[gas.lower() + "_flow"] = {"label": gas + " 流量", "unit": "sccm", "units": {"sccm": (1, 0)}}

PROCESS_TYPES = {
    "etching": {"label": "刻蚀", "defaults": ["duration", "pressure", "rf_power", "icp_power"]},
    "annealing": {"label": "退火", "defaults": ["duration", "temperature", "n2_flow"]},
    "deposition": {"label": "长膜 / 镀膜", "defaults": ["duration", "temperature", "pressure", "target_thickness"]},
    "cleaning": {"label": "清洗", "defaults": ["duration", "temperature"]},
    "lithography": {"label": "光刻", "defaults": ["duration"]},
    "other": {"label": "其他工艺", "defaults": ["duration"]},
}

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class SampleInput(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
    kind: Literal["lot", "wafer", "die", "device"]
    parent_id: str | None = Field(default=None, max_length=80)

class Quantity(StrictModel):
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=20)

    @field_validator("value", mode="before")
    @classmethod
    def numeric(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("参数值必须为数值")
        return value

class RecordInput(StrictModel):
    submission_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,80}$")
    sample_id: str = Field(min_length=1, max_length=80)
    process_type: ProcessType
    occurred_at: datetime
    equipment_id: str | None = Field(default=None, max_length=100)
    recipe: str | None = Field(default=None, max_length=200)
    parameters: dict[str, Quantity] = Field(min_length=1, max_length=30)
    notes: str = Field(default="", max_length=5000)
    supersedes_id: str | None = Field(default=None, max_length=80)

    @field_validator("occurred_at")
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("工艺时间必须包含时区")
        if value > datetime.now(timezone.utc):
            raise ValueError("这里只记录已执行工艺，时间不能在未来")
        return value

    @model_validator(mode="after")
    def known_parameters(self):
        normalize_parameters(self.parameters)
        return self


def normalize_parameters(parameters):
    result = {}
    for name, quantity in parameters.items():
        if name not in PARAMETERS:
            raise ValueError(f"未定义参数：{name}；请先扩展参数字典")
        spec = PARAMETERS[name]
        if quantity.unit not in spec["units"]:
            raise ValueError(f"{spec['label']} 不支持单位 {quantity.unit}")
        scale, offset = spec["units"][quantity.unit]
        value = quantity.value * scale + offset
        import math
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{spec['label']} 转换后必须为非负有限值")
        result[name] = {"value": value, "unit": spec["unit"]}
    return result
