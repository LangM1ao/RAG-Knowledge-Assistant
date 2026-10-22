"""文档别名的请求结构；事实仍只能来自上传文件。"""
from pydantic import BaseModel, Field


class DocumentAliasesRequest(BaseModel):
    entity_name: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list, max_length=12)
