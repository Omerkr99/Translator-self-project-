#version 300 es

precision highp float;

uniform int u_24shift;
uniform bool u_alpha;
uniform vec2 u_clut;
uniform vec2 u_cornerBR;
uniform vec2 u_cornerTL;
uniform vec2 u_pixelScale;
uniform bool u_hovered;
uniform bool u_greyscale;
uniform bool u_magnify;
uniform float u_magnifyRadius;
uniform float u_magnifyAmount;
uniform bool u_drawGrid;
uniform vec4 u_pixelGridColor;
uniform vec4 u_tpageGridColor;
uniform int u_mode;
uniform float u_monitorDPI;
uniform vec2 u_mousePos;
uniform vec2 u_mouseUV;
uniform vec4 u_readColor;
uniform vec2 u_resolution;
uniform vec2 u_origin;
uniform sampler2D u_vramTexture;
uniform vec4 u_writtenColor;
uniform sampler2D u_readHighlight;
uniform sampler2D u_writtenHighlight;

in vec2 fragUV;
out vec4 outColor;

const float ridge = 1.5f;

const vec4 grey1 = vec4(0.6f, 0.6f, 0.6f, 1.0f);
const vec4 grey2 = vec4(0.8f, 0.8f, 0.8f, 1.0f);

int texelToRaw(in vec4 t) {
    int c = (int(t.r * 31.0f + 0.5f) <<  0) |
            (int(t.g * 31.0f + 0.5f) <<  5) |
            (int(t.b * 31.0f + 0.5f) << 10) |
            (int(t.a) << 15);
    return c;
}

vec4 readTexture(in vec2 pos) {
    vec4 ret = vec4(0.0f);
    if (pos.x > 1.0f) return ret;
    if (pos.y > 1.0f) return ret;
    if (pos.x < 0.0f) return ret;
    if (pos.y < 0.0f) return ret;
    vec2 apos = vec2(1024.0f, 512.0f) * pos;
    vec2 fpos = fract(apos);
    ivec2 ipos = ivec2(apos);

    float scale = 0.0f;
    int p = 0;
    vec4 t = texture(u_vramTexture, pos);
    int c = texelToRaw(t);

    switch (u_mode) {
    case 3:
        {
            ret.a = 1.0f;
            vec4 tb = texture(u_vramTexture, pos - vec2(1.0 / 1024.0f, 0.0f));
            vec4 ta = texture(u_vramTexture, pos + vec2(1.0 / 1024.0f, 0.0f));
            int cb = texelToRaw(tb);
            int ca = texelToRaw(ta);
            switch ((ipos.x + u_24shift) % 3) {
                case 0:
                    ret.r = float((c >> 0) & 0xff) / 255.0f;
                    ret.g = float((c >> 8) & 0xff) / 255.0f;
                    ret.b = float((ca >> 0) & 0xff) / 255.0f;
                    break;
                case 1:
                    if (fpos.x < 0.5f) {
                        ret.r = float((cb >> 0) & 0xff) / 255.0f;
                        ret.g = float((cb >> 8) & 0xff) / 255.0f;
                        ret.b = float((c >> 0) & 0xff) / 255.0f;
                    } else {
                        ret.r = float((c >> 8) & 0xff) / 255.0f;
                        ret.g = float((ca >> 0) & 0xff) / 255.0f;
                        ret.b = float((ca >> 8) & 0xff) / 255.0f;
                    }
                    break;
                case 2:
                    ret.r = float((cb >> 8) & 0xff) / 255.0f;
                    ret.g = float((c >> 0) & 0xff) / 255.0f;
                    ret.b = float((c >> 8) & 0xff) / 255.0f;
                    break;
            }
        }
        break;
    case 2:
        ret = t;
        break;
    case 1:
        scale = 255.0f;
        if (fpos.x < 0.5f) {
            p = (c >> 0) & 0xff;
        } else {
            p = (c >> 8) & 0xff;
        }
        break;
    case 0:
        scale = 15.0f;
        if (fpos.x < 0.25f) {
            p = (c >> 0) & 0xf;
        } else if (fpos.x < 0.5f) {
            p = (c >> 4) & 0xf;
        } else if (fpos.x < 0.75f) {
            p = (c >> 8) & 0xf;
        } else {
            p = (c >> 12) & 0xf;
        }
        break;
    }

    if (u_mode < 2) {
        if (u_greyscale) {
            ret = vec4(float(p) / scale);
            ret.a = 1.0f;
        } else {
            ret = texture(u_vramTexture, u_clut + vec2(float(p) * 1.0f / 1024.0f, 0.0f));
        }
    } else if (u_greyscale) {
        ret = vec4(0.299, 0.587, 0.114, 0.0f) * ret;
        ret = vec4(ret.r + ret.g + ret.b);
        ret.a = 1.0f;
    }

    return ret;
}

float sampleTexture(in sampler2D sampler, in ivec2 pos) {
    if ((pos.x < 0) || (pos.y < 0)) return 0.0;
    if ((pos.x >= 1024) || (pos.y >= 512)) return 0.0;
    return texture(sampler, vec2(float(pos.x) / 1024.0, float(pos.y) / 512.0)).r;
}

float sum9(in sampler2D sampler, in vec2 pos) {
    vec2 apos = vec2(1024.0f, 512.0f) * pos;
    ivec2 ipos = ivec2(apos);
    float sum = 0.0;
    for (int y = -1; y <= 1; y++) {
        for (int x = -1; x <= 1; x++) {
          sum += sampleTexture(sampler, ipos + ivec2(x, y));
        }
    }
    return sum / 9.0;
}

vec4 outlineColor(in sampler2D sampler, in vec4 color, in vec2 pos) {
    float sum = sum9(sampler, pos);
    if ((sum >= 0.999) || (sum <= 0.001)) return vec4(0.0, 0.0, 0.0, 0.0);
    return color;
}

void main() {
    float magnifyAmount = u_magnifyAmount;
    vec2 fragCoord = gl_FragCoord.xy - u_origin;
    vec4 fragColor = readTexture(fragUV.st);
    vec2 pixelPosLinear = vec2(1024.0f, 512.0f) * fragUV.st;
    vec2 pixelPosFractional = fract(pixelPosLinear);
    ivec2 pixelPos = ivec2(pixelPosLinear);
    vec2 magnifyVector = (fragUV.st - u_mouseUV) / u_magnifyAmount;
    vec2 magnifyPos = magnifyVector + u_mouseUV;
    vec4 magnifyColor = readTexture(magnifyPos);

    vec4 readOutline = outlineColor(u_readHighlight, u_readColor, fragUV.st);
    fragColor = mix(fragColor, readOutline, readOutline.a);
    vec4 readOutlineMagnify = outlineColor(u_readHighlight, u_readColor, magnifyPos);
    magnifyColor = mix(magnifyColor, readOutlineMagnify, readOutlineMagnify.a);
    vec4 writtenOutline = outlineColor(u_writtenHighlight, u_writtenColor, fragUV.st);
    fragColor = mix(fragColor, writtenOutline, writtenOutline.a);
    vec4 writtenOutlineMagnify = outlineColor(u_writtenHighlight, u_writtenColor, magnifyPos);
    magnifyColor = mix(magnifyColor, writtenOutlineMagnify, writtenOutlineMagnify.a);
    vec2 mousePos = vec2(u_mousePos.x - u_origin.x * 2.0, u_resolution.y - u_mousePos.y);
    ivec2 mousePixelPos = ivec2(vec2(1024.0f, 512.0f) * u_mouseUV);
#if 0
    if (mousePixelPos == pixelPos) {
        fragColor = vec4(1.0f, 1.0f, 1.0f, 1.0f);
    }
#endif
    bool drawGrid = true;
    if (pixelPosLinear.x > 1024.0f) drawGrid = false;
    if (pixelPosLinear.y > 512.0f) drawGrid = false;
    if (pixelPosLinear.x < 0.0f) drawGrid = false;
    if (pixelPosLinear.y < 0.0f) drawGrid = false;
    bool drawTPageGrid = true;
    if (pixelPosLinear.x > 1030.0f) drawTPageGrid = false;
    if (pixelPosLinear.y > 520.0f) drawTPageGrid = false;
    if (pixelPosLinear.x < 0.0f) drawTPageGrid = false;
    if (pixelPosLinear.y < 0.0f) drawTPageGrid = false;

    if ((drawGrid || drawTPageGrid) && u_drawGrid) {
        vec2 pixelScaleWithMode;
        switch (u_mode) {
        case 0:
            pixelScaleWithMode.x = 4.0f;
            break;
        case 1:
            pixelScaleWithMode.x = 2.0f;
            break;
        case 2:
            pixelScaleWithMode.x = 1.0f;
            break;
        case 3:
            pixelScaleWithMode.x = 2.0f / 3.0f;
            break;
        }
        pixelScaleWithMode.y = 1.0f;

        vec2 tpageGrid = vec2(64.0f, 256.0f);
        vec2 tpagePos = pixelPosLinear / tpageGrid;
        vec2 tpagePosFractional = fract(tpagePos) * tpageGrid;
        vec2 pixelPosWithModeFractional = fract(pixelPosLinear * pixelScaleWithMode) / pixelScaleWithMode;
        vec2 pixelStep = (1.0f / u_pixelScale) / pixelScaleWithMode;
        float tpageGridBlend = smoothstep(0.3f, 0.5f, u_pixelScale.x) * u_tpageGridColor.a;
        float pixelGridBlend = smoothstep(3.0f, 5.0f, u_pixelScale.x) * u_pixelGridColor.a;
        float tpageGridVertLine = 1.0f - step(0.5f, smoothstep(0.0f, pixelStep.x * 4.0f, tpagePosFractional.x));
        float tpageGridHorzLine = 1.0f - step(0.5f, smoothstep(0.0f, pixelStep.y * 4.0f, tpagePosFractional.y));
        float pixelGridVertLine = 1.0f - step(0.5f, smoothstep(0.0f, pixelStep.x * 2.0f, pixelPosWithModeFractional.x));
        float pixelGridHorzLine = 1.0f - step(0.5f, smoothstep(0.0f, pixelStep.y * 2.0f, pixelPosWithModeFractional.y));
        vec4 pixelGridColor = u_pixelGridColor;
        vec4 tpageGridColor = u_tpageGridColor;
        pixelGridColor.a = 1.0f;
        tpageGridColor.a = 1.0f;
        if (drawGrid) {
            fragColor = mix(fragColor, pixelGridColor, pixelGridVertLine * pixelGridBlend);
            fragColor = mix(fragColor, pixelGridColor, pixelGridHorzLine * pixelGridBlend);
        }
        if (pixelPosLinear.y <= 512.0f) {
            fragColor = mix(fragColor, tpageGridColor, tpageGridVertLine * tpageGridBlend);
        }
        if (pixelPosLinear.x <= 1024.0f) {
            fragColor = mix(fragColor, tpageGridColor, tpageGridHorzLine * tpageGridBlend);
        }
    }

    float blend = u_magnify ?
        smoothstep(u_magnifyRadius + ridge, u_magnifyRadius, distance(fragCoord, mousePos)) :
        0.0f;

    outColor = mix(fragColor, magnifyColor, blend);

    if (u_alpha) {
        int x = int(fragCoord.x);
        int y = int(fragCoord.y);
        int info = (x >> 4) + (y >> 4);
        vec4 back = (info & 1) == 0 ? grey1 : grey2;
        outColor = mix(back, outColor, outColor.a);
    }
    outColor.a = 1.0f;
}
