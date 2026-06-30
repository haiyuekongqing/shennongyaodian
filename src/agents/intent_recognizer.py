"""
意图识别器 - 18类医疗问题分类
"""
import re
import logging
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class IntentType(Enum):
    """意图类型枚举"""
    # 基础查询
    INGREDIENT_QUERY = "ingredient_query"      # 中草药查询
    FORMULA_QUERY = "formula_query"             # 方剂查询

    # 症状相关
    SYMPTOM_ANALYSIS = "symptom_analysis"       # 症状分析
    SYMPTOM_DISEASE = "symptom_disease"         # 已知症状找疾病
    DISEASE_CAUSE = "disease_cause"             # 疾病病因
    DISEASE_SYMPTOM = "disease_symptom"         # 疾病症状

    # 用药相关
    PRESCRIPTION_ADVICE = "prescription_advice" # 用药建议
    DRUG_DISEASE = "drug_disease"               # 药品能治啥病
    DISEASE_DRUG = "disease_drug"               # 啥病要吃啥药

    # 饮食相关
    DISEASE_NOT_FOOD = "disease_not_food"       # 疾病忌口食物
    DISEASE_DO_FOOD = "disease_do_food"         # 疾病宜吃食物
    FOOD_NOT_DISEASE = "food_not_disease"       # 什么病不宜吃某食物
    FOOD_DO_DISEASE = "food_do_disease"         # 食物对什么病有好处

    # 疾病相关
    DISEASE_ACCOMPANY = "disease_acompany"      # 疾病的并发症
    DISEASE_CHECK = "disease_check"             # 疾病所需检查
    CHECK_DISEASE = "check_disease"             # 检查能查什么病
    DISEASE_PREVENT = "disease_prevent"         # 预防措施
    DISEASE_LASTTIME = "disease_lasttime"       # 治疗周期
    DISEASE_CUREWAY = "disease_cureway"         # 治疗方式
    DISEASE_CUREPROB = "disease_cureprob"       # 治愈概率
    DISEASE_EASYGET = "disease_easyget"         # 疾病易感人群

    # 通用
    GENERAL_INQUIRY = "general_inquiry"         # 一般咨询
    UNKNOWN = "unknown"                         # 未知


class IntentRecognizer:
    """意图识别器"""

    # 18类问题模板
    INTENT_TEMPLATES = {
        IntentType.INGREDIENT_QUERY: [
            "什么", "功效", "性味归经", "主治", "作用", "特点",
            r"(\w+)有什么.*功效",
            r"(\w+)的.*性味归经"
        ],
        IntentType.FORMULA_QUERY: [
            "方剂", "组成", "成分", "配方", "成分组成"
        ],
        IntentType.SYMPTOM_ANALYSIS: [
            "症状", "哪里痛", "老流鼻涕", "最近有.*症状",
            r"有.*症状", r"患有.*症状"
        ],
        IntentType.SYMPTOM_DISEASE: [
            "老流鼻涕怎么办", "最近老流鼻涕", r"有.*症状.*怎么办",
            r".*症状.*可能.*疾病", r"有.*症状.*是什么病"
        ],
        IntentType.DISEASE_CAUSE: [
            "原因", "为什么", "病因", r"为什么.*会.*",
            r".*的原因", "为什么会"
        ],
        IntentType.DISEASE_SYMPTOM: [
            "症状", "有什么症状", r"(\w+)的症状.*有哪些"
        ],
        IntentType.PRESCRIPTION_ADVICE: [
            "吃什么", "忌口", "宜吃", "不能吃", "不要吃",
            r"吃什么.*药", r"应该吃什么.*药", r"(\w+)的用药", "用药建议", "用药方案"
        ],
        IntentType.DRUG_DISEASE: [
            r"(\w+)能治.*什么.*病", r"(\w+)能治疗.*什么",
            r"(\w+)对.*什么.*病.*有好处"
        ],
        IntentType.DISEASE_DRUG: [
            r"什么病.*要吃.*(\w+)", r"(\w+).*要吃什么药",
            r"患有.*吃什么.*药"
        ],
        IntentType.DISEASE_NOT_FOOD: [
            "忌口", "不能吃", "不要吃", r"不宜吃.*的",
            r"忌食.*的"
        ],
        IntentType.DISEASE_DO_FOOD: [
            "宜吃", "应该吃", r"应该吃.*的",
            r"推荐吃.*的", r"适宜吃.*的"
        ],
        IntentType.FOOD_NOT_DISEASE: [
            r"什么病.*最好.*不吃.*(\w+)", r"什么病.*不宜.*吃.*(\w+)",
            r"什么病.*不能.*吃.*(\w+)"
        ],
        IntentType.FOOD_DO_DISEASE: [
            r"(\w+)对.*什么病.*有好处", r"(\w+)有什么好处",
            r"吃.*(\w+)有什么好处"
        ],
        IntentType.DISEASE_ACCOMPANY: [
            "并发症", "并发疾病", "可能并发",
            r"(\w+)的.*并发症", r"(\w+)可能并发"
        ],
        IntentType.DISEASE_CHECK: [
            "检查", "怎么查", "怎么才能查出来", r"通过.*检查.*能查出来"
        ],
        IntentType.CHECK_DISEASE: [
            r"(\w+)能查出.*什么", r"(\w+)能检查出什么病",
            r"全血.*计数能查出啥来"
        ],
        IntentType.DISEASE_PREVENT: [
            "预防", "怎么预防", r"怎样才能.*预防"
        ],
        IntentType.DISEASE_LASTTIME: [
            "周期", "多久", r"要多久.*才能好",
            r"治疗.*周期", r"需要.*多久"
        ],
        IntentType.DISEASE_CUREWAY: [
            "治疗", "怎么治", r"要怎么治", r"治疗方法"
        ],
        IntentType.DISEASE_CUREPROB: [
            "治愈", "治得好吗", r"能治好吗", r"治愈概率"
        ],
        IntentType.DISEASE_EASYGET: [
            "易感", "什么人", r"什么人容易得",
            r"易感人群", r"高危人群"
        ],
        IntentType.GENERAL_INQUIRY: [
            "什么是", r".*是什么", "的介绍", "概况"
        ]
    }

    def __init__(self):
        """初始化意图识别器"""
        self.keywords = self._build_keywords_map()

    def _build_keywords_map(self) -> Dict[IntentType, list]:
        """构建关键词映射（将所有模板编译为正则）"""
        keyword_map = {}
        for intent, templates in self.INTENT_TEMPLATES.items():
            keywords = []
            for template in templates:
                if isinstance(template, re.Pattern):
                    keywords.append(template)
                elif isinstance(template, str):
                    # 编译为正则模式（让 r"吃什么.*药" 这类字符串真正生效）
                    try:
                        keywords.append(re.compile(template, re.IGNORECASE))
                    except re.error:
                        keywords.append(re.compile(re.escape(template), re.IGNORECASE))
            keyword_map[intent] = keywords
        return keyword_map

    def recognize(self, query: str) -> Dict[str, Any]:
        """
        识别用户问题意图

        Args:
            query: 用户问题

        Returns:
            识别结果字典
        """
        if not query or not query.strip():
            return {
                "intent": IntentType.UNKNOWN,
                "confidence": 0.0,
                "keywords": [],
                "query": query
            }

        query_lower = query.lower().strip()
        keywords = self._extract_keywords(query)

        # 基于规则匹配
        rule_result = self._rule_based_classification(query_lower, keywords)

        # 如果规则匹配度高，直接返回
        if rule_result["confidence"] > 0.7:
            return {
                "intent": rule_result["intent"],
                "confidence": rule_result["confidence"],
                "keywords": keywords,
                "query": query
            }

        # 模糊匹配（可选：基于LLM的分类）
        # 这里先返回规则匹配结果
        return rule_result

    def _rule_based_classification(self, query_lower: str,
                                    keywords: list) -> Dict[str, Any]:
        """
        基于规则的分类

        Args:
            query_lower: 小写的查询字符串
            keywords: 提取的关键词

        Returns:
            分类结果
        """
        # 统计每个意图的关键词匹配数
        scores = {}
        for intent, intent_keywords in self.keywords.items():
            score = 0

            for kw in intent_keywords:
                if kw.search(query_lower):
                    score += 1

            if score > 0:
                scores[intent.value] = score

        # 找出得分最高的意图
        if scores:
            best_intent = max(scores, key=scores.get)
            kw_count = len(self.keywords.get(best_intent, []))
            confidence = (scores[best_intent] / kw_count + 0.3) if kw_count > 0 else 0.3
        else:
            best_intent = IntentType.GENERAL_INQUIRY.value
            confidence = 0.1

        # 处理特殊情况
        # 如果是查询成分或功效，明确是ingredient_query
        if any(kw in query_lower for kw in ["成分", "作用", "特点"]):
            best_intent = IntentType.INGREDIENT_QUERY.value
            confidence = 0.8

        # 如果是方剂查询，明确是formula_query
        if "方剂" in query_lower:
            best_intent = IntentType.FORMULA_QUERY.value
            confidence = 0.9

        # 如果是症状分析，明确是symptom_analysis
        if any(kw in query_lower for kw in ["症状", "哪里痛", "痛"]):
            best_intent = IntentType.SYMPTOM_ANALYSIS.value
            confidence = 0.8

        return {
            "intent": best_intent,
            "confidence": min(confidence, 1.0),
            "keywords": keywords,
            "query": query_lower
        }

    def _extract_keywords(self, query: str) -> list:
        """
        提取查询中的关键词

        Args:
            query: 查询字符串

        Returns:
            关键词列表
        """
        # 简单的关键词提取：提取2-4个字符的连续字符
        words = re.findall(r'\w{2,}', query)
        return list(set(words))

    def get_intent_description(self, intent: IntentType) -> str:
        """获取意图的中文描述"""
        descriptions = {
            IntentType.INGREDIENT_QUERY: "中草药查询",
            IntentType.FORMULA_QUERY: "方剂查询",
            IntentType.SYMPTOM_ANALYSIS: "症状分析",
            IntentType.SYMPTOM_DISEASE: "症状-疾病查询",
            IntentType.DISEASE_CAUSE: "疾病病因查询",
            IntentType.DISEASE_SYMPTOM: "疾病症状查询",
            IntentType.PRESCRIPTION_ADVICE: "用药建议查询",
            IntentType.DRUG_DISEASE: "药品-疾病查询",
            IntentType.DISEASE_DRUG: "疾病-药品查询",
            IntentType.DISEASE_NOT_FOOD: "疾病忌口查询",
            IntentType.DISEASE_DO_FOOD: "疾病宜吃查询",
            IntentType.FOOD_NOT_DISEASE: "食物-疾病查询",
            IntentType.FOOD_DO_DISEASE: "食物-疾病查询",
            IntentType.DISEASE_ACCOMPANY: "疾病并发症查询",
            IntentType.DISEASE_CHECK: "疾病检查查询",
            IntentType.CHECK_DISEASE: "检查-疾病查询",
            IntentType.DISEASE_PREVENT: "疾病预防查询",
            IntentType.DISEASE_LASTTIME: "治疗周期查询",
            IntentType.DISEASE_CUREWAY: "治疗方法查询",
            IntentType.DISEASE_CUREPROB: "治愈概率查询",
            IntentType.DISEASE_EASYGET: "易感人群查询",
            IntentType.GENERAL_INQUIRY: "一般咨询",
            IntentType.UNKNOWN: "未知"
        }
        return descriptions.get(intent, "未知")


# 测试代码
if __name__ == "__main__":
    recognizer = IntentRecognizer()

    test_queries = [
        "人参有什么功效？",
        "老流鼻涕可能是什么病？",
        "失眠有什么并发症？",
        "糖尿病要吃什么药？",
        "吃蜂蜜有什么好处？",
        "感冒要多久才能好？",
        "什么人容易得高血压？",
        "黄芪归什么经？"
    ]

    for query in test_queries:
        result = recognizer.recognize(query)
        print(f"问题: {query}")
        print(f"意图: {result['intent']}")
        print(f"置信度: {result['confidence']:.2f}")
        print(f"关键词: {result['keywords']}")
        print(f"描述: {recognizer.get_intent_description(IntentType(result['intent']))}")
        print("-" * 60)
