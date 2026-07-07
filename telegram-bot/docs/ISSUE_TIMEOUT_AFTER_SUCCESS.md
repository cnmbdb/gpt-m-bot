# 问题处理记录：多张参考图生图后误报 "Timed out"

**记录日期**: 2026-06-02  
**影响模块**: `telegram-bot/handlers/commands.py` + `telegram-bot/bot.py`  
**影响功能**: 多张参考图生成（cmd_image_gen_sc_with_ref / cmd_image_edit_gt / cmd_image_continue_edit）

---

## 1. 问题现象

用户在使用「多张参考图生图」流程时：
- ✅ 机器人正常显示成功提示（`✅ AI 参考图片已生成！消耗 50 积分`）
- ❌ 紧接着又弹出错误提示（`❌ 图片生成失败: Timed out 积分已退回，请稍后重试。`）
- 用户积分被错误退回

## 2. 根因分析

### 根因 1: 状态机缺失，并发请求无防护

`cmd_image_gen_sc_with_ref` 函数在用户处于 `awaiting_sc_prompt` 状态时被调用。
但函数内部**没有互斥保护**：

```python
# 修复前伪代码
async def cmd_image_gen_sc_with_ref(...):
    await send_message(chat_id, f"🎨 正在生成...")
    # ← 如果在 await send_message 期间用户又发送了一张图
    # ← 状态仍然是 awaiting_sc_prompt, 第二次调用会再次进入函数
    img_data, img_url = image_service.generate_with_image(...)  # 同步生成，慢
    await context.bot.send_photo(...)  # ← 超时发生在这一步
```

并发场景：
- 用户发送第 1 张图（多张作为 album）→ 触发 `cmd_image_gen_sc_with_ref`（耗时 ~60s+）
- 用户紧接着又发送新的图 / 重复点击 `/sc` → 又触发一次 `cmd_image_gen_sc_with_ref`
- 两个生成任务并发跑 → 图片中转站响应变慢 / Telegram 上传慢
- 第二次调用 send_photo 超过 60s → `telegram.error.TimedOut`

### 根因 2: Telegram 请求超时设置过小

`bot.py` 中 `app.bot.request.timeout = 60`（60 秒），对于：
- 多张参考图下载（3 张 × 60s = 180s）
- 大图上传到 Telegram（5MB+ 图片在弱网下可能 > 60s）
- 图片中转站慢响应（60~90s）

60 秒太短，极易触发 `TimedOut`。

### 根因 3: 异常处理中"成功与超时"冲突时回退了积分

```python
# 修复前
except Exception as e:
    billing.refund(user_id, cost, "generation_failed")  # ← 即使图片已成功发送也退积分
    await send_message(chat_id, f"❌ 图片生成失败: {e}...")
```

当 `send_photo` 因为 ACK 超时而抛 TimedOut，但图片**实际上已经被 Telegram 服务端接收并展示给用户**——此时仍触发积分退回，逻辑错误。

## 3. 修复方案

### 修复 1: 增加并发控制状态机

在 `commands.py` 顶部新增原子操作工具：

```python
def mark_processing(chat_id: int) -> bool:
    """原子地将 chat_id 标记为 processing。返回 True 表示获取成功，False 表示已有任务在跑。"""
    current = user_states.get(chat_id, {})
    if current.get("step") == "processing":
        return False
    user_states[chat_id] = {**current, "step": "processing"}
    return True

def mark_idle(chat_id: int) -> None:
    """将 chat 状态重置为 idle（保留其他字段）"""
    user_states[chat_id] = {**user_states.get(chat_id, {}), "step": "idle"}
```

由于 `user_states[chat_id] = ...` 是同步操作且与 `if` 判断之间无 `await` 关键字，
asyncio 事件循环不会在此期间切换协程，因此是**原子操作**。

### 修复 2: 三个生图函数入口加并发拦截

```python
async def cmd_image_gen_sc_with_ref(...):
    if not mark_processing(chat_id):
        await send_message(chat_id, "⏳ 正在处理中，请稍候再试...")
        return
    # ... 原逻辑 ...
```

同样应用到 `cmd_image_edit_gt` 和 `cmd_image_continue_edit`。

### 修复 3: 在 handle_photo_message 中跳过 processing 状态

```python
current_state = user_states.get(chat_id, {})
if current_state.get("step") == "processing":
    return  # 静默丢弃，避免重复触发
```

### 修复 4: 异常分支区分"Timed out"与真正的生成失败

```python
except Exception as e:
    mark_idle(chat_id)
    err_str = str(e)
    if err_str == "Timed out":
        # Telegram ACK 超时，但图片可能已送达 —— 不退积分
        await send_message(chat_id, "⚠️ Telegram 上传超时，但图片可能已生成。\n请稍后查看或重试（不会重复扣费）。")
    else:
        # 真正的生成失败 —— 退积分
        try:
            billing.refund(user_id, cost, "generation_failed")
        except Exception:
            pass
        await send_message(chat_id, f"❌ 图片生成失败: {e}\n积分已退回，请稍后重试。")
```

### 修复 5: 提升 Telegram 请求超时

`bot.py`: `app.bot.request.timeout = 60` → `app.bot.request.timeout = 180`（3 分钟）

## 4. 全链路时序图（修复后）

```
T0   用户发送 3 张参考图
T0+1s album 收集完毕，调用 cmd_image_gen_sc_with_ref
T0+1s mark_processing() = True  → step = "processing"
T0+2s 发送"🎨 正在生成..."
T0+2s 调用 billing.deduct() 扣 50 积分
T0+3s 调用图片中转站 /v1/images/generations (timeout=600s)
T0+60s  图片中转站返回图片 URL
T0+61s  下载图片 bytes (timeout=120s)
T0+62s  send_photo 上传到 Telegram (timeout=180s)
T0+63s  上传成功，用户看到图片 + "✅ AI 参考图片已生成！"
T0+63s  mark_idle() → step = "idle"

如果用户在此期间又发送了新图：
  handle_photo_message 看到 step == "processing" → return（不重复触发）
  album 收集后 _process_single_or_album 看到 step == "processing" → 友好提示"⏳ 正在处理中"
```

## 5. 验证场景

| 场景 | 预期行为 | 修复后 |
|------|---------|--------|
| 单张参考图 + 慢网络 | 正常生成，正常显示 | ✅ |
| 多张参考图 (3 张) + 慢网络 | 正常生成，正常显示 | ✅ |
| 多张参考图 + 用户连续触发 | 只生一次，后续提示"正在处理中" | ✅ |
| 多张参考图 + 真实超时 | 显示真实错误，回退积分 | ✅ |
| 多张参考图 + Telegram ACK 慢 (180s内) | 显示图片，提示"上传超时"但**不退积分** | ✅ |
| 多张参考图 + Telegram ACK 超过 180s | 显示图片 + 友好提示，**不退积分** | ✅ |

## 6. 文件变更清单

| 文件 | 变更 |
|------|------|
| [bot.py:101](../bot.py) | `request.timeout` 60 → 180 |
| [commands.py:27-46](../handlers/commands.py) | 新增 `_chat_locks`/`mark_processing`/`mark_idle` |
| [commands.py:411-414](../handlers/commands.py) | `handle_photo_message` 跳过 `processing` |
| [commands.py:820-823](../handlers/commands.py) | `cmd_image_gen_sc_with_ref` 加并发拦截 |
| [commands.py:881-893](../handlers/commands.py) | `cmd_image_gen_sc_with_ref` 异常分支细化 |
| [commands.py:948-951](../handlers/commands.py) | `cmd_image_edit_gt` 加并发拦截 |
| [commands.py:991-1003](../handlers/commands.py) | `cmd_image_edit_gt` 异常分支细化 |
| [commands.py:905-908](../handlers/commands.py) | `cmd_image_continue_edit` 加并发拦截 |
| [commands.py:936-948](../handlers/commands.py) | `cmd_image_continue_edit` 异常分支细化 |
