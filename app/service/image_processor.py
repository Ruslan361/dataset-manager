import cv2
import numpy as np

class ImageProcessor:
    def __init__(self, bgrImage):
        if bgrImage is None:
            raise ValueError("Изображение пусто")
        self.image = bgrImage
        self.Lchanel = self.calculateLchanel()
        
    def calculateLchanel(self):
        L_image, A, B = cv2.split(cv2.cvtColor(self.image, cv2.COLOR_BGR2LAB))
        return L_image
    
    def getLChanel(self):
        return self.Lchanel
    
    def getRGBimage(self):
        return cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)
    
    def blurGaussian(self, kernel: tuple, sigmaX: float, sigmaY: float) -> np.ndarray:
        return cv2.GaussianBlur(self.getLChanel(), kernel, sigmaX=sigmaX, sigmaY=sigmaY)
    
    def calculateMeanL(self):
        L = self.getLChanel()
        return np.mean(L)
   
    def calculateMeanRelativeToLines(self, vertical_lines: list, horizontal_lines: list):
        image = self.getLChanel()
        means = np.zeros((len(horizontal_lines) - 1, len(vertical_lines) - 1))
        for i in range(len(horizontal_lines) - 1):
            for j in range(len(vertical_lines) - 1):
                x1, x2 = vertical_lines[j], vertical_lines[j + 1]
                y1, y2 = horizontal_lines[i], horizontal_lines[i + 1]
                square = image[y1:y2, x1:x2]
                mean_luminance = np.mean(square)
                means[i, j] = mean_luminance
        return means