// PMX 2.0 / 2.1 二进制读写，字段顺序与 Python 参考实现完全一致。
#include "core/pmx.hpp"

#include "core/fs.hpp"

#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace pmx {
namespace {

template <typename... Args>
[[noreturn]] void fail(const char* fmt, Args... args) {
    char buf[512];
    std::snprintf(buf, sizeof(buf), fmt, args...);
    throw std::runtime_error(buf);
}

// ---------------------------------------------------------------- 编码
void append_utf8(std::string& out, std::uint32_t cp) {
    if (cp < 0x80) {
        out.push_back(static_cast<char>(cp));
    } else if (cp < 0x800) {
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

std::string utf16le_to_utf8(const std::uint8_t* data, std::size_t bytes) {
    std::string out;
    out.reserve(bytes);
    std::size_t n = bytes / 2;
    for (std::size_t i = 0; i < n; ++i) {
        std::uint32_t cp = static_cast<std::uint32_t>(data[i * 2]) |
                           (static_cast<std::uint32_t>(data[i * 2 + 1]) << 8);
        if (cp >= 0xD800 && cp <= 0xDBFF && i + 1 < n) {
            std::uint32_t lo = static_cast<std::uint32_t>(data[(i + 1) * 2]) |
                               (static_cast<std::uint32_t>(data[(i + 1) * 2 + 1]) << 8);
            if (lo >= 0xDC00 && lo <= 0xDFFF) {
                cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                ++i;
            } else {
                cp = 0xFFFD;
            }
        } else if (cp >= 0xDC00 && cp <= 0xDFFF) {
            cp = 0xFFFD;
        }
        append_utf8(out, cp);
    }
    return out;
}

std::vector<std::uint8_t> utf8_to_utf16le(const std::string& s) {
    std::vector<std::uint8_t> out;
    out.reserve(s.size() * 2);
    auto put = [&out](std::uint32_t u) {
        out.push_back(static_cast<std::uint8_t>(u & 0xFF));
        out.push_back(static_cast<std::uint8_t>((u >> 8) & 0xFF));
    };
    std::size_t i = 0;
    while (i < s.size()) {
        std::uint8_t c = static_cast<std::uint8_t>(s[i]);
        std::uint32_t cp = 0xFFFD;
        std::size_t len = 1;
        if (c < 0x80) {
            cp = c;
        } else if ((c & 0xE0) == 0xC0) {
            len = 2;
            cp = c & 0x1F;
        } else if ((c & 0xF0) == 0xE0) {
            len = 3;
            cp = c & 0x0F;
        } else if ((c & 0xF8) == 0xF0) {
            len = 4;
            cp = c & 0x07;
        }
        if (len > 1 && i + len <= s.size()) {
            bool ok = true;
            for (std::size_t k = 1; k < len; ++k) {
                std::uint8_t cc = static_cast<std::uint8_t>(s[i + k]);
                if ((cc & 0xC0) != 0x80) { ok = false; break; }
                cp = (cp << 6) | (cc & 0x3F);
            }
            if (!ok) { cp = 0xFFFD; len = 1; }
        } else if (len > 1) {
            cp = 0xFFFD;
            len = s.size() - i;
        }
        if (cp >= 0x10000) {
            std::uint32_t v = cp - 0x10000;
            put(0xD800 + (v >> 10));
            put(0xDC00 + (v & 0x3FF));
        } else {
            put(cp);
        }
        i += len;
    }
    return out;
}

// ---------------------------------------------------------------- 读
class Reader {
public:
    Reader(const std::vector<std::uint8_t>& data, int encoding)
        : d_(data), enc_(encoding) {}

    std::size_t offset() const { return o_; }
    void seek(std::size_t o) { o_ = o; }
    std::size_t size() const { return d_.size(); }
    bool eof() const { return o_ >= d_.size(); }

    void need(std::size_t n, const char* what) const {
        if (o_ + n > d_.size())
            fail("PMX 数据截断：读取 %s 需要 %d 字节（偏移 %d，文件 %d 字节）",
                 what, static_cast<int>(n), static_cast<int>(o_),
                 static_cast<int>(d_.size()));
    }

    std::uint8_t u8() { need(1, "u8"); return d_[o_++]; }

    std::uint16_t u16() {
        need(2, "u16");
        std::uint16_t v = static_cast<std::uint16_t>(d_[o_] | (d_[o_ + 1] << 8));
        o_ += 2;
        return v;
    }

    std::int32_t i32() {
        need(4, "i32");
        std::uint32_t v = static_cast<std::uint32_t>(d_[o_]) |
                          (static_cast<std::uint32_t>(d_[o_ + 1]) << 8) |
                          (static_cast<std::uint32_t>(d_[o_ + 2]) << 16) |
                          (static_cast<std::uint32_t>(d_[o_ + 3]) << 24);
        o_ += 4;
        return static_cast<std::int32_t>(v);
    }

    float f32() {
        std::uint32_t bits = static_cast<std::uint32_t>(i32());
        float v;
        std::memcpy(&v, &bits, 4);
        return v;
    }

    Vec3 f3() {
        float x = f32(), y = f32(), z = f32();
        return {x, y, z};
    }

    Vec4 f4() {
        float x = f32(), y = f32(), z = f32(), w = f32();
        return {x, y, z, w};
    }

    int sindex(int width) {
        switch (width) {
            case 1: return static_cast<std::int8_t>(u8());
            case 2: return static_cast<std::int16_t>(u16());
            default: return i32();
        }
    }

    std::uint32_t uindex(int width) {
        switch (width) {
            case 1: return u8();
            case 2: return u16();
            default: {
                std::uint32_t v = static_cast<std::uint32_t>(i32());
                return v;
            }
        }
    }

    std::string text() {
        std::size_t at = o_;
        std::int32_t n = i32();
        if (n < 0 || static_cast<std::size_t>(n) > d_.size() - o_)
            fail("字符串长度非法：%d（偏移 %d）", n, static_cast<int>(at));
        std::string s;
        if (enc_ == 0)
            s = utf16le_to_utf8(d_.data() + o_, static_cast<std::size_t>(n));
        else
            s.assign(reinterpret_cast<const char*>(d_.data() + o_), static_cast<std::size_t>(n));
        o_ += static_cast<std::size_t>(n);
        return s;
    }

    int count(const char* field, int min_size = 0) {
        std::size_t at = o_;
        int n = i32();
        if (n < 0) fail("%s 非法：%d（偏移 %d）", field, n, static_cast<int>(at));
        if (min_size > 0) {
            std::size_t avail = d_.size() > at + 4 ? d_.size() - (at + 4) : 0;
            if (static_cast<std::size_t>(n) > avail / static_cast<std::size_t>(min_size))
                fail("%s 过大：%d（偏移 %d，剩余 %d 字节，每个至少 %d 字节）",
                     field, n, static_cast<int>(at), static_cast<int>(avail), min_size);
        }
        return n;
    }

    const std::vector<std::uint8_t>& raw() const { return d_; }

private:
    const std::vector<std::uint8_t>& d_;
    std::size_t o_ = 0;
    int enc_ = 0;
};

// ---------------------------------------------------------------- 写
class Writer {
public:
    explicit Writer(int encoding) : enc_(encoding) {}

    void u8(int v) { buf_.push_back(static_cast<std::uint8_t>(v & 0xFF)); }

    void u16(int v) {
        buf_.push_back(static_cast<std::uint8_t>(v & 0xFF));
        buf_.push_back(static_cast<std::uint8_t>((v >> 8) & 0xFF));
    }

    void i32(int v) {
        std::uint32_t u = static_cast<std::uint32_t>(v);
        buf_.push_back(static_cast<std::uint8_t>(u & 0xFF));
        buf_.push_back(static_cast<std::uint8_t>((u >> 8) & 0xFF));
        buf_.push_back(static_cast<std::uint8_t>((u >> 16) & 0xFF));
        buf_.push_back(static_cast<std::uint8_t>((u >> 24) & 0xFF));
    }

    void f32(float v) {
        std::uint32_t bits;
        std::memcpy(&bits, &v, 4);
        i32(static_cast<std::int32_t>(bits));
    }

    void f3(Vec3 v) { f32(v.x); f32(v.y); f32(v.z); }
    void f4(Vec4 v) { f32(v.x); f32(v.y); f32(v.z); f32(v.w); }

    void text(const std::string& s) {
        std::vector<std::uint8_t> raw = enc_ == 0 ? utf8_to_utf16le(s)
                                                  : std::vector<std::uint8_t>(s.begin(), s.end());
        i32(static_cast<int>(raw.size()));
        buf_.insert(buf_.end(), raw.begin(), raw.end());
    }

    void sindex(int v, int width) {
        if (width == 1) {
            int c = v < -128 ? -128 : (v > 127 ? 127 : v);
            u8(c);
        } else if (width == 2) {
            int c = v < -32768 ? -32768 : (v > 32767 ? 32767 : v);
            u16(c);
        } else {
            i32(v);
        }
    }

    void uindex(std::uint32_t v, int width) {
        if (width == 1) u8(static_cast<int>(v & 0xFF));
        else if (width == 2) u16(static_cast<int>(v & 0xFFFF));
        else i32(static_cast<int>(v));
    }

    std::vector<std::uint8_t>& buffer() { return buf_; }

private:
    std::vector<std::uint8_t> buf_;
    int enc_ = 0;
};

int size_for(int count, int preferred) {
    int limit = preferred == 1 ? 127 : (preferred == 2 ? 32767 : 2147483647);
    if (count >= 0 && count <= limit) return preferred;
    if (count <= 32767) return 2;
    return 4;
}

std::string crlf(std::string text) {
    if (text.empty()) return text;
    std::string u;
    u.reserve(text.size() + 8);
    for (std::size_t i = 0; i < text.size(); ++i) {
        if (text[i] == '\r') {
            if (i + 1 < text.size() && text[i + 1] == '\n') continue;
            u.push_back('\r');
            u.push_back('\n');
        } else if (text[i] == '\n') {
            u.push_back('\r');
            u.push_back('\n');
        } else {
            u.push_back(text[i]);
        }
    }
    return u;
}

void write_atomic(const std::string& path, const std::vector<std::uint8_t>& data) {
    namespace fs = std::filesystem;
    fs::path target = utf8_path(path);
    fs::path tmp = target;
    tmp += ".tmp";
    {
        std::ofstream f = open_ofstream(utf8_string(tmp));
        if (!f) fail("无法写入文件：%s", path.c_str());
        f.write(reinterpret_cast<const char*>(data.data()),
                static_cast<std::streamsize>(data.size()));
        f.flush();
        if (!f) fail("写入失败：%s", path.c_str());
    }
    std::error_code ec;
    fs::rename(tmp, target, ec);
    if (ec) {
        // 部分文件系统不允许覆盖式 rename，回退为直接写目标。
        std::ofstream f = open_ofstream(path);
        if (!f) fail("无法写入文件：%s", path.c_str());
        f.write(reinterpret_cast<const char*>(data.data()),
                static_cast<std::streamsize>(data.size()));
        std::error_code rm;
        fs::remove(tmp, rm);
    }
}

}  // namespace

Model load_pmx(const std::string& path) {
    std::ifstream f = open_ifstream(path);
    if (!f) fail("无法打开文件：%s", path.c_str());
    std::vector<std::uint8_t> data((std::istreambuf_iterator<char>(f)),
                                   std::istreambuf_iterator<char>());
    if (data.size() < 9 || std::memcmp(data.data(), "PMX ", 4) != 0)
        fail("不是有效的 PMX 文件（文件头应为 'PMX '）");

    Model m;
    m.path = path;
    Reader header(data, 1);
    header.seek(4);
    m.version = std::round(header.f32() * 1000.0f) / 1000.0f;

    std::uint8_t glob_n = header.u8();
    std::size_t glob_at = header.offset();
    if (glob_n < 8 || glob_at + glob_n > data.size())
        fail("全局设置区长度非法：%d（偏移 %d）", glob_n, static_cast<int>(glob_at - 1));
    m.encoding = data[glob_at];
    m.add_uv_count = data[glob_at + 1];
    m.vsz = data[glob_at + 2];
    m.tsz = data[glob_at + 3];
    m.msz = data[glob_at + 4];
    m.bsz = data[glob_at + 5];
    m.mosz = data[glob_at + 6];
    m.rsz = data[glob_at + 7];
    if (m.encoding != 0 && m.encoding != 1)
        fail("文本编码非法：%d（偏移 %d）", m.encoding, static_cast<int>(glob_at));
    if (m.add_uv_count < 0 || m.add_uv_count > 4)
        fail("附加 UV 数非法：%d（偏移 %d）", m.add_uv_count, static_cast<int>(glob_at + 1));
    for (auto [name, width] : {std::pair{"vsz", m.vsz}, std::pair{"tsz", m.tsz},
                               std::pair{"msz", m.msz}, std::pair{"bsz", m.bsz},
                               std::pair{"mosz", m.mosz}, std::pair{"rsz", m.rsz}}) {
        if (width != 1 && width != 2 && width != 4)
            fail("索引宽度 %s 非法：%d", name, width);
    }

    Reader r(data, m.encoding);
    r.seek(glob_at + glob_n);

    m.name = r.text();
    m.name_en = r.text();
    m.comment = r.text();
    m.comment_en = r.text();

    // ---- 顶点（先扫描记录长度，再逐条解析，支持任意权重类型混排）
    const std::size_t pre = 32 + static_cast<std::size_t>(m.add_uv_count) * 16;
    const int bsz = m.bsz;
    const int wlen[5] = {bsz, 2 * bsz + 4, 4 * bsz + 16, 2 * bsz + 4 + 36, 4 * bsz + 16};
    const int reclen[5] = {static_cast<int>(pre) + 1 + wlen[0] + 4,
                           static_cast<int>(pre) + 1 + wlen[1] + 4,
                           static_cast<int>(pre) + 1 + wlen[2] + 4,
                           static_cast<int>(pre) + 1 + wlen[3] + 4,
                           static_cast<int>(pre) + 1 + wlen[4] + 4};
    int nv = r.count("顶点数 nv", reclen[0]);
    std::size_t start = r.offset();
    std::vector<std::size_t> starts(static_cast<std::size_t>(nv));
    std::size_t po = start;
    for (int i = 0; i < nv; ++i) {
        if (po + pre >= data.size())
            fail("顶点数据越界：第 %d 个顶点（偏移 %d）", i, static_cast<int>(po));
        starts[static_cast<std::size_t>(i)] = po;
        std::uint8_t wt = data[po + pre];
        if (wt > 4) fail("未知的顶点权重类型 %d（顶点 %d）", wt, i);
        po += static_cast<std::size_t>(reclen[wt]);
    }
    if (po > data.size())
        fail("顶点数据越界：需要到偏移 %d，文件仅 %d 字节", static_cast<int>(po),
             static_cast<int>(data.size()));
    r.seek(po);

    VertexData& v = m.vertices;
    const std::size_t un = static_cast<std::size_t>(nv);
    v.pos.resize(un);
    v.nrm.resize(un);
    v.uv.resize(un);
    v.add_uv.assign(un * static_cast<std::size_t>(m.add_uv_count) * 4, 0.0f);
    v.edge.resize(un);
    v.wtype.resize(un);
    v.bones.resize(un);
    v.weights.resize(un);
    v.sdef.resize(un);

    for (std::size_t i = 0; i < un; ++i) {
        std::size_t at = starts[i];
        auto atf = [&data, &at]() {
            float x;
            std::memcpy(&x, data.data() + at, 4);
            at += 4;
            return x;
        };
        v.pos[i] = {atf(), atf(), atf()};
        v.nrm[i] = {atf(), atf(), atf()};
        // 注意：Vec2(atf(), atf()) 的实参求值顺序未指定（MSVC 从右往左），
        // 而 atf() 会推进偏移，必须拆成两条语句才能保证 (u, v) 顺序。
        const float u = atf();
        const float uv_v = atf();
        v.uv[i] = Vec2(u, uv_v);
        for (int k = 0; k < m.add_uv_count * 4; ++k) v.add_uv[i * m.add_uv_count * 4 + k] = atf();
        at = starts[i] + pre;
        std::uint8_t wt = data[at++];
        v.wtype[i] = wt;
        auto sref = [&data, &at, bsz]() -> int {
            int value = 0;
            if (bsz == 1) {
                value = static_cast<std::int8_t>(data[at]);
            } else if (bsz == 2) {
                value = static_cast<std::int16_t>(data[at] | (data[at + 1] << 8));
            } else {
                std::uint32_t u = static_cast<std::uint32_t>(data[at]) |
                                  (static_cast<std::uint32_t>(data[at + 1]) << 8) |
                                  (static_cast<std::uint32_t>(data[at + 2]) << 16) |
                                  (static_cast<std::uint32_t>(data[at + 3]) << 24);
                value = static_cast<std::int32_t>(u);
            }
            at += static_cast<std::size_t>(bsz);
            return value;
        };
        auto fref = [&data, &at]() {
            float x;
            std::memcpy(&x, data.data() + at, 4);
            at += 4;
            return x;
        };
        std::array<int, 4>& b4 = v.bones[i];
        std::array<float, 4>& w4 = v.weights[i];
        switch (wt) {
            case WT_BDEF1:
                b4 = {sref(), 0, 0, 0};
                w4 = {1.0f, 0.0f, 0.0f, 0.0f};
                break;
            case WT_BDEF2:
            case WT_SDEF: {
                b4 = {sref(), sref(), 0, 0};
                float w0 = fref();
                w4 = {w0, 1.0f - w0, 0.0f, 0.0f};
                if (wt == WT_SDEF) {
                    std::array<float, 9>& s = v.sdef[i];
                    for (float& fv : s) fv = fref();
                }
                break;
            }
            case WT_BDEF4:
            case WT_QDEF: {
                b4 = {sref(), sref(), sref(), sref()};
                w4 = {fref(), fref(), fref(), fref()};
                break;
            }
            default:
                fail("未知的顶点权重类型 %u（顶点 %d）", wt, static_cast<int>(i));
        }
        v.edge[i] = fref();
    }

    // ---- 面
    int nf = r.count("面索引数 nf", m.vsz);
    m.indices.resize(static_cast<std::size_t>(nf));
    for (int i = 0; i < nf; ++i) {
        std::uint32_t idx = 0;
        if (m.vsz == 1) {
            idx = r.u8();
        } else if (m.vsz == 2) {
            idx = r.u16();
        } else {
            idx = static_cast<std::uint32_t>(r.i32());
        }
        m.indices[static_cast<std::size_t>(i)] = idx;
    }

    // ---- 贴图表
    int nt = r.count("贴图数", 4);
    m.textures.reserve(static_cast<std::size_t>(nt));
    for (int i = 0; i < nt; ++i) m.textures.push_back(r.text());

    // ---- 材质
    int nm = r.count("材质数", 84 + 2 * m.tsz);
    m.materials.reserve(static_cast<std::size_t>(nm));
    for (int i = 0; i < nm; ++i) {
        Material mt;
        mt.name = r.text();
        mt.name_en = r.text();
        mt.diffuse = r.f4();
        mt.specular = r.f3();
        mt.specular_coef = r.f32();
        mt.ambient = r.f3();
        mt.draw_flags = r.u8();
        mt.edge_color = r.f4();
        mt.edge_size = r.f32();
        mt.texture = r.sindex(m.tsz);
        mt.sphere = r.sindex(m.tsz);
        mt.sphere_mode = r.u8();
        mt.toon_shared = r.u8();
        mt.toon = mt.toon_shared == 0 ? r.sindex(m.tsz) : r.u8();
        mt.memo = r.text();
        mt.face_count = r.i32();
        m.materials.push_back(std::move(mt));
    }

    // ---- 骨骼
    int nb = r.count("骨骼数", 26 + m.bsz + (m.bsz < 12 ? m.bsz : 12));
    m.bones.reserve(static_cast<std::size_t>(nb));
    for (int i = 0; i < nb; ++i) {
        Bone b;
        b.name = r.text();
        b.name_en = r.text();
        b.pos = r.f3();
        b.parent = r.sindex(m.bsz);
        b.layer = r.i32();
        b.flags = r.u16();
        if (b.flags & BF_TAIL_INDEX) {
            b.tail_bone = r.sindex(m.bsz);
            b.tail_offset = {0.0f, 0.0f, 0.0f};
        } else {
            b.tail_bone = -1;
            b.tail_offset = r.f3();
        }
        if (b.flags & (BF_INHERIT_ROT | BF_INHERIT_MOV)) {
            b.append_parent = r.sindex(m.bsz);
            b.append_ratio = r.f32();
        }
        if (b.flags & BF_FIXED_AXIS) b.axis = r.f3();
        if (b.flags & BF_LOCAL_AXIS) {
            b.local_x = r.f3();
            b.local_z = r.f3();
        }
        if (b.flags & BF_EXTERNAL_PARENT) b.ext_key = r.i32();
        if (b.flags & BF_IK) {
            IK ik;
            ik.target = r.sindex(m.bsz);
            ik.loop = r.i32();
            ik.angle = r.f32();
            int n = r.count("IK 链接数", m.bsz + 1);
            ik.links.reserve(static_cast<std::size_t>(n));
            for (int k = 0; k < n; ++k) {
                IKLink link;
                link.bone = r.sindex(m.bsz);
                link.limited = r.u8() != 0;
                if (link.limited) {
                    link.lo = r.f3();
                    link.hi = r.f3();
                }
                ik.links.push_back(link);
            }
            b.ik = ik;
        }
        m.bones.push_back(std::move(b));
    }

    // ---- 形态
    int nmo = r.count("形态数", 14);
    m.morphs.reserve(static_cast<std::size_t>(nmo));
    for (int i = 0; i < nmo; ++i) {
        Morph mo;
        mo.name = r.text();
        mo.name_en = r.text();
        mo.panel = r.u8();
        mo.type = r.u8();
        const int t = mo.type;
        int min_off = 1;
        switch (t) {
            case 0: case 9: min_off = m.mosz + 4; break;
            case 1: min_off = m.vsz + 12; break;
            case 2: min_off = m.bsz + 28; break;
            case 3: case 4: case 5: case 6: case 7: min_off = m.vsz + 16; break;
            case 8: min_off = m.msz + 113; break;
            case 10: min_off = m.rsz + 25; break;
            default: min_off = 1; break;
        }
        int n = r.count("形态偏移数", min_off);
        mo.offsets.reserve(static_cast<std::size_t>(n));
        for (int k = 0; k < n; ++k) {
            MorphOffset off;
            if (t == 0 || t == 9) {
                off.morph = r.sindex(m.mosz);
                off.ratio = r.f32();
            } else if (t == 1) {
                off.vertex = static_cast<int>(r.uindex(m.vsz));
                Vec3 o = r.f3();
                off.offset = {o.x, o.y, o.z, 0.0f};
            } else if (t == 2) {
                off.bone = r.sindex(m.bsz);
                off.move = r.f3();
                off.rot = r.f4();
            } else if (t >= 3 && t <= 7) {
                off.vertex = static_cast<int>(r.uindex(m.vsz));
                off.offset = r.f4();
            } else if (t == 8) {
                off.material = r.sindex(m.msz);
                off.calc = r.u8();
                off.diffuse = r.f4();
                off.specular = r.f3();
                off.specular_coef = r.f32();
                off.ambient = r.f3();
                off.edge_color = r.f4();
                off.edge_size = r.f32();
                off.texture = r.f4();
                off.sphere = r.f4();
                off.toon = r.f4();
            } else if (t == 10) {
                off.rigid = r.sindex(m.rsz);
                off.local = r.u8();
                off.velocity = r.f3();
                off.torque = r.f3();
            } else {
                fail("未知形态类型 %d", t);
            }
            mo.offsets.push_back(off);
        }
        m.morphs.push_back(std::move(mo));
    }

    // ---- 显示枠
    int nd = r.count("显示枠数", 13);
    m.frames.reserve(static_cast<std::size_t>(nd));
    for (int i = 0; i < nd; ++i) {
        DisplayFrame frame;
        frame.name = r.text();
        frame.name_en = r.text();
        frame.special = r.u8();
        int n = r.count("显示枠项数", 1 + (m.bsz < m.mosz ? m.bsz : m.mosz));
        frame.items.reserve(static_cast<std::size_t>(n));
        for (int k = 0; k < n; ++k) {
            DisplayFrameItem item;
            item.type = r.u8();
            item.index = item.type == 0 ? r.sindex(m.bsz) : r.sindex(m.mosz);
            frame.items.push_back(item);
        }
        m.frames.push_back(std::move(frame));
    }

    // ---- 刚体
    int nr = r.count("刚体数", 69 + m.bsz);
    m.rigid.reserve(static_cast<std::size_t>(nr));
    for (int i = 0; i < nr; ++i) {
        RigidBody rb;
        rb.name = r.text();
        rb.name_en = r.text();
        rb.bone = r.sindex(m.bsz);
        // MMD（以及 saba 的实现）是把 PMX 的组号直接当 Bullet 的 filterGroup 位
        // （`1 << 组号`），掩码也原样当 filterMask 使用，两者都不做换算。
        // 组号是 1..16，掩码 bit=1 表示「与该组碰撞」（字段名「非衝突グループ」
        // 是历史命名，MMD 实际按碰撞掩码解释）。
        rb.group = r.u8();
        rb.mask = r.u16();
        rb.shape = r.u8();
        rb.size = r.f3();
        rb.pos = r.f3();
        rb.rot = r.f3();
        rb.mass = r.f32();
        rb.mov_damp = r.f32();
        rb.rot_damp = r.f32();
        rb.repel = r.f32();
        rb.friction = r.f32();
        rb.mode = r.u8();
        m.rigid.push_back(std::move(rb));
    }

    // ---- 关节
    int nj = r.count("关节数", 105 + 2 * m.rsz);
    m.joints.reserve(static_cast<std::size_t>(nj));
    for (int i = 0; i < nj; ++i) {
        Joint j;
        j.name = r.text();
        j.name_en = r.text();
        j.type = r.u8();
        j.rigid_a = r.sindex(m.rsz);
        j.rigid_b = r.sindex(m.rsz);
        j.pos = r.f3();
        j.rot = r.f3();
        j.min_loc = r.f3();
        j.max_loc = r.f3();
        j.min_rot = r.f3();
        j.max_rot = r.f3();
        j.spring_loc = r.f3();
        j.spring_rot = r.f3();
        m.joints.push_back(std::move(j));
    }

    // ---- 柔体（PMX 2.1）
    if (m.version >= 2.1f && !r.eof()) {
        int ns = r.count("柔体数", 141 + m.msz);
        m.soft_bodies.reserve(static_cast<std::size_t>(ns));
        for (int i = 0; i < ns; ++i) {
            SoftBody s;
            s.name = r.text();
            s.name_en = r.text();
            s.shape = r.u8();
            s.material = r.sindex(m.msz);
            s.group = r.u8();
            // 同刚体：组号与掩码按 PMX 原样保存。
            s.mask = r.u16();
            s.flags = r.u8();
            s.b_link_dist = r.i32();
            s.cluster_count = r.i32();
            s.total_mass = r.f32();
            s.collision_margin = r.f32();
            s.aero_model = r.i32();
            for (float& fv : s.config) fv = r.f32();
            for (float& fv : s.cluster) fv = r.f32();
            for (int& iv : s.iteration) iv = r.i32();
            for (float& fv : s.material_params) fv = r.f32();
            int na = r.count("柔体锚点数", m.rsz + m.vsz + 1);
            s.anchors.reserve(static_cast<std::size_t>(na));
            for (int k = 0; k < na; ++k) {
                SoftBodyAnchor a;
                a.rigid = r.sindex(m.rsz);
                a.vertex = static_cast<int>(r.uindex(m.vsz));
                a.near = r.u8();
                s.anchors.push_back(a);
            }
            int npin = r.count("柔体固定点数", m.vsz);
            s.pins.reserve(static_cast<std::size_t>(npin));
            for (int k = 0; k < npin; ++k) s.pins.push_back(static_cast<int>(r.uindex(m.vsz)));
            m.soft_bodies.push_back(std::move(s));
        }
    }

    return m;
}

void save_pmx(Model& model, const std::string& path) {
    bool need21 = !model.soft_bodies.empty();
    if (!need21) {
        for (const Morph& mo : model.morphs) {
            if (mo.type >= 9) { need21 = true; break; }
        }
    }
    const float version = need21 ? 2.1f : 2.0f;
    const int nv = static_cast<int>(model.vertices.size());
    const int vsz = nv < 256 ? 1 : (nv < 65536 ? 2 : 4);
    const int tsz = size_for(static_cast<int>(model.textures.size() > 0 ? model.textures.size() : 1), model.tsz);
    const int msz = size_for(static_cast<int>(model.materials.size() > 0 ? model.materials.size() : 1), model.msz);
    const int bsz = size_for(static_cast<int>(model.bones.size() > 0 ? model.bones.size() : 1), model.bsz);
    const int mosz = size_for(static_cast<int>(model.morphs.size() > 0 ? model.morphs.size() : 1), model.mosz);
    const int rsz = size_for(static_cast<int>(model.rigid.size() > 0 ? model.rigid.size() : 1), model.rsz);

    Writer w(model.encoding);
    auto& buf = w.buffer();
    buf.insert(buf.end(), {'P', 'M', 'X', ' '});
    w.f32(version);
    w.u8(8);
    buf.push_back(static_cast<std::uint8_t>(model.encoding));
    buf.push_back(static_cast<std::uint8_t>(model.add_uv_count));
    buf.push_back(static_cast<std::uint8_t>(vsz));
    buf.push_back(static_cast<std::uint8_t>(tsz));
    buf.push_back(static_cast<std::uint8_t>(msz));
    buf.push_back(static_cast<std::uint8_t>(bsz));
    buf.push_back(static_cast<std::uint8_t>(mosz));
    buf.push_back(static_cast<std::uint8_t>(rsz));
    w.text(model.name);
    w.text(model.name_en);
    w.text(crlf(model.comment));
    w.text(crlf(model.comment_en));

    // ---- 顶点
    w.i32(nv);
    const VertexData& v = model.vertices;
    const std::size_t addn = static_cast<std::size_t>(model.add_uv_count) * 4;
    for (int i = 0; i < nv; ++i) {
        const std::size_t k = static_cast<std::size_t>(i);
        w.f3(v.pos[k]);
        w.f3(v.nrm[k]);
        w.f32(v.uv[k].x);
        w.f32(v.uv[k].y);
        for (std::size_t a = 0; a < addn; ++a) w.f32(v.add_uv[k * addn + a]);
        const std::uint8_t wt = v.wtype[k];
        if (wt > 4) fail("未知权重类型 %u", wt);
        w.u8(wt);
        const std::array<int, 4>& b4 = v.bones[k];
        const std::array<float, 4>& w4 = v.weights[k];
        switch (wt) {
            case WT_BDEF1:
                w.sindex(b4[0], bsz);
                break;
            case WT_BDEF2:
            case WT_SDEF:
                w.sindex(b4[0], bsz);
                w.sindex(b4[1], bsz);
                w.f32(w4[0]);
                if (wt == WT_SDEF) {
                    for (float fv : v.sdef[k]) w.f32(fv);
                }
                break;
            case WT_BDEF4:
            case WT_QDEF:
                for (int c = 0; c < 4; ++c) w.sindex(b4[c], bsz);
                for (int c = 0; c < 4; ++c) w.f32(w4[c]);
                break;
            default:
                fail("未知权重类型 %u", wt);
        }
        w.f32(v.edge[k]);
    }

    // ---- 面
    w.i32(static_cast<int>(model.indices.size()));
    for (std::uint32_t idx : model.indices) {
        if (vsz == 1) w.u8(static_cast<int>(idx & 0xFF));
        else if (vsz == 2) w.u16(static_cast<int>(idx & 0xFFFF));
        else w.i32(static_cast<int>(idx));
    }

    // ---- 贴图
    w.i32(static_cast<int>(model.textures.size()));
    for (const std::string& t : model.textures) w.text(t);

    // ---- 材质
    w.i32(static_cast<int>(model.materials.size()));
    for (const Material& mt : model.materials) {
        w.text(mt.name);
        w.text(mt.name_en);
        w.f4(mt.diffuse);
        w.f3(mt.specular);
        w.f32(mt.specular_coef);
        w.f3(mt.ambient);
        w.u8(mt.draw_flags);
        w.f4(mt.edge_color);
        w.f32(mt.edge_size);
        w.sindex(mt.texture, tsz);
        w.sindex(mt.sphere, tsz);
        w.u8(mt.sphere_mode);
        w.u8(mt.toon_shared);
        if (mt.toon_shared == 0) w.sindex(mt.toon, tsz);
        else w.u8(mt.toon);
        w.text(mt.memo);
        w.i32(mt.face_count);
    }

    // ---- 骨骼
    w.i32(static_cast<int>(model.bones.size()));
    for (const Bone& b : model.bones) {
        w.text(b.name);
        w.text(b.name_en);
        w.f3(b.pos);
        w.sindex(b.parent, bsz);
        w.i32(b.layer);
        w.u16(b.flags);
        if (b.flags & BF_TAIL_INDEX) w.sindex(b.tail_bone, bsz);
        else w.f3(b.tail_offset);
        if (b.flags & (BF_INHERIT_ROT | BF_INHERIT_MOV)) {
            w.sindex(b.append_parent, bsz);
            w.f32(b.append_ratio);
        }
        if (b.flags & BF_FIXED_AXIS) w.f3(b.axis);
        if (b.flags & BF_LOCAL_AXIS) {
            w.f3(b.local_x);
            w.f3(b.local_z);
        }
        if (b.flags & BF_EXTERNAL_PARENT) w.i32(b.ext_key);
        if (b.flags & BF_IK) {
            IK none;
            const IK& ik = b.ik ? *b.ik : none;
            w.sindex(ik.target, bsz);
            w.i32(ik.loop);
            w.f32(ik.angle);
            w.i32(static_cast<int>(ik.links.size()));
            for (const IKLink& link : ik.links) {
                w.sindex(link.bone, bsz);
                w.u8(link.limited ? 1 : 0);
                if (link.limited) {
                    w.f3(link.lo);
                    w.f3(link.hi);
                }
            }
        }
    }

    // ---- 形态
    w.i32(static_cast<int>(model.morphs.size()));
    for (const Morph& mo : model.morphs) {
        w.text(mo.name);
        w.text(mo.name_en);
        w.u8(mo.panel);
        w.u8(mo.type);
        w.i32(static_cast<int>(mo.offsets.size()));
        const int t = mo.type;
        for (const MorphOffset& off : mo.offsets) {
            if (t == 0 || t == 9) {
                w.sindex(off.morph, mosz);
                w.f32(off.ratio);
            } else if (t == 1) {
                w.uindex(static_cast<std::uint32_t>(off.vertex), vsz);
                w.f3({off.offset.x, off.offset.y, off.offset.z});
            } else if (t == 2) {
                w.sindex(off.bone, bsz);
                w.f3(off.move);
                w.f4(off.rot);
            } else if (t >= 3 && t <= 7) {
                w.uindex(static_cast<std::uint32_t>(off.vertex), vsz);
                w.f4(off.offset);
            } else if (t == 8) {
                w.sindex(off.material, msz);
                w.u8(off.calc);
                w.f4(off.diffuse);
                w.f3(off.specular);
                w.f32(off.specular_coef);
                w.f3(off.ambient);
                w.f4(off.edge_color);
                w.f32(off.edge_size);
                w.f4(off.texture);
                w.f4(off.sphere);
                w.f4(off.toon);
            } else if (t == 10) {
                w.sindex(off.rigid, rsz);
                w.u8(off.local);
                w.f3(off.velocity);
                w.f3(off.torque);
            }
        }
    }

    // ---- 显示枠
    w.i32(static_cast<int>(model.frames.size()));
    for (const DisplayFrame& f : model.frames) {
        w.text(f.name);
        w.text(f.name_en);
        w.u8(f.special);
        w.i32(static_cast<int>(f.items.size()));
        for (const DisplayFrameItem& item : f.items) {
            w.u8(item.type);
            if (item.type == 0) w.sindex(item.index, bsz);
            else w.sindex(item.index, mosz);
        }
    }

    // ---- 刚体
    w.i32(static_cast<int>(model.rigid.size()));
    for (const RigidBody& rb : model.rigid) {
        w.text(rb.name);
        w.text(rb.name_en);
        w.sindex(rb.bone, bsz);
        w.u8(rb.group);
        w.u16(rb.mask);
        w.u8(rb.shape);
        w.f3(rb.size);
        w.f3(rb.pos);
        w.f3(rb.rot);
        w.f32(rb.mass);
        w.f32(rb.mov_damp);
        w.f32(rb.rot_damp);
        w.f32(rb.repel);
        w.f32(rb.friction);
        w.u8(rb.mode);
    }

    // ---- 关节
    w.i32(static_cast<int>(model.joints.size()));
    for (const Joint& j : model.joints) {
        w.text(j.name);
        w.text(j.name_en);
        w.u8(j.type);
        w.sindex(j.rigid_a, rsz);
        w.sindex(j.rigid_b, rsz);
        w.f3(j.pos);
        w.f3(j.rot);
        w.f3(j.min_loc);
        w.f3(j.max_loc);
        w.f3(j.min_rot);
        w.f3(j.max_rot);
        w.f3(j.spring_loc);
        w.f3(j.spring_rot);
    }

    // ---- 柔体
    if (version >= 2.1f) {
        w.i32(static_cast<int>(model.soft_bodies.size()));
        for (const SoftBody& s : model.soft_bodies) {
            w.text(s.name);
            w.text(s.name_en);
            w.u8(s.shape);
            w.sindex(s.material, msz);
            w.u8(s.group);
            w.u16(s.mask);
            w.u8(s.flags);
            w.i32(s.b_link_dist);
            w.i32(s.cluster_count);
            w.f32(s.total_mass);
            w.f32(s.collision_margin);
            w.i32(s.aero_model);
            for (float fv : s.config) w.f32(fv);
            for (float fv : s.cluster) w.f32(fv);
            for (int iv : s.iteration) w.i32(iv);
            for (float fv : s.material_params) w.f32(fv);
            w.i32(static_cast<int>(s.anchors.size()));
            for (const SoftBodyAnchor& a : s.anchors) {
                w.sindex(a.rigid, rsz);
                w.uindex(static_cast<std::uint32_t>(a.vertex), vsz);
                w.u8(a.near);
            }
            w.i32(static_cast<int>(s.pins.size()));
            for (int vid : s.pins) w.uindex(static_cast<std::uint32_t>(vid), vsz);
        }
    }

    write_atomic(path, buf);
    model.path = path;
    model.version = version;
    model.vsz = vsz;
    model.tsz = tsz;
    model.msz = msz;
    model.bsz = bsz;
    model.mosz = mosz;
    model.rsz = rsz;
}

}  // namespace pmx
