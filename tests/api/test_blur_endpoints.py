import pytest
import numpy as np
from unittest.mock import patch

@pytest.mark.asyncio
async def test_gaussian_blur_endpoint_success(client, sample_image):
    """Тест успешного вызова эндпоинта размытия"""
    
    # Мокаем загрузку и вычисления
    with patch("app.service.IO.image_service.ImageService.load_image_cv2") as mock_load, \
         patch("app.service.computation.filter_service.FilterService.apply_gaussian_blur") as mock_blur:
        
        mock_load.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_blur.return_value = b"fake_png_bytes"
        
        payload = {
            "kernel_size": 5,
            "sigma_x": 1.5,
            "apply_viridis": True
        }
        
        response = await client.post(
            f"/manual/gaussian-blur/{sample_image.id}",
            json=payload
        )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content == b"fake_png_bytes"

@pytest.mark.asyncio
async def test_gaussian_blur_image_not_found(client):
    """Тест 404"""
    response = await client.post(
        "/manual/gaussian-blur/99999",
        json={}
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_gaussian_blur_calc_error(client, sample_image):
    """Тест ошибки 500 при сбое вычислений"""
    from app.core.exceptions import CalculationError
    
    with patch("app.service.IO.image_service.ImageService.load_image_cv2") as mock_load, \
         patch("app.service.computation.filter_service.FilterService.apply_gaussian_blur") as mock_blur:
             
        mock_load.return_value = np.zeros((10, 10, 3))
        mock_blur.side_effect = CalculationError("Blur failed")
        
        response = await client.post(
            f"/manual/gaussian-blur/{sample_image.id}",
            json={}
        )
        assert response.status_code == 500
        assert "Blur failed" in response.json()["detail"]