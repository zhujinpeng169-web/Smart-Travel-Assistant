# FirstAgentTest.py 介绍

## 1. 文件概述

`FirstAgentTest.py` 是一个面向初学者的智能旅行助手示例。程序接收一条旅行相关请求，由大语言模型决定下一步行动，再调用外部工具查询天气或搜索景点，最后生成回答。

默认请求是：

> 你好，请帮我查询一下今天上海的天气，然后根据天气推荐一个合适的旅游景点。

也可以在命令行直接指定问题：

```bash
python FirstAgentTest.py 帮我查一下成都的天气，再推荐几个景点
```

这个示例展示了 Agent 的基本工作方式：**模型负责规划和选择工具，Python 程序负责执行工具并反馈结果**。

## 2. 总体工作流程

程序采用最多 6 轮的循环处理任务：

1. 把系统提示词、用户请求和之前的对话记录组成 `messages` 列表。
2. 调用兼容 OpenAI 接口的语言模型。
3. 从模型输出中解析出 `Thought` 和 `Action`。
4. 解析 `Action`，判断是调用工具还是结束任务。
5. 如果调用工具，就执行对应函数并生成 `Observation`。
6. 把 `Observation` 作为一条新消息加回对话，再进入下一轮。
7. 模型输出 `Action: Finish[...]` 后结束循环并返回最终答案；如果 6 轮内都没结束，会返回一段说明，而不是静默退出。

其交互链路可以概括为：

```text
用户请求
   ↓
语言模型思考 Thought / Action
   ↓
解析 Action
   ├─ get_weather(...)     → 查询天气 → Observation
   ├─ get_attraction(...)  → 搜索景点 → Observation
   └─ Finish[...]           → 输出最终答案
```

## 3. 系统提示词

`AGENT_SYSTEM_PROMPT` 规定了 Agent 的角色、可用工具和输出格式。

Agent 被设定为智能旅行助手，可使用：

- `get_weather(city: str)`：查询指定城市的实时天气。
- `get_attraction(city: str, weather: str)`：结合城市和天气推荐旅游景点。

模型每次只能输出一组：

```text
Thought: 下一步思考和计划
Action: 工具调用或 Finish[最终答案]
```

例如：

```text
Thought: 需要先了解上海当前天气。
Action: get_weather(city="上海")
```

提示词里还写明了三条纪律，用来减少模型"跑偏"：

- 不要自己编造 `Observation`，要等待系统返回真实结果；
- 工具返回以「错误：」开头时，要调整参数或换思路，不要原样重试；
- 收集到足够信息后，必须用 `Action: Finish[最终答案]` 结束。

## 4. 工具函数

### 4.1 `get_weather`

该函数通过 `wttr.in` 的 JSON 接口查询天气：

```python
url = f"https://wttr.in/{city}"
```

请求时带上两个参数：

- `format=j1`：返回 JSON；
- `lang=zh`：天气描述用中文（例如「多云」，而不是 `Partly cloudy`）。

函数从返回数据中提取当前天气描述、气温、体感温度、湿度，以及今日最高/最低温，然后生成类似下面的文本：

```text
上海当前天气：多云，气温25摄氏度，体感27摄氏度，湿度70%，今日22~30摄氏度
```

函数对两类问题进行了处理：

- `requests.exceptions.RequestException`：网络请求失败；
- `KeyError` / `IndexError` / `TypeError`：返回数据结构不符合预期，或城市名称无效。

请求设置了 `timeout=10`，网络异常时最多等 10 秒就会返回错误，不会一直挂住。

### 4.2 `get_attraction`

该函数使用 Tavily Search API，根据城市和天气生成景点搜索问题：

```text
'上海' 在'晴朗'天气下最值得去的旅游景点推荐及理由
```

API 密钥从环境变量 `TAVILY_API_KEY` 读取，搜索时使用：

- `search_depth="basic"`
- `include_answer=True`

如果 Tavily 返回综合答案，函数直接返回该答案；如果没有综合答案，就把原始搜索结果整理成列表。密钥缺失、依赖未安装、搜索失败时，都会返回一句可读的错误信息。

`tavily` 采用**函数内导入**：没装 `tavily-python` 时只影响这一个工具，程序不会在启动时就崩掉。

## 5. 模型客户端

`OpenAICompatibleClient` 对 OpenAI Python SDK 做了一层简单封装。

初始化时需要三个参数：

- `model`：模型名称；
- `api_key`：模型服务的 API 密钥；
- `base_url`：兼容 OpenAI 接口的服务地址。

创建 SDK 客户端时设置了 `timeout=60` 与 `max_retries=2`，请求超时或偶发失败时由 SDK 自动重试。

`generate(messages)` 直接把整个 `messages` 列表传给模型：

```python
response = self.client.chat.completions.create(
    model=self.model,
    messages=messages,
    stream=False,
)
```

## 6. 环境变量与依赖

程序运行前需要准备以下环境变量：

```bash
export LLM_API_KEY="你的模型服务密钥"
export LLM_BASE_URL="兼容 OpenAI 的接口地址"
export LLM_MODEL_ID="模型名称"
export TAVILY_API_KEY="你的 Tavily 密钥"
```

也支持旧写法 `API_KEY` / `BASE_URL` / `MODEL_ID`。如果目录下有 `.env` 文件（需要 `python-dotenv`），程序启动时会自动加载，不必每次手动 export。

主要 Python 依赖见 `requirements.txt`：

```bash
pip install -r requirements.txt
```

其中：

- `requests` 用于访问 `wttr.in`；
- `tavily-python` 用于搜索旅游景点；
- `openai` 用于调用兼容 OpenAI 协议的语言模型服务；
- `python-dotenv` 用于读取 `.env`（可选）。

启动时会先校验配置：缺少 `LLM_API_KEY` 或 `LLM_MODEL_ID` 时直接给出中文提示并退出，而不是等到调用模型时才报一个看不懂的错。

## 7. 如何运行

在配置好依赖和环境变量后执行：

```bash
python FirstAgentTest.py
```

或者带上自己的问题：

```bash
python FirstAgentTest.py 帮我查一下今天北京的天气并推荐景点
```

正常运行时，终端会依次打印：

1. 用户输入；
2. 当前循环轮次；
3. 模型输出的 `Thought` 和 `Action`；
4. 工具执行产生的 `Observation`；
5. 最终答案。

## 8. Action 的解析方式

程序使用正则表达式解析模型输出，`parse_action()` 会做这几件事：

- 找到 `Action:` 这一行（中文冒号 `：` 也能识别）；
- 如果模型多输出了一组 `Thought`/`Observation`，只保留第一组 Action；
- 以 `Finish` 开头时，提取方括号里的最终答案（`【】`、换行、嵌套方括号都能处理），为空则返回提示；
- 否则提取函数名和括号内的参数；
- 参数按逗号切分后逐个取 `key=value`，双引号、单引号或不加引号都支持。

工具注册表如下：

```python
available_tools = {
    "get_weather": get_weather,
    "get_attraction": get_attraction,
}
```

这种注册方式便于后续增加工具：定义新函数后，将函数名加入字典，并在系统提示词中说明调用格式即可。

解析失败或工具报错时不会让程序崩掉，而是把错误当成 `Observation` 交回给模型，让它自己纠正。

## 9. 代码特点

- 展示了 Agent 的"规划—行动—观察"循环。
- 使用真实天气接口和真实搜索接口，而不是写死演示数据。
- 通过环境变量管理密钥，避免将密钥直接写入源代码。
- 用规范的 `messages` 结构保存上下文，模型能区分 system / user / assistant 三种角色。
- 每一次外部调用都有超时保护，配置缺失会提前报错。

## 10. 使用时需要注意的问题

已经处理掉的问题：

1. ~~请求没有设置超时时间~~ —— 天气请求 `timeout=10`，模型请求 `timeout=60`。
2. ~~模型配置缺失时才会在运行中暴露问题~~ —— 启动时先校验，缺什么直接提示。
3. ~~Action 格式依赖模型严格遵守提示词~~ —— 解析容忍中文冒号、单引号、裸值、多余输出。
4. ~~`Finish` 解析缺少空值保护~~ —— 解析不到或内容为空都会返回提示而不是抛异常。
5. ~~工具参数只支持双引号字符串~~ —— 现在单引号、双引号、不加引号都能解析。
6. ~~循环次数固定为 5 次且没有失败提示~~ —— 次数可通过 `run(query, max_steps=...)` 调整，用尽后会返回说明。

仍然需要注意：

1. **参数值里不能出现逗号**：解析器按逗号切分参数，`preferences="美食,博物馆"` 会被拆错。
2. **`max_steps` 用尽不等于失败**：可能只是模型绕了远路，可以调大后重试。
3. **外部服务依赖网络和密钥**：天气服务、Tavily 和模型服务任一不可用，都会影响完整流程。

## 11. 总结

`FirstAgentTest.py` 用较少的代码实现了一个完整的工具调用型 Agent。它的核心价值不在于旅行推荐本身，而在于清晰展示了以下模式：

```text
自然语言请求
→ 模型决定行动
→ Python 执行工具
→ 结果回传模型
→ 模型继续行动或给出答案
```

后续可以在此基础上扩展更多工具，例如地图路线、酒店查询、机票搜索和日程规划。
