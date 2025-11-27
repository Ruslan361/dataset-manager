import pytest
import numpy as np
from unittest.mock import patch
from app.core.exceptions import InvalidGridError

# Данные для тестов
MOCK_MEANS_MATRIX = np.array([[10, 20], [30, 40]], dtype=np.float64)

@pytest.mark.asyncio
async def test_calculate_mean_lines_success(client, db_session, sample_image):
    """
    Тест успешного сценария calculate-mean-lines.
    """
    payload = {
        "vertical_lines": [50],
        "horizontal_lines": [50]
    }
    
    with patch("app.service.IO.image_service.ImageService.load_image_cv2") as mock_load, \
         patch("app.service.computation.brightness_service.BrightnessService.calculate_grid_means") as mock_calc:
        
        mock_load.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
        
        mock_calc.return_value = {
            "matrix": MOCK_MEANS_MATRIX,
            "vertical_lines": [0, 50, 100],
            "horizontal_lines": [0, 50, 100],
            "width": 100,
            "height": 100
        }

        # ДОБАВЛЕН ПРЕФИКС /manual
        response = await client.post(
            f"/manual/calculate-mean-lines/{sample_image.id}", 
            json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["means"] == [[10.0, 20.0], [30.0, 40.0]]
        assert data["image_id"] == sample_image.id


@pytest.mark.asyncio
async def test_calculate_mean_lines_image_not_found(client, db_session):
    """Тест 404, если изображения нет в БД"""
    # ДОБАВЛЕН ПРЕФИКС /manual
    response = await client.post(
        "/manual/calculate-mean-lines/999999", 
        json={"vertical_lines": [10], "horizontal_lines": [10]}
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_calculate_mean_lines_invalid_grid_error(client, db_session, sample_image):
    """
    Тест обработки бизнес-ошибки (InvalidGridError).
    """
    with patch("app.service.IO.image_service.ImageService.load_image_cv2") as mock_load, \
         patch("app.service.computation.brightness_service.BrightnessService.calculate_grid_means") as mock_calc:
        
        mock_load.return_value = np.zeros((100, 100, 3))
        mock_calc.side_effect = InvalidGridError("Line out of bounds")

        # ДОБАВЛЕН ПРЕФИКС /manual
        response = await client.post(
            f"/manual/calculate-mean-lines/{sample_image.id}",
            json={"vertical_lines": [9999], "horizontal_lines": [10]}
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "Line out of bounds"


@pytest.mark.asyncio
async def test_calculate_categorized_mean_success(client, db_session, sample_image):
    """Тест успешного сценария calculate-categorized-mean"""
    payload = {
        "imageID": sample_image.id,
        "verticalLines": [50],
        "horizontalLines": [50],
        "selectedCells": [{"row": 0, "col": 0, "categoryId": "cat1"}],
        "selectionCategories": [{"id": "cat1", "name": "Test", "color": "#000"}]
    }

    with patch("app.service.IO.image_service.ImageService.load_image_cv2") as mock_load, \
         patch("app.service.computation.brightness_service.BrightnessService.calculate_grid_means") as mock_grid, \
         patch("app.service.computation.brightness_service.BrightnessService.calculate_categorized_stats") as mock_stats:

        mock_load.return_value = np.zeros((100, 100, 3))
        
        mock_grid.return_value = {
            "matrix": MOCK_MEANS_MATRIX,
            "vertical_lines": [0, 50, 100],
            "horizontal_lines": [0, 50, 100],
            "width": 100, "height": 100
        }
        
        mock_stats.return_value = {
            "overallMean": 15.0,
            "categoryMeansAverage": 15.0,
            "categoryResults": [],
            "selectedCellsCount": 1
        }

        # ДОБАВЛЕН ПРЕФИКС /manual
        response = await client.post(
            f"/manual/calculate-categorized-mean/{sample_image.id}",
            json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["overallMean"] == 15.0


@pytest.mark.asyncio
async def test_calculate_categorized_mean_id_mismatch(client, sample_image):
    """Тест ошибки валидации: ID в URL отличается от ID в теле запроса"""
    payload = {
        "imageID": sample_image.id + 1,
        "verticalLines": [], "horizontalLines": [],
        "selectedCells": [], "selectionCategories": []
    }
    
    # ДОБАВЛЕН ПРЕФИКС /manual
    response = await client.post(
        f"/manual/calculate-categorized-mean/{sample_image.id}",
        json=payload
    )
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_manual_result(client, db_session, sample_image):
    """
    Тест получения результата (GET).
    """
    from app.service.IO.result_service import ResultService
    
    service = ResultService(db_session)
    await service.save_structured_result(
        image_id=sample_image.id,
        method_name="calculate_mean_lines",
        params={
            "vertical_lines": [0, 50, 100],
            "horizontal_lines": [0, 50, 100],
            "image_width": 100,
            "image_height": 100
        },
        data={
            "means": [[10, 20], [30, 40]]
        }
    )

    # ДОБАВЛЕН ПРЕФИКС /manual
    # Обратите внимание: эндпоинт get_manual_result также находится в manual роутере
    response = await client.get(f"/manual/result/{sample_image.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["brightness_data"] == [[10, 20], [30, 40]]