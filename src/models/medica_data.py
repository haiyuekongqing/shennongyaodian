"""
中草药数据模型
"""
from sqlalchemy import Column, String, Text, JSON, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base.database import BaseModel


class TCMIngredient(BaseModel):
    """中草药元数据表"""
    __tablename__ = 'tcm_ingredients'

    # 基本信息
    chinese_name = Column(String(255), unique=True, nullable=False, index=True)
    english_name = Column(String(255), nullable=True)
    latin_name = Column(String(255), nullable=True)

    # 性味归经
    taste = Column(JSON, nullable=True)  # [温, 甘, 苦, etc.]
    property = Column(String(50), nullable=True)  # 温, 凉, 寒, 热等
    meridian = Column(JSON, nullable=True)  # [肺, 脾, 肾, etc.]

    # 功效
    functions = Column(JSON, nullable=True)  # [补气固表, 利尿托毒, etc.]

    # 主治
    indications = Column(JSON, nullable=True)  # [用于气虚乏力, 食少便溏, etc.]

    # 剂量
    dose = Column(String(100), nullable=True)  # 如：6-12g

    # 禁忌
    contraindications = Column(JSON, nullable=True)  # [孕妇慎用, etc.]

    # 相互作用
    interactions = Column(JSON, nullable=True)  # [不宜与某药同用, etc.]

    # 现代研究
    modern_research = Column(JSON, nullable=True)  # [活性成分, 药理作用, etc.]

    # 来源
    source = Column(String(500), nullable=True)  # 如：豆科黄芪属

    # 备注
    notes = Column(Text, nullable=True)

    # 关系
    knowledge_references = relationship("KnowledgeReference", back_populates="ingredient")


class KnowledgeReference(BaseModel):
    """知识库引用表（关联中草药与知识文档）"""
    __tablename__ = 'knowledge_references'

    # 关联的中草药ID
    ingredient_id = Column(String(36), ForeignKey('tcm_ingredients.id'), nullable=True, index=True)
    ingredient = relationship("TCMIngredient", back_populates="knowledge_references")

    # 知识库文件路径
    file_path = Column(String(500), nullable=False, index=True)

    # 文件类型
    file_type = Column(String(50), nullable=False)  # 'pharmacopedia', 'treatise', 'case'

    # 文件标题
    file_title = Column(String(255), nullable=True)

    # 在文件中的位置
    position_in_file = Column(JSON, nullable=True)  # [chapter, section, paragraph]

    # 引用摘要
    reference_summary = Column(Text, nullable=True)

    # 相关度分数
    relevance_score = Column(Integer, default=0)  # 0-100


class KnowledgeBaseConfig(BaseModel):
    """知识库配置表"""
    __tablename__ = 'knowledge_base_config'

    # 集合名称
    collection_name = Column(String(255), unique=True, nullable=False)

    # Embedding 模型
    embedding_model = Column(String(100), nullable=False)

    # 描述
    description = Column(Text, nullable=True)

    # 状态
    status = Column(String(50), default='active')  # 'active', 'inactive', 'updating'

    # 数据统计
    total_documents = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)
    last_updated = Column(DateTime, nullable=True)


class UserSession(BaseModel):
    """用户会话表"""
    __tablename__ = 'user_sessions'

    # 用户标识
    user_id = Column(String(255), nullable=True, index=True)

    # 会话标识
    session_id = Column(String(255), nullable=True, index=True)

    # 会话标题
    session_title = Column(String(255), nullable=True)

    # 对话历史
    chat_history = Column(JSON, nullable=True)  # [messages]

    # 最后更新时间
    last_active = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 是否活跃
    is_active = Column(Boolean, default=True)


class QueryLog(BaseModel):
    """查询日志表"""
    __tablename__ = 'query_logs'

    # 用户ID
    user_id = Column(String(255), nullable=True)

    # 查询内容
    query = Column(Text, nullable=False)

    # 检索到的文档
    retrieved_documents = Column(JSON, nullable=True)  # [doc_ids]

    # 生成的回答
    answer = Column(Text, nullable=True)

    # 是否需要免责声明
    needs_disclaimer = Column(Boolean, default=True)

    # 执行时间（毫秒）
    execution_time = Column(Integer, nullable=True)

    # 错误信息
    error_message = Column(Text, nullable=True)


class ImportedFile(BaseModel):
    """已导入文件跟踪表（用于去重，基于内容哈希）"""
    __tablename__ = 'imported_files'

    # 文件 SHA-256 哈希（唯一约束确保不重复导入）
    file_hash = Column(String(64), unique=True, nullable=False, index=True, comment='文件 SHA-256 哈希')

    # 文件信息
    file_path = Column(String(500), nullable=True, comment='原始文件路径')
    file_name = Column(String(255), nullable=True, comment='文件名')

    # 导入统计
    chunk_count = Column(Integer, default=0, comment='导入的分块数')

    # 导入时间
    imported_at = Column(DateTime, default=datetime.now, comment='导入时间')


class MedicalDisclaimer(BaseModel):
    """医疗免责声明表"""
    __tablename__ = 'medical_disclaimers'

    # 免责声明内容
    disclaimer_text = Column(Text, nullable=False)

    # 适用场景
    applicable_scenarios = Column(JSON, nullable=True)  # ['medical_advice', 'medicine_recommendation']

    # 语言
    language = Column(String(10), default='zh')

    # 版本号
    version = Column(String(20), default='1.0')

    # 是否启用
    is_enabled = Column(Boolean, default=True)
