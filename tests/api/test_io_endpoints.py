"""
Интеграционные тесты IO-эндпоинтов через HTTP-клиент.
Каждый тест — один запрос, проверка статуса и тела ответа.
"""
import io
import json
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from app.models.dataset import Dataset
from app.models.image import Image


# ─────────────────────────────────────────────
# DATASET ENDPOINTS
# ─────────────────────────────────────────────

class TestCreateDataset:
    @pytest.mark.asyncio
    async def test_create_returns_success(self, io_client):
        r = await io_client.post("/dataset/create-dataset", json={"title": "DS1", "description": "desc"})
        assert r.status_code == 200
        assert r.json()["success"] is True
        assert "DS1" in r.json()["message"]

    @pytest.mark.asyncio
    async def test_create_without_description(self, io_client):
        r = await io_client.post("/dataset/create-dataset", json={"title": "NoDesc"})
        assert r.status_code == 200
        assert r.json()["success"] is True

    @pytest.mark.asyncio
    async def test_create_missing_title_returns_422(self, io_client):
        r = await io_client.post("/dataset/create-dataset", json={"description": "only desc"})
        assert r.status_code == 422


class TestGetDatasetsList:
    @pytest.mark.asyncio
    async def test_empty_list(self, io_client):
        r = await io_client.post("/dataset/get-datasets-list", json={"start": 0, "end": 10})
        assert r.status_code == 200
        assert r.json()["datasets"] == []

    @pytest.mark.asyncio
    async def test_returns_created_datasets(self, io_client):
        await io_client.post("/dataset/create-dataset", json={"title": "A", "description": "a"})
        await io_client.post("/dataset/create-dataset", json={"title": "B", "description": "b"})
        r = await io_client.post("/dataset/get-datasets-list", json={"start": 0, "end": 10})
        assert r.status_code == 200
        assert len(r.json()["datasets"]) == 2

    @pytest.mark.asyncio
    async def test_pagination_limits_results(self, io_client):
        for i in range(5):
            await io_client.post("/dataset/create-dataset", json={"title": f"D{i}", "description": "x"})
        r = await io_client.post("/dataset/get-datasets-list", json={"start": 0, "end": 2})
        assert r.status_code == 200
        assert len(r.json()["datasets"]) == 2

    @pytest.mark.asyncio
    async def test_invalid_range_returns_422(self, io_client):
        # end <= start
        r = await io_client.post("/dataset/get-datasets-list", json={"start": 5, "end": 5})
        assert r.status_code == 422


class TestUpdateDataset:
    @pytest.mark.asyncio
    async def test_update_title(self, io_client):
        await io_client.post("/dataset/create-dataset", json={"title": "Old", "description": "d"})
        r_list = await io_client.post("/dataset/get-datasets-list", json={"start": 0, "end": 5})
        ds_id = r_list.json()["datasets"][0]["id"]

        r = await io_client.put(f"/dataset/update-dataset/{ds_id}", json={"title": "New"})
        assert r.status_code == 200
        assert r.json()["title"] == "New"

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_404(self, io_client):
        r = await io_client.put("/dataset/update-dataset/9999", json={"title": "X"})
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_update_with_no_fields_returns_400(self, io_client):
        await io_client.post("/dataset/create-dataset", json={"title": "T", "description": "d"})
        r_list = await io_client.post("/dataset/get-datasets-list", json={"start": 0, "end": 5})
        ds_id = r_list.json()["datasets"][0]["id"]

        r = await io_client.put(f"/dataset/update-dataset/{ds_id}", json={})
        assert r.status_code == 400


class TestDeleteDataset:
    @pytest.mark.asyncio
    async def test_delete_existing(self, io_client):
        await io_client.post("/dataset/create-dataset", json={"title": "ToDelete", "description": "d"})
        r_list = await io_client.post("/dataset/get-datasets-list", json={"start": 0, "end": 5})
        ds_id = r_list.json()["datasets"][0]["id"]

        r = await io_client.delete(f"/dataset/remove-dataset/{ds_id}")
        assert r.status_code == 200
        assert r.json()["success"] is True

        # Проверяем что исчез из списка
        r_after = await io_client.post("/dataset/get-datasets-list", json={"start": 0, "end": 5})
        assert len(r_after.json()["datasets"]) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, io_client):
        r = await io_client.delete("/dataset/remove-dataset/9999")
        assert r.status_code == 404


# ─────────────────────────────────────────────
# IMAGE ENDPOINTS
# ─────────────────────────────────────────────

class TestGetImageInfo:
    @pytest.mark.asyncio
    async def test_get_existing_image(self, io_client, db_session):
        ds = Dataset(title="DS", description="d")
        db_session.add(ds)
        await db_session.commit()
        await db_session.refresh(ds)
        img = Image(filename="f.jpg", original_filename="orig.jpg", dataset_id=ds.id)
        db_session.add(img)
        await db_session.commit()
        await db_session.refresh(img)

        r = await io_client.get(f"/image/image/{img.id}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == img.id
        assert body["filename"] == "f.jpg"
        assert body["original_filename"] == "orig.jpg"
        assert body["dataset_id"] == ds.id

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(self, io_client):
        r = await io_client.get("/image/image/9999")
        assert r.status_code == 404


class TestGetImagesList:
    @pytest.mark.asyncio
    async def test_returns_images_for_dataset(self, io_client, db_session):
        ds = Dataset(title="DS", description="d")
        db_session.add(ds)
        await db_session.commit()
        await db_session.refresh(ds)
        for i in range(3):
            db_session.add(Image(filename=f"f{i}.jpg", original_filename=f"o{i}.jpg", dataset_id=ds.id))
        await db_session.commit()

        r = await io_client.post(f"/dataset/get-images-list/{ds.id}", json={"start": 0, "end": 10})
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        assert len(body["images"]) == 3
        assert body["dataset_id"] == ds.id

    @pytest.mark.asyncio
    async def test_pagination_works(self, io_client, db_session):
        ds = Dataset(title="DS2", description="d")
        db_session.add(ds)
        await db_session.commit()
        await db_session.refresh(ds)
        for i in range(5):
            db_session.add(Image(filename=f"p{i}.jpg", original_filename=f"p{i}.jpg", dataset_id=ds.id))
        await db_session.commit()

        r = await io_client.post(f"/dataset/get-images-list/{ds.id}", json={"start": 0, "end": 2})
        assert r.status_code == 200
        assert len(r.json()["images"]) == 2

    @pytest.mark.asyncio
    async def test_nonexistent_dataset_returns_404(self, io_client):
        r = await io_client.post("/dataset/get-images-list/9999", json={"start": 0, "end": 10})
        assert r.status_code == 404


class TestUploadImage:
    @pytest.mark.asyncio
    async def test_upload_success(self, io_client, db_session, tmp_path):
        ds = Dataset(title="DS", description="d")
        db_session.add(ds)
        await db_session.commit()
        await db_session.refresh(ds)

        fake_png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
            b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
            b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        with patch("app.service.IO.file_services.FileService.create_upload_directory") as mock_dir, \
             patch("app.service.IO.file_services.FileService.save_upload_file", new_callable=AsyncMock) as mock_save, \
             patch("app.service.IO.file_services.FileService.generate_unique_filename", return_value="unique.png"):
            mock_dir.return_value = tmp_path

            form_data_str = json.dumps({"title": "img", "dataset_id": ds.id})
            r = await io_client.post(
                "/image/upload",
                files={"file": ("test.png", io.BytesIO(fake_png), "image/png")},
                data={"form_data": form_data_str},
            )

        assert r.status_code == 200
        assert r.json()["success"] is True
        assert "image_id" in r.json()["data"]

    @pytest.mark.asyncio
    async def test_upload_non_image_returns_400(self, io_client, db_session):
        ds = Dataset(title="DS", description="d")
        db_session.add(ds)
        await db_session.commit()
        await db_session.refresh(ds)

        form_data_str = json.dumps({"title": "txt", "dataset_id": ds.id})
        r = await io_client.post(
            "/image/upload",
            files={"file": ("doc.txt", io.BytesIO(b"hello"), "text/plain")},
            data={"form_data": form_data_str},
        )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_invalid_form_data_returns_400(self, io_client):
        r = await io_client.post(
            "/image/upload",
            files={"file": ("img.png", io.BytesIO(b"\x89PNG"), "image/png")},
            data={"form_data": "not-json"},
        )
        assert r.status_code == 400


class TestRemoveImage:
    @pytest.mark.asyncio
    async def test_remove_existing_image(self, io_client, db_session):
        ds = Dataset(title="DS", description="d")
        db_session.add(ds)
        await db_session.commit()
        await db_session.refresh(ds)
        img = Image(filename="del.jpg", original_filename="del.jpg", dataset_id=ds.id)
        db_session.add(img)
        await db_session.commit()
        await db_session.refresh(img)

        with patch("app.service.IO.file_services.FileService.remove_file", return_value=True):
            r = await io_client.delete(f"/image/remove-image/{img.id}")

        assert r.status_code == 200
        assert r.json()["success"] is True

        r_info = await io_client.get(f"/image/image/{img.id}")
        assert r_info.status_code == 404

    @pytest.mark.asyncio
    async def test_remove_nonexistent_returns_404(self, io_client):
        r = await io_client.delete("/image/remove-image/9999")
        assert r.status_code == 404


class TestDownloadImage:
    @pytest.mark.asyncio
    async def test_download_returns_file(self, io_client, db_session, tmp_path):
        ds = Dataset(title="DS", description="d")
        db_session.add(ds)
        await db_session.commit()
        await db_session.refresh(ds)
        img = Image(filename="photo.jpg", original_filename="photo.jpg", dataset_id=ds.id)
        db_session.add(img)
        await db_session.commit()
        await db_session.refresh(img)

        fake_file = tmp_path / "photo.jpg"
        fake_file.write_bytes(b"FAKEJPEG")

        with patch("app.service.IO.image_service.ImageService.get_image_file_path", return_value=fake_file), \
             patch("app.service.IO.image_service.ImageService.validate_file_exists", return_value=True):
            r = await io_client.get(f"/image/download-image/{img.id}")

        assert r.status_code == 200
        assert r.content == b"FAKEJPEG"

    @pytest.mark.asyncio
    async def test_download_missing_file_returns_404(self, io_client, db_session):
        ds = Dataset(title="DS", description="d")
        db_session.add(ds)
        await db_session.commit()
        await db_session.refresh(ds)
        img = Image(filename="ghost.jpg", original_filename="ghost.jpg", dataset_id=ds.id)
        db_session.add(img)
        await db_session.commit()
        await db_session.refresh(img)

        with patch("app.service.IO.image_service.ImageService.validate_file_exists", return_value=False):
            r = await io_client.get(f"/image/download-image/{img.id}")

        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_download_nonexistent_image_returns_404(self, io_client):
        r = await io_client.get("/image/download-image/9999")
        assert r.status_code == 404
