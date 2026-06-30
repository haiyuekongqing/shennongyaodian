"""
安全过滤模块
检测和处理不安全的输入和输出
"""
import re
import logging
from typing import List, Dict, Any, Optional, Tuple

from src.models.base import db_manager
from src.models.medica_data import MedicalDisclaimer

logger = logging.getLogger(__name__)


class SecurityFilter:
    """安全过滤器"""

    # 敏感词汇列表
    SENSITIVE_WORDS = [
        '治愈', '绝对', '100%', '保证', '必须', '严禁', '禁止',
        '推荐', '建议', '处方', '方子', '配方', '药方',
        '处方药', '处方', '成瘾', '依赖', '耐药性', '耐药'
    ]

    # 违禁医疗术语
    FORBIDDEN_TERMS = [
        '代替医生', '代替治疗', '代替药品', '代替处方',
        '推荐处方', '推荐药品', '代替医生诊断',
        '治愈', '保证痊愈', '100%有效', '绝对有效',
        '必须使用', '必须服用', '严禁停药', '严禁中断'
    ]

    # 违规回答模式
    VIOLATION_PATTERNS = [
        r'(?:治愈|保证|必须|100%|绝对).*?有效',  # 包含违规词汇
        r'(?:推荐|建议).*?处方',  # 推荐处方
        r'(?:代替|替代).*?医生',  # 代替医生
        r'(?:治愈|痊愈).*?必须',  # 承诺治愈
    ]

    def __init__(self):
        """初始化安全过滤器"""
        self.disclaimer_text = self._get_disclaimer()

    def _get_disclaimer(self) -> str:
        """
        获取免责声明

        Returns:
            免责声明文本
        """
        try:
            from sqlalchemy import text
            with db_manager.get_session() as session:
                result = session.execute(
                    text("SELECT disclaimer_text FROM medical_disclaimers WHERE is_enabled=1 LIMIT 1")
                ).first()
                if result:
                    return result[0]
        except Exception as e:
            logger.error(f"✗ 获取免责声明失败: {e}")

        return "免责声明：本系统提供的信息仅供参考，不构成医疗建议。如遇健康问题，请咨询专业医生或药师。"

    def filter_input(self, user_input: str) -> Tuple[bool, str]:
        """
        过滤用户输入

        Args:
            user_input: 用户输入

        Returns:
            (是否通过过滤, 错误信息)
        """
        user_input_lower = user_input.lower()

        # 检查敏感词汇
        for word in self.SENSITIVE_WORDS:
            if word in user_input:
                return False, f"输入包含敏感词汇: {word}"

        # 检查违禁术语
        for term in self.FORBIDDEN_TERMS:
            if term in user_input:
                return False, f"输入包含违禁术语: {term}"

        # 检查违规模式
        for pattern in self.VIOLATION_PATTERNS:
            if re.search(pattern, user_input_lower):
                return False, "输入包含违规表述"

        return True, ""

    def filter_output(self, generated_text: str) -> Tuple[bool, str]:
        """
        过滤生成文本

        Args:
            generated_text: 生成文本

        Returns:
            (是否通过过滤, 错误信息)
        """
        generated_text_lower = generated_text.lower()

        # 检查敏感词汇
        for word in self.SENSITIVE_WORDS:
            if word in generated_text:
                return False, f"输出包含敏感词汇: {word}"

        # 检查违规模式
        for pattern in self.VIOLATION_PATTERNS:
            if re.search(pattern, generated_text_lower):
                return False, "输出包含违规表述"

        return True, ""

    def inject_disclaimer(self, text: str, position: str = "append") -> str:
        """
        注入免责声明

        Args:
            text: 原始文本
            position: 注入位置 ("append" - 附加到末尾, "prepend" - 添加到开头)

        Returns:
            包含免责声明的文本
        """
        if position == "append":
            return text + "\n\n" + self.disclaimer_text
        elif position == "prepend":
            return self.disclaimer_text + "\n\n" + text
        else:
            return text

    def validate_response_format(self, response: Dict[str, Any]) -> Tuple[bool, str]:
        """
        验证响应格式

        Args:
            response: 响应字典

        Returns:
            (是否通过验证, 错误信息)
        """
        # 检查必需字段
        if "answer" not in response:
            return False, "响应缺少 answer 字段"

        # 检查免责声明字段
        if "disclaimer" not in response:
            return False, "响应缺少 disclaimer 字段"

        return True, ""

    def sanitize_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        清理响应

        Args:
            response: 响应字典

        Returns:
            清理后的响应
        """
        # 验证格式
        is_valid, error_msg = self.validate_response_format(response)
        if not is_valid:
            logger.warning(f"⚠ 响应格式验证失败: {error_msg}")
            response["error"] = error_msg
            return response

        # 过滤输出
        answer = response.get("answer", "")
        is_safe, error_msg = self.filter_output(answer)
        if not is_safe:
            logger.warning(f"⚠ 输出内容不安全: {error_msg}")
            response["answer"] = answer + "\n\n(抱歉，该回答包含敏感词汇，已被过滤)"
            response["warning"] = error_msg
        else:
            # 注入免责声明
            response["answer"] = self.inject_disclaimer(answer, position="append")

        return response

    def check_medical_advice_quality(self, answer: str) -> Dict[str, Any]:
        """
        检查医疗建议质量

        Args:
            answer: 回答内容

        Returns:
            检查结果字典
        """
        result = {
            "has_disclaimer": self.disclaimer_text in answer,
            "sensitive_words": [],
            "has_formula": "方剂" in answer or "处方" in answer,
            "has_dosage": "剂量" in answer,
            "has_contraindications": "禁忌" in answer or "慎用" in answer or "忌" in answer,
        }

        # 检查敏感词汇
        for word in self.SENSITIVE_WORDS:
            if word in answer:
                result["sensitive_words"].append(word)

        # 评分
        score = 0
        if result["has_disclaimer"]:
            score += 1
        if result["has_dosage"]:
            score += 1
        if result["has_contraindications"]:
            score += 1
        if result["has_formula"]:
            score += 1

        result["score"] = score
        result["passed"] = score >= 2  # 至少 2 分才算通过

        return result

    def get_safe_prompt_template(self) -> str:
        """
        获取安全的系统 Prompt 模板

        Returns:
            安全的系统 Prompt
        """
        return f"""你是一个专业的中草药智能问答助手。你的职责是：

1. 准确回答用户关于中草药、中医理论、疾病症状和用药建议的问题
2. 所有回答必须基于提供的参考资料，严禁编造医学知识
3. 如果你不知道答案，或者提供的参考资料中没有相关信息，请直接回答'抱歉，我目前无法确认该信息'

注意事项：
- 严格区分'疗效'、'作用'、'功效'等不同概念
- 对于成分复杂的中草药，提供准确的性味归经和功效描述
- 用药建议必须明确适用症、剂量和禁忌
- 对于不确定的信息，必须明确说明'无法确认'
- 不要使用'治愈'、'保证'、'必须'、'100%'、'绝对'等词汇
- 不要推荐处方或方子
- 不要代替医生诊断或治疗
- 回答末尾必须包含免责声明

医疗免责声明：
免责声明：本系统提供的信息仅供参考，不构成医疗建议。如遇健康问题，请咨询专业医生或药师。
"""

    def add_safety_annotation(self, text: str, keyword: str) -> str:
        """
        添加安全标注

        Args:
            text: 原始文本
            keyword: 关键词

        Returns:
            添加标注的文本
        """
        return f"[{keyword}] {text}"
