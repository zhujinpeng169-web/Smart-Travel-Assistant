# FirstAgentTest.py 介绍

## 1. 文件概述

`FirstAgentTest.py` 是一个面向初学者的智能旅行助手示例。程序接收一条旅行相关请求，由大语言模型决定下一步行动，再调用外部工具查询天气或搜索景点，最后生成回答。

示例中的固定请求是：

> 你好，请帮我查询一下今天上海的天气，然后根据天气推荐一个合适的旅游景点。

这个示例展示了 Agent 的基本工作方式：**模型负责规划和选择工具，Python 程序负责执行工具并反馈结果**。

## 2. 总体工作流程

程序采用最多 5 轮的循环处理任务：

1. 将用户请求和之前的对话记录拼接成完整提示词。
2. 调用兼容 OpenAI 接口的语言模型。
3. 从模型输出中截取一组 `Thought` 和 `Action`。
4. 解析 `Action`，判断是调用工具还是结束任务。
5. 如果调用工具，就执行对应函数并生成 `Observation`。
6. 把 `Observation` 加入历史记录，再进入下一轮。
7. 模型输出 `Action: Finish[...]` 后结束循环并打印最终答案。

其交互链路可以概括为：

```text
用户请求
   ↓
语言模型规划 Thought/Action
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

## 4. 工具函数

### 4.1 `get_weather`

该函数通过 `wttr.in` 的 JSON 接口查询天气：

```python
url = f"https://wttr.in/{city}?format=j1"
```

函数从返回数据中提取：

- 当前天气描述 `weatherDesc`
- 当前温度 `temp_C`

然后生成类似下面的文本：

```text
上海当前天气：Partly cloudy，气温25摄氏度
```

函数对两类问题进行了处理：

- `requests.exceptions.RequestException`：网络请求失败。
- `KeyError` 或 `IndexError`：返回数据结构不符合预期，或城市名称无效。

### 4.2 `get_attraction`

该函数使用 Tavily Search API，根据城市和天气生成景点搜索问题：

```text
'上海' 在'晴朗'天气下最值得去的旅游景点推荐及理由
```

API 密钥从环境变量 `TAVILY_API_KEY` 读取。搜索时使用：

- `search_depth="basic"`
- `include_answer=True`

如果 Tavily 返回综合答案，函数直接返回该答案；如果没有综合答案，则将原始搜索结果整理成列表。如果没有配置密钥、没有搜索结果或请求失败，函数会返回对应的错误信息。

## 5. 模型客户端

`OpenAICompatibleClient` 对 OpenAI Python SDK 做了一层简单封装。

初始化时需要三个参数：

- `model`：模型名称。
- `api_key`：模型服务的 API 密钥。
- `base_url`：兼容 OpenAI 接口的服务地址。

`generate()` 方法将系统提示词和用户提示词组成 Chat Completions 所需的 `messages`，并以非流式方式调用模型：

```python
response = self.client.chat.completions.create(
    model=self.model,
    messages=messages,
    stream=False
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

主要 Python 依赖包括：

```bash
pip install requests tavily-python openai
```

其中：

- `requests` 用于访问 `wttr.in`。
- `tavily-python` 用于搜索旅游景点。
- `openai` 用于调用兼容 OpenAI 协议的语言模型服务。

## 7. 如何运行

在配置好依赖和环境变量后执行：

```bash
python /home/china/Desktop/hello-agents-main/code/chapter1/FirstAgentTest.py
```

正常运行时，终端会依次打印：

1. 用户输入。
2. 当前循环轮次。
3. 模型输出的 `Thought` 和 `Action`。
4. 工具执行产生的 `Observation`。
5. Agent 完成后的最终答案。

## 8. Action 的解析方式

程序使用正则表达式解析模型输出：

- 查找 `Action: ...` 行。
- 如果以 `Finish` 开头，则提取方括号中的最终答案。
- 否则提取函数名和括号内的参数。
- 使用 `available_tools` 字典找到实际函数并调用。

工具注册表如下：

```python
available_tools = {
    "get_weather": get_weather,
    "get_attraction": get_attraction,
}
```

这种注册方式便于后续增加工具：定义新函数后，将函数名加入字典，并在系统提示词中说明调用格式即可。

## 9. 代码特点

- 展示了 Agent 的“规划—行动—观察”循环。
- 使用真实天气接口和真实搜索接口，而不是写死演示数据。
- 通过环境变量管理密钥，避免将密钥直接写入源代码。
- 使用 `OpenAICompatibleClient`，可以连接不同的 OpenAI 兼容模型服务。
- 通过 `prompt_history` 保存上下文，使模型能够利用前一步工具结果继续规划。

## 10. 使用时需要注意的问题

1. **请求没有设置超时时间**：`requests.get()` 建议增加 `timeout`，否则网络异常时程序可能等待较久。
2. **模型配置缺失时才会在运行中暴露问题**：如果 `LLM_API_KEY`、`LLM_BASE_URL` 或 `LLM_MODEL_ID` 未配置，应该在初始化前增加明确的校验。
3. **Action 格式依赖模型严格遵守提示词**：当前正则解析对格式比较敏感，模型输出缺少括号、引号或字段时可能解析失败。
4. **`Finish` 解析缺少空值保护**：当 `Finish[...]` 格式不完整时，`re.match(...).group(1)` 可能抛出异常。
5. **工具参数只支持双引号字符串**：当前参数解析器不能处理复杂参数、转义引号或非字符串类型。
6. **循环次数固定为 5 次**：如果模型多次产生无效 Action，程序会在达到上限后结束，但没有额外的失败提示。
7. **外部服务依赖网络和密钥**：天气服务、Tavily 和模型服务任一不可用，都可能影响完整流程。

## 11. 总结

`FirstAgentTest.py` 用较少的代码实现了一个完整的工具调用型 Agent。它的核心价值不在于旅行推荐本身，而在于清晰展示了以下模式：

```text
自然语言请求
→ 模型决定行动
→ Python 执行工具
→ 结果回传模型
→ 模型继续行动或给出答案
```

后续可以在此基础上扩展更多工具，例如地图路线、酒店查询、机票搜索和日程规划，并进一步增强参数校验、超时控制、日志记录和结构化输出。
