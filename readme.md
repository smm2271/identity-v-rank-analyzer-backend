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