"""CP-08 EXIF Extractor (Analysis 계층, 순수 로직).

책임: 촬영 시각·GPS 추출, VLM용 축소본과 EXIF를 제거한 썸네일 생성 (FR-01, DR-04, DR-08).
의존: 없음 (Pillow 라이브러리만 사용) → 단위 테스트 대상 (설계서 3.3 의존 규칙 4).
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime

from PIL import Image, ImageOps, UnidentifiedImageError

try:  # HEIC 입력 지원 (설계서 2.5: pillow-heif)
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIC_SUPPORTED = True
except Exception:  # pragma: no cover - 설치 환경에 따라 다름
    HEIC_SUPPORTED = False

SUPPORTED_FORMATS = {"JPEG", "PNG", "HEIF", "HEIC", "MPO"}

TAG_DATETIME = 0x0132
TAG_EXIF_IFD = 0x8769
TAG_GPS_IFD = 0x8825
TAG_DATETIME_ORIGINAL = 0x9003
TAG_DATETIME_DIGITIZED = 0x9004

THUMB_MAX_PX = 640  # 화면 표시용 썸네일 (DR-04)
VLM_MAX_PX = 512  # VLM 입력용 축소본 (AIR-01, AIR-07)


class UnsupportedImageError(ValueError):
    """지원하지 않는 형식이거나 이미지가 아닌 파일."""


@dataclass(frozen=True)
class PhotoMeta:
    taken_at: datetime | None
    lat: float | None
    lng: float | None
    width: int
    height: int
    format: str

    @property
    def has_gps(self) -> bool:
        return self.lat is not None and self.lng is not None


def detect_format(data: bytes) -> str:
    """파일 형식을 확인한다. 지원하지 않으면 UnsupportedImageError (FR-01)."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = (im.format or "").upper()
    except (UnidentifiedImageError, OSError) as e:
        raise UnsupportedImageError("이미지 파일이 아니에요") from e
    if fmt not in SUPPORTED_FORMATS:
        raise UnsupportedImageError(f"지원하지 않는 형식이에요 ({fmt or '알 수 없음'})")
    return fmt


def _ratio_to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        num, den = v
        return float(num) / float(den) if den else 0.0


def _dms_to_deg(dms, ref: str | None) -> float | None:
    try:
        d, m, s = (_ratio_to_float(x) for x in dms)
    except (TypeError, ValueError):
        return None
    deg = d + m / 60.0 + s / 3600.0
    if ref and ref.upper() in ("S", "W"):
        deg = -deg
    return deg


def _parse_exif_datetime(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, bytes):
        value = value.decode(errors="ignore")
    value = str(value).strip().rstrip("\x00")
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def extract_meta(data: bytes) -> PhotoMeta:
    """촬영 시각과 GPS 좌표를 읽는다. 값이 없으면 None."""
    fmt = detect_format(data)
    with Image.open(io.BytesIO(data)) as im:
        exif = im.getexif()
        width, height = im.size
        exif_ifd = exif.get_ifd(TAG_EXIF_IFD) if exif else {}
        gps_ifd = exif.get_ifd(TAG_GPS_IFD) if exif else {}

    taken_at = (
        _parse_exif_datetime(exif_ifd.get(TAG_DATETIME_ORIGINAL))
        or _parse_exif_datetime(exif_ifd.get(TAG_DATETIME_DIGITIZED))
        or _parse_exif_datetime(exif.get(TAG_DATETIME) if exif else None)
    )

    lat = lng = None
    if gps_ifd and 2 in gps_ifd and 4 in gps_ifd:
        lat = _dms_to_deg(gps_ifd.get(2), gps_ifd.get(1))
        lng = _dms_to_deg(gps_ifd.get(4), gps_ifd.get(3))
        # (0,0)이나 범위 밖 값은 위치 없음으로 본다
        if lat is None or lng is None or (abs(lat) < 1e-6 and abs(lng) < 1e-6) or abs(lat) > 90 or abs(lng) > 180:
            lat = lng = None

    return PhotoMeta(taken_at=taken_at, lat=lat, lng=lng, width=width, height=height, format=fmt)


def _resized_jpeg(data: bytes, max_px: int, quality: int) -> bytes:
    """회전 정보를 반영해 축소한 뒤 EXIF 없이 다시 인코딩한다.

    새 이미지로 다시 저장하면서 exif 인자를 넘기지 않으므로 GPS·촬영 정보가 남지 않는다 (DR-08, AC-09).
    """
    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        im.thumbnail((max_px, max_px))
        clean = Image.new("RGB", im.size)
        clean.paste(im)
    buf = io.BytesIO()
    clean.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def make_thumbnail(data: bytes) -> bytes:
    """화면·공유 카드용 EXIF 제거 썸네일."""
    return _resized_jpeg(data, THUMB_MAX_PX, 82)


def make_vlm_image(data: bytes) -> bytes:
    """VLM 입력용 축소본 (방문지당 대표 사진 1장만 사용, AIR-07)."""
    return _resized_jpeg(data, VLM_MAX_PX, 80)


def has_location_exif(jpeg: bytes) -> bool:
    """이미지에 GPS EXIF가 남아 있는지 확인 (AC-09 검증용)."""
    with Image.open(io.BytesIO(jpeg)) as im:
        exif = im.getexif()
        return bool(exif and exif.get_ifd(TAG_GPS_IFD))
