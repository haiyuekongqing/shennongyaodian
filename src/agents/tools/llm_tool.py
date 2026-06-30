"""
LLM 调用工具
封装 OpenAI API 调用（支持缓存）
"""
import os
import json
import logging
import time
from typing import List, Dict, Any, Optional
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

from src.config.settings import settings
from src.agents.cache.semantic_cache import semantic_cache

logger = logging.getLogger(__name__)


class LLMTool:
    """LLM 调用工具"""

    def __init__(self, use_cache: bool = True):
        """
        初始化 LLM 工具

        Args:
            use_cache: 是否使用缓存
        """
        import time

        # 创建 OpenAI 客户端
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL
        )

        # 创建 LangChain ChatOpenAI，添加超时控制
        self.chat_model = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            openai_api_key=settings.OPENAI_API_KEY,
            openai_api_base=settings.OPENAI_BASE_URL,
            temperature=0.7,
            timeout=120,
            max_retries=1  # 限制最大重试次数
        )

        # 系统提示词
        self.system_prompt = self._get_system_prompt()

        # 是否使用缓存
        self.use_cache = use_cache

        logger.info(f"✓ LLM 工具初始化完成: {settings.OPENAI_MODEL}, 缓存: {use_cache}")

    def _get_system_prompt(self) -> str:
        """
        获取系统提示词

        Returns:
            系统提示词文本
        """
        return """你是一个专业的中草药智能问答助手。你的职责是：

1. 准确回答用户关于中草药、中医理论、疾病症状和用药建议的问题
2. 所有回答必须基于提供的参考资料，严禁编造医学知识
3. 如果你不知道答案，或者提供的参考资料中没有相关信息，请直接回答'抱歉，我目前无法确认该信息'

注意事项：
- 严格区分'疗效'、'作用'、'功效'等不同概念
- 对于成分复杂的中草药，提供准确的性味归经和功效描述
- 用药建议必须明确适用症、剂量和禁忌
- 对于不确定的信息，必须明确说明'无法确认'

医疗免责声明：
免责声明：本系统提供的信息仅供参考，不构成医疗建议。如遇健康问题，请咨询专业医生或药师。
"""

    def chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None) -> str:
        """
        对话式 LLM 调用（支持缓存）

        Args:
            messages: 消息列表，格式：[{"role": "user", "content": "..."}]
            temperature: 温度参数，控制回答的随机性

        Returns:
            LLM 生成的回答
        """
        start_time = time.time()

        # 从消息中提取查询文本
        query_text = ""
        for msg in messages:
            if msg.get("role") == "user":
                query_text = msg.get("content", "")
                break

        if not query_text:
            query_text = messages[-1].get("content", "") if messages else ""

        # 构建上下文用于缓存
        context = {
            "query": query_text,
            "messages": messages
        }

        # 检查缓存
        if self.use_cache:
            cached_answer = semantic_cache.search(query_text)
            if cached_answer:
                logger.info(f"✓ 语义缓存命中，节省 {time.time() - start_time:.2f} 秒")
                return cached_answer.get("answer", "")

        # 构建消息列表
        formatted_messages = [SystemMessage(content=self.system_prompt)]

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            formatted_messages.append(HumanMessage(content=content))

        try:
            # 调用 LLM
            response = self.chat_model.invoke(formatted_messages)
            answer = response.content

            # 存储到语义缓存
            if self.use_cache and query_text:
                semantic_cache.store(query_text, answer)
                logger.info(f"✓ LLM 调用成功，生成 {len(answer)} 字符，耗时 {time.time() - start_time:.2f} 秒")

            return answer

        except Exception as e:
            error_str = str(e)

            # 检查是否是速率限制错误 (429)
            if "429" in error_str or "rate limit" in error_str.lower():
                logger.error(f"✗ LLM API 速率限制（429）: {e}")
                raise Exception("抱歉，API 请求过于频繁，请稍后再试（429 速率限制）")

            logger.error(f"✗ LLM 调用失败: {e}")
            raise

    def chat_with_retrieval(self, query: str, retrieved_docs: List[Dict[str, Any]], temperature: Optional[float] = None) -> str:
        """
        基于检索结果生成回答（支持缓存）

        Args:
            query: 用户问题
            retrieved_docs: 检索到的文档列表
            temperature: 温度参数

        Returns:
            生成的回答
        """
        start_time = time.time()

        # 从文档中提取用于缓存的关键信息
        context = self._build_context(retrieved_docs)
        context_str = json.dumps(context, sort_keys=True)

        # 检查缓存（包含检索上下文）
        if self.use_cache:
            cached_answer = semantic_cache.search(query)
            if cached_answer:
                logger.info(f"✓ 语义缓存命中（包含检索上下文），节省 {time.time() - start_time:.2f} 秒")
                return cached_answer.get("answer", "")

        # 构建消息
        messages = [
            {
                "role": "system",
                "content": self.system_prompt + f"\n\n参考信息：\n{context}\n\n请基于以上参考信息回答用户问题，不要编造信息。"
            },
            {
                "role": "user",
                "content": query
            }
        ]

        answer = self.chat(messages, temperature)

        # 存储到语义缓存（包含检索上下文）
        if self.use_cache:
            semantic_cache.store(query + "|" + context_str[:100], answer)

        return answer

    def chat_with_history(self, query: str, history: List[Dict[str, str]], temperature: Optional[float] = None) -> str:
        """
        带历史记录的对话

        Args:
            query: 当前问题
            history: 历史对话记录
            temperature: 温度参数

        Returns:
            生成的回答
        """
        messages = []

        # 添加系统提示
        messages.append({
            "role": "system",
            "content": self.system_prompt
        })

        # 添加历史记录
        for msg in history:
            messages.append(msg)

        # 添加当前问题
        messages.append({
            "role": "user",
            "content": query
        })

        return self.chat(messages, temperature)

    def _build_context(self, docs: List[Dict[str, Any]], max_sources: int = 3) -> str:
        """
        构建上下文文本

        Args:
            docs: 检索到的文档列表
            max_sources: 最多使用多少个来源

        Returns:
            上下文文本
        """
        context = ""

        # 限制来源数量
        docs = docs[:max_sources]

        for i, doc in enumerate(docs, 1):
            # 兼容两种数据格式：
            # 1. 原始格式: content + source_file（来自 Milvus 向量结果）
            # 2. 融合格式: name + source（来自 _fuse_results 的图谱/混合结果）
            content = doc.get('content') or doc.get('name', '')
            source = doc.get('source_file') or doc.get('source', '未知来源')

            if content:
                context += f"[来源 {i}: {source}]\n{content}\n\n"

        return context.strip()

    def get_model_info(self) -> Dict[str, Any]:
        """
        获取模型信息

        Returns:
            模型信息字典
        """
        return {
            "model": settings.OPENAI_MODEL,
            "base_url": settings.OPENAI_BASE_URL,
            "temperature": 0.7,
            "max_tokens": 4096
        }

    def count_tokens(self, text: str) -> int:
        """
        计算文本的 token 数量（粗略估计）

        Args:
            text: 输入文本

        Returns:
            Token 数量
        """
        # 简单估计：1 token ≈ 4 字符（中文）
        return len(text) // 4

    def stream_chat(self, messages: List[Dict[str, str]]) -> str:
        """
        流式对话（占位实现）

        Args:
            messages: 消息列表

        Returns:
            生成的回答
        """
        # 当前版本暂不支持流式，使用标准调用
        return self.chat(messages)

    def set_system_prompt(self, custom_prompt: Optional[str] = None):
        """
        自定义系统提示词

        Args:
            custom_prompt: 自定义提示词，如果为 None 则恢复默认
        """
        if custom_prompt:
            self.system_prompt = custom_prompt
            logger.info("✓ 系统提示词已更新")
        else:
            self.system_prompt = self._get_system_prompt()
            logger.info("✓ 系统提示词已恢复默认")
