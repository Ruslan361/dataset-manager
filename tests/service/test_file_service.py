import os
import pytest
from pathlib import Path

from app.service.IO.file_services import FileService

class UploadFileStub:
    def __init__(self, data: bytes, filename: str = "test.txt"):
        self._data = data
        self.filename = filename

    async def read(self):
        return self._data

@pytest.mark.asyncio
async def test_file_service_all_functions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    dataset_id = 42
    original_name = "image.png"
    data = b"binary-image-data"

    unique = FileService.generate_unique_filename(original_name)
    assert unique.endswith(".png")
    assert unique != original_name

    upload_dir = FileService.create_upload_directory(dataset_id)
    result_dir = FileService.create_result_directory(dataset_id)
    assert upload_dir.exists() and upload_dir.is_dir()
    assert result_dir.exists() and result_dir.is_dir()

    img_path = FileService.get_image_path(dataset_id, unique)
    res_path = FileService.get_result_path(dataset_id, "res.json")
    assert str(img_path).endswith(f"uploads/images/{dataset_id}/{unique}")
    assert str(res_path).endswith(f"uploads/results/{dataset_id}/res.json")

    upload_stub = UploadFileStub(data, filename=original_name)
    await FileService.save_upload_file(upload_stub, img_path)
    assert img_path.exists() and img_path.is_file()
    assert img_path.read_bytes() == data

    removed = FileService.remove_file(img_path)
    assert removed is True
    assert not img_path.exists()
    assert FileService.remove_file(img_path) is False

    sample_file = result_dir / "a.txt"
    sample_file.write_bytes(b"123")
    nested = result_dir / "nested"
    nested.mkdir()
    (nested / "b.txt").write_text("x")

    assert result_dir.exists()
    removed_dir = FileService.remove_directory(result_dir)
    assert removed_dir is True
    assert not result_dir.exists()

    uploads_root = Path("uploads")
    if uploads_root.exists():
        FileService.remove_directory(uploads_root)
