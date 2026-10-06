"""自制样例数据（虚构文本，无版权问题）。

覆盖需求中要求的全部情形：
* 异体字：無/无、峯/峰、後/后、觀/覌
* 重复短句："燈火熒然。" 重复出现，考验对齐器是否错锚
* 不同断句：甲本"夜分，誦聲"与乙本"夜分誦聲，"、丙本"夜分，誦聲，"
* 脱文：丙本脱"窓月"
* 批注/添补/按语（插入片段）锚定相邻位置
* 缺叶标记〔缺二叶〕与空白正文〔空白〕严格不同
* 残泐未知字 □，不得被猜补
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import NormalizationRule, Passage, Witness

JIA = (
    "某嵗深秋，余讀書於北山之【峯→峰】。夜分，誦聲出林下，"
    "窓月皎然，了無人跡。燈火熒然。"
    "［批注：燈下似有老人影］"
    "明日，求其處，惟見敗葉埋逕而已。"
    "後人莫曉其事，姑識於此。"
)

YI = (
    "某歲深秋，余讀書於北山之峯。夜分誦聲，出林下，"
    "窓月皎然，了無人跡。燈火熒然。燈火熒然。"
    "明日，求其處，惟見敗葉埋逕而已。"
    "［添：此處疑有脫簡］"
    "後人莫覌其事，姑識於此。"
)

BING = (
    "某歲深秋，余讀書於北山之峰。夜分，誦聲，出林下。"
    "〔缺二叶〕"
    "〔空白〕"
    "燈火熒然。"
    "明日求其處，惟見敗葉埋逕而□。"
    "［按：□當是『已』字殘泐，存疑不補］"
    "後人莫曉其事，姑識於此。"
)


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(Passage).limit(1)) is not None:
        return
    p = Passage(
        title="《北山夜誦》殘卷（擬古）",
        description="自制擬古籍片段，含三個見本，用於驗證異體字、脫文、批注、"
                    "缺葉與空白、殘泐字、重複短句及斷句差異的分欄校勘。",
    )
    db.add(p)
    db.flush()
    db.add_all([
        Witness(passage_id=p.id, siglum="甲本", label="清抄本（甲）",
                source_note="私家藏清中期抄本，天頭有朱筆批注",
                raw_transcription=JIA, sort_order=0),
        Witness(passage_id=p.id, siglum="乙本", label="民國石印本（乙）",
                source_note="民國間石印小冊，欄外有添字",
                raw_transcription=YI, sort_order=1),
        Witness(passage_id=p.id, siglum="丙本", label="敦煌綴合殘卷（丙）",
                source_note="擬敦煌卷子編號 P.0000，中間缺二葉，卷面有空白",
                raw_transcription=BING, sort_order=2),
    ])
    # 规范化规则只作用于匹配层，原转录不动
    db.add_all([
        NormalizationRule(passage_id=p.id, pattern="嵗", replacement="歲",
                          note="嵗為歲之俗寫"),
        NormalizationRule(passage_id=p.id, pattern="窓", replacement="窗",
                          note="窓為窗之異構"),
        NormalizationRule(passage_id=p.id, pattern="逕", replacement="徑",
                          note="逕徑古今字"),
        NormalizationRule(passage_id=p.id, pattern="誌", replacement="識",
                          note="題識義通"),
        NormalizationRule(passage_id=p.id, pattern="覌", replacement="曉",
                          note="乙本此處「覌」為「曉」之俗寫，與他本匹配；"
                               "原字形保留於轉錄，不作改字"),
        # 內聯【峯→峰】【觀→覌】在解析層處理；內置表另收 無/峯/後 等
    ])
    db.commit()
