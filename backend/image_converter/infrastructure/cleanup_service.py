import os
import shutil
import time
import traceback
from typing import Callable

from backend.image_converter.application.dtos import (
    CleanedItem,
    CleanupError,
    CleanupSummary,
    ContainerFile,
    ContainerInventory,
)
from backend.image_converter.core.exceptions import ConversionError
from backend.image_converter.domain.units import BYTES_PER_MEBIBYTE


_KIND_DIRECTORY = "directory"
_KIND_ZIP = "zip"
_ZIP_FOLDER_LABEL = "zip"


class CleanupService:
    """Deletes expired temp conversion folders/ZIPs and reports what was kept."""

    def __init__(self, temp_dir: str, expiration_time: int, logger):
        self.temp_dir = temp_dir
        self.expiration_time = expiration_time
        self.logger = logger

    def cleanup_temp_folders(self, force: bool = False) -> CleanupSummary:
        summary = CleanupSummary()
        current_time = time.time()

        for item in os.listdir(self.temp_dir):
            item_path = os.path.join(self.temp_dir, item)
            if os.path.isdir(item_path) and item.startswith(("source_", "converted_")):
                self._record_cleanup_outcome(
                    summary, _KIND_DIRECTORY, item_path,
                    lambda: self._maybe_delete_dir(item_path, force, current_time),
                )
            elif (
                os.path.isfile(item_path)
                and item.startswith("converted_")
                and item.endswith(".zip")
            ):
                self._record_cleanup_outcome(
                    summary, _KIND_ZIP, item_path,
                    lambda: self._maybe_delete_zip(item_path, force, current_time),
                )

        return summary

    def get_container_files(self) -> ContainerInventory:
        files: list[ContainerFile] = []
        total_size = 0.0

        self.logger.log(f"Scanning TEMP_DIR: {self.temp_dir}", "info")

        for folder in os.listdir(self.temp_dir):
            folder_path = os.path.join(self.temp_dir, folder)
            if os.path.isdir(folder_path) and folder.startswith("converted_"):
                for fname in os.listdir(folder_path):
                    file_path = os.path.join(folder_path, fname)
                    if os.path.isfile(file_path):
                        size_mb = self._file_size_mb(file_path)
                        files.append(ContainerFile(
                            folder=folder,
                            folder_path=folder_path,
                            filename=fname,
                            size_mb=size_mb,
                        ))
                        total_size += size_mb

        for fname in os.listdir(self.temp_dir):
            if fname.startswith("converted_") and fname.endswith(".zip"):
                file_path = os.path.join(self.temp_dir, fname)
                if os.path.isfile(file_path):
                    size_mb = self._file_size_mb(file_path)
                    files.append(ContainerFile(
                        folder=_ZIP_FOLDER_LABEL,
                        folder_path=self.temp_dir,
                        filename=fname,
                        size_mb=size_mb,
                    ))
                    total_size += size_mb

        inventory = ContainerInventory(
            files=files,
            total_size_mb=round(total_size, 2),
            total_count=len(files),
        )
        self.logger.log(
            f"Total files found: {inventory.total_count}, "
            f"total size: {inventory.total_size_mb} MB",
            "info",
        )
        return inventory

    def _maybe_delete_dir(
        self,
        dir_path: str,
        force: bool,
        current_time: float,
    ) -> bool:
        try:
            creation_time = os.path.getctime(dir_path)
            if force or (current_time - creation_time > self.expiration_time):
                shutil.rmtree(dir_path, ignore_errors=True)
                self.logger.log(f"Deleted temp folder: {dir_path}", "info")
                return True
            return False
        except Exception:
            tb = traceback.format_exc()
            self.logger.log(f"Error deleting folder {dir_path}: {tb}", "error")
            raise ConversionError(tb) from None

    def _maybe_delete_zip(
        self,
        zip_path: str,
        force: bool,
        current_time: float,
    ) -> bool:
        try:
            creation_time = os.path.getctime(zip_path)
            if force or (current_time - creation_time > self.expiration_time):
                os.remove(zip_path)
                self.logger.log(f"Deleted ZIP file: {zip_path}", "info")
                return True
            return False
        except Exception:
            tb = traceback.format_exc()
            self.logger.log(f"Error deleting ZIP file {zip_path}: {tb}", "error")
            raise ConversionError(tb) from None

    @staticmethod
    def _record_cleanup_outcome(
        summary: CleanupSummary,
        kind: str,
        path: str,
        action: Callable[[], bool],
    ) -> None:
        try:
            if action():
                summary.deleted.append(CleanedItem(kind=kind, path=path))
        except ConversionError as exc:
            summary.errors.append(CleanupError(kind=kind, path=path, error=str(exc)))

    @staticmethod
    def _file_size_mb(path: str) -> float:
        return round(os.path.getsize(path) / BYTES_PER_MEBIBYTE, 2)
