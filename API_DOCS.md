# Identity V Rank Analyzer — API 文件

> Base URL: `http://localhost:9999`

---

## 目錄

- [認證方式](#認證方式)
- [Auth — 認證相關](#auth--認證相關)
  - [GET /auth/providers](#get-authproviders)
  - [GET /auth/{provider}/authorize](#get-authproviderauthorize)
  - [GET /auth/{provider}/callback](#get-authprovidercallback)
  - [POST /auth/register](#post-authregister)
  - [POST /auth/login](#post-authlogin)
  - [POST /auth/refresh](#post-authrefresh)
  - [POST /auth/logout](#post-authlogout)
- [Users — 使用者資訊](#users--使用者資訊)
  - [GET /users/me](#get-usersme)
  - [GET /users/me/identities](#get-usersmeidentities)
- [Matches — 對戰紀錄](#matches--對戰紀錄)
  - [POST /api/v1/matches](#post-apiv1matches)
  - [GET /api/v1/matches](#get-apiv1matches)
  - [GET /api/v1/matches/{match_id}](#get-apiv1matchesmatch_id)
- [錯誤回應格式](#錯誤回應格式)

---

## 認證方式

本 API 支援兩種認證方式：

| 方式 | Header | 適用端點 |
|------|--------|---------|
| **JWT Bearer Token** | `Authorization: Bearer <access_token>` | `/users/*`、`/auth/logout` |
| **API Key** | `X-API-Key: <api_key>` | `/api/v1/matches/*` |

---

## Auth — 認證相關

### GET /auth/providers

列出所有可用的登入供應商。

**認證**：不需要

**回應**

```json
{
  "oauth_providers": ["discord", "google"],
  "password_enabled": true
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `oauth_providers` | `string[]` | 已註冊的 OAuth 供應商名稱 |
| `password_enabled` | `boolean` | 密碼登入是否啟用 |

---

### GET /auth/{provider}/authorize

產生指定 OAuth 供應商的授權 URL。

**認證**：不需要

**路徑參數**

| 參數 | 型別 | 說明 |
|------|------|------|
| `provider` | `string` | OAuth 供應商名稱（如 `google`、`discord`） |

**查詢參數**

| 參數 | 必填 | 型別 | 說明 |
|------|------|------|------|
| `redirect_uri` | ✅ | `string` | OAuth 授權完成後的回呼 URL |

**回應** `200 OK`

```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "state": "random-csrf-state-string"
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `authorization_url` | `string` | 完整的 OAuth 授權重導向 URL |
| `state` | `string` | 防 CSRF 的 state 參數，前端需在回呼時帶回 |

**錯誤**

| 狀態碼 | 說明 |
|--------|------|
| `400` | 不支援的 OAuth 供應商 |
| `502` | 無法產生授權 URL |

---

### GET /auth/{provider}/callback

處理 OAuth 授權回呼，交換 code 取得使用者資訊，自動建立或登入使用者。

**認證**：不需要

**路徑參數**

| 參數 | 型別 | 說明 |
|------|------|------|
| `provider` | `string` | OAuth 供應商名稱 |

**查詢參數**

| 參數 | 必填 | 型別 | 說明 |
|------|------|------|------|
| `code` | ✅ | `string` | OAuth authorization code |
| `state` | ✅ | `string` | CSRF state 參數 |
| `redirect_uri` | ✅ | `string` | 與 authorize 時使用的相同回呼 URL |

**回應** `200 OK`

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer"
}
```

**錯誤**

| 狀態碼 | 說明 |
|--------|------|
| `400` | 不支援的 OAuth 供應商 |
| `502` | OAuth 驗證失敗（code 無效、過期等） |

---

### POST /auth/register

以 Email + 密碼註冊新帳號。

**認證**：不需要

**請求 Body** `application/json`

```json
{
  "email": "user@example.com",
  "password": "MyStr0ngP@ss",
  "username": "my_username"
}
```

| 欄位 | 必填 | 型別 | 說明 |
|------|------|------|------|
| `email` | ✅ | `string (email)` | 使用者 Email |
| `password` | ✅ | `string` | 密碼（至少 8 字元，需含大小寫與數字） |
| `username` | ❌ | `string` | 使用者名稱（最長 50 字元） |

**回應** `201 Created`

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer"
}
```

**錯誤**

| 狀態碼 | 說明 |
|--------|------|
| `409` | Email 已被註冊 |
| `422` | 密碼強度不足 |
| `503` | 密碼登入功能未啟用 |

---

### POST /auth/login

以 Email + 密碼登入。

**認證**：不需要

**請求 Body** `application/json`

```json
{
  "email": "user@example.com",
  "password": "MyStr0ngP@ss"
}
```

| 欄位 | 必填 | 型別 | 說明 |
|------|------|------|------|
| `email` | ✅ | `string (email)` | 使用者 Email |
| `password` | ✅ | `string` | 密碼 |

**回應** `200 OK`

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer"
}
```

**錯誤**

| 狀態碼 | 說明 |
|--------|------|
| `401` | 帳號或密碼錯誤 |
| `503` | 密碼登入功能未啟用 |

> **安全說明**：無論帳號不存在或密碼錯誤，統一回傳「帳號或密碼錯誤」以防止帳號列舉攻擊。

---

### POST /auth/refresh

以 Refresh Token 換發新的 Access + Refresh Token。

**認證**：不需要（但需提供有效的 refresh token）

**請求 Body** `application/json`

```json
{
  "refresh_token": "eyJhbGciOiJSUzI1NiIs..."
}
```

| 欄位 | 必填 | 型別 | 說明 |
|------|------|------|------|
| `refresh_token` | ✅ | `string` | 有效的 JWT Refresh Token |

**回應** `200 OK`

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer"
}
```

**錯誤**

| 狀態碼 | 說明 |
|--------|------|
| `400` | 提供的是 access token 而非 refresh token |
| `401` | Refresh token 已過期 / 已被撤銷 / 無效 |

---

### POST /auth/logout

登出當前使用者，撤銷所有已簽發的 Token（全裝置登出）。

**認證**：`Authorization: Bearer <access_token>`

**請求 Body**：無

**回應** `200 OK`

```json
{
  "message": "已成功登出"
}
```

**錯誤**

| 狀態碼 | 說明 |
|--------|------|
| `401` | 未提供 Token / Token 無效或已過期 |

---

## Users — 使用者資訊

### GET /users/me

取得當前登入使用者的基本資料。

**認證**：`Authorization: Bearer <access_token>`

**回應** `200 OK`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "my_username",
  "email": "user@example.com",
  "created_at": "2026-03-05T12:00:00",
  "token_ver": 1
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | `uuid` | 使用者 UUID |
| `username` | `string \| null` | 使用者名稱 |
| `email` | `string \| null` | Email |
| `created_at` | `datetime` | 帳號建立時間 |
| `token_ver` | `int` | Token 版本號（用於撤銷機制） |

**錯誤**

| 狀態碼 | 說明 |
|--------|------|
| `401` | 未提供 Token / Token 無效或已過期 |

---

### GET /users/me/identities

取得當前使用者已綁定的所有身份驗證來源。

**認證**：`Authorization: Bearer <access_token>`

**回應** `200 OK`

```json
[
  {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "provider": "google",
    "provider_key": "117438290512345678901"
  },
  {
    "id": "770e8400-e29b-41d4-a716-446655440002",
    "provider": "password",
    "provider_key": "user@example.com"
  }
]
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | `uuid` | 身份記錄 UUID |
| `provider` | `string` | 供應商名稱（`google` / `discord` / `password`） |
| `provider_key` | `string` | 供應商端唯一識別（OAuth user ID 或 email） |

**錯誤**

| 狀態碼 | 說明 |
|--------|------|
| `401` | 未提供 Token / Token 無效或已過期 |

---

## Matches — 對戰紀錄

> **所有 Match 端點皆需透過 `X-API-Key` Header 驗證。**

### POST /api/v1/matches

上傳一筆遊戲對戰紀錄，可同時包含所有玩家資訊。

**認證**：`X-API-Key: <api_key>`

**請求 Body** `application/json`

```json
{
  "room_guuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "scene_id": 5,
  "match_type": 1,
  "rank_level": 12,
  "kill_num": 3,
  "utype": 1,
  "pid": 102,
  "game_save_time": "2026-03-05T15:30:00",
  "cipher_progress": {"cipher_1": 0.8, "cipher_2": 1.0},
  "players": [
    {
      "player_id": 1,
      "player_name": "Hunter01",
      "character_id": 102,
      "res_type": null
    },
    {
      "player_id": 2,
      "player_name": "Survivor01",
      "character_id": 2,
      "res_type": 1
    }
  ]
}
```

| 欄位 | 必填 | 型別 | 說明 |
|------|------|------|------|
| `room_guuid` | ✅ | `uuid` | 房間 UUID |
| `scene_id` | ❌ | `int` | 地圖 ID |
| `match_type` | ❌ | `int` | 對戰類型（1:排位, 2:匹配, 3:五人制） |
| `rank_level` | ❌ | `int` | 當時段位 |
| `kill_num` | ❌ | `int` | 擊殺數 |
| `utype` | ❌ | `int` | 角色類型（1:監管, 2:求生） |
| `pid` | ❌ | `int` | 我方角色 ID |
| `game_save_time` | ❌ | `datetime` | 遊戲結束時間 |
| `cipher_progress` | ❌ | `object` | 各台密碼機修機進度 |
| `players` | ❌ | `PlayerInfo[]` | 對局玩家資料（見下表） |

**PlayerInfo 物件**

| 欄位 | 必填 | 型別 | 說明 |
|------|------|------|------|
| `player_id` | ✅ | `int` | 玩家 ID |
| `player_name` | ❌ | `string` | 玩家名稱（最長 14 字元） |
| `character_id` | ✅ | `int` | 角色 ID |
| `res_type` | ❌ | `int` | 逃脫狀態 |

**回應** `201 Created`

```json
{
  "id": "880e8400-e29b-41d4-a716-446655440003",
  "room_guuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "uploader_id": "550e8400-e29b-41d4-a716-446655440000",
  "scene_id": 5,
  "match_type": 1,
  "rank_level": 12,
  "kill_num": 3,
  "utype": 1,
  "pid": 102,
  "game_save_time": "2026-03-05T15:30:00",
  "cipher_progress": {"cipher_1": 0.8, "cipher_2": 1.0},
  "created_at": "2026-03-05T15:31:00"
}
```

**錯誤**

| 狀態碼 | 說明 |
|--------|------|
| `401` | 未提供 API Key |
| `403` | API Key 無效或已停用 |
| `409` | 此對戰紀錄已上傳過（room_guuid + uploader 重複） |

---

### GET /api/v1/matches

取得當前使用者上傳的所有對戰紀錄（分頁）。

**認證**：`X-API-Key: <api_key>`

**查詢參數**

| 參數 | 必填 | 型別 | 預設值 | 說明 |
|------|------|------|--------|------|
| `offset` | ❌ | `int` | `0` | 分頁偏移量 |
| `limit` | ❌ | `int` | `50` | 每頁筆數 |

**回應** `200 OK`

```json
{
  "total": 42,
  "offset": 0,
  "limit": 50,
  "items": [
    {
      "id": "880e8400-e29b-41d4-a716-446655440003",
      "room_guuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "uploader_id": "550e8400-e29b-41d4-a716-446655440000",
      "scene_id": 5,
      "match_type": 1,
      "rank_level": 12,
      "kill_num": 3,
      "utype": 1,
      "pid": 102,
      "game_save_time": "2026-03-05T15:30:00",
      "cipher_progress": null,
      "created_at": "2026-03-05T15:31:00"
    }
  ]
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `total` | `int` | 該使用者的對戰總數 |
| `offset` | `int` | 當前偏移量 |
| `limit` | `int` | 當前每頁筆數 |
| `items` | `MatchResponse[]` | 對戰紀錄列表 |

**錯誤**

| 狀態碼 | 說明 |
|--------|------|
| `401` | 未提供 API Key |
| `403` | API Key 無效或已停用 |

---

### GET /api/v1/matches/{match_id}

取得單筆對戰紀錄詳情（含玩家資訊）。僅能查看自己上傳的紀錄。

**認證**：`X-API-Key: <api_key>`

**路徑參數**

| 參數 | 型別 | 說明 |
|------|------|------|
| `match_id` | `uuid` | 對戰紀錄 UUID |

**回應** `200 OK`

```json
{
  "id": "880e8400-e29b-41d4-a716-446655440003",
  "room_guuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "uploader_id": "550e8400-e29b-41d4-a716-446655440000",
  "scene_id": 5,
  "match_type": 1,
  "rank_level": 12,
  "kill_num": 3,
  "utype": 1,
  "pid": 102,
  "game_save_time": "2026-03-05T15:30:00",
  "cipher_progress": {"cipher_1": 0.8, "cipher_2": 1.0},
  "created_at": "2026-03-05T15:31:00",
  "players": [
    {
      "id": "990e8400-e29b-41d4-a716-446655440004",
      "player_id": 1,
      "player_name": "Hunter01",
      "character_id": 102,
      "res_type": null,
      "created_at": "2026-03-05T15:31:00"
    },
    {
      "id": "aa0e8400-e29b-41d4-a716-446655440005",
      "player_id": 2,
      "player_name": "Survivor01",
      "character_id": 2,
      "res_type": 1,
      "created_at": "2026-03-05T15:31:00"
    }
  ]
}
```

**錯誤**

| 狀態碼 | 說明 |
|--------|------|
| `401` | 未提供 API Key |
| `403` | API Key 無效或已停用 / 無權查看此紀錄 |
| `404` | 對戰紀錄不存在 |

---

## 錯誤回應格式

所有錯誤回應皆遵循 FastAPI 標準格式：

```json
{
  "detail": "錯誤訊息描述"
}
```

### 通用 HTTP 狀態碼

| 狀態碼 | 說明 |
|--------|------|
| `400 Bad Request` | 請求參數不正確 |
| `401 Unauthorized` | 未提供認證或認證無效 |
| `403 Forbidden` | 無權存取該資源 |
| `404 Not Found` | 資源不存在 |
| `409 Conflict` | 資源已存在（重複） |
| `422 Unprocessable Entity` | 請求格式正確但內容不合法（如密碼強度不足） |
| `500 Internal Server Error` | 伺服器內部錯誤 |
| `502 Bad Gateway` | 第三方服務回應異常（OAuth 供應商錯誤） |
| `503 Service Unavailable` | 功能未啟用 |
