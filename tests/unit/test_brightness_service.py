import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from typing import List
from dataclasses import dataclass

from app.service.computation.brightness_service import BrightnessService
from app.core.exceptions import InvalidGridError, EmptySelectionError

# --- Фикстуры и Хелперы ---

@dataclass
class MockCell:
    row: int
    col: int
    categoryId: str
    
    # Эмуляция метода .dict() модели Pydantic, если он используется
    def dict(self):
        return {"row": self.row, "col": self.col, "categoryId": self.categoryId}

@dataclass
class MockCategory:
    id: str
    name: str
    color: str
    
    def dict(self):
        return {"id": self.id, "name": self.name, "color": self.color}

@pytest.fixture
def black_image():
    """Создает черное изображение 100x100"""
    return np.zeros((100, 100, 3), dtype=np.uint8)

@pytest.fixture
def split_image():
    """
    Создает изображение 100x100:
    Левая половина (0-50) - Черная (0)
    Правая половина (50-100) - Белая (255)
    """
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[:, 50:] = 255  # BGR: White
    return img

# --- Тесты: calculate_grid_means ---

def test_grid_means_validation_bounds(black_image):
    """Тест валидации: линии выходят за границы изображения"""
    # Ширина 100. Линия 150 - ошибка.
    with pytest.raises(InvalidGridError, match="within image width"):
        BrightnessService.calculate_grid_means(
            black_image, 
            vertical_lines=[150], 
            horizontal_lines=[10]
        )

    # Высота 100. Линия -5 - ошибка.
    with pytest.raises(InvalidGridError, match="within image height"):
        BrightnessService.calculate_grid_means(
            black_image, 
            vertical_lines=[10], 
            horizontal_lines=[-5]
        )

def test_grid_means_validation_non_numeric(black_image):
    """Тест валидации: переданы нечисловые значения"""
    with pytest.raises(InvalidGridError, match="must be numeric"):
        BrightnessService.calculate_grid_means(
            black_image,
            vertical_lines=["invalid"],
            horizontal_lines=[10]
        )

def test_grid_means_auto_boundaries(black_image):
    """
    Тест логики: сервис должен сам добавлять 0 и max_size, 
    а также сортировать линии.
    """
    # Мы мокаем ImageProcessor, так как здесь проверяем только подготовку линий
    with patch("app.service.computation.brightness_service.ImageProcessor") as MockProcessor:
        # Настраиваем мок, чтобы он возвращал фиктивную матрицу
        mock_instance = MockProcessor.return_value
        mock_instance.calculateMeanRelativeToLines.return_value = np.zeros((2, 2))

        result = BrightnessService.calculate_grid_means(
            black_image,
            vertical_lines=[50],    # Должен добавить 0 и 100
            horizontal_lines=[80, 20] # Должен добавить 0 и 100 и отсортировать
        )

        # Проверяем, что вернул сервис
        assert result["vertical_lines"] == [0, 50, 100]
        assert result["horizontal_lines"] == [0, 20, 80, 100]
        assert result["width"] == 100
        assert result["height"] == 100
        
        # Проверяем, с какими аргументами был вызван ImageProcessor
        mock_instance.calculateMeanRelativeToLines.assert_called_once_with(
            vertical_lines=[0, 50, 100],
            horizontal_lines=[0, 20, 80, 100]
        )

def test_grid_means_calculation_logic(split_image):
    """
    Интеграционный тест логики (с реальным ImageProcessor, если он импортирован корректно).
    Проверяем, что матрица считается правильно на черно-белом изображении.
    """
    # Если ImageProcessor требует сложной настройки OpenCV, этот тест может упасть.
    # Но предполагается, что код ImageProcessor корректен.
    
    # Изображение: 0-50 черное, 50-100 белое.
    # Делим линиями [50] по вертикали.
    
    result = BrightnessService.calculate_grid_means(
        split_image,
        vertical_lines=[50],
        horizontal_lines=[50]
    )
    
    matrix = result["matrix"]
    
    # Ожидаем сетку 2x2
    # Ячейка [0,0] (Top-Left): Черная -> Mean ~ 0
    # Ячейка [0,1] (Top-Right): Белая -> Mean ~ 255
    # Ячейка [1,0] (Bottom-Left): Черная -> Mean ~ 0
    # Ячейка [1,1] (Bottom-Right): Белая -> Mean ~ 255
    
    assert matrix.shape == (2, 2)
    assert matrix[0, 0] == 0.0
    assert matrix[0, 1] == 255.0
    assert matrix[1, 0] == 0.0
    assert matrix[1, 1] == 255.0

# --- Тесты: calculate_categorized_stats ---

def test_categorized_stats_empty_selection():
    """Ошибка, если не выбраны ячейки"""
    with pytest.raises(EmptySelectionError):
        BrightnessService.calculate_categorized_stats(
            means_matrix=np.zeros((5, 5)),
            selected_cells=[],
            categories=[],
            max_rows=5,
            max_cols=5
        )

def test_categorized_stats_bounds():
    """Ошибка, если ячейка за пределами матрицы"""
    cells = [MockCell(row=10, col=0, categoryId="cat1")]
    
    with pytest.raises(InvalidGridError, match="out of bounds"):
        BrightnessService.calculate_categorized_stats(
            means_matrix=np.zeros((5, 5)),
            selected_cells=cells,
            categories=[],
            max_rows=5,
            max_cols=5
        )

def test_categorized_stats_missing_category():
    """Ошибка, если у ячейки ID категории, которого нет в списке"""
    cells = [MockCell(row=0, col=0, categoryId="unknown_cat")]
    categories = [MockCategory(id="cat1", name="Cat 1", color="#fff")]
    
    with pytest.raises(InvalidGridError, match="not found"):
        BrightnessService.calculate_categorized_stats(
            means_matrix=np.zeros((2, 2)),
            selected_cells=cells,
            categories=categories,
            max_rows=2,
            max_cols=2
        )

def test_categorized_stats_calculation():
    """
    Проверка правильности подсчета средних значений.
    """
    # Матрица 2x2:
    # [ 10, 20 ]
    # [ 30, 40 ]
    matrix = np.array([
        [10.0, 20.0],
        [30.0, 40.0]
    ])
    
    # Категории
    cat_A = MockCategory(id="A", name="Category A", color="red")
    cat_B = MockCategory(id="B", name="Category B", color="blue")
    
    # Выбор ячеек:
    # Категория А: [0,0] (10) и [1,1] (40). Среднее = 25.
    # Категория B: [0,1] (20). Среднее = 20.
    cells = [
        MockCell(row=0, col=0, categoryId="A"),
        MockCell(row=1, col=1, categoryId="A"),
        MockCell(row=0, col=1, categoryId="B")
    ]
    
    result = BrightnessService.calculate_categorized_stats(
        means_matrix=matrix,
        selected_cells=cells,
        categories=[cat_A, cat_B],
        max_rows=2,
        max_cols=2
    )
    
    # Проверка общего среднего
    # Выбраны значения: 10, 40, 20. Среднее: (70 / 3) = 23.333...
    assert result["overallMean"] == pytest.approx(23.333, 0.01)
    
    # Проверка среднего средних категорий
    # Кат А mean: 25. Кат B mean: 20. Среднее: 22.5
    assert result["categoryMeansAverage"] == pytest.approx(22.5, 0.01)
    
    # Проверка результатов по категориям
    results = result["categoryResults"]
    assert len(results) == 2
    
    # Проверяем Категорию А (она может быть не первой, поэтому ищем)
    res_A = next(r for r in results if r["categoryId"] == "A")
    assert res_A["meanValue"] == 25.0
    assert res_A["cellCount"] == 2
    
    # Проверка Row Means для категории А
    # Row 0: ячейка [0,0] = 10. -> Mean 10
    # Row 1: ячейка [1,1] = 40. -> Mean 40
    # Ожидаем [10.0, 40.0]
    assert res_A["rowMeans"] == [10.0, 40.0]
    assert res_A["rowMeansAverage"] == 25.0

    # Проверяем Категорию B
    res_B = next(r for r in results if r["categoryId"] == "B")
    assert res_B["meanValue"] == 20.0
    
    # Проверка Row Means для категории B
    # Row 0: ячейка [0,1] = 20. -> Mean 20
    # Row 1: нет ячеек -> None
    # Ожидаем [20.0, None]
    assert res_B["rowMeans"] == [20.0, None]
    assert res_B["rowMeansAverage"] == 20.0