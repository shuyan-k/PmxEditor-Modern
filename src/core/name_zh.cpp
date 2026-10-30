#include "core/name_zh.hpp"

#include <cstdint>
#include <cstring>
#include <iterator>
#include <string>
#include <unordered_map>
#include <vector>

namespace pmx {
namespace {

struct Entry {
    const char* jp;  // 日文原名（PMX 的 name）
    const char* en;  // 英文对照名（PMX 的 name_en），`|` 分隔多个别名，可空
    const char* zh;  // 中文译名
};

const Entry kBones[] = {
    {"全ての親", "all parents|all parent|master|root", "根骨骼"},
    {"センター", "center", "中心"},
    {"グルーブ", "groove", "旋转中心"},
    {"操作中心", "operation center", "操作中心"},
    {"腰", "waist", "腰"},
    {"上半身", "upper body", "上半身"},
    {"上半身2", "upper body2", "上半身2"},
    {"上半身3", "upper body3", "上半身3"},
    {"上半身2_1", "upper body2_1", "上半身2-1"},
    {"上半身2_2", "upper body2_2", "上半身2-2"},
    {"上半身2_3", "upper body2_3", "上半身2-3"},
    {"下半身", "lower body", "下半身"},
    {"下半身2", "lower body2", "下半身2"},
    {"首", "neck", "颈"},
    {"頭", "head", "头"},
    {"顔", "face", "脸"},
    {"胸", "chest|bust", "胸"},
    {"胸1", "chest1", "胸1"},
    {"胸2", "chest2", "胸2"},
    {"胸親", "chest parent", "胸部控制"},
    {"左胸", "left chest|chest.l", "左胸"},
    {"右胸", "right chest|chest.r", "右胸"},
    {"左胸1", "left chest1|chest1.l", "左胸1"},
    {"左胸2", "left chest2|chest2.l", "左胸2"},
    {"右胸1", "right chest1|chest1.r", "右胸1"},
    {"右胸2", "right chest2|chest2.r", "右胸2"},
    {"肩", "shoulder", "肩"},
    {"左肩", "left shoulder|shoulder.l", "左肩"},
    {"右肩", "right shoulder|shoulder.r", "右肩"},
    {"左肩P", "left shoulder p|shoulderp.l", "左肩P"},
    {"右肩P", "right shoulder p|shoulderp.r", "右肩P"},
    {"左肩C", "left shoulder c|shoulderc.l", "左肩C"},
    {"右肩C", "right shoulder c|shoulderc.r", "右肩C"},
    {"腕", "arm", "臂"},
    {"左腕", "left arm|arm.l", "左臂"},
    {"右腕", "right arm|arm.r", "右臂"},
    {"ひじ", "elbow", "肘"},
    {"左ひじ", "left elbow|elbow.l", "左肘"},
    {"右ひじ", "right elbow|elbow.r", "右肘"},
    {"手首", "wrist", "手腕"},
    {"左手首", "left wrist|wrist.l", "左手腕"},
    {"右手首", "right wrist|wrist.r", "右手腕"},
    {"手先", "hand", "手"},
    {"左手先", "left hand|hand.l", "左手"},
    {"右手先", "right hand|hand.r", "右手"},
    {"足", "leg", "腿"},
    {"左足", "left leg|leg.l", "左腿"},
    {"右足", "right leg|leg.r", "右腿"},
    {"ひざ", "knee", "膝"},
    {"左ひざ", "left knee|knee.l", "左膝"},
    {"右ひざ", "right knee|knee.r", "右膝"},
    {"足首", "ankle", "踝"},
    {"左足首", "left ankle|ankle.l", "左踝"},
    {"右足首", "right ankle|ankle.r", "右踝"},
    {"つま先", "toe", "脚尖"},
    {"左つま先", "left toe|toe.l", "左脚尖"},
    {"右つま先", "right toe|toe.r", "右脚尖"},
    {"足先", "toe tip|toetip", "脚尖"},
    {"左足先", "left toe tip|toetip.l", "左脚尖"},
    {"右足先", "right toe tip|toetip.r", "右脚尖"},
    {"足D", "leg d", "腿D"},
    {"左足D", "left leg d|legd.l", "左腿D"},
    {"右足D", "right leg d|legd.r", "右腿D"},
    {"ひざD", "knee d", "膝D"},
    {"左ひざD", "left knee d|kneed.l", "左膝D"},
    {"右ひざD", "right knee d|kneed.r", "右膝D"},
    {"足首D", "ankle d", "踝D"},
    {"左足首D", "left ankle d|ankled.l", "左踝D"},
    {"右足首D", "right ankle d|ankled.r", "右踝D"},
    {"足先EX", "toe ex|toeex", "脚尖EX"},
    {"左足先EX", "left toe ex|toeex.l", "左脚尖EX"},
    {"右足先EX", "right toe ex|toeex.r", "右脚尖EX"},
    {"足先EX先", "toe ex tip|toeextip", "脚尖EX末端"},
    {"左足先EX先", "left toe ex tip|toeextip.l", "左脚尖EX末端"},
    {"右足先EX先", "right toe ex tip|toeextip.r", "右脚尖EX末端"},
    {"足A", "leg a", "腿A"},
    {"左足A", "left leg a|lega.l", "左腿A"},
    {"右足A", "right leg a|lega.r", "右腿A"},
    {"ひざA", "knee a", "膝A"},
    {"左ひざA", "left knee a|kneea.l", "左膝A"},
    {"右ひざA", "right knee a|kneea.r", "右膝A"},
    {"足首A", "ankle a", "踝A"},
    {"左足首A", "left ankle a|anklea.l", "左踝A"},
    {"右足首A", "right ankle a|anklea.r", "右踝A"},
    {"左足IK", "left leg ik|legik.l", "左腿IK"},
    {"右足IK", "right leg ik|legik.r", "右腿IK"},
    {"左つま先IK", "left toe ik|toeik.l", "左脚尖IK"},
    {"右つま先IK", "right toe ik|toeik.r", "右脚尖IK"},
    {"左手IK", "left hand ik|handik.l", "左手IK"},
    {"右手IK", "right hand ik|handik.r", "右手IK"},
    {"目", "eye", "眼"},
    {"左目", "left eye|eye.l", "左眼"},
    {"右目", "right eye|eye.r", "右眼"},
    {"両目", "both eyes|eyes", "双眼"},
    {"眉", "eyebrow", "眉"},
    {"左眉", "left eyebrow|eyebrow.l", "左眉"},
    {"右眉", "right eyebrow|eyebrow.r", "右眉"},
    {"あご", "jaw|chin", "下巴"},
    {"舌", "tongue", "舌"},
    {"唇", "lip", "唇"},
    {"上唇", "upper lip", "上唇"},
    {"下唇", "lower lip", "下唇"},
    {"頬", "cheek", "脸颊"},
    {"左頬", "left cheek|cheek.l", "左脸颊"},
    {"右頬", "right cheek|cheek.r", "右脸颊"},
    {"鼻", "nose", "鼻"},
    {"耳", "ear", "耳"},
    {"左耳", "left ear|ear.l", "左耳"},
    {"右耳", "right ear|ear.r", "右耳"},
    {"髪", "hair", "头发"},
    {"後髪", "back hair", "后发"},
    {"前髪", "front hair|bang|fringe", "刘海"},
    {"横髪", "side hair", "侧发"},
    {"髪1", "hair1", "头发1"},
    {"髪2", "hair2", "头发2"},
    {"アホ毛", "ahoge", "呆毛"},
    {"スカート", "skirt", "裙子"},
    {"前スカート", "front skirt", "前裙"},
    {"後スカート", "back skirt", "后裙"},
    {"左スカート", "left skirt|skirt.l", "左裙"},
    {"右スカート", "right skirt|skirt.r", "右裙"},
    {"胸スペーサー", "chest spacer", "胸部间距"},
    {"下半身マスク", "lower body mask", "下半身遮罩"},
    {"両足", "both legs|legs", "双腿"},
    {"柄", "grip|handle", "握柄"},
    {"武器", "weapon", "武器"},
    {"小物", "prop", "配件"},
    {"アクセサリ", "accessory", "饰品"},
    {"アクセサリ1", "accessory1", "饰品1"},
    {"アクセサリ2", "accessory2", "饰品2"},
    {"左腕捩", "left arm twist|armtwist.l", "左臂扭转"},
    {"右腕捩", "right arm twist|armtwist.r", "右臂扭转"},
    {"左腕捩1", "left arm twist1|armtwist1.l", "左臂扭转1"},
    {"右腕捩1", "right arm twist1|armtwist1.r", "右臂扭转1"},
    {"左腕捩2", "left arm twist2|armtwist2.l", "左臂扭转2"},
    {"右腕捩2", "right arm twist2|armtwist2.r", "右臂扭转2"},
    {"左腕捩3", "left arm twist3|armtwist3.l", "左臂扭转3"},
    {"右腕捩3", "right arm twist3|armtwist3.r", "右臂扭转3"},
    {"左腕捩4", "left arm twist4|armtwist4.l", "左臂扭转4"},
    {"右腕捩4", "right arm twist4|armtwist4.r", "右臂扭转4"},
    {"左手捩", "left hand twist|handtwist.l", "左手扭转"},
    {"右手捩", "right hand twist|handtwist.r", "右手扭转"},
    {"左手首捩", "left wrist twist|wristtwist.l", "左手腕扭转"},
    {"右手首捩", "right wrist twist|wristtwist.r", "右手腕扭转"},
    {"左ひじ捩", "left elbow twist|elbowtwist.l", "左肘扭转"},
    {"右ひじ捩", "right elbow twist|elbowtwist.r", "右肘扭转"},
    {"左肩捩", "left shoulder twist|shouldertwist.l", "左肩扭转"},
    {"右肩捩", "right shoulder twist|shouldertwist.r", "右肩扭转"},
    {"左足捩", "left leg twist|legtwist.l", "左腿扭转"},
    {"右足捩", "right leg twist|legtwist.r", "右腿扭转"},
    {"左足捩1", "left leg twist1|legtwist1.l", "左腿扭转1"},
    {"右足捩1", "right leg twist1|legtwist1.r", "右腿扭转1"},
    {"左足捩2", "left leg twist2|legtwist2.l", "左腿扭转2"},
    {"右足捩2", "right leg twist2|legtwist2.r", "右腿扭转2"},
    {"左足捩3", "left leg twist3|legtwist3.l", "左腿扭转3"},
    {"右足捩3", "right leg twist3|legtwist3.r", "右腿扭转3"},
    {"左足捩4", "left leg twist4|legtwist4.l", "左腿扭转4"},
    {"右足捩4", "right leg twist4|legtwist4.r", "右腿扭转4"},
    {"左ひざ捩", "left knee twist|kneetwist.l", "左膝扭转"},
    {"右ひざ捩", "right knee twist|kneetwist.r", "右膝扭转"},
    {"左足首捩", "left ankle twist|ankletwist.l", "左踝扭转"},
    {"右足首捩", "right ankle twist|ankletwist.r", "右踝扭转"},
    {"左つま先捩", "left toe twist|toetwist.l", "左脚尖扭转"},
    {"右つま先捩", "right toe twist|toetwist.r", "右脚尖扭转"},
    {"左親指", "left thumb|thumb.l", "左拇指"},
    {"右親指", "right thumb|thumb.r", "右拇指"},
    {"左人指", "left index|index.l", "左食指"},
    {"右人指", "right index|index.r", "右食指"},
    {"左中指", "left middle|middle.l", "左中指"},
    {"右中指", "right middle|middle.r", "右中指"},
    {"左薬指", "left ring|ring.l", "左无名指"},
    {"右薬指", "right ring|ring.r", "右无名指"},
    {"左小指", "left pinky|pinky.l|little.l", "左小指"},
    {"右小指", "right pinky|pinky.r|little.r", "右小指"},
    {"左親指1", "left thumb1|thumb1.l", "左拇指1"},
    {"左親指2", "left thumb2|thumb2.l", "左拇指2"},
    {"左親指3", "left thumb3|thumb3.l", "左拇指3"},
    {"右親指1", "right thumb1|thumb1.r", "右拇指1"},
    {"右親指2", "right thumb2|thumb2.r", "右拇指2"},
    {"右親指3", "right thumb3|thumb3.r", "右拇指3"},
    {"左人指1", "left index1|index1.l", "左食指1"},
    {"左人指2", "left index2|index2.l", "左食指2"},
    {"左人指3", "left index3|index3.l", "左食指3"},
    {"右人指1", "right index1|index1.r", "右食指1"},
    {"右人指2", "right index2|index2.r", "右食指2"},
    {"右人指3", "right index3|index3.r", "右食指3"},
    {"左中指1", "left middle1|middle1.l", "左中指1"},
    {"左中指2", "left middle2|middle2.l", "左中指2"},
    {"左中指3", "left middle3|middle3.l", "左中指3"},
    {"右中指1", "right middle1|middle1.r", "右中指1"},
    {"右中指2", "right middle2|middle2.r", "右中指2"},
    {"右中指3", "right middle3|middle3.r", "右中指3"},
    {"左薬指1", "left ring1|ring1.l", "左无名指1"},
    {"左薬指2", "left ring2|ring2.l", "左无名指2"},
    {"左薬指3", "left ring3|ring3.l", "左无名指3"},
    {"右薬指1", "right ring1|ring1.r", "右无名指1"},
    {"右薬指2", "right ring2|ring2.r", "右无名指2"},
    {"右薬指3", "right ring3|ring3.r", "右无名指3"},
    {"左小指1", "left pinky1|pinky1.l", "左小指1"},
    {"左小指2", "left pinky2|pinky2.l", "左小指2"},
    {"左小指3", "left pinky3|pinky3.l", "左小指3"},
    {"右小指1", "right pinky1|pinky1.r", "右小指1"},
    {"右小指2", "right pinky2|pinky2.r", "右小指2"},
    {"右小指3", "right pinky3|pinky3.r", "右小指3"},
    {"手首補助", "wrist helper", "手腕辅助"},
    {"左手首補助", "left wrist helper|wristhelper.l", "左手腕辅助"},
    {"右手首補助", "right wrist helper|wristhelper.r", "右手腕辅助"},
    {"左足首補助", "left ankle helper|anklehelper.l", "左踝辅助"},
    {"右足首補助", "right ankle helper|anklehelper.r", "右踝辅助"},
    {"左肩アーマー", "left shoulder armor|shoulderarmor.l|shoulderarmour.l", "左肩甲"},
    {"右肩アーマー", "right shoulder armor|shoulderarmor.r|shoulderarmour.r", "右肩甲"},
    {"肩アーマー", "shoulder armor|shoulderarmour", "肩甲"},
    {"腰飾り", "waist ornament", "腰部装饰"},
    {"腰キャンセル", "waist cancel", "腰部取消"},
    {"頭D", "head d", "头D"},
    {"首D", "neck d", "颈D"},
    {"肩D", "shoulder d", "肩D"},
    {"左肩D", "left shoulder d|shoulderd.l", "左肩D"},
    {"右肩D", "right shoulder d|shoulderd.r", "右肩D"},
    {"腕D", "arm d", "臂D"},
    {"左腕D", "left arm d|armd.l", "左臂D"},
    {"右腕D", "right arm d|armd.r", "右臂D"},
    {"ひじD", "elbow d", "肘D"},
    {"左ひじD", "left elbow d|elbowd.l", "左肘D"},
    {"右ひじD", "right elbow d|elbowd.r", "右肘D"},
    // 尾巴 / 衣装 / 饰品 / 武器等常见附加骨骼
    {"尻尾", "tail", "尾巴"},
    {"しっぽ", "tail", "尾巴"},
    {"シッポ", "tail", "尾巴"},
    {"ケツ", "butt", "臀部"},
    {"お尻", "butt", "臀部"},
    {"袖", "sleeve", "袖子"},
    {"袖口", "cuff", "袖口"},
    {"ネクタイ", "necktie|tie", "领带"},
    {"リボン", "ribbon", "蝴蝶结"},
    {"蝶ネクタイ", "bow tie|bowtie", "蝴蝶结领带"},
    {"ベルト", "belt", "腰带"},
    {"マフラー", "scarf", "围巾"},
    {"マント", "mantle", "披风"},
    {"ケープ", "cape", "斗篷"},
    {"フード", "hood", "兜帽"},
    {"襟", "collar", "衣领"},
    {"ポケット", "pocket", "口袋"},
    {"ネックレス", "necklace", "项链"},
    {"ペンダント", "pendant", "吊坠"},
    {"イヤリング", "earring", "耳环"},
    {"ピアス", "piercing", "耳钉"},
    {"ヘッドホン", "headphones", "耳机"},
    {"ヘッドセット", "headset", "头戴设备"},
    {"イヤホン", "earphones", "耳塞"},
    {"帽子", "hat", "帽子"},
    {"ハット", "hat", "帽子"},
    {"カチューシャ", "headband", "发箍"},
    {"髪留め", "hairpin", "发夹"},
    {"眼鏡", "glasses", "眼镜"},
    {"サングラス", "sunglasses", "墨镜"},
    {"マスク", "mask", "面罩"},
    {"手袋", "glove|gloves", "手套"},
    {"グローブ", "glove", "手套"},
    {"靴", "shoe|shoes", "鞋子"},
    {"ブーツ", "boot|boots", "靴子"},
    {"ハイヒール", "high heels|heels", "高跟鞋"},
    {"靴下", "socks|sock", "袜子"},
    {"ストッキング", "stockings", "丝袜"},
    {"ニーソ", "knee socks", "过膝袜"},
    {"翼", "wing|wings", "翅膀"},
    {"羽", "feather", "羽毛"},
    {"羽根", "feather", "羽毛"},
    {"角", "horn", "角"},
    {"剣", "sword", "剑"},
    {"刀", "katana", "刀"},
    {"鞘", "sheath", "刀鞘"},
    {"銃", "gun", "枪"},
    {"サーベル", "saber", "军刀"},
    {"杖", "staff|wand", "法杖"},
    {"弓", "bow", "弓"},
    {"矢", "arrow", "箭"},
    {"盾", "shield", "盾"},
    // 四肢与躯干的别称
    {"上腕", "upper arm", "上臂"},
    {"前腕", "forearm", "前臂"},
    {"二の腕", "upper arm", "上臂"},
    {"太もも", "thigh", "大腿"},
    {"腿", "thigh", "大腿"},
    {"脚", "leg", "腿"},
    {"すね", "shin", "小腿"},
    {"脛", "shin", "小腿"},
    {"ふくらはぎ", "calf", "小腿肚"},
    {"かかと", "heel", "脚跟"},
    {"踵", "heel", "脚跟"},
    {"背中", "back", "背部"},
    {"背骨", "spine", "脊骨"},
    {"腹", "belly", "腹部"},
    {"お腹", "belly", "肚子"},
    {"骨盤", "pelvis", "骨盆"},
    {"ウエスト", "waist", "腰围"},
    {"ヒップ", "hip", "臀部"},
    {"肩甲骨", "shoulder blade", "肩胛骨"},
    {"鎖骨", "collarbone", "锁骨"},
    {"うなじ", "nape", "后颈"},
    {"額", "forehead", "额头"},
    {"口", "mouth", "嘴"},
    {"瞳", "pupil", "瞳孔"},
    {"黒目", "iris", "黑眼珠"},
    {"白目", "sclera", "白眼球"},
    {"まつ毛", "eyelashes", "睫毛"},
    {"睫毛", "eyelashes", "睫毛"},
    {"体", "body", "身体"},
    {"体幹", "torso", "躯干"},
    {"胴", "torso", "躯干"},
    {"ギミック", "gimmick", "机关"},
    {"ハンドル", "handle", "把手"},
    {"持ち物", "prop", "道具"},
};

const Entry kMorphs[] = {
    {"まばたき", "blink", "眨眼"},
    {"笑い", "smile", "微笑"},
    {"ウィンク", "wink", "单眼眨眼"},
    {"ウィンク2", "wink2", "单眼眨眼2"},
    {"ウィンク右", "right wink|wink right", "右眼眨眼"},
    {"ウィンク２", "wink2", "单眼眨眼2"},
    {"じと目", "half closed|halfclosed", "半眯眼"},
    {"ジト目", "half closed|halfclosed", "半眯眼"},
    {"怒り", "angry", "生气"},
    {"困り", "troubled", "困扰"},
    {"困る", "troubled", "困扰"},
    {"悲しい", "sad", "悲伤"},
    {"照れ", "shy", "害羞"},
    {"涙", "tears", "眼泪"},
    {"涙2", "tears2", "眼泪2"},
    {"涙目", "teary eyes", "泪眼"},
    {"びっくり", "surprised", "惊讶"},
    {"あ", "a", "啊"},
    {"い", "i", "依"},
    {"う", "u", "呜"},
    {"え", "e", "诶"},
    {"お", "o", "哦"},
    {"あ2", "a2", "啊2"},
    {"い2", "i2", "依2"},
    {"う2", "u2", "呜2"},
    {"え2", "e2", "诶2"},
    {"お2", "o2", "哦2"},
    {"口角上げ", "mouth corners up", "嘴角上扬"},
    {"口角下げ", "mouth corners down", "嘴角下垂"},
    {"にっこり", "grin", "眯眼笑"},
    {"にやり", "smirk", "坏笑"},
    {"真面目", "serious", "认真"},
    {"デフォ子", "default", "默认表情"},
    {"瞳小", "pupil small", "瞳孔缩小"},
    {"瞳大", "pupil large", "瞳孔放大"},
    {"白目", "white eye", "翻白眼"},
    {"閉じ目", "closed eyes", "闭眼"},
    {"眉上げ", "eyebrow up", "挑眉"},
    {"眉下げ", "eyebrow down", "皱眉"},
    {"頬染め", "blush", "脸颊泛红"},
    {"頬膨らみ", "puffed cheeks", "鼓腮"},
    {"ぶどう", "puffed cheeks", "鼓腮"},
    {"むー", "pout", "嘟嘴"},
    {"舌出し", "tongue out", "吐舌"},
    {"発光", "glow", "发光"},
    {"強調", "emphasis", "强调"},
};

const Entry kMaterials[] = {
    {"顔", "face", "脸"},
    {"睫毛", "eyelash|eyelashes", "睫毛"},
    {"目HL", "eye highlight", "眼睛高光"},
    {"瞳透過", "pupil transparent", "透明瞳孔"},
    {"表情デカール", "expression decal", "表情贴花"},
    {"髪_01", "hair 01", "头发 01"},
    {"髪_02", "hair 02", "头发 02"},
    {"肌", "skin", "皮肤"},
    {"肌スフマ", "skin", "皮肤"},
    {"髪", "hair", "头发"},
    {"髪影", "hair shadow", "发影"},
    {"目", "eye", "眼睛"},
    {"瞳", "pupil", "瞳孔"},
    {"白目", "white eye", "眼白"},
    {"眉", "eyebrow", "眉"},
    {"口", "mouth", "口"},
    {"歯", "teeth", "牙齿"},
    {"舌", "tongue", "舌"},
    {"服", "clothes", "服装"},
    {"シャツ", "shirt", "衬衫"},
    {"スカート", "skirt", "裙子"},
    {"靴", "shoes|shoe", "鞋"},
    {"靴下", "socks|sock", "袜子"},
    {"タイツ", "tights", "紧身袜"},
    {"水着", "swimsuit", "泳装"},
    {"下着", "underwear", "内衣"},
    {"透明", "transparent", "透明"},
    {"影", "shadow", "阴影"},
    {"ハイライト", "highlight", "高光"},
    {"ライン", "line", "线条"},
    {"目影", "eye shadow", "眼影"},
    {"ウィッグ", "wig", "假发"},
    {"アクセサリ", "accessory", "饰品"},
};

const Entry kFrames[] = {
    {"標準表示", "standard", "标准表示"},
    {"準標準表示", "semi standard", "准标准表示"},
    {"センター", "center", "中心"},
    {"体", "body", "躯干"},
    {"腕", "arm", "臂"},
    {"足", "leg", "腿"},
    {"髪", "hair", "头发"},
    {"スカート", "skirt", "裙子"},
    {"表情", "expression", "表情"},
    {"アクセサリ", "accessory", "饰品"},
    {"その他", "other", "其他"},
    {"全ての親", "all parents", "根骨骼"},
};

using Table = std::unordered_map<std::string, std::string>;

// 全角 ASCII（U+FF01..U+FF5E）折叠为半角；去掉空格 / 全角空格 / `_ . - ( )`，
// 让「左足ＩＫ」「left_arm.L」「スカート_0_1」这类写法都能命中同一份表。
std::string normalize(const std::string& in, bool fold_case) {
    std::string out;
    out.reserve(in.size());
    for (std::size_t i = 0; i < in.size();) {
        const unsigned char c = static_cast<unsigned char>(in[i]);
        std::uint32_t cp = 0;
        std::size_t len = 0;
        if (c < 0x80) {
            cp = c;
            len = 1;
        } else if ((c & 0xE0) == 0xC0 && i + 1 < in.size()) {
            cp = c & 0x1Fu;
            len = 2;
        } else if ((c & 0xF0) == 0xE0 && i + 2 < in.size()) {
            cp = c & 0x0Fu;
            len = 3;
        } else if ((c & 0xF8) == 0xF0 && i + 3 < in.size()) {
            cp = c & 0x07u;
            len = 4;
        } else {
            ++i;
            continue;
        }
        for (std::size_t k = 1; k < len; ++k)
            cp = (cp << 6) | (static_cast<unsigned char>(in[i + k]) & 0x3Fu);
        i += len;
        if (cp == 0x3000) continue;                     // 全角空格
        if (cp >= 0xFF01 && cp <= 0xFF5E) cp -= 0xFEE0;  // 全角 → 半角
        if (cp == ' ' || cp == '_' || cp == '.' || cp == '-' || cp == '(' || cp == ')') continue;
        if (fold_case && cp >= 'A' && cp <= 'Z') cp += 32;
        if (cp < 0x80) {
            out.push_back(static_cast<char>(cp));
        } else {
            // 还原 UTF-8，保留中日文。
            if (cp < 0x800) {
                out.push_back(static_cast<char>(0xC0 | (cp >> 6)));
                out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
            } else if (cp < 0x10000) {
                out.push_back(static_cast<char>(0xE0 | (cp >> 12)));
                out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
                out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
            } else {
                out.push_back(static_cast<char>(0xF0 | (cp >> 18)));
                out.push_back(static_cast<char>(0x80 | ((cp >> 12) & 0x3F)));
                out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
                out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
            }
        }
    }
    return out;
}

Table build(const Entry* entries, std::size_t count, bool english) {
    Table table;
    table.reserve(count * 2);
    for (std::size_t i = 0; i < count; ++i) {
        const Entry& e = entries[i];
        if (!english) {
            const std::string key = normalize(e.jp, false);
            if (!key.empty()) table.emplace(key, e.zh);
            continue;
        }
        // 英文别名按 `|` 拆分；同一别名重复时保留先出现的译名。
        const char* begin = e.en;
        while (begin && *begin) {
            const char* bar = begin;
            while (*bar && *bar != '|') ++bar;
            const std::string key = normalize(std::string(begin, bar), true);
            if (!key.empty()) table.emplace(key, e.zh);
            begin = *bar ? bar + 1 : nullptr;
        }
    }
    return table;
}

const Table& bones_jp() {
    static const Table t = build(kBones, std::size(kBones), false);
    return t;
}

const Table& bones_en() {
    static const Table t = build(kBones, std::size(kBones), true);
    return t;
}

const Table& morphs_jp() {
    static const Table t = build(kMorphs, std::size(kMorphs), false);
    return t;
}

const Table& morphs_en() {
    static const Table t = build(kMorphs, std::size(kMorphs), true);
    return t;
}

const Table& materials_jp() {
    static const Table t = build(kMaterials, std::size(kMaterials), false);
    return t;
}

const Table& materials_en() {
    static const Table t = build(kMaterials, std::size(kMaterials), true);
    return t;
}

const Table& frames_jp() {
    static const Table t = build(kFrames, std::size(kFrames), false);
    return t;
}

const Table& frames_en() {
    static const Table t = build(kFrames, std::size(kFrames), true);
    return t;
}

std::string find(const Table& table, const std::string& key) {
    if (key.empty()) return {};
    const auto it = table.find(key);
    return it == table.end() ? std::string() : it->second;
}

bool starts_with(const std::string& s, const char* utf8_prefix) {
    const std::size_t n = std::strlen(utf8_prefix);
    return s.size() >= n && s.compare(0, n, utf8_prefix) == 0;
}

bool ends_with(const std::string& s, const char* utf8_suffix) {
    const std::size_t n = std::strlen(utf8_suffix);
    return s.size() >= n && s.compare(s.size() - n, n, utf8_suffix) == 0;
}

// 日文表：精确 → 左/右 前缀 → 扭转 / D / EX / IK / 親 等后缀。
std::string lookup_jp(const Table& table, const std::string& name, int depth) {
    if (depth > 2) return {};
    const std::string key = normalize(name, false);
    if (auto zh = find(table, key); !zh.empty()) return zh;
    if (starts_with(key, "\xE5\xB7\xA6") || starts_with(key, "\xE5\x8F\xB3")) {  // 左 / 右
        const std::string prefix = key.substr(0, 3);
        const std::string rest = key.substr(3);
        if (auto zh = lookup_jp(table, rest, depth + 1); !zh.empty()) return prefix + zh;
    }
    struct Suffix {
        const char* suffix;
        const char* zh;
    };
    static const Suffix kSuffixes[] = {
        {"\xE6\x8D\xB9", "扭转"},          // 捩
        {"\xE6\x8D\xBB\xE3\x82\x8A", "扭转"},  // 捻り
        {"\xE6\x8D\xBB", "扭转"},          // 捻
        {"\xE3\x81\xAD\xE3\x81\x98\xE3\x82\x8A", "扭转"},  // ねじり
        {"\xE8\xA6\xAA", "控制"},          // 親
        {"EX", "EX"},
        {"IK", "IK"},
        {"D", "D"},
        {"P", "P"},
        {"C", "C"},
        {"B", "B"},  // 捩B / 捩1B 这类 B 型变体
    };
    for (const Suffix& s : kSuffixes) {
        if (!ends_with(key, s.suffix)) continue;
        const std::string base = key.substr(0, key.size() - std::strlen(s.suffix));
        if (auto zh = lookup_jp(table, base, depth + 1); !zh.empty()) return zh + s.zh;
    }
    return {};
}

// 英文表：精确 → left/right 前缀 → d / ex / ik / twist / p / c 后缀。
std::string lookup_en(const Table& table, const std::string& name, int depth) {
    if (depth > 2) return {};
    const std::string key = normalize(name, true);
    if (auto zh = find(table, key); !zh.empty()) return zh;
    if (starts_with(key, "left") || starts_with(key, "right")) {
        const bool left = starts_with(key, "left");
        const std::string rest = key.substr(left ? 4 : 5);
        if (auto zh = lookup_en(table, rest, depth + 1); !zh.empty())
            return (left ? "左" : "右") + zh;
    }
    struct Suffix {
        const char* suffix;
        const char* zh;
    };
    static const Suffix kSuffixes[] = {
        {"twist", "扭转"},
        {"ex", "EX"},
        {"ik", "IK"},
        {"d", "D"},
        {"p", "P"},
        {"c", "C"},
        {"b", "B"},  // twistB / twist1B 这类 B 型变体
    };
    for (const Suffix& s : kSuffixes) {
        if (!ends_with(key, s.suffix)) continue;
        const std::string base = key.substr(0, key.size() - std::strlen(s.suffix));
        if (auto zh = lookup_en(table, base, depth + 1); !zh.empty()) return zh + s.zh;
    }
    return {};
}

std::string lookup_pair(const Table& jp, const Table& en, const std::string& name,
                        const std::string& name_en) {
    if (auto zh = lookup_jp(jp, name, 0); !zh.empty()) return zh;
    if (auto zh = lookup_en(en, name, 0); !zh.empty()) return zh;
    if (!name_en.empty()) {
        if (auto zh = lookup_jp(jp, name_en, 0); !zh.empty()) return zh;
        if (auto zh = lookup_en(en, name_en, 0); !zh.empty()) return zh;
    }
    return {};
}

bool all_digits(const std::string& s) {
    if (s.empty()) return false;
    const std::string norm = normalize(s, false);
    if (norm.empty()) return false;
    for (char c : norm)
        if (c < '0' || c > '9') return false;
    return true;
}

// 「スカート_0_1」「髪_01」「左腕捩_0_1」这类链名：剥离尾部数字组，再按基名查表。
std::string lookup_chain(const Table& jp, const Table& en, const std::string& name) {
    std::vector<std::string> groups;
    std::string base = name;
    while (!base.empty()) {
        // 从尾部切出最后一段（`_` / 半角空格 / 全角空格分隔）。
        std::size_t sep = std::string::npos;
        std::size_t sep_len = 1;
        for (std::size_t i = base.size(); i > 0; --i) {
            const std::size_t pos = i - 1;
            if (base[pos] == '_' || base[pos] == ' ') {
                sep = pos;
                break;
            }
            // 全角空格 U+3000 = E3 80 80
            if (pos >= 2 && base[pos - 2] == '\xE3' && base[pos - 1] == '\x80' &&
                base[pos] == '\x80') {
                sep = pos - 2;
                sep_len = 3;
                break;
            }
        }
        const std::size_t start = sep == std::string::npos ? 0 : sep + sep_len;
        const std::string tail = base.substr(start);
        if (!all_digits(tail)) {
            // 没有分隔符时（髪01 / 袖01 / スカート0_1 的基名段），从尾部切出连续数字。
            if (sep != std::string::npos) break;
            std::size_t dstart = tail.size();
            while (dstart > 0) {
                const char c = tail[dstart - 1];
                if (c >= '0' && c <= '9') {
                    --dstart;
                    continue;
                }
                // 全角数字 U+FF10..U+FF19：EF BC 90..99
                if (dstart >= 3 && tail[dstart - 3] == '\xEF' && tail[dstart - 2] == '\xBC' &&
                    tail[dstart - 1] >= '\x90' && tail[dstart - 1] <= '\x99') {
                    dstart -= 3;
                    continue;
                }
                break;
            }
            if (dstart == 0 || dstart == tail.size()) break;
            groups.insert(groups.begin(), normalize(tail.substr(dstart), false));
            base = tail.substr(0, dstart);
            continue;
        }
        groups.insert(groups.begin(), normalize(tail, false));
        if (sep == std::string::npos) {
            base.clear();
        } else {
            base = base.substr(0, sep);
        }
    }
    if (groups.empty()) return {};
    std::string zh = lookup_pair(jp, en, base, std::string());
    if (zh.empty()) return {};
    for (const std::string& g : groups) zh += " " + g;
    return zh;
}

std::string lookup_kind(NameKind kind, const std::string& name, const std::string& name_en) {
    switch (kind) {
        case NameKind::Bone: {
            if (auto zh = lookup_pair(bones_jp(), bones_en(), name, name_en); !zh.empty())
                return zh;
            // 髪_01 / 髪_0_2 / 腕捩_0_1 这类带数字组的骨骼链名。
            return lookup_chain(bones_jp(), bones_en(), name);
        }
        case NameKind::Morph:
            return lookup_pair(morphs_jp(), morphs_en(), name, name_en);
        case NameKind::Material:
            return lookup_pair(materials_jp(), materials_en(), name, name_en);
        case NameKind::Frame:
            return lookup_pair(frames_jp(), frames_en(), name, name_en);
        case NameKind::Rigid:
        case NameKind::Joint:
        case NameKind::Soft: {
            // 刚体 / 关节 / 柔体名多复用骨骼名或带 `_0_1` 后缀的链名。
            if (auto zh = lookup_pair(bones_jp(), bones_en(), name, name_en); !zh.empty())
                return zh;
            if (auto zh = lookup_chain(bones_jp(), bones_en(), name); !zh.empty()) return zh;
            if (auto zh = lookup_pair(materials_jp(), materials_en(), name, name_en); !zh.empty())
                return zh;
            if (auto zh = lookup_chain(materials_jp(), materials_en(), name); !zh.empty())
                return zh;
            return lookup_pair(frames_jp(), frames_en(), name, name_en);
        }
        case NameKind::Model: {
            for (NameKind k : {NameKind::Bone, NameKind::Morph, NameKind::Material,
                               NameKind::Frame}) {
                if (auto zh = lookup_kind(k, name, name_en); !zh.empty()) return zh;
            }
            return {};
        }
    }
    return {};
}

}  // namespace

std::string name_zh(NameKind kind, const std::string& name, const std::string& name_en) {
    return lookup_kind(kind, name, name_en);
}

std::string name_with_zh(NameKind kind, const std::string& name, const std::string& name_en) {
    const std::string zh = name_zh(kind, name, name_en);
    const std::string& base = name.empty() ? name_en : name;
    if (base.empty()) return {};
    if (zh.empty() || zh == base) return base;
    return base + "  " + zh;
}

}  // namespace pmx
