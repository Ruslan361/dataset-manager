from concurrent.futures import ThreadPoolExecutor
import os
import multiprocessing

# Оптимальное число воркеров:
# Для CPU-задач (OpenCV): число ядер
# Для IO-задач (файлы, архивы): число ядер * 2 или больше
# Возьмем сбалансированное значение:
count = multiprocessing.cpu_count()
MAX_WORKERS = max(4, count + 2)

# Создаем глобальный инстанс
# Он будет использоваться во всем приложении
global_executor = ThreadPoolExecutor(
    max_workers=MAX_WORKERS, 
    thread_name_prefix="fastapi_worker"
)

def get_executor():
    return global_executor

def shutdown_executor():
    """Корректное завершение работы пула"""
    global_executor.shutdown(wait=True)