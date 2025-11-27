from typing import List, Dict, Any, Optional
import numpy as np
from app.service.image_processor import ImageProcessor
from app.core.exceptions import InvalidGridError, EmptySelectionError

class BrightnessService:
    """
    Сервис для математических расчетов яркости и статистики.
    Не взаимодействует с БД.
    """

    @staticmethod
    def calculate_grid_means(
        bgr_image: np.ndarray, 
        vertical_lines: List[float], 
        horizontal_lines: List[float]
    ) -> Dict[str, Any]:
        """
        Расчет матрицы средних значений яркости по сетке.
        """
        height, width = bgr_image.shape[:2]
        
        # 1. Валидация и конвертация линий
        try:
            v_lines_int = [int(round(x)) for x in vertical_lines]
            h_lines_int = [int(round(x)) for x in horizontal_lines]
        except (ValueError, TypeError):
            raise InvalidGridError("Lines must be numeric values")

        # Проверка границ
        if any(x < 0 or x > width for x in v_lines_int):
            raise InvalidGridError(f"Vertical lines must be within image width (0-{width})")
        if any(y < 0 or y > height for y in h_lines_int):
            raise InvalidGridError(f"Horizontal lines must be within image height (0-{height})")
            
        # 2. Подготовка финальных границ (добавляем 0 и max, убираем дубли, сортируем)
        final_v_lines = sorted(list(set([0] + v_lines_int + [width])))
        final_h_lines = sorted(list(set([0] + h_lines_int + [height])))
        
        # Сетка должна образовывать хотя бы одну ячейку (минимум 2 линии по каждой оси)
        if len(final_v_lines) < 2 or len(final_h_lines) < 2:
            raise InvalidGridError("Grid must define at least one cell (min 2 lines per axis)")

        # 3. Вычисления через ImageProcessor
        # (Предполагается, что ImageProcessor уже существует и работает корректно)
        processor = ImageProcessor(bgr_image)
        means_matrix = processor.calculateMeanRelativeToLines(
            vertical_lines=final_v_lines,
            horizontal_lines=final_h_lines
        )
        
        return {
            "matrix": means_matrix,
            "vertical_lines": final_v_lines,
            "horizontal_lines": final_h_lines,
            "width": width,
            "height": height
        }

    @staticmethod
    def calculate_categorized_stats(
        means_matrix: np.ndarray,
        selected_cells: List[Any],  # List[SelectedCell] pydantic models
        categories: List[Any],      # List[SelectionCategory] pydantic models
        max_rows: int,
        max_cols: int
    ) -> Dict[str, Any]:
        """
        Расчет статистики по выбранным категориям.
        """
        if not selected_cells:
            # Можно вернуть пустой результат или ошибку, в зависимости от бизнес-логики
            # Здесь выкинем ошибку, так как считать нечего
            raise EmptySelectionError("No cells selected for calculation")

        # Проверка границ ячеек
        for cell in selected_cells:
            if not (0 <= cell.row < max_rows):
                raise InvalidGridError(f"Cell row {cell.row} out of bounds (0-{max_rows-1})")
            if not (0 <= cell.col < max_cols):
                raise InvalidGridError(f"Cell col {cell.col} out of bounds (0-{max_cols-1})")

        # Создание словаря категорий для быстрого доступа
        categories_dict = {cat.id: cat for cat in categories}
        
        # Группировка ячеек
        category_cells_map = {}
        for cell in selected_cells:
            if cell.categoryId not in category_cells_map:
                category_cells_map[cell.categoryId] = []
            category_cells_map[cell.categoryId].append(cell)
            
        category_results = []
        all_selected_values = []
        category_means_for_overall = []

        # Обработка каждой категории
        for category_id, cells in category_cells_map.items():
            if category_id not in categories_dict:
                raise InvalidGridError(f"Category ID '{category_id}' not found in definitions")
            
            category = categories_dict[category_id]
            category_values = []
            cell_coords = []
            rows_dict = {} # Для расчета средних по строкам внутри категории

            for cell in cells:
                # Получаем значение из матрицы яркости
                value = means_matrix[cell.row, cell.col]
                category_values.append(value)
                all_selected_values.append(value)
                cell_coords.append({"row": cell.row, "col": cell.col})
                
                if cell.row not in rows_dict:
                    rows_dict[cell.row] = []
                rows_dict[cell.row].append(value)

            if category_values:
                cat_mean = float(np.mean(category_values))
                category_means_for_overall.append(cat_mean)
                
                # Расчет средних по строкам (Row Means)
                row_means = []
                valid_row_means = []
                
                for r in range(max_rows):
                    if r in rows_dict:
                        rm = float(np.mean(rows_dict[r]))
                        row_means.append(rm)
                        valid_row_means.append(rm)
                    else:
                        row_means.append(None)
                
                row_means_avg = float(np.mean(valid_row_means)) if valid_row_means else None

                category_results.append({
                    "categoryId": category_id,
                    "categoryName": category.name,
                    "color": category.color,
                    "meanValue": cat_mean,
                    "cellCount": len(cells),
                    "cells": cell_coords,
                    "rowMeans": row_means,
                    "rowMeansAverage": row_means_avg
                })

        overall_mean = float(np.mean(all_selected_values)) if all_selected_values else None
        cat_means_avg = float(np.mean(category_means_for_overall)) if category_means_for_overall else None

        return {
            "overallMean": overall_mean,
            "categoryMeansAverage": cat_means_avg,
            "categoryResults": category_results,
            "selectedCellsCount": len(selected_cells)
        }