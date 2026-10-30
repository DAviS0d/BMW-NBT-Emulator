precision mediump float;

varying mediump vec2 vTexCoord;

uniform sampler2D tex0;
uniform float u_ScaleV;
uniform float u_Fade;

void main()
{
    float endFallOff = 0.5 + u_ScaleV/2.0;
    float startFallOff = 0.5 - u_ScaleV/2.0;
    
    float alpha = startFallOff + (vTexCoord.y) * (endFallOff - startFallOff);
    
    alpha = clamp(1.0 - (alpha*7.0),0.0,1.0);
    
    vec4 texColor = texture2D(tex0, vTexCoord);
    gl_FragColor = texColor;
    gl_FragColor.a = texColor.a * alpha * 0.7 * u_Fade;
    
}