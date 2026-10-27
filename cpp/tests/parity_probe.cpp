// 与 Python 版做校验用的命令行探针：读入 PMX、按 C++ 实现写回。
// 用法：
//   pmx_parity_probe info <in.pmx>
//   pmx_parity_probe roundtrip <in.pmx> <out.pmx>
#include <cstdio>
#include <exception>
#include <string>

#include "core/pmx.hpp"

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "用法: pmx_parity_probe info <in.pmx>\n"
                             "      pmx_parity_probe roundtrip <in.pmx> <out.pmx>\n");
        return 2;
    }
    const std::string mode = argv[1];
    try {
        pmx::Model model = pmx::load_pmx(argv[2]);
        if (mode == "info") {
            std::printf("version %.1f encoding %d add_uv %d\n", model.version,
                        model.encoding, model.add_uv_count);
            std::printf("vertices %zu faces %zu materials %zu bones %zu morphs %zu "
                        "frames %zu rigid %zu joints %zu soft %zu textures %zu\n",
                        model.vertices.size(), model.n_faces(), model.materials.size(),
                        model.bones.size(), model.morphs.size(), model.frames.size(),
                        model.rigid.size(), model.joints.size(),
                        model.soft_bodies.size(), model.textures.size());
            return 0;
        }
        if (mode == "roundtrip") {
            if (argc < 4) {
                std::fprintf(stderr, "roundtrip 需要输出路径\n");
                return 2;
            }
            pmx::save_pmx(model, argv[3]);
            std::printf("OK %zu %zu %zu %zu %zu %zu %zu %zu %zu\n",
                        model.vertices.size(), model.n_faces(), model.materials.size(),
                        model.bones.size(), model.morphs.size(), model.frames.size(),
                        model.rigid.size(), model.joints.size(),
                        model.soft_bodies.size());
            return 0;
        }
        std::fprintf(stderr, "未知模式：%s\n", mode.c_str());
        return 2;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "ERR %s\n", e.what());
        return 1;
    }
}
