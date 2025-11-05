

# Callback функция для обновления прогресса из синхронного кода
def progress_callback(task_id: str, progress: int, message: str = ""):
    """Функция для обновления прогресса из синхронного потока"""
    # Создаем корутину и запускаем в event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(task_manager.update_task_progress(task_id, progress, message))
    finally:
        loop.close()

def process_kmeans_sync(task_id: str, image_path: str, params: dict) -> dict:
    """Синхронная обработка K-means с прогресс-коллбеками"""
    import time
    import cv2
    
    try:
        # Этапы обработки с прогрессом
        stages = [
            (10, "Loading image..."),
            (30, "Converting color space..."),
            (50, "Applying K-means clustering..."),
            (80, "Processing results..."),
            (95, "Saving results...")
        ]
        
        for progress, message in stages:
            progress_callback(task_id, progress, message)
            time.sleep(1)  # Имитация работы
        
        # Здесь была бы реальная обработка изображения
        # bgr_image = cv2.imread(image_path)
        # ... K-means processing ...
        
        return {
            "success": True,
            "centers": [[255, 0, 0], [0, 255, 0], [0, 0, 255]],  # Пример
            "clusters_found": 3,
            "result_path": f"results/kmeans_{task_id}.png"
        }
        
    except Exception as e:
        logger.error(f"Error in K-means processing: {str(e)}")
        raise

async def execute_task_async(task: Task, processing_func: Callable, *args):
    """Асинхронное выполнение задачи в thread pool"""
    try:
        task.status = TaskStatus.PROCESSING
        await task_manager.send_to_client(task.client_id, {
            "type": "started",
            "task_id": task.task_id,
            "message": f"Started {task.task_type} processing"
        })
        
        # Запускаем в thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            thread_pool,
            processing_func,
            task.task_id,
            *args
        )
        
        # Завершаем задачу
        await task_manager.complete_task(task.task_id, result)
        
    except Exception as e:
        await task_manager.fail_task(task.task_id, str(e))
    finally:
        # Удаляем задачу через некоторое время
        await asyncio.sleep(60)  # Держим результат 1 минуту
        task_manager.remove_task(task.task_id)

@router.websocket("/kmeans/{image_id}")
async def kmeans_websocket(websocket: WebSocket, image_id: int):
    client_id = str(uuid.uuid4())
    
    try:
        await task_manager.connect_client(client_id, websocket)
        
        while True:
            data = await websocket.receive_text()
            request_data = json.loads(data)
            
            if request_data.get("action") == "start_kmeans":
                task_id = str(uuid.uuid4())
                
                # Создаем задачу
                task = Task(
                    task_id=task_id,
                    client_id=client_id,
                    task_type="kmeans"
                )
                
                task_manager.add_task(task)
                
                # Сообщаем клиенту что задача создана
                await task_manager.send_to_client(client_id, {
                    "type": "task_created",
                    "task_id": task_id,
                    "message": "K-means task created and queued"
                })
                
                # Запускаем выполнение асинхронно
                task.future = asyncio.create_task(
                    execute_task_async(
                        task,
                        process_kmeans_sync,
                        f"uploads/images/1/{image_id}.jpg",  # Пример пути
                        request_data.get("parameters", {})
                    )
                )
            
            elif request_data.get("action") == "cancel_task":
                task_id = request_data.get("task_id")
                task = task_manager.get_task(task_id)
                if task and task.client_id == client_id:
                    task.status = TaskStatus.CANCELLED
                    if task.future:
                        task.future.cancel()
                    await task_manager.send_to_client(client_id, {
                        "type": "cancelled",
                        "task_id": task_id
                    })
            
            elif request_data.get("action") == "get_status":
                tasks = task_manager.get_client_tasks(client_id)
                await task_manager.send_to_client(client_id, {
                    "type": "status",
                    "tasks": [
                        {
                            "task_id": task.task_id,
                            "status": task.status.value,
                            "progress": task.progress,
                            "message": task.message
                        } for task in tasks
                    ]
                })
                
    except WebSocketDisconnect:
        task_manager.disconnect_client(client_id)
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        task_manager.disconnect_client(client_id)

@router.websocket("/monitor")
async def monitor_websocket(websocket: WebSocket):
    """WebSocket для мониторинга всех задач"""
    client_id = f"monitor_{uuid.uuid4()}"
    
    try:
        await task_manager.connect_client(client_id, websocket)
        
        while True:
            await asyncio.sleep(5)
            
            # Статистика системы
            stats = {
                "type": "system_stats",
                "total_tasks": len(task_manager.tasks),
                "active_clients": len(task_manager.client_connections),
                "thread_pool_active": len([f for f in thread_pool._threads if f]) if thread_pool._threads else 0,
                "thread_pool_queue": thread_pool._work_queue.qsize(),
                "tasks_by_status": {}
            }
            
            # Группируем по статусам
            for task in task_manager.tasks.values():
                status = task.status.value
                stats["tasks_by_status"][status] = stats["tasks_by_status"].get(status, 0) + 1
            
            await task_manager.send_to_client(client_id, stats)
            
    except WebSocketDisconnect:
        task_manager.disconnect_client(client_id)