"""
医疗问答 Agent - 混合检索版本
基于 ReAct 模式 + 混合检索策略
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from langchain.agents import initialize_agent, AgentType, Tool
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate

from src.agents.tools.llm_tool import LLMTool
from src.agents.tools.vector_tool import VectorTool
from src.agents.tools.grep_tool import GrepTool
from src.agents.tools.neo4j_tool import Neo4jTool
from src.agents.hybrid_retriever import HybridRetriever
from src.models.base import db_manager
from src.models.medica_data import QueryLog

logger = logging.getLogger(__name__)


class MedicalAgent:
    """医疗问答 Agent"""

    def __init__(self, use_hybrid_retrieval: bool = True):
        """
        初始化医疗问答 Agent

        Args:
            use_hybrid_retrieval: 是否使用混合检索
        """
        # 初始化工具
        self.llm_tool = LLMTool()
        self.vector_tool = VectorTool()
        self.grep_tool = GrepTool()
        self.neo4j_tool = Neo4jTool()

        # 初始化混合检索器（如果启用）
        self.use_hybrid_retrieval = use_hybrid_retrieval
        if use_hybrid_retrieval:
            self.hybrid_retriever = HybridRetriever(
                vector_tool=self.vector_tool,
                grep_tool=self.grep_tool,
                neo4j_tool=self.neo4j_tool,
                llm_tool=self.llm_tool
            )
            logger.info("✓ 混合检索器初始化完成")
        else:
            self.hybrid_retriever = None

        # 初始化记忆
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )

        # 创建工具列表
        self.tools = self._create_tools()

        # 初始化 Agent
        self.agent = self._create_agent()

        logger.info("✓ 医疗问答 Agent 初始化完成")

    def _create_tools(self) -> List[Tool]:
        """
        创建工具列表

        Returns:
            工具列表
        """
        tools = [
            Tool(
                name="VectorSearch",
                func=self.vector_tool.search,
                description=(
                    "用于语义检索。适用于：查询中草药功效、性味归经、主治等概念性问题。"
                    "输入：用户查询的文本"
                )
            ),
            Tool(
                name="GrepSearch",
                func=self.grep_tool.search,
                description=(
                    "用于精确检索。适用于：查找特定的中草药名称、方剂名称、化学成分。"
                    "输入：搜索关键词"
                )
            ),
            Tool(
                name="IngredientSearch",
                func=self.grep_tool.search_ingredient,
                description=(
                    "用于精确匹配中草药名称。适用于：用户明确提到中草药名称的查询。"
                    "输入：中草药名称"
                )
            ),
            Tool(
                name="FormulaSearch",
                func=self.grep_tool.search_formula,
                description=(
                    "用于搜索方剂名称。适用于：查找特定方剂的详细信息。"
                    "输入：方剂名称"
                )
            ),
            Tool(
                name="CompoundSearch",
                func=self.grep_tool.search_compound,
                description=(
                    "用于精确匹配化学成分。适用于：查找特定化学成分的详细信息。"
                    "输入：化学成分名称"
                )
            ),
            Tool(
                name="Neo4jQuery",
                func=self.neo4j_tool.search_entity,
                description=(
                    "用于图谱查询。适用于：查询疾病、药物、方剂等结构化信息。"
                    "输入：实体类型和名称，格式：entity_type,entity_name"
                )
            ),
        ]

        return tools

    def _create_agent(self) -> AgentType:
        """
        创建 ReAct Agent

        Returns:
            ReAct Agent
        """
        # 自定义 Prompt 模板
        prompt = PromptTemplate(
            input_variables=["input", "agent_scratchpad", "chat_history"],
            template="""你是一个专业的中草药智能问答助手。你的职责是：

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

工具列表：
{tools}

工具输入格式：
我应该使用哪个工具？我应该输入什么参数？使用正确的工具名称，并按照以下格式提供参数：
Action: 工具名称
Action Input: 参数
Observation: 工具输出

开始！你应该首先考虑是否需要使用工具来回答问题，然后依次执行工具调用。如果你已经获得了足够的信息，可以停止使用工具，直接回答用户问题。

{chat_history}

User: {input}
Thought: 我应该首先考虑如何回答这个问题...
{agent_scratchpad}
Thought: 我已经获得了足够的信息，现在可以回答用户的问题了。
Final Answer: """
        )

        # 创建 Agent
        agent = initialize_agent(
            tools=self.tools,
            llm=self.llm_tool.chat_model,
            agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
            verbose=True,
            memory=self.memory,
            agent_kwargs={
                "prompt": prompt,
                "handle_parsing_errors": True,
            }
        )

        return agent

    def query(self, user_input: str, session_id: Optional[str] = None,
              user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        执行查询

        Args:
            user_input: 用户输入
            session_id: 会话 ID
            user_id: 用户 ID

        Returns:
            响应结果
        """
        start_time = datetime.now()

        try:
            # 混合检索模式
            if self.use_hybrid_retrieval and self.hybrid_retriever:
                return self.query_with_hybrid_retrieval(user_input, session_id, user_id)

            # 传统模式
            response = self.agent.run(user_input)

            # 记录查询日志
            self._log_query(user_input, session_id, user_id, success=True)

            # 格式化响应
            result = {
                "answer": response,
                "success": True,
                "disclaimer": self.llm_tool.system_prompt.split("免责声明：")[1].split("\n\n注意事项")[0].strip(),
                "retrieval_type": "traditional"
            }

            return result

        except Exception as e:
            logger.error(f"✗ Agent 查询失败: {e}")

            # 记录错误日志
            self._log_query(user_input, session_id, user_id, success=False, error=str(e))

            # 提取有用的错误信息
            error_msg = str(e)
            if "429" in error_msg or "rate limit" in error_msg.lower():
                answer = "抱歉，API 请求过于频繁，请稍后再试。"
            elif "timeout" in error_msg.lower():
                answer = "抱歉，请求超时，请稍后再试。"
            elif "network" in error_msg.lower():
                answer = "抱歉，网络连接失败，请检查网络设置后重试。"
            else:
                answer = "抱歉，处理您的请求时出现错误。请稍后再试。"

            return {
                "answer": answer,
                "success": False,
                "error": str(e),
                "disclaimer": self.llm_tool.system_prompt.split("免责声明：")[1].split("\n\n注意事项")[0].strip()
            }

    def query_with_hybrid_retrieval(self, user_input: str,
                                     session_id: Optional[str] = None,
                                     user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        使用混合检索执行查询

        Args:
            user_input: 用户输入
            session_id: 会话 ID
            user_id: 用户 ID

        Returns:
            响应结果
        """
        from src.timeline import Timeline
        tl = Timeline()

        try:
            # 执行混合检索
            retrieval_result = self.hybrid_retriever.retrieve(user_input, top_k=5)
            tl.mark("search")

            logger.info(f"检索结果: {retrieval_result.get('retrieval_type', 'unknown')}")
            logger.info(f"图谱结果: {retrieval_result.get('graph_results', 0)}, "
                       f"向量结果: {retrieval_result.get('vector_results', 0)}")

            # 打印匹配到的具体内容
            fused = retrieval_result.get('fused_results', [])
            if fused:
                logger.info("▸ 匹配内容:")
                for i, r in enumerate(fused[:5], 1):
                    name = r.get('name', '?')
                    src = r.get('source', '?')
                    # 向量结果有 content 字段，截取前 60 字
                    content = r.get('content', '')
                    if content:
                        content = content[:60].replace('\n', ' ')
                        logger.info(f"  {i}. [{src}] {name} → {content}...")
                    else:
                        logger.info(f"  {i}. [{src}] {name}")

            # 生成回答
            answer = self.llm_tool.chat_with_retrieval(user_input,
                                                       retrieval_result.get('fused_results', []))
            tl.mark("llm")

            # 记录查询日志
            self._log_query(user_input, session_id, user_id, success=True)

            logger.info(f"时序: {tl.summary()}")

            # 合并检索器和调用链的时序数据
            timing_data = retrieval_result.get('timing', []) + tl.report()

            return {
                "answer": answer,
                "success": True,
                "disclaimer": self.llm_tool.system_prompt.split("免责声明：")[1].split("\n\n注意事项")[0].strip(),
                "retrieval_type": retrieval_result.get('retrieval_type', 'unknown'),
                "intent": retrieval_result.get('intent', 'unknown'),
                "graph_results": retrieval_result.get('graph_results', 0),
                "vector_results": retrieval_result.get('vector_results', 0),
                "timing": timing_data,
            }

        except Exception as e:
            logger.error(f"✗ 混合检索查询失败: {e}")

            # Fallback: 如果检索失败，使用传统模式
            answer = self._fallback_answer(user_input)
            tl.mark("fallback")

            return {
                "answer": answer,
                "success": True,
                "disclaimer": self.llm_tool.system_prompt.split("免责声明：")[1].split("\n\n注意事项")[0].strip(),
                "error": "混合检索失败，已切换到基础对话模式",
                "timing": tl.report(),
            }

    def _log_query(self, query: str, session_id: Optional[str], user_id: Optional[str],
                   success: bool, error: Optional[str] = None):
        """
        记录查询日志

        Args:
            query: 查询内容
            session_id: 会话 ID
            user_id: 用户 ID
            success: 是否成功
            error: 错误信息
        """
        try:
            with db_manager.get_session() as session:
                log = QueryLog(
                    user_id=user_id,
                    query=query,
                    retrieved_documents=f"Intent: {session_id}, {error}",
                    answer=None,
                    needs_disclaimer=success,
                    execution_time=None,
                    error_message=error
                )
                session.add(log)
                session.commit()
        except Exception as e:
            logger.error(f"✗ 记录查询日志失败: {e}")

    def _fallback_answer(self, query: str) -> str:
        """
        Fallback 回答

        当检索失败时，使用基本对话功能

        Args:
            query: 用户查询

        Returns:
            Fallback 回答
        """
        messages = [
            {"role": "system", "content": self.llm_tool.system_prompt},
            {"role": "user", "content": query}
        ]

        try:
            answer = self.llm_tool.chat(messages)
            return answer
        except Exception as e:
            logger.error(f"✗ Fallback 对话失败: {e}")
            return "抱歉，处理您的请求时出现错误。请稍后再试。"

    def get_memory_history(self) -> List[Dict[str, str]]:
        """
        获取记忆历史

        Returns:
            记忆历史列表
        """
        try:
            history = self.memory.load_memory_variables({})
            messages = history.get("chat_history", [])
            return [
                {"role": msg.type, "content": msg.content}
                for msg in messages
            ]
        except Exception as e:
            logger.error(f"✗ 获取记忆历史失败: {e}")
            return []

    def clear_memory(self):
        """清空记忆"""
        self.memory.clear()
        logger.info("✓ 记忆已清空")

    def get_model_info(self) -> Dict[str, Any]:
        """
        获取模型信息

        Returns:
            模型信息字典
        """
        return self.llm_tool.get_model_info()

    def get_tool_info(self) -> Dict[str, Any]:
        """
        获取工具信息

        Returns:
            工具信息字典
        """
        return {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description
                }
                for tool in self.tools
            ],
            "use_hybrid_retrieval": self.use_hybrid_retrieval
        }

    def get_retrieval_stats(self) -> Dict[str, Any]:
        """
        获取检索统计信息

        Returns:
            统计信息
        """
        if self.hybrid_retriever:
            return self.hybrid_retriever.get_retrieval_stats()
        return {}
