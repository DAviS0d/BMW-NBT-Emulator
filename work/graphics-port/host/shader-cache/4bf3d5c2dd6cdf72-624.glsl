precision mediump float;

varying mediump vec2 vTexCoord;
uniform sampler2D tex0;

void main()
{
    vec4 color = texture2D(tex0, vTexCoord.xy);
    gl_FragColor = vec4(0.0,0.0,0.0,color.r);
}