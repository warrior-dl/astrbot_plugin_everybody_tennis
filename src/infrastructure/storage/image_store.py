import asyncio
import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.infrastructure.persistence.db import get_plugin_data_root


@dataclass(slots=True)
class SavedImage:
    saved_path: str
    sha256: str


class ImageStore:
    def __init__(self, plugin_name: str):
        self._images_dir = get_plugin_data_root() / plugin_name / "images"

    async def save_image(self, source_path: str) -> SavedImage:
        source = Path(source_path).resolve()
        if not source.exists():
            raise FileNotFoundError(f"图片文件不存在: {source_path}")

        sha256 = await asyncio.to_thread(self._sha256_file, source)
        suffix = source.suffix.lower() or ".jpg"
        month_dir = self._images_dir / datetime.utcnow().strftime("%Y%m")
        month_dir.mkdir(parents=True, exist_ok=True)
        destination = month_dir / f"{sha256}{suffix}"
        if not destination.exists():
            await asyncio.to_thread(shutil.copy2, source, destination)
        return SavedImage(saved_path=str(destination), sha256=sha256)

    def _sha256_file(self, file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
