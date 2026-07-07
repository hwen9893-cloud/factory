from __future__ import annotations

from typing import Any

from ..base import Skill


class ChapterSkill(Skill):
    name = "skill.novel.chapter"
    required_inputs = ("plot", "knowledge_snapshot")
    required_outputs = ("chapter_id", "ch_no", "title", "body", "word_count")

    def generate(self, state: dict[str, Any]) -> dict[str, Any]:
        plot = state["plot"]
        ch_no = int(plot["ch_no"])
        protagonist = state["knowledge_snapshot"]["characters"][0]["name"]
        title = f"第{ch_no}章 灵根初鸣"
        paragraphs = [
            f"{protagonist}站在青岚宗外门演武场边缘，掌心还残留着昨夜吐纳留下的寒意。",
            "台上铜钟一响，执事淡淡念出试炼名册。那些熟悉的嘲笑声像碎石一样落下来，砸得人心口发闷。",
            "他没有急着争辩，只把袖口往下压了压，遮住腕上那道旧伤。那是三年前灵根破裂时留下的痕迹，也是所有人认定他再无前途的证据。",
            "挑衅他的外门弟子越众而出，故意将木剑点在他脚边。周围人群顿时散开，给这场早有预谋的羞辱让出空地。",
            f"{protagonist}抬眼，第一次没有退。他记得师父说过，修行路上最可怕的不是境界低，而是连拔剑的念头都被别人夺走。",
            "下一息，灵气沿着残破经脉逆冲而上。疼痛像火线钻入骨缝，他却借着这股疼，把第一式青岚剑诀完整递了出去。",
            "木剑相交的声音短促得近乎冷硬。挑衅者脸上的笑还没散去，人已经连退七步，撞翻了身后的兵器架。",
            "演武场静了一瞬。随即，压低的惊呼从四面八方涌来。没人想到，一个被判定灵根残缺的人，还能把青岚剑诀用到这种地步。",
            f"{protagonist}收剑时指尖微颤，旧伤几乎裂开。他知道这不是胜利，只是把自己重新推回了所有人的视线中央。",
            "高台之上，灰袍执事终于睁开眼。那目光没有赞赏，只有审视，像是在衡量一件本不该出现的异物。",
            "钟声第二次响起时，云层压低。更大的试炼还没有开始，而他已经没有退路。",
        ]
        body = "\n\n".join(paragraphs)
        return {
            "chapter_id": f"chapter.ch{ch_no:03d}",
            "ch_no": ch_no,
            "title": title,
            "body": body,
            "word_count": len(body),
            "new_knowledge": [],
            "realm_changes": [],
        }
