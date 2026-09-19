import os
import re
import sys

import requests
from openai import OpenAI

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()


AGENT_SYSTEM_PROMPT = """
你是一个智能旅行助手。你的任务是分析用户的请求，并使用可用工具一步步地解决问题。

# 可用工具:
- `get_weather(city: str)`: 查询指定城市的实时天气。
- `get_attraction(city: str, weather: str)`: 根据城市和天气搜索推荐的旅游景点。

# 输出格式要求:
你的每次回复必须严格遵循以下格式，包含一对Thought和Action：

Thought: [你的思考过程和下一步计划]
Action: [你要执行的具体行动]

Action的格式必须是以下之一：
1. 调用工具：function_name(arg_name="arg_value")
2. 结束任务：Finish[最终答案]

# 重要提示:
- 每次只输出一对Thought-Action
- Action必须在同一行，不要换行
- 字符串参数请使用双引号，多个参数用英文逗号分隔
- 不要自己编造Observation，要等待系统返回真实结果
- 工具返回以「错误：」开头时，请调整参数或换一个思路，不要原样重试
- 当收集到足够信息可以回答用户问题时，必须使用 Action: Finish[最终答案] 格式结束
- Finish 里的答案要完整，可以直接展示给用户

请开始吧！
"""


def get_weather(city):
    url = f"https://wttr.in/{city}"
    try:
        response = requests.get(url, params={"format": "j1", "lang": "zh"}, timeout=10)
        response.raise_for_status()
        data = response.json()
        current = data["current_condition"][0]
        description = (current.get("lang_zh") or current.get("weatherDesc"))[0]["value"]
        parts = [f"{city}当前天气：{description}", f"气温{current['temp_C']}摄氏度"]
        if current.get("FeelsLikeC"):
            parts.append(f"体感{current['FeelsLikeC']}摄氏度")
        if current.get("humidity"):
            parts.append(f"湿度{current['humidity']}%")
        weather_today = data.get("weather") or [{}]
        if weather_today[0].get("mintempC"):
            parts.append(f"今日{weather_today[0]['mintempC']}~{weather_today[0]['maxtempC']}摄氏度")
        return "，".join(parts)
    except requests.exceptions.RequestException as e:
        return f"错误：查询天气时遇到网络问题 - {e}"
    except (KeyError, IndexError, TypeError) as e:
        return f"错误：解析天气数据失败，可能是城市名称无效 - {e}"


def get_attraction(city, weather):
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return "错误：未配置 TAVILY_API_KEY。"
    try:
        from tavily import TavilyClient
    except ImportError:
        return "错误：未安装 tavily-python，请先执行 pip install tavily-python。"

    query = f"{city} 在{weather}天气下最值得去的旅游景点推荐及理由"
    try:
        response = TavilyClient(api_key=api_key).search(query=query, search_depth="basic", include_answer=True)
    except Exception as e:
        return f"错误：执行搜索时出现问题 - {e}"

    if response.get("answer"):
        return response["answer"]

    results = [f"- {item.get('title')}: {item.get('content')}" for item in response.get("results", [])]
    if not results:
        return "抱歉，没有找到相关的旅游景点推荐。"
    return "根据搜索，为您找到以下信息：\n" + "\n".join(results)


available_tools = {
    "get_weather": get_weather,
    "get_attraction": get_attraction,
}


class OpenAICompatibleClient:
    def __init__(self, model, api_key, base_url):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=60, max_retries=2)

    def generate(self, messages):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=False,
        )
        return response.choices[0].message.content or ""


def load_settings():
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("API_KEY")
    base_url = os.environ.get("LLM_BASE_URL") or os.environ.get("BASE_URL")
    model = os.environ.get("LLM_MODEL_ID") or os.environ.get("MODEL_ID")
    missing = [name for name, value in (("LLM_API_KEY", api_key), ("LLM_MODEL_ID", model)) if not value]
    if missing:
        raise SystemExit(
            "缺少环境变量：" + "、".join(missing) + "\n"
            "请先配置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_ID 与 TAVILY_API_KEY 后重试。"
        )
    return model, api_key, base_url


def parse_action(text):
    match = re.search(r"Action\s*[:：]\s*(.+)", text, re.DOTALL)
    if not match:
        return None, {}, "没有找到 Action，请严格按「Thought: ... 换行 Action: ...」的格式输出。"

    action = re.split(r"\n\s*(?:Thought|Observation)\s*[:：]", match.group(1))[0].strip()

    finish = re.match(r"finish\s*[\[【](.*)[\]】]\s*$", action, re.DOTALL | re.IGNORECASE)
    if finish:
        answer = finish.group(1).strip().strip('"').strip()
        if not answer:
            return None, {}, "Finish 的方括号里没有最终答案。"
        return "__finish__", {"answer": answer}, None

    call = re.match(r"([A-Za-z_]\w*)\s*\((.*)\)\s*$", action, re.DOTALL)
    if not call:
        return None, {}, f"无法解析 Action：{action}"

    arguments = {}
    for item in re.split(r"[,，]", call.group(2)):
        if "=" not in item:
            continue
        key, _, value = item.partition("=")
        key = key.strip().strip("\"'")
        value = value.strip().strip("\"'")
        if key:
            arguments[key] = value
    return call.group(1), arguments, None


def run(user_prompt, max_steps=6):
    model, api_key, base_url = load_settings()
    llm = OpenAICompatibleClient(model, api_key, base_url)
    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": f"用户请求: {user_prompt}"},
    ]

    for step in range(1, max_steps + 1):
        print(f"--- 循环 {step}/{max_steps} ---\n")

        reply = llm.generate(messages)
        messages.append({"role": "assistant", "content": reply})
        print(f"模型输出:\n{reply}\n")

        tool_name, arguments, error = parse_action(reply)

        if error:
            observation = f"错误：{error}"
        elif tool_name == "__finish__":
            return arguments["answer"]
        elif tool_name in available_tools:
            try:
                observation = available_tools[tool_name](**arguments)
            except TypeError as e:
                observation = f"错误：工具参数不正确 - {e}"
        else:
            observation = f"错误：未定义的工具 '{tool_name}'，可用工具：{', '.join(available_tools)}"

        print(f"Observation: {observation}\n" + "=" * 40 + "\n")
        messages.append({"role": "user", "content": f"Observation: {observation}"})

    return (
        f"抱歉，经过 {max_steps} 次尝试仍未完成任务。\n"
        "可以试试把问题拆小一点（例如先只问天气），或稍后重试。"
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    query = " ".join(sys.argv[1:]).strip()
    if not query:
        query = "你好，请帮我查询一下今天上海的天气，然后根据天气推荐一个合适的旅游景点。"

    print(f"用户输入: {query}\n" + "=" * 40)
    print("\n最终答案: " + run(query))
