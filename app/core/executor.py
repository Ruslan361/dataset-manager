from concurrent.futures import ThreadPoolExecutor
import os
import multiprocessing

count = multiprocessing.cpu_count()
MAX_WORKERS = max(4, count + 2)

global_executor = ThreadPoolExecutor(
    max_workers=MAX_WORKERS, 
    thread_name_prefix="fastapi_worker"
)

def get_executor():
    return global_executor

def shutdown_executor():
    """Корректное завершение работы пула"""
    global_executor.shutdown(wait=True)