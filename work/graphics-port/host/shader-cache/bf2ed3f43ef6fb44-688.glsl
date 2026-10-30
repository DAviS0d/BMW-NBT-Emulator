
/**
    This shader receives a modulation color that will be combined with 
    the incomming texture. The incoming texture has the luminance stored as the
    color value which must be put into the alpha canal.
*/

precision mediump float;

varying mediump vec2 vTexCoord;
uniform sampler2D tex0;

uniform vec4 modulationColor;

void main()
{
    gl_FragColor = 
    vec4(
        modulationColor.xyz,
        texture2D(tex0, vec2(vTexCoord.x, vTexCoord.y)).r
        );
}