precision mediump float;

varying vec2 vTexCoord;
uniform sampler2D tex0;

void main()
{
    //gl_FragColor = vColor;
    vec4 texColor = texture2D(tex0, vec2(vTexCoord.x, 1.0-vTexCoord.y));
    gl_FragColor = texColor;
    //gl_FragColor = vec4(1., 1., 1., 1.);
}
