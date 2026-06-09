import cv2
import numpy as np
from app.service.image_processor import ImageProcessor
from app.core.exceptions import CalculationError
from pydantic import BaseModel

class KMeansParams(BaseModel):
    nclusters: int
    criteria_type: str  # 'epsilon', 'max iterations', 'both'
    max_iterations: int
    attempts: int
    epsilon: float
    flags_type: str  # 'pp' or 'random'
    colors: list  # List of RGB tuples

class ResultData(BaseModel):
    centers_sorted: list
    compactness: float
    processed_pixels: int
    cluster_ranges: list = []  # [{"min": float, "max": float, "range": float}, ...]
    cluster_std_dev: list = []  # [float, ...]

class KMeansResult(BaseModel):
    result_data: ResultData
    colored_image: np.ndarray
    model_config = {"arbitrary_types_allowed": True}

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
    ) -> KMeansResult:
        try:
            params: KMeansParams = KMeansParams(
                nclusters=nclusters,
                criteria_type=criteria_type,
                max_iterations=max_iterations,
                attempts=attempts,
                epsilon=epsilon,
                flags_type=flags_type,
                colors=colors
            )
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
            
            # Создание изображения + диапазоны яркости по кластерам
            height, width = L_channel.shape
            colored_image = np.zeros((height, width, 3), dtype=np.uint8)
            cluster_ranges = []
            cluster_std_dev = []

            for i in range(nclusters):
                mask = remapped_labels == i
                colored_image[mask.reshape(height, width)] = (colors[i][2], colors[i][1], colors[i][0])
                pixels = data[mask]
                if len(pixels):
                    lo, hi = float(pixels.min()), float(pixels.max())
                    cluster_ranges.append({"min": lo, "max": hi, "range": hi - lo})
                    center_value = float(sorted_centers[i])
                    mse = float(np.mean((pixels - center_value) ** 2))
                    cluster_std_dev.append(float(np.sqrt(mse)))
                else:
                    cluster_ranges.append({"min": 0.0, "max": 0.0, "range": 0.0})
                    cluster_std_dev.append(0.0)

            return KMeansResult(
                result_data=ResultData(
                    centers_sorted=sorted_centers.tolist(),
                    compactness=float(compactness),
                    processed_pixels=len(data),
                    cluster_ranges=cluster_ranges,
                    cluster_std_dev=cluster_std_dev
                ),
                colored_image=colored_image
            )
        except Exception as e:
            raise CalculationError(f"K-means error: {str(e)}")