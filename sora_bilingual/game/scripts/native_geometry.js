// Compiled once by Frida CModule when the resident agent starts.
const NATIVE_GEOMETRY_SOURCE=String.raw`
#include <stdint.h>
#include <float.h>

/*
 * Static ruby geometry batch ABI:
 *   glyphs[i] points at a native glyph.  ranges has lane_count triples:
 *   [primary_start, secondary_start, secondary_end].
 *
 * The caller owns parse lifecycle and invokes this only for simple static
 * ruby.  This routine deliberately has no retained state: each call uses the
 * current glyph colours, so a caller must avoid a repeated call for one parse.
 */

static int finite_float(float value) {
    return value == value && value >= -FLT_MAX && value <= FLT_MAX;
}

static double abs_double(double value) {
    return value < 0.0 ? -value : value;
}

static float read_float(unsigned char *glyph, uint32_t offset) {
    return *(float *)(glyph + offset);
}

static void write_float(unsigned char *glyph, uint32_t offset, float value) {
    *(float *)(glyph + offset) = value;
}

/*
 * Returns zero on success.  Nonzero values identify invalid ABI input and are
 * returned before a glyph is changed: 1 pointer, 2 count, 3 style, 4 glyph,
 * 5 range.
 */
int adjust_static_ruby(void **glyphs, uint32_t count, const uint32_t *ranges,
                       uint32_t lane_count, const float *style) {
    uint32_t i;
    uint32_t previous_end = 0;
    double ruby_gap;
    double ruby_offset_x;
    double color_r;
    double color_g;
    double color_b;
    double opacity;
    double group_offset_y;

    if (glyphs == 0 || ranges == 0 || style == 0) return 1;
    if (count > 32768U || lane_count > count) return 2;
    for (i = 0; i < 7U; ++i) {
        if (!finite_float(style[i])) return 3;
    }
    if (style[2] < 0.0f || style[2] > 1.0f || style[3] < 0.0f ||
        style[3] > 1.0f || style[4] < 0.0f || style[4] > 1.0f ||
        style[5] < 0.0f || style[5] > 1.0f) return 3;

    for (i = 0; i < lane_count; ++i) {
        uint32_t primary_start = ranges[i * 3U];
        uint32_t secondary_start = ranges[i * 3U + 1U];
        uint32_t secondary_end = ranges[i * 3U + 2U];
        if (primary_start > secondary_start || secondary_start >= secondary_end ||
            secondary_end > count || primary_start < previous_end) return 5;
        previous_end = secondary_end;
    }
    /* Validate exactly the fields this invocation owns before the first
     * store. Main-language and unrelated glyph colours may use renderer
     * values outside [0, 1], so they must never make static ruby fail. */
    for (i = 0; i < lane_count; ++i) {
        uint32_t primary_start = ranges[i * 3U];
        uint32_t secondary_start = ranges[i * 3U + 1U];
        uint32_t secondary_end = ranges[i * 3U + 2U];
        uint32_t j;
        for (j = primary_start; j < secondary_start; ++j) {
            unsigned char *glyph = (unsigned char *)glyphs[j];
            if (glyph == 0) return 1;
            if (!finite_float(read_float(glyph, 0x38U)) ||
                !finite_float(read_float(glyph, 0x3cU)) ||
                !finite_float(read_float(glyph, 0x08U)) ||
                !finite_float(read_float(glyph, 0x1cU))) return 4;
        }
        for (j = secondary_start; j < secondary_end; ++j) {
            unsigned char *glyph = (unsigned char *)glyphs[j];
            uint32_t component;
            if (glyph == 0) return 1;
            if (!finite_float(read_float(glyph, 0x38U)) ||
                !finite_float(read_float(glyph, 0x3cU)) ||
                !finite_float(read_float(glyph, 0x08U)) ||
                !finite_float(read_float(glyph, 0x1cU))) return 4;
            for (component = 0; component < 4U; ++component) {
                float color = read_float(glyph, 0x98U + component * 4U);
                if (!finite_float(color) || color < 0.0f || color > 1.0f) return 4;
            }
        }
    }
    if (style[6] != 0.0f) {
        for (i = 0; i < count; ++i) {
            unsigned char *glyph = (unsigned char *)glyphs[i];
            if (glyph == 0 || !finite_float(read_float(glyph, 0x3cU))) return glyph == 0 ? 1 : 4;
        }
    }

    ruby_gap = (double)style[0];
    ruby_offset_x = (double)style[1];
    color_r = (double)style[2];
    color_g = (double)style[3];
    color_b = (double)style[4];
    opacity = (double)style[5];
    group_offset_y = (double)style[6];

    for (i = 0; i < lane_count; ++i) {
        uint32_t primary_start = ranges[i * 3U];
        uint32_t secondary_start = ranges[i * 3U + 1U];
        uint32_t secondary_end = ranges[i * 3U + 2U];
        int have_primary = primary_start < secondary_start;
        int primary_has_bounds = 0;
        double primary_left = DBL_MAX;
        double primary_top = DBL_MAX;
        double secondary_left = DBL_MAX;
        double secondary_bottom = -DBL_MAX;
        uint32_t j;

        if (have_primary) {
            for (j = primary_start; j < secondary_start; ++j) {
                unsigned char *glyph = (unsigned char *)glyphs[j];
                double x;
                double y;
                double width;
                double height;
                if (*(uint32_t *)(glyph + 0xc0U) == 1U) continue;
                x = (double)read_float(glyph, 0x38U);
                y = (double)read_float(glyph, 0x3cU);
                width = abs_double((double)read_float(glyph, 0x08U));
                height = abs_double((double)read_float(glyph, 0x1cU));
                if (x - width / 2.0 < primary_left) primary_left = x - width / 2.0;
                if (y - height / 2.0 < primary_top) primary_top = y - height / 2.0;
                primary_has_bounds = 1;
            }
            /* A primary run containing only icons has no visible main bounds.
             * Match the JavaScript non-finite guard by leaving this lane alone.
             */
            if (!primary_has_bounds) continue;
        }

        for (j = secondary_start; j < secondary_end; ++j) {
            unsigned char *glyph = (unsigned char *)glyphs[j];
            double x = (double)read_float(glyph, 0x38U);
            double y = (double)read_float(glyph, 0x3cU);
            double width = abs_double((double)read_float(glyph, 0x08U));
            double height = abs_double((double)read_float(glyph, 0x1cU));
            if (x - width / 2.0 < secondary_left) secondary_left = x - width / 2.0;
            if (y + height / 2.0 > secondary_bottom) secondary_bottom = y + height / 2.0;
        }

        {
            double dx = have_primary ? primary_left + ruby_offset_x - secondary_left : 0.0;
            double dy = have_primary ? primary_top - ruby_gap - secondary_bottom : 0.0;
            for (j = secondary_start; j < secondary_end; ++j) {
                unsigned char *glyph = (unsigned char *)glyphs[j];
                if (have_primary) {
                    write_float(glyph, 0x38U, (float)((double)read_float(glyph, 0x38U) + dx));
                    write_float(glyph, 0x3cU, (float)((double)read_float(glyph, 0x3cU) + dy));
                }
                write_float(glyph, 0x98U,
                            (float)((double)read_float(glyph, 0x98U) * color_r));
                write_float(glyph, 0x9cU,
                            (float)((double)read_float(glyph, 0x9cU) * color_g));
                write_float(glyph, 0xa0U,
                            (float)((double)read_float(glyph, 0xa0U) * color_b));
                write_float(glyph, 0xa4U,
                            (float)((double)read_float(glyph, 0xa4U) * opacity));
            }
        }
    }

    if (group_offset_y != 0.0) {
        for (i = 0; i < count; ++i) {
            unsigned char *glyph = (unsigned char *)glyphs[i];
            write_float(glyph, 0x3cU,
                        (float)((double)read_float(glyph, 0x3cU) + group_offset_y));
        }
    }
    return 0;
}
`;
