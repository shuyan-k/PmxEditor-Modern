// PMX 名称的中文对照：日文原名 / 英文对照名 → 中文译名。
// 只用于界面显示与搜索，绝不写回模型数据；未收录的名称返回空（显示原文）。
#pragma once

#include <string>

namespace pmx {

// 与 PMX 里带 name / name_en 的对象一一对应。
enum class NameKind {
    Bone,
    Morph,
    Material,
    Frame,
    Rigid,
    Joint,
    Soft,
    Model,
};

// 返回中文译名；先按日文表匹配 name，再按英文表匹配 name / name_en。
// 刚体 / 关节 / 柔体名称常复用骨骼名或带 `_0_1` 后缀的链名，会先查骨骼表再查材质表。
std::string name_zh(NameKind kind, const std::string& name, const std::string& name_en = {});

// 显示用「原名  中文对照」：未收录或译名与原名相同时只返回原名。
std::string name_with_zh(NameKind kind, const std::string& name,
                         const std::string& name_en = {});

}  // namespace pmx
