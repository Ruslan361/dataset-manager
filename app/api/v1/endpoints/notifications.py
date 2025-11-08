from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.task_manager import task_manager
import uuid
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.websocket("/task/{task_id}/subscribe")
async def subscribe_to_task(websocket: WebSocket, task_id: str):
    """WebSocket для подписки на обновления конкретной задачи"""
    
    await websocket.accept()
    
    # Проверяем существование задачи
    task = task_manager.get_task(task_id)
    if not task:
        await websocket.send_text(json.dumps({
            "error": "Task not found",
            "task_id": task_id
        }))
        await websocket.close()
        return
    
    # Отправляем текущий статус
    current_status = task_manager.get_task_summary(task_id)
    await websocket.send_text(json.dumps({
        "type": "current_status",
        **current_status
    }))
    
    # Callback функция для отправки уведомлений
    async def send_notification(notification: dict):
        try:
            await websocket.send_text(json.dumps({
                "type": "update",
                **notification
            }))
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
    
    # Подписываемся на обновления
    task_manager.subscribe_to_task(task_id, send_notification)
    
    try:
        # Держим соединение открытым
        while True:
            try:
                # Ожидаем ping от клиента
                message = await websocket.receive_text()
                data = json.loads(message)
                
                if data.get("action") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif data.get("action") == "get_status":
                    current_status = task_manager.get_task_summary(task_id)
                    if current_status:
                        await websocket.send_text(json.dumps({
                            "type": "status_response",
                            **current_status
                        }))
                
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "error": "Invalid JSON format"
                }))
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Отписываемся при закрытии соединения
        task_manager.unsubscribe_from_task(task_id, send_notification)
        logger.info(f"Client unsubscribed from task {task_id}")

@router.websocket("/notifications/general")
async def general_notifications(websocket: WebSocket):
    """Общий WebSocket для системных уведомлений"""
    
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("action") == "get_all_tasks":
                tasks = task_manager.get_all_tasks_summary()
                await websocket.send_text(json.dumps({
                    "type": "all_tasks",
                    "tasks": tasks
                }))
            elif message.get("action") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"General WebSocket error: {e}")