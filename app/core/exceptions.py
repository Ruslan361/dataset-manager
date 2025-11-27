class AppBaseException(Exception):
    """Базовый класс для всех ошибок приложения"""
    pass

class ResourceNotFoundError(AppBaseException):
    """Ошибка: ресурс (файл, запись в БД) не найден"""
    pass

class CalculationError(AppBaseException):
    """Общая ошибка в процессе вычислений"""
    pass

class InvalidGridError(CalculationError):
    """Ошибка: параметры сетки некорректны (выход за границы, наложение и т.д.)"""
    pass

class EmptySelectionError(CalculationError):
    """Ошибка: не выбраны данные для расчета"""
    pass

class DataMismatchError(CalculationError):
    """Ошибка: несоответствие входных данных (например, ID в URL и Body)"""
    pass