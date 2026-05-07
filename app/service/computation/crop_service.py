import cv2
import numpy as np
from typing import Optional, Tuple
from app.core.exceptions import CalculationError


class CropService:
    @staticmethod
    def compute_auto_crop(bgr_image: np.ndarray, white_thresh: float = 0.9) -> Tuple[int, int, int, int]:
        """
        Определяет координаты обрезки белых границ через K-means по L-каналу.
        Возвращает (top, bottom, left, right).
        """
        try:
            lab = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2Lab)
            L = lab[:, :, 0]
            data = L.reshape((-1, 1)).astype(np.float32)

            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 0.1)
            _, labels, centers = cv2.kmeans(data, 2, None, criteria, 3, cv2.KMEANS_PP_CENTERS)

            white_cluster_idx = int(np.argmax(centers))
            labels = labels.flatten()

            mask = np.zeros_like(L, dtype=np.uint8)
            mask.flat[labels == white_cluster_idx] = 255
            mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

            result = CropService._find_content_bbox(mask_bgr, white_thresh)
            if result is None:
                raise CalculationError("No content found in image — entire image appears to be background")

            _, coords = result
            return coords
        except CalculationError:
            raise
        except Exception as e:
            raise CalculationError(f"Error in auto crop: {str(e)}")

    @staticmethod
    def _find_content_bbox(
        mask_bgr: np.ndarray, white_thresh: float = 0.9
    ) -> Optional[Tuple[np.ndarray, Tuple[int, int, int, int]]]:
        mask_gray = cv2.cvtColor(mask_bgr, cv2.COLOR_BGR2GRAY)

        row_is_white = np.mean(mask_gray == 255, axis=1) > white_thresh
        col_is_white = np.mean(mask_gray == 255, axis=0) > white_thresh

        rows_with_content = np.where(~row_is_white)[0]
        cols_with_content = np.where(~col_is_white)[0]

        if rows_with_content.size == 0 or cols_with_content.size == 0:
            return None

        top = int(rows_with_content[0]) + 2
        bottom = int(rows_with_content[-1]) - 2
        left = int(cols_with_content[0]) + 2
        right = int(cols_with_content[-1]) - 2

        cropped = mask_bgr[top:bottom, left:right]
        return cropped, (top, bottom, left, right)
