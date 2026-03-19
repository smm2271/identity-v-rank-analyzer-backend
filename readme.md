# Identity V Rank Analyzer — Backend

本後端服務為「第五人格戰績記錄與分析系統」的一部分，提供資料儲存、驗證、查詢與分析的 API。  
使用 **FastAPI** 建置，並以 **JWT** 進行使用者認證，搭配資料庫儲存所有對局紀錄。

---

## 功能 Features

- 使用者註冊 / 登入（JWT Token 驗證）
- 上傳對局紀錄（由 Python CLI 上傳）
- 查詢個人歷史戰績
- 地圖與角色勝率統計 API
- 符合前端 React Dashboard 的資料格式

---

## 系統架構 Architecture

Python CLI → FastAPI Backend → Database → React Dashboard


後端負責：

- 接收 CLI 上傳的對局資料
- 儲存解析後的戰績
- 計算統計數據
- 對前端提供查詢 API

---

## 主要技術 Tech Stack

- **FastAPI**
- **Python 3.10+**
- **SQLAlchemy**
- **JWT**
- **Uvicorn**

---

## 環境需求 Requirements

- Python 3.10 以上
- PostgreSQL 14 以上
- Linux Server（正式部署建議）

---

## 安裝套件

```bash
conda create -n idv_analyzer_backend python=3.11
conda activate idv_analyzer_backend
pip install -r requirements.txt
```

---

## 環境變數設定

1. 複製範例檔：

```bash
cp .env.example .env
```

2. 依需求修改 `.env`：

- 資料庫（`DATABASE_URL` 或 `db_user/db_password/db_host/db_port/db_name`）
- JWT 過期時間（`JWT_ACCESS_EXPIRE_MINUTES`, `JWT_REFRESH_EXPIRE_DAYS`）
- OAuth（`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`）
- 建議額外設定：`OAUTH_STATE_SECRET`（防 CSRF state 驗證，未設定會使用啟動時隨機值）

---

## 初始化資料庫

建立資料表（首次部署或 schema 變更後執行）：

```bash
python database/database.py
```

---

## 本機啟動

```bash
uvicorn app:app --host 0.0.0.0 --port 9999 --reload
```

啟動後可透過以下網址確認：

- API Root: `http://127.0.0.1:9999/`
- Swagger: `http://127.0.0.1:9999/docs`

---