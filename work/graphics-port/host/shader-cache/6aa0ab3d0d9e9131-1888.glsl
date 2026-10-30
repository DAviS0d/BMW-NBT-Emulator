precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord,content_coords,alphaCoord;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;
varying vec4 varBasicFade;

/* 
oparam0 ... alpha
oparam1 ... content alpha
oparam2 ... alpha fall off start
oparam3 ... alpha fall off end
oparam6 ... edge brightness
oparam7 ... content channel scale
*/

void main()
{
    /************** basic ****************/
    vec4 color = texture2D(tex0, varCoord);
    vec4 basic = color * varBasicFade;
    
    
    /************ content **********************************/
    vec4 content = texture2D(tex1, content_coords) * oparam1;
 
    float alphaFalloff = texture2D(tex2, alphaCoord).r;
    content *= alphaFalloff;
    
    gl_FragColor = vec4(basic.rgb * (1. - content.a) + content.rgb, basic.a + content.a);
}
