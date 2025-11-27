import cv2
import numpy as np
from app.service.image_processor import ImageProcessor
from app.core.exceptions import CalculationError

class FilterService:
    @staticmethod
    def apply_gaussian_blur(bgr_image: np.ndarray, kernel_size: int, sigma_x: float, sigma_y: float, apply_viridis: bool) -> bytes:
        """Применяет размытие и возвращает закодированные байты изображения"""
        try:
            processor = ImageProcessor(bgr_image)
            kernel = (kernel_size, kernel_size)
            
            blurred_l_channel = processor.blurGaussian(
                kernel=kernel,
                sigmaX=sigma_x,
                sigmaY=sigma_y
            )
            
            if apply_viridis:
                normalized = cv2.normalize(blurred_l_channel, None, 0, 255, cv2.NORM_MINMAX)
                normalized = normalized.astype(np.uint8)
                colored = cv2.applyColorMap(normalized, cv2.COLORMAP_VIRIDIS)
                success, encoded = cv2.imencode('.png', colored)
            else:
                success, encoded = cv2.imencode('.png', blurred_l_channel)
                
            if not success:
                raise CalculationError("Failed to encode processed image")
                
            return encoded.tobytes()
        except Exception as e:
            raise CalculationError(f"Error in gaussian blur: {str(e)}")