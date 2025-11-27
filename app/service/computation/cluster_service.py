import cv2
import numpy as np
from app.service.image_processor import ImageProcessor
from app.core.exceptions import CalculationError

class ClusterService:
    @staticmethod
    def apply_kmeans(
        bgr_image: np.ndarray, 
        nclusters: int,
        criteria_type: str, # передаем enum.value или строку
        max_iterations: int,
        attempts: int,
        epsilon: float,
        flags_type: str,
        colors: list
    ) -> dict:
        try:
            processor = ImageProcessor(bgr_image)
            L_channel = processor.getLChanel()
            data = L_channel.reshape((-1, 1)).astype(np.float32)
            
            # Настройка критериев
            if criteria_type == 'epsilon':
                cv_criteria = (cv2.TERM_CRITERIA_EPS, max_iterations, epsilon)
            elif criteria_type == 'max iterations':
                cv_criteria = (cv2.TERM_CRITERIA_MAX_ITER, max_iterations, epsilon)
            else:
                cv_criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, max_iterations, epsilon)
            
            # Настройка флагов
            cv_flags = cv2.KMEANS_PP_CENTERS if flags_type == 'pp' else cv2.KMEANS_RANDOM_CENTERS
            
            # K-means
            compactness, labels, centers = cv2.kmeans(
                data, nclusters, None, cv_criteria, attempts, cv_flags
            )
            
            # Сортировка центров и переназначение меток
            centers_flat = centers.flatten()
            sorted_indices = np.argsort(centers_flat)
            sorted_centers = centers_flat[sorted_indices]
            
            label_mapping = np.zeros(nclusters, dtype=np.int32)
            label_mapping[sorted_indices] = np.arange(nclusters)
            remapped_labels = label_mapping[labels.flatten()]
            
            # Создание изображения
            height, width = L_channel.shape
            colored_image = np.zeros((height, width, 3), dtype=np.uint8)
            
            for i in range(nclusters):
                mask = remapped_labels == i
                # RGB -> BGR для OpenCV
                color_bgr = (colors[i][2], colors[i][1], colors[i][0])
                colored_image[mask.reshape(height, width)] = color_bgr
                
            return {
                "result_data": {
                    "centers_sorted": sorted_centers.tolist(),
                    "compactness": float(compactness),
                    "processed_pixels": len(data)
                },
                "colored_image": colored_image
            }
        except Exception as e:
            raise CalculationError(f"K-means error: {str(e)}")