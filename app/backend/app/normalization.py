"""规范化：把原字形转换为用于匹配的规范形。

关键边界：
* 规范化只作用于匹配层，token.display（原字形）永不改变；
* unknown / lacuna / blank / annotation 不产生匹配形（norm 保持 ""），
  任何规则都不允许把"未知字"变成确定的字；
* 规则来源有三：库中 NormalizationRule、转录内联【原→范】、内置异体字表。
"""
from __future__ import annotations

from .transcription import Token

# 内置常用异体/俗字表（示例性质，可在数据库规则中扩充）
BUILTIN_VARIANTS: dict[str, str] = {
    "无": "无",
    "峯": "峰",
    "群": "群",
    "峰": "峰",
    "㸦": "互",
    "于": "于",
    "於": "于",
    "后": "后",
    "後": "后",
    "才": "才",
    "纔": "才",
    "徧": "遍",
    "覩": "睹",
    "畧": "略",
    "眞": "真",
    "旣": "既",
    "爲": "为",
    "來": "来",
    "書": "书",
    "學": "学",
    "經": "经",
    "雲": "云",
    "谿": "溪",
    "砎": "界",
}


class Normalizer:
    def __init__(self, rules: list[tuple[str, str]] | None = None, use_builtin: bool = True):
        # rules: (pattern, replacement)，已按优先级与适用范围过滤、排序
        self._rules: list[tuple[str, str]] = list(rules or [])
        self._builtin = dict(BUILTIN_VARIANTS) if use_builtin else {}

    def normalize_char(self, display: str) -> str:
        for pattern, replacement in self._rules:
            if pattern == display:
                return replacement
        return self._builtin.get(display, display)

    def apply(self, tokens: list[Token]) -> None:
        """就地写 token.norm；非正文/未知项一律跳过。"""
        for t in tokens:
            if t.kind != "char":
                continue
            # 内联【原→范】已在解析时给出 norm，只有在它仍等于 display 时才覆盖
            if not t.norm or t.norm == t.display:
                t.norm = self.normalize_char(t.display)
