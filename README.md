**Project Overview**

- **Name**: FastAPI Image Processor (dataset-manager repository)
- **Purpose**: Сервер для загрузки изображений, выполнения анализа (например, K-means кластеризация, размытие, усреднение линий, обрезка и др.) и хранения результатов в БД + файловой системе.

**Quick Summary**
- **Backend**: FastAPI application (entry point: `main.py`).
- **DB**: SQLAlchemy async (по умолчанию sqlite via `aiosqlite`), конфиг в `app/core/config.py`.
- **Long-running processing**: CPU-bound операции выполняются в пуле потоков (executor) и запускаются как фоновые задачи, результаты сохраняются на диск в `uploads/results/<dataset_id>` и в БД через `ResultService`.

**Repository Layout (важные директории)**
- `app/` : основная логика приложения
	- `api/v1/endpoints/` : HTTP endpoints (включая `analysis/k_means.py`)
	- `core/` : конфигурация, исключения, executor, lifecycle
	- `db/` : инициализация БД, сессии
	- `service/` : бизнес-логика и обработчики изображений
	- `models/`, `schemas/`, `crud/` : ORM и схемы
- `uploads/` : хранилище загруженных изображений и результатов
- `tests/` : тесты (pytest)

**Environment & Dependencies**
- **Python**: проект совместим с Python 3.10+ (virtualenv recommended).
- **Install deps**: `pip install -r req.txt` (используется файл `req.txt`).
- **Configuration**: переменные окружения читаются через `pydantic-settings` и `.env` (см. `app/core/config.py`). По умолчанию `DATABASE_URL` указывает на sqlite `sqlite+aiosqlite:///./app.db`.

**Run locally**
- Create and activate a virtual environment (zsh example):
	- `python -m venv .venv`
	- `source .venv/bin/activate`
	- `pip install -r req.txt`
- Run the app (development):
	- `uvicorn main:app --reload --host 0.0.0.0 --port 8000`
- The application exposes API under the prefix `/api/v1` (see `main.py`).

**Database initialization**
- The app calls `init_db()` during startup (see `main.py` lifespan). If you want to reset DB manually, delete `app.db` (if using sqlite) or set `DATABASE_URL` to your DB.
- If you use migrations (alembic is in requirements) — configure and run them according to your workflow.

**Key concepts and behaviour**
- **Background tasks & executor**: Heavy CPU-bound image processing (OpenCV, clustering) runs in a thread-pool executor to avoid blocking the asyncio event loop. The executor is provided by `app.core.executor` and shutdown on app stop.
- **DB sessions in background**: Background tasks open their own `AsyncSessionLocal()` to update results because request-scoped sessions (from `Depends`) are closed after the response.
- **Result storage**: Processed images are saved to `uploads/results/<dataset_id>/` with filenames like `<image_id>_kmeans_<nclusters>.jpg` and metadata saved via `ResultService`.

**API: K-means endpoints (example)**
Note: the routing structure currently mounts the analysis endpoints as follows:

- Base route for API: `/api/v1`
- Analysis router prefix: `/analysis` (see `app/api/v1/api.py`)
- `analysis` subrouter mounts k-means router under `/kmeans` (see `app/api/v1/endpoints/analysis/api.py`).

Important: the `k_means.py` endpoint paths also include `kmeans` in their route definitions. As a result, the effective endpoint paths are (as implemented):

- POST queue K-means job: `POST /api/v1/analysis/kmeans/kmeans/{image_id}`
- GET metadata/status: `GET  /api/v1/analysis/kmeans/kmeans/{image_id}/result`
- GET result image file: `GET /api/v1/analysis/kmeans/kmeans/{image_id}/result/image`

If you prefer shorter paths, remove the duplicated `kmeans` either from `analysis/api.py` or from the route definitions in `k_means.py`.

Example: Queue a K-means processing job (cURL)

```
curl -X POST "http://localhost:8000/api/v1/analysis/kmeans/kmeans/123" \
	-H "Content-Type: application/json" \
	-d '{
		"nclusters": 3,
		"criteria": "all",
		"max_iterations": 100,
		"attempts": 5,
		"epsilon": 0.5,
		"flags": "pp",
		"colors": [[255,0,0],[0,255,0],[0,0,255]]
	}'
```

Notes about the request body (KMeansRequest):
- `nclusters` (int): количество кластеров.
- `criteria` (string): одно из `"epsilon"`, `"max iterations"`, `"all"`.
- `flags` (string): `"pp"` (kmeans++) или `"random"`.
- `colors`: массив RGB-цветов по количеству кластеров — передавайте как массивы (JSON не поддерживает кортежи): e.g. `[[255,0,0],[0,255,0],[0,0,255]]`.

Response (when queued)
- A successful enqueue returns JSON like:
	- `{"success": true, "message": "K-means task queued", "image_id": <id>, "result_id": <id>, "status": "processing"}`

Check status and retrieve result
- `GET /api/v1/analysis/kmeans/kmeans/{image_id}/result` — возвращает JSON с полем `status` (`processing`|`completed`|`failed`). Если `completed`, в ответе будет поле `has_result_image: true` и информация о ресурсах (путь к файлу).
- `GET /api/v1/analysis/kmeans/kmeans/{image_id}/result/image` — скачивает результат в формате `image/jpeg`.

**Where results are stored**
- Files: `uploads/results/<dataset_id>/<image_id>_kmeans_<nclusters>.jpg`
- DB: через `ResultService.update_result_data(...)` — содержит `status`, `centers_sorted`, `compactness`, `processed_pixels` и `resources` (файлы).

**Services & Important Modules**
- `app/service/computation/cluster_service.py` — содержит `ClusterService.apply_kmeans` (core algorithm invocation).
- `app/service/IO/image_service.py` — загрузка/чтение изображений (CV2).
- `app/service/IO/result_service.py` — CRUD для результатов, создание записи `processing` и обновление итогов.
- `app/db/session.py` / `app/db/init_db.py` — DB session factory и инициализация.

**Tests**
- Unit and integration tests are under `tests/`. Run them with:

```
pytest -q
```

**Development notes / Tips**
- When adding new CPU-bound image operations, run the heavy work inside the provided `executor` (see `app/core/executor.py`) and call it via `asyncio.get_running_loop().run_in_executor(...)` from the request handler or background task, so the event loop stays responsive.
- When a background task needs DB access, create a fresh `AsyncSessionLocal()` inside the task — request-scoped sessions are closed after response.
- Ensure `uploads/` has correct filesystem permissions for the user running the app.

**Common troubleshooting**
- If processed images are missing — check `uploads/results/<dataset_id>/` and application logs for exceptions thrown in the background task. The background task logs errors and calls `result_service.mark_as_failed(...)` on failure.
- If you see duplicated `kmeans` in path and want to change it, edit `app/api/v1/endpoints/analysis/api.py` or the route decorators in `app/api/v1/endpoints/analysis/k_means.py`.

**Next steps / Suggestions**
- Add OpenAPI documentation snippets or examples for each endpoint (FastAPI auto-docs available at `/docs`).
- Add CI to run `pytest` on push.

If you want, I can:
- add example Postman collection or OpenAPI examples for the K-means endpoint,
- fix the duplicated `kmeans` route so endpoints become `/api/v1/analysis/kmeans/{image_id}` (less redundancy), or
- run the test suite and report failures.

