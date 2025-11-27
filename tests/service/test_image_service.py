import pytest
import os
from pathlib import Path

import numpy as np
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import asc

from fastapi import HTTPException

from app.db.base import Base
from app.models.dataset import Dataset
from app.models.image import Image
from app.service.IO.image_service import ImageService

DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="function")
async def db_session(tmp_path, monkeypatch):
    # ensure tests run isolated from repo filesystem
    monkeypatch.chdir(tmp_path)
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()

@pytest.mark.asyncio
async def test_create_get_delete_image_flow(db_session):
    svc = ImageService(db_session)

    # create dataset record directly
    ds = Dataset(title="ds1", description="d")
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)

    # create image
    img = await svc.create_image("file.jpg", "orig.jpg", ds.id)
    assert img.id is not None
    assert img.filename == "file.jpg"
    assert img.original_filename == "orig.jpg"
    assert img.dataset_id == ds.id

    fetched = await svc.get_image_by_id(img.id)
    assert fetched is not None
    assert fetched.id == img.id

    imgs_all = await svc.get_images_by_dataset(ds.id)
    assert isinstance(imgs_all, list)
    assert any(i.id == img.id for i in imgs_all)

    deleted = await svc.delete_image(img.id)
    assert deleted.id == img.id

    after = await svc.get_image_by_id(img.id)
    assert after is None

@pytest.mark.asyncio
async def test_get_images_from_dataset_pagination_and_delete_count(db_session):
    svc = ImageService(db_session)

    ds = Dataset(title="ds2", description="d2")
    db_session.add(ds)
    await db_session.commit()
    await db_session.refresh(ds)

    # create multiple images
    for i in range(5):
        await svc.create_image(f"f{i}.png", f"orig{i}.png", ds.id)

    # use order_by asc(Image.id)
    images_page, total = await svc.get_images_from_dataset(
        dataset_id=ds.id,
        start=0,
        limit=2,
        sort_column=None,
        order_by=asc(Image.id)
    )
    assert total == 5
    assert len(images_page) == 2

    # delete_images_by_dataset should return count (implementation returns count without commit)
    count = await svc.delete_images_by_dataset(ds.id)
    assert count == 5

@pytest.mark.asyncio
async def test_file_path_validate_and_load_cv2(tmp_path, monkeypatch, db_session):
    svc = ImageService(db_session)

    # create dummy image record object with attributes used by method
    class DummyImage:
        def __init__(self, dataset_id, filename):
            self.dataset_id = dataset_id
            self.filename = filename

    img_obj = DummyImage(7, "abc.png")

    # get_image_file_path
    path = svc.get_image_file_path(img_obj)
    assert str(path).endswith(f"uploads/images/{img_obj.dataset_id}/{img_obj.filename}")

    # validate_file_exists False
    assert not svc.validate_file_exists(Path("nonexistent.png"))

    # load_image_cv2 should raise 404 when file missing
    with pytest.raises(HTTPException) as excinfo:
        svc.load_image_cv2(Path("nonexistent.png"))
    assert excinfo.value.status_code == 404

    # create empty file so validate_file_exists True, and monkeypatch cv2.imread to return array
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00")  # create file
    import cv2
    monkeypatch.setattr("app.service.IO.image_service.cv2.imread", lambda p: np.zeros((10, 20, 3), dtype=np.uint8))
    img = svc.load_image_cv2(path)
    assert isinstance(img, np.ndarray)
    assert img.shape[0] == 10 and img.shape[1] == 20

@pytest.mark.asyncio
async def test_validate_image_bounds(db_session):
    svc = ImageService(db_session)

    # create dummy numpy image with shape (height=100, width=200)
    dummy = np.zeros((100, 200, 3), dtype=np.uint8)

    # valid lines
    svc.validate_image_bounds(dummy, vertical_lines=[0, 10, 199], horizontal_lines=[0, 50, 99])

    # invalid vertical (>= width)
    with pytest.raises(HTTPException) as ev_v:
        svc.validate_image_bounds(dummy, vertical_lines=[200], horizontal_lines=[])
    assert ev_v.value.status_code == 400

    # invalid horizontal (>= height)
    with pytest.raises(HTTPException) as ev_h:
        svc.validate_image_bounds(dummy, vertical_lines=[], horizontal_lines=[100])
    assert ev_h.value.status_code == 400