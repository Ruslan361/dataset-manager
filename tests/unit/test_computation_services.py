import pytest
import numpy as np
import cv2
from unittest.mock import patch, MagicMock

from app.service.computation.filter_service import FilterService
from app.service.computation.cluster_service import ClusterService
from app.core.exceptions import CalculationError

# --- Фикстуры ---
@pytest.fixture
def bgr_image():
    """Создает тестовое изображение 10x10"""
    return np.zeros((10, 10, 3), dtype=np.uint8)

# --- Тесты Gaussian Blur ---

def test_gaussian_blur_success(bgr_image):
    """Тест успешного размытия и кодирования"""
    # Мы не мокаем OpenCV полностью, так как это unit тест логики
    # Проверяем, что на выходе байты
    result = FilterService.apply_gaussian_blur(
        bgr_image, 
        kernel_size=3, 
        sigma_x=1.0, 
        sigma_y=1.0, 
        apply_viridis=False
    )
    assert isinstance(result, bytes)
    assert len(result) > 0

def test_gaussian_blur_viridis(bgr_image):
    """Тест с применением цветовой карты"""
    result = FilterService.apply_gaussian_blur(
        bgr_image, 
        kernel_size=3, 
        sigma_x=0, 
        sigma_y=0, 
        apply_viridis=True
    )
    assert isinstance(result, bytes)

def test_gaussian_blur_error():
    """Тест обработки ошибок (например, битая картинка)"""
    # Передаем None вместо картинки
    with pytest.raises(CalculationError):
        FilterService.apply_gaussian_blur(None, 3, 0, 0, False)

# --- Тесты K-Means (ClusterService) ---

def test_kmeans_computation_logic(bgr_image):
    """
    Тест логики формирования структур данных K-Means.
    Мокаем тяжелые вызовы OpenCV.
    """
    n_clusters = 2
    
    # Мокаем ImageProcessor и cv2.kmeans
    with patch("app.service.computation.cluster_service.ImageProcessor") as MockProc, \
         patch("cv2.kmeans") as mock_kmeans:
             
        # Настройка мока процессора
        mock_instance = MockProc.return_value
        # L-канал 10x10
        mock_instance.getLChanel.return_value = np.zeros((10, 10), dtype=np.uint8)
        
        # Настройка мока kmeans
        # returns: (compactness, labels, centers)
        mock_labels = np.random.randint(0, n_clusters, (100, 1)).astype(np.int32)
        mock_centers = np.array([[10.0], [200.0]], dtype=np.float32)
        mock_kmeans.return_value = (100.0, mock_labels, mock_centers)
        
        # Вызов
        result = ClusterService.apply_kmeans(
            bgr_image,
            nclusters=n_clusters,
            criteria_type="all",
            max_iterations=10,
            attempts=1,
            epsilon=0.1,
            flags_type="pp",
            colors=[(255, 0, 0), (0, 255, 0)] # Red, Green
        )
        
        # Проверки
        data = result["result_data"]
        assert "colored_image" in result
        assert len(data["centers_sorted"]) == n_clusters
        # Проверяем, что центры отсортированы (10 < 200)
        assert data["centers_sorted"][0] < data["centers_sorted"][1]
        assert data["processed_pixels"] == 100