/* © 2026 davisod & JEtsKi
 * nbt-glhost-v2 (bridge v2, host): FNV-1a 64 and lookup of GLSL replacements for NVIDIA binary shaders.
 */
#include "glh.h"
#include <stdio.h>
#include <stdlib.h>

#define GLSL_MAX (1024u * 1024u)

uint64_t glh_fnv1a64(const uint8_t *p, size_t n)
{
    uint64_t h = 14695981039346656037ull;
    for (size_t i = 0; i < n; i++) {
        h ^= p[i];
        h *= 1099511628211ull;
    }
    return h;
}

static char *read_file(const char *path, size_t max, size_t *len)
{
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    char *buf = (char *)malloc(max + 2);
    if (!buf) { fclose(f); return NULL; }
    size_t n = fread(buf, 1, max + 1, f);
    fclose(f);
    if (n > max) { free(buf); return NULL; }
    buf[n] = 0;
    *len = n;
    return buf;
}

int glh_shader_cache_lookup(const char *dir, uint64_t hash, uint32_t length, int *blend, char **glsl)
{
    char base[4096];
    size_t dl = strlen(dir);
    const char *sep = (dl && (dir[dl - 1] == '/' || dir[dl - 1] == '\\')) ? "" : "/";
    if (snprintf(base, sizeof base, "%s%s%016llx-%u", dir, sep, (unsigned long long)hash, length) >= (int)sizeof base - 8)
        return 0;
    char path[4200];
    size_t n = 0;

    snprintf(path, sizeof path, "%s.blend", base);
    char *b = read_file(path, 64, &n);
    if (!b) return 0;
    char *p = b;
    while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n') p++;
    int ok = *p >= '0' && *p <= '9';
    long v = 0;
    while (*p >= '0' && *p <= '9') { v = v * 10 + (*p - '0'); if (v > 1000) break; p++; }
    while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n') p++;
    if (*p != 0 || v > 5) ok = 0;
    free(b);
    if (!ok) return 0;

    snprintf(path, sizeof path, "%s.glsl", base);
    char *src = read_file(path, GLSL_MAX, &n);
    if (!src) return 0;
    if (n < 1) { free(src); return 0; }
    *blend = (int)v;
    *glsl = src;
    return 1;
}
