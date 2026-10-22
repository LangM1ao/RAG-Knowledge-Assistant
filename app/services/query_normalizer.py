"""统一查询和词项格式；不猜测实体对应关系，也不调用模型翻译。"""
import re
import unicodedata


def normalize_query(text: str) -> str:
    # NFKC 将全角字母/数字转为普通形式，casefold 统一大小写。
    text = unicodedata.normalize('NFKC', text).casefold()
    text = text.translate(str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"'}))
    return re.sub(r'\s+', ' ', text).strip()
