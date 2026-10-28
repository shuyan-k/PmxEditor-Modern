// 命令行参数解码。
// Windows 的 CRT 按系统 ANSI 代码页解释 main 的 argv（中文系统为 GBK/CP936），
// 直接把 argv 当 UTF-8 路径使用会打不开中文/日文目录。这里改用宽字符命令行
// （GetCommandLineW + CommandLineToArgvW）重新解析，再统一转成 UTF-8。
#pragma once

#include <string>
#include <vector>

namespace pmx {

// 返回 UTF-8 编码的完整参数列表（含 argv[0]）。
std::vector<std::string> utf8_args(int argc, char** argv);

}  // namespace pmx
