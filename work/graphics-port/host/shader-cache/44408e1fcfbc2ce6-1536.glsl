precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/* 
oparam0 ... alpha
oparam6 ... brightness
*/

void main()
{
    vec4 color = texture2D(tex0, varCoord);
    gl_FragColor = oparam0 * vec4(color.rgb * oparam6, color.a);
}