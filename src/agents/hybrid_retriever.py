"""
混合检索器 - 向量检索 + 图谱检索
"""
import logging
import re
from typing import List, Dict, Any, Optional
from src.agents.intent_recognizer import IntentRecognizer, IntentType
from src.retrieval.vector_store import VectorStore
from src.agents.tools.grep_tool import GrepTool
from src.agents.tools.neo4j_tool import Neo4jTool
from src.agents.tools.llm_tool import LLMTool

logger = logging.getLogger(__name__)


class HybridRetriever:
    """混合检索器"""

    def __init__(self, vector_tool: VectorStore, grep_tool: GrepTool,
                 neo4j_tool: Neo4jTool, llm_tool: LLMTool):
        """
        初始化混合检索器

        Args:
            vector_tool: 向量检索工具
            grep_tool: Grep检索工具
            neo4j_tool: Neo4j检索工具
            llm_tool: LLM工具
        """
        self.vector_tool = vector_tool
        self.grep_tool = grep_tool
        self.neo4j_tool = neo4j_tool
        self.llm_tool = llm_tool
        self.intent_recognizer = IntentRecognizer()

    def retrieve(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """
        执行混合检索

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            检索结果
        """
        # 1. 意图识别
        intent_result = self.intent_recognizer.recognize(query)
        intent = IntentType(intent_result["intent"])

        logger.info(f"✓ 意图识别: {intent.value}, 置信度: {intent_result['confidence']:.2f}")

        # 2. 根据意图选择检索策略
        if intent == IntentType.INGREDIENT_QUERY or intent == IntentType.FORMULA_QUERY:
            result = self._precise_retrieval(query, intent, top_k)
        elif intent == IntentType.SYMPTOM_ANALYSIS or intent == IntentType.SYMPTOM_DISEASE:
            result = self._symptom_retrieval(query, intent, top_k)
        elif intent == IntentType.PRESCRIPTION_ADVICE or intent == IntentType.DISEASE_DRUG:
            result = self._prescription_retrieval(query, intent, top_k)
        elif intent in [IntentType.DISEASE_CHECK, IntentType.CHECK_DISEASE]:
            result = self._check_retrieval(query, intent, top_k)
        elif intent == IntentType.GENERAL_INQUIRY:
            result = self._general_retrieval(query, intent, top_k)
        else:
            result = self._vector_search(query, top_k)

        return result

    def _precise_retrieval(self, query: str, intent: IntentType,
                           top_k: int) -> Dict[str, Any]:
        """精确检索：图谱 + Grep"""
        logger.info(f"执行精确检索: {intent.value}")

        # 步骤1: 图谱检索
        graph_results = []
        try:
            if intent == IntentType.INGREDIENT_QUERY:
                # 提取药名
                drug_names = self._extract_entities(query, ["药物", "药", "方剂"])
                for name in drug_names[:3]:  # 取前3个
                    results = self.neo4j_tool.search_entity("Drug", name)
                    if results:
                        graph_results.extend(results)
            elif intent == IntentType.FORMULA_QUERY:
                # 查询方剂
                results = self.neo4j_tool.search_entity("Formula", query)
                if results:
                    graph_results = results[:top_k]
        except Exception as e:
            logger.error(f"✗ 图谱检索失败: {e}")

        # 步骤2: Grep检索补充
        grep_results = []
        try:
            grep_results = self.grep_tool.search(query)
        except Exception as e:
            logger.error(f"✗ Grep检索失败: {e}")

        # 步骤3: 如果图谱+Grep没有结果，回退到向量检索
        vector_results = []
        if not graph_results and not grep_results:
            try:
                vector_results = self.vector_tool.search(query, top_k=5)
                logger.info(f"✓ 回退到向量检索，获取 {len(vector_results)} 条结果")
            except Exception as e:
                logger.error(f"✗ 向量检索回退失败: {e}")

        # 步骤4: 结果融合（优先用图谱+Grep，没有则用向量）
        if vector_results:
            fused_results = vector_results
            vector_count = len(vector_results)
        else:
            fused_results = self._fuse_results(graph_results, grep_results,
                                               graph_weight=0.6, vector_weight=0.4)
            vector_count = 0

        return {
            "intent": intent.value,
            "retrieval_type": "hybrid_precise",
            "graph_results": len(graph_results),
            "grep_results": len(grep_results),
            "vector_results": vector_count,
            "fused_results": fused_results[:top_k]
        }

    def _symptom_retrieval(self, query: str, intent: IntentType,
                           top_k: int) -> Dict[str, Any]:
        """症状检索：图谱 + 向量"""
        logger.info(f"执行症状检索: {intent.value}")

        # 步骤1: 图谱检索（症状 → 疾病）
        graph_results = []
        try:
            # 提取症状
            symptoms = self._extract_entities(query, [
                "症状", "痛", "感觉", "咳", "烧", "热",
                "晕", "吐", "泻", "肿", "痒",
            ])
            # 兜底：提取不到时直接用 query 搜索
            if not symptoms:
                symptoms = [query]

            for symptom in symptoms[:2]:
                results = self.neo4j_tool.search_disease_by_symptom(symptom)
                if results:
                    graph_results.extend(results)
        except Exception as e:
            logger.error(f"✗ 症状图谱检索失败: {e}")

        # 步骤2: 向量检索补充
        vector_results = []
        try:
            vector_results = self.vector_tool.search(query, top_k=5)
        except Exception as e:
            logger.error(f"✗ 向量检索失败: {e}")

        # 步骤3: 结果融合
        fused_results = self._fuse_results(graph_results, vector_results,
                                           graph_weight=0.5, vector_weight=0.5)

        return {
            "intent": intent.value,
            "retrieval_type": "hybrid_symptom",
            "graph_results": len(graph_results),
            "vector_results": len(vector_results),
            "fused_results": fused_results[:top_k]
        }

    def _prescription_retrieval(self, query: str, intent: IntentType,
                                top_k: int) -> Dict[str, Any]:
        """用药建议检索：图谱 + 向量"""
        logger.info(f"执行用药建议检索: {intent.value}")

        # 步骤1: 图谱检索（疾病 → 用药）
        graph_results = []
        try:
            # 提取疾病（覆盖常见的病名关键词）
            diseases = self._extract_entities(query, [
                "病", "症", "炎", "痛", "咳", "烧", "热",
                "毒", "湿", "肿", "疮", "癣", "癌", "瘤",
                "压", "冒", "泻", "喘", "虚", "痹",
            ])
            # 兜底：提取不到时用 query 的第一个实体词（jieba 切出来的名词）
            if not diseases:
                try:
                    import jieba
                    words = jieba.lcut(query)
                    # 取第一个长度 ≥ 2 的词作为疾病名
                    for word in words:
                        if len(word) >= 2 and word not in ("什么", "怎么", "如何", "为什么", "需要", "可以", "这个", "那个"):
                            diseases = [word]
                            break
                except ImportError:
                    pass
            # 实在没有就用 query 前 4 个字
            if not diseases:
                diseases = [query[:4]]

            for disease in diseases[:2]:
                results = self.neo4j_tool.search_drug_by_disease(disease)
                if results:
                    graph_results.extend(results)
        except Exception as e:
            logger.error(f"✗ 用药图谱检索失败: {e}")

        # 步骤2: 向量检索补充
        vector_results = []
        try:
            vector_results = self.vector_tool.search(query, top_k=5)
        except Exception as e:
            logger.error(f"✗ 向量检索失败: {e}")

        # 步骤3: 结果融合
        fused_results = self._fuse_results(graph_results, vector_results,
                                           graph_weight=0.6, vector_weight=0.4)

        return {
            "intent": intent.value,
            "retrieval_type": "hybrid_prescription",
            "graph_results": len(graph_results),
            "vector_results": len(vector_results),
            "fused_results": fused_results[:top_k]
        }

    def _check_retrieval(self, query: str, intent: IntentType,
                         top_k: int) -> Dict[str, Any]:
        """检查相关检索：图谱 + Grep"""
        logger.info(f"执行检查检索: {intent.value}")

        # 步骤1: 图谱检索
        graph_results = []
        try:
            results = self.neo4j_tool.search_entity("Check", query)
            if results:
                graph_results = results[:top_k]
        except Exception as e:
            logger.error(f"✗ 检查图谱检索失败: {e}")

        # 步骤2: Grep检索补充
        grep_results = []
        try:
            grep_results = self.grep_tool.search(query)
        except Exception as e:
            logger.error(f"✗ Grep检索失败: {e}")

        # 步骤3: 结果融合
        fused_results = self._fuse_results(graph_results, grep_results,
                                           graph_weight=0.5, vector_weight=0.5)

        return {
            "intent": intent.value,
            "retrieval_type": "hybrid_check",
            "graph_results": len(graph_results),
            "grep_results": len(grep_results),
            "vector_results": 0,
            "fused_results": fused_results[:top_k]
        }

    def _general_retrieval(self, query: str, intent: IntentType,
                           top_k: int) -> Dict[str, Any]:
        """一般检索：向量 + Grep + 图谱补充"""
        logger.info(f"执行一般检索: {intent.value}")

        # 向量检索
        vector_results = []
        try:
            vector_results = self.vector_tool.search(query, top_k=5)
        except Exception as e:
            logger.error(f"✗ 向量检索失败: {e}")

        # Grep检索
        grep_results = []
        try:
            grep_results = self.grep_tool.search(query)
        except Exception as e:
            logger.error(f"✗ Grep检索失败: {e}")

        # 图谱补充检索（如果问题涉及疾病，尝试查 Neo4j）
        graph_results = []
        try:
            diseases = self._extract_entities(query, [
                "病", "症", "炎", "痛", "咳", "烧", "热",
                "毒", "湿", "肿", "疮", "癣", "癌", "瘤",
                "压", "冒", "泻", "喘", "虚", "痹",
            ])
            if diseases:
                for disease in diseases[:2]:
                    results = self.neo4j_tool.search_drug_by_disease(disease)
                    if results:
                        graph_results.extend(results)
        except Exception as e:
            logger.debug(f"图谱补充检索跳过: {e}")

        # 结果融合（有图谱结果则一起融合）
        if graph_results:
            logger.info(f"图谱补充检索到 {len(graph_results)} 条结果")
            fused_results = self._fuse_results(vector_results, graph_results,
                                               graph_weight=0.4, vector_weight=0.6)
        else:
            fused_results = self._fuse_results(vector_results, grep_results,
                                               graph_weight=0.3, vector_weight=0.7)

        return {
            "intent": intent.value,
            "retrieval_type": "hybrid_general",
            "graph_results": len(graph_results),
            "vector_results": len(vector_results),
            "grep_results": len(grep_results),
            "fused_results": fused_results[:top_k]
        }

    def _vector_search(self, query: str, top_k: int) -> Dict[str, Any]:
        """向量检索（默认）"""
        logger.info("执行向量检索（默认）")

        vector_results = []
        try:
            vector_results = self.vector_tool.search(query, top_k=top_k)
        except Exception as e:
            logger.error(f"✗ 向量检索失败: {e}")

        return {
            "intent": "general_inquiry",
            "retrieval_type": "vector_only",
            "vector_results": len(vector_results),
            "fused_results": vector_results[:top_k]
        }

    def _fuse_results(self, results1: List, results2: List,
                      graph_weight: float = 0.5, vector_weight: float = 0.5) -> List[Dict]:
        """
        融合两种检索结果

        Args:
            results1: 第一种检索结果
            results2: 第二种检索结果
            graph_weight: 第一种结果的权重
            vector_weight: 第二种结果的权重

        Returns:
            融合后的结果
        """
        # 创建结果字典（以实体名称为键）
        result_dict = {}

        # 处理第一种结果（通常是图谱结果）
        for item in results1:
            name = self._extract_name(item)
            if name:
                score = item.get("score", None)
                if score is None:
                    score = 1.0  # 图谱精确匹配默认满分
                result_dict[name] = {
                    "name": name,
                    "score": score * graph_weight,
                    "source": item.get("source", "graph"),
                    "content": item.get("content", ""),
                }

        # 处理第二种结果（通常是向量结果）
        for item in results2:
            name = self._extract_name(item)
            if name:
                score = item.get("score", 0.0)
                if name in result_dict:
                    result_dict[name]["score"] += score * vector_weight
                    result_dict[name]["source"] = result_dict[name]["source"] + "+vector"
                    # 向量结果优先保留更完整的 content
                    if not result_dict[name].get("content"):
                        result_dict[name]["content"] = item.get("content", "")
                else:
                    result_dict[name] = {
                        "name": name,
                        "score": score * vector_weight,
                        "source": item.get("source", "vector"),
                        "content": item.get("content", ""),
                    }

        # 转换为列表并排序
        fused_list = list(result_dict.values())
        fused_list.sort(key=lambda x: x["score"], reverse=True)

        return fused_list

    def _extract_name(self, item: Any) -> Optional[str]:
        """从检索结果中提取名称"""
        try:
            if isinstance(item, dict):
                # 1. 直取 name 字段（标准格式）
                name = item.get("name")
                if name:
                    return name

                # 2. entity 嵌套（某些中间格式）
                entity = item.get("entity")
                if isinstance(entity, dict):
                    name = entity.get("name")
                    if name:
                        return name

                # 3. Neo4j 节点格式：record.data() 返回 {节点标签: Node对象}
                #    Node 对象支持 .get("property") 取属性
                #    按优先级尝试各节点标签
                for key in ("drug", "disease", "symptom", "d", "m", "n"):
                    node = item.get(key)
                    if node is not None:
                        if isinstance(node, dict):
                            name = node.get("name")
                        else:
                            try:
                                name = node.get("name")
                            except Exception:
                                name = None
                        if name:
                            return name

                # 4. 兜底——向量结果没有 name，用 content 前缀标识
                content = item.get("content", "")
                if content:
                    return content[:60]

                return None

            elif hasattr(item, "name"):
                return item.name
            return None
        except Exception:
            return None

    def _extract_entities(self, query: str, keywords: List[str]) -> List[str]:
        """从查询中提取实体（关键词）"""
        entities = []

        # 方法1: jieba 分词（优先，能正确切出"糖尿病"这种复合词）
        try:
            import jieba
            words = jieba.lcut(query)
            for word in words:
                if len(word) >= 2:
                    for kw in keywords:
                        if kw in word and word not in entities:
                            entities.append(word)
        except ImportError:
            pass

        # 方法2: 正则匹配（处理"发烧症状"、"头痛怎么治"等 jieba 分不出的结构）
        if not entities:
            for keyword in keywords:
                pattern = rf"{keyword}[：:]*\s*([^\s，,，]+)"
                match = re.search(pattern, query)
                if match and match.group(1) not in entities:
                    entities.append(match.group(1))

        return entities

    def get_retrieval_stats(self) -> Dict[str, Any]:
        """获取检索统计信息"""
        try:
            graph_stats = self.neo4j_tool.get_graph_stats()
            vector_stats = self.vector_tool.get_stats()

            return {
                "graph_nodes": graph_stats.get("total_nodes", 0),
                "graph_relationships": graph_stats.get("total_relationships", 0),
                "vector_entities": vector_stats.get("num_entities", 0),
                "vector_dimension": vector_stats.get("dimension", 0)
            }
        except Exception as e:
            logger.error(f"✗ 获取统计失败: {e}")
            return {}
