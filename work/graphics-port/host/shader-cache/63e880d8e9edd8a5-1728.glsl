precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord,content_coords;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;
varying vec4 varFade;

/* 
oparam0 ... alpha
oparam1 ... content alpha
oparam6 ... edge brightness
*/

void main()
{
    vec4 color = texture2D(tex0, varCoord);
    vec4 basic = color * varFade;
    
    /************ content *********************************/
    vec4 content = texture2D(tex1, content_coords) * oparam1;
    
    gl_FragColor = vec4(basic.rgb * (1.-content.a) + content.rgb, basic.a + content.a);
}
