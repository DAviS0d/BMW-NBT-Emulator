precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;
varying vec4 varBasicFade;

/* 
oparam0 ... alpha
*/

void main()
{
    /************** basic ****************/
    vec4 color = texture2D(tex0, varCoord);
    
    gl_FragColor = vec4(color.rgb * 0.5, color.a);
	gl_FragColor.a *= oparam0;
}
