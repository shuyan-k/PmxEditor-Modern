// VPD（Vocaloid Pose Data）解析与应用：名称精确匹配优先，其次宽松匹配。
#pragma once

#include <string>
#include <vector>

#include "core/pose.hpp"

namespace pmx {

struct VpdBone {
    std::string name;
    Vec3 pos{};
    Quat rot{};
    int line = 0;
};

struct VpdMorph {
    std::string name;
    float weight = 0.0f;
    int line = 0;
};

struct VpdFile {
    std::vector<VpdBone> bones;
    std::vector<VpdMorph> morphs;
    std::string source;
    std::string encoding;
};

struct VpdMatchResult {
    int matched = 0;
    int total = 0;
    std::vector<std::string> missing;
    std::vector<std::pair<std::string, std::string>> renamed;
    MorphWeights morph_weights;

    bool ok() const { return matched > 0; }
};

// 解码顺序：UTF-8 BOM / UTF-16LE BOM / UTF-8 / 系统本地编码（Windows CP932）。
std::string decode_vpd_text(const std::vector<std::uint8_t>& data, std::string* encoding);
VpdFile parse_vpd_text(const std::string& text, const std::string& source,
                       const std::string& encoding);
VpdFile load_vpd(const std::string& path);

// 把 VPD 姿态写入 pose（位移与旋转覆盖静态姿态），形态权重写入 weights。
VpdMatchResult apply_vpd(const Model& model, Pose& pose, const VpdFile& vpd,
                         MorphWeights* morph_weights);

struct VpdExport {
    std::string path;
    std::string encoding;
    int bones = 0;
    int morphs = 0;
};

// 生成 VPD 文本：默认只导出与静止姿态不同的骨骼，以及非零形态权重。
std::string build_vpd_text(const Model& model, const Pose& pose,
                           const MorphWeights* morph_weights = nullptr,
                           const std::string& model_name = std::string(),
                           bool include_all = false, int digits = 6);

// 写出 VPD：优先 Shift-JIS（CP932），名称无法编码时退回 UTF-8。
VpdExport save_vpd(const std::string& path, const Model& model, const Pose& pose,
                   const MorphWeights* morph_weights = nullptr,
                   const std::string& model_name = std::string(),
                   bool include_all = false);

}  // namespace pmx
