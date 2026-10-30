/* © 2026 davisod & JEtsKi
 * nbt-glhost-v2 (bridge v2, host): record validation rules of section 5.7 (pure function, unit-testable).
 */
#include "glh.h"

#define NAME_LIMIT (1u << 20)
#define MIB16 (16ull * 1024ull * 1024ull)

/* payload length for fixed-size opcodes; -1 = not a fixed-size opcode */
static int fixed_length(uint32_t op)
{
    switch (op) {
    case 1: return 8;   case 2: return 16;  case 3: return 16;  case 4: return 4;   case 5: return 0;
    case 6: return 0;   case 7: return 8;   case 9: return 4;   case 10: return 4;  case 11: return 8;
    case 12: return 4;  case 13: return 4;  case 16: return 8;  case 19: return 24; case 20: return 4;
    case 21: return 4;  case 29: return 8;  case 30: return 8;  case 31: return 12; case 32: return 16;
    case 33: return 4;  case 34: return 4;  case 35: return 8;  case 36: return 4;  case 37: return 4;
    case 38: return 4;  case 39: return 4;  case 40: return 4;  case 42: return 4;  case 43: return 8;
    case 51: return 8;  case 53: return 12; case 54: return 4;  case 55: return 8;  case 57: return 4;
    case 58: return 12; case 60: return 8;  case 61: return 8;  case 62: return 20; case 63: return 16;
    case 64: return 16; case 65: return 16; case 66: return 16; case 67: return 4;  case 68: return 4;
    case 69: return 12; case 70: return 12; case 71: return 16; case 72: return 4;  case 73: return 8;
    case 75: return 8;  case 76: return 16; case 77: return 16; case 84: return 20; case 85: return 8;
    case 86: return 16; case 87: return 8;  case 102: return 8; case 103: return 8; case 104: return 4;
    case 105: return 0; case 106: return 4; case 107: return 4; case 108: return 8; case 109: return 4;
    case 119: return 4;
    default: return -1;
    }
}

uint32_t glh_normalize_op(uint32_t op, uint32_t len)
{
    return (op == 128 && len == 12) ? 138u : op;
}

static int in_range(int32_t v, int32_t lo, int32_t hi) { return v >= lo && v <= hi; }

static uint32_t index_width(uint32_t type) { return type == 0x1401 ? 1u : type == 0x1403 ? 2u : 4u; }

int glh_validate(uint32_t op, const uint8_t *p, uint32_t L)
{
    int fl = fixed_length(op);
    if (fl >= 0) {
        if (L != (uint32_t)fl) return 0;
        if ((op == 7 || op == 10 || op == 12 || op == 13) && rd_u32(p) >= NAME_LIMIT) return 0;
        if (op == 11 && (rd_u32(p) >= NAME_LIMIT || rd_u32(p + 4) >= NAME_LIMIT)) return 0;
        return 1;
    }
    switch (op) {
    case 8: case 100: case 101:
        return L >= 8 && rd_u32(p) < NAME_LIMIT && rd_u32(p + 4) == L - 8;
    case 14:
        return L >= 12 && rd_u32(p + 8) == L - 12;
    case 15: case 50: case 78: case 79: {
        if (L < 4 || (L - 4) % 4 != 0 || rd_u32(p) != (L - 4) / 4) return 0;
        for (uint32_t i = 4; i < L; i += 4)
            if (rd_u32(p + i) >= NAME_LIMIT) return 0;
        return 1;
    }
    case 17:
        return L >= 12 && (L == 12 || rd_u32(p + 4) == L - 12);
    case 18:
        return L >= 12 && rd_u32(p + 8) == L - 12;
    case 22: case 23: case 24: case 25:
        return L >= 8 && (uint64_t)rd_u32(p + 4) * (op - 21) * 4 == (uint64_t)(L - 8);
    case 26: case 27: case 28: {
        uint64_t k = op - 24;
        return L >= 12 && (uint64_t)rd_u32(p + 4) * k * k * 4 == (uint64_t)(L - 12);
    }
    case 80: case 81: case 82: case 83:
        return L >= 8 && (uint64_t)rd_u32(p + 4) * (op - 79) * 4 == (uint64_t)(L - 8);
    case 52: case 56:
        return L >= 36 && rd_u32(p + 32) == L - 36;
    case 110: {
        if (L < 12) return 0;
        uint64_t cnt = rd_u32(p);
        if (cnt * 4 + rd_u32(p + 8) != (uint64_t)(L - 12)) return 0;
        for (uint64_t i = 0; i < cnt; i++)
            if (rd_u32(p + 12 + 4 * i) >= NAME_LIMIT) return 0;
        return 1;
    }
    case 120:
        return L == 24 && in_range(rd_i32(p + 8), 1, 2048) && in_range(rd_i32(p + 12), 1, 2048) &&
               rd_u32(p + 16) == 0x1908 && rd_u32(p + 20) == 0x1401;
    case 122: case 126:
        return L == 4;
    case 123: case 124:
        return L == 12 && rd_u32(p + 8) <= 4096;
    case 125:
        return L == 4 && rd_u32(p) == 1;
    case 127: {
        if (L < 24) return 0;
        int32_t w = rd_i32(p + 4), h = rd_i32(p + 8);
        if (!in_range(w, 1, 2048) || !in_range(h, 1, 2048) || (w & 1) || (h & 1)) return 0;
        if (!in_range(rd_i32(p + 12), 1, 60)) return 0;
        uint32_t br = rd_u32(p + 16);
        if (br < 64000 || br > 20000000 || rd_u32(p + 20) > 1) return 0;
        return (uint64_t)w * (uint64_t)h * 4 == (uint64_t)(L - 24);
    }
    case 128:
        return L >= 24 && rd_u32(p) < 16 && rd_u32(p + 20) == L - 24;
    case 129:
        return L >= 16 && rd_u32(p + 12) == L - 16 &&
               (uint64_t)rd_u32(p + 4) * index_width(rd_u32(p + 8)) == (uint64_t)(L - 16);
    case 130:
        return L >= 8 && rd_u32(p) <= 3 && (uint64_t)rd_u32(p + 4) * 4 == (uint64_t)(L - 8);
    case 131:
        return L == 28 && in_range(rd_i32(p + 8), 1, 2048) && in_range(rd_i32(p + 12), 1, 2048) &&
               rd_u32(p + 16) == 0x1908 && rd_u32(p + 20) == 0x1401;
    case 132:
        return L == 12 && in_range(rd_i32(p + 4), 1, 2048) && in_range(rd_i32(p + 8), 1, 2048);
    case 133:
        return L == 4;
    case 134:
        return (L == 12 || (L == 16 && rd_u32(p + 12) <= 1)) &&
               in_range(rd_i32(p + 4), 1, 2048) && in_range(rd_i32(p + 8), 1, 2048);
    case 135:
        return L > 8 && (uint64_t)L <= MIB16 + 8 && rd_u32(p + 4) == L - 8;
    case 136:
        return L == 68;
    case 137:
        return L == 4;
    case 138: {
        uint32_t t = L == 12 ? rd_u32(p + 4) : 0;
        return L == 12 && rd_u32(p) <= MIB16 && (t == 0x1401 || t == 0x1403 || t == 0x1405);
    }
    case 139:
        return L >= 28 && rd_i32(p + 24) >= 0 && (L == 28 || 28ull + rd_u32(p + 24) == (uint64_t)L);
    case 140: return L == 32;
    case 141: return L == 8;
    case 142: return L == 4;
    case 143: return L == 8;
    case 144: return L == 28;
    default:
        return 0;
    }
}
