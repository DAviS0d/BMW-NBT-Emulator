precision mediump float;


uniform sampler2D tex0;
uniform float u_ConstAlpha;

varying vec2 vTexCoord;
varying mediump float vFalloff;

void main()
{
    vec4 color = texture2D(tex0, vTexCoord.xy);
    // use premultiplied alpha
    gl_FragColor = color * u_ConstAlpha * clamp( vFalloff, 0., 1. );
}
