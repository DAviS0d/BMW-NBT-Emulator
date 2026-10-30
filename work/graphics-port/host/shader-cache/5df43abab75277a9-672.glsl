precision mediump float;

varying vec2 vTexCoord;
uniform sampler2D tex0;

uniform float u_ConstAlpha;

void main()
{
    gl_FragColor = texture2D(tex0, vec2(vTexCoord.x, vTexCoord.y));
    // use premultiplied alpha
    gl_FragColor *= u_ConstAlpha;
}
