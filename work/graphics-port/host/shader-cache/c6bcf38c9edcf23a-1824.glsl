#extension GL_EXT_gpu_shader4 : enable

precision mediump float;

uniform sampler2D uTexture;

uniform float viewPortDimensionX;
uniform float viewPortDimensionY;
varying mediump  vec2 varCoord;


uniform mediump float vx_offset;
mediump float FXAA_SPAN_MAX = 8.0;
mediump float FXAA_REDUCE_MUL = 1.0/8.0;
varying mediump vec4 posPos;

#define FxaaInt2 ivec2
#define FxaaFloat2 vec2
#define FxaaTexLod0(t, p) texture2D(t, p)
//#define FxaaTexOff(t, p, o, r) texture2DLodOffset(t, p, 0.0, o)
#define FxaaTexOff(t, p, o, r) texture2D(t, p + o * r)

lowp vec4 FxaaPixelShader(
  mediump vec4 posPos, // Output of FxaaVertexShader interpolated across screen.
  sampler2D tex, // Input texture.
  mediump vec2 rcpFrame) // Constant {1.0/frameWidth, 1.0/frameHeight}.
{
/*---------------------------------------------------------*/
    #define FXAA_REDUCE_MIN   (1.0/128.0)
    //#define FXAA_REDUCE_MUL   (1.0/8.0)
    //#define FXAA_SPAN_MAX     8.0
/*---------------------------------------------------------*/
   lowp vec3 rgbNW = FxaaTexLod0(tex, posPos.zw).xyz;
   lowp vec3 rgbNE = FxaaTexOff(tex, posPos.zw, FxaaFloat2(1.,0.), rcpFrame.xy).xyz;
   lowp vec3 rgbSW = FxaaTexOff(tex, posPos.zw, FxaaFloat2(0.,1.), rcpFrame.xy).xyz;
   lowp vec3 rgbSE = FxaaTexOff(tex, posPos.zw, FxaaFloat2(1.,1.), rcpFrame.xy).xyz;
   lowp vec3 rgbM  = FxaaTexLod0(tex, posPos.xy).xyz;
/*---------------------------------------------------------*/
    mediump vec3 luma = vec3(0.299, 0.587, 0.114);
    mediump float lumaNW = dot(rgbNW, luma);
    mediump float lumaNE = dot(rgbNE, luma);
    mediump float lumaSW = dot(rgbSW, luma);
    mediump float lumaSE = dot(rgbSE, luma);
    mediump float lumaM  = dot(rgbM,  luma);
/*---------------------------------------------------------*/
    mediump  float lumaMin = min(lumaM, min(min(lumaNW, lumaNE), min(lumaSW, lumaSE)));
    mediump  float lumaMax = max(lumaM, max(max(lumaNW, lumaNE), max(lumaSW, lumaSE)));
/*---------------------------------------------------------*/
    mediump vec2 dir;
    dir.x = -((lumaNW + lumaNE) - (lumaSW + lumaSE));
    dir.y =  ((lumaNW + lumaSW) - (lumaNE + lumaSE));
/*---------------------------------------------------------*/
    mediump float dirReduce = max(
        (lumaNW + lumaNE + lumaSW + lumaSE) * (0.25 * FXAA_REDUCE_MUL),
        FXAA_REDUCE_MIN);
    mediump float rcpDirMin = 1.0/(min(abs(dir.x), abs(dir.y)) + dirReduce);
    dir = min(FxaaFloat2( FXAA_SPAN_MAX,  FXAA_SPAN_MAX),
          max(FxaaFloat2(-FXAA_SPAN_MAX, -FXAA_SPAN_MAX),
          dir * rcpDirMin)) * rcpFrame.xy;
/*--------------------------------------------------------*/
    lowp vec4 rgbA = (1.0/2.0) * (
        FxaaTexLod0(tex, posPos.xy + dir * (1.0/3.0 - 0.5)).rgba +
        FxaaTexLod0(tex, posPos.xy + dir * (2.0/3.0 - 0.5)).rgba);
    lowp vec4 rgbB = rgbA * (1.0/2.0) + (1.0/4.0) * (
        FxaaTexLod0(tex, posPos.xy + dir * (0.0/3.0 - 0.5)).rgba +
        FxaaTexLod0(tex, posPos.xy + dir * (3.0/3.0 - 0.5)).rgba);
    lowp float lumaB = dot(rgbB.xyz, luma);
    if((lumaB < lumaMin) || (lumaB > lumaMax)) return rgbA;
    return rgbB;
}

lowp vec4 PostFX(sampler2D tex, vec2 uv, float time)
{
  lowp vec4 c = vec4(0.0);
  mediump vec2 rcpFrame = vec2(1.0/viewPortDimensionX, 1.0/viewPortDimensionY);
  c.rgba = FxaaPixelShader(posPos, tex, rcpFrame);

  return c;
}

void main()
{
  highp vec2 uv = varCoord.st;
    gl_FragColor = PostFX(uTexture, uv, 0.0);
    //gl_FragColor.a = 1.;
}

